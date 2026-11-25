"""API Credit Code: a local chat window that runs your own Claude Code (`claude -p`) on your Anthropic API key.

Start it with the app icon, or `api-credit-code` in a terminal. It opens http://localhost:8790/ in your browser. Each
message runs `claude -p` in the chat's folder with your API key, so it has the same CLAUDE.md, memory, skills and
MCP servers as `claude` in that folder, and the monthly API credits pay for it. A chat's follow-ups resume that chat
by its session ID, never --continue (which grabs whatever conversation in the folder is most recent).

Chats live in this app's folder in your user profile (chats/<id>.json, a chat's pictures in chats/<id>/), and an
answer keeps running when the page that asked for it closes.
"""
import argparse
import base64
import copy
import io
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import APP_ID, APP_NAME, __version__
from . import claude as cc
from . import folders, keys, launcher, paths

PORT = 8790  # fixed, so the browser keeps your settings (they are kept per address)
MODELS = ["claude-fable-5-2", "claude-fable-5-1", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]
DEFAULT_MODEL = "claude-opus-5-5"
EFFORTS = ["low", "medium", "high", "xhigh", "max"]
DEFAULT_EFFORT = "high"
MAX_CHARS = 100_000
MAX_IMAGES = 8               # pictures per message
MAX_IMAGE_BYTES = 5_000_000  # the API's limit per image; the page shrinks pictures to 1568 px first, so they stay far smaller
MAX_BODY = 60_000_000        # a message with its pictures, base64-encoded
IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg"}  # all the page sends: it re-encodes every picture through a canvas
ASK_TIMEOUT = 30 * 60        # a "may I?" nobody answers is declined after this long
IDLE_QUIT = 120              # with --app: quit once no page has been open for this long (and nothing is running)
CHAT_URL = re.compile(r"^/api/chats/([0-9a-f-]{36})(?:/(events|send|stop|answer|delete|rename))?$")
FILE_URL = re.compile(r"^/files/([0-9a-f-]{36})/(img-\d{1,4}\.(?:png|jpg))$")  # a chat's pictures, by exact name
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
TYPES = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".png": "image/png",
         ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".ico": "image/x-icon",
         ".webmanifest": "application/manifest+json"}
# img-src has no https: so an answer can't make the page load a remote image (a way to leak text out).
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
       "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")

STATIC = paths.static_dir()
# Everything under static/ except index.html, by exact path, so nothing outside it can be requested.
STATIC_FILES = {p.relative_to(STATIC).as_posix(): TYPES[p.suffix] for p in STATIC.rglob("*") if p.suffix in TYPES}
TOKEN = secrets.token_urlsafe(32)  # the page gets it; other websites can't, so they can't drive this app
HOME = paths.data_dir()
CHATS_DIR = HOME / "chats"
STATE = {"claude": None, "claude_version": None, "claude_checked": 0.0, "port": PORT, "hosts": {"127.0.0.1", "localhost", "[::1]"},
         "version": 0, "seen": time.time(), "app": False}
CHATS = {}  # chat id -> chat. LOCK guards it and the contents of every chat.
RUNS = {}   # chat id -> Run, while an answer is being produced
LOCK = threading.RLock()
WAKE = threading.Condition(LOCK)  # notified whenever a run produces an event or ends, or the chats change
QUIT = threading.Event()


def log(msg):
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}", flush=True)


def now_ms():
    return int(time.time() * 1000)


def projects_dir():
    return paths.claude_dir() / "projects"


def has_transcript(sid):
    return any(projects_dir().glob(f"*/{sid}.jsonl"))


def session_cost(sid):
    """The chat's running cost so far: the last cost-state record Claude Code wrote into its transcript.

    A resumed run reports that running total plus its own spend, so this is subtracted to get one answer's cost.
    """
    total = 0.0
    for path in projects_dir().glob(f"*/{sid}.jsonl"):
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"cost-state"' in line:
                    try:
                        total = float(json.loads(line).get("totalCostUSD") or total)
                    except (ValueError, TypeError, AttributeError):
                        pass
    return total


def claude_status():
    """What the page needs to know about Claude Code: found, version, and whether Manual/Accept edits work.
    While it is missing or too old, look again (at most every few seconds): the user may have just installed or
    updated it, and shouldn't need to restart this app for that."""
    v = STATE["claude_version"]
    stale = not STATE["claude"] or (v is not None and v < cc.MIN_VERSION)  # an unreadable version isn't asked again
    if stale and time.time() - STATE["claude_checked"] > 10:
        find_claude()
        v = STATE["claude_version"]
    return {"found": bool(STATE["claude"]), "version": ".".join(map(str, v)) if v else None,
            "host_ok": bool(v and v >= cc.MIN_VERSION)}


def key_status():
    key, problem = keys.load(HOME)
    return {"set": bool(key), "masked": keys.mask(key), "problem": problem, "file": str(keys.key_file(HOME))}


# ---------------------------------------------------------------- one answer

def user_message(text, images):
    """The message as one stream-json line that carries the pictures themselves (before the words, as Anthropic
    advises), so Claude sees them directly. The files are named too, in case Claude wants to crop or zoom into one."""
    content = [{"type": "image", "source": {"type": "base64", "media_type": mtype,
                                             "data": base64.b64encode(path.read_bytes()).decode("ascii")}}
               for mtype, path in images]
    if images:
        note = f"[Attached image file{'s' if len(images) > 1 else ''}: {', '.join(str(p) for _, p in images)}]"
        text = f"{text}\n\n{note}" if text else note
    content.append({"type": "text", "text": text})
    return {"type": "user", "message": {"role": "user", "content": content}, "parent_tool_use_id": None}


def drain(stream, tail):
    for line in stream:
        tail.append(line.rstrip())
        del tail[:-20]


def short(text, n=160):
    text = " ".join(str(text or "").split())
    return text[:n] + ("…" if len(text) > n else "")


