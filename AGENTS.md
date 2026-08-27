# Agent instructions

## Agent skills

### Issue tracker

Work is tracked in GitHub Issues for `JohanSardar/hermes-bot-fleet`. See `docs/agents/issue-tracker.md`.

### Domain docs

This repository uses a single-context domain glossary. See `docs/agents/domain.md` and `CONTEXT.md`.

## Project rules

- Never commit credentials, tokens, browser data, SSH private keys, or exported cookies.
- Every claimed capability must be backed by a real acceptance test or explicitly marked unsupported.
- Public exposure of browser control, VNC, Chrome DevTools, SSH, MCP, or Hermes control endpoints is prohibited; use private networking and authentication.
- Preserve the distinction between Hermes profile separation and operating-system/container security isolation.
