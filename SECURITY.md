# Security Policy

## Reporting a Vulnerability
We take the security and data integrity of emergency reports seriously. **Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report them using [GitHub Private Vulnerability Reporting](https://github.com/fireform-core/FireForm/security/advisories/new).

We will acknowledge receipt of your vulnerability report within 48 hours and strive to send you regular updates about our progress. If the issue is confirmed, we will release a patch as quickly as possible.

## Scope
Because FireForm generates critical emergency documentation, we are particularly interested in vulnerabilities regarding:
- Prompt injections that bypass formatting constraints or manipulate PDF fields.
- Unauthorized data leakage across different templates.
- Any bug allowing bypass of our data schema validations.

General LLM hallucinations that do not involve malicious input manipulation are considered functional bugs, not security vulnerabilities.

## Supported Versions
We currently support the latest version on the main branch.