def describe(name, inp):
    """A short label for a tool call, e.g. the search query or the file being read."""
    if not isinstance(inp, dict):
        return ""
    key = {"WebSearch": "query", "WebFetch": "url", "Read": "file_path", "Write": "file_path", "Edit": "file_path",
           "MultiEdit": "file_path", "NotebookEdit": "notebook_path", "Grep": "pattern", "Glob": "pattern",
           "Skill": "skill", "Agent": "description", "Task": "description"}.get(name)
    return short(inp.get(key) if key else (inp.get("description") or inp.get("command") or ""))


ASK_TITLES = {"Bash": "Run a command", "PowerShell": "Run a command", "Edit": "Edit a file", "MultiEdit": "Edit a file",
              "Write": "Write a file", "NotebookEdit": "Edit a notebook", "WebFetch": "Read a web page",
              "WebSearch": "Search the web", "Read": "Read a file", "Glob": "List files", "Grep": "Search files"}


def ask_detail(tool, inp):
    """What exactly Claude wants to do, for the Allow / Deny card."""
    for k in ("command", "file_path", "notebook_path", "url", "query", "pattern"):
        if isinstance(inp.get(k), str) and inp[k].strip():
            v = inp[k].strip()
            if k == "pattern" and inp.get("path"):
                v += f"   in {inp['path']}"
            return v[:4000]
    try:
        return json.dumps(inp, ensure_ascii=False)[:2000]
    except (TypeError, ValueError):
        return ""


