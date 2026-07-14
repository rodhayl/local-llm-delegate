<!-- SPDX-License-Identifier: MIT -->

# Security Policy

## Reporting vulnerabilities

If you discover a security vulnerability, please report it responsibly. Do not open a public GitHub issue for security vulnerabilities.

## Security features

- **Privacy guard** (strong tier, ON by default): refuses sensitive files, redacts secrets from outbound text
- **File deny-list**: blocks `.env*`, `*secret*`, keys/certs, `.ssh`, and more
- **Symlink denial**: prevents bypassing the deny-list via symbolic links
- **Confidential tools**: redacts all tool output before upload when using `--confidential-tools`
- **Capability guard**: `--require-model` prevents silent quality degradation

## Known limitations

- `run_python` executes arbitrary Python code — no sandbox, no container
- Privacy redaction covers common formats but cannot catch every possible secret
- Local tier processes data on your machine — ensure your LM Studio instance is secure

## Scope

This project delegates LLM inference to:
- **Local**: LM Studio (runs on your machine, data never leaves)
- **Cloud**: Opencode Zen API (data is redacted before upload in privacy mode)
