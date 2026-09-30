# Configured model routing correction — 30 September 2026

## Scope

Baseline: `4780b47161fb44b8130951c859fb9cb3efd4f60a`. This is a narrow correction to `llm_strong.py`, with offline tests and documentation. No provider credentials, endpoints, account settings or runtime environment were changed.

Previously a chain containing `-free` in either environment setting could override the other route's configured model. Five new test cases reproduce the mismatch on the baseline.

## Resulting precedence

1. Explicit `--model`, with its configured order of fallbacks
2. For `--no-privacy`, `OPENCODE_MODEL_OPEN` when configured
3. Otherwise `OPENCODE_MODEL` when configured
4. Existing built-in free default when no applicable configuration exists

With privacy enabled, an open-route setting alone does not select the destination; configure `OPENCODE_MODEL` explicitly. The built-in free default remains for compatibility and is **not** a confidentiality approval. A deliberately selected free model is still permitted with filtering enabled; the operator must assess its provider terms.

Explicit fallback chains, alias normalization, the endpoint compatibility adjustment and existing escalation/no-escalation rules are retained. This does not add automatic paid escalation to free-named chains. The existing non-free open-route escalation remains configurable and can be disabled with `--no-escalate`.

Fleet's historical `paid` boolean and labels are unchanged for compatibility. They represent intended filtering routes, not verified billing or data-handling properties. This patch corrects route selection rather than creating a provider-policy enforcement system.

## Executed verification

Command: `python -m unittest discover -s tests -v`

- Before source change: 17 cases executed, 5 failed, 12 passed
- After source change: 17 cases executed, 17 passed
- `python -m compileall -q skills tests`: passed
- The tests call the actual argument-parsing and selection entry point, replace the model execution engine, use a synthetic credential and make HTTP attempts fail
- Fleet worker construction is exercised with subprocess execution mocked
- Cases cover both privacy modes, configured precedence, explicit selection, missing settings/key, aliases, caller-provided fallback chains, free-chain escalation exclusion, `--no-escalate`, dry-run and retained privacy refusals

No live model request, paid API call or real credential was used. No user-side test is needed to reproduce this deterministic selection correction; use the included suite. Live model availability, provider terms, latency, output quality, redaction completeness and host execution isolation are outside this verification.

## Compatibility note

If both settings previously existed, the effective model can now change to the model the selected route explicitly configured. Inspect the printed model/chain before real use, particularly if that configured model is billed. No model names or provider settings were changed by the patch.
