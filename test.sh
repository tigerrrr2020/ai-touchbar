#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
APP_PATH="${1:-$ROOT/build/AI Touch Bar.app}"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$ROOT/helper/vendor${PYTHONPATH:+:$PYTHONPATH}"
python3 "$ROOT/helper/test_bridge.py"
python3 "$ROOT/helper/test_status_bridge.py"
python3 -m unittest discover -s "$ROOT/helper/vendor/tests" -p 'test_*.py' -v
python3 "$ROOT/helper/agent_status.py" --self-test
python3 "$ROOT/helper/quota_touchbar.py" --self-test
"$APP_PATH/Contents/MacOS/TouchBarNativeLive" --self-test
