<!-- SPDX-License-Identifier: MIT -->

# Changelog — local-llm-delegate

Versions track the exportable engine (`llm_local.py` + `llm_strong.py`) and skill docs.
Project-specific collectors/orchestrators (e.g. trading data collectors) live outside the
plugin and are not versioned here.

## Recent highlights (v1.12.0)

- Extended privacy redaction (Google API keys, GitHub PATs, SSH keys, hex strings)
- Symlink denial in file deny-list
- `<tool_output>` markers for prompt injection defense
- `--dry-run` for cost preview, `--version` flag
- `--no-privacy` warning on stderr

## 1.12.0
- **Security hardening.** Extended privacy redaction (Google API keys, GitHub PATs,
  Basic auth, SSH keys, hex strings). Added symlink denial to file deny-list. Extended
  deploy guard patterns (`getattr`, `__import__`, `exec`, `eval`, `os.system`, `os.popen`).
  Added `<tool_output>` markers to defend against prompt injection via tool output. Added
  `--no-privacy` warning on stderr. Added `--dry-run` to `llm_strong.py`. Redact
  `consult_local` question before sending to local model. Runbook loading now warns when
  loaded from `$LLM_RUNBOOK_DIR`. Added `--version` flag. Fixed documentation mismatches
  (default endpoint, concurrency, base URL).

## 1.11.3
- **Route strong delegate defaults to DeepSeek V4 Flash Free.** `llm_strong.py`
  now defaults to the Zen endpoint (`https://opencode.ai/zen/v1`) and model id
  `deepseek-v4-flash-free` for both privacy and no-privacy routes. The old Go
  endpoint (`/zen/go/v1`) does not list free models, which is why the same id
  failed there with unsupported-model errors. Provider/typo aliases normalize to
  the free id, an old Go base URL is auto-switched when using the free default,
  and any configured `*-free` model becomes the implicit default for all routes
  without auto-escalating to a paid model.

## 1.11.2
- **Environment model override for local LLM.** Added `LOCAL_LLM_MODEL` environment variable support to `llm_local.py` to allow override of default local models when executing local actions or sub-commands.

## 1.11.1
- **Switch Strong paid model to GLM-5.2.** Updated strong model defaults and documentation to target `glm-5.2` on Opencode Zen for enhanced reasoning and paid-tier delegations.

## 1.11.0
- **`fleet` — whole-codebase review swarm (commander → workers → auditor).** New
  orchestrator `fleet_review.py` (stdlib-only, sits next to `llm_strong.py`) plus the
  `fleet` runbook. The local commander enumerates `git ls-files`, keeps reviewable source,
  and routes each file by confidentiality: **hard-denied** (secrets/keys/`.env`, via
  `llm_strong.denied_pattern`) are NEVER uploaded (listed for a human); **confidential**
  (`--confidential-glob` / `LLM_FLEET_CONFIDENTIAL_GLOBS`) go to **PAID** privacy-ON worker
  agents (`OPENCODE_MODEL`); everything else goes to **FREE** `--no-privacy` worker agents
  (`OPENCODE_MODEL_OPEN`). Workers run in parallel (`--concurrency`, 429-friendly) using the
  FP-resistant `review` runbook over byte-budgeted slices (`--files-per-worker`/
  `--kb-per-worker`, capped by `--max-workers`). All merged findings then go to ONE PAID
  auditor agent that dedupes cross-worker duplicates, drops false positives, ranks by
  severity, and returns a single compact table — the only thing surfaced. Raw per-worker
  findings persist at `.llm_delegate/fleet_findings_raw.md`; the audited report at
  `.llm_delegate/fleet_report.md`. `--dry-run` previews the PAID-vs-FREE fan-out and cost
  with zero spend. Verified live: 3 workers (2 paid + 1 free) + auditor → 5-row ranked table
  in ~219s.

## 1.9.0
- **`--runbook NAME` template library (adoption lever).** Loads a bundled prompt template as
  the instruction preamble so the agent fills a blank instead of hand-authoring a bespoke
  prompt for every recurring delegation — the per-use authoring tax was a top reason
  delegation got skipped. Bundled: `triage` (top finding in log/test/cmd output), `summarize`
  (long doc → decisions/issues/gotchas), `count` (exact aggregation), `review` (code/diff
  correctness+safety bugs), `commit` (conventional commit message from a staged diff),
  `supervise` (AGREE/DISAGREE on a load-bearing claim), `watch` (poll a status command,
  early-stop on a condition). A runbook makes the positional prompt OPTIONAL (the template is
  the instruction; pipe data via `--stdin`/`-f`) and is batteries-included: the terse runbooks
  auto-set `--caveman`, and `count` auto-enables `--tools` on the local tier. Resolution:
  explicit `.md` path → `$LLM_RUNBOOK_DIR/<name>.md` (project-specific, not bundled) →
  `<tool-dir>/runbooks/<name>.md`. Unknown name exits and lists the bundled set. Works on both
  tiers (shared `build_parser`).
- **Escalation visibility.** Auto-escalation now prints a loud `[ESCALATION] free→PAID … paid
  tokens will be billed` banner, and every usage record in `usage.jsonl` carries an
  `"escalated": true|false` field — so paid-token spend triggered from a `--no-privacy` (free)
  invocation is never a silent surprise.
