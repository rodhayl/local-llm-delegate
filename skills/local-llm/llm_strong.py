"""CLI wrapper for a strong secondary cloud LLM (Opencode Zen, OpenAI-compatible).

Same interface as llm_local.py (it reuses its engine), but targets a
Sonnet-level cloud model for tasks the local model can't be trusted with:
second-opinion verification, nuanced review drafts, cross-file synthesis.

--consult-local gives the strong model a consult_local tool: it can ask the free
local LM Studio model for brainstorming, drafts, or second opinions mid-reasoning.
Safe even in privacy mode: the question is redacted before upload (in privacy mode)
and the local answer is also redacted before upload.

PRIVACY MODE IS ON BY DEFAULT (this sends data to a cloud service):
  - refuses to inline sensitive files (.env*, *secret*, *token*, keys/certs, .ssh, ...);
    extend per-project via LLM_EXTRA_DENY_GLOBS
  - blocks --tools (local execution output can't be audited before upload)
  - blocks -i/--image (pixels can't be redacted)
  - redacts secrets/IPs/emails/account numbers from all outbound text
Pass --no-privacy only for data that is already non-sensitive.

--confidential-tools lets the strong model drive long local jobs (e.g. deploy +
verify the TEST/PROD servers) WITHOUT leaving privacy mode: it enables run_python
but routes EVERY tool output through the same redactor before it is uploaded, so
server IPs / account numbers / secrets in command output never reach the cloud
verbatim. It also raises the per-call subprocess timeout (deploys run ~200s) and
the tool-round cap, and gates run_python so subprocesses may only launch
project-supplied allowlisted scripts (--allow-script / LLM_CONFIDENTIAL_ALLOWED_SCRIPTS).
Use it with a self-contained runbook prompt that names only wrapper-script commands
(no IPs/keys/accounts in the prompt itself) — the project provides the runbook.

Configuration (env vars; set once in ~/.claude/settings.json "env" block):
  OPENCODE_API_KEY    required
  OPENCODE_MODEL      optional fallback legacy setting (or pass --model)
  OPENCODE_MODEL_OPEN optional fallback legacy setting
  Default model for every tier is deepseek-v4-flash-free on the Zen endpoint.
  Historical/provider aliases are normalized to the advertised Opencode model id.
  OPENCODE_BASE_URL   optional, default https://opencode.ai/zen/v1

Usage:
    python llm_strong.py --check
    python llm_strong.py "review this design" -f notes.md --caveman --max-words 120
    git diff | python llm_strong.py "spot logic bugs" --stdin
"""

from __future__ import annotations

import argparse
import fnmatch
import glob
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import llm_local  # noqa: E402

DEFAULT_BASE_URL = "https://opencode.ai/zen/v1"
DEFAULT_STRONG_MODEL = "deepseek-v4-flash-free"
MODEL_ALIASES = {
    "deeepseek-v4-flash-free": DEFAULT_STRONG_MODEL,
    "deepseek/deepseek-v4-flash-free": DEFAULT_STRONG_MODEL,
    "opencode/deepseek-v4-flash-free": DEFAULT_STRONG_MODEL,
    "deepseek/deepseek-v4-flash:free": DEFAULT_STRONG_MODEL,
}

CONFIG_HELP = (
    'Set it once in ~/.claude/settings.json:\n'
    '  { "env": { "OPENCODE_API_KEY": "<key>" } }\n'
    "or as system env vars. OPENCODE_BASE_URL is optional "
    f"(default {DEFAULT_BASE_URL})."
)

# Privacy deny-list: matched case-insensitively against every path segment.
# Generic secret/key/cert patterns. Projects add their own sensitive filenames via
# LLM_EXTRA_DENY_GLOBS=glob1,glob2 (e.g. a runtime config-snapshot pattern) — keeps
# this wrapper portable. `live_config_snapshot_*` kept as a harmless example default.
DENY_GLOBS = [
    ".env*", "*.env", "*secret*", "*credential*", "*token*", "*password*", "*passwd*",
    "*apikey*", "*api_key*", "*api-key*", "*keyring*", "id_*", ".ssh",
    "live_config_snapshot_*", "*.pem", "*.pfx", "*.p12", "*.key",
]


def _deny_globs() -> list[str]:
    extra = os.environ.get("LLM_EXTRA_DENY_GLOBS", "")
    return DENY_GLOBS + [g.strip() for g in extra.split(",") if g.strip()]
# 'key' as a path-segment word (api_key.txt, keys/, my-key.json) without hitting keyboard/monkey.
KEY_WORD_RE = re.compile(r"(?i)(^|[._\-])keys?([._\-]|$)")

