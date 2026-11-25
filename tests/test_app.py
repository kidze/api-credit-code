"""The whole app, started the way a user starts it, with a stand-in for Claude Code (fake_claude.py).

No network, no real API key, nothing outside a temporary folder: the app's folder, Claude Code's folder and the
project folder all live there.
"""
import base64
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "src"
FAKE = HERE / "fake_claude.py"
GOOD_KEY = "sk-ant-api03-good" + "x" * 30
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNg+M/wHwAEAQH/2NOuWQAAAABJRU5ErkJggg==")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class AppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        t = Path(cls.tmp.name)
        cls.home, cls.config, cls.project, cls.untrusted = t / "app", t / "claude", t / "project", t / "untrusted"
        for p in (cls.config, cls.project, cls.untrusted):
            p.mkdir()
        (cls.config / ".claude.json").write_text(json.dumps({"projects": {
            str(cls.project): {"hasTrustDialogAccepted": True, "lastSessionModified": 5},
            str(cls.untrusted): {"hasTrustDialogAccepted": False}}}), encoding="utf-8")
        cls.log = t / "fake.log"
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        env.update(API_CREDIT_CODE_HOME=str(cls.home), CLAUDE_CONFIG_DIR=str(cls.config),
                   API_CREDIT_CODE_CLAUDE=json.dumps([sys.executable, str(FAKE)]), API_CREDIT_CODE_FAKE_CHECK="1",
                   FAKE_CLAUDE_LOG=str(cls.log), PYTHONPATH=str(SRC), PYTHONIOENCODING="utf-8")
        cls.port = free_port()
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.out = open(t / "server.log", "w", encoding="utf-8")
        cls.proc = subprocess.Popen([sys.executable, "-m", "api_credit_code", "--no-browser", "--port", str(cls.port)],
                                    env=env, stdin=subprocess.DEVNULL, stdout=cls.out, stderr=subprocess.STDOUT)
        for _ in range(100):
            try:
                with urllib.request.urlopen(cls.base + "/", timeout=2) as r:
                    cls.page = r.read().decode("utf-8")
                    cls.headers = dict(r.headers)
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("the app didn't start")
        cls.token = re.search(r'name="token" content="([^"]+)"', cls.page).group(1)

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.kill()
            cls.proc.wait(10)
        cls.out.close()
        cls.tmp.cleanup()

    # ------------------------------------------------------------ helpers

    def call(self, path, body=None, token=True, host=None):
        headers = {"X-Token": self.token} if token else {}
        if host:
            headers["Host"] = host
        data = json.dumps(body).encode("utf-8") if body is not None else None
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, headers=headers,
                                     method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.read()

    def get(self, path):
        code, body = self.call(path)
        self.assertEqual(code, 200, body)
        return json.loads(body)

    def send(self, cid, message, mode="auto", folder=None, **extra):
        body = {"message": message, "mode": mode, "model": "claude-haiku-5-5", "effort": "low", "budget": 1,
                "folder": str(folder or self.project), **extra}
        return self.call(f"/api/chats/{cid}/send", body)

    def wait(self, cid, until, timeout=30):
        end = time.time() + timeout
        while time.time() < end:
            got = self.get(f"/api/chats/{cid}")
            if until(got):
                return got
            time.sleep(0.1)
        self.fail(f"timed out waiting on chat {cid}")

    def done(self, cid):
        return self.wait(cid, lambda c: not c["running"])["chat"]

    def last_args(self):
        return json.loads(self.log.read_text(encoding="utf-8").splitlines()[-1])

    def pending_ask(self, cid):
        def find(c):
            bot = c["chat"]["messages"][-1]
            return next((p for p in bot.get("parts", []) if p["k"] == "ask" and p["state"] == "pending"), None)
        got = self.wait(cid, find)
        return find(got)

    # ------------------------------------------------------------ the tests, in order

    def test_01_only_this_app_can_drive_it(self):
        self.assertIn("default-src 'self'", self.headers["Content-Security-Policy"])
        self.assertEqual(self.call("/api/status", token=False)[0], 403)
        self.assertEqual(self.call("/api/status", host=f"evil.example:{self.port}")[0], 403)
        self.assertEqual(self.call("/api/status", host="localhost:1")[0], 403)
        self.assertEqual(self.call("/api/status", host=f"localhost:{self.port}")[0], 200)
        self.assertEqual(self.call("/api/key", {"key": GOOD_KEY}, token=False)[0], 403)
        hello = json.loads(self.call("/api/hello", token=False)[1])
        self.assertEqual(hello["app"], "api-credit-code")
        self.assertNotIn("token", json.dumps(hello))
        for name in ("app.js", "app.css", "icon.svg", "marked.umd.js", "purify.min.js"):
            self.assertEqual(self.call("/static/" + name, token=False)[0], 200, name)
        self.assertEqual(self.call("/static/../app.py", token=False)[0], 404)
        self.assertEqual(self.call("/static/index.html", token=False)[0], 404)

    def test_02_status_before_a_key(self):
        s = self.get("/api/status")
        self.assertTrue(s["claude"]["found"])
        self.assertEqual(s["claude"]["version"], "2.1.400")
        self.assertTrue(s["claude"]["host_ok"])
        self.assertFalse(s["key"]["set"])
        self.assertEqual(s["modes"], ["auto", "default", "acceptEdits", "plan"])
        paths = [f["path"] for f in s["folders"]]
        self.assertEqual(paths[0], str(self.project))
        self.assertNotIn(str(self.untrusted), paths)
        code, body = self.send(str(uuid.uuid4()), "hello")
        self.assertEqual(code, 400)
        self.assertIn(b"API key", body)

    def test_03_key(self):
        r = json.loads(self.call("/api/key", {"key": "not a key"})[1])
        self.assertFalse(r["ok"])
        r = json.loads(self.call("/api/key", {"key": "sk-ant-api03-" + "x" * 30})[1])
        self.assertFalse(r["ok"])
        self.assertFalse(r["key"]["set"])
        r = json.loads(self.call("/api/key", {"key": "sk-ant-api03-nocredit" + "x" * 30})[1])
        self.assertTrue(r["ok"])
        self.assertEqual(r["status"], "nocredit")
        r = json.loads(self.call("/api/key", {"key": f"  {GOOD_KEY}\n"})[1])
        self.assertTrue(r["ok"])
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["key"]["masked"], "sk-ant-api03-...xxxx")
        self.assertNotIn(GOOD_KEY, json.dumps(self.get("/api/status")))
        self.assertEqual((self.home / "key.txt").read_text(encoding="utf-8").strip(), GOOD_KEY)

    def test_04_folders_must_be_trusted(self):
        code, body = self.send(str(uuid.uuid4()), "hello", folder=self.untrusted)
        self.assertEqual(code, 400)
        self.assertIn(b"folder", body)
        self.assertEqual(self.send(str(uuid.uuid4()), "hello", folder=self.project / "nope")[0], 400)
        self.assertEqual(self.send(str(uuid.uuid4()), "hello", mode="bypassPermissions")[0], 200)  # falls back to Auto
        self.assertIn("auto", self.last_args_after_done()["args"])

    def last_args_after_done(self):
        for c in self.get("/api/chats"):
            if c["running"]:
                self.done(c["id"])
        return self.last_args()

    def test_05_auto_chat_and_follow_up(self):
        cid = str(uuid.uuid4())
        self.assertEqual(self.send(cid, "hello")[0], 200)
        chat = self.done(cid)
        bot = chat["messages"][-1]
        self.assertEqual(bot["status"], "ok", bot)
        self.assertEqual(bot["text"], "Hello there")
        self.assertEqual(bot["mode"], "auto")
        self.assertAlmostEqual(bot["cost"], 0.01)
        self.assertNotIn("warn", bot)  # billed to the key
        self.assertEqual(chat["folder"], str(self.project))
        run = self.last_args()
        a = run["args"]
        self.assertEqual(a[a.index("--session-id") + 1], cid)
        self.assertEqual(a[a.index("--permission-mode") + 1], "auto")
        self.assertEqual(a[a.index("--permission-prompts") + 1], "none")
        self.assertNotIn("--permission-prompt-tool", a)
        self.assertEqual(a[a.index("--model") + 1], "claude-haiku-5-5")
        self.assertTrue(run["key"])
        self.assertIsNone(run["scrub"])  # it would force Manual mode
        self.assertEqual(os.path.normcase(os.path.realpath(run["cwd"])),  # macOS: /var is /private/var
                         os.path.normcase(os.path.realpath(self.project)))

        # the follow-up resumes the same session, in the mode picked for it, in the chat's own folder
        self.assertEqual(self.send(cid, "hello again", mode="plan", folder=self.untrusted)[0], 200)
        chat = self.done(cid)
        a = self.last_args()["args"]
        self.assertEqual(a[a.index("--resume") + 1], cid)
        self.assertNotIn("--session-id", a)
        self.assertEqual(a[a.index("--permission-mode") + 1], "plan")
        self.assertAlmostEqual(chat["messages"][-1]["cost"], 0.01)  # this answer only, not the running total
        self.assertAlmostEqual(chat["cost"], 0.02)
        self.assertEqual(chat["folder"], str(self.project))

    def test_06_manual_allow(self):
        cid = str(uuid.uuid4())
        self.assertEqual(self.send(cid, "ask", mode="default")[0], 200)
        ask = self.pending_ask(cid)
        self.assertEqual(ask["tool"], "Bash")
        self.assertEqual(ask["detail"], "echo hi")
        self.assertEqual(ask["title"], "Run a command")
        self.assertTrue(ask["reason"].startswith("Say hi · Bash commands need approval · Path: "), ask["reason"])
        self.assertTrue(ask["reason"].endswith(self.project.name), ask["reason"])
        self.assertEqual(self.call(f"/api/chats/{cid}/answer", {"ask": "perm_nope", "allow": True})[0], 409)
        self.assertEqual(self.call(f"/api/chats/{cid}/answer", {"ask": ask["id"], "allow": True})[0], 200)
        bot = self.done(cid)["messages"][-1]
        self.assertEqual(bot["status"], "ok", bot)
        self.assertEqual(bot["text"], "You allowed it: hi")
        self.assertEqual([p["state"] for p in bot["parts"] if p["k"] == "ask"], ["allowed"])
        a = self.last_args()["args"]
        self.assertEqual(a[a.index("--permission-prompt-tool") + 1], "stdio")
        self.assertEqual(a[a.index("--disallowedTools") + 1], "AskUserQuestion")
        self.assertNotIn("--permission-prompts", a)

    def test_07_accept_edits_deny(self):
        cid = str(uuid.uuid4())
        self.assertEqual(self.send(cid, "ask", mode="acceptEdits")[0], 200)
        ask = self.pending_ask(cid)
        self.assertEqual(self.call(f"/api/chats/{cid}/answer", {"ask": ask["id"], "allow": False})[0], 200)
        bot = self.done(cid)["messages"][-1]
        self.assertEqual(bot["text"], "You said no.")
        self.assertEqual([p["state"] for p in bot["parts"] if p["k"] == "ask"], ["denied"])

    def test_08_stop_while_streaming(self):
        cid = str(uuid.uuid4())
        self.assertEqual(self.send(cid, "slow", mode="default")[0], 200)
        req = urllib.request.Request(f"{self.base}/api/chats/{cid}/events?from=0", headers={"X-Token": self.token})
        seen = []
        with urllib.request.urlopen(req, timeout=30) as r:
            for line in r:
                ev = json.loads(line)
                seen.append(ev["t"])
                if ev["t"] == "text" and "stop" not in seen:
                    seen.append("stop")
                    self.assertEqual(self.call(f"/api/chats/{cid}/stop", {})[0], 200)
                if ev["t"] == "done":
                    break
        self.assertIn("init", seen)
        self.assertIn("result", seen)
        bot = self.done(cid)["messages"][-1]
        self.assertEqual(bot["status"], "stopped", bot)
        self.assertEqual(bot["text"], "Working on it")

    def test_09_stop_in_auto(self):
        cid = str(uuid.uuid4())
        self.assertEqual(self.send(cid, "slow")[0], 200)
        self.wait(cid, lambda c: any(p["k"] == "text" for p in c["chat"]["messages"][-1]["parts"]))
        self.assertEqual(self.call(f"/api/chats/{cid}/stop", {})[0], 200)
        bot = self.done(cid)["messages"][-1]
        self.assertEqual(bot["status"], "stopped", bot)

    def test_10_failure_is_shown(self):
        cid = str(uuid.uuid4())
        self.assertEqual(self.send(cid, "fail")[0], 200)
        bot = self.done(cid)["messages"][-1]
        self.assertEqual(bot["status"], "error")
        self.assertIn("boom", bot["error"])
        cid = str(uuid.uuid4())
        self.assertEqual(self.send(cid, "outdated")[0], 200)
        bot = self.done(cid)["messages"][-1]
        self.assertIn("claude update", bot["error"])

    def test_11_pictures(self):
        cid = str(uuid.uuid4())
        pic = {"type": "image/png", "data": base64.b64encode(PNG).decode(), "w": 1, "h": 1}
        self.assertEqual(self.send(cid, "", images=[pic])[0], 200)
        chat = self.done(cid)
        self.assertEqual(chat["title"], "Picture")
        self.assertEqual(chat["messages"][0]["images"], [{"name": "img-1.png", "w": 1, "h": 1}])
        self.assertEqual(chat["messages"][-1]["text"], "Hello there (1 picture)")
        code, body = self.call(f"/files/{cid}/img-1.png", token=False)
        self.assertEqual((code, body), (200, PNG))
        self.assertEqual(self.call(f"/files/{cid}/img-2.png", token=False)[0], 404)
        bad = {"type": "image/png", "data": base64.b64encode(b"GIF89a....").decode()}
        self.assertEqual(self.send(str(uuid.uuid4()), "x", images=[bad])[0], 400)
        self.assertEqual(self.send(str(uuid.uuid4()), "x", images=[pic] * 9)[0], 400)

    def test_12_rename_and_delete(self):
        cid = str(uuid.uuid4())
        self.send(cid, "hello")
        self.done(cid)
        self.assertEqual(json.loads(self.call(f"/api/chats/{cid}/rename", {"title": "  My   chat "})[1])["title"],
                         "My chat")
        self.assertEqual(self.call(f"/api/chats/{cid}/rename", {"title": "   "})[0], 400)
        self.assertIn("My chat", [c["title"] for c in self.get("/api/chats")])
        self.assertEqual(self.call(f"/api/chats/{cid}/delete", {})[0], 200)
        self.assertEqual(self.call(f"/api/chats/{cid}")[0], 404)
        self.assertFalse((self.home / "chats" / f"{cid}.json").exists())

    def test_13_changes_wake_pages(self):
        v = self.get("/api/changes?since=-1")["version"]
        cid = str(uuid.uuid4())
        self.send(cid, "hello")
        self.assertNotEqual(self.get(f"/api/changes?since={v}")["version"], v)
        self.done(cid)

    def test_14_key_file_by_hand(self):
        path = self.home / "key.txt"
        try:
            path.write_text(f"{GOOD_KEY}\nsk-ant-api03-second{'y' * 30}\n", encoding="utf-8")
            k = self.get("/api/status")["key"]
            self.assertTrue(k["set"])
            self.assertTrue(k["problem"].startswith("key.txt has 2 API keys. Using the first one"), k)
            self.assertEqual(os.path.normcase(os.path.realpath(k["file"])), os.path.normcase(os.path.realpath(path)))
            cid = str(uuid.uuid4())
            self.assertEqual(self.send(cid, "hello")[0], 200)
            bot = self.done(cid)["messages"][-1]
            self.assertEqual(bot["status"], "ok", bot)
            self.assertEqual(bot["keywarn"], k["problem"])  # said with the answer too

            path.write_text("my key: sk-ant-oops", encoding="utf-8")
            k = self.get("/api/status")["key"]
            self.assertFalse(k["set"])
            self.assertIn("no API key in key.txt", k["problem"])
            code, body = self.send(str(uuid.uuid4()), "hello")
            self.assertEqual(code, 400)
            self.assertIn(b"no API key in key.txt", body)
        finally:
            path.write_text(GOOD_KEY + "\n", encoding="utf-8")
        self.assertIsNone(self.get("/api/status")["key"]["problem"])

    def test_99_quit(self):
        self.assertEqual(self.call("/api/quit", {})[0], 200)
        self.assertEqual(self.proc.wait(15), 0)


if __name__ == "__main__":
    unittest.main()