def translate(ev):
    """Turn Claude Code's stream-json events into the few the page needs."""
    kind = ev.get("type")
    if kind == "system" and ev.get("subtype") == "init":
        yield {"t": "init", "model": ev.get("model"), "mode": ev.get("permissionMode"),
               "billing_ok": ev.get("apiKeySource") == "ANTHROPIC_API_KEY"}
    elif kind == "stream_event" and ev.get("parent_tool_use_id") is None:
        e = ev.get("event") or {}
        delta = e.get("delta") or {}
        if e.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
            yield {"t": "text", "d": delta.get("text", "")}
        elif e.get("type") == "message_start":
            yield {"t": "turn"}
    elif kind == "assistant":
        for block in (ev.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                yield {"t": "tool", "name": block.get("name"), "detail": describe(block.get("name"), block.get("input")),
                       "sub": ev.get("parent_tool_use_id") is not None}
    elif kind == "result":
        usage = (ev.get("modelUsage") or {}).values()
        yield {"t": "result", "ok": not ev.get("is_error") and ev.get("subtype") == "success",
               "subtype": ev.get("subtype"), "text": ev.get("result") or "", "cost": ev.get("total_cost_usd") or 0.0,
               "cost_unknown": any(isinstance(u, dict) and u.get("costBasis") == "unknown" for u in usage),
               "seconds": round((ev.get("duration_ms") or 0) / 1000),
               "blocked": len(ev.get("permission_denials") or [])}


# ---------------------------------------------------------------- chats

def decode_images(raw):
    """The pictures sent with a message, [{type, data (base64), w, h}], checked: a ValueError means refuse the request."""
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_IMAGES:
        raise ValueError(f"You can send up to {MAX_IMAGES} pictures with one message.")
    out = []
    for r in raw:
        ext = IMAGE_TYPES.get(r.get("type")) if isinstance(r, dict) else None
        try:
            blob = base64.b64decode(str(r.get("data") or ""), validate=True) if ext else b""
        except ValueError:
            blob = b""
        magic = b"\x89PNG\r\n\x1a\n" if ext == ".png" else b"\xff\xd8\xff"
        if not blob or len(blob) > MAX_IMAGE_BYTES or not blob.startswith(magic):
            raise ValueError("Pictures must be PNG or JPEG, under 5 MB each.")
        im = {"type": r["type"], "ext": ext, "blob": blob}
        for k in ("w", "h"):  # only so the page can lay the picture out before it loads
            try:
                v = int(r.get(k) or 0)
            except (TypeError, ValueError):
                v = 0
            if 0 < v <= 20000:
                im[k] = v
        out.append(im)
    return out


def save_images(chat, images):
    """Write a message's pictures into the chat's own folder, chats/<id>/img-N.png, numbered on through the chat.
    They are deleted with the chat. Call with LOCK held."""
    if not images:
        return []
    folder = CHATS_DIR / chat["id"]
    folder.mkdir(parents=True, exist_ok=True)
    n = sum(len(m.get("images") or []) for m in chat["messages"])
    saved = []
    for im in images:
        n += 1
        name = f"img-{n}{im['ext']}"
        (folder / name).write_bytes(im["blob"])
        saved.append({"name": name, **{k: im[k] for k in ("w", "h") if k in im}})
    return saved


def make_title(text):
    t = " ".join(text.split())
    if len(t) <= 50:
        return t
    cut = t[:50]
    space = cut.rfind(" ")
    return (cut[:space] if space > 30 else cut).rstrip(" .,;:!?-") + "…"


def fmt_cost(v):
    return "<$0.01" if 0 < v < 0.01 else f"${v:.2f}"


def result_problem(ev, bot):
    s = ev.get("subtype") or ""
    if "budget" in s:
        return (f"Stopped: this answer reached its Max $ limit ({fmt_cost(bot.get('budget') or 0)}). "
                'Raise Max $ and say "continue".')
    if "turns" in s:
        return 'Stopped: the answer hit Claude Code\'s turn limit. Say "continue" to go on.'
    return ev.get("text") or f"Claude Code reported an error ({s or 'unknown'})."


def finish(bot, status, error=None):
    bot["status"] = status
    if error:
        bot["error"] = error
    for p in bot["parts"]:
        if p.get("k") == "ask" and p.get("state") == "pending":
            p["state"] = "expired"
    texts = [p["s"].strip() for p in bot["parts"] if p["k"] == "text" and p["s"].strip()]
    if bot.get("final") and not texts:
        bot["parts"].append({"k": "text", "s": bot["final"]})
        texts = [bot["final"].strip()]
    bot["text"] = "\n\n".join(texts)
    for k in ("final", "brk", "phase", "current"):
        bot.pop(k, None)


def apply(bot, ev):
    """Fold one answer event into the bot message. The page's onEvent does the same, so both build the same parts."""
    t, parts = ev["t"], bot["parts"]
    last = parts[-1] if parts else None
    if t == "init":
        if ev.get("model"):
            bot["model"] = ev["model"]
        if ev.get("billing_ok") is False:
            bot["warn"] = "This answer was NOT billed to your API key."
        ran = {"manual": "default"}.get(ev.get("mode"), ev.get("mode"))  # newer Claude Code calls Manual "manual"
        if ran and bot.get("mode") and ran != bot["mode"]:
            bot["notice"] = f"Claude Code ran this in {cc.MODES.get(ran, ran)} mode."
    elif t == "notice":
        bot["notice"] = ev["msg"]
    elif t == "keywarn":
        bot["keywarn"] = ev["msg"]
    elif t == "turn":
        bot["phase"], bot["brk"] = "thinking", True
    elif t == "text":
        bot["phase"] = "text"
        if last and last["k"] == "text":
            if bot.get("brk") and last["s"] and not last["s"].endswith("\n\n"):
                last["s"] += "\n\n"
            last["s"] += ev["d"]
        else:
            parts.append({"k": "text", "s": ev["d"]})
        bot["brk"] = False
    elif t == "tool":
        bot["phase"], bot["current"] = "tool", {"name": ev["name"], "detail": ev["detail"]}
        item = {"name": ev["name"], "detail": ev["detail"], "sub": ev["sub"]}
        if last and last["k"] == "tools":
            last["items"].append(item)
        else:
            parts.append({"k": "tools", "items": [item]})
    elif t == "ask":
        bot["phase"] = "ask"
        parts.append({"k": "ask", "id": ev["id"], "tool": ev["tool"], "title": ev["title"], "detail": ev["detail"],
                      "reason": ev.get("reason") or "", "state": "pending"})
    elif t == "answered":
        for p in parts:
            if p.get("k") == "ask" and p.get("id") == ev["id"]:
                p["state"] = ev["state"]
        if not any(p.get("k") == "ask" and p.get("state") == "pending" for p in parts):
            bot["phase"] = "thinking"
    elif t == "result":
        bot.update(cost=ev["cost"] or 0.0, costUnknown=bool(ev.get("cost_unknown")),
                   seconds=ev["seconds"], blocked=ev["blocked"])
        if ev.get("stopped"):
            finish(bot, "stopped")
        elif ev["ok"]:
            bot["final"] = ev["text"]
            finish(bot, "ok")
        else:
            finish(bot, "error", result_problem(ev, bot))
    elif t == "stopped":
        finish(bot, "stopped")
    elif t == "error":
        finish(bot, "error", ev["msg"])


def changed():
    """A chat started or finished answering, or was renamed, deleted or added. Open pages wait for this
    (/api/changes) to catch up with what another tab did. Call with LOCK held."""
    STATE["version"] += 1
    WAKE.notify_all()


def clean_text(s):
    """Text from the page, safe to save: a lone half of an emoji pair (it can't be written as UTF-8) becomes "?"."""
    return str(s or "").encode("utf-8", "replace").decode("utf-8")


def save_chat(chat):
    """Write the chat's file. Call with LOCK held."""
    CHATS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CHATS_DIR / f"{chat['id']}.json.tmp"
    tmp.write_text(json.dumps(chat, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, CHATS_DIR / f"{chat['id']}.json")


def load_chats():
    CHATS_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(CHATS_DIR.glob("*.json")):
        try:
            chat = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log(f"skipping unreadable chat file {path.name}")
            continue
        if not isinstance(chat, dict) or chat.get("id") != path.stem or not isinstance(chat.get("messages"), list):
            continue
        for k, v in (("title", "Untitled chat"), ("folder", ""), ("created", 0), ("updated", 0), ("cost", 0.0)):
            chat.setdefault(k, v)  # a file from an older or hand-edited copy still lists
        for m in chat["messages"]:
            if m.get("role") == "bot" and m.get("status") == "running":  # the app was closed mid-answer
                finish(m, "stopped")
                m["note"] = f"Interrupted: {APP_NAME} was closed while this was running."
        CHATS[chat["id"]] = chat


class Run:
    """One answer being produced: Claude Code's process, its events, and any questions waiting for you."""

    def __init__(self, chat, bot, mode):
        self.chat, self.bot, self.mode = chat, bot, mode
        self.id = secrets.token_hex(8)
        self.events = []  # everything the page needs to replay this answer, in order
        self.proc = None
        self.done = self.stopped = False
        self.host = mode in cc.HOST_MODES  # this app answers Claude Code's "may I?" requests
        self.asks = {}  # request id -> {"input", "t0"} for each request waiting for Allow / Deny
        self.stdin_lock = threading.Lock()
        self.stdin_open = False
        self.result_at = None  # when the answer's result arrived
        self.states = False    # whether this Claude Code reports session_state_changed
        self.state = None
        self.req = 0

    def push(self, ev):
        with LOCK:
            apply(self.bot, ev)
            self.events.append(ev)
            WAKE.notify_all()

    def write(self, obj):
        """Send one stream-json line to Claude Code. False when its input is already closed."""
        with self.stdin_lock:
            if not self.stdin_open:
                return False
            try:
                self.proc.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
                self.proc.stdin.flush()
                return True
            except (OSError, ValueError):
                self.stdin_open = False
                return False

    def close_input(self):
        """Ends the session: Claude Code finishes up and exits once its input closes."""
        with self.stdin_lock:
            if self.stdin_open:
                self.stdin_open = False
                try:
                    self.proc.stdin.close()
                except OSError:
                    pass

    def control(self, subtype, **extra):
        self.req += 1
        return self.write({"type": "control_request", "request_id": f"req_{self.req}_{secrets.token_hex(4)}",
                           "request": {"subtype": subtype, **extra}})

    def reply(self, rid, response):
        return self.write({"type": "control_response",
                           "response": {"subtype": "success", "request_id": rid, "response": response}})

    def on_request(self, ev):
        """Claude Code asks permission for a tool call: show it in the page and wait for your answer."""
        rid, req = ev.get("request_id"), ev.get("request") or {}
        if not rid:
            return
        if req.get("subtype") != "can_use_tool":
            self.write({"type": "control_response", "response": {
                "subtype": "error", "request_id": rid, "error": f"{APP_NAME} doesn't handle {req.get('subtype')}"}})
            return
        tool = str(req.get("tool_name") or "a tool")
        inp = req.get("input") if isinstance(req.get("input"), dict) else {}
        # Claude Code 2.1.323 sends display_name (just the tool's name) and description (for Bash, what the command
        # is for; for Write, the file's name), but no title.
        title = req.get("title") or ASK_TITLES.get(tool) or req.get("display_name") or f"Use {tool}"
        detail = ask_detail(tool, inp)
        why = [str(req.get("description") or "").strip(), ANSI.sub("", str(req.get("decision_reason") or "")).strip()]
        why = [w for w in why if w and w not in detail]
        if req.get("blocked_path") and str(req["blocked_path"]) not in detail:
            why.append(f"Path: {req['blocked_path']}")
        with LOCK:
            self.asks[rid] = {"input": inp, "t0": time.time()}
        self.push({"t": "ask", "id": rid, "tool": tool, "title": short(title, 120), "detail": detail,
                   "reason": short(" · ".join(why), 400)})

    def answer(self, rid, allow, why=None, interrupt=False, state="denied"):
        """Your Allow / Deny goes back to Claude Code. False when that request is no longer waiting."""
        with LOCK:
            info = self.asks.pop(rid, None)
        if info is None:
            return False
        if allow:
            sent = self.reply(rid, {"behavior": "allow", "updatedInput": info["input"]})
        else:
            sent = self.reply(rid, {"behavior": "deny", "interrupt": interrupt,
                                    "message": why or "The user said no. Don't try it again; ask in your reply "
                                                      "if you need it."})
        self.push({"t": "answered", "id": rid, "state": "allowed" if allow else state})
        return sent

    def cancel(self, rid):
        with LOCK:
            known = self.asks.pop(rid, None) is not None
        if known:
            self.push({"t": "answered", "id": rid, "state": "cancelled"})

    def stop(self):
        self.stopped = True
        if self.host and self.stdin_open:
            for rid in list(self.asks):
                self.answer(rid, False, why="Stopped by the user.", interrupt=True, state="stopped")
            self.control("interrupt")  # lets Claude Code end the turn cleanly and save it

            def later():
                time.sleep(5)
                self.close_input()
                time.sleep(5)
                cc.kill_tree(self.proc)
            threading.Thread(target=later, daemon=True).start()
        else:
            cc.kill_tree(self.proc)

    def tick(self):
        """Every few seconds while running: decline questions nobody answered, and end a finished session whose
        Claude Code never said it went idle."""
        now = time.time()
        with LOCK:
            late = [rid for rid, a in self.asks.items() if now - a["t0"] > ASK_TIMEOUT]
            waiting = bool(self.asks)
        for rid in late:
            self.answer(rid, False, why="Nobody answered for 30 minutes, so this was declined.", interrupt=True,
                        state="expired")
        if self.result_at and not waiting and now - self.result_at > 15:
            self.close_input()


def run_chat(run, *args):
    try:
        _run_chat(run, *args)
    except Exception as e:  # a bug in here must not leave the chat "answering" for ever
        log(f"chat {run.chat['id'][:8]}  crashed: {e!r}")
        cc.kill_tree(run.proc)
        if not run.done:
            run.push({"t": "error", "msg": f"Something went wrong in {APP_NAME}: {e}. Details are in app.log."})
    finally:
        if not run.done:
            end_run(run)


def _run_chat(run, text, images, model, effort, budget, followup):
    chat, sid = run.chat, run.chat["id"]
    key, problem = keys.load(HOME)
    if not key:  # without it Claude Code would fall back to your Claude login, which isn't what this app is for
        run.push({"t": "error", "msg": problem or "Add your API key first."})
        end_run(run)
        return
    if problem:  # there's a key to use, but key.txt needs a look: say so with the answer
        run.push({"t": "keywarn", "msg": problem})
    resume = has_transcript(sid)  # the chat's first message creates the session, later ones resume it
    before = session_cost(sid) if resume else 0.0
    args = cc.build_args(STATE["claude"], sid=sid, resume=resume, model=model, effort=effort, budget=budget,
                         mode=run.mode)
    log(f"chat {sid[:8]}  {model} {effort} {run.mode}  max ${budget:.2f}  in {chat['folder']}"
        + (f"  + {len(images)} picture(s)" if images else ""))
    t0, result = time.time(), None
    try:
        message = user_message(text, images)
        proc = subprocess.Popen(args, cwd=chat["folder"], env=cc.child_env(key), stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, **cc.popen_kwargs())
    except OSError as e:
        run.push({"t": "error", "msg": f"Could not start Claude Code: {e}"})
        end_run(run)
        return
    run.proc, run.stdin_open = proc, True
    if run.stopped:  # Stop was pressed while Claude Code was starting
        cc.kill_tree(proc)
    err_tail = []
    threading.Thread(target=drain, args=(io.TextIOWrapper(proc.stderr, encoding="utf-8", errors="replace"),
                                         err_tail), daemon=True).start()

    def send_message():
        if run.host:
            run.control("initialize", hooks=None)  # what Anthropic's own SDK sends before talking to Claude Code
        run.write(message)
        if not run.host:
            run.close_input()  # nothing to answer: Claude Code runs the message and exits

    threading.Thread(target=send_message, daemon=True).start()

    def ticker():
        while not run.done:
            time.sleep(3)
            run.tick()

    threading.Thread(target=ticker, daemon=True).start()
    answered = any(m.get("role") == "bot" and m is not run.bot and (m.get("status") == "ok" or m.get("cost"))
                   for m in chat["messages"])
    if followup and not resume and answered:  # (an earlier message that failed before it began doesn't count)
        run.push({"t": "notice", "msg": "Claude Code no longer has the earlier part of this chat "
                                        "(it keeps chats for 30 days), so this answer starts fresh."})
    for line in io.TextIOWrapper(proc.stdout, encoding="utf-8", errors="replace"):
        try:
            ev = json.loads(line)
        except ValueError:
            if line.strip():  # a plain-text error from Claude Code: keep it for the error message
                err_tail.append(ANSI.sub("", line.strip())[:500])
                del err_tail[:-20]
            continue
        if not isinstance(ev, dict):
            continue
        kind = ev.get("type")
        if kind == "control_request":
            run.on_request(ev)
            continue
        if kind == "control_cancel_request":
            run.cancel(ev.get("request_id"))
            continue
        if kind == "control_response":
            continue
        if kind == "system" and ev.get("subtype") == "session_state_changed":
            run.states, run.state = True, ev.get("state")
            if run.state == "idle" and run.result_at and not run.asks:
                run.close_input()
            continue
        for out in translate(ev):
            if out["t"] == "result":
                out["cost"] = max(0.0, out["cost"] - before)
                if run.stopped and not out["ok"]:
                    out["stopped"] = True
                result = out
                run.result_at = time.time()
            run.push(out)
        if kind == "result" and run.host and (not run.states or run.state == "idle") and not run.asks:
            run.close_input()
    proc.wait()
    run.close_input()
    for rid in list(run.asks):
        run.cancel(rid)
    if result is None:
        if run.stopped:
            run.push({"t": "stopped"})
        else:
            msg = " | ".join([t for t in err_tail if t][-3:]) or (
                f"Claude Code stopped with error code {proc.returncode}. Running claude in a terminal may show why.")
            if "unknown option" in msg:
                msg += "\n\nYour Claude Code may be too old for this app. Run `claude update`, then try again."
            run.push({"t": "error", "msg": msg})
    end_run(run)
    if result:
        log(f"chat {sid[:8]}  done in {time.time() - t0:.0f}s, cost ${result['cost']:.2f}")
    else:
        log(f"chat {sid[:8]}  {'stopped' if run.stopped else 'failed'}")


def end_run(run):
    with LOCK:
        run.done = True
        run.events.append({"t": "done"})
        RUNS.pop(run.chat["id"], None)
        run.chat["cost"] = sum(m.get("cost") or 0 for m in run.chat["messages"] if m["role"] == "bot")
        run.chat["updated"] = now_ms()
        try:
            save_chat(run.chat)
        except (OSError, ValueError) as e:
            log(f"couldn't save chat {run.chat['id'][:8]}: {e}")
        changed()


# ---------------------------------------------------------------- the web app

class Server(ThreadingHTTPServer):
    # macOS/Linux: lets the app take its port straight back after it quits (the last run's connections linger on it
    # for up to a minute, and without this it would move to the next port). On a Mac it could also share a port with
    # a program listening on all addresses, so main() first checks that nothing answers there. Not on Windows, where
    # it would let a second copy of the app bind the same port.
    allow_reuse_address = not cc.WINDOWS
    daemon_threads = True

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], ConnectionError):
            return  # the page went away before its answer was sent (a reload, a closed tab): nothing went wrong
        super().handle_error(request, client_address)


