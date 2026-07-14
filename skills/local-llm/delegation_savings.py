#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Delegation token-savings report.

Reads the per-call usage JSONL written by llm_local.py / llm_strong.py and prints
a high-level (but granular) view of how many tokens delegation kept OUT of the
main model's context, split by tier and by cost class (free vs paid).

Savings model (deliberately simple, documented so it isn't mistaken for exact
billing): every token a delegate processes is a token the orchestrating "main"
model did NOT have to carry. So for each delegated call:

    offloaded = prompt_tokens + completion_tokens

is the input you did not Read into context PLUS the analysis you did not generate
yourself — you only paid for the short summary you read back. Summed across calls,
`offloaded` is the estimated main-model context saved. Free tiers (local LM Studio
and the OPENCODE_MODEL_OPEN cloud model) cost $0; only the strong privacy-tier
(paid) model bills.

Usage:
    python delegation_savings.py                      # all-time, default log
    python delegation_savings.py --session            # since the last >45min gap
    python delegation_savings.py --since 2026-06-14    # ISO date/datetime cutoff
    python delegation_savings.py --log path.jsonl --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict


def _default_log_path() -> str:
    base = os.environ.get("LLM_DELEGATE_LOG_DIR") or os.path.join(os.getcwd(), ".llm_delegate")
    return os.environ.get("LLM_DELEGATE_LOG") or os.path.join(base, "usage.jsonl")


# Models that are free to call. Local is always free; the cloud "open" tier is too.
# Anything else on the strong tier is treated as paid.
_FREE_HINTS = ("free", "flash-free")


def _is_free(rec: dict) -> bool:
    if rec.get("tier") == "local":
        return True
    model = (rec.get("model") or "").lower()
    # OPENCODE_MODEL_OPEN chain (e.g. deepseek-v4-flash-free) is the free cloud tier.
    open_models = (os.environ.get("OPENCODE_MODEL_OPEN") or "").lower()
    if model and model in open_models:
        return True
    return any(h in model for h in _FREE_HINTS)


def _load(path: str) -> list[dict]:
    recs: list[dict] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    recs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return []
    return recs


def _session_cutoff(recs: list[dict], gap_min: int = 45) -> str | None:
    """Return the ts of the first record in the most recent session.

    A session boundary is any gap > gap_min between consecutive (sorted) records.
    """
    ts = sorted(r.get("ts", "") for r in recs if r.get("ts"))
    if not ts:
        return None
    from datetime import datetime
    cutoff = ts[0]
    for prev, cur in zip(ts, ts[1:]):
        try:
            dp = datetime.fromisoformat(prev)
            dc = datetime.fromisoformat(cur)
        except ValueError:
            continue
        if (dc - dp).total_seconds() > gap_min * 60:
            cutoff = cur
    return cutoff


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", default=_default_log_path(), help="usage JSONL path")
    ap.add_argument("--since", help="ISO date/datetime cutoff (inclusive)")
    ap.add_argument("--session", action="store_true", help="only the most recent session (>45min gap boundary)")
    ap.add_argument("--gap-min", type=int, default=45, help="session gap in minutes for --session")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args()

    recs = _load(args.log)
    if not recs:
        print(f"No delegation usage logged yet at {args.log}", file=sys.stderr)
        return 0

    cutoff = args.since
    if args.session:
        cutoff = _session_cutoff(recs, args.gap_min) or cutoff
    if cutoff:
        recs = [r for r in recs if (r.get("ts") or "") >= cutoff]

    # Aggregate by (tier, free/paid).
    groups: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"calls": 0, "prompt": 0, "completion": 0})
    for r in recs:
        cost = "free" if _is_free(r) else "paid"
        g = groups[(r.get("tier", "?"), cost)]
        g["calls"] += 1
        g["prompt"] += int(r.get("prompt_tokens") or 0)
        g["completion"] += int(r.get("completion_tokens") or 0)

    def offloaded(g):
        return g["prompt"] + g["completion"]

    total_offloaded = sum(offloaded(g) for g in groups.values())
    free_offloaded = sum(offloaded(g) for (t, c), g in groups.items() if c == "free")
    paid_offloaded = sum(offloaded(g) for (t, c), g in groups.items() if c == "paid")
    total_calls = sum(g["calls"] for g in groups.values())

    if args.json:
        out = {
            "log": args.log,
            "since": cutoff,
            "total_calls": total_calls,
            "main_context_tokens_saved_est": total_offloaded,
            "free_offloaded": free_offloaded,
            "paid_offloaded": paid_offloaded,
            "by_group": {f"{t}/{c}": {**g, "offloaded": offloaded(g)} for (t, c), g in sorted(groups.items())},
        }
        print(json.dumps(out, indent=2))
        return 0

    scope = f"since {cutoff}" if cutoff else "all-time"
    print(f"=== Delegation token savings ({scope}) — {total_calls} calls ===")
    print(f"  Est. main-model context tokens SAVED: {total_offloaded:,}")
    print(f"    (= input not read into context + analysis not generated; summaries read back are small)")
    print(f"  Free tiers offloaded (local + OPENCODE_MODEL_OPEN, $0): {free_offloaded:,}")
    print(f"  Paid strong-tier offloaded (privacy model, billed):     {paid_offloaded:,}")
    print(f"  --- breakdown ---")
    for (tier, cost), g in sorted(groups.items()):
        print(f"  {tier:6} {cost:4} | calls={g['calls']:3} prompt={g['prompt']:>9,} "
              f"completion={g['completion']:>8,} offloaded={offloaded(g):>9,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
