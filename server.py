import json
import urllib.request
import urllib.parse
from pathlib import Path

from mcp.server.fastmcp import FastMCP

CREDS_FILE = Path(__file__).parent / "credentials.json"

mcp = FastMCP("slacc")


def _load_creds() -> dict:
    if not CREDS_FILE.exists():
        from main import main as extract
        extract()
    if not CREDS_FILE.exists():
        raise RuntimeError("Token extraction failed. Run manually: uv run main.py")
    return json.loads(CREDS_FILE.read_text())


def _call_slack(method: str, params: dict | None = None) -> dict:
    creds = _load_creds()
    data = urllib.parse.urlencode(params or {}).encode()
    req = urllib.request.Request(
        f"https://slack.com/api/{method}",
        data=data,
        headers={
            "Authorization": f"Bearer {creds['token']}",
            "Cookie": f"d={creds['cookie']}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read())


@mcp.tool()
def slack_api(method: str, params: str = "{}") -> str:
    """Call any Slack API method.

    method: The Slack API method (e.g. "search.messages", "conversations.history", "chat.postMessage")
    params: JSON string of parameters to pass (e.g. '{"channel": "C04GP9KGU3T", "limit": 10}')

    See https://api.slack.com/methods for all available methods.

    Some enterprise workspaces restrict "conversations.list" and "users.list".
    Use "search.messages" to find content or "conversations.history" with a known channel ID instead.
    """
    try:
        parsed_params = json.loads(params)
    except json.JSONDecodeError as e:
        return json.dumps({"ok": False, "error": f"Invalid params JSON: {e}"})
    result = _call_slack(method, parsed_params)
    return json.dumps(result, indent=2)


if __name__ == "__main__":
    mcp.run()
