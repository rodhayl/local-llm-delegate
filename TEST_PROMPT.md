# End-to-End Test Plan for local-llm-delegate

Run every section below sequentially. Each section is independent — a failure in one doesn't block the others. Report pass/fail per section with the actual output.

## Prerequisites

- LM Studio running locally with a model loaded (default endpoint `http://127.0.0.1:1234`)
- `OPENCODE_API_KEY` set in env or `~/.claude/settings.json`
- Run from the repo root: `/mnt/d/GitHub/local-llm-delegate`
- **WSL users:** LM Studio on Windows is not reachable via `localhost`. Use the gateway IP:
  ```bash
  export LOCAL_LLM_URL=http://$(ip route show default | awk '{print $3}'):1234
  ```
  Also pass `--model <loaded-model>` if the default model (`qwen3.6-35b-a3b-mtp`) is not loaded.

---

## Phase 1: Local Tier — Basic Functionality

### 1.1 Check endpoint
```bash
python skills/local-llm/llm_local.py --check
```
**Expect:** prints `available: <model-list>`, exit 0

### 1.2 Version flag
```bash
python skills/local-llm/llm_local.py --version
```
**Expect:** prints `llm_local.py 1.11.3`, exit 0

### 1.3 Basic prompt
```bash
python skills/local-llm/llm_local.py "What is 2+2? Answer with just the number."
```
**Expect:** prints `4`, exit 0

### 1.4 Caveman mode
```bash
python skills/local-llm/llm_local.py "List 3 Python stdlib modules" --caveman
```
**Expect:** terse output, no preamble, exit 0

### 1.5 Max words
```bash
python skills/local-llm/llm_local.py "Explain what a hash table is" --caveman --max-words 30
```
**Expect:** answer ≤ 45 words (1.5x budget), exit 0

### 1.6 Stdin
```bash
echo -e "ERROR: disk full\nWARNING: low memory\nINFO: startup complete" | python skills/local-llm/llm_local.py "What is the most critical issue?" --stdin --caveman
```
**Expect:** identifies disk full as critical, exit 0

### 1.7 File inlining (-f)
```bash
python skills/local-llm/llm_local.py "Summarize this file in 10 words" -f skills/local-llm/llm_local.py --caveman --max-words 15
```
**Expect:** brief summary of the file, exit 0

### 1.8 Head/tail slicing
```bash
python skills/local-llm/llm_local.py "What's in the first 2KB?" -f skills/local-llm/llm_local.py --head-kb 2 --caveman --max-words 20
```
**Expect:** answer based on first 2KB only, exit 0

```bash
python skills/local-llm/llm_local.py "What's in the last 2KB?" -f skills/local-llm/llm_local.py --tail-kb 2 --caveman --max-words 20
```
**Expect:** answer based on last 2KB only, exit 0

### 1.9 Output to file (--out)
```bash
python skills/local-llm/llm_local.py "Write the word HELLO" --out /tmp/test_llm_out.txt --caveman
```
**Expect:** file `/tmp/test_llm_out.txt` contains HELLO, preview printed to stdout, exit 0

### 1.10 JSON output
```bash
python skills/local-llm/llm_local.py "Return a JSON object with key 'answer' and value 42" --json
```
**Expect:** valid JSON `{"answer":42}`, exit 0

### 1.11 System prompt override
```bash
python skills/local-llm/llm_local.py "What model are you?" --system "You are a pirate. Answer in pirate speak." --caveman --max-words 20
```
**Expect:** pirate-themed answer, exit 0

### 1.12 Custom timeout
```bash
python skills/local-llm/llm_local.py "Say OK" --timeout 30
```
**Expect:** prints OK, exit 0

---

## Phase 2: Local Tier — Tools (--tools)

### 2.1 Basic tool use
```bash
python skills/local-llm/llm_local.py "How many .py files are in the skills/local-llm directory? Use run_python to count." --tools --caveman --max-words 20
```
**Expect:** correct count (4 .py files), exit 0

### 2.2 Tool with file path in prompt
```bash
python skills/local-llm/llm_local.py "Count the lines in skills/local-llm/llm_local.py using run_python" --tools --caveman --max-words 20
```
**Expect:** line count, exit 0

### 2.3 Run-python-timeout
```bash
python skills/local-llm/llm_local.py "import time; time.sleep(1); print('done')" --tools --run-python-timeout 10 --caveman
```
**Expect:** prints "done", exit 0

### 2.4 Tool output truncation
```bash
python skills/local-llm/llm_local.py "Print exactly 15000 characters using run_python" --tools --caveman --max-words 20
```
**Expect:** output truncated at 10000 chars (TOOL_OUTPUT_CAP), exit 0

