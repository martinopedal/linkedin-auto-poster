# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability, please report it privately:
- Use GitHub's [private vulnerability reporting](../../security/advisories/new)

Do NOT open a public issue for security vulnerabilities.

## Security Measures

- All secrets managed via environment variables (never committed)
- SSRF protection on HTTP fetches (private IP blocking, DNS timeout)
- Content validation for PII, customer names, sensitive data
- SHA-pinned GitHub Actions dependencies
- Prompt injection protection with data delimiters