_redaction_counts: dict[str, int] = {}


def _count(kind: str) -> None:
    _redaction_counts[kind] = _redaction_counts.get(kind, 0) + 1


def _long_string_sub(m: re.Match) -> str:
    s = m.group(0)
    # Redact high-entropy-looking strings (mixed case + digit) or pure hex (40+ chars).
    # Leaves git SHAs (40 hex, lowercase only) and base64 config values alone.
    if any(c.islower() for c in s) and any(c.isupper() for c in s) and any(c.isdigit() for c in s):
        _count("long-string")
        return "[REDACTED:long-string]"
    if len(s) >= 40 and all(c in "0123456789abcdefABCDEF" for c in s):
        _count("hex-string")
        return "[REDACTED:hex-string]"
    return s


REDACT_RULES = [
    # bearer/jwt must run before secret-kv: "Authorization: Bearer <jwt>" would otherwise
    # have only the word "Bearer" eaten as the kv value, leaving the token exposed.
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+"), "[REDACTED:bearer]"),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"), "[REDACTED:jwt]"),
    ("secret-kv", re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password|passwd|authorization|access[_-]?key|private[_-]?key)"
        r"\b(\s*[:=]\s*)(?!\[REDACTED:)(\S+)"), r"\1\2[REDACTED:secret-kv]"),
    ("token-like", re.compile(r"\b(?:sk|pk|rk|ghp|gho|ghu|xox[a-z])[-_][A-Za-z0-9_\-]{16,}\b"), "[REDACTED:token-like]"),
    # AWS access-key IDs concatenate directly after the prefix (no separator), 20 chars
    # total — too short for the long-string rule, so they need their own pattern.
    ("aws-key", re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ABIA|ACCA)[0-9A-Z]{16}\b"), "[REDACTED:aws-key]"),
    ("google-api", re.compile(r"\bAIza[A-Za-z0-9_\-]{35}\b"), "[REDACTED:google-api]"),
    ("github-pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{50,}\b"), "[REDACTED:github-pat]"),
    ("basic-auth", re.compile(r"(?i)\bbasic\s+[A-Za-z0-9+/=]{20,}"), "[REDACTED:basic-auth]"),
    ("ssh-key", re.compile(r"-----BEGIN[A-Z ]+PRIVATE KEY-----[\s\S]*?-----END[A-Z ]+PRIVATE KEY-----"), "[REDACTED:ssh-key]"),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"), "[REDACTED:email]"),
    ("ipv4", re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "[REDACTED:ipv4]"),
    ("account", re.compile(r"(?i)\b(login|account)(\s*[:=]\s*)(\d{5,})"), r"\1\2[REDACTED:account]"),
]
LONG_STRING_RE = re.compile(r"\b[A-Za-z0-9+/=_\-]{40,}\b")


def redact(text: str) -> str:
    if not text:
        return text
    for kind, rx, repl in REDACT_RULES:
        def _sub(m, kind=kind, repl=repl):
            _count(kind)
            return m.expand(repl)
        text = rx.sub(_sub, text)
    text = LONG_STRING_RE.sub(_long_string_sub, text)
    if _redaction_counts:
        summary = " ".join(f"{k}={v}" for k, v in sorted(_redaction_counts.items()))
        print(f"[privacy] redacted: {summary}", file=sys.stderr)
        _redaction_counts.clear()
    return text


def denied_pattern(path: str) -> str | None:
    globs = _deny_globs()
    # Refuse symlinks — their target may be a sensitive file with a non-sensitive name
    try:
        if Path(path).is_symlink():
            return "symlink"
    except OSError:
        return "symlink-error"
    for seg in Path(path).resolve().parts:
        s = seg.lower()
        for g in globs:
            if fnmatch.fnmatch(s, g):
                return g
        if KEY_WORD_RE.search(s):
            return "key-segment"
    return None


CONSULT_SPEC = {
    "type": "function",
    "function": {
        "name": "consult_local",
        "description": (
            "Ask a free local assistant model (qwen3.6-35b) a self-contained question: "
            "brainstorm alternatives, request a draft, or get a second opinion. "
            "Treat its reply as a suggestion to verify, not as fact."
        ),
        "parameters": {
            "type": "object",
            "properties": {"question": {"type": "string", "description": "Self-contained question or task"}},
            "required": ["question"],
        },
    },
}
CONSULT_NOTE = (
    " You also have a consult_local tool: a free local assistant model. Use it when a second "
    "opinion, brainstorm, or delegated draft would help; verify its suggestions yourself."
)
_privacy_on = True


