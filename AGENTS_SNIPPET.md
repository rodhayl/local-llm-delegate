<!-- SPDX-License-Identifier: MIT -->

## LLM Delegates — two-tier split

**Delegation is the DEFAULT, not an option.** Before every Read/Grep/file-dump that returns content you'd only skim, ask: "do I need the CONCLUSION or the content?" — conclusion → DELEGATE.

### When to delegate

- Any log/test/diff output, any size
- Any count/aggregation (`local --tools` + file PATH)
- Any doc/file ≳100 lines (`local -f FILE --caveman`)
- Code/architecture "what/where/how" questions

**Read content yourself ONLY** when you will edit it, quote it verbatim, decide on it, or act on it (commits, git, small outputs). Probe `--check` first; answer → stdout, usage/timing → stderr.

### Local tier (free, private)

`llm_local.py` — free LM Studio, **nothing leaves the machine**. Use for: bulk analysis, data aggregation, log triage, vision (`-i`), first-pass drafts. `--tools` for exact counting (raise `--run-python-timeout N` for big jobs). `--require-model NAME` preflights that the expected model is loaded.

### Strong tier (cloud, privacy guard)

`llm_strong.py` — Opencode Zen cloud. **Supervises** load-bearing local conclusions (sees only the distilled, redacted result). Privacy guard ON by default (sensitive-file deny-list + redaction; blocks `--tools`/`-i`).

**Cost routing:** privacy-ON → `OPENCODE_MODEL` (PAID); `--no-privacy` → `OPENCODE_MODEL_OPEN` (FREE). **Default to `--no-privacy` for non-confidential work.** Auto-escalation: free tier self-upgrades to paid once if it truncates or returns invalid JSON (`--no-escalate` opts out).

`--confidential-tools` runs `run_python` under privacy with EVERY tool output redacted AND a guard (subprocesses restricted to allowlisted scripts; destructive code refused).

### Confidentiality invariant

Raw confidential data (full logs/configs/snapshots) → LOCAL only; only a distilled conclusion ever goes to STRONG.

### Supervise a load-bearing local conclusion

```
LOCAL_OUT=$(… | llm_local "analyze" --stdin --caveman); echo "$LOCAL_OUT" | llm_strong "Supervise: agree or correct, flag errors" --stdin --caveman
```

### Code review (free tier)

```
git diff -- files | python llm_strong.py "review for correctness/safety bugs; SEVERITY|where|issue|fix" --no-privacy --stdin --caveman --max-words 400
```

Split inputs >240KB with `--head-kb/--tail-kb`. ALWAYS verify load-bearing findings against the code yourself.

### Telemetry (automatic)

Every call logged to `./.llm_delegate/usage.jsonl`. Report: `python delegation_savings.py --session`.

### Runbook templates

`--runbook NAME` prepends a bundled template as the prompt preamble. Makes the positional prompt optional (pipe data via `--stdin`/`-f`). Bundled: `triage`, `summarize`, `count`, `review`, `commit`, `supervise`, `watch`. **Safety-collision:** if a delegated call is blocked/times-out, fall back to doing it in-context.

### Rules

1. Counting/aggregation → `--tools` + file PATH in prompt (never inline via `-f`)
2. Append `--caveman --max-words N` unless exact quotes or `--json` required
3. Verify critical claims locally; delegate only analysis, never code edits or irreversible actions

### Project delegation targets

| Target | Command |
|--------|---------|
| `<main log path>` | local: `--tools` + path (large) or `-f LOG --tail-kb 80 --caveman` (small) |
| `<results DB/JSON>` | local: `--tools` + path in prompt |
| `<big report docs>` | local: `--caveman --max-words 50` pre-read |
| `<screenshots>` | local: `-i IMG` |
| `<decision-critical>` | strong: second-opinion (`--caveman --max-words 80`) |
| `<brainstorm>` | strong + `--consult-local` |
