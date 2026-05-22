# Security Policy

## 🔒 Reporting a Vulnerability

Security is our top priority. We take all security vulnerabilities seriously.

### How to Report

**Please DO NOT report security vulnerabilities through public GitHub issues.**

Instead, please report them via email to:

**Please use GitHub Security Advisories to report vulnerabilities:**

https://github.com/agentguard-ai/tealtiger-python-prod/security/advisories/new

**Note**: If you get a 404 error, Security Advisories may not be enabled yet. In that case, please:
1. Open a GitHub issue with the title prefix `[SECURITY]` (do NOT include sensitive details)
2. We will contact you privately to discuss the vulnerability details

### What to Include

Please include as much of the following information as possible:

- **Type of vulnerability** (e.g., authentication bypass, injection, etc.)
- **Full paths of source file(s)** related to the vulnerability
- **Location of the affected source code** (tag/branch/commit or direct URL)
- **Step-by-step instructions** to reproduce the issue
- **Proof-of-concept or exploit code** (if possible)
- **Impact of the vulnerability** and how an attacker might exploit it
- **Any potential mitigations** you've identified

### Response Timeline

- **Initial Response**: Within 24 hours
- **Status Update**: Within 72 hours
- **Fix Timeline**: Depends on severity
  - **Critical**: 1-7 days
  - **High**: 7-14 days
  - **Medium**: 14-30 days
  - **Low**: 30-90 days

### What to Expect

1. **Acknowledgment** - We'll confirm receipt of your report
2. **Investigation** - We'll investigate and validate the vulnerability
3. **Fix Development** - We'll develop and test a fix
4. **Disclosure** - We'll coordinate disclosure with you
5. **Credit** - We'll credit you in our security advisories (if desired)

## 🛡️ Security Measures

### Current Security Features

- **API Key Authentication** - Secure authentication for all API calls
- **HTTPS Only** - All communications encrypted in transit
- **Input Validation** - Comprehensive validation of all inputs
- **Type Safety** - Full type hints for better security
- **Dependency Scanning** - Regular security audits of dependencies

### Secure Development Practices

- **Code Review** - All code changes reviewed before merge
- **Automated Testing** - Comprehensive test suite including security tests
- **Dependency Updates** - Regular updates to address known vulnerabilities
- **Static Analysis** - Automated security scanning in CI/CD
- **Least Privilege** - Minimal permissions by default

## 🔐 Supported Versions

We provide security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | ✅ Yes             |
| < 0.1.0 | ❌ No              |

## 🚨 Known Security Considerations

### API Key Management

**Risk**: Exposed API keys can lead to unauthorized access

**Mitigation**:
- Never commit API keys to version control
- Use environment variables for API keys
- Rotate API keys regularly
- Use different keys for different environments

```python
# ✅ Good - Use environment variables
import os
from tealtiger import TealOpenAI

client = TealOpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

# ❌ Bad - Hardcoded API key
client = TealOpenAI(
    api_key="sk-1234567890abcdef"
)
```

### Network Security

**Risk**: Man-in-the-middle attacks on unencrypted connections

**Mitigation**:
- Always use HTTPS for SSA connections
- Validate SSL certificates
- Use certificate pinning for high-security environments

```python
# ✅ Good - HTTPS (OpenAI/Anthropic APIs use HTTPS by default)
from tealtiger import TealOpenAI

client = TealOpenAI(
    api_key=api_key
)

# Note: TealTiger uses OpenAI/Anthropic APIs directly
# All connections are HTTPS by default
```

### Input Validation

**Risk**: Injection attacks through unvalidated inputs

**Mitigation**:
- SDK validates all inputs before sending to SSA
- Use type hints for compile-time validation
- Sanitize user inputs before passing to tools

```python
# ✅ Good - Validated input
from tealtiger import TealOpenAI

def sanitize_input(text: str) -> str:
    # Remove potentially dangerous content
    return text.strip()[:1000]  # Limit length

response = await client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": sanitize_input(user_input)}],
    max_tokens=min(user_max_tokens, 4000)
)
```

### Dependency Security

**Risk**: Vulnerabilities in third-party dependencies

**Mitigation**:
- Regular dependency audits (`safety check`)
- Automated dependency updates (Dependabot)
- Minimal dependency footprint
- Pinned dependency versions

## 📋 Security Checklist for Users

### Development

- [ ] Store API keys in environment variables
- [ ] Use HTTPS for all SSA connections
- [ ] Validate and sanitize all user inputs
- [ ] Keep SDK updated to latest version
- [ ] Review security advisories regularly
- [ ] Enable debug logging only in development
- [ ] Use type hints for better safety

### Production

- [ ] Rotate API keys regularly
- [ ] Monitor for suspicious activity
- [ ] Set up security alerts
- [ ] Implement backup and recovery
- [ ] Use separate keys per environment
- [ ] Enable all security features
- [ ] Regular security audits
- [ ] Incident response plan

## 🚀 Security Roadmap

### Planned Security Features

- **v0.2.0**
  - Built-in guardrails for common threats
  - PII detection and redaction
  - Content moderation
  - Prompt injection detection

- **v0.3.0**
  - Advanced threat detection
  - Behavioral analysis
  - Anomaly detection
  - Threat intelligence integration

- **v1.0.0**
  - Security certification (SOC 2)
  - Compliance frameworks (HIPAA, GDPR)
  - Advanced encryption
  - Zero-trust architecture

## 📞 Contact

- **Security Issues**: Use [GitHub Security Advisories](https://github.com/agentguard-ai/tealtiger-python-prod/security/advisories/new)
- **GitHub**: [agentguard-ai/tealtiger-python-prod](https://github.com/agentguard-ai/tealtiger-python-prod)

## 📄 Disclosure Policy

### Coordinated Disclosure

We follow coordinated disclosure:

1. **Report** - Researcher reports vulnerability privately
2. **Acknowledge** - We acknowledge within 24 hours
3. **Fix** - We develop and test a fix
4. **Release** - We release the fix
5. **Disclose** - We publicly disclose (coordinated with researcher)

### Public Disclosure Timeline

- **Critical**: 7 days after fix release
- **High**: 14 days after fix release
- **Medium**: 30 days after fix release
- **Low**: 90 days after fix release

### Credit Policy

We credit security researchers in:
- Security advisories
- Release notes
- Security Hall of Fame
- Social media (with permission)

---

**Thank you for helping keep TealTiger Python SDK secure!** 🔒