def _canonical_model_name(name: str) -> str:
    model = name.strip()
    return MODEL_ALIASES.get(model.lower(), model)


def _model_chain(raw: str) -> list[str]:
    return [_canonical_model_name(m) for m in raw.split(",") if m.strip()]


def _contains_free_model(chain: list[str]) -> bool:
    return any("-free" in m.lower() for m in chain)


def _consult_local(arguments: dict, tag: str) -> str:
    question = str(arguments.get("question", "")).strip()
    if not question:
        return "error: empty question"
    print(f"[{tag}tool] consult_local ({len(question)} chars)", file=sys.stderr)
    sub = argparse.Namespace(
        model=llm_local.DEFAULT_MODEL, max_tokens=4096, temperature=0.2, timeout=300,
        tools=False, extra_tool_specs=None, caveman=True, system=None,
        show_reasoning=False, no_retry=False,
    )
    try:
        send_question = redact(question) if _privacy_on else question
        answer = llm_local.call_llm(sub, send_question + "\nAnswer in <= 200 words.",
                                    llm_local.local_backend(), tag=f"{tag}consult ")
    except SystemExit as exc:
        return f"consult_local unavailable: {exc}"
    answer = answer or "(no answer)"
    return redact(answer) if _privacy_on else answer


# Confidential-tools guard: capability containment for the cloud model running
# run_python (e.g. driving a deploy). Confidentiality is handled by redaction; this
# limits BLAST RADIUS — destructive / exfiltrating / repo-mutating code is refused, and
# any subprocess must invoke a caller-supplied allowlisted script. Defense-in-depth, not
# a sandbox. The allowlist is PROJECT-SUPPLIED (keeps this wrapper generic/portable):
# pass --allow-script NAME (repeatable) and/or set LLM_CONFIDENTIAL_ALLOWED_SCRIPTS=a,b.
DEPLOY_DENY_PATTERNS = [
    r"rm\s+-rf?", r"shutil\.rmtree", r"os\.remove", r"os\.unlink", r"os\.rmdir",
    r"\bmkfs\b", r"\bdd\b", r">\s*/dev/", r"chmod\s+777", r"\bshutdown\b", r"\breboot\b",
    r"git\s+(push|commit|reset|checkout|clean|rm)", r"--force\b", r"--hard\b",
    r"\bcurl\b", r"\bwget\b", r"requests\.", r"urllib\.request", r"\bsocket\b", r"ftplib",
    r"/etc/", r"id_ed25519", r"id_rsa", r"\.ssh\b", r"\.env\b",
    r"secret", r"password", r"private[_-]?key", r"base64\.b64decode",
    r"getattr\s*\(", r"__import__\s*\(", r"\bexec\s*\(", r"\beval\s*\(",
    r"\bos\.system\b", r"\bos\.popen\b",
]


def allowed_scripts_from(args) -> list[str]:
    """Build the subprocess allowlist from --allow-script and the env var (generic)."""
    scripts = list(getattr(args, "allow_script", None) or [])
    env = os.environ.get("LLM_CONFIDENTIAL_ALLOWED_SCRIPTS", "")
    scripts += [s.strip() for s in env.split(",") if s.strip()]
    return scripts


def deploy_guard(code: str, allowed_scripts: list[str]) -> str | None:
    """Return a refusal reason if `code` is outside the guard, else None.
    `allowed_scripts` is caller-supplied (no project names hardcoded here).
    Defense-in-depth, not a sandbox — determined code can bypass regex patterns."""
    for pat in DEPLOY_DENY_PATTERNS:
        if re.search(pat, code, re.IGNORECASE):
            return (f"REFUSED by guard: code matches denied pattern /{pat}/. "
                    "Only run the allowlisted wrapper commands from the runbook.")
    if re.search(r"subprocess|os\.system|os\.popen|\bPopen\b", code):
        if not allowed_scripts:
            return ("REFUSED by guard: subprocess launching is blocked because no allowlist "
                    "is configured. Pass --allow-script NAME or set "
                    "LLM_CONFIDENTIAL_ALLOWED_SCRIPTS.")
        if not any(s in code for s in allowed_scripts):
            return ("REFUSED by guard: a subprocess must invoke an allowlisted wrapper "
                    f"({', '.join(allowed_scripts)}). No other commands.")
    return None


def _guarded_redacting_python(handler, allowed_scripts: list[str]):
    """run_python wrapper for confidential-tools: guard first, then redact."""
    def wrapped(arguments, tag, _h=handler):
        refusal = deploy_guard(str(arguments.get("code", "")), allowed_scripts)
        if refusal:
            print(f"[{tag}guard] {refusal[:80]}", file=sys.stderr)
            return refusal
        return redact(_h(arguments, tag))
    return wrapped


