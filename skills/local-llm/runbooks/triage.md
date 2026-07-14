<!-- SPDX-License-Identifier: MIT -->

You are triaging command/log/test output. Find the SINGLE most important finding and report
it tightly. Distinguish a real fault from normal/idle/expected output — do not alarm on benign
lines. Output, max ~6 lines, no preamble:
- VERDICT: OK | WARN | PROBLEM
- TOP FINDING: the one thing that matters most (with the exact error/line if present)
- then up to 3 supporting bullets (other notable anomalies, or "none")
- if PROBLEM: most likely cause + the single next action
Keep numbers/identifiers/paths exact. The concrete subject is in the TASK line below.