class Server6(Server):
    address_family = socket.AF_INET6


class Handler(BaseHTTPRequestHandler):
    server_version = f"APICreditCode/{__version__}"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body=b"", ctype="text/plain; charset=utf-8", extra=None):
        headers = {"Content-Type": ctype, "Content-Length": str(len(body)), "Cache-Control": "no-store",
                   "X-Content-Type-Options": "nosniff", **(extra or {})}
        self.send_response(code)
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _allowed(self, need_token):
        """Only this computer, only by this app's own names, and for the API only with the page's token."""
        try:
            client = ipaddress.ip_address(self.client_address[0].split("%")[0])
        except ValueError:
            return False
        mapped = getattr(client, "ipv4_mapped", None)  # ::ffff:127.0.0.1 on a dual-stack socket
        if not client.is_loopback and not (mapped and mapped.is_loopback):
            return False
        raw = (self.headers.get("Host") or "").lower()
        host, _, port = raw.rpartition(":")
        if host not in STATE["hosts"] or port != str(STATE["port"]):
            return False  # blocks websites that reach this app through DNS tricks
        return not need_token or secrets.compare_digest(self.headers.get("X-Token", ""), TOKEN)

    def do_GET(self):
        path, _, query = self.path.partition("?")
        if path == "/api/hello":  # how a second copy of the app finds this one; tells nothing else
            if not self._allowed(False):
                return self._send(403, b"forbidden")
            return self._json(200, {"app": APP_ID, "version": __version__})
        if not self._allowed(path.startswith("/api/")):
            return self._send(403, b"forbidden")
        if path.startswith("/api/"):
            STATE["seen"] = time.time()
        if path == "/":
            html = (STATIC / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", TOKEN)
            return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8",
                              {"Content-Security-Policy": CSP, "Referrer-Policy": "no-referrer"})
        if path == "/favicon.ico":
            return self._send(200, (STATIC / "icon.ico").read_bytes(), TYPES[".ico"])
        name = path[len("/static/"):] if path.startswith("/static/") else ""
        if name in STATIC_FILES:
            return self._send(200, (STATIC / name).read_bytes(), STATIC_FILES[name])
        f = FILE_URL.match(path)
        if f:  # a chat's pictures. No token (an <img> can't send one): the chat id is unguessable, and the network and
            # Host checks above still apply, like for the page itself. Pictures never change, so the browser may keep them.
            file = CHATS_DIR / f.group(1) / f.group(2)
            with LOCK:
                known = f.group(1) in CHATS
            if not known or not file.is_file():
                return self._send(404, b"not found")
            return self._send(200, file.read_bytes(), TYPES[file.suffix],
                              {"Cache-Control": "private, max-age=31536000, immutable"})
        if path == "/api/status":
            return self._json(200, {
                "version": __version__, "models": MODELS, "efforts": EFFORTS, "modes": list(cc.MODES),
                "defaults": {"model": DEFAULT_MODEL, "effort": DEFAULT_EFFORT, "mode": "auto"},
                "claude": claude_status(), "key": key_status(), "data_dir": str(HOME), "platform": sys.platform,
                "folders": folders.trusted(paths.claude_state_file()), "app_mode": STATE["app"]})
        if path == "/api/folders":
            return self._json(200, folders.trusted(paths.claude_state_file()))
        if path == "/api/chats":
            with LOCK:
                items = [{"id": c["id"], "title": c["title"], "updated": c["updated"], "cost": c["cost"],
                          "running": c["id"] in RUNS} for c in CHATS.values()]
            items.sort(key=lambda c: -c["updated"])
            return self._json(200, items)
        if path == "/api/changes":
            since = re.search(r"(?:^|&)since=(-?\d+)", query)
            since = int(since.group(1)) if since else -1
            with WAKE:  # answer at once if the page is behind, else as soon as something changes (or after 25 s)
                WAKE.wait_for(lambda: STATE["version"] != since or QUIT.is_set(), timeout=25)
                version = STATE["version"]
            STATE["seen"] = time.time()
            return self._json(200, {"version": version})
        m = CHAT_URL.match(path)
        if m and m.group(2) is None:
            with LOCK:
                chat = CHATS.get(m.group(1))
                if not chat:
                    return self._send(404, b"no such chat")
                run = RUNS.get(m.group(1))
                payload = {"chat": copy.deepcopy(chat), "running": run is not None,
                           "cursor": len(run.events) if run else None}
            return self._json(200, payload)
        if m and m.group(2) == "events":
            start = re.search(r"(?:^|&)from=(\d+)", query)
            return self._events(m.group(1), int(start.group(1)) if start else 0)
        self._send(404, b"not found")

    def do_POST(self):
        if not self._allowed(True):
            return self._send(403, b"forbidden")
        STATE["seen"] = time.time()
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                left = min(n, 4 * MAX_BODY)  # read it first: closing with it unread resets the connection on Windows
                while left > 0:
                    chunk = self.rfile.read(min(left, 1 << 20))
                    if not chunk:
                        break
                    left -= len(chunk)
                return self._send(413, b"That's too much to send at once. Try fewer or smaller pictures.")
            body = json.loads(self.rfile.read(n)) if n > 0 else {}
        except (ValueError, RecursionError):
            return self._send(400, b"bad request")
        if not isinstance(body, dict):
            return self._send(400, b"bad request")
        if self.path == "/api/key":
            return self._save_key(body)
        if self.path == "/api/key/delete":
            try:
                keys.delete(HOME)
            except OSError as e:
                return self._send(500, f"Couldn't remove key.txt ({e.strerror or e}). Delete it yourself: "
                                       f"{keys.key_file(HOME)}".encode("utf-8"))
            return self._json(200, {"key": key_status()})
        if self.path == "/api/quit":
            self._json(200, {"bye": True})
            threading.Thread(target=lambda: (time.sleep(0.3), QUIT.set()), daemon=True).start()
            return None
        m = CHAT_URL.match(self.path)
        if m and m.group(2) == "send":
            return self._start(m.group(1), body)
        if m and m.group(2) == "stop":
            with LOCK:
                run = RUNS.get(m.group(1))
            if run:
                run.stop()
            return self._json(200, {"stopped": bool(run)})
        if m and m.group(2) == "answer":
            with LOCK:
                run = RUNS.get(m.group(1))
            if not run or not run.answer(str(body.get("ask") or ""), bool(body.get("allow"))):
                return self._send(409, b"Claude isn't waiting for that answer any more.")
            return self._json(200, {"answered": True})
        if m and m.group(2) == "rename":
            title = " ".join(clean_text(body.get("title")).split())[:80]
            if not title:
                return self._send(400, b"Type a name first.")
            with LOCK:
                chat = CHATS.get(m.group(1))
                if not chat:
                    return self._send(404, b"no such chat")
                old, chat["title"] = chat["title"], title
                try:
                    save_chat(chat)
                except (OSError, ValueError) as e:
                    chat["title"] = old
                    return self._send(500, f"Couldn't save the new name: {e}".encode("utf-8"))
                changed()
            return self._json(200, {"title": title})
        if m and m.group(2) == "delete":
            with LOCK:
                if m.group(1) in RUNS:
                    return self._send(409, b"This chat is still answering. Stop it first.")
                CHATS.pop(m.group(1), None)
                (CHATS_DIR / f"{m.group(1)}.json").unlink(missing_ok=True)
                shutil.rmtree(CHATS_DIR / m.group(1), ignore_errors=True)  # its pictures
                changed()
            return self._json(200, {"deleted": True})
        self._send(404, b"not found")

    def _save_key(self, body):
        raw = str(body.get("key") or "")
        found = keys.KEY_RE.search(raw)
        if not found:
            return self._json(200, {"ok": False, "status": "bad", "key": key_status(), "message": (
                "That isn't an API key. Keys start with sk-ant-." if "sk-ant-" not in raw else
                "That isn't the whole key: it has a space or line break in it, or part of it is missing. "
                "Copy it again from the Console, all in one piece.")})
        key = found.group(0)
        status, message = keys.check(key)
        if status == "bad" and keys.CUT_RE.match(raw, found.end()):  # (text after a whole key is fine)
            message = ("Anthropic didn't accept this key, and it looks cut in two by a space or line break. "
                       "Copy it again from the Console, all in one piece.")
        if status != "bad":
            try:
                keys.save(HOME, key)
            except OSError as e:
                return self._json(200, {"ok": False, "status": "unknown", "key": key_status(),
                                        "message": f"Couldn't save the key in {keys.key_file(HOME)} "
                                                   f"({e.strerror or e})."})
            log(f"saved API key {keys.mask(key)} ({status})")
        return self._json(200, {"ok": status != "bad", "status": status, "message": message, "key": key_status()})

    def _start(self, sid, body):
        text = clean_text(body.get("message")).strip()
        try:
            images = decode_images(body.get("images"))
        except ValueError as e:
            return self._send(400, str(e).encode("utf-8"))
        if not text and not images:
            return self._send(400, b"Type a message first.")
        if len(text) > MAX_CHARS:
            return self._send(400, f"That message is too long: the limit is {MAX_CHARS:,} characters.".encode("utf-8"))
        claude = claude_status()  # looks again if Claude Code was missing or too old
        if not claude["found"]:
            return self._send(400, b"Claude Code isn't installed on this computer. Install it, then try again.")
        key, problem = keys.load(HOME)
        if not key:
            return self._send(400, (problem or "There's no API key yet. Click the key button at the top right and "
                                               "paste your key.").encode("utf-8"))
        model = body.get("model") if body.get("model") in MODELS else DEFAULT_MODEL
        effort = body.get("effort") if body.get("effort") in EFFORTS else DEFAULT_EFFORT
        mode = body.get("mode") if body.get("mode") in cc.MODES else "auto"
        if mode in cc.HOST_MODES and not claude["host_ok"]:
            need = ".".join(map(str, cc.MIN_VERSION))
            return self._send(400, f"Manual and Accept edits need Claude Code {need} or newer. Run: claude update, "
                                   "then try again.".encode("utf-8"))
        try:
            budget = min(max(float(body.get("budget") or 5), 0.1), 50.0)
        except (TypeError, ValueError):
            budget = 5.0
        with LOCK:
            last = RUNS.get(sid)
        if last and last.result_at and not last.asks:  # its answer is in and Claude Code is closing (that takes a few
            end = time.time() + 20                     # seconds): wait, so a quick follow-up or "Run this plan" works
            while not last.done and time.time() < end:
                time.sleep(0.1)
        with LOCK:
            if sid in RUNS:
                return self._send(409, b"This chat is still answering. Stop it first, or wait for it to finish.")
            chat = CHATS.get(sid)
            followup = bool(chat and chat["messages"])
            if chat:
                folder = chat["folder"]
            else:
                folder = folders.match(str(body.get("folder") or ""), folders.trusted(paths.claude_state_file()))
                if not folder:
                    return self._send(400, b"Pick a folder from the list. To add one, open it once with `claude` "
                                           b"in a terminal and say yes when it asks whether you trust it.")
            if not os.path.isdir(folder):
                gone = f"This chat's folder is gone: {folder}." if folder else "This chat has no folder."
                return self._send(400, f"{gone} Start a new chat.".encode("utf-8"))
            if not chat:
                chat = CHATS[sid] = {"id": sid, "title": make_title(text or "Picture"), "folder": folder,
                                     "created": now_ms(), "updated": now_ms(), "cost": 0.0, "messages": []}
            try:
                saved = save_images(chat, images)
            except OSError as e:
                if not followup:
                    CHATS.pop(sid, None)
                return self._send(500, f"Couldn't save the picture: {e}".encode("utf-8"))
            user = {"role": "user", "text": text, "ts": now_ms()}
            if saved:
                user["images"] = saved
            bot = {"role": "bot", "status": "running", "parts": [], "phase": "thinking", "model": model,
                   "effort": effort, "mode": mode, "budget": budget, "started": now_ms()}
            chat["messages"] += [user, bot]
            chat["updated"] = now_ms()
            try:  # saved before it starts, so a chat that can't be saved never starts "answering"
                save_chat(chat)
            except (OSError, ValueError) as e:
                del chat["messages"][-2:]
                if not followup:
                    CHATS.pop(sid, None)
                return self._send(500, f"Couldn't save this chat in {CHATS_DIR}: {e}".encode("utf-8"))
            run = RUNS[sid] = Run(chat, bot, mode)
            changed()
        files = [(im["type"], CHATS_DIR / sid / s["name"]) for im, s in zip(images, saved)]
        threading.Thread(target=run_chat, args=(run, text, files, model, effort, budget, followup), daemon=True).start()
        self._json(200, {"run": run.id})

    def _events(self, sid, start):
        """Stream an answer's events from `start` on, then a final "done". Reconnecting pages pass where they left off."""
        with LOCK:
            run = RUNS.get(sid)
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()

        def emit(obj):
            self.wfile.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
            self.wfile.flush()

        i = start
        try:
            if run is None:
                return emit({"t": "done"})
            while True:
                with WAKE:
                    WAKE.wait_for(lambda: len(run.events) > i or run.done, timeout=15)
                    batch, finished = run.events[i:], run.done
                i += len(batch)
                STATE["seen"] = time.time()
                for ev in batch:
                    emit(ev)
                if finished and (not batch or batch[-1]["t"] == "done"):
                    if not batch:
                        emit({"t": "done"})
                    return
                if not batch:
                    emit({"t": "ping"})  # keeps the connection alive while Claude is quiet
        except (OSError, ValueError):
            pass  # the page went away; the answer keeps running for whoever opens the chat next