def _redacting_handler(handler):
    """Wrap a tool handler so its output is redacted before it is uploaded to
    the cloud model. This is what makes --tools safe under privacy mode."""
    def wrapped(arguments, tag, _h=handler):
        return redact(_h(arguments, tag))
    return wrapped


def prep_confidential_tools(args) -> None:
    """Enable run_python under privacy mode with a deploy-friendly subprocess
    timeout and a raised tool-round cap so a multi-step deploy+verify of both
    servers can complete in one delegation. Call BEFORE the consult-local block
    so the tools system prompt is selected. Handler redaction is applied
    separately (after all handlers are registered) by wrap_tool_handlers()."""
    args.tools = True
    llm_local.RUN_PYTHON_TIMEOUT = 1500  # deploys cold-start ~200s; allow headroom
    if not args.max_tool_rounds:
        args.max_tool_rounds = 30


def wrap_tool_handlers(allowed_scripts: list[str]) -> None:
    """Route EVERY registered tool output through the redactor before upload, and
    gate run_python through the guard. Call AFTER all handlers (incl. consult_local)
    are registered. This is what makes --tools safe under privacy mode."""
    for name, handler in list(llm_local.TOOL_HANDLERS.items()):
        if name == "consult_local":
            continue  # already redacts its own output internally (avoid a wasteful double pass)
        if name == "run_python":
            llm_local.TOOL_HANDLERS[name] = _guarded_redacting_python(handler, allowed_scripts)
        else:
            llm_local.TOOL_HANDLERS[name] = _redacting_handler(handler)
    allow = ", ".join(allowed_scripts) if allowed_scripts else "(none — subprocess blocked)"
    print(f"[privacy] confidential-tools: run_python enabled (guarded; allow={allow}), ALL tool "
          f"output redacted (subprocess timeout {llm_local.RUN_PYTHON_TIMEOUT}s)", file=sys.stderr)


def enforce_privacy(args) -> None:
    if args.tools and not args.confidential_tools:
        sys.exit("error: --tools is blocked in privacy mode (local execution output would be uploaded unaudited); "
                 "use --confidential-tools to run tools with redacted output, --no-privacy if the data is "
                 "non-sensitive, or use llm_local.py")
    if args.image:
        sys.exit("error: -i/--image is blocked in privacy mode (images can't be redacted); "
                 "use --no-privacy or llm_local.py")
    for pattern in args.file:
        matches = sorted(glob.glob(pattern, recursive=True)) or [pattern]
        for name in matches:
            hit = denied_pattern(name)
            if hit:
                sys.exit(f"error: privacy mode refuses file {name} (matches deny pattern '{hit}'); "
                         "use --no-privacy only if you are sure it holds no secrets")


