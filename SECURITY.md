# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability, please report it privately through
[GitHub Private Vulnerability Reporting](https://github.com/HuziM/zurixai/security/advisories/new)
(Security tab, then "Report a vulnerability").

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will respond within 48 hours and work with you to understand and address the issue.

## What We Store

ZurixAI's hosted service stores:
- Check results and verdicts (pass/fail/error)
- Signed audit log entries
- Repository and PR metadata (owner, repo name, PR number, commit SHA)

We do **not** store:
- Source code
- API keys or secrets (beyond what is needed for GitHub App operation)
- File contents from scanned repositories

## GitHub App Permissions

The ZurixAI GitHub App requests these permissions:
- **Contents**: Read (to clone repos for analysis)
- **Checks**: Write (to post check results on PRs)
- **Pull requests**: Write (to post review comments and dismiss stale reviews)
- **Metadata**: Read (repository info)

## Data Retention

- Check results: retained for the duration of the service
- Audit logs: retained while the account is active
- On uninstall: new data stops. Contact us to request deletion of existing data.

## Signed Audit Reports

ZurixAI signs audit reports using Ed25519 keys. You can verify any report:

```bash
zurix verify <audit.json> --key <public_key>
```

The signed payload includes what was checked, not just that a run happened.

## Verified

This security policy was last reviewed on September 30, 2026.
