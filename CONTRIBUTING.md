<!-- SPDX-License-Identifier: MIT -->

# Contributing to local-llm-delegate

## Development setup

1. Clone the repo
2. Install Python 3.10+
3. No external dependencies — stdlib only

## Running tests

```bash
# Quick smoke test
python skills/local-llm/llm_local.py --check
python skills/local-llm/llm_strong.py --dry-run "test"

# Full test suite (requires LM Studio + OPENCODE_API_KEY)
# See TEST_PROMPT.md for the 58-test end-to-end plan
```

## Code style

- Stdlib only — no external dependencies
- Keep scripts self-contained (each `.py` file is a standalone CLI tool)
- Privacy guard changes must be tested with `--no-privacy` and without
- All new flags must be documented in `SKILL.md`

## Pull requests

1. Run the test plan (`TEST_PROMPT.md`) before submitting
2. Update `CHANGELOG.md` with your changes
3. Keep commits focused — one logical change per commit
