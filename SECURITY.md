# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in AutoSwarm Office, please report it responsibly:

1. **Do not** open a public GitHub issue
2. Email security@autoswarm.dev with details
3. Include steps to reproduce if possible
4. We will acknowledge receipt within 48 hours

## Sensitive Data

This project handles sensitive data including:
- LLM provider API keys (OpenAI, Anthropic, etc.)
- Agent orchestration data and execution logs
- Real-time collaboration session data (Colyseus)
- User authentication tokens and session state
- Database credentials and connection strings

### Rules

- API keys and LLM credentials must **never** be committed to version control
- All secrets must be provided via environment variables or K8s secrets
- Agent execution logs must not contain user PII or credentials
- Colyseus room state must not persist sensitive data beyond session lifetime
- Logs must never contain passwords, tokens, or API keys

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.2.x   | Yes       |
