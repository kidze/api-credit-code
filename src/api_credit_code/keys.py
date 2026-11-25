"""Your Anthropic API key.

It is kept in key.txt in this app's folder in your user profile, and it only ever goes to Anthropic: to check it
when you paste it, and to Claude Code, which uses it for every message. The page never gets it back in full.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

KEY_RE = re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")
API = "https://api.anthropic.com"
CHECK_MODEL = "claude-haiku-5-5"  # the cheapest model: the check's one-token call costs a tiny fraction of a cent

CREDITS_HELP = ("Claim your monthly API credits at claude.ai > Settings > Billing, and make the key in the "
                "Console organization that gets them.")
WORKSPACE_HELP = ("This key isn't tied to a workspace, so Claude Code can't use it. Make a new key and pick the "
                  "Default workspace.")


def key_file(home):
    return home / "key.txt"


def load(home):
    """(key, where) for the key to use: key.txt, else ANTHROPIC_API_KEY from the environment, else (None, None).

    key.txt is read whatever an editor saved it as (UTF-8 with or without a BOM, or UTF-16), and only the key is
    taken from it, so a stray space or line break doesn't matter.
    """
    try:
        data = key_file(home).read_bytes()
    except OSError:
        data = b""
    for enc in ("utf-8-sig", "utf-16"):
        found = KEY_RE.search(data.decode(enc, errors="ignore"))
        if found:
            return found.group(0), "file"
    found = KEY_RE.search(os.environ.get("ANTHROPIC_API_KEY", ""))
    if found:
        return found.group(0), "environment"
    return None, None


def save(home, key):
    """Write the key to key.txt, readable by your user account only."""
    home.mkdir(parents=True, exist_ok=True)
    path = key_file(home)
    tmp = path.with_name("key.txt.tmp")
    tmp.write_text(key + "\n", encoding="utf-8")
    if sys.platform != "win32":  # on Windows the profile folder is already private to its user
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def delete(home):
    try:
        key_file(home).unlink()
    except FileNotFoundError:
        pass


def mask(key):
    """sk-ant-api03-...abcd: the part that isn't secret, and the last four characters to tell keys apart."""
    if not key:
        return ""
    kind = re.match(r"sk-ant-[a-z]+\d*-", key)
    return (kind.group(0) if kind else "sk-ant-") + "..." + key[-4:]


def _request(path, key, body=None, timeout=20):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(API + path, data=data, method="POST" if data else "GET",
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.status


def _error(e):
    try:
        return json.loads(e.read())["error"]["message"]
    except (ValueError, KeyError, TypeError, OSError):
        return f"HTTP {e.code}"


def check(key):
    """Ask Anthropic whether the key works and has credits to spend.

    Returns (status, message). status: "ok"; "bad" (Anthropic refuses the key: don't save it); "nocredit" (the key
    works but its organization has nothing to spend); "unknown" (Anthropic couldn't be asked; save it anyway).
    """
    if os.environ.get("API_CREDIT_CODE_FAKE_CHECK"):  # the tests: no network, no real key
        if "nocredit" in key:
            return "nocredit", "This key works, but its organization has no credits. " + CREDITS_HELP
        return ("ok", "") if "good" in key else ("bad", "Anthropic didn't accept this key.")
    try:
        _request("/v1/models?limit=1", key)  # free: is the key real?
    except urllib.error.HTTPError as e:
        why = _error(e)
        if "workspace" in why.lower():
            return "bad", WORKSPACE_HELP + f" (Anthropic says: {why})"
        if e.code in (401, 403):
            return "bad", ("Anthropic didn't accept this key. Copy it again from the Console, or make a new one. "
                           f"(Anthropic says: {why})")
        return "unknown", f"Anthropic couldn't check the key right now ({why}). It was saved anyway."
    except (OSError, ValueError) as e:
        return "unknown", f"Couldn't reach Anthropic to check the key ({e.__class__.__name__}). It was saved anyway."
    try:  # one token: can the key spend? This is where "credit balance too low" shows up.
        _request("/v1/messages", key, {"model": CHECK_MODEL, "max_tokens": 1,
                                       "messages": [{"role": "user", "content": "Hi"}]})
    except urllib.error.HTTPError as e:
        why = _error(e)
        if "credit balance" in why.lower():
            return "nocredit", "This key works, but its organization has no credits to spend. " + CREDITS_HELP
        if "workspace" in why.lower():
            return "bad", WORKSPACE_HELP + f" (Anthropic says: {why})"
        if e.code in (401, 403):
            return "bad", f"Anthropic didn't accept this key for messages. (Anthropic says: {why})"
        if e.code in (400, 404, 429, 500, 529):  # busy, rate-limited or a model hiccup: the key itself is fine
            return "ok", ""
        return "unknown", f"Anthropic couldn't fully check the key ({why}). It was saved anyway."
    except (OSError, ValueError) as e:
        return "unknown", f"Couldn't reach Anthropic to check the key ({e.__class__.__name__}). It was saved anyway."
    return "ok", ""
