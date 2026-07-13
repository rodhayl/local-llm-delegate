Draft ONE conventional-commit message from the staged diff in the input. Output ONLY the
message — no preamble, no fences, nothing else. Format:
  type(scope): concise subject in imperative mood, <=72 chars
  <blank line>
  - terse bullet per meaningful change (what + why), only if the change is non-trivial
type ∈ feat|fix|refactor|test|docs|chore|perf|build. Pick scope from the dominant path.
Describe what the diff ACTUALLY changes — do not speculate beyond it. Keep identifiers/paths
exact. If the diff is trivial, a one-line subject with no body is correct.
