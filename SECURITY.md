# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| `0.1.x` | :white_check_mark: |

## Reporting a Vulnerability

Security and credential isolation are top priorities for this project. Because this server interacts with YouTube accounts via OAuth 2.0, sensitive credentials (`client_secret.json`) and session tokens (`token.json`) must remain strictly local on user machines.

If you discover a security vulnerability or accidental secret exposure:

1. **Do NOT open a public GitHub issue.**
2. Open a [Private Security Advisory](https://github.com/vunm-io/vunm-youtube-mcp/security/advisories/new) on GitHub or contact the maintainer directly via GitHub ([@vunm-io](https://github.com/vunm-io)).
3. Provide a clear description, proof of concept, and affected environment.

We will review, acknowledge, and resolve security reports promptly.
