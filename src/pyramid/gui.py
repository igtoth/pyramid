"""The desktop app (Tkinter).

Every API call runs on a worker thread; workers never touch Tk. They post
events to a queue that the main thread drains with after(), so the window
stays responsive and Cancel stops a request between pages and during
rate-limit waits.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import queue
import random
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from collections.abc import Callable
from importlib import resources
from tkinter import filedialog, messagebox, ttk
from typing import Any

from . import APP_TITLE, REPO_URL, __version__, data
from .catalog import Column, Endpoint, load
from .client import ApiError, Cancelled, CancelToken, GenesysClient
from .config import OAuthClient, Store, redact_url, valid_proxy
from .fetch import Result, fetch, queue_members
from .regions import REGIONS

log = logging.getLogger("pyramid")

IS_WIN, IS_MAC = sys.platform == "win32", sys.platform == "darwin"
MOD = "Command" if IS_MAC else "Control"
MOD_LABEL = "⌘" if IS_MAC else "Ctrl+"

# ── design tokens ─────────────────────────────────────────────────────────────

DARK = {
    "bg_base": "#16181f", "bg_surface": "#1e2130", "bg_raised": "#272b3d", "bg_hover": "#323759",
    "bg_active": "#3d4468", "border": "#353a55", "border_hi": "#5a6490",
    "fg_primary": "#f0f4ff", "fg_secondary": "#a8b4cc", "fg_muted": "#7280a8",
    "accent": "#6b9fff", "accent_hi": "#90b8ff", "accent_dim": "#2e4a8c",
    "success": "#4ade80", "warn": "#fcd34d", "danger": "#ff7878",
    "danger_bg": "#4a1f1f", "danger_hover": "#6b2a2a",
    "sect": ["#6b9fff", "#c084fc", "#4ade80", "#fcd34d", "#fb9f4a", "#f875c0"],
}
LIGHT = {
    "bg_base": "#f0f0f0", "bg_surface": "#ffffff", "bg_raised": "#e6e6e6", "bg_hover": "#cce4f7",
    "bg_active": "#99caf5", "border": "#c4c4c4", "border_hi": "#0078d4",
    "fg_primary": "#111111", "fg_secondary": "#444444", "fg_muted": "#6e6e6e",
    "accent": "#0067b8", "accent_hi": "#005a9e", "accent_dim": "#cce4f7",
    "success": "#107c10", "warn": "#9d5d00", "danger": "#c42b1c",
    "danger_bg": "#fde8e8", "danger_hover": "#fccaca",
    "sect": ["#0067b8", "#744da9", "#107c10", "#9d5d00", "#c43e00", "#c30078"],
}
P: dict[str, Any] = dict(LIGHT)

if IS_WIN:
    UI, MONO = "Segoe UI", "Consolas"
elif IS_MAC:
    UI, MONO = "Helvetica Neue", "Menlo"
else:
    UI, MONO = "DejaVu Sans", "DejaVu Sans Mono"
F = {
    "ui": (UI, 9), "ui_b": (UI, 9, "bold"), "ui_sm": (UI, 8), "heading": (UI, 11, "bold"),
    "title": (UI, 14, "bold"), "hero": (UI, 18, "bold"), "mono": (MONO, 9), "mono_sm": (MONO, 8),
}
if IS_MAC:  # Tk on macOS draws points larger than pixels
    F = {k: (v[0], v[1] + 3, *v[2:]) for k, v in F.items()}


def apply_style(root: tk.Tk) -> None:
    root.configure(bg=P["bg_base"])
    s = ttk.Style(root)
    try:
        s.theme_use("clam")
    except tk.TclError:
        pass
    s.configure(".", background=P["bg_base"], foreground=P["fg_primary"], font=F["ui"],
                bordercolor=P["border"], lightcolor=P["bg_raised"], darkcolor=P["bg_raised"],
                troughcolor=P["bg_surface"], fieldbackground=P["bg_surface"])
    s.configure("TNotebook", background=P["bg_base"], borderwidth=0, tabmargins=(6, 6, 6, 0))
    s.configure("TNotebook.Tab", background=P["bg_raised"], foreground=P["fg_secondary"],
                padding=(14, 6), font=F["ui_b"], borderwidth=0)
    s.map("TNotebook.Tab", background=[("selected", P["bg_surface"]), ("active", P["bg_hover"])],
          foreground=[("selected", P["accent"]), ("active", P["fg_primary"])])
    s.configure("Treeview", background=P["bg_surface"], fieldbackground=P["bg_surface"],
                foreground=P["fg_primary"], font=F["ui"], rowheight=24, borderwidth=0)
    s.configure("Treeview.Heading", background=P["bg_raised"], foreground=P["accent"], font=F["ui_b"],
                relief="flat", borderwidth=0, padding=(6, 4))
    s.map("Treeview", background=[("selected", P["accent_dim"])], foreground=[("selected", P["fg_primary"])])
    s.map("Treeview.Heading", background=[("active", P["bg_hover"])])
    s.configure("TScrollbar", background=P["bg_raised"], troughcolor=P["bg_surface"], borderwidth=0,
                arrowcolor=P["fg_secondary"], relief="flat")
    s.map("TScrollbar", background=[("active", P["bg_hover"])])
    s.configure("TCombobox", fieldbackground=P["bg_raised"], background=P["bg_raised"],
                foreground=P["fg_primary"], arrowcolor=P["accent"], selectbackground=P["bg_raised"],
                selectforeground=P["fg_primary"])
    s.map("TCombobox", fieldbackground=[("readonly", P["bg_raised"])])
    root.option_add("*TCombobox*Listbox.background", P["bg_surface"])
    root.option_add("*TCombobox*Listbox.foreground", P["fg_primary"])
    root.option_add("*TCombobox*Listbox.selectBackground", P["accent_dim"])
    s.configure("bar.Horizontal.TProgressbar", troughcolor=P["bg_raised"], background=P["accent"],
                bordercolor=P["border"], thickness=6)


def button(parent, text, command, kind="normal", **kw) -> tk.Button:
    """Flat themed button with hover. kind: normal | accent | danger | ghost."""
    kinds = {
        "normal": (P["bg_raised"], P["fg_primary"], P["bg_hover"]),
        "accent": (P["accent"], "#ffffff", P["accent_hi"]),
        "danger": (P["danger_bg"], P["danger"], P["danger_hover"]),
        "ghost": (P["bg_base"], P["fg_secondary"], P["bg_raised"]),
    }
    bg, fg, hover = kinds[kind]
    b = tk.Button(parent, text=text, command=command, bg=bg, fg=fg, activebackground=hover,
                  activeforeground=fg, relief="flat", bd=0, padx=10, pady=5, cursor="hand2",
                  font=F["ui"], highlightthickness=0, disabledforeground=P["fg_muted"], **kw)
    b.bind("<Enter>", lambda e: b.config(bg=hover) if str(b["state"]) != "disabled" else None)
    b.bind("<Leave>", lambda e: b.config(bg=bg))
    return b


def label(parent, text="", bg=None, fg=None, font=None, **kw) -> tk.Label:
    return tk.Label(parent, text=text, bg=bg or P["bg_surface"], fg=fg or P["fg_primary"],
                    font=font or F["ui"], **kw)


def entry(parent, width=30, **kw) -> tk.Entry:
    return tk.Entry(parent, width=width, bg=P["bg_raised"], fg=P["fg_primary"], insertbackground=P["accent"],
                    relief="flat", bd=4, highlightthickness=1, highlightbackground=P["border"],
                    highlightcolor=P["accent"], font=F["ui"], **kw)


class Scrollable(tk.Frame):
    """A vertically scrolling frame; the wheel scrolls it while the pointer is over it."""

    def __init__(self, parent, bg):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        for w in (self.canvas, self.body):
            w.bind("<Enter>", self._bind_wheel)
            w.bind("<Leave>", self._unbind_wheel)

    def _bind_wheel(self, _e=None):
        self.bind_all("<MouseWheel>", self._wheel)
        self.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-3, "units"))
        self.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(3, "units"))

    def _unbind_wheel(self, _e=None):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.unbind_all(seq)

    def _wheel(self, e):
        if self.body.winfo_height() <= self.canvas.winfo_height():
            return
        step = -e.delta if IS_MAC else -e.delta / 40   # macOS deltas are small integers
        self.canvas.yview_scroll(int(step) or (-1 if e.delta > 0 else 1), "units")


class ToolTip:
    def __init__(self, widget, text: str | Callable[[], str]):
        self.widget, self.text, self.tip = widget, text, None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def show(self, _e=None):
        text = self.text() if callable(self.text) else self.text
        if not text:
            return
        x, y = self.widget.winfo_rootx() + 12, self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=text, bg=P["bg_raised"], fg=P["fg_primary"], font=F["ui_sm"], padx=8, pady=4,
                 justify="left", highlightbackground=P["border"], highlightthickness=1).pack()

    def hide(self, _e=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class GuiLogHandler(logging.Handler):
    """Forwards log records from any thread to the app's queue."""

    def __init__(self, q: queue.Queue):
        super().__init__(logging.INFO)
        self.q = q

    def emit(self, record):
        level = {logging.WARNING: "WARN", logging.ERROR: "ERROR"}.get(record.levelno, "INFO")
        self.q.put(("log", level, record.getMessage()))