def main() -> int:
    # DeepSeek-class reasoning routinely burns >8k tokens on review tasks; a higher
    # default avoids the empty-truncation retry round trip (observed: 157s wasted).
    ap = llm_local.build_parser(default_model=None, description=__doc__.splitlines()[0],
                                default_max_tokens=16384)
    ap.add_argument("--no-privacy", action="store_true",
                    help="disable privacy protections (file deny-list, redaction, tools/image block)")
    ap.add_argument("--confidential-tools", action="store_true",
                    help="run tools under privacy mode with ALL tool output redacted (for delegated deploys; "
                         "covers common secret formats; use only with trusted runbooks)")
    ap.add_argument("--allow-script", action="append", default=[],
                    help="confidential-tools: allow run_python subprocesses that invoke this script "
                         "name (repeatable; also reads LLM_CONFIDENTIAL_ALLOWED_SCRIPTS=a,b)")
    ap.add_argument("--consult-local", action="store_true",
                    help="let the strong model query the free local LLM for second opinions/brainstorms")
    ap.add_argument("--no-escalate", action="store_true",
                    help="disable auto-escalation from the open/free model to the paid model on "
                         "reasoning-truncation or invalid JSON (escalation is ON by default for --no-privacy)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print model routing decision and exit (no API call)")
    args = ap.parse_args()

    if args.confidential_tools and args.no_privacy:
        sys.exit("error: --confidential-tools is for privacy mode; drop --no-privacy "
                 "(or use plain --tools with --no-privacy if the data is non-sensitive)")

    api_key = os.environ.get("OPENCODE_API_KEY")
    if not api_key:
        sys.exit(f"error: OPENCODE_API_KEY is not set.\n{CONFIG_HELP}")
    # Model routing: if any configured default contains "-free", use that free
    # model for every implicit request (privacy and no-privacy). Explicit
    # --model still wins for manual probes.
    chain = _model_chain(args.model) if args.model else []
    tier = "explicit --model"
    on_open_tier = False
    selected_free_override = False
    if not chain:
        open_chain = _model_chain(os.environ.get("OPENCODE_MODEL_OPEN", ""))
        privacy_chain = _model_chain(os.environ.get("OPENCODE_MODEL", ""))
        configured = open_chain + privacy_chain
        free_chain = open_chain if _contains_free_model(open_chain) else (
            privacy_chain if _contains_free_model(privacy_chain) else []
        )
        if free_chain:
            chain = free_chain
            tier = "configured free tier (*-free default)"
            on_open_tier = True
            selected_free_override = bool(configured and configured[0] != chain[0])
        elif args.no_privacy and open_chain:
            chain = open_chain
            tier = "open tier (OPENCODE_MODEL_OPEN)"
            on_open_tier = True
        elif privacy_chain:
            chain = privacy_chain
            tier = "privacy tier (OPENCODE_MODEL)"
        else:
            chain = [DEFAULT_STRONG_MODEL]
            tier = "built-in free default"
            on_open_tier = True
        if selected_free_override and not args.check:
            print(f"[model] overriding configured {configured[0]} -> {chain[0]}", file=sys.stderr)
    args.model = chain[0] if chain else None
    args.fallback_models = chain[1:]
    # Escalation: when running the cheaper open tier, keep the stronger PAID model
    # (OPENCODE_MODEL) on standby. call_llm / the --json validator escalate to it once
    # if the open model truncates on reasoning or returns invalid JSON, so a weak free
    # model never silently yields garbage. --no-escalate opts out.
    args.escalate_model = None
    args.escalate_fallbacks = []
    if on_open_tier and not args.no_escalate and not _contains_free_model(chain):
        paid_chain = _model_chain(os.environ.get("OPENCODE_MODEL", ""))
        paid_chain = [m for m in paid_chain if m not in chain]  # don't escalate to a model we're already using
        if paid_chain:
            args.escalate_model = paid_chain[0]
            args.escalate_fallbacks = paid_chain[1:]
    if args.model and not args.check:
        suffix = f" (429 fallback: {', '.join(args.fallback_models)})" if args.fallback_models else ""
        esc = f" (escalates to: {args.escalate_model})" if args.escalate_model else ""
        print(f"[model] {args.model} — {tier}{suffix}{esc}", file=sys.stderr)

    if args.dry_run:
        print(f"[dry-run] model={args.model} tier={tier} escalate={args.escalate_model}")
        return 0

    base_url = os.environ.get("OPENCODE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    if args.model == DEFAULT_STRONG_MODEL and base_url == "https://opencode.ai/zen/go/v1":
        if not args.check:
            print(f"[model] {DEFAULT_STRONG_MODEL} is not served on /zen/go/v1; using {DEFAULT_BASE_URL}", file=sys.stderr)
        base_url = DEFAULT_BASE_URL

    backend = llm_local.Backend(
        name="opencode",
        base_url=base_url,
        api_key=api_key,
        default_model=args.model or "",
    )

    privacy = not args.no_privacy
    global _privacy_on
    _privacy_on = privacy
    print(f"[privacy] {'ON' if privacy else 'OFF (--no-privacy)'}", file=sys.stderr)
    if not privacy and not args.check:
        print("[privacy] WARNING: file deny-list, redaction, tool/image blocks are DISABLED. "
              "Sensitive data may be sent to the cloud.", file=sys.stderr)
    # Enable tools + raise limits BEFORE the consult block so the tools system
    # prompt is selected; enforce_privacy then permits tools for this mode.
    if args.confidential_tools:
        prep_confidential_tools(args)
    if privacy and not args.check:
        enforce_privacy(args)

    args.extra_tool_specs = None
    if args.consult_local:
        llm_local.TOOL_HANDLERS["consult_local"] = _consult_local
        args.extra_tool_specs = [CONSULT_SPEC]
        args.system = (args.system or (llm_local.TOOLS_SYSTEM if args.tools else llm_local.DEFAULT_SYSTEM)) + CONSULT_NOTE

    # Redact every tool output AFTER all handlers are registered.
    if args.confidential_tools and privacy:
        wrap_tool_handlers(allowed_scripts_from(args))

    return llm_local.run(args, backend, sanitize=redact if privacy else None)


if __name__ == "__main__":
    sys.exit(main())
