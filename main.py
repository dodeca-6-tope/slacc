import asyncio
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websockets

DEBUG_PORT = 9222
DEBUG_URL = f"http://localhost:{DEBUG_PORT}/json"
SLACK_LEVELDB = Path.home() / "Library/Application Support/Slack/Local Storage/leveldb"
OUTPUT_FILE = Path(__file__).parent / "credentials.json"


# ---------------------------------------------------------------------------
# Token extraction (headless — reads LevelDB files on disk)
# ---------------------------------------------------------------------------

def extract_token_from_disk() -> str | None:
    """Read the xoxc- token directly from Slack's LevelDB files (no app restart)."""
    if not SLACK_LEVELDB.exists():
        return None
    tokens = set()
    for pattern in ["*.ldb", "*.log"]:
        for filepath in SLACK_LEVELDB.glob(pattern):
            try:
                data = filepath.read_bytes()
                tokens.update(re.findall(rb"xoxc-[a-zA-Z0-9_-]{50,}", data))
            except OSError:
                continue
    if not tokens:
        return None
    # Return the longest (most recent) token
    return max(tokens, key=len).decode()


# ---------------------------------------------------------------------------
# Cookie extraction (needs debug port — cookie is HttpOnly + encrypted on disk)
# ---------------------------------------------------------------------------

def is_debug_port_open() -> bool:
    """Check if the debug port is already available."""
    try:
        urllib.request.urlopen(DEBUG_URL, timeout=1)
        return True
    except Exception:
        return False


def is_slack_running() -> bool:
    """Check if Slack is currently running."""
    result = subprocess.run(["pgrep", "-x", "Slack"], capture_output=True)
    return result.returncode == 0


def ensure_debug_port() -> tuple[bool, bool]:
    """Make sure Slack is running with the debug port open. Restarts only if needed.

    Returns (success, was_already_running) so caller knows whether to restore Slack.
    """
    was_running = is_slack_running()

    if is_debug_port_open():
        print("Debug port already open.")
        return True, was_running

    print("Starting Slack with debug port...")
    subprocess.run(["osascript", "-e", 'quit app "Slack"'], capture_output=True)
    time.sleep(3)
    subprocess.Popen(
        ["open", "-a", "Slack", "--args", f"--remote-debugging-port={DEBUG_PORT}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        if is_debug_port_open():
            print("Debug port ready.")
            time.sleep(5)
            return True, was_running
        time.sleep(1)

    print("Timed out waiting for Slack debug port.", file=sys.stderr)
    return False, was_running


def restore_slack(was_running: bool):
    """Restart Slack normally if it was running before, otherwise quit it."""
    if was_running:
        print("Restarting Slack normally...")
        subprocess.run(["osascript", "-e", 'quit app "Slack"'], capture_output=True)
        time.sleep(2)
        subprocess.Popen(
            ["open", "-a", "Slack"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        print("Closing Slack (was not running before)...")
        subprocess.run(["osascript", "-e", 'quit app "Slack"'], capture_output=True)


def get_ws_url() -> str | None:
    """Get the WebSocket debugger URL for the first available page."""
    resp = urllib.request.urlopen(DEBUG_URL, timeout=5)
    targets = json.loads(resp.read())
    for target in targets:
        if ws_url := target.get("webSocketDebuggerUrl"):
            return ws_url
    return None


async def send_cdp(ws, method: str, params: dict | None = None, msg_id: int = 1) -> dict:
    """Send a CDP command and return the result."""
    msg = json.dumps({"id": msg_id, "method": method, "params": params or {}})
    await ws.send(msg)
    while True:
        resp = json.loads(await ws.recv())
        if resp.get("id") == msg_id:
            return resp.get("result", {})


async def extract_cookie_via_cdp() -> str | None:
    """Extract the 'd' session cookie via CDP (HttpOnly, can't read from disk)."""
    ws_url = get_ws_url()
    if not ws_url:
        return None
    async with websockets.connect(ws_url) as ws:
        result = await send_cdp(
            ws, "Network.getCookies",
            {"urls": ["https://slack.com", "https://app.slack.com"]},
        )
    for cookie in result.get("cookies", []):
        if cookie.get("name") == "d":
            return cookie["value"]
    return None


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify_credentials(creds: dict) -> dict | None:
    """Verify the extracted credentials against Slack's auth.test API."""
    req = urllib.request.Request(
        "https://slack.com/api/auth.test",
        headers={
            "Authorization": f"Bearer {creds['token']}",
            "Cookie": f"d={creds['cookie']}",
        },
    )
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # 1. Token — read from disk (no restart)
    print("Reading token from disk...")
    token = extract_token_from_disk()
    if not token:
        print("Could not find token in LevelDB files.", file=sys.stderr)
        sys.exit(1)
    print(f"Token: {token[:30]}...")

    # 2. Cookie — needs debug port
    success, was_running = ensure_debug_port()
    if not success:
        sys.exit(1)

    print("Extracting session cookie...")
    cookie = asyncio.run(extract_cookie_via_cdp())
    if not cookie:
        print("Could not find 'd' cookie.", file=sys.stderr)
        sys.exit(1)
    print(f"Cookie: found ({len(cookie)} chars)")

    # 3. Restore Slack to its previous state
    restore_slack(was_running)

    # 4. Verify
    creds = {"token": token, "cookie": cookie}
    print("Verifying credentials...")
    auth = verify_credentials(creds)
    if auth and auth.get("ok"):
        print(f"Authenticated as: {auth.get('user')} @ {auth.get('team')}")
    else:
        print(f"Verification failed: {auth}", file=sys.stderr)
        sys.exit(1)

    # 5. Save
    OUTPUT_FILE.write_text(json.dumps(creds, indent=2))
    print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
