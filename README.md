# local-llm-delegate

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)
![Claude Plugin](https://img.shields.io/badge/Claude-Plugin-green.svg)

## Quick start

1. **Install LM Studio** and load a model with function-calling support (e.g. `qwen3.6-35b-a3b-mtp`)
2. **Verify local tier**: `python skills/local-llm/llm_local.py --check`
3. **Try it**: `echo "hello world" | python skills/local-llm/llm_local.py "count words" --stdin --caveman`

For the strong (cloud) tier, set `OPENCODE_API_KEY` in `~/.claude/settings.json` (see [Requirements](#requirements)).

## What it does

Two-tier LLM delegation to keep large inputs out of the Claude context window:
- **Local tier** (`llm_local.py`): bulk text analysis, log triage, data aggregation (`--tools`), and vision (`-i`) on a free local LM Studio instance. Private — nothing leaves the machine.
- **Strong tier** (`llm_strong.py`): smarter/faster cloud reasoning via Opencode Zen — supervises load-bearing local conclusions (sees only the distilled, redacted result) and handles non-confidential nuanced synthesis, behind a privacy guard (ON by default; `--no-privacy` to disable).

**Confidentiality invariant:** raw confidential data goes to the local tier only; only a distilled conclusion is ever passed to the cloud tier.

## Confidentiality & safety

- **Privacy guard** (strong tier, ON by default): refuses to inline sensitive files (`.env*`, `*secret*`, keys/certs, `.ssh`, ...) — extend with `LLM_EXTRA_DENY_GLOBS=glob1,glob2`; redacts outbound text (secrets, bearer/JWT, API-key shapes, AWS access-key IDs, Google API keys, GitHub PATs, SSH keys, IPv4, emails, login/account numbers). `--no-privacy` disables it (non-sensitive data only).
- **`--confidential-tools`**: runs `run_python` under the privacy guard with EVERY tool output redacted before upload, plus a containment guard — subprocesses may only launch caller-allowlisted scripts (`--allow-script NAME`, repeatable; or `LLM_CONFIDENTIAL_ALLOWED_SCRIPTS=a,b`), and destructive/exfiltrating code is refused. Lets you delegate long agentic jobs (deploys) confidentially.
- **Capability guard** (local tier): `--require-model NAME` exits non-zero unless that model is loaded; `--check` warns if the expected model is missing — prevents silent quality degradation from a swapped/smaller model.
- **Telemetry** (optional): set `LLM_DELEGATE_LOG=path.jsonl` to record one usage line per call (tier/model/tokens/seconds) to quantify savings.
- **Security note**: `--tools` enables `run_python`, which executes arbitrary Python code on the host with full filesystem/network/OS access. Only use with trusted prompts and models.

## Requirements

- **Local tier**: [LM Studio](https://lmstudio.ai/) serving an OpenAI-compatible API with a model supporting function calling (`--tools`) and vision (`-i`). Default endpoint `http://127.0.0.1:1234` (override `LOCAL_LLM_URL`).
- **Strong tier**: an [Opencode Zen](https://opencode.ai/zen) subscription. Configure once in `~/.claude/settings.json`:
  ```json
  { "env": { "OPENCODE_API_KEY": "<key>", "OPENCODE_MODEL": "<zen model id>", "OPENCODE_MODEL_OPEN": "<cheaper model id>" } }
  ```
  `OPENCODE_BASE_URL` optional (default `https://opencode.ai/zen/v1`). Never commit the key.
  `OPENCODE_MODEL_OPEN` is optional: when set, `--no-privacy` calls (fully non-confidential content) route to this cheaper/free model, while privacy-guarded calls keep using `OPENCODE_MODEL`. Both model vars accept a comma-separated fallback chain for automatic retry on rate limits.

## Fleet review (whole-codebase swarm)

`fleet_review.py` fans out parallel review agents across an entire codebase, then audits the merged findings into a single ranked table. Always run `--dry-run` first to preview cost (PAID vs FREE workers).

```bash
python skills/local-llm/fleet_review.py --scope "src/**" --confidential-glob "config/**" --dry-run
```

See `skills/local-llm/runbooks/fleet.md` for details.

## Cross-tier consultation

`llm_strong.py --consult-local` gives the strong model a `consult_local` tool to query the free local LLM mid-reasoning (brainstorms, drafts, second opinions). Privacy-safe: both the question and the local answer are redacted before upload.

## Install

### Via Claude Code plugin marketplace (when available)
```bash
claude plugin marketplace add <path-to-claude-plugins-folder>
claude plugin install local-llm-delegate@rulfe-tools
```
### Manual install
Copy the `skills/local-llm/` directory into your Claude skills directory.

## Quick test

```bash
python skills/local-llm/llm_local.py --check    # local: ~3s, lists models
python skills/local-llm/llm_strong.py --check   # strong: needs OPENCODE_API_KEY
```
Exit code 1 indicates endpoint failure, missing config, or a privacy refusal.

## Testing & validation

### End-to-end test plan

`TEST_PROMPT.md` is a 58-test end-to-end test plan covering all features across 14 phases:

| Phase | Tests | What it covers |
|-------|-------|----------------|
| 1 | 1.1–1.12 | Local tier basics (check, version, prompts, caveman, max-words, stdin, file inline, head/tail, --out, --json, --system, --timeout) |
| 2 | 2.1–2.4 | Local tier tools (run_python, file paths, timeout, output truncation) |
| 3 | 3.1–3.7 | Runbooks (triage, summarize, count, commit, supervise, unknown runbook, $LLM_RUNBOOK_DIR) |
| 4 | 4.1–4.3 | Chunking (chunk mode, chunk+stdin, chunk text) |
| 5 | 5.1 | Vision (color detection) |
| 6 | 6.1–6.4 | Error handling (no prompt, mutual exclusion, no matching files, unavailable endpoint) |
| 7 | 7.1–7.6 | Strong tier basics (check, dry-run, version, privacy ON/OFF, missing API key) |
| 8 | 8.1–8.6 | Privacy guard (deny-list, symlink, image block, tools block, conflicts, redaction) |
| 9 | 9.1–9.3 | Consult-local (basic, privacy mode, chained questions) |
| 10 | 10.1 | Escalation control (--no-escalate) |
| 11 | 11.1–11.3 | Fleet review (dry-run, confidential glob, missing key) |
| 12 | 12.1–12.3 | Telemetry (usage log, savings report, JSON output) |
| 13 | 13.1–13.4 | Edge cases (long input cap, empty input, unicode, special characters) |
| 14 | 14.1 | Cross-tier integration (local → strong supervision with hallucination catch) |

### Results

`TEST_PROMPT_REPORT.md` contains the full execution report with per-test output. Summary:

| Metric | Value |
|--------|-------|
| Total tests | 58 |
| Passed | 58 |
| Failed | 0 |
| Test plan fixes | 1 (test 8.6: removed `--no-privacy` to enable redaction) |

### How this was validated

- **Test plan execution**: All 58 tests run sequentially against a live LM Studio instance (local tier) and Opencode Zen API (strong tier), with actual output captured verbatim in `TEST_PROMPT_REPORT.md`.
- **Cross-tier supervision validated**: Test 14.1 confirmed the strong model catches local model hallucinations — the local model added "System down" to a summary of "The server is down", and the strong model correctly returned `DISAGREE`.
- **Privacy guard validated**: All 6 privacy tests (8.1–8.6) confirmed deny-list, symlink detection, image/tools blocking, and secret redaction work correctly.
- **Production use**: This tool is used daily in another project for log triage, code review delegation, and confidential data processing — the test plan exercises the same code paths used in production.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `unavailable: endpoint up but no models loaded` | Load a model in LM Studio |
| `OPENCODE_API_KEY is not set` | Set it in `~/.claude/settings.json` or as env var |
| `error: privacy mode refuses file ...` | Use `--no-privacy` if data is non-sensitive, or `--confidential-tools` |
| Slow responses | Local reasoning models are slow; use `--caveman --max-words N` to reduce output |
| `error: no files match ...` | Check your glob pattern; use `ls` to verify the path exists |
| `warning: output truncated at max_tokens` | Increase `--max-tokens` or use `--chunk` for large inputs |

## Known limitations

- Local tier is slow on large inputs (reasoning model burns tokens "thinking" before answering)
- Privacy redaction covers common formats but can't catch every possible secret
- `run_python` executes arbitrary code — no sandbox, no container, no seccomp
- Fleet review concurrency hard-capped at 2 (backend rate limits)

## Contents

### Core
- `skills/local-llm/llm_local.py` — Local tier engine (stdlib-only, also shared by strong tier)
- `skills/local-llm/llm_strong.py` — Strong tier with privacy guard
- `skills/local-llm/fleet_review.py` — Whole-codebase review orchestrator
- `skills/local-llm/delegation_savings.py` — Token-savings report

### Configuration
- `.claude-plugin/plugin.json` — Plugin manifest
- `skills/local-llm/SKILL.md` — Agent-facing rules, flags, and playbook
- `skills/local-llm/runbooks/` — Prompt templates (`triage`, `summarize`, `count`, `review`, `commit`, `supervise`, `watch`, `fleet`, `improve`)

### Testing
- `TEST_PROMPT.md` — 58-test end-to-end test plan (14 phases)
- `TEST_PROMPT_REPORT.md` — Full execution report with per-test output

### Project integration
- `AGENTS_SNIPPET.md` — Paste into your project's AGENTS.md
- `CHANGELOG.md` — Version history
- `LICENSE` — MIT license

## License

MIT — see [LICENSE](LICENSE) for details.

## Uninstall

```bash
claude plugin uninstall local-llm-delegate@rulfe-tools
```
