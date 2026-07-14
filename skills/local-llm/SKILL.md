<!-- SPDX-License-Identifier: MIT -->

---
name: local-llm
description: Delegate analysis to cheaper LLMs to save API tokens. Two tiers — free local LM Studio for bulk work (logs, counting, vision, diffs) and strong cloud model (Opencode Zen) behind a privacy guard for judgment calls (review, synthesis, second opinions). Delegation is the DEFAULT: before every read that returns content you'd only skim, ask "conclusion or content?" — conclusion → delegate.
---

# LLM Delegates

Two wrappers (stdlib-only), same CLI:

| Tier | Script | Backend | Cost | Use for |
|------|--------|---------|------|---------|
| **local** (default) | `python "${CLAUDE_PLUGIN_ROOT}/skills/local-llm/llm_local.py"` | LM Studio, `LOCAL_LLM_URL` env (default `http://127.0.0.1:1234`) | free | bulk volume: logs, big files, counting, vision, diffs |
| **strong** | `python "${CLAUDE_PLUGIN_ROOT}/skills/local-llm/llm_strong.py"` | Opencode Zen (cloud), env-configured | subscription | quality: hard reasoning the local model can't be trusted with |

Answer → stdout. Token usage + timing → stderr. Exit 1 = endpoint down / request failed / privacy refusal.

## Prerequisites

