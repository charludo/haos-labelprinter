"""Replays every message the frontend's Api wrapper can send against the real backend (HA venv).

The messages come from frontend/dev/tests/capture_calls.mjs, so a UI/backend schema mismatch (wrong
field name, wrong type, unknown command) fails here. Bluetooth and the printer are faked; nothing touches
a real radio or the system D-Bus."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from test_bluetooth_ha import bt, bt_entry, call, tr, ws  # noqa: F401  (fixtures)
from test_ha import _enable  # noqa: F401

pytest_plugins = "pytest_homeassistant_custom_component"

FRONTEND = Path(__file__).resolve().parent.parent / "custom_components" / "brother_ptouch" / "frontend"
# A schema or routing problem, as opposed to a legitimate business answer (not_found, cannot_connect...).
SCHEMA_ERRORS = {"invalid_format", "unknown_command"}


def captured():
    if not shutil.which("node"):
        pytest.skip("node is not installed")
    out = subprocess.run(["node", str(FRONTEND / "dev" / "tests" / "capture_calls.mjs")],
                         capture_output=True, text=True, timeout=60, check=True)
    return json.loads(out.stdout)


async def test_every_frontend_message_is_accepted_by_the_backend(hass, ws, bt, tr):
    entry = await bt_entry(hass)
    msgs = captured()
    assert len(msgs) >= 25
    problems, seen = [], {}
    for item in msgs:
        msg = json.loads(json.dumps(item["msg"]).replace("ENTRY", entry.entry_id).replace("DESIGN", "nope")
                         .replace("TEMPLATE", "pantry-jar"))
        await ws.send_json_auto_id(msg)
        res = await ws.receive_json()
        code = None if res.get("success") else (res.get("error") or {}).get("code")
        seen[item["name"]] = "ok" if res.get("success") else code
        if code in SCHEMA_ERRORS:
            problems.append(f"{item['name']}: {msg['type']} -> {code}: {(res.get('error') or {}).get('message')}")
    assert not problems, "\n".join(problems) + f"\nall results: {seen}"
    covered = {json.loads(json.dumps(i["msg"]))["type"] for i in msgs}
    assert "brother_ptouch/printers/add" in covered and "brother_ptouch/bluetooth/pair" in covered
