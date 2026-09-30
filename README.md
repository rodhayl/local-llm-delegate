<!-- SPDX-License-Identifier: MIT -->

# local-llm-delegate

An experimental delegation toolkit for local analysis and external-model review in coding-agent workflows.

**Status: engineering prototype and portfolio case study. Not production-ready.** This project explores how context, model choice, cost and data exposure interact. It does not provide certified confidentiality, a hardened execution sandbox or a production service.

## Why I built it

Large logs, source files and intermediate findings can consume a coding agent's context. Sending everything to a stronger cloud model also raises questions about cost and what data should leave the machine.

I built a small Python toolkit to explore a split: a local model handles some bulk work, an external model can review selected findings or perform other explicitly delegated tasks, and the calling agent remains responsible for the result. Runbooks make recurring tasks easier to request.

Development and the public repository begin in **July 2026**. This is an applied integration experiment, not a claim to have invented model routing, hybrid inference or privacy filtering.

## What it demonstrates

- Integration of a local OpenAI-compatible model endpoint and the OpenCode Zen API behind related command-line interfaces
- Task decomposition, reusable runbooks, chunking and a worker/auditor review workflow
- Explicit attempts to control outgoing data through file exclusions, pattern-based redaction and tool restrictions
- Configurable model selection and usage telemetry to investigate cost/context trade-offs
- Testing material that exposes both intended behavior and the need to compare documentation with actual implementation

The repository offers concrete code to discuss in a technical review. It does not establish customer usage, measured savings for a business, universal model quality or production readiness.

## Intended workflow and current behavior

The local tier is `llm_local.py`; the external tier is `llm_strong.py`. Both are Python CLIs. The external tier calls the OpenCode Zen API; this is not a complete orchestrator for arbitrary vendor CLI applications.

The intended policy distinguishes local work, external work with filtering, and non-sensitive external work where the filtering can be disabled. “Strong” is a role name; the configured external model is not necessarily stronger or faster.

### Model selection

Selection follows the requested route:

1. An explicit `--model` takes precedence, including its caller-supplied fallback chain
2. With `--no-privacy`, `OPENCODE_MODEL_OPEN` is used when configured
3. Otherwise `OPENCODE_MODEL` is used when configured
4. If the selected route has no applicable model configuration, the existing built-in free-model default is retained

A model name containing `-free` no longer overrides another route's configured model. `OPENCODE_MODEL_OPEN` alone does not configure the privacy-on route. Configure `OPENCODE_MODEL` explicitly for that route rather than assuming it inherits a suitable destination.

This is model-selection precedence, not provider privacy enforcement. Configured chains retain their order and may contain free or paid models. Availability and data terms need independent review. Fleet's historical `paid`/`FREE` labels describe intended filtering routes; they are not verified price or confidentiality classifications.

The existing escalation policy is unchanged: free-named chains do not acquire automatic paid escalation, while configured non-free open routes can use the existing escalation unless `--no-escalate` is set. Explicitly configured fallback chains remain explicit choices.

See [the selection logic](skills/local-llm/llm_strong.py) and [offline routing tests](tests/test_model_routing.py).