- **Local tier**: [LM Studio](https://lmstudio.ai/) running with a model that supports function calling
- **Strong tier**: An [Opencode Zen](https://opencode.ai/zen) subscription + `OPENCODE_API_KEY`

## Availability

```
python ".../llm_local.py" --check    # 3s probe, lists models
python ".../llm_strong.py" --check   # needs OPENCODE_API_KEY; probes /v1/models, falls back to chat probe
```

If unavailable: do the task yourself (or use the other tier if appropriate); do not retry-loop.

## Strong tier configuration (env vars — skills can't carry secrets)

Set once in `~/.claude/settings.json` `"env"` block (applies to every project) or as system env vars:

```json
{ "env": { "OPENCODE_API_KEY": "<key>", "OPENCODE_MODEL": "<zen model id>" } }
```

`OPENCODE_BASE_URL` optional (default `https://opencode.ai/zen/v1`). Missing key/model → clear error, exit 1.
Model switching: `--check` lists every model ID the subscription offers; switch via `OPENCODE_MODEL` (permanent) or `--model <id>` (per call).
Two-model confidentiality routing: privacy-guarded calls use `OPENCODE_MODEL` (strong **paid** model); `--no-privacy` calls prefer `OPENCODE_MODEL_OPEN` (the **free**/cheaper model for fully non-confidential content; falls back to `OPENCODE_MODEL` if unset). Explicit `--model` overrides both. The chosen model + tier is announced on stderr (`[model] ...`). **COST DEFAULT: for non-confidential strong work (code review of non-secret source, diffs, public docs, cross-file synthesis) pass `--no-privacy` so it uses the FREE tier — reserve the paid privacy model for genuinely confidential data. Privacy-ON (paid) on plain source review is wasted spend; verify with the telemetry reader below.**
Both model vars accept a comma-separated fallback chain (e.g. `deepseek-v4-flash-free,deepseek-v4-flash`): on HTTP 429 (rate limit) or an unsupported/unknown model id, the call automatically retries on the next model in the chain (`[fallback] ...` on stderr).

## Strong tier privacy guard — ON by default (cloud upload!)

- Refuses sensitive files (`.env*`, `*secret*`, `*token*`, `*credential*`, key/cert files, `.ssh`, ...) — hard error naming the file. Projects add their own sensitive globs via `LLM_EXTRA_DENY_GLOBS=glob1,glob2`.
- Blocks `--tools` (local execution output can't be audited before upload) and `-i` images (pixels can't be redacted) — **unless** `--confidential-tools`, which runs `run_python` with every tool output redacted AND a guard: subprocesses may only launch caller-allowlisted scripts (`--allow-script NAME` / `LLM_CONFIDENTIAL_ALLOWED_SCRIPTS=a,b`), and destructive/exfiltrating code is refused. Redaction covers common secret formats but cannot guarantee catching every possible format — only use with trusted runbooks.
- Redacts outbound text: key/token/password assignments, bearer/JWT, API-key-shaped strings, IPv4, emails, `login=`/`account` numbers → `[REDACTED:<type>]`, per-type counts on stderr. Git SHAs and config values survive.
- `--no-privacy` disables all of it — only for data already known non-sensitive.

## Token-savings telemetry (automatic)

Every call (local and strong) appends one usage record (tier, model, tokens, seconds) to `./.llm_delegate/usage.jsonl` — no opt-in. Override the file with `LLM_DELEGATE_LOG`, the dir with `LLM_DELEGATE_LOG_DIR`, or disable with `LLM_DELEGATE_LOG=NUL`.
Report savings: `python delegation_savings.py [--session | --since ISO] [--json]`. It prints tokens **offloaded** (`prompt+completion` per call = input you didn't read into the main model's context + analysis it didn't generate ≈ main-context tokens saved), split by tier and by **free vs paid** cost class. Use it to confirm non-confidential work is hitting the free tier.

## Why this saves tokens

The script inlines file contents itself (or the model reads files via its python tool), so
large inputs never enter your context — you read only the distilled answer. Savings = output << input.
Verified: 100k-token logs triaged into 3 bullets; 10MB JSON explored via tools with zero inlining.

## Flags (both tiers)

| Flag | Use |
|------|-----|
| `--runbook NAME` | load a bundled runbook template as the instruction preamble — fill a blank instead of hand-authoring (see below) |
| `-f FILE\|GLOB` (repeat) | inline files; cap 240KB total (≈110k tokens for dense logs) |
| `--head-kb N` / `--tail-kb N` | slice big files in-script (logs: tail is usually what you want) |
| `--chunk` / `--chunk-kb N` | map-reduce past the cap (sequential, slow — run in background) |
| `--stdin` | pipe command output in (test runs, diffs) |
| `--tools` | model executes python locally — counting, parsing, SQLite (local tier; strong only with `--no-privacy`) |
| `-i IMG` (repeat) | vision: screenshots, charts — LOCAL TIER ONLY (DeepSeek models on Zen reject images) |
| `--json` | validated, compacted JSON answer |
| `--caveman` | telegraphic minimal-token output |
| `--max-words N` | word budget (obeyed reliably; auto-compress fallback) |
| `--out FILE` | long answer to disk, 15-line preview to stdout |
| `--timeout S` | adaptive: 900s floor + ~12s/KB of inlined input, capped at 3600s |
| `--version` | print version and exit |
| `--check` | probe the endpoint and list loaded models (exit 0 if available, 1 if not) |
| `--system PROMPT` | custom system prompt (overrides default) |
| `--model NAME` | model override (default: `qwen3.6-35b-a3b-mtp` local, `OPENCODE_MODEL` strong) |
| `--temperature F` | model temperature (default: 0.2) |
| `--max-tokens N` | response length limit |
| `--no-retry` | disable auto-retry on empty/truncated answers |
| `--show-reasoning` | print model reasoning to stderr |
| `--require-model NAME` | exit non-zero unless that model is loaded (preflight check) |
| `--max-tool-rounds N` | max tool-call rounds (default: 5) |
| `--run-python-timeout S` | per-call subprocess timeout for `run_python` (default: 30s) |
| `--no-privacy` | strong tier only: disable deny-list/redaction/blocks |
| `--consult-local` | strong tier only: strong model may query the free local LLM mid-reasoning (privacy-safe; both question and local answer redacted before upload) |
| `--confidential-tools` | strong tier + privacy: run `run_python` with ALL tool output redacted before upload; requires `--allow-script` for subprocesses |
| `--allow-script NAME` | (repeatable) allowlist scripts for `--confidential-tools` subprocess execution; or set `LLM_CONFIDENTIAL_ALLOWED_SCRIPTS=a,b` |
| `--no-escalate` | strong tier only: disable auto-escalation from free to paid model |
| `--dry-run` | strong tier only: print routing decision and exit without making an API call |

## Runbook templates — fill a blank, don't hand-author

`--runbook NAME` prepends a bundled template (in `skills/local-llm/runbooks/`) as the
instruction preamble; your prompt becomes the concrete TASK. This removes the per-use authoring
tax for recurring delegation shapes — reach for it before writing a bespoke prompt.

| Name | Shape | Typical call |
|------|-------|--------------|
| `triage` | one most-important finding in log/test/cmd output | `<cmd> 2>&1 \| python .../llm_local.py --runbook triage --stdin --caveman` |
| `summarize` | decisions/issues/gotchas from a long doc | `python .../llm_local.py --runbook summarize -f BIG.md --caveman` |
| `count` | exact counts/aggregations over a data file | `python .../llm_local.py --runbook count "counts of X in var/.../data.db"` |
| `review` | FP-resistant, confidence-tagged correctness/safety review | `git diff -- f \| python .../llm_strong.py --runbook review --stdin --no-privacy` |
| `commit` | conventional commit message from a staged diff | `git diff --cached \| python .../llm_local.py --runbook commit --stdin` |
| `supervise` | second-opinion AGREE/DISAGREE on a claim | `echo "CLAIM: ..." \| python .../llm_strong.py --runbook supervise --stdin --no-privacy` |
| `watch` | poll a status command, early-stop on a condition | `python .../llm_strong.py --runbook watch "<status cmd>; stop when ...; max 6 cycles"` |
| `fleet` | swarm strong agents over a WHOLE codebase, audited before return | `python .../fleet_review.py --scope "src/**" --confidential-glob "config/**" --dry-run` |
| `improve` | quality + structure review (not a bug hunt) — finds misplaced responsibility, dead code, confusing UX, stale docs | `python .../llm_strong.py --runbook improve -f FILE --no-privacy` |

A runbook makes the positional prompt OPTIONAL (the template is the instruction; pipe data via
`--stdin`/`-f`). Batteries-included defaults: `triage`/`summarize`/`supervise`/`review`/`commit`
turn on `--caveman` automatically; `count` auto-enables `--tools` on the local tier. Resolution
order: explicit `.md` path → `$LLM_RUNBOOK_DIR/<name>.md` (project-specific, not bundled) →
`<tool-dir>/runbooks/<name>.md`. Unknown name exits and lists the bundled set.

### `fleet` — whole-codebase swarm (commander → workers → auditor)
`fleet` is not a one-shot prompt: it is orchestrated by `fleet_review.py` (next to
`llm_strong.py`), which IS the fleet commander. It enumerates `git ls-files`, routes each
file by confidentiality — **hard-denied** (secrets/keys/`.env`) are never uploaded;
**confidential** (`--confidential-glob` / `LLM_FLEET_CONFIDENTIAL_GLOBS`) → PAID privacy-ON
worker agents (`OPENCODE_MODEL`); everything else → FREE `--no-privacy` worker agents
(`OPENCODE_MODEL_OPEN`) — fans out parallel `llm_strong.py --runbook review` workers, then
sends ALL merged findings to ONE PAID auditor agent that dedupes, drops false positives,
ranks by severity, and returns a single compact table. Raw per-worker findings stay on disk
(`.llm_delegate/fleet_findings_raw.md`); only the audited report comes back
(`.llm_delegate/fleet_report.md`). **Always `--dry-run` first** to preview the PAID-vs-FREE
fan-out and cost. Knobs: `--files-per-worker`/`--kb-per-worker` (slice size), `--max-workers`
(fan-out cap), `--concurrency` (default 2, hard-capped at 2 — higher fan-out errors out), `--worker-max-words`/
`--max-words` (budgets), `--scope`/`--paths` (file selection), `--include-ext` (extra extensions),
`--worker-runbook` (swap worker review runbook), `--worker-timeout`/`--audit-timeout` (per-stage timeouts),
`--audit-no-privacy` (run auditor without privacy), `--no-audit` (skip audit pass), `--out` (write report to file).
Full details in `runbooks/fleet.md`.

The `review` runbook is tuned against FALSE POSITIVES (in practice strong-model review
over-flags hardened code >50%): every finding is tagged HIGH/MED/LOW confidence, it refuses
"undefined/unused/dead" claims whose definition+callers it can't see, treats parity-neutral
formula changes (same code in train+serve) as "needs-retrain" not bugs, flags config-disabled
paths as no-impact, and honors **DOMAIN NOTES** you pass in the TASK (units/conventions — e.g.
"`sl_pips` are broker POINTS"). Still verify every load-bearing finding against the code before
acting; pass the relevant domain caveats up front to cut the noise.

## Rules

1. Counting/aggregation → ALWAYS `--tools` and pass the file PATH in the prompt (no `-f`):
   plain-prompt arithmetic makes the local reasoning model burn its whole budget and return empty.
   Same for LOG TRIAGE of files >80KB: `--tools` + path ("count error patterns via python, then
   summarize") finishes in ~1 min where inlining 200KB can exceed 15 min of prompt processing.
2. Add `--caveman --max-words N` to every call unless you need verbatim quotes or `--json`.
   Numbers, identifiers and paths stay exact.
3. Spot-check load-bearing claims with your own grep/read — local-tier failure modes:
   it pattern-matches config key names (may report a similar key, not the operative one),
   and it quotes documents accurately but can miss that a passage was superseded later in the file.
4. Keep for yourself: code edits, decisions, deploys, git, anything irreversible.
5. `--tools` executes arbitrary Python on the host — never use with untrusted prompts or models.
6. For vision metric questions, ask for tail metrics (max, % above threshold) explicitly —
   "volatility" defaults to means and may hide bursts.

## Tier routing — local first, strong for judgment, yourself for actions

| Task | Tier |
|------|------|
| Log triage, big-file summaries, counting, screenshots, diffs, drafting | local (free — always first choice) |
| Second opinion on a load-bearing local-tier claim | strong |
| Nuanced code-review draft, cross-file synthesis, tricky test-failure interpretation | strong |
| Strong-tier task that benefits from cheap brainstorming/drafts | strong + `--consult-local` |
| Doc reasoning where timeline/supersession matters | strong |
| Anything sent to strong | privacy ON unless data is known non-sensitive |
| Code edits, decisions, deploys, git | yourself — never delegated |

Keep strong-tier volume low: quality, not bulk (it costs subscription usage; local is free).

## Playbook — delegate FIRST, read second

| When | Delegate |
|------|----------|
| "why is X happening" diagnostic | local: log tail triage `"errors + dominant patterns, 3 bullets" -f LOG --tail-kb 150 --caveman` |
| Data file questions (CSV/JSON/SQLite/DB) | local: `--tools` + path in prompt: exact counts, group-bys, schema exploration |
| Doc ≳ 100 lines you might read | local: `--caveman --max-words 50` pre-read → read only flagged sections yourself |
| Test failures | local: `<test cmd> 2>&1 \| ... "cluster failures, first actionable error each" --stdin --caveman` |
| Committing | local: `git diff \| ... "draft commit message" --stdin --caveman` |
| GUI / dashboard / chart verification | local: screenshot or PNG via `-i` |
| Monitoring loops | local: summarize new log segment, report ONLY anomalies |
| Local-tier answer drives a decision | strong: verify the claim (`--caveman --max-words 80`) before acting |

## Project integration

Paste `${CLAUDE_PLUGIN_ROOT}/AGENTS_SNIPPET.md` into the project's AGENTS.md / CLAUDE.md and
replace the placeholder rows with that project's concrete artifacts (log paths, result DBs,
report files) so agents know the project-specific delegation targets.

## Copy-paste examples

```bash
# Triage a log file
tail -100 app.log | python llm_local.py --runbook triage --stdin --caveman

# Count rows in a CSV
python llm_local.py --runbook count "rows by status in data.csv"

# Summarize a long document
python llm_local.py --runbook summarize -f docs/design.md --caveman --max-words 50

# Review a git diff (free tier)
git diff | python llm_strong.py --runbook review --stdin --no-privacy --caveman --max-words 400

# Draft a commit message
git diff --cached | python llm_local.py --runbook commit --stdin

# Second opinion on a claim
echo "CLAIM: the cache TTL is 300s" | python llm_strong.py --runbook supervise --stdin --no-privacy --caveman

# Fleet review of a module (dry-run first)
python fleet_review.py --scope "src/myapp/**" --dry-run

# Check token savings
python delegation_savings.py --session
```
