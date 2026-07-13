# Fleet review runbook — swarm the whole codebase, audited before return

Fan a swarm of strong-model agents across an entire codebase to find ALL issues,
then have a separate strong agent audit the merged findings before anything comes
back to you. The orchestration is deterministic (a local commander script) so the
fan-out, confidentiality routing, and cost stay predictable — the agents do the
judgement, the script does the plumbing.

## How to run it

The commander is `fleet_review.py` (sits next to `llm_strong.py`). It IS the fleet —
running it sends the worker agents and the auditor agent for you:

```
# 1. PLAN first — no agents, no cost. Confirm the partition + routing.
python .../skills/local-llm/fleet_review.py --scope "src/**" \
    --confidential-glob "config/**" --dry-run

# 2. Real run. Workers + auditor; only the audited report comes back.
python .../skills/local-llm/fleet_review.py --scope "src/**" \
    --confidential-glob "config/**" --max-words 350
```

Always `--dry-run` first on an unfamiliar scope to see how many PAID vs FREE workers
it will launch.

## The fleet (three roles)

1. **Commander** (`fleet_review.py`, local): enumerates `git ls-files`, keeps only
   reviewable source, classifies each file, partitions into byte-budgeted slices, and
   dispatches workers in parallel (`--concurrency`, default 4 — 429-friendly).
2. **Worker agents** (`llm_strong.py --runbook review`, parallel): each reviews one
   slice with the false-positive-resistant `review` runbook (confidence-tagged).
3. **Auditor agent** (one `llm_strong.py`, PAID privacy-ON): receives ALL merged
   worker findings, dedupes cross-worker duplicates, drops the false positives a
   single worker can't see are dups, ranks by severity, emits ONE compact table.
   This is the only thing returned — raw per-worker findings are saved to
   `.llm_delegate/fleet_findings_raw.md` for drill-down, not surfaced.

## Confidentiality routing (operator requirement)

| Tier | Files | Agent | Model |
|------|-------|-------|-------|
| **skip** | hard-denied (`.env`, `*secret*`, `*token*`, keys, `live_config_snapshot_*` — via `llm_strong.denied_pattern`) | none — **never uploaded**, listed for a human | — |
| **confidential** | match a `--confidential-glob` / `LLM_FLEET_CONFIDENTIAL_GLOBS` | **PAID** strong, privacy ON (content redacted on upload) | `OPENCODE_MODEL` |
| **non-confidential** | everything else | **FREE** strong, `--no-privacy` | `OPENCODE_MODEL_OPEN` |

The auditor always runs PAID privacy-ON (it sees findings that may quote confidential
code). Pass `--audit-no-privacy` only when the whole scope is known non-secret.

Set this project's confidential globs once (so a bare run routes correctly):
`LLM_FLEET_CONFIDENTIAL_GLOBS=config/**,src/scalping_bot/runtime/**` (env), or pass
`--confidential-glob` per run.

## Efficiency knobs (keep the report — and the bill — tight)

- `--files-per-worker N` / `--kb-per-worker N` — size each agent's slice (default 12 / 110KB).
- `--max-workers N` — hard cap on fan-out (0 = unlimited); excess slices merge into the last.
- `--concurrency N` — parallel API calls; default 2 and **hard-capped at 2** — higher
  fan-out triggers backend errors (rate-limit / connection resets).
- `--worker-max-words` (220) / `--max-words` (final, 400) — word budgets; workers and
  auditor run `--caveman`, so the report is a table, not prose.
- Workers that error are recorded and the run continues; the run summary on stderr
  reports `workers/ok/paid/free/skipped_sensitive` + token totals + wall time.

## Optional: drive it from a cloud commander

If you want a strong agent (not your local shell) to launch the fleet, allowlist the
script under confidential-tools — it runs `fleet_review.py` in ONE guarded subprocess:

```
python .../llm_strong.py "Run the fleet review over src/** with confidential glob
config/**, then report the auditor's verdict and table verbatim."
    --confidential-tools --allow-script fleet_review.py
```

The commander's findings come back redacted (expected); the un-redacted audited report
is on disk at `.llm_delegate/fleet_report.md`.

## TASK
Run the fleet over the scope below, then report the auditor's verdict line and table
verbatim plus the one-line run summary. Do not re-review files yourself.
