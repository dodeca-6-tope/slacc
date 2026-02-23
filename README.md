# slacc

Slack access for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Extracts credentials from the macOS Slack desktop app and exposes a Slack API tool via MCP.

## Install

```bash
bash <(curl -sSL https://raw.githubusercontent.com/dodeca-6-tope/slacc/main/install.sh)
```

Restart Claude Code after installing. Credentials are extracted automatically on first use.

## Disclaimers

- **macOS only** — uses Slack's Electron debug port and LevelDB storage, both macOS-specific paths.
- **Not affiliated with Slack** — this is an unofficial tool. Use at your own risk.
- **Credentials are stored in plaintext** — `credentials.json` contains your session token and cookie. It is gitignored but treat it like a password.
- **Token extraction requires a brief Slack restart** — the app is relaunched with a debug port to extract the session cookie, then restored to its previous state.
- **May violate Slack's ToS** — extracting session tokens from the desktop app is not an officially supported flow. Your workspace admin could potentially flag this.