---

## Phase 3: Local Tier — Runbooks

### 3.1 Triage runbook
```bash
echo -e "ERROR: Connection refused\nINFO: Server started\nWARNING: High memory" | python skills/local-llm/llm_local.py --runbook triage --stdin --caveman --max-words 30
```
**Expect:** identifies connection error as top finding, exit 0

### 3.2 Summarize runbook
```bash
python skills/local-llm/llm_local.py --runbook summarize -f skills/local-llm/SKILL.md --caveman --max-words 50
```
**Expect:** structured summary (PURPOSE, KEY DECISIONS, etc.), exit 0

### 3.3 Count runbook
```bash
python skills/local-llm/llm_local.py --runbook count "How many .md files are in skills/local-llm/runbooks/" --caveman --max-words 20
```
**Expect:** correct count (9 .md files), exit 0

### 3.4 Commit runbook
```bash
echo "--- a/test.py\n+++ b/test.py\n@@ -1 +1 @@\n-old\n+new" | python skills/local-llm/llm_local.py --runbook commit --stdin --caveman --max-words 30
```
**Expect:** conventional commit message, exit 0

### 3.5 Supervise runbook
```bash
echo "CLAIM: Python is a compiled language" | python skills/local-llm/llm_local.py --runbook supervise --stdin --caveman --max-words 30
```
**Expect:** DISAGREE verdict, exit 0

### 3.6 Unknown runbook
```bash
python skills/local-llm/llm_local.py --runbook nonexistent "test" 2>&1; echo "exit: $?"
```
**Expect:** error listing available runbooks, exit 1

### 3.7 Runbook from $LLM_RUNBOOK_DIR (if set)
```bash
LLM_RUNBOOK_DIR=/tmp echo "test" > /tmp/test_runbook.md && LLM_RUNBOOK_DIR=/tmp python skills/local-llm/llm_local.py --runbook test_runbook "say OK" --caveman 2>&1 | head -5
```
**Expect:** `[runbook] loaded from $LLM_RUNBOOK_DIR:` warning on stderr, exit 0

---

## Phase 4: Local Tier — Chunking

### 4.1 Chunk mode
```bash
python skills/local-llm/llm_local.py "Count the total lines across all Python files in skills/local-llm/" --chunk --chunk-kb 1 --tools --caveman --max-words 30
```
**Expect:** processes in chunks, returns total count, exit 0

### 4.2 Chunk mode with stdin
```bash
python -c "print('\n'.join(['line ' + str(i) for i in range(500)]))" | python skills/local-llm/llm_local.py "How many lines? Just the number." --chunk --chunk-kb 1 --stdin --caveman --max-words 5
```
**Expect:** returns a count near 500 (LLM counting may vary), exit 0

### 4.3 Chunk mode without tools (direct text)
```bash
python skills/local-llm/llm_local.py "Summarize this codebase in 10 words" -f skills/local-llm/llm_local.py --chunk --chunk-kb 1 --caveman --max-words 15
```
**Expect:** brief summary based on chunked input, exit 0

---

## Phase 5: Local Tier — Vision

