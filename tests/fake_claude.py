"""A stand-in for Claude Code in the tests. It speaks just enough stream-json to drive API Credit Code.

What it does depends on the message it gets:
  "hello"  answers "Hello there", streamed in two pieces
  "ask"    asks to run a command (Manual / Accept edits) and says what the user answered
  "slow"   keeps working until it is stopped
  "fail"   exits with an error
Anything else gets "Hello there" too. It logs each command line to $FAKE_CLAUDE_LOG and keeps a transcript with a
cost-state record under $CLAUDE_CONFIG_DIR/projects, like Claude Code does, so a follow-up finds it and resumes.
"""
import json
import os
import sys
import time
import uuid
from pathlib import Path


def out(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def arg(name):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else None


def read():
    line = sys.stdin.readline()
    return json.loads(line) if line.strip() else None


def stream(text):
    out({"type": "stream_event", "event": {"type": "message_start"}, "parent_tool_use_id": None})
    half = len(text) // 2
    for piece in (text[:half], text[half:]):
        out({"type": "stream_event", "parent_tool_use_id": None,
             "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": piece}}})


def main():
    if "--version" in sys.argv:
        print(os.environ.get("FAKE_CLAUDE_VERSION", "2.1.400") + " (Claude Code)")
        return
    if os.environ.get("FAKE_CLAUDE_LOG"):
        with open(os.environ["FAKE_CLAUDE_LOG"], "a", encoding="utf-8") as f:
            f.write(json.dumps({"args": sys.argv[1:], "cwd": os.getcwd(),
                                "key": bool(os.environ.get("ANTHROPIC_API_KEY")),
                                "scrub": os.environ.get("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB")}) + "\n")
    sid = arg("--resume") or arg("--session-id")
    mode = arg("--permission-mode") or "default"
    host = arg("--permission-prompt-tool") == "stdio"
    transcript = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / "fake" / f"{sid}.jsonl"
    total = 0.0
    if transcript.exists():
        for line in transcript.read_text(encoding="utf-8").splitlines():
            if '"cost-state"' in line:
                total = json.loads(line)["totalCostUSD"]

    msg = None
    while msg is None:  # Manual and Accept edits start with the app's initialize request
        ev = read()
        if ev is None:
            return
        if ev.get("type") == "control_request":
            out({"type": "control_response",
                 "response": {"subtype": "success", "request_id": ev["request_id"], "response": {}}})
        elif ev.get("type") == "user":
            msg = ev
    content = msg["message"]["content"]
    text = " ".join(b.get("text", "") for b in content if b.get("type") == "text")
    pictures = sum(1 for b in content if b.get("type") == "image")

    out({"type": "system", "subtype": "init", "model": arg("--model"), "permissionMode": mode, "session_id": sid,
         "apiKeySource": "ANTHROPIC_API_KEY" if os.environ.get("ANTHROPIC_API_KEY") else "none"})
    if host:
        out({"type": "system", "subtype": "session_state_changed", "state": "running"})
    if "fail" in text:
        sys.stderr.write("boom: something went wrong\n")
        sys.exit(1)

    if "slow" in text:
        stream("Working on it")
        if not host:
            while True:  # until the app ends this process
                time.sleep(0.2)
        while True:
            ev = read()
            if ev is None:
                return
            if ev.get("type") == "control_request" and ev["request"].get("subtype") == "interrupt":
                out({"type": "control_response",
                     "response": {"subtype": "success", "request_id": ev["request_id"], "response": {}}})
                out({"type": "result", "subtype": "error_during_execution", "is_error": True, "result": "",
                     "total_cost_usd": total + 0.005, "duration_ms": 900, "permission_denials": []})
                out({"type": "system", "subtype": "session_state_changed", "state": "idle"})
                while read() is not None:
                    pass
                return

    reply = "Hello there"
    if "ask" in text:
        reply = "I can't ask in this mode."
        if host:
            rid = "perm_" + uuid.uuid4().hex[:8]
            out({"type": "control_request", "request_id": rid, "request": {
                "subtype": "can_use_tool", "tool_name": "Bash", "tool_use_id": "toolu_1",
                "input": {"command": "echo hi", "description": "Say hi"},
                "decision_reason": "Bash commands need approval"}})
            while True:
                ev = read()
                if ev is None:
                    return
                if ev.get("type") == "control_response" and ev["response"].get("request_id") == rid:
                    answer = ev["response"]["response"]
                    break
            if answer.get("behavior") == "allow" and answer.get("updatedInput", {}).get("command") == "echo hi":
                out({"type": "assistant", "parent_tool_use_id": None,
                     "message": {"content": [{"type": "tool_use", "name": "Bash", "input": answer["updatedInput"]}]}})
                reply = "You allowed it: hi"
            else:
                reply = "You said no."
    if pictures:
        reply += f" ({pictures} picture{'s' if pictures > 1 else ''})"

    stream(reply)
    out({"type": "assistant", "parent_tool_use_id": None, "message": {"content": [{"type": "text", "text": reply}]}})
    total += 0.01
    transcript.parent.mkdir(parents=True, exist_ok=True)
    with open(transcript, "a", encoding="utf-8") as f:
        f.write(json.dumps({"type": "cost-state", "totalCostUSD": total}) + "\n")
    out({"type": "result", "subtype": "success", "is_error": False, "result": reply, "total_cost_usd": total,
         "duration_ms": 1200, "permission_denials": [], "modelUsage": {}})
    if host:
        out({"type": "system", "subtype": "session_state_changed", "state": "idle"})
        while read() is not None:  # the app closes the input to end the session
            pass


if __name__ == "__main__":
    main()
