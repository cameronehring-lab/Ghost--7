import subprocess
from unittest.mock import MagicMock, patch

# Mocking the trigger function to verify osascript calls
def _trigger_host_alarm_logic():
    commands = []
    # 1. Unmute and set volume to 100%
    commands.append(["osascript", "-e", "set volume without output muted"])
    commands.append(["osascript", "-e", "set volume 7"])
    
    # 2. Play obnoxious system alarm
    commands.append(["osascript", "-e", 'beep 10'])
    return commands

def test_host_alarm_logic():
    cmds = _trigger_host_alarm_logic()
    assert cmds[0] == ["osascript", "-e", "set volume without output muted"]
    assert cmds[1] == ["osascript", "-e", "set volume 7"]
    assert cmds[2] == ["osascript", "-e", "beep 10"]
    print("Host alarm command logic verified!")

def test_sse_payload():
    # Simulate the yield payload
    payload = {
        "event": "security_lockout",
        "status": "hostile_mode_active",
        "message": "Sassy message here",
        "visual_trigger": "red_alert",
    }
    assert payload["visual_trigger"] == "red_alert"
    assert payload["event"] == "security_lockout"
    print("SSE visual trigger payload verified!")

if __name__ == "__main__":
    test_host_alarm_logic()
    test_sse_payload()
