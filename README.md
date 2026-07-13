# local-llm-delegate

## What it does
Two-tier LLM delegation to keep large inputs out of the Claude context window, as a
**split**: LOCAL does the confidential/bulk work → STRONG supervises load-bearing LOCAL
conclusions → the calling agent oversees both and decides.
- **Local tier** (`llm_local.py`): bulk text analysis, log triage, data aggregation (`--tools`), and vision (`-i`) on a free local LM Studio instance. Private — nothing leaves the machine, so it has zero confidentiality limits and is the default sink for sensitive data.
- **Strong tier** (`llm_strong.py`): smarter/faster cloud reasoning via Opencode Zen — supervises load-bearing local conclusions (sees only the distilled, redacted result) and handles non-confidential nuanced synthesis, behind a privacy guard (ON by default; `--no-privacy` to disable).

**Confidentiality invariant:** raw confidential data goes to the local tier only; only a distilled conclusion is ever passed to the cloud tier.

## Confidentiality & safety
- **Privacy guard** (strong tier, ON by default): refuses to inline sensitive files (`.env*`, `*secret*`, keys/certs, `.ssh`, ...) — extend with `LLM_EXTRA_DENY_GLOBS=glob1,glob2`; redacts outbound text (secrets, bearer/JWT, API-key shapes, AWS access-key IDs, IPv4, emails, login/account numbers). `--no-privacy` disables it (non-sensitive data only).
- **`--confidential-tools`**: runs `run_python` under the privacy guard with EVERY tool output redacted before upload, plus a containment guard — subprocesses may only launch caller-allowlisted scripts (`--allow-script NAME`, repeatable; or `LLM_CONFIDENTIAL_ALLOWED_SCRIPTS=a,b`), and destructive/exfiltrating code is refused. Lets you delegate long agentic jobs (deploys) confidentially.
- **Capability guard** (local tier): `--require-model NAME` exits non-zero unless that model is loaded; `--check` warns if the expected model is missing — prevents silent quality degradation from a swapped/smaller model.
- **Telemetry** (optional): set `LLM_DELEGATE_LOG=path.jsonl` to record one usage line per call (tier/model/tokens/seconds) to quantify savings.

## Requirements
- Local tier: LM Studio serving an OpenAI-compatible API with a model supporting function calling (`--tools`) and vision (`-i`). Default endpoint `http://169.254.83.107:1234` (override `LOCAL_LLM_URL`).
- Strong tier: an Opencode Zen subscription. Configure once in `~/.claude/settings.json`:
  ```json
  { "env": { "OPENCODE_API_KEY": "<key>", "OPENCODE_MODEL": "<zen model id>", "OPENCODE_MODEL_OPEN": "<cheaper model id>" } }
  ```
  `OPENCODE_BASE_URL` optional (default `https://opencode.ai/zen/go/v1`). Never commit the key.
  `OPENCODE_MODEL_OPEN` is optional: when set, `--no-privacy` calls (fully non-confidential content)
  route to this cheaper/free model, while privacy-guarded calls keep using `OPENCODE_MODEL`.
  Explicit `--model` overrides the routing; the chosen model is announced on stderr.
  Both model vars accept a comma-separated fallback chain (e.g.
  `"deepseek-v4-flash-free,deepseek-v4-flash"`): on rate limit (429) or an unsupported model id,
  the call retries automatically on the next model in the chain.

## Switching the strong-tier model (Opencode Zen)
1. **List the model IDs available to your subscription** — run the probe; it prints every ID:
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/skills/local-llm/llm_strong.py" --check
    # available: minimax-m3, kimi-k2.6, glm-5.2, deepseek-v4-pro, qwen3.7-max, ...
   ```
   (Equivalently: `GET https://opencode.ai/zen/go/v1/models` with `Authorization: Bearer <key>`, or see the model catalog in the Opencode dashboard at https://opencode.ai/zen.)
2. **Switch permanently**: edit `OPENCODE_MODEL` in `~/.claude/settings.json` (new Claude Code sessions pick it up).
3. **Switch for one call**: pass `--model <id>` on the command line.

## Cross-tier consultation
`llm_strong.py --consult-local` gives the strong model a `consult_local` tool to query the free local
LLM mid-reasoning (brainstorms, drafts, second opinions). Privacy-safe: the question can only contain
what the cloud model already saw, and the local answer is redacted before upload.

## Install
```bash
claude plugin marketplace add <path-to-claude-plugins-folder>
claude plugin install local-llm-delegate@rulfe-tools
```

## Quick test
```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/local-llm/llm_local.py" --check    # local: ~3s, lists models
python "${CLAUDE_PLUGIN_ROOT}/skills/local-llm/llm_strong.py" --check   # strong: needs OPENCODE_API_KEY
```
Exit code 1 indicates endpoint failure, missing config, or a privacy refusal.

## Contents
- `.claude-plugin/plugin.json` — Plugin manifest & metadata
- `skills/local-llm/SKILL.md` — Delegation rules, tier routing, CLI flags, playbook
- `skills/local-llm/llm_local.py` — Stdlib-only CLI wrapper (local tier; also the shared engine)
- `skills/local-llm/runbooks/` — Bundled `--runbook NAME` prompt templates (`triage`, `summarize`, `count`, `review`, `commit`, `supervise`, `watch`); load one as the instruction preamble instead of hand-authoring. A runbook makes the positional prompt optional and auto-sets `--caveman`/`--tools` per template. Add project-specific runbooks via `$LLM_RUNBOOK_DIR`.
- `skills/local-llm/llm_strong.py` — Strong cloud tier with privacy guard (imports the engine)
- `AGENTS_SNIPPET.md` — Generic delegation snippet to paste into a project's AGENTS.md (fill the artifact-mapping table)
- `CHANGELOG.md` — Version history of the exportable engine

## Uninstall
```bash
claude plugin uninstall local-llm-delegate@rulfe-tools
```
