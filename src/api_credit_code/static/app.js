(() => {
  "use strict";

  let TOKEN = document.querySelector('meta[name="token"]').content; // replaced by freshToken() after the app restarts
  const PREFS = "api-credit-code.prefs";
  const MODEL_NAMES = {
    "claude-fable-5-2": "Fable 5.2",
    "claude-fable-5-1": "Fable 5.1",
    "claude-opus-5-5": "Opus 5.5",
    "claude-sonnet-5-5": "Sonnet 5.5",
    "claude-haiku-5-5": "Haiku 5.5",
  };
  const EFFORTS = ["low", "medium", "high", "xhigh", "max"];
  const MODE_NAMES = { auto: "Auto", default: "Manual", acceptEdits: "Accept edits", plan: "Plan" };
  const MODE_TIPS = {
    auto: "Claude handles permission decisions",
    default: "Always ask before making changes",
    acceptEdits: "Automatically accept all file edits",
    plan: "Create a plan before making changes",
  };
  const HOST_MODES = ["default", "acceptEdits"];
  const THEMES = ["auto", "light", "dark"];
  const OFFLINE = "Can't reach API Credit Code. Is it still running? Open it again from its icon.";
  const ASK_STATES = { allowed: "Allowed", denied: "Denied", expired: "No answer", cancelled: "Withdrawn", stopped: "Stopped" };

  const svg = (body, cls = "ico") => `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true">${body}</svg>`;
  const ICON = {
    search: svg('<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>'),
    globe: svg('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>'),
    terminal: svg('<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M13 15h4"/>'),
    file: svg('<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>'),
    pencil: svg('<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>'),
    agent: svg('<path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/>'),
    star: svg('<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>'),
    list: svg('<path d="M10 6h10M10 12h10M10 18h10M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2"/>'),
    tool: svg('<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-.6-.6-2.4z"/>'),
    copy: svg('<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>'),
    check: svg('<path d="m5 12 5 5 9-10"/>'),
    up: svg('<path d="M12 19V5M5 12l7-7 7 7"/>'),
    down: svg('<path d="M12 5v14M5 12l7 7 7-7"/>'),
    stop: svg('<rect x="6.5" y="6.5" width="11" height="11" rx="2"/>', "ico fill"),
    panel: svg('<rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M9.5 4v16"/>'),
    plus: svg('<path d="M12 5v14M5 12h14"/>'),
    x: svg('<path d="M6 6l12 12M18 6 6 18"/>'),
    chev: svg('<path d="m9 6 6 6-6 6"/>', "ico chev"),
    monitor: svg('<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>'),
    sun: svg('<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>'),
    moon: svg('<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>'),
    shield: svg('<path d="M12 3 4 6v6c0 4.5 3.4 8.3 8 9 4.6-.7 8-4.5 8-9V6z"/>'),
  };

  const many = (one, word) => ({ done: one, many: (n) => `${word} ${n} times` });
  const TOOLS = {
    WebSearch: { icon: "search", active: "Searching the web", ...many("Searched the web", "Searched the web") },
    WebFetch: { icon: "globe", active: "Reading", done: "Read a page", many: (n) => `Read ${n} pages` },
    Bash: { icon: "terminal", active: "Running", done: "Ran a command", many: (n) => `Ran ${n} commands` },
    PowerShell: { icon: "terminal", active: "Running", done: "Ran a command", many: (n) => `Ran ${n} commands` },
    Read: { icon: "file", active: "Reading", done: "Read a file", many: (n) => `Read ${n} files` },
    Write: { icon: "pencil", active: "Writing", done: "Wrote a file", many: (n) => `Wrote ${n} files` },
    Edit: { icon: "pencil", active: "Editing", done: "Edited a file", many: (n) => `Edited ${n} files` },
    MultiEdit: { icon: "pencil", active: "Editing", done: "Edited a file", many: (n) => `Edited ${n} files` },
    NotebookEdit: { icon: "pencil", active: "Editing", done: "Edited a notebook", many: (n) => `Edited ${n} notebooks` },
    Grep: { icon: "search", active: "Searching files", ...many("Searched files", "Searched files") },
    Glob: { icon: "search", active: "Listing files", ...many("Listed files", "Listed files") },
    Agent: { icon: "agent", active: "Helper agent working", done: "Used a helper agent", many: (n) => `Used ${n} helper agents` },
    Task: { icon: "agent", active: "Helper agent working", done: "Used a helper agent", many: (n) => `Used ${n} helper agents` },
    Skill: { icon: "star", active: "Using a skill", done: "Used a skill", many: (n) => `Used ${n} skills` },
    ToolSearch: { icon: "search", active: "Finding the right tool", done: "Looked up a tool", many: (n) => `Looked up tools ${n} times` },
    TodoWrite: { icon: "list", active: "Planning", done: "Updated its plan", many: () => "Updated its plan" },
  };
  const toolInfo = (name) => TOOLS[name] || { icon: "tool", active: "Using " + name, done: name, many: (n) => `${name} ×${n}` };

  const CHIPS = [
    { icon: "file", label: "Explain this project", text: "Look around this folder and explain what's in it: what it does, how it's organized, and where to start." },
    { icon: "search", label: "Find bugs", text: "Look for bugs in this project and list the most likely ones, with the file and line for each." },
    { icon: "list", label: "Plan a change", text: "Help me plan this change: " },
    { icon: "terminal", label: "What changed lately?", text: "Summarize what changed in this project recently, from git log and git diff." },
  ];

  const $ = (id) => document.getElementById(id);
  const el = {
    app: $("app"), main: $("main"), chats: $("chats"), spent: $("spent"), newChat: $("newChat"),
    sideOpen: $("sideOpen"), sideClose: $("sideClose"), scrim: $("scrim"), themeBtn: $("themeBtn"), quitBtn: $("quitBtn"),
    title: $("chatTitle"), keyPill: $("keyPill"), keyText: $("keyText"),
    model: $("model"), effort: $("effort"), budget: $("budget"), mode: $("mode"), folder: $("folder"), folderPill: $("folderPill"),
    log: $("log"), msgs: $("msgs"), composer: $("composer"), input: $("input"), send: $("send"), toBottom: $("toBottom"),
    chips: $("chips"), greetText: $("greetText"), toast: $("toast"),
    attach: $("attach"), file: $("file"), strip: $("strip"), sendNote: $("sendNote"),
    setup: $("setup"), claudeMissing: $("claudeMissing"), installCmd: $("installCmd"), keyForm: $("keyForm"),
    keyInput: $("keyInput"), keySave: $("keySave"), keyMsg: $("keyMsg"), keyCurrent: $("keyCurrent"),
    keyCurrentText: $("keyCurrentText"), keyRemove: $("keyRemove"), keyClose: $("keyClose"),
    keyProblem: $("keyProblem"), keyFile: $("keyFile"),
  };

  DOMPurify.addHook("afterSanitizeAttributes", (n) => {
    if (n.tagName === "A") {
      n.setAttribute("target", "_blank");
      n.setAttribute("rel", "noopener noreferrer");
    }
  });

  // marked strikes through text between single tildes, so "~$5 (~$6)" would lose "$5 (~". Only ~~double~~ should.
  marked.use({
    tokenizer: {
      del(src) {
        const m = /^~~(?=\S)([\s\S]*?\S)~~/.exec(src);
        if (m) return { type: "del", raw: m[0], text: m[1], tokens: this.lexer.inlineTokens(m[1]) };
        if (src.startsWith("~")) return { type: "text", raw: "~", text: "~" };
        return false;
      },
    },
  });

  function markdown(text) {
    try {
      return DOMPurify.sanitize(marked.parse(text || ""));
    } catch {
      const d = document.createElement("div");
      d.textContent = text;
      return d.innerHTML;
    }
  }

  // Per-browser settings only; the browser may refuse storage, and the page still works without it.
  function read(key, fallback) {
    try {
      const v = JSON.parse(localStorage.getItem(key));
      return v ?? fallback;
    } catch {
      return fallback;
    }
  }
  function write(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // nothing to do: the setting just won't be remembered
    }
  }

  const prefs = Object.assign({ model: null, effort: null, mode: "auto", folder: null, budget: 5, theme: "auto" }, read(PREFS, {}));
  let status = null;      // what the app says about itself: Claude Code, the key, the folders
  let list = [];          // every chat, newest first: {id, title, updated, cost, running}
  let current = null;     // the open chat as the app sent it: {chat, running, cursor}; null for a new chat
  const live = new Map(); // chat id -> {id, bot, abort} while this page is streaming its answer
  const nodes = new WeakMap(); // bot message -> its element
  let toastTimer = 0;
  let editing = null;     // {id, finish} while a chat's name is being typed
  let pending = [];       // pictures waiting in the entry box: {blob, type, w, h, url}
  let sending = false;    // a message (with its pictures) is on its way to the app
  let setupOpen = false;  // the key screen was opened from the key button

  const currentId = () => (current ? current.chat.id : null);
  const isRunning = () => !!current && !!current.running;

  // ---------- talking to the app ----------
  // When the app restarts it hands pages a new key. Only this site's own pages can read it from the page itself, so
  // fetching it again is as safe as the first load, and nothing needs a reload (nothing typed is lost).
  async function freshToken() {
    try {
      const m = (await (await fetch("/", { cache: "no-store" })).text()).match(/name="token" content="([^"]+)"/);
      if (m && m[1] !== TOKEN) {
        TOKEN = m[1];
        return true;
      }
    } catch {
      // the app is still starting; the caller tries again later
    }
    return false;
  }

  async function api(path, body, retried) {
    let res;
    try {
      res = await fetch(path, body === undefined
        ? { headers: { "X-Token": TOKEN } }
        : { method: "POST", headers: { "Content-Type": "application/json", "X-Token": TOKEN }, body: JSON.stringify(body) });
    } catch {
      throw new Error(OFFLINE);
    }
    if (res.status === 403 && !retried && (await freshToken())) return api(path, body, true);
    if (!res.ok) throw new Error(await problem(res));
    return res;
  }
  const apiJson = async (path, body) => (await api(path, body)).json();

  async function problem(res) {
    if (res.status === 403) return "This page is out of date because the app was restarted. Reload it, then try again.";
    const text = await res.text().catch(() => "");
    if (res.status === 409 && !text) return "This chat is still answering. Stop it first, or wait for it to finish.";
    return text || `The app answered with error ${res.status}.`;
  }

  function toast(msg) {
    el.toast.textContent = msg;
    el.toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (el.toast.hidden = true), 7000);
  }

  // ---------- small helpers ----------
  function uuid() {
    if (crypto.randomUUID) return crypto.randomUUID();
    const b = crypto.getRandomValues(new Uint8Array(16));
    b[6] = (b[6] & 15) | 64;
    b[8] = (b[8] & 63) | 128;
    const h = [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
  }
  const fmtCost = (v) => (v > 0 && v < 0.01 ? "<$0.01" : "$" + (v || 0).toFixed(2));
  const fmtTime = (s) => (s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`);
  function node(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function button(cls, text, onClick) {
    const b = node("button", cls, text);
    b.type = "button";
    if (onClick) b.addEventListener("click", onClick);
    return b;
  }
  function iconNode(name) {
    const t = document.createElement("template");
    t.innerHTML = ICON[name];
    return t.content.firstChild;
  }
  async function copyText(text) {
    if (navigator.clipboard) return navigator.clipboard.writeText(text);
    const t = document.createElement("textarea");
    t.value = text;
    t.style.position = "fixed";
    t.style.opacity = "0";
    document.body.append(t);
    t.focus();
    t.select();
    try {
      if (!document.execCommand("copy")) throw new Error("copy refused");
    } finally {
      t.remove();
    }
  }
  function copyButton(getText, label) {
    const b = button("copy-btn");
    b.title = "Copy";
    const show = (icon, text) => {
      b.textContent = "";
      b.append(iconNode(icon));
      if (text) b.append(node("span", null, text));
    };
    show("copy", label);
    b.addEventListener("click", async () => {
      try {
        await copyText(getText());
        show("check", label && "Copied");
      } catch {
        show("x", label && "Couldn't copy");
      }
      setTimeout(() => show("copy", label), 1500);
    });
    return b;
  }
  function greeting() {
    const h = new Date().getHours();
    return h >= 5 && h < 12 ? "Good morning" : h >= 12 && h < 18 ? "Good afternoon" : "Good evening";
  }

  // ---------- pictures ----------
  // A picture goes to Claude inside the message. The page first fits it into what Claude actually sees (1568 px on
  // the long side; the API scales anything bigger down anyway) by redrawing it on a canvas: less to upload, and a
  // photo's hidden details (where it was taken) stay behind.
  const MAX_IMAGES = 8;
  const MAX_EDGE = 1568;

  function picturesEl(sid, images) {
    const d = node("div", "pics");
    images.forEach((im, i) => {
      const a = node("a", "pic");
      a.href = `/files/${sid}/${im.name}`;
      a.target = "_blank";
      a.rel = "noopener";
      a.title = "Open full size";
      const img = node("img");
      img.src = a.href;
      img.alt = `Picture ${i + 1}`;
      img.loading = "lazy";
      if (im.w && im.h) { // the right shape before it loads, so the chat doesn't jump
        img.width = im.w;
        img.height = im.h;
      }
      a.append(img);
      d.append(a);
    });
    return d;
  }

  // The image files in a paste or drop (a pasted screenshot arrives as a file too).
  function imageFiles(dt) {
    const out = [];
    for (const f of (dt && dt.files) || []) if (f.type.startsWith("image/")) out.push(f);
    if (!out.length) {
      for (const it of (dt && dt.items) || []) {
        const f = it.kind === "file" && it.type.startsWith("image/") && it.getAsFile();
        if (f) out.push(f);
      }
    }
    return out;
  }
  const hasFiles = (dt) => !!dt && [...dt.types].includes("Files");

  function loadImage(file) {
    return new Promise((ok, fail) => {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        URL.revokeObjectURL(url);
        ok(img);
      };
      img.onerror = () => {
        URL.revokeObjectURL(url);
        fail(new Error("not a picture this browser can read"));
      };
      img.src = url;
    });
  }
  const toBlob = (canvas, type, quality) =>
    new Promise((ok, fail) => canvas.toBlob((b) => (b ? ok(b) : fail(new Error("couldn't encode"))), type, quality));

  async function shrink(file) {
    const img = await loadImage(file);
    const scale = Math.min(1, MAX_EDGE / Math.max(img.naturalWidth, img.naturalHeight));
    const w = Math.max(1, Math.round(img.naturalWidth * scale));
    const h = Math.max(1, Math.round(img.naturalHeight * scale));
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    canvas.getContext("2d").drawImage(img, 0, 0, w, h);
    const photo = /jpe?g|hei[cf]/i.test(file.type); // photos stay JPEG; screenshots stay PNG so small text keeps its edges
    let blob = await toBlob(canvas, photo ? "image/jpeg" : "image/png", 0.9);
    if (!photo && blob.size > 2000000) blob = await toBlob(canvas, "image/jpeg", 0.92); // a photo that was saved as PNG
    return { blob, type: blob.type, w, h, url: URL.createObjectURL(blob) };
  }

  async function addImages(files) {
    if (!files.length) return;
    if (sending) {
      toast("One moment: the last message is still being sent.");
      return;
    }
    const room = Math.max(0, MAX_IMAGES - pending.length);
    if (files.length > room) toast(`Up to ${MAX_IMAGES} pictures in one message${room ? `; the first ${room} were kept` : ""}.`);
    for (const f of files.slice(0, room)) {
      try {
        pending.push(await shrink(f));
      } catch {
        toast(`Couldn't read ${f.name || "that picture"}.`);
      }
    }
    renderStrip();
    syncComposer();
    if (!touch()) el.input.focus();
  }

  function renderStrip() {
    el.strip.textContent = "";
    el.strip.hidden = !pending.length;
    pending.forEach((p, i) => {
      const t = node("div", "thumb");
      const img = node("img");
      img.src = p.url;
      img.alt = `Picture ${i + 1}`;
      const x = button("thumb-x", null, () => {
        if (sending) return;
        URL.revokeObjectURL(p.url);
        pending.splice(i, 1);
        renderStrip();
        syncComposer();
      });
      x.title = "Remove";
      x.setAttribute("aria-label", "Remove this picture");
      x.append(iconNode("x"));
      t.append(img, x);
      el.strip.append(t);
    });
  }

  function clearPending() {
    for (const p of pending) URL.revokeObjectURL(p.url);
    pending = [];
    renderStrip();
  }

  const base64 = (blob) =>
    new Promise((ok, fail) => {
      const r = new FileReader();
      r.onload = () => ok(r.result.slice(r.result.indexOf(",") + 1));
      r.onerror = () => fail(new Error("couldn't read the picture"));
      r.readAsDataURL(blob);
    });

  // ---------- the key screen ----------
  const installCommand = (platform) => platform === "win32"
    ? "irm https://claude.ai/install.ps1 | iex"
    : "curl -fsSL https://claude.ai/install.sh | bash";

  function renderSetup() {
    const s = status;
    const needClaude = !!s && !s.claude.found;
    const needKey = !!s && !s.key.set;
    const show = !!s && (needClaude || needKey || setupOpen);
    el.setup.hidden = !show;
    el.main.classList.toggle("setup-on", show);
    if (!s) return;
    el.claudeMissing.hidden = !needClaude;
    el.installCmd.textContent = installCommand(s.platform);
    // What's wrong with key.txt, if anything: no key to use (red), or a key to use but a file to look at (amber).
    const k = s.key;
    el.keyProblem.textContent = k.problem || "";
    el.keyProblem.className = "key-msg " + (k.set ? "warn" : "bad");
    el.keyProblem.hidden = !k.problem;
    el.keyCurrent.hidden = !k.set && !k.problem; // no file yet: nothing to show
    el.keyCurrentText.hidden = !k.set;
    el.keyCurrentText.textContent = k.set ? `Using ${k.masked}.` : "";
    el.keyFile.textContent = k.file;
    el.keyRemove.hidden = el.keyClose.hidden = !k.set;
    if (show && !needClaude && !touch() && document.activeElement !== el.keyInput) setTimeout(() => el.keyInput.focus(), 0);
    // the key button in the corner
    el.keyPill.className = "keypill " + (!k.set ? "bad" : k.problem ? "warn" : "ok");
    el.keyText.textContent = k.set ? k.masked.replace(/^sk-ant-[a-z]+\d*-/, "key ") : "No API key";
    el.keyPill.title = !k.set ? k.problem || "Add your Anthropic API key"
      : k.problem ? `${k.problem} Click to see the key.`
      : `Claude Code runs on this API key (${k.masked}). Its use is billed to the key's Console organization. Click to change the key.`;
  }

  function keyMessage(text, kind) {
    el.keyMsg.textContent = text || "";
    el.keyMsg.className = "key-msg " + (kind || "");
    el.keyMsg.hidden = !text;
  }

  async function saveKey() {
    const key = el.keyInput.value.trim();
    if (!key) {
      keyMessage("Paste your key first. It starts with sk-ant-.", "bad");
      return;
    }
    el.keySave.disabled = true;
    keyMessage("Checking the key with Anthropic…", "");
    try {
      const r = await apiJson("/api/key", { key });
      status.key = r.key;
      if (!r.ok) {
        keyMessage(r.message, "bad");
        return;
      }
      el.keyInput.value = "";
      if (r.status === "ok") {
        keyMessage("", "");
        setupOpen = false;
        toast("Key saved. You're ready to go.");
      } else {
        setupOpen = true; // saved, but with something to know (no credits, or not checked): keep it on screen
        keyMessage(r.message, "warn");
      }
      renderSetup();
      syncComposer();
      if (!setupOpen && !touch()) el.input.focus();
    } catch (e) {
      keyMessage(e.message, "bad");
    } finally {
      el.keySave.disabled = false;
    }
  }

  async function removeKey() {
    if (!confirm("Remove the saved API key from this computer?")) return;
    try {
      const r = await apiJson("/api/key/delete", {});
      status.key = r.key;
      renderSetup();
      syncComposer();
    } catch (e) {
      toast(e.message);
    }
  }

  // ---------- rendering ----------
  function renderAll() {
    renderSidebar();
    renderChat();
    syncComposer();
  }

  function renderSidebar() {
    el.chats.textContent = "";
    for (const c of list) {
      const item = node("div", "chat-item" + (c.id === currentId() ? " active" : ""));
      item.tabIndex = 0;
      item.title = c.title;
      if (c.running) item.append(node("span", "live-dot"));
      item.append(node("span", "name", c.title || "Untitled"), node("span", "cost", fmtCost(c.cost)));
      const ren = button("ren", null, (e) => {
        e.stopPropagation();
        renameChat(c.id);
      });
      ren.title = "Rename";
      ren.append(iconNode("pencil"));
      const del = button("del", null, (e) => {
        e.stopPropagation();
        removeChat(c);
      });
      del.title = "Delete this chat";
      del.append(iconNode("x"));
      item.append(ren, del);
      item.addEventListener("click", () => openChat(c.id));
      item.addEventListener("keydown", (e) => e.key === "Enter" && openChat(c.id));
      el.chats.append(item);
    }
    const total = list.reduce((a, c) => a + (c.cost || 0), 0);
    el.spent.textContent = list.length ? `Spent in these chats: ${fmtCost(total)}` : "Your chats will be listed here.";
  }

  function renderChat() {
    const chat = current && current.chat;
    history.replaceState(null, "", chat ? `#${chat.id}` : location.pathname); // a reload reopens this chat
    const empty = !chat || !chat.messages.length;
    el.main.classList.toggle("empty", empty);
    if (editing && editing.id !== (chat && chat.id)) editing.finish(true); // left the chat: keep the typed name
    if (!editing) { // an answer finishing mustn't wipe a name being typed
      el.title.textContent = chat ? chat.title : "";
      el.title.title = chat ? `${chat.folder}\nClick to rename` : "";
    }
    renderFolder();
    el.msgs.textContent = "";
    if (empty) {
      el.greetText.textContent = greeting();
      updateToBottom();
      return;
    }
    const lastBot = [...chat.messages].reverse().find((m) => m.role === "bot");
    for (const m of chat.messages) {
      const n = node("div", "msg " + m.role);
      if (m.role === "user") {
        if (m.images && m.images.length) n.append(picturesEl(chat.id, m.images));
        if (m.text) n.append(node("div", "bubble", m.text));
      } else {
        m.isLast = m === lastBot;
        nodes.set(m, n);
        fillBot(n, m);
      }
      el.msgs.append(n);
    }
    scrollToEnd();
  }

  function fillBot(n, m) {
    n.textContent = "";
    if (m.notice) n.append(node("div", "notice", m.notice));
    if (m.warn) n.append(node("div", "notice warn", "⚠ " + m.warn));
    if (m.keywarn) n.append(node("div", "notice warn", "⚠ " + m.keywarn));
    const parts = m.parts || (m.text ? [{ k: "text", s: m.text }] : []);
    for (const p of parts) {
      if (p.k === "tools") {
        n.append(toolsEl(p));
      } else if (p.k === "ask") {
        n.append(askEl(p, m));
      } else if (p.s.trim()) {
        const d = node("div", "md");
        d.innerHTML = markdown(p.s);
        enhance(d);
        n.append(d);
      }
    }
    if (m.status === "running") n.append(activityEl(m));
    if (m.error) n.append(node("div", "error", m.error));
    if (m.note) n.append(node("div", "notice", m.note));
    if (m.status !== "running") n.append(actionsEl(m));
    if (m.mode === "plan" && m.status === "ok" && m.isLast) n.append(planEl());
  }

  // Code blocks get a header with the language and a copy button; tables scroll sideways in a frame.
  function enhance(d) {
    for (const pre of d.querySelectorAll("pre")) {
      const code = pre.querySelector("code");
      const lang = ((code && code.className.match(/language-([\w+#.-]+)/)) || [])[1] || "code";
      const box = node("div", "codeblock");
      const head = node("div", "code-head");
      head.append(node("span", null, lang), copyButton(() => (code || pre).textContent, "Copy"));
      pre.replaceWith(box);
      box.append(head, pre);
    }
    for (const table of d.querySelectorAll("table")) {
      const wrap = node("div", "table-wrap");
      table.replaceWith(wrap);
      wrap.append(table);
      const cols = table.rows[0] ? table.rows[0].cells.length : 0;
      if (cols > 2) table.style.minWidth = `${cols * 7.5}em`;
    }
  }

  function toolsSummary(items) {
    const groups = new Map();
    for (const it of items) {
      const info = toolInfo(it.name);
      const g = groups.get(info.done) || { info, n: 0 };
      g.n += 1;
      groups.set(info.done, g);
    }
    return [...groups.values()].map((g) => (g.n === 1 ? g.info.done : g.info.many(g.n))).join(" · ");
  }

  function toolsEl(p) {
    const d = node("details", "tools");
    d.open = !!p.open;
    d.addEventListener("toggle", () => (p.open = d.open));
    const s = node("summary");
    s.append(iconNode(toolInfo(p.items[0].name).icon), node("span", "tsum", toolsSummary(p.items)), iconNode("chev"));
    const ol = node("ol", "tlist");
    for (const it of p.items) {
      const info = toolInfo(it.name);
      const li = node("li");
      li.append(iconNode(info.icon), node("span", "tname", info.done));
      if (it.sub) li.append(node("span", "sub-tag", "helper"));
      if (it.detail) li.append(node("span", "tdetail", it.detail));
      ol.append(li);
    }
    d.append(s, ol);
    return d;
  }

  // Manual and Accept edits: Claude asks before it acts, and the answer goes back from here.
  function askEl(p, m) {
    const d = node("div", "ask " + p.state);
    const head = node("div", "ask-head");
    head.append(iconNode("shield"), node("span", "ask-title", p.title));
    d.append(head);
    if (p.detail) d.append(node("pre", "ask-detail", p.detail));
    if (p.reason) d.append(node("div", "ask-reason", p.reason));
    if (p.state === "pending" && m.status === "running") {
      const row = node("div", "ask-buttons");
      const answer = async (allow) => {
        for (const b of row.querySelectorAll("button")) b.disabled = true;
        try {
          await api(`/api/chats/${currentId()}/answer`, { ask: p.id, allow });
        } catch (e) {
          toast(e.message);
          for (const b of row.querySelectorAll("button")) b.disabled = false;
        }
      };
      row.append(button("btn primary", "Allow", () => answer(true)), button("btn", "Deny", () => answer(false)));
      d.append(row);
    } else {
      d.append(node("div", "ask-state", ASK_STATES[p.state] || ASK_STATES.expired));
    }
    return d;
  }

  // After a plan: carry it out in the mode you pick.
  function planEl() {
    const d = node("div", "plan-run");
    d.append(node("span", null, "Run this plan in:"));
    for (const mode of ["auto", "acceptEdits", "default"]) {
      const b = button("btn" + (mode === "auto" ? " primary" : ""), MODE_NAMES[mode], () => {
        if (HOST_MODES.includes(mode) && status && !status.claude.host_ok) {
          toast("Manual and Accept edits need a newer Claude Code. Run: claude update");
          return;
        }
        prefs.mode = mode;
        el.mode.value = mode;
        write(PREFS, prefs);
        send("Go ahead and carry out the plan.");
      });
      b.title = MODE_TIPS[mode];
      d.append(b);
    }
    return d;
  }

  function activityEl(m) {
    const d = node("div", "activity");
    d.append(node("span", "spin"));
    let label = "Thinking…";
    if (m.phase === "ask") {
      label = "Waiting for you to allow or deny…";
    } else if (m.phase === "tool" && m.current) {
      label = toolInfo(m.current.name).active + (m.current.detail ? ": " + m.current.detail : "") + " …";
    } else if (m.phase === "text") {
      label = "Writing…";
    }
    d.append(node("span", "act-label", label), node("span", "elapsed", fmtTime(Math.round((Date.now() - m.started) / 1000))));
    return d;
  }

  function actionsEl(m) {
    const d = node("div", "actions");
    if (m.text) d.append(copyButton(() => m.text));
    const parts = [MODEL_NAMES[m.model] || m.model, m.effort, MODE_NAMES[m.mode]];
    if (m.seconds != null) parts.push(fmtTime(m.seconds));
    if (m.cost != null) parts.push((m.costUnknown ? "~" : "") + fmtCost(m.cost));
    const meta = node("span", null, parts.filter(Boolean).join(" · "));
    meta.title = m.costUnknown
      ? "The cost is a rough guess: this Claude Code version doesn't know this model's price yet. The Console's billing page shows the exact amount."
      : "The cost is Claude Code's estimate. The Console's billing page shows the exact amount.";
    d.append(meta);
    if (m.blocked) d.append(node("span", "flag", `${m.blocked} action${m.blocked > 1 ? "s" : ""} blocked`));
    if (m.status === "stopped") d.append(node("span", "flag", "Stopped"));
    return d;
  }

  const nearBottom = () => el.log.scrollHeight - el.log.scrollTop - el.log.clientHeight < 120;
  const scrollToEnd = () => {
    el.log.scrollTop = el.log.scrollHeight;
    updateToBottom();
  };
  const updateToBottom = () => {
    el.toBottom.classList.toggle("show", !el.main.classList.contains("empty") && !nearBottom());
  };

  // Streaming text arrives in many small pieces; repaint at most every 80 ms.
  const dirty = new Set();
  let paintTimer = 0;
  function paint(state) {
    dirty.add(state);
    if (!paintTimer) paintTimer = setTimeout(flushPaint, 80);
  }
  function flushPaint() {
    paintTimer = 0;
    const stick = nearBottom();
    for (const s of dirty) {
      const n = s.id === currentId() && nodes.get(s.bot);
      if (n) fillBot(n, s.bot);
    }
    dirty.clear();
    if (stick) scrollToEnd();
    else updateToBottom();
  }

  setInterval(() => {
    for (const s of live.values()) {
      const n = s.id === currentId() && nodes.get(s.bot);
      const e = n && n.querySelector(".elapsed");
      if (e) e.textContent = fmtTime(Math.round((Date.now() - s.bot.started) / 1000));
    }
  }, 1000);

  const ready = () => !!status && status.claude.found && status.key.set;

  function syncComposer() {
    const running = isRunning();
    el.send.classList.toggle("stop", running);
    el.send.textContent = "";
    el.send.append(iconNode(running ? "stop" : "up"));
    el.send.setAttribute("aria-label", running ? "Stop" : "Send");
    el.send.title = running ? "Stop this answer" : "Send (Enter)";
    el.send.disabled = sending || (!running && (!ready() || (!el.input.value.trim() && !pending.length)));
  }

  function autosize() {
    el.input.style.height = "auto";
    el.input.style.height = Math.min(el.input.scrollHeight, innerHeight * 0.4) + "px";
  }

  // ---------- the pickers ----------
  function fillSelect(sel, values, names, chosen, tips) {
    sel.textContent = "";
    for (const v of values) {
      const o = node("option", null, (names && names[v]) || v);
      o.value = v;
      if (tips && tips[v]) o.title = tips[v];
      sel.append(o);
    }
    sel.value = values.includes(chosen) ? chosen : values[0];
  }

  // A new chat picks its folder; an open chat stays in the folder it started in.
  function renderFolder() {
    const chat = current && current.chat;
    const folders = (status && status.folders) || [];
    el.folder.textContent = "";
    if (chat) {
      const known = folders.find((f) => f.path === chat.folder);
      const o = node("option", null, known ? known.name : chat.folder.split(/[\\/]/).filter(Boolean).pop() || chat.folder);
      o.value = chat.folder;
      el.folder.append(o);
      el.folder.disabled = true;
      el.folderPill.title = `This chat works in ${chat.folder}`;
      return;
    }
    for (const f of folders) {
      const o = node("option", null, f.name);
      o.value = f.path;
      o.title = f.path;
      el.folder.append(o);
    }
    el.folder.disabled = false;
    if (folders.some((f) => f.path === prefs.folder)) el.folder.value = prefs.folder;
    const picked = folders.find((f) => f.path === el.folder.value);
    el.folderPill.title = (picked ? picked.path + "\n\n" : "")
      + "The folder Claude works in. Its CLAUDE.md, memory, skills and MCP servers load like in your terminal. "
      + "Only folders you already trust in Claude Code are listed: to add one, run claude in it once and say yes.";
  }

  function renderModes() {
    const hostOk = !status || status.claude.host_ok;
    fillSelect(el.mode, Object.keys(MODE_NAMES), MODE_NAMES, prefs.mode, MODE_TIPS);
    for (const o of el.mode.options) {
      if (HOST_MODES.includes(o.value) && !hostOk) {
        o.disabled = true;
        o.title = "Needs a newer Claude Code. Run: claude update";
      }
    }
    if (el.mode.selectedOptions[0] && el.mode.selectedOptions[0].disabled) el.mode.value = "auto";
  }

  // ---------- chats ----------
  const narrow = () => matchMedia("(max-width: 820px)").matches; // the chat list becomes a drawer
  const touch = () => matchMedia("(pointer: coarse)").matches;   // no physical keyboard to expect
  const closeDrawer = () => el.app.classList.remove("drawer");

  async function loadList() {
    try {
      list = await apiJson("/api/chats");
    } catch (e) {
      toast(e.message);
      return;
    }
    if (current && !list.some((c) => c.id === current.chat.id)) current = null; // deleted in another tab
    renderSidebar();
  }

  function stopFollowing() {
    for (const s of live.values()) s.abort.abort(); // this page stops watching; the answer itself carries on
    live.clear();
  }

  async function openChat(id) {
    stopFollowing();
    try {
      current = await apiJson(`/api/chats/${id}`);
    } catch (e) {
      toast(e.message);
      return;
    }
    renderAll();
    closeDrawer();
    if (current.running) follow();
  }

  // Watch the open chat's answer as it is produced. Stops watching when the page leaves the chat; if the
  // connection drops, the chat is fetched again and watched from there.
  async function follow() {
    const id = currentId();
    if (!id || live.has(id)) return;
    const bot = current.chat.messages[current.chat.messages.length - 1];
    if (!bot || bot.role !== "bot" || bot.status !== "running") return;
    const state = { id, bot, abort: new AbortController() };
    live.set(id, state);
    let finished = false;
    try {
      const res = await fetch(`/api/chats/${id}/events?from=${current.cursor}`,
        { headers: { "X-Token": TOKEN }, signal: state.abort.signal });
      if (!res.ok) throw new Error(await problem(res));
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (!finished) {
        const chunk = await reader.read();
        if (chunk.done) break;
        buf += decoder.decode(chunk.value, { stream: true });
        let nl;
        while ((nl = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, nl);
          buf = buf.slice(nl + 1);
          if (!line.trim()) continue;
          const ev = JSON.parse(line);
          if (ev.t === "done") {
            finished = true;
            break;
          }
          if (ev.t !== "ping") onEvent(state, ev);
        }
      }
    } catch (e) {
      if (state.abort.signal.aborted) return;
      if (e.message && !e.message.startsWith("Failed") && !(e instanceof TypeError)) toast(e.message);
    } finally {
      live.delete(id);
    }
    if (finished) reopen(id);
    else if (document.visibilityState === "visible") setTimeout(() => reopen(id), 2000);
  }

  async function reopen(id) {
    if (currentId() !== id) {
      loadList();
      return;
    }
    const wasAtBottom = nearBottom();
    const top = el.log.scrollTop;
    try {
      current = await apiJson(`/api/chats/${id}`);
    } catch (e) {
      toast(e.message);
      return;
    }
    renderChat();
    if (!wasAtBottom) el.log.scrollTop = top; // the reader had scrolled up: don't yank them to the end
    syncComposer();
    loadList();
    if (current.running) follow();
  }

  // Catch up with what another tab did: the chat list, and the open chat if it moved on.
  async function sync() {
    const id = currentId();
    await loadList();
    if (!id) return;
    if (!current) { // deleted elsewhere
      stopFollowing();
      renderAll();
      return;
    }
    const item = list.find((c) => c.id === id);
    if (!item || live.has(id)) return; // this page is already watching the answer come in
    if (item.running || item.updated !== current.chat.updated || item.title !== current.chat.title) reopen(id);
  }

  async function renameChat(id) {
    if (currentId() !== id) await openChat(id);
    closeDrawer();
    if (currentId() === id) startRename();
  }

  // The name at the top turns into a text box: Enter or clicking elsewhere saves, Escape cancels.
  function startRename() {
    if (!current || el.title.querySelector("input")) return;
    const id = current.chat.id;
    const old = current.chat.title;
    const input = node("input", "title-edit");
    input.value = old;
    input.maxLength = 80;
    input.setAttribute("aria-label", "Chat name");
    el.title.textContent = "";
    el.title.append(input);
    input.focus();
    input.select();
    let done = false;
    const finishEdit = async (save) => {
      if (done) return;
      done = true;
      editing = null;
      const title = input.value.replace(/\s+/g, " ").trim();
      if (input.isConnected) el.title.textContent = current ? current.chat.title : "";
      if (!save || !title || title === old) return;
      try {
        const r = await apiJson(`/api/chats/${id}/rename`, { title });
        if (currentId() === id) {
          current.chat.title = r.title;
          el.title.textContent = r.title;
        }
        const item = list.find((c) => c.id === id);
        if (item) item.title = r.title;
        renderSidebar();
      } catch (e) {
        toast(e.message);
      }
    };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.isComposing) {
        e.preventDefault();
        finishEdit(true);
      } else if (e.key === "Escape") {
        finishEdit(false);
      }
    });
    input.addEventListener("blur", () => finishEdit(true));
    editing = { id, finish: finishEdit };
  }

  function newChat() {
    stopFollowing();
    current = null;
    renderAll();
    closeDrawer();
    el.input.focus();
  }

  async function removeChat(c) {
    if (c.running) {
      toast("This chat is still answering. Stop it first.");
      return;
    }
    if (!confirm(`Delete "${c.title}"?`)) return;
    try {
      await api(`/api/chats/${c.id}/delete`, {});
    } catch (e) {
      toast(e.message);
      return;
    }
    if (currentId() === c.id) {
      stopFollowing();
      current = null;
    }
    await loadList();
    renderChat();
    syncComposer();
  }

  function finish(bot, status_, error) {
    bot.status = status_;
    if (error) bot.error = error;
    for (const p of bot.parts) if (p.k === "ask" && p.state === "pending") p.state = "expired";
    if (bot.final && !bot.parts.some((p) => p.k === "text" && p.s.trim())) bot.parts.push({ k: "text", s: bot.final });
    bot.text = bot.parts.filter((p) => p.k === "text").map((p) => p.s.trim()).filter(Boolean).join("\n\n");
    for (const k of ["final", "brk", "phase", "current"]) delete bot[k];
    if (current && current.chat.messages.includes(bot)) current.running = false;
    syncComposer();
  }

  function resultProblem(ev, bot) {
    const s = ev.subtype || "";
    if (s.includes("budget")) return `Stopped: this answer reached its Max $ limit (${fmtCost(bot.budget)}). Raise Max $ and say "continue".`;
    if (s.includes("turns")) return 'Stopped: the answer hit Claude Code\'s turn limit. Say "continue" to go on.';
    return ev.text || `Claude Code reported an error (${s || "unknown"}).`;
  }

  // Same folding as apply() in app.py, so the live view matches what the app saves.
  function onEvent(state, ev) {
    const bot = state.bot;
    const last = bot.parts[bot.parts.length - 1];
    switch (ev.t) {
      case "init":
        if (ev.model) bot.model = ev.model;
        if (ev.billing_ok === false) bot.warn = "This answer was NOT billed to your API key.";
        {
          const ran = ev.mode === "manual" ? "default" : ev.mode; // newer Claude Code calls Manual "manual"
          if (ran && bot.mode && ran !== bot.mode) bot.notice = `Claude Code ran this in ${MODE_NAMES[ran] || ran} mode.`;
        }
        break;
      case "notice":
        bot.notice = ev.msg;
        break;
      case "keywarn":
        bot.keywarn = ev.msg;
        break;
      case "turn":
        bot.phase = "thinking";
        bot.brk = true;
        break;
      case "text":
        bot.phase = "text";
        if (last && last.k === "text") {
          if (bot.brk && last.s && !last.s.endsWith("\n\n")) last.s += "\n\n";
          last.s += ev.d;
        } else {
          bot.parts.push({ k: "text", s: ev.d });
        }
        bot.brk = false;
        break;
      case "tool": {
        bot.phase = "tool";
        bot.current = { name: ev.name, detail: ev.detail };
        const item = { name: ev.name, detail: ev.detail, sub: ev.sub };
        if (last && last.k === "tools") last.items.push(item);
        else bot.parts.push({ k: "tools", items: [item] });
        break;
      }
      case "ask":
        bot.phase = "ask";
        bot.parts.push({ k: "ask", id: ev.id, tool: ev.tool, title: ev.title, detail: ev.detail, reason: ev.reason || "", state: "pending" });
        break;
      case "answered":
        for (const p of bot.parts) if (p.k === "ask" && p.id === ev.id) p.state = ev.state;
        if (!bot.parts.some((p) => p.k === "ask" && p.state === "pending")) bot.phase = "thinking";
        break;
      case "result":
        bot.cost = ev.cost || 0;
        bot.costUnknown = !!ev.cost_unknown;
        bot.seconds = ev.seconds;
        bot.blocked = ev.blocked;
        if (ev.stopped) {
          finish(bot, "stopped");
        } else if (ev.ok) {
          bot.final = ev.text;
          finish(bot, "ok");
        } else {
          finish(bot, "error", resultProblem(ev, bot));
        }
        break;
      case "stopped":
        finish(bot, "stopped");
        break;
      case "error":
        finish(bot, "error", ev.msg);
        break;
      default:
        return;
    }
    paint(state);
  }

  async function send(override) {
    const text = override || el.input.value.trim();
    if ((!text && !pending.length) || isRunning() || sending) return;
    if (!ready()) {
      renderSetup();
      return;
    }
    const id = currentId() || uuid();
    const withPictures = !override && pending.length;
    sending = true;
    el.send.disabled = true;
    el.sendNote.textContent = pending.length > 1 ? "Sending the pictures…" : "Sending the picture…";
    el.sendNote.hidden = !withPictures;
    try {
      const images = [];
      if (withPictures) for (const p of pending) images.push({ type: p.type, w: p.w, h: p.h, data: await base64(p.blob) });
      await api(`/api/chats/${id}/send`, {
        message: text, images, model: el.model.value, effort: el.effort.value, budget: prefs.budget,
        mode: el.mode.value, folder: el.folder.value,
      });
    } catch (e) {
      toast(e.message);
      loadStatus(); // key.txt may have changed since the page last looked: show the key screen if there's no key now
      return;
    } finally {
      sending = false;
      el.sendNote.hidden = true;
      syncComposer();
    }
    if (!override) {
      el.input.value = "";
      clearPending();
      autosize();
    }
    syncComposer();
    await openChat(id);
    loadList();
  }

  async function stop() {
    if (!isRunning()) return;
    el.send.disabled = true;
    try {
      await api(`/api/chats/${currentId()}/stop`, {});
    } catch (e) {
      toast(e.message);
      el.send.disabled = false;
    }
  }

  // ---------- settings ----------
  function savePrefs() {
    prefs.model = el.model.value;
    prefs.effort = el.effort.value;
    prefs.mode = el.mode.value;
    if (!el.folder.disabled && el.folder.value) prefs.folder = el.folder.value;
    const b = parseFloat(el.budget.value);
    prefs.budget = Number.isFinite(b) ? Math.min(Math.max(b, 0.1), 50) : 5;
    write(PREFS, prefs);
  }

  function applyTheme() {
    const t = THEMES.includes(prefs.theme) ? prefs.theme : "auto";
    if (t === "auto") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = t;
    el.themeBtn.textContent = "";
    el.themeBtn.append(iconNode(t === "auto" ? "monitor" : t === "light" ? "sun" : "moon"),
      node("span", null, t === "auto" ? "Theme: match device" : t === "light" ? "Theme: light" : "Theme: dark"));
  }

  async function loadStatus() {
    try {
      status = await apiJson("/api/status");
    } catch (e) {
      el.keyText.textContent = e.message === OFFLINE ? "App not running" : "Error";
      el.keyPill.title = e.message; // on a phone the button is only a dot
      el.keyPill.className = "keypill bad";
      return;
    }
    fillSelect(el.model, status.models, MODEL_NAMES, prefs.model || status.defaults.model);
    fillSelect(el.effort, status.efforts, null, prefs.effort || status.defaults.effort);
    renderModes();
    renderFolder();
    renderSetup();
    syncComposer();
  }

  async function quit() {
    if (!confirm("Quit API Credit Code? Answers still running are stopped. Open it again from its icon.")) return;
    try {
      await api("/api/quit", {});
    } catch {
      // already gone
    }
    document.body.textContent = "";
    const d = node("div", "bye");
    d.append(node("p", null, "API Credit Code has stopped."), node("p", null, "Open it again from its icon, then reload this tab."));
    document.body.append(d);
  }

  // static icons and buttons
  $("plusIcon").append(iconNode("plus"));
  el.attach.append(iconNode("plus"));
  el.sideOpen.append(iconNode("panel"));
  el.sideClose.append(iconNode("panel"));
  el.toBottom.append(iconNode("down"));
  for (const c of CHIPS) {
    const b = button("chip", null, () => {
      el.input.value = c.text;
      autosize();
      syncComposer();
      el.input.focus();
      el.input.setSelectionRange(c.text.length, c.text.length);
    });
    b.append(iconNode(c.icon), node("span", null, c.label));
    el.chips.append(b);
  }

  fillSelect(el.model, Object.keys(MODEL_NAMES), MODEL_NAMES, prefs.model || "claude-opus-5-5");
  fillSelect(el.effort, EFFORTS, null, prefs.effort || "high");
  renderModes();
  el.budget.value = prefs.budget;
  for (const s of [el.model, el.effort, el.mode, el.folder]) s.addEventListener("change", () => {
    savePrefs();
    if (s === el.folder) renderFolder();
  });
  el.budget.addEventListener("change", () => {
    savePrefs();
    el.budget.value = prefs.budget;
  });

  el.composer.addEventListener("submit", (e) => {
    e.preventDefault();
    if (isRunning()) stop();
    else send();
  });
  el.input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing && !touch()) { // on a touch screen, Enter makes a new line
      e.preventDefault();
      if (!isRunning()) send();
    }
  });
  el.input.addEventListener("input", () => {
    autosize();
    syncComposer();
  });
  // Pictures: the + button, Ctrl+V, and a file dragged onto the chat.
  el.attach.addEventListener("click", () => el.file.click());
  el.file.addEventListener("change", () => {
    addImages([...el.file.files]);
    el.file.value = ""; // so picking the same file again counts
  });
  document.addEventListener("paste", (e) => {
    const files = imageFiles(e.clipboardData);
    if (!files.length) return;
    const t = e.target;
    if (t !== el.input && t instanceof Element && t.closest("input, textarea")) return; // pasting into another box
    if (t !== el.input || !(e.clipboardData.getData("text/plain") || "").trim()) e.preventDefault(); // words that came along still paste
    addImages(files);
  });
  let dragDepth = 0;
  el.main.addEventListener("dragenter", (e) => {
    if (!hasFiles(e.dataTransfer)) return;
    e.preventDefault();
    dragDepth += 1;
    el.main.classList.add("dropping");
  });
  el.main.addEventListener("dragover", (e) => {
    if (!hasFiles(e.dataTransfer)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  });
  el.main.addEventListener("dragleave", () => {
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) el.main.classList.remove("dropping");
  });
  el.main.addEventListener("drop", (e) => {
    if (!hasFiles(e.dataTransfer)) return;
    e.preventDefault();
    dragDepth = 0;
    el.main.classList.remove("dropping");
    addImages(imageFiles(e.dataTransfer));
  });
  el.newChat.addEventListener("click", newChat);
  el.sideOpen.addEventListener("click", () => {
    if (narrow()) {
      el.app.classList.add("drawer");
    } else {
      el.app.classList.remove("side-hidden");
      prefs.sideHidden = false;
      write(PREFS, prefs);
    }
  });
  el.sideClose.addEventListener("click", () => {
    if (narrow()) {
      closeDrawer();
    } else {
      el.app.classList.add("side-hidden");
      prefs.sideHidden = true;
      write(PREFS, prefs);
    }
  });
  el.scrim.addEventListener("click", closeDrawer);
  el.themeBtn.addEventListener("click", () => {
    prefs.theme = THEMES[(THEMES.indexOf(prefs.theme) + 1) % THEMES.length];
    write(PREFS, prefs);
    applyTheme();
  });
  el.quitBtn.addEventListener("click", quit);
  el.keyPill.addEventListener("click", () => {
    setupOpen = !setupOpen || !status || !status.key.set;
    keyMessage("", "");
    renderSetup();
  });
  el.keyForm.addEventListener("submit", (e) => {
    e.preventDefault();
    saveKey();
  });
  el.keyRemove.addEventListener("click", removeKey);
  el.keyClose.addEventListener("click", () => {
    setupOpen = false;
    renderSetup();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || e.defaultPrevented) return;
    if (setupOpen && status && status.key.set) {
      setupOpen = false;
      renderSetup();
    } else if (el.app.classList.contains("drawer")) {
      closeDrawer();
    }
  });
  el.title.addEventListener("click", () => current && startRename());
  el.log.addEventListener("scroll", updateToBottom);
  el.toBottom.addEventListener("click", () => el.log.scrollTo({ top: el.log.scrollHeight, behavior: "smooth" }));

  // Back to this tab: catch up on what happened meanwhile, and pick up newly trusted folders.
  function wake() {
    if (document.visibilityState !== "visible") return;
    sync();
    loadStatus();
  }

  // The app answers this as soon as any chat starts or finishes answering, or is renamed, deleted or added, so a
  // page left open updates itself without a reload. It is also how the app knows a tab is still open.
  let version = null;
  let unreachable = false; // the app stopped answering: say so once, and catch up when it's back
  async function watchChanges() {
    for (let wait = 1000; ; ) {
      const stopper = new AbortController();
      const timer = setTimeout(() => stopper.abort(), 35000);
      try {
        const res = await fetch(`/api/changes?since=${version === null ? -1 : version}`,
          { headers: { "X-Token": TOKEN }, signal: stopper.signal });
        if (res.status === 403) {
          await outOfDate();
          continue;
        }
        if (!res.ok) throw new Error(res.status);
        const r = await res.json();
        wait = 1000;
        if (unreachable) {
          unreachable = false;
          loadStatus();
        }
        if (r.version !== version) {
          version = r.version;
          await sync();
        }
      } catch {
        if (!unreachable && wait >= 2000) { // a second failure in a row: not just a hiccup
          unreachable = true;
          toast(OFFLINE);
          loadStatus(); // the key button says "App not running" until it's back
        }
        await new Promise((done) => setTimeout(done, wait)); // the app is closed or busy: try again
        wait = Math.min(wait * 2, 15000);
      } finally {
        clearTimeout(timer);
      }
    }
  }

  // The app was restarted. Reload the page (it reopens the same chat) unless that would throw away something being
  // typed, or it was just reloaded for this; otherwise carry on with the new key.
  async function outOfDate() {
    let last = 0;
    try {
      last = Number(sessionStorage.getItem("api-credit-code.reloaded")) || 0;
    } catch {
      // no storage: reload anyway
    }
    if (!el.input.value.trim() && !editing && Date.now() - last > 60000) {
      try {
        sessionStorage.setItem("api-credit-code.reloaded", String(Date.now()));
      } catch {
        // see above
      }
      location.reload();
      await new Promise(() => {}); // the page is going away
    }
    if (!(await freshToken())) await new Promise((done) => setTimeout(done, 2000)); // still starting: try again soon
  }
  document.addEventListener("visibilitychange", wake);
  addEventListener("pageshow", (e) => e.persisted && wake());
  setInterval(() => {
    if (list.some((c) => c.running) || isRunning()) sync();
  }, 10000);

  if (prefs.sideHidden) el.app.classList.add("side-hidden");
  const reopenId = location.hash.slice(1); // the chat this page showed before a reload; read before the first render clears it
  applyTheme();
  renderAll();
  (async () => {
    await loadStatus();
    await loadList();
    const asked = list.find((c) => c.id === reopenId);
    const running = list.find((c) => c.running); // e.g. the page was reloaded while an answer was underway
    if (asked || running) await openChat((asked || running).id);
    else if (ready()) el.input.focus();
    watchChanges();
  })();
})();