- **Docs:** SKILL.md gains a runbook-template section + flag row; AGENTS_SNIPPET.md adds the
  runbook line and a SAFETY-COLLISION rule (a blocked/sandboxed/timed-out delegate → fall back
  in-context, never bypass the classifier); README lists the `runbooks/` directory.

## 1.8.0
- **Auto-escalation free → paid.** When `--no-privacy` runs the cheap open tier
  (`OPENCODE_MODEL_OPEN`), the paid `OPENCODE_MODEL` is kept on standby and the call
  escalates to it automatically — once — if the open model (a) truncates because
  reasoning ate the whole token budget (`finish_reason=length` after the max-tokens
  retry) or (b) returns invalid JSON under `--json`. Previously a weak free model just
  warned and returned truncated garbage (observed: a 5-doc `--json` task burned 56k
  tokens of reasoning twice and produced nothing). The escalation re-runs on the
  stronger model with `max_tokens` raised to ≥16384. Opt out with `--no-escalate`.
  Net effect: prefer the free model by default for non-confidential work; it silently
  upgrades to the paid model only when genuinely needed. Verified live (flash-free
  truncated → deepseek-v4-pro completed valid JSON).

## 1.7.0
- **Token-savings telemetry, automatic.** `_log_usage` now defaults its JSONL path
  (`./.llm_delegate/usage.jsonl`, override `LLM_DELEGATE_LOG`/`LLM_DELEGATE_LOG_DIR`,
  disable with `LLM_DELEGATE_LOG=NUL`) so every local/strong call is recorded with
  zero opt-in. New `delegation_savings.py` reader aggregates tokens offloaded
  (≈ main-model context saved) by tier and by **free vs paid** cost class, with
  `--session`/`--since`/`--json`. Makes "how many tokens did delegation save, and how
  many on the free vs paid model" answerable per session.
- Docs: emphasise using the FREE `--no-privacy` (OPENCODE_MODEL_OPEN) tier for
  non-confidential strong-model work (e.g. code review of non-secret source); the
  paid privacy tier is only for confidential data.

## 1.6.3
- Much more generous default request timeout so the local (slow reasoning) model is
  usable across ALL task sizes without manual `--timeout`: floor raised 300s→900s and
  per-KB rate 5→12 s/KB, capped at 3600s (was unbounded). `RUN_PYTHON_TIMEOUT` default
  raised 120s→600s so big-log/aggregation `--tools` jobs finish without `--run-python-timeout`.

## 1.6.2
- Delegation-default guidance hardened in SKILL.md + AGENTS_SNIPPET.md: an explicit
  "conclusion or content?" self-check BEFORE reading, a trigger list, and the anti-pattern
  (reading a long doc / inline-scripting a count yourself) — so agents actually delegate.

## 1.6.1
- Export cleanliness: genericized a project-specific filename example in the wrapper
  docstring (deny-list illustration) — the shipped skill now contains zero project specifics.

## 1.6.0
- **Capability guard** (local): `--require-model NAME` exits non-zero unless that model is
  loaded; `--check` warns when the expected default model is missing — prevents silent
  quality degradation from a swapped/smaller model.
- **Deny-list env extension**: `LLM_EXTRA_DENY_GLOBS=glob1,glob2` adds project sensitive-file
  patterns without editing the wrapper (keeps it portable).
- Docs: README/SKILL/AGENTS_SNIPPET refreshed to the two-tier split (local worker → strong
  supervisor → agent) + confidentiality invariant + telemetry.

## 1.5.2
- **Redaction**: cover AWS access-key IDs (`AKIA…`, no separator, 20 chars) that the
  token-like and long-string rules missed.

## 1.5.1
- **Portability**: the `--confidential-tools` guard no longer hardcodes project script
  names. Allowlist is caller-supplied via `--allow-script NAME` /
  `LLM_CONFIDENTIAL_ALLOWED_SCRIPTS`; with no allowlist, any subprocess is refused
  (pure-python passes). Generic security defaults only.

## 1.5.0
- **`--confidential-tools` guard**: every `run_python` is gated — destructive/exfiltrating/
  repo-mutating code refused; subprocesses restricted to the allowlist.
- **Usage telemetry**: `LLM_DELEGATE_LOG=path.jsonl` records one record per call
  (tier/model/tokens/seconds).

## 1.4.1
- `--run-python-timeout N` on the local tier for long `--tools` jobs (big-log triage).

## 1.4.0
- **`--confidential-tools`** (strong): run `run_python` under privacy mode with EVERY tool
  output redacted before upload — for delegating long agentic jobs (e.g. deploys) without
  leaking. Raised subprocess timeout + `--max-tool-rounds`.

## 1.3.x
- Two-model confidentiality routing (`OPENCODE_MODEL` vs `OPENCODE_MODEL_OPEN`); comma-
  separated 429/unsupported-model fallback chains; delegation-as-default guidance.

## 1.2.x
- Strong tier live-verified (deepseek-v4-pro); gateway fixes (User-Agent, `/v1` handling);
  adaptive inline timeout; higher default max-tokens for reasoning models.

## 1.1.0
- Strong cloud tier (`llm_strong.py`) added behind the privacy guard; `--consult-local`.

## 1.0.0
- Local tier (`llm_local.py`): inline files/stdin, `--tools` run_python, `-i` vision,
  `--caveman`/`--max-words`, `--json`, `--out`, `--chunk` map-reduce.
