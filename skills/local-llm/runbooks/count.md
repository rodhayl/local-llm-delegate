<!-- SPDX-License-Identifier: MIT -->

You must produce EXACT counts/aggregations over a data file (CSV / JSON / JSONL / SQLite / log).
Use your python tool to compute — never estimate by eye, never do arithmetic in prose (that
truncates and returns empty). Run this call with `--tools` and pass the file PATH in the TASK
line (do NOT inline the file with -f). Steps:
1. Inspect structure (columns/keys/schema) with python.
2. Compute the requested counts / group-bys / sums with python.
3. Report EXACT numbers in a compact table or bullet list — no narrative.
State the row/record total you scanned so the caller can sanity-check coverage. The dataset and
the exact question are in the TASK line below.
