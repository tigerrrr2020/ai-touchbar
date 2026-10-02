"""User configuration for optional usage refresh behavior."""
import json
import os


CONFIG_PATH = os.path.expanduser(
    "~/.config/ai-agent-usage-widget/config.json"
)
DEFAULT_CODEX_REFRESH_INTERVAL = 1800
MIN_CODEX_REFRESH_INTERVAL = 300


def load_config(path=None):
    path = path or os.environ.get("AI_AGENT_USAGE_CONFIG") or CONFIG_PATH
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}

    enabled = data.get("codex_active_refresh") is True
    try:
        interval = int(data.get(
            "codex_refresh_interval_seconds",
            DEFAULT_CODEX_REFRESH_INTERVAL,
        ))
    except (TypeError, ValueError):
        interval = DEFAULT_CODEX_REFRESH_INTERVAL
    interval = max(MIN_CODEX_REFRESH_INTERVAL, interval)
    return {
        "codex_active_refresh": enabled,
        "codex_refresh_interval_seconds": interval,
    }