**Cost and confidentiality are separate properties.** A paid model is not automatically appropriate for confidential data, and a free model's data policy must be checked individually. Review [OpenCode Zen's current privacy terms](https://opencode.ai/docs/zen/#privacy) and the actual provider before sharing anything.

## Safety boundaries

- The external tier sends data to a cloud service. Its input can include supplied files after filtering; it is not structurally restricted to short summaries
- Local processing stays local only when the configured endpoint and enabled tools remain local. A remote `LOCAL_LLM_URL`, host tools or later forwarding by the calling agent changes that boundary
- Privacy mode is on by default for the external wrapper. It blocks selected file patterns and some tool/image paths and applies pattern-based redaction. These controls can miss secrets, proprietary code and contextual identifiers
- `--no-privacy` disables those protections. Use only with data approved for the selected destination; it is not a general workaround for a privacy refusal
- `--tools` enables host Python execution. `--confidential-tools` adds filtering and pattern/allowlist checks, but **neither is an OS security sandbox**. Do not use with production credentials or untrusted code outside an appropriately isolated environment
- `--require-model` checks model identity; it does not certify the model's quality or safety
- Review generated findings and proposed actions. Redaction tests and a successful model response do not establish end-to-end confidentiality

## Quick start

Begin with non-sensitive text and no tool execution.

1. Install [LM Studio](https://lmstudio.ai/) and load a model compatible with the tasks you plan to test
2. Check the configured local endpoint:
   ```bash
   python skills/local-llm/llm_local.py --check
   ```
3. Try a small text-only request:
   ```bash
   echo "hello world" | python skills/local-llm/llm_local.py "count words" --stdin --caveman
   ```

Function calling is needed for tool use; vision support is needed for image input. Local inference uses your hardware and is not cost-free in the broader sense.

## Installation and configuration

The Python engine uses the standard library. See [pyproject.toml](pyproject.toml) for the supported Python version.

### Claude Code integration

If you already maintain a compatible plugin marketplace, add its path and use the marketplace name actually configured there:

```bash
claude plugin marketplace add <path-to-claude-plugins-folder>
claude plugin install local-llm-delegate@<your-marketplace-name>
```

Alternatively, follow your installed agent's skill-loading instructions to use `skills/local-llm/`, or call the Python scripts directly. No hosted plugin marketplace or automatic integration with every CLI is promised.

### Model endpoints

- Local: default `http://127.0.0.1:1234`; override using `LOCAL_LLM_URL`
- External: OpenCode Zen account/API access and `OPENCODE_API_KEY`; usage may be billed
- `OPENCODE_BASE_URL` overrides the default `https://opencode.ai/zen/v1`
- `OPENCODE_MODEL` and `OPENCODE_MODEL_OPEN` configure model chains, subject to the selection precedence above

For a Claude Code setup, environment variables can be configured in its local settings:

```json
{
  "env": {
    "OPENCODE_API_KEY": "<key>",
    "OPENCODE_MODEL": "<approved model id>",
    "OPENCODE_MODEL_OPEN": "<approved non-sensitive-work model id>"
  }
}
```

Keep credentials outside Git. Verify current model IDs and inspect the reported selected model rather than inferring it from a tier label. Fallbacks may change the model actually used.

```bash
python skills/local-llm/llm_local.py --check
python skills/local-llm/llm_strong.py --check
```

A non-zero exit can indicate missing configuration, unavailable endpoints/models or a refusal. The external check requires credentials; this README does not execute it.

## Fleet review and consultation

`fleet_review.py` partitions a repository review into workers and sends merged findings to an auditor. Preview file selection and intended tiers first:

```bash
python skills/local-llm/fleet_review.py --scope "src/**" --confidential-glob "config/**" --dry-run
```

A dry-run is not a quoted price or proof of provider privacy. “PAID” and “FREE” labels describe intended routing categories and do not establish the effective model price or data policy. See [the fleet runbook](skills/local-llm/runbooks/fleet.md).

`llm_strong.py --consult-local` lets the external model ask a local model a question. In privacy mode the question and returned answer pass through redaction. This is a useful review mechanism to evaluate, not a guarantee that a second opinion is correct or private.

## Telemetry

Usage records and [delegation_savings.py](skills/local-llm/delegation_savings.py) help inspect calls and offloaded tokens. Token counts are not measured financial savings or a quality benchmark: use an explicit comparison baseline and actual provider pricing. Treat stored prompts, outputs and reports as potentially sensitive.

## Evaluation evidence

The repository retains [TEST_PROMPT.md](TEST_PROMPT.md), a 58-case plan across 14 phases, and [TEST_PROMPT_REPORT.md](TEST_PROMPT_REPORT.md), the recorded execution report.

That historical report records **58 passed / 0 failed** in its particular setup, including local/cloud interaction and selected privacy checks. It is not an independent production certification, a guarantee for current providers, or a new test run performed for this documentation update. A single example of a reviewer catching a model error does not establish a general detection rate.

<details>
<summary>Retained test-plan coverage</summary>

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

</details>

Before adopting or extending this prototype, reproduce the relevant cases in your environment and test model routing, data filtering, failure recovery and host execution separately. Do not use live confidential data as a test fixture.

### Routing regression update, 30 September 2026

The configured-route precedence correction has 17 offline unittest cases, including five failures reproduced before the fix. They exercise the real CLI parsing/selection with a mocked execution engine, synthetic credentials and blocked HTTP. No live model calls or billing occurred. This establishes the narrow routing behavior, not end-to-end model quality or confidentiality. See [the change report](docs/ROUTING_FIX_20260930.md).

## Troubleshooting

| Problem | Next check |
| --- | --- |
| Endpoint responds but no model is loaded | Load a model in LM Studio and repeat the local check |
| Missing `OPENCODE_API_KEY` | Configure it privately for the process that runs the wrapper |
| Privacy-mode file refusal | Stop and review the file and destination; do not disable privacy merely to make the call succeed |
| Slow responses | Check model/hardware and input size; shorter requested output does not guarantee shorter reasoning |
| No files match | Check the path/glob and exclusions |
| Output truncated | Review limits and consider chunking; inspect the result before further use |
| Unexpected free/paid model | Read the effective selection and chain; see the selection precedence above |

## Known limitations

- Pattern-based filtering is incomplete and does not determine all confidentiality requirements
- Host tool execution lacks a hardened OS/container sandbox
- Fleet tier labels do not verify effective model pricing or provider data terms
- Large inputs, reasoning models and rate limits can make execution slow or costly
- Fleet concurrency and per-call limits depend on the implementation/configuration; inspect the active settings
- Examples, model names and external services may have changed since July 2026

## Repository map

- [llm_local.py](skills/local-llm/llm_local.py): local tier and shared execution engine
- [llm_strong.py](skills/local-llm/llm_strong.py): external tier, filtering and model selection
- [fleet_review.py](skills/local-llm/fleet_review.py): review workers and auditor
- [delegation_savings.py](skills/local-llm/delegation_savings.py): usage summary
- [SKILL.md](skills/local-llm/SKILL.md): agent-facing instructions and flags
- [runbooks](skills/local-llm/runbooks/): triage, summarize, count, review, commit, supervise, watch, fleet and improve templates
- [.claude-plugin/plugin.json](.claude-plugin/plugin.json): plugin metadata
- [AGENTS_SNIPPET.md](AGENTS_SNIPPET.md): example integration guidance
- [CHANGELOG.md](CHANGELOG.md): recorded evolution
- [SECURITY.md](SECURITY.md) and [CONTRIBUTING.md](CONTRIBUTING.md): security and contribution notes

Older descriptions in historical reports or agent snippets may reflect the intended design rather than the current behavior. The limitations above take precedence when assessing this snapshot; read the implementation before trusting a security or routing claim.

## Uninstall

If installed as a Claude Code plugin, uninstall it using the marketplace name used during installation:

```bash
claude plugin uninstall local-llm-delegate@<your-marketplace-name>
```

## License

MIT. See [LICENSE](LICENSE).

Documentation positioning reviewed on 30 September 2026. The subsequent routing correction is documented above; production readiness remains unclaimed.