# ---------------------------------------------------------------- starting and stopping

def running_copy(port):
    """True when this app already answers on that port (a second start then just opens a tab)."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/hello", timeout=2) as r:
            return json.loads(r.read()).get("app") == APP_ID
    except (OSError, ValueError):
        return False


def answers(port):
    """True when some program accepts connections on this port of this computer."""
    for host in ("127.0.0.1", "::1"):
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            pass
    return False


def bind(port):
    """Listen on this computer only: 127.0.0.1, and ::1 too where the computer has IPv6."""
    servers = [Server(("127.0.0.1", port), Handler)]
    port = servers[0].server_address[1]
    try:
        servers.append(Server6(("::1", port), Handler))
    except OSError:
        pass
    return servers, port


def log_to_file():
    """No console (started from an icon): write the log to app.log in this app's folder instead."""
    HOME.mkdir(parents=True, exist_ok=True)
    path = HOME / "app.log"
    try:
        if path.stat().st_size > 1_000_000:
            os.replace(path, HOME / "app.log.1")
    except OSError:
        pass
    f = open(path, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = f


def quit_when_closed():
    """With --app: once no page has talked to the app for a while and nothing is running, quit.

    It must stay idle for several checks in a row, so waking a laptop from sleep doesn't end it before the page
    reconnects."""
    idle = 0
    while not QUIT.wait(30):
        with LOCK:
            busy = bool(RUNS)
        idle = idle + 1 if not busy and time.time() - STATE["seen"] > IDLE_QUIT else 0
        if idle >= 6:
            log("no page open for a while: quitting")
            QUIT.set()


def find_claude():
    STATE["claude_checked"] = time.time()  # first, so a page asking at the same moment doesn't look as well
    found = cc.find()
    ver = cc.version(found) if found else None
    STATE["claude"], STATE["claude_version"] = found, ver  # together, so nobody sees one without the other
    if not STATE["claude"]:
        log("Claude Code not found")
    else:
        v = STATE["claude_version"]
        log(f"Claude Code {'.'.join(map(str, v)) if v else '(version unknown)'} at {STATE['claude'][-1]}")


def selftest():
    """Start on a free port, then fetch the page and the status the way a browser would (used by the builds)."""
    servers, port = bind(0)
    STATE["port"] = port
    for srv in servers:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    with urllib.request.urlopen(base + "/api/hello", timeout=10) as r:
        assert json.loads(r.read())["app"] == APP_ID
    with urllib.request.urlopen(base + "/", timeout=10) as r:
        assert TOKEN in r.read().decode("utf-8")
    req = urllib.request.Request(base + "/api/status", headers={"X-Token": TOKEN})
    with urllib.request.urlopen(req, timeout=60) as r:
        status = json.loads(r.read())
    assert status["version"] == __version__ and status["models"]
    msg = (f"selftest ok: {APP_NAME} {__version__}, Claude Code "
           f"{status['claude']['version'] or 'not found'}, {len(status['folders'])} folder(s)")
    if sys.stdout is not None:
        print(msg, flush=True)
    else:  # the windowed app builds have no console
        HOME.mkdir(parents=True, exist_ok=True)
        (HOME / "selftest.txt").write_text(msg + "\n", encoding="utf-8")


def detach(port):
    """The Mac app build: run the app as a separate process and return, so double-clicking the app again works
    (macOS only brings a running app forward; it doesn't start it again)."""
    if running_copy(port):
        webbrowser.open(f"http://localhost:{port}/")
        return
    subprocess.Popen([sys.executable, "--app", "--serve"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def main():
    ap = argparse.ArgumentParser(prog=APP_ID, description=f"{APP_NAME}: run your own Claude Code from a browser "
                                                          "tab, on your monthly API credits.")
    ap.add_argument("--port", type=int, default=PORT, help=f"port on this computer (default {PORT})")
    ap.add_argument("--no-browser", action="store_true", help="don't open the browser")
    ap.add_argument("--app", action="store_true", help="started from the app icon: log to a file, quit when closed")
    ap.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--make-launcher", action="store_true", help="add the app icon (Start menu and Desktop, or "
                                                                 "~/Applications on a Mac)")
    ap.add_argument("--remove-launcher", action="store_true", help="remove the app icon")
    ap.add_argument("--selftest", action="store_true", help="start, check the app answers, and exit")
    ap.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    frozen = getattr(sys, "frozen", False)
    # an app started from an icon ignores arguments it doesn't know (older macOS adds -psn_...)
    a = ap.parse_known_args()[0] if frozen else ap.parse_args()
    if not 1 <= a.port <= 65535:
        ap.error("--port must be a number from 1 to 65535")
    a.app = a.app or frozen  # the .exe and the Mac app are always started from an icon

    if a.make_launcher or a.remove_launcher:
        try:
            done = launcher.make() if a.make_launcher else launcher.remove()
        except (OSError, subprocess.SubprocessError) as e:
            sys.exit(f"Couldn't {'make' if a.make_launcher else 'remove'} the app icon: {e}")
        for p in done:
            print(("Made " if a.make_launcher else "Removed ") + p)
        return
    if a.selftest:
        find_claude()
        selftest()
        return
    if frozen and sys.platform == "darwin" and not a.serve:
        detach(a.port)
        return
    if a.app or sys.stdout is None:
        log_to_file()
    elif hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    for port in range(a.port, min(a.port + 10, 65536)):  # another program may have the port: try the next few
        if running_copy(port):
            log(f"{APP_NAME} is already running on port {port}: opening a tab")
            if not a.no_browser:
                webbrowser.open(f"http://localhost:{port}/")
            return
        if not cc.WINDOWS and answers(port):  # another program is on it (bind alone could share it there: see Server)
            continue
        try:
            servers, port = bind(port)
            break
        except OSError:
            continue
    else:
        sys.exit(f"Ports {a.port}-{min(a.port + 9, 65535)} are all busy. Start with --port <another number>.")
    STATE["port"], STATE["app"] = port, a.app
    url = f"http://localhost:{port}/"
    log(f"{APP_NAME} {__version__} on {url}  (data: {HOME})")
    if a.app and sys.platform == "darwin":
        cc.adopt_login_path()
    find_claude()
    load_chats()
    for srv in servers:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    if not a.app:
        print(f"\n{APP_NAME} is running: {url}\nKeep this window open while you use it. Press Ctrl+C to stop.\n",
              flush=True)
    if not a.no_browser:
        webbrowser.open(url)
    if a.app:
        threading.Thread(target=quit_when_closed, daemon=True).start()
    try:
        while not QUIT.wait(1):
            pass
    except KeyboardInterrupt:
        pass
    finally:
        with LOCK:
            runs = list(RUNS.values())
        for run in runs:
            cc.kill_tree(run.proc)
        for srv in servers:
            srv.shutdown()
        log("stopped")


if __name__ == "__main__":
    main()
