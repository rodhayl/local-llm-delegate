"""Offline CLI routing regressions: no provider calls or real credentials."""
from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1] / "skills" / "local-llm"
sys.path.insert(0, str(TOOLS))
import llm_strong  # noqa: E402
import fleet_review  # noqa: E402


class RoutingTests(unittest.TestCase):
    def invoke(self, env=None, flags=()):
        captured = {}

        def run(args, backend, *, sanitize):
            captured.update(model=args.model, fallbacks=args.fallback_models,
                            escalate=args.escalate_model,
                            escalation_fallbacks=args.escalate_fallbacks,
                            sanitize=sanitize, endpoint=backend.base_url)
            return 0

        variables = {"OPENCODE_API_KEY": "synthetic-test-only", **(env or {})}
        with mock.patch.dict(os.environ, variables, clear=True), \
             mock.patch.object(sys, "argv", ["llm_strong.py", "synthetic text", *flags]), \
             mock.patch.object(llm_strong.llm_local, "run", side_effect=run), \
             mock.patch("urllib.request.urlopen", side_effect=AssertionError("Network forbidden")), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(llm_strong.main(), 0)
        return captured

    def test_private_route_is_not_overridden_by_open_free(self):
        r = self.invoke({"OPENCODE_MODEL": "approved-private", "OPENCODE_MODEL_OPEN": "open-free"})
        self.assertEqual(r["model"], "approved-private")
        self.assertIs(r["sanitize"], llm_strong.redact)
        self.assertIsNone(r["escalate"])

    def test_private_chain_order_is_preserved(self):
        r = self.invoke({"OPENCODE_MODEL": "primary,backup", "OPENCODE_MODEL_OPEN": "other-free"})
        self.assertEqual((r["model"], r["fallbacks"]), ("primary", ["backup"]))

    def test_open_route_is_not_overridden_by_private_free(self):
        r = self.invoke({"OPENCODE_MODEL": "private-free", "OPENCODE_MODEL_OPEN": "open-selected"}, ["--no-privacy", "--no-escalate"])
        self.assertEqual(r["model"], "open-selected")
        self.assertIsNone(r["sanitize"])

    def test_explicit_model_takes_precedence_in_both_modes(self):
        for flags in ([], ["--no-privacy"]):
            with self.subTest(flags=flags):
                r = self.invoke({"OPENCODE_MODEL": "private", "OPENCODE_MODEL_OPEN": "open-free"}, [*flags, "--model", "explicit,explicit-backup"])
                self.assertEqual((r["model"], r["fallbacks"]), ("explicit", ["explicit-backup"]))
                self.assertIsNone(r["escalate"])

    def test_free_model_can_be_explicitly_selected_for_filtered_route(self):
        r = self.invoke({"OPENCODE_MODEL": "chosen-free", "OPENCODE_MODEL_OPEN": "different-free"})
        self.assertEqual(r["model"], "chosen-free")
        self.assertIs(r["sanitize"], llm_strong.redact)

    def test_no_model_configuration_keeps_existing_free_default(self):
        for flags in ([], ["--no-privacy"]):
            with self.subTest(flags=flags):
                r = self.invoke(flags=flags)
                self.assertEqual(r["model"], llm_strong.DEFAULT_STRONG_MODEL)
                self.assertIsNone(r["escalate"])

    def test_open_only_config_does_not_define_filtered_model(self):
        r = self.invoke({"OPENCODE_MODEL_OPEN": "open-only-free"})
        self.assertEqual(r["model"], llm_strong.DEFAULT_STRONG_MODEL)
        self.assertIs(r["sanitize"], llm_strong.redact)

    def test_open_mode_falls_back_to_existing_general_config(self):
        r = self.invoke({"OPENCODE_MODEL": "general"}, ["--no-privacy"])
        self.assertEqual(r["model"], "general")
        self.assertIsNone(r["sanitize"])

    def test_free_open_chain_does_not_add_paid_escalation(self):
        r = self.invoke({"OPENCODE_MODEL": "paid-model", "OPENCODE_MODEL_OPEN": "open-free"}, ["--no-privacy"])
        self.assertEqual(r["model"], "open-free")
        self.assertIsNone(r["escalate"])

    def test_existing_nonfree_open_escalation_can_be_disabled(self):
        env = {"OPENCODE_MODEL": "strong,backup", "OPENCODE_MODEL_OPEN": "small"}
        r = self.invoke(env, ["--no-privacy"])
        self.assertEqual((r["escalate"], r["escalation_fallbacks"]), ("strong", ["backup"]))
        self.assertIsNone(self.invoke(env, ["--no-privacy", "--no-escalate"])["escalate"])

    def test_explicit_mixed_fallback_chain_is_not_reordered(self):
        r = self.invoke(flags=["--model", "approved-free,approved-paid"])
        self.assertEqual((r["model"], r["fallbacks"]), ("approved-free", ["approved-paid"]))
        self.assertIsNone(r["escalate"])

    def test_alias_normalization_is_preserved(self):
        r = self.invoke(flags=["--model", "deepseek/deepseek-v4-flash:free"])
        self.assertEqual(r["model"], llm_strong.DEFAULT_STRONG_MODEL)

    def test_missing_api_key_fails_before_engine(self):
        with self.assertRaisesRegex(SystemExit, "OPENCODE_API_KEY is not set"):
            self.invoke({"OPENCODE_API_KEY": ""})

    def test_dry_run_never_calls_engine(self):
        self.assertEqual(self.invoke(flags=["--dry-run"]), {})

    def test_private_mode_still_blocks_unapproved_tools(self):
        with self.assertRaisesRegex(SystemExit, "tools is blocked"):
            self.invoke(flags=["--tools"])

    def test_conflicting_privacy_flags_still_rejected(self):
        with self.assertRaisesRegex(SystemExit, "confidential-tools is for privacy mode"):
            self.invoke(flags=["--confidential-tools", "--no-privacy"])

    def test_fleet_worker_flag_controls_filtering_not_price(self):
        for filtered in (True, False):
            with self.subTest(filtered=filtered), mock.patch.object(fleet_review.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "synthetic finding", "")) as runner:
                result = fleet_review.run_worker(Path("/synthetic"), ["example.py"], filtered, 120, 10)
                self.assertTrue(result["ok"])
                cmd = runner.call_args.args[0]
                self.assertEqual("--no-privacy" in cmd, not filtered)
                self.assertNotIn("--model", cmd)


if __name__ == "__main__":
    unittest.main()
