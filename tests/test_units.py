"""The small pieces on their own: the key file, the trusted folders, Claude Code's command line, the answer events."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ["API_CREDIT_CODE_HOME"] = tempfile.mkdtemp(prefix="acc-units-")  # app.py reads it on import

from api_credit_code import app, folders, keys  # noqa: E402
from api_credit_code import claude as cc  # noqa: E402

KEY = "sk-ant-api03-" + "A1b2_C3d4-" * 4 + "wxyz"


class Keys(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.env = os.environ.pop("ANTHROPIC_API_KEY", None)

    def tearDown(self):
        if self.env is not None:
            os.environ["ANTHROPIC_API_KEY"] = self.env
        self.tmp.cleanup()

    def test_save_load_delete(self):
        self.assertEqual(keys.load(self.home), (None, None))
        keys.save(self.home, KEY)
        keys.save(self.home, KEY)  # again, over the old file
        self.assertEqual(keys.load(self.home), (KEY, None))
        if os.name == "posix":
            self.assertEqual(keys.key_file(self.home).stat().st_mode & 0o777, 0o600)
        self.assertFalse(keys.key_file(self.home).with_name("key.txt.tmp").exists())
        keys.delete(self.home)
        keys.delete(self.home)  # twice is fine
        self.assertEqual(keys.load(self.home), (None, None))

    def test_any_editor_encoding(self):
        for data in ((KEY + "\r\n").encode("utf-8-sig"), f"  {KEY}  ".encode("utf-16"), f"key = {KEY}".encode(),
                     f'"{KEY}"\n\nmy work key\n'.encode(), f"{KEY}  # mine".encode(), f"{KEY}\n{KEY}\n".encode()):
            keys.key_file(self.home).write_bytes(data)
            self.assertEqual(keys.load(self.home), (KEY, None), data)

    def test_environment_is_not_used(self):
        os.environ["ANTHROPIC_API_KEY"] = KEY  # it may belong to an organization that pays by card
        try:
            self.assertEqual(keys.load(self.home), (None, None))
        finally:
            del os.environ["ANTHROPIC_API_KEY"]

    def test_file_problems(self):
        other = KEY.replace("wxyz", "abcd")
        cases = {
            b"": (None, "no API key in key.txt"),
            b"my key is in the Console": (None, "no API key in key.txt"),
            (KEY[:15] + " " + KEY[15:]).encode(): (None, "no API key in key.txt"),  # cut before it looks like a key
            f"{KEY}\n{other}\n".encode(): (KEY, "key.txt has 2 API keys. Using the first one, sk-ant-api03-...wxyz."),
            (KEY[:40] + " " + KEY[40:]).encode(): (KEY[:40], "cut in two"),
            (KEY[:40] + "\r\n" + KEY[40:]).encode(): (KEY[:40], "cut in two"),
        }
        for data, (key, words) in cases.items():
            keys.key_file(self.home).write_bytes(data)
            got, problem = keys.load(self.home)
            self.assertEqual(got, key, data)
            self.assertIn(words, problem or "", data)
        keys.key_file(self.home).unlink()
        keys.key_file(self.home).mkdir()  # there, but not a file that can be read
        got, problem = keys.load(self.home)
        self.assertIsNone(got)
        self.assertTrue(problem.startswith("Can't read key.txt ("), problem)

    def test_mask(self):
        self.assertEqual(keys.mask(KEY), "sk-ant-api03-...wxyz")
        self.assertEqual(keys.mask(None), "")
        self.assertNotIn(KEY[15:-4], keys.mask(KEY))

    def test_fake_check(self):
        os.environ["API_CREDIT_CODE_FAKE_CHECK"] = "1"
        try:
            self.assertEqual(keys.check("sk-ant-good")[0], "ok")
            self.assertEqual(keys.check("sk-ant-nocredit")[0], "nocredit")
            self.assertEqual(keys.check("sk-ant-other")[0], "bad")
        finally:
            del os.environ["API_CREDIT_CODE_FAKE_CHECK"]


class Folders(unittest.TestCase):
    def test_only_trusted_existing_folders(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            home, a, b, gone, no = t / "home", t / "a", t / "b", t / "gone", t / "no"
            for p in (home, a, b, no):
                p.mkdir()
            state = t / ".claude.json"
            state.write_text(json.dumps({"projects": {
                str(a): {"hasTrustDialogAccepted": True, "lastSessionModified": 10},
                str(b): {"hasTrustDialogAccepted": True, "lastStartTime": 20},
                str(gone): {"hasTrustDialogAccepted": True},
                str(no): {"hasTrustDialogAccepted": False},
                str(t / "c"): "junk",
            }}), encoding="utf-8")
            got = folders.trusted(state, home=home)
            self.assertEqual([f["path"] for f in got], [str(b), str(a), str(home)])
            self.assertEqual(got[-1]["name"], "~ (home)")
            self.assertEqual(got[0]["name"], "b")
            self.assertTrue(folders.allowed(str(a), got))
            self.assertFalse(folders.allowed(str(no), got))
            self.assertFalse(folders.allowed("", got))
            # a chat runs in the folder as it is listed, whatever spelling the request used
            self.assertEqual(folders.match(str(a) + os.sep + ".", got), str(a))
            self.assertIsNone(folders.match(str(no), got))

    def test_missing_or_broken_state_file(self):
        with tempfile.TemporaryDirectory() as t:
            home = Path(t)
            self.assertEqual(folders.trusted(home / "missing.json", home=home), [{"path": str(home), "name": "~ (home)"}])
            (home / "bad.json").write_text("{not json", encoding="utf-8")
            self.assertEqual(len(folders.trusted(home / "bad.json", home=home)), 1)


class CommandLine(unittest.TestCase):
    def args(self, mode, resume=False):
        return cc.build_args(["claude"], sid="abc", resume=resume, model="claude-haiku-5-5", effort="low",
                             budget=2, mode=mode)

    def test_modes(self):
        for mode in ("auto", "plan"):
            a = self.args(mode)
            self.assertEqual(a[a.index("--permission-mode") + 1], mode)
            self.assertEqual(a[a.index("--permission-prompts") + 1], "none")
            self.assertNotIn("--permission-prompt-tool", a)
        for mode in ("default", "acceptEdits"):
            a = self.args(mode)
            self.assertEqual(a[a.index("--permission-prompt-tool") + 1], "stdio")
            self.assertEqual(a[a.index("--disallowedTools") + 1], "AskUserQuestion")
            self.assertNotIn("--permission-prompts", a)

    def test_plan_prompt(self):
        for mode, said in (("plan", True), ("auto", False)):
            a = self.args(mode)
            self.assertEqual("ExitPlanMode" in a[a.index("--append-system-prompt") + 1], said)

    def test_session_and_budget(self):
        a = self.args("auto")
        self.assertEqual(a[-2:], ["--session-id", "abc"])
        self.assertEqual(self.args("auto", resume=True)[-2:], ["--resume", "abc"])
        self.assertEqual(a[a.index("--max-budget-usd") + 1], "2.00")
        self.assertEqual(a[:2], ["claude", "-p"])
        self.assertNotIn("--continue", a)

    def test_child_env(self):
        saved = dict(os.environ)
        os.environ.update(ANTHROPIC_AUTH_TOKEN="t", CLAUDE_CODE_USE_BEDROCK="1", CLAUDECODE="1",
                          CLAUDE_CODE_SESSION_ID="x", CLAUDE_CODE_BRIDGE_URL="u", HOME_SAFE="kept",
                          CLAUDE_CODE_SUBPROCESS_ENV_SCRUB="1", ANTHROPIC_BASE_URL="https://gateway.example")
        try:
            env = cc.child_env(KEY)
        finally:
            os.environ.clear()
            os.environ.update(saved)
        self.assertEqual(env["ANTHROPIC_API_KEY"], KEY)
        self.assertEqual(env["HOME_SAFE"], "kept")
        for k in ("ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK", "CLAUDECODE", "CLAUDE_CODE_SESSION_ID",
                  "CLAUDE_CODE_BRIDGE_URL", "CLAUDE_CODE_SUBPROCESS_ENV_SCRUB", "ANTHROPIC_BASE_URL"):
            self.assertNotIn(k, env)

    def test_find_override(self):
        os.environ["API_CREDIT_CODE_CLAUDE"] = json.dumps(["python", "fake.py"])
        try:
            self.assertEqual(cc.find(), ["python", "fake.py"])
        finally:
            del os.environ["API_CREDIT_CODE_CLAUDE"]


class Events(unittest.TestCase):
    def bot(self, mode="auto"):
        return {"role": "bot", "status": "running", "parts": [], "mode": mode, "budget": 1}

    def feed(self, bot, *raw):
        for ev in raw:
            for out in app.translate(ev):
                app.apply(bot, out)

    def test_text_tools_result(self):
        bot = self.bot()
        delta = lambda s: {"type": "stream_event", "parent_tool_use_id": None,  # noqa: E731
                           "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": s}}}
        start = {"type": "stream_event", "parent_tool_use_id": None, "event": {"type": "message_start"}}
        tool = {"type": "assistant", "parent_tool_use_id": None,
                "message": {"content": [{"type": "tool_use", "name": "Read", "input": {"file_path": "a.py"}}]}}
        self.feed(bot, {"type": "system", "subtype": "init", "model": "m", "permissionMode": "plan",
                        "apiKeySource": "ANTHROPIC_API_KEY"},
                  start, delta("One"), delta(" two"), tool, start, delta("Three"),
                  {"type": "result", "subtype": "success", "is_error": False, "result": "Three",
                   "total_cost_usd": 0.5, "duration_ms": 2500, "permission_denials": [{}]})
        self.assertEqual(bot["status"], "ok")
        self.assertEqual(bot["text"], "One two\n\nThree")
        self.assertEqual([p["k"] for p in bot["parts"]], ["text", "tools", "text"])
        self.assertEqual(bot["parts"][1]["items"][0]["detail"], "a.py")
        self.assertEqual((bot["cost"], bot["seconds"], bot["blocked"]), (0.5, 2, 1))
        self.assertIn("Plan", bot["notice"])  # it ran in another mode than the one asked for
        self.assertNotIn("warn", bot)

    def test_manual_is_default(self):
        bot = self.bot("default")
        self.feed(bot, {"type": "system", "subtype": "init", "permissionMode": "manual",
                        "apiKeySource": "ANTHROPIC_API_KEY"})
        self.assertNotIn("notice", bot)
        self.feed(bot, {"type": "system", "subtype": "init", "permissionMode": "auto",
                        "apiKeySource": "ANTHROPIC_API_KEY"})
        self.assertIn("Auto", bot["notice"])

    def test_not_billed_to_the_key(self):
        bot = self.bot()
        self.feed(bot, {"type": "system", "subtype": "init", "permissionMode": "auto", "apiKeySource": "none"})
        self.assertIn("NOT billed", bot["warn"])

    def test_budget_stop(self):
        bot = self.bot()
        self.feed(bot, {"type": "result", "subtype": "error_max_budget_usd", "is_error": True, "total_cost_usd": 1})
        self.assertEqual(bot["status"], "error")
        self.assertIn("Max $", bot["error"])

    def test_asks(self):
        bot = self.bot("default")
        app.apply(bot, {"t": "ask", "id": "r1", "tool": "Bash", "title": "Run a command", "detail": "ls"})
        app.apply(bot, {"t": "ask", "id": "r2", "tool": "Edit", "title": "Edit a file", "detail": "a.py"})
        self.assertEqual(bot["phase"], "ask")
        app.apply(bot, {"t": "answered", "id": "r1", "state": "allowed"})
        self.assertEqual(bot["phase"], "ask")  # r2 still waits
        app.apply(bot, {"t": "error", "msg": "gone"})
        self.assertEqual([p["state"] for p in bot["parts"]], ["allowed", "expired"])

    def test_ask_detail(self):
        self.assertEqual(app.ask_detail("Bash", {"command": " rm -rf build "}), "rm -rf build")
        self.assertEqual(app.ask_detail("Grep", {"pattern": "TODO", "path": "src"}), "TODO   in src")
        self.assertEqual(json.loads(app.ask_detail("X", {"a": 1})), {"a": 1})

    def test_titles(self):
        self.assertEqual(app.make_title("  short  "), "short")
        long = app.make_title("word " * 30)
        self.assertTrue(long.endswith("…") and len(long) <= 51)

    def test_pictures_are_checked(self):
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 10
        import base64
        ok = app.decode_images([{"type": "image/png", "data": base64.b64encode(png).decode(), "w": 3, "h": "x"}])
        self.assertEqual((ok[0]["ext"], ok[0]["w"], "h" in ok[0]), (".png", 3, False))
        for bad in ([{"type": "image/gif", "data": "R0lG"}], [{"type": "image/png", "data": "!!"}],
                    [{"type": "image/jpeg", "data": base64.b64encode(png).decode()}], "nope"):
            with self.assertRaises(ValueError):
                app.decode_images(bad)


class Ports(unittest.TestCase):
    def test_answers(self):
        import socket
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen()
            port = s.getsockname()[1]
            self.assertTrue(app.answers(port))  # another program on the port: the app moves on
        servers, port = app.bind(0)  # a port nobody listens on any more
        for srv in servers:
            srv.server_close()
        if sys.platform != "win32":  # (Windows takes 2 s to refuse a connection: the app doesn't ask there)
            self.assertFalse(app.answers(port))

    def test_quiet_when_the_page_goes_away(self):
        import io
        from contextlib import redirect_stderr
        servers, _ = app.bind(0)
        try:
            for exc, quiet in ((BrokenPipeError(), True), (ConnectionResetError(), True), (ValueError("x"), False)):
                err = io.StringIO()
                with redirect_stderr(err):
                    try:
                        raise exc
                    except Exception:
                        servers[0].handle_error(None, ("127.0.0.1", 1))
                self.assertEqual(err.getvalue() == "", quiet, err.getvalue()[:200])
        finally:
            for srv in servers:
                srv.server_close()


if __name__ == "__main__":
    unittest.main()
