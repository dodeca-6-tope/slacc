#!/usr/bin/env bash
set -euo pipefail

REPO="https://github.com/dodeca-6-tope/slacc.git"
INSTALL_DIR="${HOME}/.slacc"

# Check macOS
if [[ "$(uname)" != "Darwin" ]]; then
  echo "Error: slacc only supports macOS" >&2
  exit 1
fi

# Check/install uv
if ! command -v uv &>/dev/null; then
  echo "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="${HOME}/.local/bin:${PATH}"
fi

# Check claude CLI
if ! command -v claude &>/dev/null; then
  echo "Error: claude CLI not found. Install Claude Code first." >&2
  exit 1
fi

# Clone or update
if [[ -d "${INSTALL_DIR}" ]]; then
  echo "Updating slacc..."
  git -C "${INSTALL_DIR}" pull --ff-only
else
  echo "Installing slacc..."
  git clone "${REPO}" "${INSTALL_DIR}"
fi

# Install deps
uv sync --project "${INSTALL_DIR}" --quiet

# Extract credentials
if [[ ! -f "${INSTALL_DIR}/credentials.json" ]]; then
  echo "Extracting Slack credentials..."
  uv run --project "${INSTALL_DIR}" python "${INSTALL_DIR}/main.py"
fi

# Register MCP server globally (remove first if exists)
claude mcp remove slacc -s user 2>/dev/null || true
claude mcp add --scope user slacc -- uv run --project "${INSTALL_DIR}" python "${INSTALL_DIR}/server.py"

echo ""
echo "slacc installed! Restart Claude Code to start using it."