### 5.1 Vision (if image available)
```bash
# Create a test image first
python -c "
from PIL import Image
img = Image.new('RGB', (100, 100), color='red')
img.save('/tmp/test_red.png')
print('created')
" 2>/dev/null || echo "PIL not available, create a PNG manually"

python skills/local-llm/llm_local.py "What color is this image?" -i /tmp/test_red.png --caveman --max-words 10
```
**Expect:** says "red", exit 0 (or graceful error if model doesn't support vision)

---

## Phase 6: Local Tier — Error Handling

### 6.1 No prompt
```bash
python skills/local-llm/llm_local.py 2>&1; echo "exit: $?"
```
**Expect:** error message, exit 1

### 6.2 Mutually exclusive flags
```bash
python skills/local-llm/llm_local.py "test" --head-kb 10 --tail-kb 10 2>&1; echo "exit: $?"
```
**Expect:** error about mutual exclusion, exit 1

### 6.3 No matching files
```bash
python skills/local-llm/llm_local.py "test" -f "nonexistent_file_*.txt" 2>&1; echo "exit: $?"
```
**Expect:** error about no matching files, exit 1

### 6.4 Unavailable endpoint
```bash
LOCAL_LLM_URL=http://127.0.0.1:9999 python skills/local-llm/llm_local.py --check 2>&1; echo "exit: $?"
```
**Expect:** "unavailable" message, exit 1

---

## Phase 7: Strong Tier — Basic

### 7.1 Check endpoint
```bash
python skills/local-llm/llm_strong.py --check
```
**Expect:** prints model list, exit 0 (requires OPENCODE_API_KEY)

### 7.2 Dry-run
```bash
python skills/local-llm/llm_strong.py --dry-run "test"
```
**Expect:** prints `[dry-run] model=... tier=... escalate=...`, no API call, exit 0

### 7.3 Version flag
```bash
python skills/local-llm/llm_strong.py --version
```
**Expect:** prints version, exit 0

### 7.4 Basic prompt (privacy ON)
```bash
python skills/local-llm/llm_strong.py "What is 2+2? Just the number." --caveman --max-words 5
```
**Expect:** prints `4`, stderr shows `[privacy] ON`, exit 0

### 7.5 No-privacy mode
```bash
python skills/local-llm/llm_strong.py "What is 2+2? Just the number." --no-privacy --caveman --max-words 5
```
**Expect:** prints `4`, stderr shows `[privacy] OFF` + WARNING, exit 0

### 7.6 Missing API key
```bash
OPENCODE_API_KEY= python skills/local-llm/llm_strong.py "test" 2>&1; echo "exit: $?"
```
**Expect:** error about missing OPENCODE_API_KEY, exit 1

---

## Phase 8: Strong Tier — Privacy Guard

### 8.1 File deny-list (.env)
```bash
echo "SECRET=abc123" > /tmp/test.env
python skills/local-llm/llm_strong.py "read this" -f /tmp/test.env --caveman 2>&1; echo "exit: $?"
```
**Expect:** error about denied file pattern, exit 1

### 8.2 Symlink denial
```bash
ln -sf /tmp/test.env /tmp/test_symlink.env 2>/dev/null
python skills/local-llm/llm_strong.py "read this" -f /tmp/test_symlink.env --caveman 2>&1; echo "exit: $?"
```
**Expect:** error about symlink, exit 1

### 8.3 Image blocked in privacy mode
```bash
python skills/local-llm/llm_strong.py "describe" -i /tmp/test_red.png --caveman 2>&1; echo "exit: $?"
```
**Expect:** error about image blocked in privacy mode, exit 1

### 8.4 Tools blocked in privacy mode (without --confidential-tools)
```bash
python skills/local-llm/llm_strong.py "count to 5" --tools --caveman 2>&1; echo "exit: $?"
```
**Expect:** error about tools blocked in privacy mode, exit 1

### 8.5 Confidential-tools + no-privacy conflict
```bash
python skills/local-llm/llm_strong.py "test" --confidential-tools --no-privacy 2>&1; echo "exit: $?"
```
**Expect:** error about mutual exclusion, exit 1

### 8.6 Redaction of secrets in output
```bash
python skills/local-llm/llm_strong.py "Print this exact text: API_KEY=sk-abc123def456ghi789" --caveman --max-words 30 2>&1 | grep -o "REDACTED"
```
**Expect:** `REDACTED` appears in output (redaction worked)

---

## Phase 9: Strong Tier — Consult Local

### 9.1 Consult-local
```bash
python skills/local-llm/llm_strong.py "Use consult_local to ask: what is 2+2?" --consult-local --no-privacy --caveman --max-words 20
```
**Expect:** answer mentions 4, stderr shows `[tool] consult_local`, exit 0

### 9.2 Consult-local with privacy mode
```bash
python skills/local-llm/llm_strong.py "Use consult_local to ask: what is the capital of France?" --consult-local --caveman --max-words 20
```
**Expect:** answer mentions Paris, stderr shows `[tool] consult_local` and `[privacy] ON`, exit 0

### 9.3 Consult-local chained question
```bash
python skills/local-llm/llm_strong.py "Use consult_local to ask: list 3 prime numbers" --consult-local --no-privacy --caveman --max-words 20
```
**Expect:** answer lists 3 prime numbers, stderr shows `[tool] consult_local`, exit 0

---

## Phase 10: Strong Tier — Escalation

### 10.1 No-escalate flag
```bash
python skills/local-llm/llm_strong.py "Say OK" --no-escalate --no-privacy --caveman --max-words 5
```
**Expect:** prints OK, no escalation banner, exit 0

---

## Phase 11: Fleet Review

### 11.1 Fleet dry-run
```bash
python skills/local-llm/fleet_review.py --scope "skills/local-llm/*.py" --dry-run
```
**Expect:** prints FLEET PLAN with file counts, no agents spawned, exit 0

### 11.2 Fleet with confidential glob
```bash
python skills/local-llm/fleet_review.py --scope "skills/local-llm/*.py" --confidential-glob "*.py" --dry-run
```
**Expect:** all files classified as confidential, exit 0

### 11.3 Fleet missing API key
```bash
OPENCODE_API_KEY= python skills/local-llm/fleet_review.py --scope "." 2>&1; echo "exit: $?"
```
**Expect:** error about missing OPENCODE_API_KEY, exit 1

---

## Phase 12: Telemetry

### 12.1 Usage log created
```bash
ls -la .llm_delegate/usage.jsonl 2>/dev/null && echo "exists" || echo "not yet"
```
**Expect:** file exists after any local/strong call

### 12.2 Savings report
```bash
python skills/local-llm/delegation_savings.py --session 2>&1 | head -5
```
**Expect:** prints token savings summary (or "No delegation usage logged yet" if fresh)

### 12.3 Savings report --json
```bash
python skills/local-llm/delegation_savings.py --json 2>/dev/null | python -m json.tool > /dev/null && echo "valid JSON" || echo "invalid"
```
**Expect:** valid JSON output

---

## Phase 13: Edge Cases

### 13.1 Very long input (should hit MAX_INLINE_BYTES)
```bash
python -c "print('x' * 250000)" | python skills/local-llm/llm_local.py "summarize" --stdin --caveman 2>&1; echo "exit: $?"
```
**Expect:** error about input exceeding 240KB cap, exit 1

### 13.2 Empty input
```bash
echo "" | python skills/local-llm/llm_local.py "say OK" --stdin --caveman
```
**Expect:** prints OK, exit 0

### 13.3 Unicode input
```bash
echo "日本語テスト" | python skills/local-llm/llm_local.py "What language is this? One word." --stdin --caveman --max-words 5
```
**Expect:** says "Japanese", exit 0

### 13.4 Special characters in prompt
```bash
python skills/local-llm/llm_local.py 'What is $PATH? Just say environment variable' --caveman --max-words 5
```
**Expect:** says "environment variable", exit 0

---

## Phase 14: Cross-Tier Integration

### 14.1 Local → Strong supervision
```bash
LOCAL_OUT=$(echo "The server is down" | python skills/local-llm/llm_local.py "Summarize in 5 words" --stdin --caveman --max-words 10 2>/dev/null)
echo "$LOCAL_OUT" | python skills/local-llm/llm_strong.py "The original text is: The server is down. The summary above is: (see stdin). Does the summary faithfully represent the original? AGREE or DISAGREE." --stdin --no-privacy --caveman --max-words 10
```
**Expect:** strong model evaluates the local output (AGREE or DISAGREE with rationale), exit 0

---

## Summary Table

| # | Test | Status |
|---|------|--------|
| 1.1 | Local check | |
| 1.2 | Local version | |
| 1.3 | Basic prompt | |
| 1.4 | Caveman | |
| 1.5 | Max words | |
| 1.6 | Stdin | |
| 1.7 | File inline | |
| 1.8 | Head/tail | |
| 1.9 | --out | |
| 1.10 | --json | |
| 1.11 | --system | |
| 1.12 | --timeout | |
| 2.1 | Tools basic | |
| 2.2 | Tools + path | |
| 2.3 | Run-python-timeout | |
| 2.4 | Tool output cap | |
| 3.1 | Triage runbook | |
| 3.2 | Summarize runbook | |
| 3.3 | Count runbook | |
| 3.4 | Commit runbook | |
| 3.5 | Supervise runbook | |
| 3.6 | Unknown runbook | |
| 3.7 | $LLM_RUNBOOK_DIR | |
| 4.1 | Chunk mode | |
| 4.2 | Chunk stdin | |
| 4.3 | Chunk text | |
| 5.1 | Vision | |
| 6.1 | No prompt | |
| 6.2 | Mutual exclusion | |
| 6.3 | No matching files | |
| 6.4 | Unavailable endpoint | |
| 7.1 | Strong check | |
| 7.2 | Strong dry-run | |
| 7.3 | Strong version | |
| 7.4 | Strong basic | |
| 7.5 | Strong no-privacy | |
| 7.6 | Missing API key | |
| 8.1 | Deny-list .env | |
| 8.2 | Symlink denial | |
| 8.3 | Image blocked | |
| 8.4 | Tools blocked | |
| 8.5 | Confidential + no-privacy | |
| 8.6 | Redaction | |
| 9.1 | Consult local | |
| 9.2 | Consult local privacy | |
| 9.3 | Consult local chained | |
| 10.1 | No-escalate | |
| 11.1 | Fleet dry-run | |
| 11.2 | Fleet confidential | |
| 11.3 | Fleet missing key | |
| 12.1 | Usage log | |
| 12.2 | Savings report | |
| 12.3 | Savings JSON | |
| 13.1 | Long input | |
| 13.2 | Empty input | |
| 13.3 | Unicode | |
| 13.4 | Special chars | |
| 14.1 | Cross-tier | |