LEVELS = ["DEBUG", "INFO", "OK", "WARN", "ERROR"]


# ── the app ───────────────────────────────────────────────────────────────────

class App:
    def __init__(self, root: tk.Tk, store: Store | None = None):
        self.root = root
        self.store = store or Store()
        self.cat = load()
        self.events: queue.Queue = queue.Queue()
        self.cache: dict[tuple, Result] = {}
        self.clients: dict[str, GenesysClient] = {}
        self.active: OAuthClient | None = None
        self.cancel: CancelToken | None = None
        self.busy = False
        self.tabs: list[ReportTab] = []
        self.current: ReportTab | None = None   # None: the Reports sub-tab
        self.log_lines: list[tuple[str, str, str]] = []
        self.log_level = tk.StringVar(value="INFO")
        self.theme = self.store.get("theme", "light")
        P.update(DARK if self.theme == "dark" else LIGHT)
        self.proxy_on = tk.BooleanVar(value=self.store.get_bool("proxy_enabled"))
        self.proxy_on.trace_add("write", lambda *_: self._proxy_toggled())
        handler = GuiLogHandler(self.events)
        logging.getLogger("pyramid").addHandler(handler)
        logging.getLogger("pyramid").setLevel(logging.INFO)

        root.title(f"{APP_TITLE}  v{__version__}")
        self._set_icon()
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        w, h = min(1400, int(sw * 0.78)), min(900, int(sh * 0.8))
        root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 3}")
        root.minsize(960, 620)
        self._bind_keys()
        last = self.store.get("last_client")
        if last and self.store.client(last):
            self.active = self.store.client(last)
        self.build()
        self.logline("INFO", f"{APP_TITLE} {__version__} started; config: {self.store.path}")
        root.after(60, self._drain)

    # ── plumbing ──────────────────────────────────────────────────────────

    def _set_icon(self):
        try:
            imgs = []
            for size in (16, 32, 64, 256):
                data_ = resources.files("pyramid").joinpath(f"assets/pyramid-{size}.png").read_bytes()
                imgs.append(tk.PhotoImage(data=data_))
            self.root.iconphoto(True, *imgs)
            self._icons = imgs
        except Exception:  # icons are cosmetic
            pass

    def _bind_keys(self):
        r = self.root
        r.bind("<Escape>", lambda e: self.go_home())
        for key in ("s", "S"):
            r.bind(f"<{MOD}-{key}>", lambda e: self.export_csv())
        for key in ("f", "F"):
            r.bind(f"<{MOD}-{key}>", lambda e: self._focus_search())
        for key in ("r", "R"):
            r.bind(f"<{MOD}-{key}>", lambda e: self.refresh())
        r.bind("<F5>", lambda e: self.refresh())
        for key in ("w", "W"):
            r.bind(f"<{MOD}-{key}>", lambda e: self.close_current())

    def _drain(self):
        """Run what the workers posted. One failing event must not stop the next ones."""
        try:
            while True:
                try:
                    ev = self.events.get_nowait()
                except queue.Empty:
                    break
                try:
                    kind = ev[0]
                    if kind == "log":
                        self.logline(ev[1], ev[2])
                    elif kind == "progress":
                        self.status(ev[1], "accent")
                    elif kind == "call":
                        ev[1](*ev[2:])
                except Exception as e:  # keep the window alive, say what happened
                    self.busy = False
                    try:
                        self._busy_ui(False)
                        self.status(f"Error: {type(e).__name__}: {e}", "danger")
                        self.logline("ERROR", f"Internal error: {type(e).__name__}: {e}")
                    except Exception:
                        pass
        finally:
            self.root.after(60, self._drain)

    def run_task(self, label_: str, work: Callable[[CancelToken], Any], done: Callable[[Any], None],
                 cancellable: bool = True):
        """Run work(cancel) on a thread; done(result) runs on the Tk thread."""
        if self.busy:
            self.status("Another request is running; cancel it first", "warn")
            return
        self.busy = True
        self.cancel = CancelToken()
        cancel = self.cancel
        self._busy_ui(True, cancellable)
        self.status(f"{label_}...", "accent")
        self.logline("INFO", f"Started: {label_}")

        def runner():
            try:
                out = work(cancel)
                self.events.put(("call", self._finish, label_, done, out, None))
            except Cancelled:
                self.events.put(("call", self._finish, label_, done, None, "cancelled"))
            except Exception as e:  # shown to the user, logged without secrets
                self.events.put(("call", self._finish, label_, done, None, e))

        threading.Thread(target=runner, daemon=True, name=f"task:{label_}").start()

    def _finish(self, label_, done, out, err):
        self.busy = False
        self._busy_ui(False)
        if err == "cancelled":
            self.status("Cancelled", "warn")
            self.logline("WARN", f"Cancelled: {label_}")
            return
        if err is not None:
            msg = str(err) if isinstance(err, ApiError) else f"{type(err).__name__}: {err}"
            self.status(f"Error: {msg}", "danger")
            self.logline("ERROR", f"{label_}: {msg}")
            self.show_error(label_, msg)
            return
        done(out)

    def progress_fn(self):
        return lambda text: self.events.put(("progress", text))

    def client(self) -> GenesysClient | None:
        c = self.active
        if not c:
            return None
        key = c.name
        gc = self.clients.get(key)
        proxy = self.store.proxy() if self.proxy_on.get() else None
        if gc is None or (gc.region, gc.client_id) != (c.region, c.client_id) or getattr(gc, "_proxy", None) != proxy:
            gc = GenesysClient(c.region, c.client_id, c.client_secret, proxy=proxy)
            gc._proxy = proxy
            self.clients[key] = gc
        return gc

    def cache_key(self, ep: Endpoint) -> tuple:
        c = self.active
        return (c.name, c.region, c.client_id, ep.key) if c else (None, None, None, ep.key)

    def forget_client(self, name: str):
        self.clients.pop(name, None)
        for k in [k for k in self.cache if k[0] == name]:
            del self.cache[k]

    # ── layout ────────────────────────────────────────────────────────────

    def build(self):
        """(Re)build the whole window; used at start and on theme changes."""
        for w in self.root.winfo_children():
            w.destroy()
        apply_style(self.root)
        self._status_bar()
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True)
        self.tab_main = tk.Frame(self.nb, bg=P["bg_base"])
        self.tab_oauth = tk.Frame(self.nb, bg=P["bg_base"])
        self.tab_config = tk.Frame(self.nb, bg=P["bg_base"])
        self.tab_log = tk.Frame(self.nb, bg=P["bg_base"])
        self.tab_help = tk.Frame(self.nb, bg=P["bg_base"])
        self.tab_about = tk.Frame(self.nb, bg=P["bg_base"])
        for t, name in ((self.tab_main, "Main"), (self.tab_oauth, "OAuth"), (self.tab_config, "Config"),
                        (self.tab_log, "Log"), (self.tab_help, "Help"), (self.tab_about, "About")):
            self.nb.add(t, text=f"  {name}  ")
        self.build_oauth()
        self.build_config()
        self.build_log()
        self.build_help()
        self.build_about()
        self.build_main()

    def _status_bar(self):
        tk.Frame(self.root, bg=P["border"], height=1).pack(side="bottom", fill="x")
        bar = tk.Frame(self.root, bg=P["bg_raised"])
        bar.pack(side="bottom", fill="x")
        self.client_lbl = label(bar, bg=P["bg_raised"], fg=P["accent"], font=F["ui_b"])
        self.client_lbl.pack(side="left", padx=10, pady=4)
        self.cancel_btn = button(bar, "⏹ Cancel", self.cancel_task, kind="danger")
        theme_btn = button(bar, "☀" if self.theme == "dark" else "🌙", self.toggle_theme, kind="ghost")
        theme_btn.configure(bg=P["bg_raised"])
        theme_btn.pack(side="right", padx=(0, 6))
        ToolTip(theme_btn, "Dark / light theme")
        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=110, style="bar.Horizontal.TProgressbar")
        self.progress_slot = tk.Frame(bar, bg=P["bg_raised"])
        self.progress_slot.pack(side="right")
        self.status_lbl = label(bar, "Ready", bg=P["bg_raised"], fg=P["fg_secondary"], font=F["ui_sm"])
        self.status_lbl.pack(side="right", padx=6)
        chk = tk.Checkbutton(bar, text="Proxy", variable=self.proxy_on, bg=P["bg_raised"], fg=P["fg_secondary"],
                             selectcolor=P["bg_surface"], activebackground=P["bg_raised"],
                             activeforeground=P["accent"], font=F["ui_sm"], bd=0, highlightthickness=0)
        chk.pack(side="right", padx=6)
        ToolTip(chk, lambda: f"Use the proxy\n{redact_url(self.store.get('proxy_url')) or 'No proxy configured (Config tab)'}")
        self._client_label()

    def _client_label(self):
        if self.active:
            self.client_lbl.config(text=f"●  {self.active.name}  ·  {self.active.region}", fg=P["success"])
        else:
            self.client_lbl.config(text="No client selected", fg=P["warn"])

    def _busy_ui(self, busy: bool, cancellable: bool = True):
        if busy:
            self.progress.pack(in_=self.progress_slot, padx=6)
            self.progress.start(12)
            if cancellable:
                self.cancel_btn.pack(side="left", padx=4, pady=2)
        else:
            self.progress.stop()
            self.progress.pack_forget()
            self.cancel_btn.pack_forget()
        for b in getattr(self, "report_buttons", []):
            if b.winfo_exists():
                b.config(state="disabled" if busy or not self.active else "normal")

    def status(self, text: str, color: str = "fg_secondary"):
        if self.status_lbl.winfo_exists():
            self.status_lbl.config(text=text[:160], fg=P[color])

    def logline(self, level: str, msg: str):
        ts = _dt.datetime.now().strftime("%H:%M:%S")
        self.log_lines.append((ts, level, msg))
        del self.log_lines[:-5000]
        if hasattr(self, "log_text") and self.log_text.winfo_exists() and self._shown(level):
            self._append_log(ts, level, msg)

    def _shown(self, level: str) -> bool:
        return LEVELS.index(level) >= LEVELS.index(self.log_level.get())

    # ── Main: sub-tabs (Reports, then one per opened report) ──────────────

    MAX_TABS = 12

    def build_main(self):
        for w in self.tab_main.winfo_children():
            w.destroy()
        self.subbar = tk.Frame(self.tab_main, bg=P["bg_base"])
        self.subbar.pack(fill="x", padx=8, pady=(6, 0))
        tk.Frame(self.tab_main, bg=P["accent"], height=2).pack(fill="x")
        self.stack = tk.Frame(self.tab_main, bg=P["bg_base"])
        self.stack.pack(fill="both", expand=True)
        self.home_frame = None
        for t in self.tabs:
            t.frame = None
        self.select(self.current if self.current in self.tabs else None)

    def render_subbar(self):
        for w in self.subbar.winfo_children():
            w.destroy()

        def chip(text, tab, closable):
            active = tab is self.current
            bg = P["bg_surface"] if active else P["bg_raised"]
            f = tk.Frame(self.subbar, bg=bg, highlightbackground=P["accent"] if active else P["border"],
                         highlightthickness=1)
            f.pack(side="left", padx=(0, 3))
            lb = tk.Label(f, text=text, bg=bg, fg=P["accent"] if active else P["fg_secondary"],
                          font=F["ui_b"] if active else F["ui"], padx=10, pady=4, cursor="hand2")
            lb.pack(side="left")
            for w in (f, lb):
                w.bind("<Button-1>", lambda e, t=tab: self.select(t))
                if closable:
                    w.bind("<Button-2>", lambda e, t=tab: self.close_tab(t))
            if closable:
                x = tk.Label(f, text="✕", bg=bg, fg=P["fg_muted"], font=F["ui_sm"], padx=6, cursor="hand2")
                x.pack(side="left")
                x.bind("<Button-1>", lambda e, t=tab: self.close_tab(t))
                x.bind("<Enter>", lambda e, w=x: w.config(fg=P["danger"]))
                x.bind("<Leave>", lambda e, w=x: w.config(fg=P["fg_muted"]))
                ToolTip(lb, lambda t=tab: f"{t.res.endpoint.label} · fetched {t.res.fetched_at.replace('T', ' ')}")
            return f

        chip("▦  Reports", None, False)
        for t in self.tabs:
            chip(t.res.endpoint.label, t, True)
        if self.tabs:
            more = tk.Label(self.subbar, text="Close all", bg=P["bg_base"], fg=P["fg_muted"], font=F["ui_sm"],
                            cursor="hand2", padx=8)
            more.pack(side="right")
            more.bind("<Button-1>", lambda e: self.close_all_tabs())

    def select(self, tab: ReportTab | None):
        """Show the Reports sub-tab (None) or a report's sub-tab."""
        for w in self.stack.winfo_children():
            w.pack_forget()
        self.current = tab
        if tab is None:
            if self.home_frame is not None:
                self.home_frame.destroy()
            self.home_frame = tk.Frame(self.stack, bg=P["bg_base"])
            self.render_home(self.home_frame)
            self.home_frame.pack(fill="both", expand=True)
        else:
            if tab.frame is None or not tab.frame.winfo_exists():
                tab.frame = tk.Frame(self.stack, bg=P["bg_base"])
                self.render_result(tab)
            tab.frame.pack(fill="both", expand=True)
            self._update_count(tab)
        self.render_subbar()

    def open_tab(self, res: Result):
        tab = next((t for t in self.tabs if t.res.endpoint.key == res.endpoint.key), None)
        if tab:
            tab.res = res
            if tab.frame is not None:
                tab.frame.destroy()
                tab.frame = None
        else:
            tab = ReportTab(res)
            self.tabs.append(tab)
            while len(self.tabs) > self.MAX_TABS:
                old = next(t for t in self.tabs if t is not tab)
                self.close_tab(old, reselect=False)
        self.nb.select(self.tab_main)
        self.select(tab)

    def close_tab(self, tab: ReportTab, reselect: bool = True):
        if tab not in self.tabs:
            return
        i = self.tabs.index(tab)
        self.tabs.remove(tab)
        if tab.frame is not None:
            tab.frame.destroy()
        if reselect:
            if self.current is tab:
                self.select(self.tabs[min(i, len(self.tabs) - 1)] if self.tabs else None)
            else:
                self.render_subbar()

    def close_all_tabs(self):
        for t in list(self.tabs):
            if t.frame is not None:
                t.frame.destroy()
        self.tabs.clear()
        if hasattr(self, "stack"):
            self.select(None)

    def close_current(self):
        if self.current is not None:
            self.close_tab(self.current)

    def go_home(self):
        self.nb.select(self.tab_main)
        self.select(None)

    def show_home(self):
        if hasattr(self, "stack") and self.current is None:
            self.select(None)

    def render_home(self, outer):
        banner = tk.Frame(outer, bg=P["bg_surface"], pady=10)
        banner.pack(fill="x")
        if self.active:
            label(banner, f"●  Connected to  {self.active.name}", fg=P["success"], font=F["ui_b"]).pack(side="left", padx=16)
            label(banner, f"{len(self.cat)} reports  ·  each opens in its own tab  ·  ⚡ already fetched (Refresh fetches again)",
                  fg=P["fg_muted"], font=F["ui_sm"]).pack(side="left")
        else:
            label(banner, "⚠  No client selected: add or pick one in the OAuth tab.", fg=P["warn"],
                  font=F["ui_b"]).pack(side="left", padx=16)
            button(banner, "Open OAuth tab", lambda: self.nb.select(self.tab_oauth), kind="accent").pack(side="left")
        tk.Frame(outer, bg=P["border"], height=1).pack(fill="x")
        sc = Scrollable(outer, P["bg_base"])
        sc.pack(fill="both", expand=True)
        grid = sc.body
        self.report_buttons = []
        cards = []
        for s in self.cat.sections:
            color = P["sect"][s.color % 6]
            card = tk.Frame(grid, bg=P["bg_surface"], highlightbackground=P["border"], highlightthickness=1)
            tk.Frame(card, bg=color, width=4).pack(side="left", fill="y")
            body = tk.Frame(card, bg=P["bg_surface"])
            body.pack(side="left", fill="both", expand=True, padx=10, pady=8)
            label(body, f"{s.icon}  {s.name}", fg=color, font=F["ui_b"]).pack(anchor="w", pady=(0, 4))
            tk.Frame(body, bg=color, height=1).pack(fill="x", pady=(0, 6))
            for ep in self.cat.in_section(s.id):
                cached = self.active is not None and self.cache_key(ep) in self.cache
                b = button(body, ("⚡ " if cached else "") + ep.label, lambda e=ep: self.open_report(e), anchor="w")
                b.pack(fill="x", pady=2)
                ToolTip(b, ep.help)
                if not self.active or self.busy:
                    b.config(state="disabled")
                self.report_buttons.append(b)
            cards.append(card)
        state = {"cols": 0}

        def relayout(width):
            cols = max(1, min(4, width // 330))
            if cols == state["cols"]:
                return
            state["cols"] = cols
            for i, c in enumerate(cards):
                c.grid(row=i // cols, column=i % cols, padx=10, pady=8, sticky="nsew")
            for c in range(6):
                grid.grid_columnconfigure(c, weight=1 if c < cols else 0, uniform="cards" if c < cols else "")

        sc.canvas.bind("<Configure>", lambda e: (sc.canvas.itemconfigure(sc._win, width=e.width), relayout(e.width)), add="+")
        relayout(max(990, self.root.winfo_width()))

    # ── running a report ──────────────────────────────────────────────────

    def open_report(self, ep: Endpoint, force: bool = False):
        if not self.active:
            self.nb.select(self.tab_oauth)
            return
        key = self.cache_key(ep)
        if not force and key in self.cache:
            self.status("⚡ From memory (Refresh to fetch again)", "success")
            self.open_tab(self.cache[key])
            return
        if ep.slow and not force and not messagebox.askyesno(
                ep.label, f"{ep.help}\n\nThis can take several minutes in a large org. Continue?"):
            return
        try:
            gc = self.client()
        except ValueError as e:  # a region this version does not know
            self.show_error(ep.label, str(e))
            return
        progress = self.progress_fn()

        def work(cancel):
            return fetch(gc, ep, cancel=cancel, progress=progress)

        def done(res: Result):
            self.cache[key] = res
            what = "fetched" if ep.is_object else f"{res.count} records"
            self.status(f"✓  {ep.label}: {what}, {res.calls} API calls", "success")
            self.logline("OK", f"{ep.label}: {what} in {res.calls} calls")
            self.open_tab(res)

        self.run_task(ep.label, work, done)

    def refresh(self):
        if self.current is not None and not self.busy:
            self.open_report(self.current.res.endpoint, force=True)

    def cancel_task(self):
        if self.cancel:
            self.cancel.cancel()
            self.status("Cancelling...", "warn")

    # ── one report's sub-tab ──────────────────────────────────────────────

    def render_result(self, tab: ReportTab):
        res, parent = tab.res, tab.frame
        ep = res.endpoint
        hdr = tk.Frame(parent, bg=P["bg_surface"])
        hdr.pack(fill="x")
        left = tk.Frame(hdr, bg=P["bg_surface"])
        left.pack(side="left", padx=14, pady=8)
        label(left, ep.label, fg=P["accent"], font=F["heading"]).pack(side="left", padx=(0, 12))
        tab.count_lbl = label(left, "", fg=P["fg_secondary"])
        tab.count_lbl.pack(side="left")
        label(left, f"   ·   {self.active.name if self.active else ''}   ·   fetched {res.fetched_at.replace('T', ' ')}",
              fg=P["fg_muted"], font=F["ui_sm"]).pack(side="left")
        right = tk.Frame(hdr, bg=P["bg_surface"])
        right.pack(side="right", padx=10)
        b = button(right, "🔄 Refresh", self.refresh, kind="ghost")
        b.configure(bg=P["bg_surface"])
        b.pack(side="left", padx=3)
        ToolTip(b, f"Fetch again from the API ({MOD_LABEL}R)")
        b = button(right, "⬇ Raw JSON", self.export_json, kind="ghost")
        b.configure(bg=P["bg_surface"])
        b.pack(side="left", padx=3)
        ToolTip(b, "The API's own JSON, page by page")
        button(right, f"⬇ Export CSV  ({MOD_LABEL}S)", self.export_csv, kind="accent").pack(side="left", padx=3)
        tk.Frame(parent, bg=P["border"], height=1).pack(fill="x")
        if ep.is_object:
            cols = [Column("Key", "k"), Column("Value", "v")]
            rows = [[k, v] for k, v in data.flatten_object(res.obj)]
            records = None
        else:
            cols = data.table_columns(ep.columns, res.records)
            rows = data.rows(res.records, cols)
            records = res.records
        tab.table = ResultTable(self, parent, cols, rows, records, ep, on_change=lambda: self._update_count(tab))

    def _update_count(self, tab: ReportTab | None = None):
        tab = tab or self.current
        t = tab.table if tab else None
        if t and tab.count_lbl is not None and tab.count_lbl.winfo_exists():
            shown, total = len(t.visible), len(t.rows)
            unit = "fields" if t.records is None else "records"
            tab.count_lbl.config(text=f"{total} {unit}" if shown == total else f"{shown} of {total} {unit}")

    def _focus_search(self):
        if self.current is not None and self.current.table is not None:
            self.current.table.search.focus_set()

    def _default_name(self, ext: str) -> str:
        res: Result = self.current.res
        org = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (self.active.name if self.active else "org"))
        return f"{org}_{res.endpoint.key}_{_dt.datetime.now():%Y%m%d_%H%M}.{ext}"

    def export_csv(self):
        if self.current is None or self.current.table is None:
            return
        t = self.current.table
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=self._default_name("csv"),
                                            filetypes=[("CSV", "*.csv"), ("All files", "*.*")], title="Export CSV")
        if not path:
            return
        n = data.write_csv(path, [c.header for c in t.cols], t.visible_rows())
        filt = " (filtered)" if len(t.visible) != len(t.rows) else ""
        self.status(f"✓  {n} rows saved{filt}: {os.path.basename(path)}", "success")
        self.logline("OK", f"CSV saved: {path} ({n} rows{filt})")

    def export_json(self):
        if self.current is None:
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", initialfile=self._default_name("json"),
                                            filetypes=[("JSON", "*.json"), ("All files", "*.*")], title="Save raw JSON")
        if path:
            data.write_json(path, self.current.res.raw)
            self.status(f"✓  JSON saved: {os.path.basename(path)}", "success")
            self.logline("OK", f"JSON saved: {path}")

    def show_members(self, queue_rec: dict):
        try:
            gc = self.client()
        except ValueError as e:
            self.show_error("Queue members", str(e))
            return
        name = queue_rec.get("name", "")

        def done(members):
            rows = [[m.get("name", ""), data.cell(data.resolve(m, "routingStatus.status")),
                     data.cell(m.get("joined")), m.get("memberBy", ""), m.get("id", "")] for m in members]
            self.status(f"✓  {len(members)} members in {name}", "success")
            popup_table(self.root, f"Members of {name}", ["Name", "Routing Status", "Joined", "Member By", "User ID"], rows)

        self.run_task(f"Members of {name}", lambda c: queue_members(gc, queue_rec["id"], c, self.progress_fn()), done)

    def show_error(self, title: str, msg: str):
        hint = ""
        if "HTTP 401" in msg or "invalid_client" in msg:
            hint = "\n\nCheck the region, Client ID and secret in the OAuth tab."
        elif "HTTP 403" in msg:
            hint = "\n\nThe OAuth client's roles lack the permission for this report."
        elif "Cannot reach" in msg or "Network error" in msg:
            hint = "\n\nCheck the network and the proxy (Config tab)."
        messagebox.showerror(title, msg + hint)

    # ── OAuth tab ─────────────────────────────────────────────────────────

    def build_oauth(self):
        tab = self.tab_oauth
        wrap = tk.Frame(tab, bg=P["bg_base"])
        wrap.pack(fill="both", expand=True, padx=14, pady=14)
        lf = tk.Frame(wrap, bg=P["bg_surface"], highlightbackground=P["border"], highlightthickness=1, width=280)
        lf.pack(side="left", fill="y")
        lf.pack_propagate(False)
        label(lf, "Saved clients", fg=P["accent"], font=F["ui_b"]).pack(anchor="w", padx=12, pady=(12, 4))
        tk.Frame(lf, bg=P["accent"], height=1).pack(fill="x", padx=12, pady=(0, 6))
        self.client_list = tk.Listbox(lf, bg=P["bg_surface"], fg=P["fg_primary"], selectbackground=P["accent_dim"],
                                      selectforeground=P["fg_primary"], relief="flat", bd=0, highlightthickness=0,
                                      font=F["ui"], activestyle="none", exportselection=False)
        self.client_list.pack(fill="both", expand=True, padx=12)
        self.client_list.bind("<<ListboxSelect>>", lambda e: self._pick_client())
        row = tk.Frame(lf, bg=P["bg_surface"])
        row.pack(fill="x", padx=12, pady=10)
        button(row, "＋ New", self._new_client, kind="normal").pack(side="left")
        self.del_btn = button(row, "Delete", self._delete_client, kind="danger")
        self.del_btn.pack(side="right")

        rf = tk.Frame(wrap, bg=P["bg_surface"], highlightbackground=P["border"], highlightthickness=1)
        rf.pack(side="left", fill="both", expand=True, padx=(12, 0))
        label(rf, "Client details", fg=P["accent"], font=F["ui_b"]).pack(anchor="w", padx=16, pady=(12, 4))
        tk.Frame(rf, bg=P["accent"], height=1).pack(fill="x", padx=16, pady=(0, 10))
        form = tk.Frame(rf, bg=P["bg_surface"])
        form.pack(fill="x", padx=16)

        def field(text, widget):
            r = tk.Frame(form, bg=P["bg_surface"])
            r.pack(fill="x", pady=4)
            label(r, text, fg=P["fg_secondary"], width=14, anchor="w").pack(side="left")
            widget(r).pack(side="left", fill="x", expand=True)

        self.f_name = self.f_id = self.f_secret = None
        self.f_region = tk.StringVar(value="us_east_1")
        field("Name", lambda r: self._mk("f_name", entry(r, 40)))
        field("Region", lambda r: ttk.Combobox(r, textvariable=self.f_region, values=REGIONS, state="readonly", width=24))
        field("Client ID", lambda r: self._mk("f_id", entry(r, 48)))
        field("Client secret", lambda r: self._mk("f_secret", entry(r, 48, show="•")))
        show = tk.BooleanVar(value=False)
        tk.Checkbutton(rf, text="Show secret", variable=show, bg=P["bg_surface"], fg=P["fg_secondary"],
                       selectcolor=P["bg_raised"], activebackground=P["bg_surface"], font=F["ui_sm"], bd=0,
                       highlightthickness=0,
                       command=lambda: self.f_secret.config(show="" if show.get() else "•")).pack(anchor="w", padx=126)
        btns = tk.Frame(rf, bg=P["bg_surface"])
        btns.pack(fill="x", padx=16, pady=14)
        button(btns, "Save and use", self._save_client, kind="accent").pack(side="left")
        button(btns, "Test connection", self._test_client, kind="normal").pack(side="left", padx=8)
        info = ("The OAuth client must use the Client Credentials grant (Admin › Integrations › OAuth) with roles that\n"
                "can read what you want to export. Pyramid only reads: every call it makes is a GET.\n\n"
                f"Saved in {self.store.path}\n"
                "Secrets are stored in plain text; on macOS and Linux only your user can read the file.")
        label(rf, info, fg=P["fg_muted"], font=F["ui_sm"], justify="left").pack(anchor="w", padx=16, pady=(4, 12))
        self._editing: str | None = None
        self._fill_clients()

    def _mk(self, attr, widget):
        setattr(self, attr, widget)
        return widget

    def _fill_clients(self):
        self.client_list.delete(0, "end")
        names = [c.name for c in self.store.clients()]
        for n in names:
            self.client_list.insert("end", n)
        if self.active and self.active.name in names:
            i = names.index(self.active.name)
            self.client_list.selection_set(i)
            self._load_form(self.active)
        self.del_btn.config(state="normal" if self.active else "disabled")

    def _load_form(self, c: OAuthClient):
        self._editing = c.name
        for w, v in ((self.f_name, c.name), (self.f_id, c.client_id), (self.f_secret, c.client_secret)):
            w.delete(0, "end")
            w.insert(0, v)
        self.f_region.set(c.region if c.region in REGIONS else "us_east_1")

    def _pick_client(self):
        sel = self.client_list.curselection()
        if not sel:
            return
        c = self.store.client(self.client_list.get(sel[0]))
        if not c:
            return
        self._load_form(c)
        self.use_client(c)

    def use_client(self, c: OAuthClient):
        self.active = c
        self.store.set("last_client", c.name)
        self._client_label()
        self.del_btn.config(state="normal")
        self.logline("INFO", f"Using client {c.name} ({c.region})")
        if hasattr(self, "stack"):
            self.close_all_tabs()

    def _new_client(self):
        self._editing = None
        self.client_list.selection_clear(0, "end")
        for w in (self.f_name, self.f_id, self.f_secret):
            w.delete(0, "end")
        self.f_region.set("us_east_1")
        self.f_name.focus_set()

    def _form_client(self) -> OAuthClient | None:
        c = OAuthClient(self.f_name.get().strip(), self.f_region.get(), self.f_id.get().strip(), self.f_secret.get().strip())
        if not all((c.name, c.region, c.client_id, c.client_secret)):
            messagebox.showerror("Missing fields", "Name, region, Client ID and secret are all required.")
            return None
        import uuid
        try:
            uuid.UUID(c.client_id)
        except ValueError:
            messagebox.showerror("Client ID", "The Client ID should look like xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx.")
            return None
        return c

    def _save_client(self):
        c = self._form_client()
        if not c:
            return
        try:
            self.store.put_client(c, old_name=self._editing)
        except (OSError, ValueError) as e:
            messagebox.showerror("Could not save", str(e))
            return
        if self._editing:
            self.forget_client(self._editing)
        self.forget_client(c.name)
        self._editing = c.name
        self.use_client(c)
        self._fill_clients()
        self.status(f"✓  Client {c.name} saved", "success")
        self.logline("OK", f"Client saved: {c.name}")

    def _delete_client(self):
        name = self._editing or (self.active.name if self.active else None)
        if not name or not messagebox.askyesno("Delete client", f"Delete the saved client {name!r}?"):
            return
        self.store.delete_client(name)
        self.forget_client(name)
        if self.active and self.active.name == name:
            self.active = None
            self.store.set("last_client", "")
        self._client_label()
        self._new_client()
        self._fill_clients()
        self.show_home()
        self.logline("OK", f"Client deleted: {name}")

    def _test_client(self):
        c = self._form_client()
        if not c:
            return
        proxy = self.store.proxy() if self.proxy_on.get() else None

        def work(cancel):
            gc = GenesysClient(c.region, c.client_id, c.client_secret, proxy=proxy)
            gc.token()
            org = gc.get("/api/v2/organizations/me", cancel=cancel)
            return org, gc.token_expires_in()

        def done(out):
            org, ttl = out
            msg = f"Connected to {org.get('name', '?')} ({c.region}). Token valid for {ttl // 3600}h {ttl % 3600 // 60}m."
            self.status("✓  " + msg, "success")
            self.logline("OK", msg)
            messagebox.showinfo("Connection OK", msg)

        self.run_task("Test connection", work, done)

    # ── Config tab ────────────────────────────────────────────────────────

    def build_config(self):
        outer = tk.Frame(self.tab_config, bg=P["bg_base"])
        outer.pack(fill="both", expand=True, padx=30, pady=16)

        def section(title):
            tk.Frame(outer, bg=P["border"], height=1).pack(fill="x", pady=(16, 6))
            label(outer, title, bg=P["bg_base"], fg=P["accent"], font=F["ui_b"]).pack(anchor="w")

        section("Proxy")
        r = tk.Frame(outer, bg=P["bg_base"])
        r.pack(fill="x", pady=4)
        label(r, "Proxy URL", bg=P["bg_base"], fg=P["fg_secondary"], width=16, anchor="w").pack(side="left")
        url = entry(r, 52)
        url.insert(0, self.store.get("proxy_url"))
        url.pack(side="left")
        label(r, "  e.g. http://proxy.corp.example:8080", bg=P["bg_base"], fg=P["fg_muted"], font=F["ui_sm"]).pack(side="left")
        r2 = tk.Frame(outer, bg=P["bg_base"])
        r2.pack(fill="x")
        tk.Checkbutton(r2, text="Use the proxy", variable=self.proxy_on, bg=P["bg_base"], fg=P["fg_primary"],
                       selectcolor=P["bg_raised"], activebackground=P["bg_base"], font=F["ui"], bd=0,
                       highlightthickness=0).pack(side="left", padx=(128, 0))

        def save_proxy():
            u = url.get().strip()
            if not valid_proxy(u):
                messagebox.showerror("Proxy URL", "The proxy URL must start with http:// or https://")
                return
            self.store.set("proxy_url", u)
            self.store.set("proxy_enabled", bool(self.proxy_on.get() and u))
            self.clients.clear()
            self.status("✓  Proxy saved", "success")
            self.logline("OK", f"Proxy {'on: ' + redact_url(u) if self.proxy_on.get() and u else 'off'}")

        button(outer, "Save proxy", save_proxy, kind="accent").pack(anchor="w", padx=128, pady=6)

        section("Appearance")
        r3 = tk.Frame(outer, bg=P["bg_base"])
        r3.pack(fill="x", pady=4)
        label(r3, "Theme", bg=P["bg_base"], fg=P["fg_secondary"], width=16, anchor="w").pack(side="left")
        tv = tk.StringVar(value=self.theme)
        for val, text in (("light", "☀  Light"), ("dark", "🌙  Dark")):
            tk.Radiobutton(r3, text=text, value=val, variable=tv, command=lambda: self.set_theme(tv.get()),
                           bg=P["bg_base"], fg=P["fg_primary"], selectcolor=P["bg_raised"],
                           activebackground=P["bg_base"], font=F["ui"], bd=0, highlightthickness=0).pack(side="left", padx=(0, 14))

        section("Storage")
        r4 = tk.Frame(outer, bg=P["bg_base"])
        r4.pack(fill="x", pady=4)
        label(r4, "Config file", bg=P["bg_base"], fg=P["fg_secondary"], width=16, anchor="w").pack(side="left")
        label(r4, str(self.store.path), bg=P["bg_base"], font=F["mono_sm"]).pack(side="left")
        button(outer, "Open the config folder", lambda: open_path(str(self.store.path.parent)), kind="ghost").pack(anchor="w", padx=124, pady=4)

    def _proxy_toggled(self):
        url = self.store.get("proxy_url")
        on = bool(self.proxy_on.get() and url)
        self.store.set("proxy_enabled", on)
        self.clients.clear()
        if hasattr(self, "status_lbl"):
            self.status(f"Proxy {'ON: ' + redact_url(url) if on else 'OFF'}", "warn" if on else "fg_secondary")

    def set_theme(self, theme: str):
        if theme == self.theme:
            return
        self.theme = theme
        self.store.set("theme", theme)
        P.update(DARK if theme == "dark" else LIGHT)
        current = self.nb.index(self.nb.select()) if hasattr(self, "nb") else 0
        self.build()
        self.nb.select(current)

    def toggle_theme(self):
        self.set_theme("light" if self.theme == "dark" else "dark")

    # ── Log tab ───────────────────────────────────────────────────────────

    def build_log(self):
        outer = tk.Frame(self.tab_log, bg=P["bg_base"])
        outer.pack(fill="both", expand=True, padx=8, pady=8)
        bar = tk.Frame(outer, bg=P["bg_base"])
        bar.pack(fill="x", pady=(0, 6))
        label(bar, "Level", bg=P["bg_base"], fg=P["fg_muted"]).pack(side="left")
        cb = ttk.Combobox(bar, textvariable=self.log_level, values=LEVELS, width=8, state="readonly")
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self._render_log())
        button(bar, "Clear", self._clear_log, kind="ghost").pack(side="right")
        button(bar, "Save log...", self._save_log, kind="ghost").pack(side="right", padx=6)
        frame = tk.Frame(outer, bg=P["bg_surface"])
        frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(frame, bg=P["bg_surface"], fg=P["fg_primary"], font=F["mono_sm"], relief="flat",
                                bd=6, wrap="word", state="disabled", highlightthickness=0)
        sb = ttk.Scrollbar(frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log_text.pack(fill="both", expand=True)
        colors = {"DEBUG": P["fg_muted"], "INFO": P["fg_primary"], "OK": P["success"], "WARN": P["warn"], "ERROR": P["danger"]}
        for lvl, col in colors.items():
            self.log_text.tag_config(lvl, foreground=col)
        self._render_log()

    def _append_log(self, ts, level, msg):
        self.log_text.config(state="normal")
        self.log_text.insert("end", f"{ts}  {level:<5}  {msg}\n", level)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _render_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")
        for ts, level, msg in self.log_lines:
            if self._shown(level):
                self._append_log(ts, level, msg)

    def _clear_log(self):
        self.log_lines.clear()
        self._render_log()

    def _save_log(self):
        path = filedialog.asksaveasfilename(defaultextension=".log", initialfile=f"pyramid_{_dt.datetime.now():%Y%m%d_%H%M}.log")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                for ts, level, msg in self.log_lines:
                    f.write(f"{ts}  {level:<5}  {msg}\n")

    # ── Help tab ──────────────────────────────────────────────────────────

    def build_help(self):
        sc = Scrollable(self.tab_help, P["bg_base"])
        sc.pack(fill="both", expand=True)
        body = sc.body
        general = [
            ("Getting started", "1. OAuth tab: add a Client Credentials OAuth client of your org, pick its region, "
             "Save and use, then Test connection.\n2. Main tab: click a report. Results stay in memory for this "
             "session; ⚡ marks the ones already fetched.\n3. Search, sort by any column, right-click a row for "
             "more, then Export CSV or Raw JSON."),
            ("Keyboard", f"Esc  back to the reports    {MOD_LABEL}F  search    {MOD_LABEL}S  export CSV    "
             f"{MOD_LABEL}R or F5  refresh    double-click a row  every field of the record"),
            ("Exports", "CSV is UTF-8 with the columns you see, in the order and filter you see (Excel and Power BI "
             "read it directly). Cells that would run as spreadsheet formulas get a leading apostrophe. Raw JSON is "
             "the API's own answer, page by page, for scripts and migrations."),
            ("Rate limits and errors", "Pyramid waits and retries when Genesys Cloud answers 429 (too many requests) "
             "or a temporary 5xx, honouring Retry-After; Cancel stops it at once. A 403 means the OAuth client's roles "
             "lack a permission; nothing is cached after an error."),
            ("Command line and web", "pyramid export users queues --client NAME -o exports/   exports without the window.\n"
             "pyramid export all --client NAME -o snapshot/   every report at once.\n"
             "pyramid web   the same reports in your browser, on this computer."),
        ]
        self._help_block(body, "📖  Using Pyramid", P["sect"][0], general)
        for s in self.cat.sections:
            items = [(e.label, e.help) for e in self.cat.in_section(s.id)]
            self._help_block(body, f"{s.icon}  {s.name}", P["sect"][s.color % 6], items)
        tk.Frame(body, bg=P["bg_base"], height=20).pack()

    def _help_block(self, body, title, color, items):
        h = tk.Frame(body, bg=P["bg_surface"])
        h.pack(fill="x", padx=16, pady=(16, 0))
        tk.Frame(h, bg=color, width=5).pack(side="left", fill="y")
        label(h, title, fg=color, font=F["heading"]).pack(side="left", padx=10, pady=6)
        for t, d in items:
            f = tk.Frame(body, bg=P["bg_surface"], highlightbackground=P["border"], highlightthickness=1)
            f.pack(fill="x", padx=22, pady=3)
            tk.Frame(f, bg=color, width=3).pack(side="left", fill="y")
            inner = tk.Frame(f, bg=P["bg_surface"])
            inner.pack(side="left", fill="both", expand=True, padx=10, pady=6)
            label(inner, t, font=F["ui_b"]).pack(anchor="w")
            label(inner, d, fg=P["fg_secondary"], justify="left", wraplength=900).pack(anchor="w")

    # ── About tab ─────────────────────────────────────────────────────────

    def build_about(self):
        outer = tk.Frame(self.tab_about, bg=P["bg_base"])
        outer.pack(fill="both", expand=True, padx=34, pady=28)
        tk.Frame(outer, bg=P["accent"], height=3).pack(fill="x", pady=(0, 14))
        top = tk.Frame(outer, bg=P["bg_base"])
        top.pack(fill="x")
        SieveLogo(top, self.nb, self.tab_about).pack(side="left", padx=(0, 24))
        info = tk.Frame(top, bg=P["bg_base"])
        info.pack(side="left", anchor="n")
        label(info, APP_TITLE, bg=P["bg_base"], fg=P["accent"], font=F["hero"]).pack(anchor="w")
        label(info, f"Version {__version__}", bg=P["bg_base"], fg=P["fg_secondary"]).pack(anchor="w", pady=(2, 10))
        label(info, "Developed by Ighor Toth  ·  toth@ighor.com", bg=P["bg_base"], font=F["ui_b"]).pack(anchor="w")
        link = label(info, REPO_URL, bg=P["bg_base"], fg=P["accent"], cursor="hand2")
        link.pack(anchor="w")
        link.bind("<Button-1>", lambda e: webbrowser.open(REPO_URL))
        label(info, "MIT License  ·  written with Claude Code as co-author", bg=P["bg_base"], fg=P["fg_muted"],
              font=F["ui_sm"]).pack(anchor="w", pady=(6, 0))
        label(info, "An independent tool: not a Genesys product, not affiliated with or endorsed by Genesys.",
              bg=P["bg_base"], fg=P["danger"], font=F["ui_sm"]).pack(anchor="w", pady=(2, 0))
        tk.Frame(outer, bg=P["border"], height=1).pack(fill="x", pady=16)
        rows = [("Reports", f"{len(self.cat)} in {len(self.cat.sections)} sections"),
                ("API", "Genesys Cloud Platform API v2 (REST, read only)"),
                ("Config file", str(self.store.path)),
                ("Python", f"{sys.version.split()[0]}  ·  Tk {tk.TkVersion}")]
        for k, v in rows:
            r = tk.Frame(outer, bg=P["bg_base"])
            r.pack(fill="x", pady=2)
            label(r, k, bg=P["bg_base"], fg=P["fg_secondary"], font=F["ui_b"], width=14, anchor="w").pack(side="left")
            label(r, v, bg=P["bg_base"], font=F["mono_sm"]).pack(side="left")


class SieveLogo(tk.Canvas):
    """The pyramid of bricks: a Sieve of Eratosthenes runs over it while the About tab is open."""

    ROWS, BW, BH, PAD = 18, 9, 6, 8

    def __init__(self, parent, nb: ttk.Notebook, tab):
        w = self.BW * self.ROWS + self.PAD * 2
        h = self.BH * self.ROWS + self.PAD * 2
        super().__init__(parent, width=w, height=h, bg=P["bg_base"], highlightthickness=0, bd=0)
        self.nb, self.tab, self.h = nb, tab, h
        self.items, n = {}, 0
        for r in range(self.ROWS):
            for c in range(self.ROWS - r):
                n += 1
                x = self.PAD + c * self.BW + r * self.BW // 2
                y = h - self.PAD - self.BH - r * self.BH
                self.items[n] = self.create_rectangle(x, y, x + self.BW - 1, y + self.BH - 1, fill="#cd853f", outline="#7a4a1a")
        self.total = n
        self.prime = [True] * (n + 1)
        self.prime[0] = self.prime[1] = False
        for i in range(2, int(n ** 0.5) + 1):
            if self.prime[i]:
                for j in range(i * i, n + 1, i):
                    self.prime[j] = False
        self.order, self.step, self.timer = [], 0, None
        nb.bind("<<NotebookTabChanged>>", self._tab, add="+")
        self.bind("<Destroy>", lambda e: self._stop())

    def _tab(self, _e=None):
        try:
            if self.nb.select() == str(self.tab):
                self._restart()
            else:
                self._stop()
        except tk.TclError:
            pass

    def _restart(self):
        self._stop()
        for i in self.items.values():
            self.itemconfig(i, fill="#cd853f", outline="#7a4a1a")
        self.order = list(range(1, self.total + 1))
        random.shuffle(self.order)
        self.step = 0
        self.timer = self.after(120, self._tick)

    def _tick(self):
        if self.step > 0:
            prev = self.order[self.step - 1]
            self._paint(prev, ("#ffd700", "#b8860b") if self.prime[prev] else ("#7a8fa6", "#5a6f86"))
        if self.step >= len(self.order):
            self.timer = self.after(3000, self._restart)
            return
        self._paint(self.order[self.step], ("#5090ff", "#1a4acc"))
        self.step += 1
        self.timer = self.after(90, self._tick)

    def _paint(self, n, colors):
        self.itemconfig(self.items[n], fill=colors[0], outline=colors[1])

    def _stop(self):
        if self.timer:
            try:
                self.after_cancel(self.timer)
            except tk.TclError:
                pass
            self.timer = None


class ReportTab:
    """One opened report in Main: its result and its widgets (rebuilt on theme changes)."""

    def __init__(self, res: Result):
        self.res = res
        self.frame: tk.Frame | None = None
        self.table: ResultTable | None = None
        self.count_lbl: tk.Label | None = None


class ResultTable:
    """Sortable, searchable table of one result; sorting and filtering keep each other."""

    def __init__(self, app: App, parent, cols: list[Column], rows: list[list[str]], records, ep: Endpoint,
                 on_change: Callable[[], None] = lambda: None):
        self.app, self.cols, self.rows, self.records, self.ep = app, cols, rows, records, ep
        self.on_change = on_change
        self.order = list(range(len(rows)))
        self.visible = list(self.order)
        self.sort_col: int | None = None
        self.sort_rev = False
        bar = tk.Frame(parent, bg=P["bg_base"])
        bar.pack(fill="x", padx=12, pady=(8, 4))
        label(bar, "🔍", bg=P["bg_base"], fg=P["fg_secondary"]).pack(side="left")
        self.query = tk.StringVar()
        self.search = entry(bar, 44, textvariable=self.query)
        self.search.pack(side="left", padx=6)
        self.query.trace_add("write", lambda *_: self.apply())
        button(bar, "✕", lambda: self.query.set(""), kind="ghost").pack(side="left")
        hint = f"{MOD_LABEL}F search  ·  {MOD_LABEL}W close tab  ·  Esc reports  ·  double-click a row for every field"
        if "members" in ep.actions:
            hint += "  ·  right-click a queue for its members"
        label(bar, hint, bg=P["bg_base"], fg=P["fg_muted"], font=F["ui_sm"]).pack(side="right")
        frame = tk.Frame(parent, bg=P["bg_base"])
        frame.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        ids = [f"c{i}" for i in range(len(cols))]
        self.tree = ttk.Treeview(frame, columns=["#"] + ids, show="headings", selectmode="extended")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.tree.pack(fill="both", expand=True)
        self.tree.heading("#", text="#")
        self.tree.column("#", width=48, minwidth=40, anchor="e", stretch=False)
        for i, c in enumerate(cols):
            sample = [len(r[i]) for r in rows[:300]] or [0]
            width = max(80, min(420, 9 * max(len(c.header), int(sorted(sample)[int(len(sample) * 0.9)]))))
            self.tree.heading(ids[i], text=c.header, command=lambda i=i: self.sort(i))
            self.tree.column(ids[i], width=width, minwidth=60, anchor="w")
        self.tree.tag_configure("odd", background=P["bg_surface"])
        self.tree.tag_configure("even", background=P["bg_raised"] if app.theme == "dark" else "#f6f8fa")
        self.tree.bind("<Double-1>", self._details)
        self.tree.bind("<Return>", self._details)
        self.tree.bind("<Button-3>", self._menu)
        self.tree.bind("<Button-2>" if IS_MAC else "<Control-Button-1>", self._menu)
        self.apply()

    def visible_rows(self) -> list[list[str]]:
        return [self.rows[i] for i in self.visible]

    def apply(self):
        q = self.query.get().strip().lower()
        self.visible = [i for i in self.order if not q or any(q in v.lower() for v in self.rows[i])]
        self.tree.delete(*self.tree.get_children())
        for n, i in enumerate(self.visible):
            self.tree.insert("", "end", iid=str(i), values=[i + 1] + self.rows[i], tags=("even" if n % 2 else "odd",))
        self.on_change()

    def sort(self, col: int):
        self.sort_rev = not self.sort_rev if self.sort_col == col else False
        self.sort_col = col

        def key(i):
            v = self.rows[i][col]
            try:
                return (0, float(v), "")
            except ValueError:
                return (1, 0.0, v.lower())

        self.order = sorted(range(len(self.rows)), key=key, reverse=self.sort_rev)
        for j, c in enumerate(self.cols):
            arrow = (" ▼" if self.sort_rev else " ▲") if j == col else ""
            self.tree.heading(f"c{j}", text=c.header + arrow)
        self.apply()

    def _row_at(self, event) -> int | None:
        iid = self.tree.identify_row(event.y) if event and hasattr(event, "y") and event.y else self.tree.focus()
        return int(iid) if iid else None

    def _details(self, event=None):
        i = self._row_at(event)
        if i is None:
            return
        if self.records is None:
            text = f"{self.rows[i][0]}\n\n{self.rows[i][1]}"
        else:
            text = json.dumps(self.records[i], indent=2, ensure_ascii=False)
        popup_text(self.app.root, f"{self.ep.label}: {self.rows[i][0]}", text)

    def _menu(self, event):
        i = self._row_at(event)
        if i is None:
            return
        self.tree.selection_set(str(i))
        col = self.tree.identify_column(event.x)
        cidx = int(col[1:]) - 2 if col and col != "#1" else None
        m = tk.Menu(self.tree, tearoff=0, bg=P["bg_surface"], fg=P["fg_primary"], activebackground=P["accent_dim"],
                    activeforeground=P["fg_primary"], bd=0, font=F["ui"])
        if cidx is not None and 0 <= cidx < len(self.cols):
            m.add_command(label=f"Copy {self.cols[cidx].header}", command=lambda: self._copy(self.rows[i][cidx]))
        m.add_command(label="Copy row", command=lambda: self._copy("\t".join(self.rows[i])))
        m.add_command(label="Show every field", command=lambda: self._details_index(i))
        if "members" in self.ep.actions and self.records is not None:
            m.add_separator()
            m.add_command(label="Show queue members", command=lambda: self.app.show_members(self.records[i]))
        m.add_separator()
        m.add_command(label=f"Export CSV  ({MOD_LABEL}S)", command=self.app.export_csv)
        m.tk_popup(event.x_root, event.y_root)

    def _details_index(self, i):
        self.tree.focus(str(i))
        self._details(None)

    def _copy(self, text):
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(text)
        self.app.status("Copied to the clipboard", "success")


def popup_text(root, title, text):
    win = tk.Toplevel(root)
    win.title(title)
    win.configure(bg=P["bg_surface"])
    win.geometry("640x560")
    frame = tk.Frame(win, bg=P["bg_surface"])
    frame.pack(fill="both", expand=True, padx=10, pady=10)
    t = tk.Text(frame, bg=P["bg_raised"], fg=P["fg_primary"], font=F["mono_sm"], relief="flat", bd=8, wrap="none",
                highlightthickness=0)
    sb = ttk.Scrollbar(frame, command=t.yview)
    t.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    t.pack(fill="both", expand=True)
    t.insert("1.0", text)
    t.config(state="disabled")
    row = tk.Frame(win, bg=P["bg_surface"])
    row.pack(fill="x", padx=10, pady=(0, 10))

    def copy():
        root.clipboard_clear()
        root.clipboard_append(text)

    button(row, "Copy", copy, kind="normal").pack(side="left")
    button(row, "Close", win.destroy, kind="ghost").pack(side="right")
    win.bind("<Escape>", lambda e: win.destroy())


def popup_table(root, title, headers, rows):
    win = tk.Toplevel(root)
    win.title(title)
    win.configure(bg=P["bg_surface"])
    win.geometry("760x480")
    frame = tk.Frame(win, bg=P["bg_surface"])
    frame.pack(fill="both", expand=True, padx=10, pady=10)
    ids = [f"c{i}" for i in range(len(headers))]
    tree = ttk.Treeview(frame, columns=ids, show="headings")
    sb = ttk.Scrollbar(frame, command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    tree.pack(fill="both", expand=True)
    for i, h in enumerate(headers):
        tree.heading(ids[i], text=h)
        tree.column(ids[i], width=140 if i else 220)
    for r in rows:
        tree.insert("", "end", values=r)
    row = tk.Frame(win, bg=P["bg_surface"])
    row.pack(fill="x", padx=10, pady=(0, 10))

    def save():
        path = filedialog.asksaveasfilename(parent=win, defaultextension=".csv", initialfile="members.csv")
        if path:
            data.write_csv(path, headers, rows)

    label(row, f"{len(rows)} members", fg=P["fg_secondary"]).pack(side="left")
    button(row, "Close", win.destroy, kind="ghost").pack(side="right")
    button(row, "Export CSV", save, kind="accent").pack(side="right", padx=6)
    win.bind("<Escape>", lambda e: win.destroy())


def open_path(path: str):
    try:
        if IS_WIN:
            os.startfile(path)  # type: ignore[attr-defined]
        elif IS_MAC:
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except OSError as e:
        messagebox.showerror("Open folder", f"Could not open {path}: {e}")


TERMS = """By using this software you agree to the following.

1.  AUTHORIZED USE ONLY
    Use this tool only with Genesys Cloud organizations for which you hold valid
    administrative credentials and explicit permission. Unauthorized access to
    computer systems may be a criminal offence (e.g. CFAA, Computer Misuse Act,
    Lei nº 12.737/2012).

2.  DATA PRIVACY
    Reports can contain personal data (names, e-mail addresses, login dates).
    You are responsible for handling it under the privacy law that applies to
    you (GDPR, LGPD, ...) and your organization's policies. Pyramid sends data
    only to Genesys Cloud and keeps nothing except the files you export.

3.  CREDENTIAL STORAGE
    OAuth Client IDs and secrets are stored in plain text in pyramid.cfg in your
    user profile. Do not use this tool on shared or untrusted computers.

4.  NO WARRANTY
    The software is provided "as is", without warranty of any kind, under the
    MIT License. You use it entirely at your own risk."""


def terms_dialog(root: tk.Tk) -> bool:
    accepted = {"v": False}
    dlg = tk.Toplevel(root)
    dlg.title(f"Terms of use · {APP_TITLE}")
    dlg.configure(bg=P["bg_base"])
    dlg.resizable(False, False)
    tk.Frame(dlg, bg=P["accent"], height=4).pack(fill="x")
    label(dlg, APP_TITLE, bg=P["bg_base"], fg=P["accent"], font=F["title"]).pack(anchor="w", padx=26, pady=(18, 0))
    label(dlg, "Terms of use  ·  shown once", bg=P["bg_base"], fg=P["fg_muted"]).pack(anchor="w", padx=26)
    t = tk.Text(dlg, width=84, height=24, bg=P["bg_raised"], fg=P["fg_primary"], font=F["mono_sm"], relief="flat",
                bd=10, highlightthickness=0)
    t.insert("1.0", TERMS)
    t.config(state="disabled")
    t.pack(padx=26, pady=12)
    row = tk.Frame(dlg, bg=P["bg_base"])
    row.pack(anchor="e", padx=26, pady=(0, 18))

    def close(v):
        accepted["v"] = v
        dlg.destroy()

    button(row, "Decline", lambda: close(False), kind="danger").pack(side="left", padx=(0, 8))
    button(row, "I accept", lambda: close(True), kind="accent").pack(side="left")
    dlg.protocol("WM_DELETE_WINDOW", lambda: close(False))
    dlg.update_idletasks()
    x = (dlg.winfo_screenwidth() - dlg.winfo_width()) // 2
    y = (dlg.winfo_screenheight() - dlg.winfo_height()) // 3
    dlg.geometry(f"+{x}+{y}")
    dlg.grab_set()
    root.wait_window(dlg)
    return accepted["v"]


def main() -> int:
    if IS_WIN:
        try:  # crisp text on high-DPI screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    root.withdraw()
    store = Store()
    P.update(DARK if store.get("theme", "light") == "dark" else LIGHT)
    apply_style(root)
    if not store.get_bool("terms_accepted") and not os.environ.get("PYRAMID_ACCEPT_TERMS"):
        if not terms_dialog(root):
            root.destroy()
            return 0
        store.set("terms_accepted", True)
    root.deiconify()
    App(root, store)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
