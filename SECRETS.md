# Secrets Management Guide

This document outlines best practices for managing secrets in FireForm.

## Environment Variables

All secrets are managed via environment variables. **Never commit secrets to Git.**

### Required Variables

See `.env.example` for the complete list of required environment variables.

### Local Development

1. Copy the example file:
```bash
   cp .env.example .env
```

2. Fill in actual values:
```bash
   # Generate a secure SECRET_KEY
   python -c "import secrets; print(secrets.token_urlsafe(32))"
```

3. **Never commit `.env`** — it's in `.gitignore`

---

## Secrets Rotation

### Database Credentials

**When to rotate:** Every 90 days or immediately after suspected compromise

**Steps:**
1. Create new database user with same permissions
2. Update `DATABASE_URL` in production environment
3. Restart application (zero downtime with health checks)
4. Verify new credentials work
5. Revoke old database user

**Example:**
```sql
-- Create new user
CREATE USER fireform_user_new WITH PASSWORD 'new_secure_password';
GRANT ALL PRIVILEGES ON DATABASE fireform TO fireform_user_new;

-- After rotation succeeds
DROP USER fireform_user_old;
```

---

### LLM API Keys

**When to rotate:** Every 90 days or when API key is exposed

**Steps:**
1. Generate new API key from LLM provider dashboard
2. Update `LLM_API_KEY` in production environment
3. Restart application
4. Verify extraction still works
5. Revoke old API key

---

### Application Secret Key

**When to rotate:** Every 180 days or after security incident

**Impact:** Rotating `SECRET_KEY` invalidates all active sessions

**Steps:**
1. Generate new secret key:
```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
```
2. Update `SECRET_KEY` in production
3. Restart application
4. Notify users they'll need to re-authenticate

---

## Production Deployment

### Environment-Specific Secrets

Use separate secrets for each environment:

- **Development:** `.env` (local only, never committed)
- **Staging:** Staging secrets manager (AWS Secrets Manager, Vault, etc.)
- **Production:** Production secrets manager with audit logging

### CAL FIRE Deployment Checklist

- [ ] Database credentials rotated within last 90 days
- [ ] LLM API key rotated within last 90 days
- [ ] `SECRET_KEY` is cryptographically random (min 32 chars)
- [ ] All secrets stored in approved secrets manager
- [ ] Secrets rotation schedule documented
- [ ] Audit logging enabled for secrets access
- [ ] No secrets in application logs (verified via `api/utils/secrets.py`)

---

## Secrets in Logs

The application automatically redacts secrets from logs using `api/utils/secrets.py`.

**Redacted patterns:**
- API keys
- Passwords
- Tokens
- Database credentials
- Bearer tokens

**Example:**
```python
from api.utils.secrets import sanitize_log_message

message = "Failed to connect with api_key=sk_test_12345"
sanitized, _ = sanitize_log_message(message)
# Output: "Failed to connect with api_key=***REDACTED***"
```

---

## Git Protection

### Pre-commit Hook (Recommended)

Create `.git/hooks/pre-commit`:

```bash
#!/bin/bash
# Prevent committing .env files

if git diff --cached --name-only | grep -q "^.env$"; then
    echo "ERROR: Attempting to commit .env file"
    echo "Secrets should never be committed to Git"
    exit 1
fi
```

Make it executable:
```bash
chmod +x .git/hooks/pre-commit
```

---

## Compliance

### Federal Standards

- **NIST SP 800-53 (AC-2):** Access control for credentials
- **FEMA IS-700:** Incident management security requirements
- **OWASP Top 10:** Sensitive Data Exposure prevention

### Audit Trail

For CAL FIRE production:
- Log all secrets rotation events
- Maintain 1-year audit history
- Alert on rotation failures
- Monthly compliance review