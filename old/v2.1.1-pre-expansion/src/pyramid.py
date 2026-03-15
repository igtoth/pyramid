# pyinstaller --noconsole --onefile --icon=pyramid.ico pyramid.py

# ── Standard library ──────────────────────────────────────────────────────────
from importlib.metadata import version, PackageNotFoundError
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font, scrolledtext
from io import BytesIO
import base64
import os
import configparser
import datetime
import uuid
import time
import csv
import json
import threading
import logging

# ── Third-party ───────────────────────────────────────────────────────────────
from PIL import Image, ImageTk, ImageDraw
import PureCloudPlatformClientV2
from PureCloudPlatformClientV2.rest import ApiException

"""
Pyramid API Management
=========================
A desktop tool for querying and exporting data from Genesys Cloud via the
PureCloudPlatformClientV2 SDK.

Change log:
- v1.0.0 (12/04/2024): Initial version
- v1.1.0 (03/27/2024): Added all users with queues
- v1.1.1 (04/03/2024): Added all external contacts
- v1.1.2 (08/03/2024): Added Save JSON, Edges, Settings
- v2.0.0: Bug fixes, token caching, 13 new API methods, search bar,
          right-click copy, keyboard shortcuts, retry/backoff
- v2.1.1 (Current):
    • Dark / Light theme toggle in About tab (persisted in registry)
    • Restart to apply theme change
- v2.1.0:
    • Removed all company-specific branding
    • Full visual redesign: dark corporate theme, custom ttk.Style,
      button hover effects, coloured section badges, animated status bar,
      consistent typography with Segoe UI / Helvetica
    • Proxy URL now user-configurable (stored in registry)
    • Configurable proxy label (no hardcoded company name)
"""

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# ╔══════════════════════════════════════════════════════════════════════════════
# ║  DESIGN TOKENS
# ╚══════════════════════════════════════════════════════════════════════════════


def create_logo():
    """Generate the animated pyramid brick logo (random highlight brick)."""
    import random as _rnd
    _rnd.seed(int(time.time()))
    img = Image.new('RGBA', (200, 200), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    brick_width  = 8
    brick_height = 5
    pyramid_height = 18
    start_x = (img.width  - (brick_width  * pyramid_height)) // 2
    start_y =  img.height - brick_height
    random_row   = _rnd.randint(0, pyramid_height - 1)
    random_col   = _rnd.randint(0, pyramid_height - random_row - 1)
    random_color = (_rnd.randint(0, 255), _rnd.randint(0, 255), _rnd.randint(0, 255), 255)
    for row in range(pyramid_height):
        for col in range(pyramid_height - row):
            top_left     = (start_x + col * brick_width + row * brick_width // 2,
                            start_y - row * brick_height)
            bottom_right = (top_left[0] + brick_width, top_left[1] + brick_height)
            fill_color   = random_color if (row == random_row and col == random_col) else 'sandybrown'
            draw.rectangle([top_left, bottom_right], fill=fill_color, outline='black')
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode('utf-8')


DARK_PALETTE = {
    # Background layers
    "bg_base":    "#0f1117",
    "bg_surface": "#1a1d27",
    "bg_raised":  "#22263a",
    "bg_hover":   "#2e3452",
    "bg_active":  "#374060",
    # Borders
    "border":     "#2e3452",
    "border_hi":  "#4a5275",
    # Text
    "fg_primary":  "#e2e8f0",
    "fg_secondary":"#8893a8",
    "fg_muted":    "#4a5275",
    # Accents
    "accent":      "#5b8af5",
    "accent_hi":   "#7da1f8",
    "accent_dim":  "#2e4a8c",
    "success":     "#34d399",
    "warn":        "#fbbf24",
    "danger":      "#f87171",
    # Section badge colours
    "sect_0":  "#5b8af5",
    "sect_1":  "#a78bfa",
    "sect_2":  "#34d399",
    "sect_3":  "#fbbf24",
    "sect_4":  "#fb923c",
    "sect_5":  "#f472b6",
}

LIGHT_PALETTE = {
    # Background layers — true Windows system colours
    "bg_base":    "#f0f0f0",   # GetSysColor(COLOR_BTNFACE)
    "bg_surface": "#ffffff",   # white panels / lists
    "bg_raised":  "#e1e1e1",   # raised buttons
    "bg_hover":   "#cce4f7",   # hover  (Windows accent light)
    "bg_active":  "#99caf5",   # pressed
    # Borders
    "border":     "#adadad",   # standard Windows border
    "border_hi":  "#0078d4",   # Windows accent blue
    # Text
    "fg_primary":  "#000000",
    "fg_secondary":"#444444",
    "fg_muted":    "#767676",
    # Accents — Windows 10/11 accent blue
    "accent":      "#0078d4",
    "accent_hi":   "#005a9e",
    "accent_dim":  "#cce4f7",
    "success":     "#107c10",
    "warn":        "#ca5010",
    "danger":      "#c42b1c",
    # Section badge colours
    "sect_0":  "#0078d4",
    "sect_1":  "#744da9",
    "sect_2":  "#107c10",
    "sect_3":  "#ca5010",
    "sect_4":  "#da3b01",
    "sect_5":  "#e3008c",
}

PALETTE = LIGHT_PALETTE.copy()   # light is default; dark loaded at runtime if set

FONTS = {
    "ui":      ("Segoe UI", 9),
    "ui_b":    ("Segoe UI", 9, "bold"),
    "ui_sm":   ("Segoe UI", 8),
    "heading": ("Segoe UI", 11, "bold"),
    "title":   ("Segoe UI", 13, "bold"),
    "mono":    ("Consolas", 9),
    "mono_sm": ("Consolas", 8),
}


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  CONFIG
# ╚══════════════════════════════════════════════════════════════════════════════

class AppConfig:
    RELEASE_VERSION        = "2.1.2"
    RELEASE_DATE           = "2025"
    APP_NAME               = "Pyramid API Management"
    ROOT_TITLE             = f"{APP_NAME}  v{RELEASE_VERSION}"
    SDK_VERSION_FALLBACK   = "197.0.0"
    TOKEN_CACHE_TTL        = 82800   # 23 h
    MAX_RETRIES            = 3
    RETRY_BACKOFF          = 2       # seconds (doubles per attempt)
    CONFIG_DIR             = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Pyramid")
    CONFIG_FILE            = os.path.join(CONFIG_DIR, "pyramid.cfg")


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  THEME SETUP
# ╚══════════════════════════════════════════════════════════════════════════════

def apply_theme(root: tk.Tk):
    """Configure ttk.Style and root window based on current PALETTE."""
    root.configure(bg=PALETTE["bg_base"])

    s = ttk.Style(root)
    # Use 'vista' as base for light (crisp Windows look), 'clam' for dark
    is_dark = PALETTE["bg_base"] == DARK_PALETTE["bg_base"]
    try:
        s.theme_use("vista" if not is_dark else "clam")
    except tk.TclError:
        s.theme_use("clam")

    # ── Notebook (tabs) ──────────────────────────────────────────────────────
    s.configure("TNotebook",
                background=PALETTE["bg_base"],
                borderwidth=0)
    s.configure("TNotebook.Tab",
                background=PALETTE["bg_raised"],
                foreground=PALETTE["fg_secondary"],
                padding=[14, 6],
                font=FONTS["ui_b"],
                borderwidth=0)
    s.map("TNotebook.Tab",
          background=[("selected", PALETTE["bg_surface"]),
                      ("active",   PALETTE["bg_hover"])],
          foreground=[("selected", PALETTE["accent_hi"]),
                      ("active",   PALETTE["fg_primary"])])

    # ── Frame / LabelFrame ───────────────────────────────────────────────────
    s.configure("TFrame", background=PALETTE["bg_base"])
    s.configure("Card.TFrame", background=PALETTE["bg_surface"])

    s.configure("TLabelframe",
                background=PALETTE["bg_surface"],
                bordercolor=PALETTE["border"],
                relief="flat", borderwidth=1)
    s.configure("TLabelframe.Label",
                background=PALETTE["bg_surface"],
                foreground=PALETTE["fg_secondary"],
                font=FONTS["ui_sm"])

    # ── Scrollbar ────────────────────────────────────────────────────────────
    s.configure("TScrollbar",
                background=PALETTE["bg_raised"],
                troughcolor=PALETTE["bg_surface"],
                borderwidth=0, arrowsize=12,
                relief="flat")
    s.map("TScrollbar", background=[("active", PALETTE["bg_hover"])])

    # ── Separator ────────────────────────────────────────────────────────────
    s.configure("TSeparator", background=PALETTE["border"])

    # ── Treeview ─────────────────────────────────────────────────────────────
    s.configure("Treeview",
                background=PALETTE["bg_surface"],
                fieldbackground=PALETTE["bg_surface"],
                foreground=PALETTE["fg_primary"],
                font=FONTS["ui_sm"],
                rowheight=22,
                borderwidth=0,
                relief="flat")
    s.configure("Treeview.Heading",
                background=PALETTE["bg_raised"],
                foreground=PALETTE["accent"],
                font=FONTS["ui_b"],
                relief="groove" if not is_dark else "flat",
                borderwidth=1 if not is_dark else 0)
    s.map("Treeview",
          background=[("selected", PALETTE["accent_dim"])],
          foreground=[("selected", PALETTE["fg_primary"])])
    s.map("Treeview.Heading",
          background=[("active", PALETTE["bg_hover"])])

    # ── Combobox ─────────────────────────────────────────────────────────────
    s.configure("TCombobox",
                fieldbackground=PALETTE["bg_raised"],
                background=PALETTE["bg_raised"],
                foreground=PALETTE["fg_primary"],
                arrowcolor=PALETTE["accent"],
                bordercolor=PALETTE["border"],
                font=FONTS["ui"])
    s.map("TCombobox",
          fieldbackground=[("readonly", PALETTE["bg_raised"])],
          background=[("active", PALETTE["bg_hover"])])

    # ── Entry ────────────────────────────────────────────────────────────────
    s.configure("TEntry",
                fieldbackground=PALETTE["bg_raised"],
                foreground=PALETTE["fg_primary"],
                bordercolor=PALETTE["border"],
                font=FONTS["ui"])


def _tk_button(parent, text, command, kind="normal", width=None, **kw):
    """
    Factory for themed tk.Button with hover + press colour animation.
    kind: "normal" | "accent" | "danger" | "ghost"
    """
    colours = {
        "normal": (PALETTE["bg_raised"],  PALETTE["fg_primary"],  PALETTE["bg_hover"],  PALETTE["bg_active"]),
        "accent": (PALETTE["accent_dim"], PALETTE["accent_hi"],   PALETTE["accent"],    PALETTE["accent_hi"]),
        "danger": ("#3d1515",             PALETTE["danger"],      "#5a1f1f",            "#7a2929"),
        "ghost":  (PALETTE["bg_base"],    PALETTE["fg_secondary"],PALETTE["bg_surface"],PALETTE["bg_raised"]),
    }
    bg, fg, hover_bg, press_bg = colours.get(kind, colours["normal"])
    is_light = PALETTE["bg_base"] == LIGHT_PALETTE["bg_base"]

    btn_kw = dict(
        text=text, command=command,
        bg=bg, fg=fg,
        relief="raised" if is_light and kind == "normal" else "flat",
        activebackground=press_bg, activeforeground=fg,
        bd=0,
        padx=10, pady=5,
        cursor="hand2",
        font=FONTS["ui"],
        **kw
    )
    if width:
        btn_kw["width"] = width

    btn = tk.Button(parent, **btn_kw)

    def _on_enter(e):  btn.config(bg=hover_bg)
    def _on_leave(e):  btn.config(bg=bg)
    def _on_press(e):  btn.config(bg=press_bg)
    def _on_release(e):btn.config(bg=hover_bg)

    btn.bind("<Enter>",          _on_enter)
    btn.bind("<Leave>",          _on_leave)
    btn.bind("<ButtonPress-1>",  _on_press)
    btn.bind("<ButtonRelease-1>",_on_release)
    return btn


def _tk_label(parent, text="", **kw):
    defaults = dict(bg=PALETTE["bg_surface"], fg=PALETTE["fg_primary"], font=FONTS["ui"])
    defaults.update(kw)
    return tk.Label(parent, text=text, **defaults)


def _tk_entry(parent, width=30, show=None, **kw):
    defaults = dict(
        bg=PALETTE["bg_raised"], fg=PALETTE["fg_primary"],
        insertbackground=PALETTE["accent"],
        relief="flat", bd=0, highlightthickness=1,
        highlightbackground=PALETTE["border"],
        highlightcolor=PALETTE["accent"],
        font=FONTS["ui"], width=width
    )
    defaults.update(kw)
    if show:
        defaults["show"] = show
    e = tk.Entry(parent, **defaults)
    return e


def _tk_listbox(parent, **kw):
    defaults = dict(
        bg=PALETTE["bg_raised"], fg=PALETTE["fg_primary"],
        selectbackground=PALETTE["accent_dim"],
        selectforeground=PALETTE["accent_hi"],
        relief="flat", bd=0,
        highlightthickness=1,
        highlightbackground=PALETTE["border"],
        highlightcolor=PALETTE["accent"],
        font=FONTS["ui"],
        activestyle="none",
    )
    defaults.update(kw)
    return tk.Listbox(parent, **defaults)


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  MAIN APPLICATION
# ╚══════════════════════════════════════════════════════════════════════════════

class GCApplication:

    def __init__(self, master: tk.Tk):
        self.master = master
        self.master.title(AppConfig.ROOT_TITLE)

        # Load theme preference from registry before applying
        _theme = self._load_setting("theme", "light")
        if _theme == "light":
            PALETTE.update(LIGHT_PALETTE)
        else:
            PALETTE.update(DARK_PALETTE)

        self.master.configure(bg=PALETTE["bg_base"])
        apply_theme(master)

        # Proxy config — loaded from config file
        self.use_proxy_var = tk.IntVar(master)
        self.proxy_server  = self._load_setting("proxy_url", "")
        _proxy_on_start    = self._load_setting("proxy_enabled", "0")
        if _proxy_on_start == "1" and self.proxy_server:
            self.use_proxy_var.set(1)

        # Registry data
        self.saved_data = {}
        self.saved_data = self.load_from_registry()

        # Token cache
        self._token_cache = {'api_client': None, 'expires_at': 0,
                             'region': None, 'client_id': None}

        # Progress / spinner
        self.spinner_chars = ['█' * i + '░' * (10 - i) for i in range(1, 11)]

        # Widget references
        self.bottom_frame             = None
        self.selected_client_name     = None
        self.buttons                  = []
        self.cancel_button            = None
        self.back_button              = None
        self.version_tab              = None
        self.log_tab                  = None
        self.log_text                 = None
        self.config_tab               = None
        self.progress_bar             = None
        self.log_level_var            = None
        self.client_listbox           = _tk_listbox(master)
        self.refresh_client_list()
        self.client_name_label        = None
        self.status_message_label     = None
        self.spinner_active           = True
        self.last_update_time         = time.time()
        self.region_name_entry        = None
        self.client_id_entry          = None
        self.client_secret_entry      = None
        self.selected_region_name     = None
        self.selected_client_id       = None
        self.selected_client_secret   = None
        self.name_entry               = None
        self.active_client_id         = None
        self.is_view_active           = False
        self.task_complete_executed   = False
        self.is_updating_fields       = None
        self.region_name_combobox     = None
        self.editing_entry            = None
        self.editing_entry_widget     = None
        self.cancel_event             = threading.Event()
        self.task_thread              = None
        self.cancel_process_button    = None
        self._current_raw_data        = None
        self._current_method          = None
        # In-memory cache: (client_id, method) → raw_data
        self._data_cache              = {}

        self.initialize_ui()

    # ──────────────────────────────────────────────────────────────────────────
    # INIT
    # ──────────────────────────────────────────────────────────────────────────

    def initialize_data(self):
        try:
            self.saved_data = self.load_from_registry()
        except MyCustomError as e:
            self.cancel_process(user=False, message="Error updating registry", error_message=str(e))

    def set_app_icon(self):
        image_data = base64.b64decode(self._icon_b64())
        photo_image = tk.PhotoImage(data=image_data)
        self.master.iconphoto(False, photo_image)

    def set_app_config(self):
        sw, sh = self.master.winfo_screenwidth(), self.master.winfo_screenheight()
        ww = int(sw * 0.72)
        wh = int(sh * 0.72)
        self.master.geometry(f"{ww}x{wh}+{(sw-ww)//2}+{(sh-wh)//2}")
        self.master.minsize(900, 600)

    def setup_tab_control(self):
        self.tab_control = ttk.Notebook(self.master)
        self.main_tab    = tk.Frame(self.tab_control, bg=PALETTE["bg_base"])
        self.oauth_tab   = tk.Frame(self.tab_control, bg=PALETTE["bg_base"])
        self.config_tab  = tk.Frame(self.tab_control, bg=PALETTE["bg_base"])
        self.log_tab     = tk.Frame(self.tab_control, bg=PALETTE["bg_base"])
        self.help_tab    = tk.Frame(self.tab_control, bg=PALETTE["bg_base"])
        self.version_tab = tk.Frame(self.tab_control, bg=PALETTE["bg_base"])
        self.tab_control.add(self.main_tab,    text='  Main  ')
        self.tab_control.add(self.oauth_tab,   text='  OAuth  ')
        self.tab_control.add(self.config_tab,  text='  Config  ')
        self.tab_control.add(self.log_tab,     text='  Log  ')
        self.tab_control.add(self.help_tab,    text='  ❓ Help  ')
        self.tab_control.add(self.version_tab, text='  About  ')
        # NOTE: bottom_frame must be packed BEFORE tab_control so it is not hidden
        # create_bottom_area() is called from create_widgets before tab_control.pack

    def create_widgets(self):
        self.create_bottom_area()          # pack bottom bar FIRST
        self.tab_control.pack(expand=1, fill='both', padx=0, pady=0)
        self.create_main_view()
        self.create_oauth_view()
        self.create_config_view()
        self.create_log_view()
        self.create_help_view()
        self.create_version_view()

    def initialize_ui(self):
        self.set_app_icon()
        self.initialize_data()
        self.set_app_config()
        self.setup_tab_control()
        self.create_widgets()
        self.master.bind('<Escape>',   lambda e: self.show_customer_selection_view())
        self.master.bind('<Control-s>',lambda e: self._save_current_csv())

    def _save_current_csv(self):
        if self._current_raw_data and self._current_method:
            self.save_file(self._current_raw_data, self.selected_client_name,
                           self._current_method, "csv")

    # ──────────────────────────────────────────────────────────────────────────
    # CONFIG FILE  (clients + settings → %APPDATA%/Pyramid/pyramid.cfg)
    # ──────────────────────────────────────────────────────────────────────────

    def _get_config(self):
        """Return a ConfigParser loaded from disk (creates file/dir if missing)."""
        os.makedirs(AppConfig.CONFIG_DIR, exist_ok=True)
        cfg = configparser.ConfigParser()
        if os.path.exists(AppConfig.CONFIG_FILE):
            cfg.read(AppConfig.CONFIG_FILE, encoding="utf-8")
        return cfg

    def _write_config(self, cfg):
        """Write ConfigParser back to disk."""
        os.makedirs(AppConfig.CONFIG_DIR, exist_ok=True)
        with open(AppConfig.CONFIG_FILE, "w", encoding="utf-8") as fh:
            cfg.write(fh)

    def load_from_registry(self):
        """Load OAuth clients from config file (named load_from_registry for compat)."""
        cfg = self._get_config()
        if not cfg.has_section("clients"):
            return {}
        return dict(cfg.items("clients"))

    def _load_setting(self, name, default=""):
        cfg = self._get_config()
        if cfg.has_section("settings"):
            return cfg.get("settings", name, fallback=default)
        return default

    def _save_setting(self, name, value):
        cfg = self._get_config()
        if not cfg.has_section("settings"):
            cfg.add_section("settings")
        cfg.set("settings", name, value)
        self._write_config(cfg)

    # ──────────────────────────────────────────────────────────────────────────
    # PROXY
    # ──────────────────────────────────────────────────────────────────────────

    def apply_proxy_setting(self, *args):
        proxy_enabled = self.use_proxy_var.get() == 1
        if proxy_enabled and self.proxy_server:
            # Basic sanity check — must start with http:// or https://
            if not self.proxy_server.startswith(("http://", "https://")):
                self.append_log(
                    f"Proxy URL rejected (must start with http:// or https://): {self.proxy_server}",
                    "WARN")
                PureCloudPlatformClientV2.configuration.proxy = None
                return
        PureCloudPlatformClientV2.configuration.proxy = self.proxy_server if proxy_enabled else None
        state = f"enabled: {self.proxy_server}" if proxy_enabled else "disabled"
        self.append_log(f"Proxy {state}", "INFO")
        if self.status_message_label:
            self.status_message_label.config(
                text=f"Proxy {'ON' if proxy_enabled else 'OFF'}",
                fg=PALETTE["warn"] if proxy_enabled else PALETTE["fg_secondary"])

    # ──────────────────────────────────────────────────────────────────────────
    # ICON (minimal base64 placeholder — replace with real icon)
    # ──────────────────────────────────────────────────────────────────────────

    def _icon_b64(self):
        # 1×1 transparent PNG — replace with real 32×32 icon
        return "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

    # ──────────────────────────────────────────────────────────────────────────
    # TOOLTIP
    # ──────────────────────────────────────────────────────────────────────────

    class ToolTip:
        def __init__(self, widget, text):
            self.widget = widget
            self.text   = text
            self.tip    = None
            widget.bind("<Enter>", self._show)
            widget.bind("<Leave>", self._hide)

        def _show(self, e=None):
            try:
                x, y, _, _ = self.widget.bbox("insert")
            except Exception:
                x, y = 0, 0
            x += self.widget.winfo_rootx() + 22
            y += self.widget.winfo_rooty() + 22
            self.tip = tk.Toplevel(self.widget)
            self.tip.wm_overrideredirect(True)
            self.tip.wm_geometry(f"+{x}+{y}")
            lbl = tk.Label(self.tip, text=self.text,
                           bg=PALETTE["bg_raised"], fg=PALETTE["fg_primary"],
                           relief="flat", bd=1,
                           highlightbackground=PALETTE["border"],
                           highlightthickness=1,
                           font=FONTS["ui_sm"], padx=8, pady=4)
            lbl.pack()

        def _hide(self, e=None):
            if self.tip:
                self.tip.destroy()
                self.tip = None

    # ──────────────────────────────────────────────────────────────────────────
    # SPINNER
    # ──────────────────────────────────────────────────────────────────────────

    def update_spinner(self, index=0, text=None):
        index = int(round(index))
        self.last_update_time = time.time()
        adjusted_index = index     # FIX: always initialised

        if index == -1:
            display_text  = text or ""
            color         = PALETTE["danger"]
        else:
            if index > 100:
                cycle          = 200
                adjusted_index = index % cycle
                if adjusted_index > 100:
                    adjusted_index = 200 - adjusted_index
                spinner_index = adjusted_index // 10
            else:
                spinner_index = index // 10

            spinner_index = max(0, min(spinner_index, len(self.spinner_chars) - 1))
            bar           = self.spinner_chars[spinner_index]
            pct           = adjusted_index if index > 100 else index

            if index > 100:
                progress_text = f"PLEASE HOLD ON… [{bar}]"
            else:
                progress_text = f"{min(int(pct), 100)}%  [{bar}]"

            label_text   = 'Processing…' if text is None else text
            display_text = f"{label_text}   {progress_text}"
            color        = PALETTE["accent"]

        if hasattr(self, 'status_message_label') and self.status_message_label:
            self.status_message_label.config(text=display_text, fg=color)

    # ──────────────────────────────────────────────────────────────────────────
    # TASK MANAGEMENT
    # ──────────────────────────────────────────────────────────────────────────

    def long_running_task(self, method, callback):
        client_id = self.active_client_id
        self.spinner_active   = True
        self.last_update_time = time.time()
        self.cancel_event.clear()

        method_functions = {
            "users":          self.get_all_users_from_customer,
            "usersqueues":    self.get_all_usersqueues_from_customer,
            "externalcontacts": self.get_all_external_contacts,
            "groups":         self.get_all_groups,
            "teams":          self.get_all_teams,
            "edges":          self.get_telephony_providers_edges,
            "phonenumbers":   self.get_telephony_dids,
            "sites":          self.get_telephony_sites,
            "trunks":         self.get_telephony_trunks,
            "flows":          self.get_all_flows_from_customer,
            "ivrs":           self.get_architect_ivrs,
            "schedules":      self.get_architect_schedules,
            "schedulegroups": self.get_architect_schedulegroups,
            "queues":         self.get_all_queues_from_customer,
            "skills":         self.get_all_skills_from_customer,
            "wrapupcodes":    self.get_routing_wrapupcodes,
            "languages":      self.get_routing_languages,
            "oauth_clients":  self.get_oauth_clients,
            "auth_roles":     self.get_authorization_roles,
            "settings":       self.get_settings,
            "license_users":  self.get_all_license_users,
            "integrations":   self.get_all_integrations,
        }

        fetch_data = method_functions.get(method)

        while not self.cancel_event.is_set():
            try:
                if fetch_data:
                    self.append_log(f"Calling {method} API method…", "DEBUG")
                    raw_data = fetch_data()
                    self.append_log(f"API method returned: {type(raw_data).__name__} len={len(raw_data) if raw_data else 0}", "DEBUG")
                else:
                    raise ValueError(f"Unsupported method: {method}")

                if self.cancel_event.is_set() or (time.time() - self.last_update_time > 60):
                    raise Exception("Operation cancelled" if self.cancel_event.is_set() else "Timeout occurred")

                self.master.after(0, callback, raw_data, client_id, method, None)
                return

            except Exception as e:
                import traceback
                # Truncate raw exception to avoid leaking tokens/secrets in log
                err_summary = str(e)[:300]
                self.append_log(f"Exception in task '{method}': {type(e).__name__}: {err_summary}", "ERROR")
                self.append_log(traceback.format_exc()[:2000], "DEBUG")
                self.spinner_active = False
                self.cancel_event.set()
                self.master.after(0, callback, None, client_id, method, e)
                return

        if self.cancel_event.is_set():
            return

    def on_task_complete(self, raw_data, client_id, method, exception=None):
        self.spinner_active = False
        self.task_complete_executed = True

        if exception:
            self.append_log(f"Task error: {exception}", "ERROR")
            if self.progress_bar: self.progress_bar.stop()
            if self.status_message_label:
                self.status_message_label.config(text=f"Error: {exception}", fg=PALETTE["danger"])
        else:
            count = len(raw_data) if isinstance(raw_data, list) else (len(raw_data) if raw_data else 0)
            self.append_log(f"Task completed — {count} records", "OK")
            if self.progress_bar: self.progress_bar.stop()
            if self.status_message_label:
                self.status_message_label.config(text="✓  Task completed", fg=PALETTE["success"])
            self.toggle_button("back")
            self._data_cache[(client_id, method)] = raw_data   # store for instant reuse
            self.show_results(raw_data, client_id, method, exception)
            if self.task_complete_executed:
                return

    def cancel_process(self, user=True, message=None, error_message=None):
        def _wait():
            if self.task_thread:
                self.task_thread.join()
                self.status_message_label.config(text="Cancelled by user", fg=PALETTE["warn"])
                self.cancel_event.clear()
                self.change_buttons_states(disable=None, buttons=self.buttons)
            else:
                self.status_message_label.config(text="Cancelling…", fg=PALETTE["warn"])

        if user:
            self.cancel_event.set()
            self.status_message_label.config(text="Cancelling task…", fg=PALETTE["warn"])
            threading.Thread(target=_wait).start()
            self.toggle_button(None)
        else:
            threading.Thread(target=_wait).start()
            self.status_message_label.config(text=f"{message}", fg=PALETTE["danger"])
            messagebox.showinfo("Error", f"{message}\n\n{error_message}")
            self.status_message_label.config(text="Ready", fg=PALETTE["fg_secondary"])
            if not self.cancel_event.is_set():
                self.cancel_event.set()
            if self.cancel_button:
                self.toggle_button(None)

    def start_task(self, method, force_refresh=False):
        client_id = self.active_client_id
        cache_key = (client_id, method)

        # Serve from cache when available and not forcing a refresh
        if not force_refresh and cache_key in self._data_cache:
            self.append_log(f"Cache hit: {method}", "INFO")
            self.toggle_button("back")
            if self.status_message_label:
                self.status_message_label.config(text="⚡  Loaded from cache", fg=PALETTE["success"])
            self.show_results(self._data_cache[cache_key], client_id, method, None)
            return

        self.task_complete_executed = False
        self.change_buttons_states(disable=True, buttons=self.buttons)
        self.spinner_active = True
        self.toggle_button("cancel")

        self.append_log(f"Starting task: {method}", "INFO")
        if self.progress_bar:
            self.progress_bar.start(12)
        if self.status_message_label:
            self.status_message_label.config(text="Processing…", fg=PALETTE["accent"])
            self.update_spinner()

        self.cancel_event.clear()
        self.task_thread = threading.Thread(
            target=self.long_running_task, args=(method, self.on_task_complete))
        self.task_thread.start()

    # ──────────────────────────────────────────────────────────────────────────
    # EXCEPTION DISPLAY
    # ──────────────────────────────────────────────────────────────────────────

    def show_exception_message(self, message):
        self.clear_main_tab()
        f = tk.Frame(self.main_tab, bg=PALETTE["bg_base"])
        f.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        hdr = tk.Frame(f, bg=PALETTE["danger"], height=3)
        hdr.pack(fill="x", pady=(0, 12))

        _tk_label(f, text="⚠  An error occurred",
                  bg=PALETTE["bg_base"], fg=PALETTE["danger"],
                  font=FONTS["heading"]).pack(anchor="w")

        ta = scrolledtext.ScrolledText(f, wrap=tk.WORD, width=80, height=14,
                                       bg=PALETTE["bg_raised"], fg=PALETTE["danger"],
                                       insertbackground=PALETTE["accent"],
                                       font=FONTS["mono_sm"], relief="flat", bd=0)
        ta.pack(fill=tk.BOTH, expand=True, pady=8)
        ta.insert(tk.END, message)
        ta.config(state=tk.DISABLED)

        _tk_button(f, "← Back to Menu",
                   self.show_customer_selection_view, kind="ghost").pack(pady=4)

    # ──────────────────────────────────────────────────────────────────────────
    # RESULTS VIEW
    # ──────────────────────────────────────────────────────────────────────────

    def show_results(self, raw_data, client_id, method, exception=None):
        self._current_raw_data = raw_data
        self._current_method   = method

        if method == "users":
            _remove = [
                'date_last_login','version','chat','primary_contact_info','addresses',
                'manager','images','certifications','biography','employer_info',
                'routing_status','presence','integration_presence','conversation_summary',
                'out_of_office','geolocation','station','authorization','locations',
                'groups','team','languages','acd_auto_answer','language_preference','self_uri'
            ]
            processed_data = self.process_data(raw_data, _remove)
        else:
            processed_data = self.process_data(raw_data, None)

        # ── Header bar ──────────────────────────────────────────────────────
        def build_header(parent):
            hdr = tk.Frame(parent, bg=PALETTE["bg_surface"])
            hdr.pack(fill="x", padx=10, pady=(8, 0))

            # Left: info + cache badge
            info_frame = tk.Frame(hdr, bg=PALETTE["bg_surface"])
            info_frame.pack(side="left", fill="y")

            count = len(processed_data) if isinstance(processed_data, list) else "—"
            _tk_label(info_frame, text=f"{method.upper()}",
                      bg=PALETTE["bg_surface"], fg=PALETTE["accent"],
                      font=FONTS["heading"]).pack(side="left", padx=(0, 12))
            _tk_label(info_frame,
                      text=f"{count} records   •   {self.selected_client_name or '—'}",
                      bg=PALETTE["bg_surface"], fg=PALETTE["fg_secondary"],
                      font=FONTS["ui"]).pack(side="left")

            is_cached = (self.active_client_id, method) in self._data_cache
            _tk_label(info_frame,
                      text="  ⚡ cached" if is_cached else "  🌐 live",
                      bg=PALETTE["bg_surface"],
                      fg=PALETTE["success"] if is_cached else PALETTE["accent"],
                      font=FONTS["ui_sm"]).pack(side="left")

            # Right: Refresh + export buttons
            btn_frame = tk.Frame(hdr, bg=PALETTE["bg_surface"])
            btn_frame.pack(side="right")

            def _refresh():
                if method == "usersqueues":
                    if messagebox.askyesno("Refresh",
                            "Fetching all users + queues can take several minutes.\nRefresh from API?"):
                        self.start_task(method, force_refresh=True)
                else:
                    self.start_task(method, force_refresh=True)

            _tk_button(btn_frame, "🔄  Refresh",
                       _refresh, kind="ghost").pack(side="left", padx=3)

            _tk_button(btn_frame, "⬇  Raw JSON",
                       lambda: self.save_file(raw_data, self.selected_client_name, method, "json"),
                       kind="ghost").pack(side="left", padx=3)

            if method != "settings":
                _src = raw_data if method == "externalcontacts" else processed_data
                _tk_button(btn_frame, "⬇  Export CSV  [Ctrl+S]",
                           lambda: self.save_file(_src, self.selected_client_name, method, "csv"),
                           kind="accent").pack(side="left", padx=3)

            # Thin accent separator
            sep = tk.Frame(parent, bg=PALETTE["accent"], height=2)
            sep.pack(fill="x", padx=10, pady=(4, 0))

        # ── Text view (settings / org info) ─────────────────────────────────
        def build_text_view(parent):
            ta = scrolledtext.ScrolledText(
                parent, wrap=tk.WORD,
                bg=PALETTE["bg_surface"], fg=PALETTE["fg_primary"],
                font=FONTS["mono"], relief="flat", bd=0,
                insertbackground=PALETTE["accent"])
            ta.pack(padx=12, pady=10, fill=tk.BOTH, expand=True)

            data = processed_data
            text = ""
            if data is None:
                text = "Nothing returned."
            elif exception:
                text = f"Error: {exception}"
            else:
                if hasattr(data, '__dict__'):
                    data = vars(data)
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, dict):
                            text += f"\n{k}:\n"
                            for sk, sv in v.items():
                                text += f"   {sk}: {sv}\n"
                        else:
                            text += f"{k}: {v}\n"
                else:
                    text = str(data)
            ta.insert(tk.END, text)

        # ── Search bar ───────────────────────────────────────────────────────
        def build_search_bar(parent, table):
            sf = tk.Frame(parent, bg=PALETTE["bg_base"])
            sf.pack(fill="x", padx=12, pady=(6, 2))

            _tk_label(sf, text="🔍", bg=PALETTE["bg_base"],
                      fg=PALETTE["fg_secondary"], font=FONTS["ui"]).pack(side="left")

            sv   = tk.StringVar()
            entry = _tk_entry(sf, width=42)
            entry.pack(side="left", padx=6)

            _tk_label(sf, text="[Esc] Back  |  [Ctrl+S] Save CSV",
                      bg=PALETTE["bg_base"], fg=PALETTE["fg_muted"],
                      font=FONTS["ui_sm"]).pack(side="right")

            all_items = []

            def _capture():
                nonlocal all_items
                all_items = [(iid, table.item(iid, 'values')) for iid in table.get_children('')]

            def _filter(*_):
                q = entry.get().lower()
                for iid in table.get_children(''):
                    table.delete(iid)
                for iid, vals in all_items:
                    if not q or any(q in str(v).lower() for v in vals):
                        table.insert('', 'end', iid=iid, values=vals)

            def _clear():
                entry.delete(0, tk.END)
                _filter()

            parent.after(120, _capture)
            entry.bind("<KeyRelease>", _filter)
            sv.trace_add('write', _filter)
            _tk_button(sf, "✕", _clear, kind="ghost").pack(side="left")

        # ── Table view ───────────────────────────────────────────────────────
        def build_table_view(parent):
            BASE_COLS = {
                "users":        ('#','name','username','division','state','last_token_issued'),
                "usersqueues":  ('#','name','username','queues'),
                "queues":       ('#','name','division','description','date_created','member_count'),
                "externalcontacts": ('#','first_name','last_name','title','external_organization','id'),
                "flows":        ('#','name','division','type','description'),
                "edges":        ('#','name','division','description','version','state'),
                "groups":       ('#','name','type','visibility','member_count'),
                "teams":        ('#','name','division','member_count'),
                "sites":        ('#','name','description','primary_sites','state'),
                "trunks":       ('#','name','state','trunk_type','connected'),
                "phonenumbers": ('#','number','number_type','owner_type'),
                "ivrs":         ('#','name','division','dnis'),
                "schedules":    ('#','name','division','description','start','end'),
                "schedulegroups": ('#','name','division','description'),
                "wrapupcodes":  ('#','name','date_created','date_modified'),
                "languages":    ('#','name','state','date_modified'),
                "oauth_clients":('#','name','authorized_grant_type','registered_redirect_uris'),
                "auth_roles":   ('#','name','description','default_role_id'),
                "integrations": ('#','name','integration_type','intended_state','notes'),
                "license_users":('#','id','licenses'),
                "skills":       ('#','name','date_modified','state'),
            }

            # ── context menu ─────────────────────────────────────────────────
            ctx = tk.Menu(parent, tearoff=0,
                          bg=PALETTE["bg_raised"], fg=PALETTE["fg_primary"],
                          activebackground=PALETTE["accent_dim"],
                          activeforeground=PALETTE["accent_hi"],
                          relief="flat", bd=0, font=FONTS["ui_sm"])

            def _copy(event):
                item = table.identify_row(event.y)
                col  = table.identify_column(event.x)
                if item and col:
                    val = table.set(item, col)
                    self.master.clipboard_clear()
                    self.master.clipboard_append(val)
                    self.master.update()

            def _show_ctx(event):
                item = table.identify_row(event.y)
                if item:
                    table.selection_set(item)
                    ctx.entryconfig("Copy cell value", command=lambda: _copy(event))
                    ctx.post(event.x_root, event.y_root)

            ctx.add_command(label="Copy cell value")
            ctx.add_separator()
            ctx.add_command(label="Export CSV  [Ctrl+S]",
                            command=lambda: self._save_current_csv())

            # ── sortable treeview ─────────────────────────────────────────────
            class SortTree(ttk.Treeview):
                def __init__(self, p, **kw):
                    super().__init__(p, **kw)
                    self._scol = None
                    self._srev = False
                    for col in self["columns"]:
                        self.heading(col, text=col.replace('_',' ').title(),
                                     command=lambda c=col: self._sort(c))

                def _sort(self, col):
                    if col == '#':
                        lst = [(int(self.set(c, col)), c) for c in self.get_children('')]
                    else:
                        lst = [(self.set(c, col), c) for c in self.get_children('')]
                    self._srev = not self._srev if self._scol == col else False
                    self._scol = col
                    lst.sort(reverse=self._srev)
                    for i, (_, c) in enumerate(lst):
                        self.move(c, '', i)
                    for c in self["columns"]:
                        arrow = " ↓" if self._scol==c and self._srev else " ↑" if self._scol==c else ""
                        self.heading(c, text=c.replace('_',' ').title() + arrow)

            # ── double-click detail popups ────────────────────────────────────
            def _row_dblclick(event):
                if method == "users":
                    iid = table.focus()
                    if not iid:
                        return
                    try:
                        idx = int(iid[1:]) - 1
                        if 0 <= idx < len(processed_data):
                            _detail_popup("User Details", processed_data[idx])
                    except ValueError as e:
                        self.cancel_process(user=False, message="Error", error_message=str(e))

                if method == "queues":
                    table.unbind("<Double-1>")
                    for item in table.get_children():
                        table.item(item, tags=('dim',))
                    table.tag_configure('dim', foreground=PALETTE["fg_muted"])
                    iid = table.focus()
                    if not iid:
                        return
                    try:
                        idx = int(iid[1:]) - 1
                        if 0 <= idx < len(processed_data):
                            qid  = processed_data[idx]["id"]
                            self.status_message_label.config(
                                text="Fetching queue members…", fg=PALETTE["accent"])
                            self.master.update_idletasks()
                            result = self.get_queue_memberships(qid)
                            if isinstance(result, Exception):
                                messagebox.showerror("Error", f"Failed: {result}")
                                return
                            if not result:
                                messagebox.showinfo("Info", "No members in this queue.")
                                return
                            _members_popup(processed_data[idx]['name'], result)
                            self.status_message_label.config(text="Ready", fg=PALETTE["fg_secondary"])
                            for item in table.get_children():
                                table.item(item, tags=('normal',))
                            table.tag_configure('normal', foreground=PALETTE["fg_primary"])
                            table.bind("<Double-1>", _row_dblclick)
                    except ValueError as e:
                        self.cancel_process(user=False, message="Error", error_message=str(e))

            def _detail_popup(title, data_dict):
                win = tk.Toplevel(self.master)
                win.title(title)
                win.configure(bg=PALETTE["bg_surface"])
                win.geometry("500x420")
                f   = tk.Frame(win, bg=PALETTE["bg_surface"])
                f.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
                ta  = tk.Text(f, wrap="word", height=20, width=58,
                              bg=PALETTE["bg_raised"], fg=PALETTE["fg_primary"],
                              font=FONTS["mono_sm"], relief="flat", bd=0,
                              insertbackground=PALETTE["accent"])
                sb  = tk.Scrollbar(f, command=ta.yview, bg=PALETTE["bg_raised"])
                sb.pack(side="right", fill="y")
                ta.config(yscrollcommand=sb.set)
                ta.pack(side="left", fill=tk.BOTH, expand=True)
                for k, v in data_dict.items():
                    ta.insert(tk.END, f"{k.capitalize()}: {v}\n")
                ta.config(state=tk.DISABLED)
                _tk_button(win, "Close", win.destroy, kind="ghost").pack(pady=6)

            def _members_popup(queue_name, members):
                win = tk.Toplevel(self.master)
                win.title(f"Members — {queue_name}")
                win.configure(bg=PALETTE["bg_surface"])
                win.geometry("480x380")
                tree = ttk.Treeview(win, columns=("name","status","id"), show="headings")
                tree.heading("name",   text="Name")
                tree.heading("status", text="Routing Status")
                tree.heading("id",     text="User ID")
                sb = ttk.Scrollbar(win, command=tree.yview)
                sb.pack(side="right", fill="y")
                tree.configure(yscrollcommand=sb.set)
                tree.pack(fill="both", expand=True, padx=8, pady=8)
                for m in members:
                    tree.insert("", tk.END, values=(
                        m.get("name",""), m.get("routing_status",""), m.get("id","")))
                _tk_button(win, "Close", win.destroy, kind="ghost").pack(pady=6)

            # ── determine columns ─────────────────────────────────────────────
            def _cols():
                if method in BASE_COLS:
                    cols = list(BASE_COLS[method])
                elif processed_data and isinstance(processed_data[0], dict):
                    keys = list(processed_data[0].keys())
                    if 'id' in keys:
                        keys.remove('id')
                    cols = ['#'] + keys
                else:
                    cols = ['#','Data']
                if method not in ("externalcontacts","usersqueues"):
                    if processed_data and isinstance(processed_data[0], dict) \
                            and 'id' in processed_data[0] and 'id' not in cols:
                        cols.append('id')
                return tuple(cols)

            columns = _cols()

            # ── build frame + scrollbars ──────────────────────────────────────
            tf = tk.Frame(parent, bg=PALETTE["bg_base"])
            tf.pack(expand=True, fill=tk.BOTH, padx=12, pady=(4, 8))

            table = SortTree(tf, columns=columns, show='headings', selectmode='extended')

            vsb = ttk.Scrollbar(tf, orient="vertical",   command=table.yview)
            hsb = ttk.Scrollbar(tf, orient="horizontal", command=table.xview)
            vsb.pack(side='right',  fill='y')
            hsb.pack(side='bottom', fill='x')
            table.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

            # Column sizing
            for col in columns:
                w = 30 if col=='#' else 800 if col=='queues' else 55 if col=='state' else 140
                table.column(col, anchor="w", width=w)
                table.heading(col, text=col.replace('_',' ').title())

            table.pack(side='left', fill='both', expand=True)

            # Populate
            for idx, item in enumerate(processed_data, 1):
                if hasattr(item, 'to_json'):
                    item = json.loads(item.to_json())
                start = 1 if columns[0]=='#' else 0
                vals  = [idx] if columns[0]=='#' else []
                for c in columns[start:]:
                    vals.append(item.get(c, 'N/A') if isinstance(item, dict) else 'N/A')
                table.insert('', 'end', iid=f"I{idx:04}", values=vals)

            # Alternating row colours
            table.tag_configure('odd',  background=PALETTE["bg_surface"])
            table.tag_configure('even', background=PALETTE["bg_raised"])
            for i, iid in enumerate(table.get_children('')):
                table.item(iid, tags=('even' if i % 2 == 0 else 'odd',))

            # Bindings
            if method in ("users","queues"):
                table.bind("<Double-1>", _row_dblclick)
            table.bind("<Button-3>", _show_ctx)

            # Search bar (inserted above the table frame — slightly hacky but works)
            build_search_bar(parent, table)
            table.update_idletasks()

        # ── Assemble results page ────────────────────────────────────────────
        self.clear_main_tab()

        if exception:
            self.show_exception_message(f"Error while processing '{method}':\n\n{exception}")
            return

        build_header(self.main_tab)

        if method == "settings":
            build_text_view(self.main_tab)
        else:
            build_table_view(self.main_tab)

    # ──────────────────────────────────────────────────────────────────────────
    # SAVE FILE
    # ──────────────────────────────────────────────────────────────────────────

    def save_file(self, data, customer_name, method, filetype):
        current_date     = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        default_filename = f"{customer_name}_{method}_{current_date}.{filetype}"
        filename = filedialog.asksaveasfilename(
            defaultextension=f".{filetype}",
            filetypes=[(f"{filetype.upper()} Files", f"*.{filetype}"), ("All Files", "*.*")],
            title="Save as",
            initialfile=default_filename)
        if not filename:
            return

        if filetype == "csv":
            if method == "externalcontacts":
                self._write_contacts_csv(data, filename)
            else:
                self._write_generic_csv(data, method, filename)
        elif filetype == "json":
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(json.dumps(data, indent=2, default=str))

    def _write_generic_csv(self, data, method, filename):
        field_map = {
            "usersqueues":  ['name','username','division','queues','skills'],
            "queues":       ['id','name','division','description','date_created','member_count'],
            "skills":       ['id','name','date_modified','state'],
            "edges":        ['id','name','division','description','version','state'],
            "flows":        ['id','name','description','type','division','state'],
            "groups":       ['id','name','type','visibility','member_count'],
            "teams":        ['id','name','division','member_count'],
            "sites":        ['id','name','description','state'],
            "trunks":       ['id','name','state','trunk_type'],
            "phonenumbers": ['id','number','number_type','owner_type'],
            "ivrs":         ['id','name','division','dnis'],
            "schedules":    ['id','name','division','start','end'],
            "schedulegroups":['id','name','division','description'],
            "wrapupcodes":  ['id','name','date_created','date_modified'],
            "languages":    ['id','name','state','date_modified'],
            "oauth_clients":['client_id','name','authorized_grant_type'],
            "auth_roles":   ['id','name','description'],
            "integrations": ['id','name','integration_type','intended_state'],
        }
        with open(filename, mode='w', newline='', encoding='utf-8') as f:
            if not data:
                return
            if method == "users":
                headers = data[0].keys()
                w = csv.writer(f)
                w.writerow(headers)
                for row in data:
                    w.writerow(row.values())
            elif method == "usersqueues":
                fields = field_map["usersqueues"]
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader()
                for user in data:
                    div = user.get('division', {})
                    w.writerow({
                        'name':     user.get('name', ''),
                        'username': user.get('username', ''),
                        'division': div.get('name','N/A') if isinstance(div, dict) else div,
                        'queues':   ', '.join(q['name'] for q in user.get('queues',[]) if isinstance(q,dict)),
                        'skills':   ', '.join(s['name'] for s in user.get('skills',[]) if isinstance(s,dict)),
                    })
            else:
                fields = field_map.get(method)
                if fields and data and isinstance(data[0], dict):
                    w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
                    w.writeheader()
                    for row in data:
                        w.writerow(row)
                elif data and isinstance(data[0], dict):
                    fields = list(data[0].keys())
                    w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
                    w.writeheader()
                    for row in data:
                        w.writerow(row)

    def _write_contacts_csv(self, data, filename):
        def sg(d, keys, default='N/A'):
            for k in keys:
                try:
                    if d is None: return default
                    d = d.get(k, default)
                except AttributeError:
                    return default
            return d

        headers = ["Id","First Name","Last Name","Title","Work Email","Personal Email",
                   "Work Phone","Cell Phone","City","State","Country",
                   "Account Id","Account Name","Account Phone","Account Industry"]
        with open(filename, mode='w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=headers)
            w.writeheader()
            for page in data:
                if not page or 'entities' not in page:
                    continue
                for e in page.get('entities', []):
                    if not e:
                        continue
                    w.writerow({
                        "Id":             e.get('id',''),
                        "First Name":     e.get('first_name',''),
                        "Last Name":      e.get('last_name',''),
                        "Title":          e.get('title',''),
                        "Work Email":     e.get('work_email',''),
                        "Personal Email": e.get('personal_email',''),
                        "Work Phone":     sg(e,['work_phone','display']),
                        "Cell Phone":     e.get('cell_phone',''),
                        "City":           sg(e,['address','city']),
                        "State":          sg(e,['address','state']),
                        "Country":        sg(e,['address','country_code']),
                        "Account Id":     sg(e,['external_organization','id']),
                        "Account Name":   sg(e,['external_organization','name']),
                        "Account Phone":  sg(e,['external_organization','phone_number']),
                        "Account Industry": sg(e,['external_organization','industry']),
                    })

    # ──────────────────────────────────────────────────────────────────────────
    # MAIN VIEW
    # ──────────────────────────────────────────────────────────────────────────

    def change_buttons_states(self, disable=None, buttons=None):
        for b in self.buttons:
            if b.winfo_exists():
                if self.selected_client_name is not None and disable is None:
                    b['state'] = tk.NORMAL if not getattr(b,'initially_disabled',False) else "disabled"
                else:
                    b['state'] = "disabled"

    def confirm_and_start_usersqueues(self):
        if messagebox.askyesno("Confirm",
                               "Fetching all users + their queues can take several minutes.\n\nContinue?"):
            self.start_task("usersqueues")

    def toggle_button(self, button_type):
        if self.cancel_button: self.cancel_button.pack_forget()
        if self.back_button:   self.back_button.pack_forget()
        if button_type == "cancel":
            self.cancel_button.pack(side="left", padx=5, pady=2)
        elif button_type == "back":
            self.back_button.pack(side="left", padx=5, pady=2)

    def show_customer_selection_view(self):
        self.tab_control.select(self.main_tab)   # always snap back to Main tab
        self.clear_main_tab()
        self.is_view_active = True
        self.buttons = []

        outer = tk.Frame(self.main_tab, bg=PALETTE["bg_base"])
        outer.pack(fill=tk.BOTH, expand=True)

        # ── Top banner ───────────────────────────────────────────────────────
        banner = tk.Frame(outer, bg=PALETTE["bg_surface"], pady=10)
        banner.pack(fill="x", padx=0, pady=0)

        if self.selected_client_name:
            msg   = f"●  Connected:  {self.selected_client_name}"
            color = PALETTE["success"]
        else:
            msg   = "⚠  No client selected — go to the OAuth tab first."
            color = PALETTE["warn"]

        _tk_label(banner, text=msg, bg=PALETTE["bg_surface"],
                  fg=color, font=FONTS["ui_b"]).pack(side="left", padx=16)

        sep = tk.Frame(outer, bg=PALETTE["border"], height=1)
        sep.pack(fill="x")

        # ── Section grid ─────────────────────────────────────────────────────
        scroll_canvas = tk.Canvas(outer, bg=PALETTE["bg_base"],
                                  highlightthickness=0, bd=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=scroll_canvas.yview)
        scroll_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        scroll_canvas.pack(side="left", fill="both", expand=True)

        grid_host = tk.Frame(scroll_canvas, bg=PALETTE["bg_base"])
        scroll_canvas.create_window((0,0), window=grid_host, anchor="nw")
        grid_host.bind("<Configure>", lambda e: scroll_canvas.configure(
            scrollregion=scroll_canvas.bbox("all")))

        SECTIONS = [
            {
                "name":  "Users, Teams & Directory",
                "icon":  "👤",
                "idx":   0,
                "items": [
                    ("All Users",               "users"),
                    ("All Users + Queues",       "usersqueues", "confirm"),
                    ("External Contacts",        "externalcontacts"),
                    ("Groups",                  "groups"),
                    ("Teams",                   "teams"),
                ],
            },
            {
                "name":  "Telephony & Architect",
                "icon":  "📞",
                "idx":   1,
                "items": [
                    ("Phone Numbers (DIDs)",    "phonenumbers"),
                    ("Edge Devices",            "edges"),
                    ("Sites",                   "sites"),
                    ("Trunks",                  "trunks"),
                    ("All Flows",               "flows"),
                    ("IVR Configurations",      "ivrs"),
                    ("Schedules",               "schedules"),
                    ("Schedule Groups",         "schedulegroups"),
                ],
            },
            {
                "name":  "Routing & Queues",
                "icon":  "🔀",
                "idx":   2,
                "items": [
                    ("All Queues",              "queues"),
                    ("All Skills",              "skills"),
                    ("Wrap-up Codes",           "wrapupcodes"),
                    ("Routing Languages",       "languages"),
                ],
            },
            {
                "name":  "Security",
                "icon":  "🔐",
                "idx":   3,
                "items": [
                    ("OAuth Clients",           "oauth_clients"),
                    ("Authorization Roles",     "auth_roles"),
                ],
            },
            {
                "name":  "Configuration",
                "icon":  "⚙",
                "idx":   4,
                "items": [
                    ("Organization Settings",   "settings"),
                    ("License Users",           "license_users"),
                ],
            },
            {
                "name":  "Integrations",
                "icon":  "🔌",
                "idx":   5,
                "items": [
                    ("All Integrations",        "integrations"),
                ],
            },
        ]

        BADGE_COLORS = [PALETTE[f"sect_{i}"] for i in range(6)]

        # Build all cards first, then lay them out dynamically
        cards = []
        for i, section in enumerate(SECTIONS):
            color = BADGE_COLORS[section["idx"] % len(BADGE_COLORS)]

            card = tk.Frame(grid_host, bg=PALETTE["bg_surface"],
                            highlightbackground=PALETTE["border"],
                            highlightthickness=1, bd=0)

            stripe = tk.Frame(card, bg=color, width=4)
            stripe.pack(side="left", fill="y")

            body = tk.Frame(card, bg=PALETTE["bg_surface"])
            body.pack(side="left", fill="both", expand=True, padx=10, pady=8)

            hdr_f = tk.Frame(body, bg=PALETTE["bg_surface"])
            hdr_f.pack(fill="x", pady=(0, 6))
            _tk_label(hdr_f, text=section["icon"] + "  " + section["name"],
                      bg=PALETTE["bg_surface"], fg=color,
                      font=FONTS["ui_b"]).pack(side="left")

            tk.Frame(body, bg=color, height=1).pack(fill="x", pady=(0, 8))

            for item in section["items"]:
                label_text = item[0]
                method_key = item[1]
                confirm    = len(item) > 2 and item[2] == "confirm"
                cmd = self.confirm_and_start_usersqueues if confirm else (lambda m=method_key: self.start_task(m))
                btn = _tk_button(body, label_text, cmd, kind="normal", width=28)
                btn.pack(fill="x", pady=2)
                btn.initially_disabled = False
                self.buttons.append(btn)

            cards.append(card)

        # ── Responsive re-layout ─────────────────────────────────────────────
        MIN_CARD_W = 360
        _last_ncols = [0]

        def _relayout(ncols):
            if ncols == _last_ncols[0]:
                return
            _last_ncols[0] = ncols
            for ci, c in enumerate(cards):
                r, col = divmod(ci, ncols)
                c.grid(row=r, column=col, padx=12, pady=10, sticky="nsew")
            for col in range(ncols):
                grid_host.grid_columnconfigure(col, weight=1)
            for col in range(ncols, 6):
                grid_host.grid_columnconfigure(col, weight=0, minsize=0)

        def _on_canvas_resize(event):
            _relayout(max(1, event.width // MIN_CARD_W))

        scroll_canvas.bind("<Configure>", _on_canvas_resize)
        _relayout(2)  # default start

        if self.selected_client_name is None:
            self.change_buttons_states(disable=True, buttons=self.buttons)

        self.toggle_button(None)

        # mousewheel scroll
        def _mwheel(e):
            scroll_canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        scroll_canvas.bind_all("<MouseWheel>", _mwheel)

    def clear_main_tab(self):
        for w in self.main_tab.winfo_children():
            w.destroy()

    def create_main_view(self):
        self.show_customer_selection_view()

    # ──────────────────────────────────────────────────────────────────────────
    # HELP TAB
    # ──────────────────────────────────────────────────────────────────────────

    def create_help_view(self):
        """Scrollable Help tab with documentation for every section and tab."""

        HELP_CONTENT = [
            # ── Overview ──────────────────────────────────────────────────────
            {
                "section": "Overview",
                "icon": "📖",
                "idx": 0,
                "items": [
                    ("What is Pyramid API Management?",
                     "A desktop tool to query, browse and export data from Genesys Cloud "
                     "via the PureCloudPlatformClientV2 SDK.\n\n"
                     "Typical workflow:\n"
                     "  1. Go to the OAuth tab → add your org credentials → click Test.\n"
                     "  2. Come back to Main → select your org → click any data button.\n"
                     "  3. Browse results, search/filter, export CSV or JSON.\n\n"
                     "Results are cached in memory — clicking the same button again opens "
                     "instantly without a new API call. Use 🔄 Refresh to force a fresh fetch."),
                    ("Keyboard shortcuts",
                     "  [Esc]       →  Back to Main menu (works from any tab)\n"
                     "  [Ctrl+S]    →  Save current result as CSV\n"
                     "  [Double-click row]  →  Detail popup (Users and Queues only)"),
                    ("Status bar indicators",
                     "  ⚡ cached   →  Data loaded from memory (instant, no API call)\n"
                     "  🌐 live     →  Data just fetched from the Genesys Cloud API\n"
                     "  ✓ Task completed  →  Last API call finished successfully\n"
                     "  ░░ progress bar   →  API call in progress"),
                ],
            },
            # ── Main tab ──────────────────────────────────────────────────────
            {
                "section": "Main Tab — Users, Teams & Directory",
                "icon": "👤",
                "idx": 1,
                "items": [
                    ("All Users",
                     "Fetches every user in the org (paginated, 100 per page).\n"
                     "Columns: name, username, division, state, last login token date.\n"
                     "Double-click a row to open a full detail popup for that user.\n"
                     "⚠ Large orgs (10k+ users) may take 30–60 s on first fetch."),
                    ("All Users + Queues",
                     "Fetches all users AND their queue memberships in a single export.\n"
                     "Each user row lists all queues the user belongs to (comma-separated).\n"
                     "⚠ This is the slowest query — it makes one extra API call per user "
                     "to resolve queue names. A confirmation dialog appears before starting."),
                    ("External Contacts",
                     "Lists all external contacts stored in Genesys Cloud.\n"
                     "Includes: name, title, email, phone, address, linked account.\n"
                     "CSV export uses a dedicated flat layout (one contact per row)."),
                    ("Groups",
                     "Lists all user groups in the org.\n"
                     "Columns: name, type (official/social), visibility, member count."),
                    ("Teams",
                     "Lists all teams (functional groups used in routing).\n"
                     "Columns: name, division, member count."),
                ],
            },
            {
                "section": "Main Tab — Telephony & Architect",
                "icon": "📞",
                "idx": 2,
                "items": [
                    ("Phone Numbers (DIDs)",
                     "All DID/DDI numbers assigned in the org.\n"
                     "Columns: number, number type (did/toll-free), owner type."),
                    ("Edge Devices",
                     "All Genesys Edge hardware/virtual edge devices.\n"
                     "Columns: name, division, description, software version, state."),
                    ("Sites",
                     "All telephony sites (logical groupings of edges and phone settings).\n"
                     "Columns: name, description, primary site, state."),
                    ("Trunks",
                     "All configured SIP trunks.\n"
                     "Columns: name, state, trunk type, connected status.\n"
                     "Useful to audit BYOC/Carrier trunks and their health."),
                    ("All Flows",
                     "All Architect call flows (inbound call, inbound chat, in-queue, etc.).\n"
                     "Columns: name, division, type, description.\n"
                     "Does NOT include flow versions — only the current published flow."),
                    ("IVR Configurations",
                     "All IVR entries — maps DIDs to Architect flows.\n"
                     "Columns: name, division, DNIS list.\n"
                     "Use this to audit which phone numbers route to which flow."),
                    ("Schedules",
                     "All org schedules (open hours definitions).\n"
                     "Columns: name, division, start datetime, end datetime."),
                    ("Schedule Groups",
                     "All schedule groups (combine open/closed/holiday schedules).\n"
                     "Columns: name, division, description."),
                ],
            },
            {
                "section": "Main Tab — Routing & Queues",
                "icon": "🔀",
                "idx": 3,
                "items": [
                    ("All Queues",
                     "All routing queues in the org.\n"
                     "Columns: name, division, description, created date, member count.\n"
                     "Double-click a row to load and display current queue members."),
                    ("All Skills",
                     "All routing skills defined in the org.\n"
                     "Columns: name, state, last modified date.\n"
                     "Skills are assigned to agents and matched against queue requirements."),
                    ("Wrap-up Codes",
                     "All wrap-up (disposition) codes available in the org.\n"
                     "Columns: name, created date, last modified date."),
                    ("Routing Languages",
                     "All language skills used for language-based routing.\n"
                     "Columns: name, state, last modified date."),
                ],
            },
            {
                "section": "Main Tab — Security",
                "icon": "🔐",
                "idx": 4,
                "items": [
                    ("OAuth Clients",
                     "All OAuth client credentials registered in the org.\n"
                     "Columns: name, grant type (client_credentials/code/implicit), redirect URIs.\n"
                     "⚠ Client secrets are NOT returned by the API — only metadata is shown."),
                    ("Authorization Roles",
                     "All permission roles defined in the org (custom + default).\n"
                     "Columns: name, description, default role ID.\n"
                     "Use this to audit who has admin or elevated access."),
                ],
            },
            {
                "section": "Main Tab — Configuration & Integrations",
                "icon": "⚙",
                "idx": 5,
                "items": [
                    ("Organization Settings",
                     "Returns the org-level configuration object.\n"
                     "Displayed as a key/value text view (no table).\n"
                     "Includes: org name, default language, media regions, feature flags."),
                    ("License Users",
                     "All users with their assigned license types.\n"
                     "Columns: user ID, licenses list.\n"
                     "Useful to audit license consumption and allocated seats."),
                    ("All Integrations",
                     "All third-party integrations configured in the org.\n"
                     "Columns: name, integration type, intended state (enabled/disabled), notes."),
                ],
            },
            # ── OAuth tab ─────────────────────────────────────────────────────
            {
                "section": "OAuth Tab",
                "icon": "🔑",
                "idx": 0,
                "items": [
                    ("Adding a new credential",
                     "Fill in:\n"
                     "  • Name       — a friendly label (e.g. 'Prod Org')\n"
                     "  • Region     — your Genesys Cloud region (e.g. us_east_1)\n"
                     "  • Client ID  — the OAuth client_credentials Client ID\n"
                     "  • Secret     — the corresponding client secret\n\n"
                     "Click Save, then Test to verify the connection.\n"
                     "Credentials are stored in:\n"
                     "  %APPDATA%\\Pyramid\\pyramid.cfg  (Windows)\n"
                     "  ~/.config/Pyramid/pyramid.cfg   (Linux/macOS)"),
                    ("Switching orgs",
                     "Click any saved credential in the list on the left.\n"
                     "The Main tab reloads automatically. Cached data from the previous "
                     "org is NOT cleared — it stays in memory keyed to the old client ID."),
                    ("Deleting a credential",
                     "Select it in the list, then click Delete.\n"
                     "This removes it from pyramid.cfg immediately."),
                    ("Token caching",
                     "After a successful auth, the access token is cached for 23 hours.\n"
                     "Subsequent API calls within that window reuse the token without "
                     "re-authenticating. The cache is in memory only — it resets on app restart."),
                ],
            },
            # ── Config tab ────────────────────────────────────────────────────
            {
                "section": "Config Tab",
                "icon": "⚙",
                "idx": 1,
                "items": [
                    ("Theme",
                     "Toggle between Light (Windows-native) and Dark themes.\n"
                     "The selection is saved to pyramid.cfg and restored on next launch."),
                    ("Proxy",
                     "If your network requires a proxy to reach the Genesys Cloud API:\n"
                     "  • Enter the full proxy URL (e.g. http://proxy.corp.com:8080)\n"
                     "  • Enable the checkbox\n"
                     "  • Click Save\n\n"
                     "The proxy setting is persisted in pyramid.cfg.\n"
                     "Leave blank if you connect directly."),
                ],
            },
            # ── Log tab ───────────────────────────────────────────────────────
            {
                "section": "Log Tab",
                "icon": "📋",
                "idx": 2,
                "items": [
                    ("What is logged",
                     "The Log tab records every significant app event in real time:\n"
                     "  OK    — successful API calls and task completions\n"
                     "  INFO  — task starts, cache hits, auth events\n"
                     "  WARN  — non-fatal issues (e.g. cancelled tasks)\n"
                     "  ERROR — API exceptions and authentication failures\n\n"
                     "The log is in-memory only and resets when you close the app."),
                    ("Log level filter",
                     "Use the dropdown to filter the displayed log level.\n"
                     "  DEBUG  →  everything (verbose)\n"
                     "  INFO   →  normal operational messages\n"
                     "  WARN   →  warnings and above\n"
                     "  ERROR  →  errors only"),
                    ("Clearing the log",
                     "Click Clear to wipe the log display. This does not affect any files."),
                ],
            },
            # ── Results view ──────────────────────────────────────────────────
            {
                "section": "Results View (common to all queries)",
                "icon": "📊",
                "idx": 3,
                "items": [
                    ("Sorting",
                     "Click any column header to sort ascending.\n"
                     "Click again to sort descending.\n"
                     "A third click resets to original order."),
                    ("Search / Filter",
                     "The search bar above the table filters all visible columns in real time.\n"
                     "Type any string — the table updates as you type.\n"
                     "Click ✕ or clear the field to reset."),
                    ("Right-click",
                     "Right-click any cell to copy its value to the clipboard.\n"
                     "The context menu also provides a shortcut to Export CSV."),
                    ("Export CSV",
                     "Exports the processed (cleaned) data to a CSV file.\n"
                     "The default filename includes org name, method and timestamp.\n"
                     "[Ctrl+S] is a shortcut for this action from anywhere in the app."),
                    ("Export Raw JSON",
                     "Exports the raw API response (before any field processing) to JSON.\n"
                     "Useful for debugging or feeding into other tools."),
                    ("🔄 Refresh",
                     "Forces a new API call for this specific query, bypassing the cache.\n"
                     "The cache entry is updated with the fresh result.\n"
                     "For 'All Users + Queues' a confirmation dialog appears first."),
                ],
            },
        ]

        outer = tk.Frame(self.help_tab, bg=PALETTE["bg_base"])
        outer.pack(fill=tk.BOTH, expand=True)

        # ── Header ───────────────────────────────────────────────────────────
        hdr = tk.Frame(outer, bg=PALETTE["bg_surface"], pady=10)
        hdr.pack(fill="x")
        tk.Frame(hdr, bg=PALETTE["accent"], width=4).pack(side="left", fill="y")
        _tk_label(hdr, text="  ❓  Help & Documentation",
                  bg=PALETTE["bg_surface"], fg=PALETTE["accent_hi"],
                  font=FONTS["title"]).pack(side="left", padx=12)
        _tk_label(hdr, text="Pyramid API Management  •  reference guide",
                  bg=PALETTE["bg_surface"], fg=PALETTE["fg_muted"],
                  font=FONTS["ui_sm"]).pack(side="left")
        tk.Frame(outer, bg=PALETTE["border"], height=1).pack(fill="x")

        # ── Scrollable body ───────────────────────────────────────────────────
        canvas = tk.Canvas(outer, bg=PALETTE["bg_base"], highlightthickness=0, bd=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        body = tk.Frame(canvas, bg=PALETTE["bg_base"])
        canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))

        def _mwheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _mwheel)

        BADGE_COLORS = [PALETTE[f"sect_{i}"] for i in range(6)]

        # ── Render each section ───────────────────────────────────────────────
        for section_data in HELP_CONTENT:
            color = BADGE_COLORS[section_data["idx"] % len(BADGE_COLORS)]

            # Section header bar
            sh = tk.Frame(body, bg=PALETTE["bg_surface"])
            sh.pack(fill="x", padx=16, pady=(18, 0))
            tk.Frame(sh, bg=color, width=5).pack(side="left", fill="y")
            _tk_label(sh,
                      text=f"  {section_data['icon']}  {section_data['section']}",
                      bg=PALETTE["bg_surface"], fg=color,
                      font=FONTS["heading"]).pack(side="left", padx=8, pady=6)
            tk.Frame(body, bg=color, height=1).pack(fill="x", padx=16, pady=(0, 4))

            # Items
            for title, desc in section_data["items"]:
                item_frame = tk.Frame(body, bg=PALETTE["bg_surface"],
                                      highlightbackground=PALETTE["border"],
                                      highlightthickness=1)
                item_frame.pack(fill="x", padx=20, pady=4)

                # Left accent dot
                tk.Frame(item_frame, bg=color, width=3).pack(side="left", fill="y")

                content = tk.Frame(item_frame, bg=PALETTE["bg_surface"])
                content.pack(side="left", fill="both", expand=True, padx=12, pady=8)

                # Title row with optional copy-tip
                title_row = tk.Frame(content, bg=PALETTE["bg_surface"])
                title_row.pack(fill="x")
                _tk_label(title_row, text=title,
                          bg=PALETTE["bg_surface"], fg=PALETTE["fg_primary"],
                          font=FONTS["ui_b"]).pack(side="left")

                # Description (read-only Text widget for selectable text)
                desc_widget = tk.Text(
                    content,
                    wrap="word",
                    height=len(desc.splitlines()) + 1,
                    bg=PALETTE["bg_surface"],
                    fg=PALETTE["fg_secondary"],
                    font=FONTS["ui_sm"],
                    relief="flat", bd=0,
                    cursor="arrow",
                    selectbackground=PALETTE["accent_dim"],
                    selectforeground=PALETTE["fg_primary"],
                )
                desc_widget.insert("1.0", desc)
                desc_widget.config(state="disabled")
                desc_widget.pack(fill="x", pady=(3, 0))

        # Bottom padding
        tk.Frame(body, bg=PALETTE["bg_base"], height=24).pack()

    # ──────────────────────────────────────────────────────────────────────────
    # ABOUT TAB
    # ──────────────────────────────────────────────────────────────────────────

    def create_version_view(self):
        for w in self.version_tab.winfo_children():
            w.destroy()

        # ── Scrollable wrapper ────────────────────────────────────────────────
        _canvas = tk.Canvas(self.version_tab, bg=PALETTE["bg_base"],
                            highlightthickness=0, bd=0)
        _vsb = ttk.Scrollbar(self.version_tab, orient="vertical", command=_canvas.yview)
        _canvas.configure(yscrollcommand=_vsb.set)
        _vsb.pack(side="right", fill="y")
        _canvas.pack(side="left", fill="both", expand=True)

        _scroll_host = tk.Frame(_canvas, bg=PALETTE["bg_base"])
        _canvas.create_window((0, 0), window=_scroll_host, anchor="nw")
        _scroll_host.bind("<Configure>", lambda e: _canvas.configure(
            scrollregion=_canvas.bbox("all")))

        def _mwheel(e):
            _canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        _canvas.bind_all("<MouseWheel>", _mwheel)

        outer = tk.Frame(_scroll_host, bg=PALETTE["bg_base"])
        outer.pack(fill=tk.BOTH, expand=True, padx=30, pady=30)

        # App name hero
        tk.Frame(outer, bg=PALETTE["accent"], height=3).pack(fill="x", pady=(0, 12))
        _tk_label(outer, text=AppConfig.APP_NAME,
                  bg=PALETTE["bg_base"], fg=PALETTE["accent_hi"],
                  font=("Segoe UI", 18, "bold")).pack(anchor="w")
        _tk_label(outer,
                  text=f"Version {AppConfig.RELEASE_VERSION}   •   {AppConfig.RELEASE_DATE}",
                  bg=PALETTE["bg_base"], fg=PALETTE["fg_secondary"],
                  font=FONTS["ui"]).pack(anchor="w", pady=(4, 20))

        # ── Pyramid logo + author ──────────────────────────────────────────
        top_area = tk.Frame(outer, bg=PALETTE["bg_base"])
        top_area.pack(fill="x", pady=(0, 16))
        try:
            _ld  = base64.b64decode(create_logo())
            _img = ImageTk.PhotoImage(Image.open(BytesIO(_ld)))
            _lbl = tk.Label(top_area, image=_img, bg=PALETTE["bg_base"], bd=0)
            _lbl.image = _img
            _lbl.pack(side="left", padx=(0, 20))
        except Exception:
            pass
        _af = tk.Frame(top_area, bg=PALETTE["bg_base"])
        _af.pack(side="left", fill="both")
        _tk_label(_af, text="Developed by: Ighor Toth",
                  bg=PALETTE["bg_base"], fg=PALETTE["fg_primary"],
                  font=FONTS["ui_b"]).pack(anchor="w")
        _tk_label(_af, text="Contact: toth@ighor.com",
                  bg=PALETTE["bg_base"], fg=PALETTE["accent"],
                  font=FONTS["ui"]).pack(anchor="w")
        _tk_label(_af, text="License: MIT License",
                  bg=PALETTE["bg_base"], fg=PALETTE["fg_secondary"],
                  font=FONTS["ui_sm"]).pack(anchor="w", pady=(4, 0))
        _tk_label(_af,
                  text="This is not an official product. Send issues to the email above.",
                  bg=PALETTE["bg_base"], fg=PALETTE["danger"],
                  font=FONTS["ui_sm"]).pack(anchor="w", pady=(2, 0))

        try:
            sdk_ver = version('PureCloudPlatformClientV2')
        except PackageNotFoundError:
            sdk_ver = AppConfig.SDK_VERSION_FALLBACK

        info = [
            ("SDK",        f"PureCloudPlatformClientV2  v{sdk_ver}"),
            ("Python",     "tkinter GUI  •  threading  •  configparser"),
            ("Config file", AppConfig.CONFIG_FILE),
            ("Token TTL",  f"{AppConfig.TOKEN_CACHE_TTL // 3600} hours"),
        ]
        for label, val in info:
            row = tk.Frame(outer, bg=PALETTE["bg_base"])
            row.pack(fill="x", pady=2)
            _tk_label(row, text=f"{label}:",
                      bg=PALETTE["bg_base"], fg=PALETTE["fg_secondary"],
                      font=FONTS["ui_b"], width=14, anchor="w").pack(side="left")
            _tk_label(row, text=val,
                      bg=PALETTE["bg_base"], fg=PALETTE["fg_primary"],
                      font=FONTS["mono_sm"]).pack(side="left")

        tk.Frame(outer, bg=PALETTE["border"], height=1).pack(fill="x", pady=16)

        chlog = """v2.1.2 (Current)
  • Registry replaced with config file (%APPDATA%/Pyramid/pyramid.cfg)
  • winreg removed -- fully portable on Windows
  • Light (Windows-native) theme as default; Dark mode toggle in About

v2.1.1
  • Dark / Light theme toggle added; theme persisted in config

v2.1.0
  • Removed company-specific branding; proxy URL user-configurable
  • Full visual overhaul: custom ttk.Style, hover/press animations,
    colour-coded section cards, alternating table rows

v2.0.0
  • Token caching; generic _paginate() with 429 backoff
  • 13 new SDK methods: Groups, Teams, Sites, Trunks, DIDs, IVRs,
    Schedules, Schedule Groups, Wrap-up Codes, Languages,
    OAuth Clients, Authorization Roles, Integrations
  • Search/filter bar, right-click copy, keyboard shortcuts

v1.x.x -- Initial releases (2024)"""

        ta = scrolledtext.ScrolledText(outer, wrap=tk.WORD, height=14,
                                       bg=PALETTE["bg_raised"], fg=PALETTE["fg_secondary"],
                                       font=FONTS["mono_sm"], relief="flat", bd=0,
                                       insertbackground=PALETTE["accent"])
        ta.pack(fill="both", expand=True)
        ta.insert(tk.END, chlog)
        ta.config(state=tk.DISABLED)

        # ── Why Pyramid? ─────────────────────────────────────────────────────
        tk.Frame(outer, bg=PALETTE["border"], height=1).pack(fill="x", pady=(20, 0))

        wp_hdr = tk.Frame(outer, bg=PALETTE["bg_base"])
        wp_hdr.pack(fill="x", pady=(12, 0))
        tk.Frame(wp_hdr, bg=PALETTE["sect_2"], width=4).pack(side="left", fill="y")
        _tk_label(wp_hdr, text="  📌  What Pyramid does",
                  bg=PALETTE["bg_base"], fg=PALETTE["sect_2"],
                  font=FONTS["heading"]).pack(side="left", padx=8, pady=6)
        tk.Frame(outer, bg=PALETTE["sect_2"], height=1).pack(fill="x", pady=(0, 10))

        WHY = [
            ("📦  Full pagination — no record limits",
             PALETTE["danger"],
             "Pyramid paginates the API automatically and fetches every record\n"
             "regardless of org size — users, queues, contacts, roles and more.\n"
             "Results are only limited by what the API returns."),

            ("💾  Saves directly to your filesystem",
             PALETTE["warn"],
             "Exports are saved as CSV or JSON directly to any folder you choose.\n"
             "No size limits, no expiry, no inbox required.\n"
             "Files stay where you put them, named as you want."),

            ("🔗  Users + Queues in one export",
             PALETTE["accent"],
             "Export a flat table of all users and all their queue memberships\n"
             "in a single CSV — one row per user, queues as a comma-separated column.\n"
             "Ready for Excel, Power BI or any reporting tool."),

            ("⚙  Config objects: IVRs, Flows, Schedules and more",
             PALETTE["sect_1"],
             "Pyramid can export configuration objects that are not available\n"
             "through standard bulk export workflows:\n"
             "  • IVR Configurations (DNIS → Flow mappings)\n"
             "  • Architect Flows metadata\n"
             "  • Schedules and Schedule Groups\n"
             "  • OAuth Clients\n"
             "  • Authorization Roles\n"
             "  • Integrations\n"
             "  • License Users"),

            ("🏢  Multiple orgs, one tool",
             PALETTE["sect_3"],
             "Store credentials for as many orgs as you need.\n"
             "Switch between them with a single click.\n"
             "Each org's data is cached independently in memory."),

            ("⚡  In-memory cache — instant re-open",
             PALETTE["success"],
             "Once a dataset is fetched, clicking the same button again\n"
             "opens it instantly from memory — no new API call.\n"
             "Use 🔄 Refresh only when you need fresh data."),

            ("📋  Raw JSON export",
             PALETTE["sect_5"],
             "Every query can be exported as the raw API JSON response.\n"
             "Useful for migration scripting, debugging, or feeding\n"
             "data into other tools."),

            ("🎯  Built for migrations & audits",
             PALETTE["sect_4"],
             "Pyramid is purpose-built for getting a complete snapshot\n"
             "of an org's configuration at any point in time.\n\n"
             "Typical scenarios:\n"
             "  • Pre/post migration comparison between orgs\n"
             "  • Security audit (roles, OAuth clients, license usage)\n"
             "  • Documentation of a live org before making changes\n"
             "  • Onboarding: quickly understand an unknown org's setup"),
        ]

        for title, color, desc in WHY:
            card = tk.Frame(outer, bg=PALETTE["bg_surface"],
                            highlightbackground=PALETTE["border"],
                            highlightthickness=1)
            card.pack(fill="x", pady=4)
            tk.Frame(card, bg=color, width=4).pack(side="left", fill="y")
            body = tk.Frame(card, bg=PALETTE["bg_surface"])
            body.pack(side="left", fill="both", expand=True, padx=12, pady=8)
            _tk_label(body, text=title,
                      bg=PALETTE["bg_surface"], fg=PALETTE["fg_primary"],
                      font=FONTS["ui_b"]).pack(anchor="w")
            dt = tk.Text(body, wrap="word",
                         height=len(desc.splitlines()) + 1,
                         bg=PALETTE["bg_surface"], fg=PALETTE["fg_secondary"],
                         font=FONTS["ui_sm"], relief="flat", bd=0,
                         cursor="arrow",
                         selectbackground=PALETTE["accent_dim"],
                         selectforeground=PALETTE["fg_primary"])
            dt.insert("1.0", desc)
            dt.config(state="disabled")
            dt.pack(fill="x", pady=(3, 0))

        tk.Frame(outer, bg=PALETTE["border"], height=1).pack(fill="x", pady=(20, 0))
        _tk_label(outer, text="Appearance",
                  bg=PALETTE["bg_base"], fg=PALETTE["accent"],
                  font=FONTS["ui_b"]).pack(anchor="w")

        theme_row = tk.Frame(outer, bg=PALETTE["bg_base"])
        theme_row.pack(fill="x", pady=6)

        current_theme = self._load_setting("theme", "light")
        theme_var = tk.StringVar(value=current_theme)

        for val, label in (("dark", "🌙  Dark"), ("light", "☀️  Light")):
            tk.Radiobutton(
                theme_row, text=label, variable=theme_var, value=val,
                bg=PALETTE["bg_base"], fg=PALETTE["fg_primary"],
                selectcolor=PALETTE["bg_raised"],
                activebackground=PALETTE["bg_hover"],
                activeforeground=PALETTE["fg_primary"],
                font=FONTS["ui"], bd=0, highlightthickness=0
            ).pack(side="left", padx=(0, 16))

        def _save_theme():
            chosen = theme_var.get()
            self._save_setting("theme", chosen)
            messagebox.showinfo(
                "Theme saved",
                f"Theme set to '{chosen}'.\nRestart the application to apply."
            )

        _tk_button(theme_row, "Apply on next start", _save_theme, kind="accent").pack(side="left", padx=8)



    # ──────────────────────────────────────────────────────────────────────────
    # OAUTH TAB
    # ──────────────────────────────────────────────────────────────────────────

    def is_valid_uuid(self, s, version=4):
        try:
            return str(uuid.UUID(s, version=version)) == s
        except ValueError:
            return False

    def refresh_client_list(self):
        self.client_listbox.delete(0, tk.END)
        self.saved_data = self.load_from_registry()
        for client in self.saved_data:
            self.client_listbox.insert(tk.END, client)

    def create_oauth_view(self):
        REGIONS = ["us_east_1","us_east_2","us_west_2","eu_west_1","eu_west_2",
                   "eu_central_1","ca_central_1","ap_south_1","ap_southeast_2",
                   "ap_northeast_1","ap_northeast_2"]
        self.is_updating_fields = False

        def _name():
            if isinstance(self.selected_client_name, tk.StringVar):
                return self.selected_client_name.get()
            return self.selected_client_name or ''

        def _del_reg(key_path, name):
            """Remove client from config file."""
            try:
                cfg = self._get_config()
                if cfg.has_section("clients") and cfg.has_option("clients", name):
                    cfg.remove_option("clients", name)
                    self._write_config(cfg)
                return True
            except Exception as e:
                self.cancel_process(user=False, message="Config file error",
                                    error_message=str(e))
                return False

        def _remove_client():
            name = _name()
            if name and name in self.saved_data:
                try:
                    _del_reg(None, name)
                except Exception:
                    messagebox.showinfo("Error", "Client not removed.")
                    return
                self.refresh_client_list()
                delete_btn['state'] = tk.DISABLED
                test_btn['state']   = tk.DISABLED
                self.client_name_label.config(text="No client selected")
                self.selected_client_name = None
                self.create_main_view()
                messagebox.showinfo("Done", f"Client '{name}' removed.")
            else:
                messagebox.showinfo("Error", "No client selected.")

        def _clear_fields():
            if isinstance(self.selected_client_name, tk.StringVar):
                self.selected_client_name.set('')
            self.region_name_combobox.set('')
            for e in [self.name_entry, self.client_id_entry, self.client_secret_entry]:
                e.delete(0, tk.END)

        def _on_select(event):
            if not self.client_listbox.curselection():
                delete_btn['state'] = test_btn['state'] = tk.DISABLED
                return
            sel = self.client_listbox.get(self.client_listbox.curselection())
            self.selected_client_name = sel
            if sel in self.saved_data:
                rn, cid, csec = self.saved_data[sel].split(',')
                self.client_name_label.config(text=f"Selected:  {sel}")
                self.selected_region_name   = rn
                self.selected_client_id     = cid
                self.selected_client_secret = csec
                self.name_entry.delete(0, tk.END);   self.name_entry.insert(0, sel)
                self.region_name_combobox.set(rn)
                self.client_id_entry.delete(0, tk.END);     self.client_id_entry.insert(0, cid)
                self.client_secret_entry.delete(0, tk.END); self.client_secret_entry.insert(0, csec)
            delete_btn['state'] = test_btn['state'] = tk.NORMAL
            self.change_buttons_states(disable=None, buttons=self.buttons)
            self.create_main_view()

        def _save_client():
            orig = _name()
            upd_name   = self.name_entry.get().strip()
            upd_region = self.region_name_combobox.get().strip()
            upd_id     = self.client_id_entry.get().strip()
            upd_secret = self.client_secret_entry.get().strip()
            if not all([upd_name, upd_region, upd_id, upd_secret]):
                messagebox.showerror("Error", "All fields are required.")
                return
            if not self.is_valid_uuid(upd_id):
                messagebox.showerror("Error",
                    "Client ID doesn't look valid.\nExpected a 36-character UUID (e.g. xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx).")
                return
            val = f"{upd_region},{upd_id},{upd_secret}"
            if orig != upd_name and orig in self.saved_data:
                del self.saved_data[orig]
            self.saved_data[upd_name] = val

            try:
                cfg = self._get_config()
                if not cfg.has_section("clients"):
                    cfg.add_section("clients")
                cfg.set("clients", upd_name, val)
                if orig != upd_name and orig and cfg.has_option("clients", orig):
                    cfg.remove_option("clients", orig)
                self._write_config(cfg)
            except Exception as e:
                self.cancel_process(user=False, message="Config file write error", error_message=str(e))
                return

            self.refresh_client_list()
            self.selected_client_name  = upd_name
            self._token_cache['expires_at'] = 0   # invalidate cache
            self.append_log(f"Client saved: {upd_name}", "OK")
            messagebox.showinfo("Saved", f"Client '{upd_name}' saved.")

        def _on_field_change(event):
            if not self.is_updating_fields:
                save_btn['state'] = tk.NORMAL

        def _test_auth():
            region = self.region_name_combobox.get().strip()
            cid    = self.client_id_entry.get().strip()
            csec   = self.client_secret_entry.get().strip()
            if not all([region, cid, csec]):
                self.append_log("Test Auth: fields incomplete", "WARN")
                messagebox.showwarning("Missing fields", "Fill in Region, Client ID and Secret first.")
                return
            self.append_log(f"Test Auth → region={region}  client_id={cid[:8]}…", "DEBUG")
            self.append_log(f"Host: {PureCloudPlatformClientV2.PureCloudRegionHosts[region].get_api_host()}", "DEBUG")
            # Force fresh auth (bypass cache)
            self._token_cache['expires_at'] = 0
            ac = self.authenticate_genesys(region, cid, csec)
            if ac:
                self.append_log("Authentication successful — token acquired", "OK")
                self.status_message_label.config(text="✓  Connection OK", fg=PALETTE["success"])
                messagebox.showinfo("OK", "Authentication successful!")
                self.status_message_label.config(text="Ready", fg=PALETTE["fg_secondary"])
            else:
                self.append_log("Authentication FAILED — check credentials and region", "ERROR")

        # ── Build UI ──────────────────────────────────────────────────────────
        tab = self.oauth_tab
        tab.configure(bg=PALETTE["bg_base"])

        paned = tk.PanedWindow(tab, orient=tk.HORIZONTAL,
                               bg=PALETTE["bg_base"],
                               sashrelief="flat", sashwidth=4,
                               handlesize=0)
        paned.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        # ── Left: client list ─────────────────────────────────────────────────
        lf = tk.Frame(paned, bg=PALETTE["bg_surface"],
                      highlightbackground=PALETTE["border"], highlightthickness=1)
        paned.add(lf, minsize=200)

        _tk_label(lf, text="Saved Clients",
                  bg=PALETTE["bg_surface"], fg=PALETTE["accent"],
                  font=FONTS["ui_b"]).pack(anchor="w", padx=10, pady=(10, 4))
        tk.Frame(lf, bg=PALETTE["accent"], height=1).pack(fill="x", padx=10, pady=(0, 6))

        self.client_listbox = _tk_listbox(lf)
        vsb_lb = ttk.Scrollbar(lf, command=self.client_listbox.yview)
        self.client_listbox.config(yscrollcommand=vsb_lb.set)
        vsb_lb.pack(side="right", fill="y", padx=(0,4))
        self.client_listbox.pack(fill="both", expand=True, padx=(10, 0), pady=4)
        self.client_listbox.bind('<<ListboxSelect>>', _on_select)

        btn_row = tk.Frame(lf, bg=PALETTE["bg_surface"])
        btn_row.pack(fill="x", padx=10, pady=8)
        delete_btn = _tk_button(btn_row, "Delete", _remove_client, kind="danger")
        delete_btn.pack(side="right")
        delete_btn['state'] = tk.DISABLED
        test_btn = _tk_button(btn_row, "Test Auth", _test_auth, kind="ghost")
        test_btn.pack(side="left")
        test_btn['state'] = tk.DISABLED

        # ── Right: client form ────────────────────────────────────────────────
        rf = tk.Frame(paned, bg=PALETTE["bg_surface"],
                      highlightbackground=PALETTE["border"], highlightthickness=1)
        paned.add(rf, minsize=380)

        _tk_label(rf, text="Client Details",
                  bg=PALETTE["bg_surface"], fg=PALETTE["accent"],
                  font=FONTS["ui_b"]).pack(anchor="w", padx=16, pady=(12, 4))
        tk.Frame(rf, bg=PALETTE["accent"], height=1).pack(fill="x", padx=16, pady=(0, 12))

        form = tk.Frame(rf, bg=PALETTE["bg_surface"])
        form.pack(fill="x", padx=16)

        def _row(parent, label_text, widget_factory, **kw):
            r = tk.Frame(parent, bg=PALETTE["bg_surface"])
            r.pack(fill="x", pady=4)
            _tk_label(r, text=label_text,
                      bg=PALETTE["bg_surface"], fg=PALETTE["fg_secondary"],
                      font=FONTS["ui_sm"], width=14, anchor="w").pack(side="left")
            w = widget_factory(r, **kw)
            w.pack(side="left", fill="x", expand=True)
            return w

        self.name_entry = _row(form, "Name", _tk_entry, width=36)
        self.name_entry.bind("<KeyRelease>", _on_field_change)

        # Region combobox
        reg_row = tk.Frame(form, bg=PALETTE["bg_surface"])
        reg_row.pack(fill="x", pady=4)
        _tk_label(reg_row, text="Region",
                  bg=PALETTE["bg_surface"], fg=PALETTE["fg_secondary"],
                  font=FONTS["ui_sm"], width=14, anchor="w").pack(side="left")
        self.region_name_combobox = ttk.Combobox(reg_row, values=REGIONS,
                                                  font=FONTS["ui"], width=22)
        self.region_name_combobox.pack(side="left")
        self.region_name_combobox.bind("<<ComboboxSelected>>", _on_field_change)

        self.client_id_entry = _row(form, "Client ID", _tk_entry, width=48)
        self.client_id_entry.bind("<KeyRelease>", _on_field_change)

        self.client_secret_entry = _row(form, "Client Secret", _tk_entry, width=48, show="*")
        self.client_secret_entry.bind("<KeyRelease>", _on_field_change)

        # Show/hide toggle for secret field
        _sec_row = tk.Frame(rf, bg=PALETTE["bg_surface"])
        _sec_row.pack(fill="x", padx=16, pady=(0, 4))
        _show_secret_var = tk.BooleanVar(value=False)
        def _toggle_secret():
            self.client_secret_entry.config(
                show="" if _show_secret_var.get() else "*")
        tk.Checkbutton(
            _sec_row, text="Show secret", variable=_show_secret_var,
            command=_toggle_secret,
            bg=PALETTE["bg_surface"], fg=PALETTE["fg_secondary"],
            selectcolor=PALETTE["bg_raised"],
            activebackground=PALETTE["bg_hover"],
            activeforeground=PALETTE["fg_secondary"],
            font=FONTS["ui_sm"], bd=0, highlightthickness=0
        ).pack(side="left")

        btn_row2 = tk.Frame(rf, bg=PALETTE["bg_surface"])
        btn_row2.pack(fill="x", padx=16, pady=12)
        save_btn = _tk_button(btn_row2, "Save Changes", _save_client, kind="accent")
        save_btn.pack(side="left", padx=(0, 6))
        save_btn['state'] = tk.DISABLED
        _tk_button(btn_row2, "Clear", _clear_fields, kind="ghost").pack(side="left")

        self.saved_data = self.load_from_registry()
        self.selected_client_name = tk.StringVar()
        self.refresh_client_list()

    # ──────────────────────────────────────────────────────────────────────────
    # BOTTOM BAR
    # ──────────────────────────────────────────────────────────────────────────

    def append_log(self, msg, level="INFO"):
        """Append a timestamped line to the Log tab. Thread-safe. Respects level filter."""
        import datetime as _dt
        LEVEL_ORDER = {"DEBUG": 0, "INFO": 1, "OK": 2, "WARN": 3, "ERROR": 4}
        line = f"{_dt.datetime.now().strftime('%H:%M:%S')}  [{level:<5}]  {msg}\n"
        color = {
            "DEBUG":   PALETTE["fg_muted"],
            "INFO":    PALETTE["fg_primary"],
            "OK":      PALETTE["success"],
            "WARN":    PALETTE["warn"],
            "ERROR":   PALETTE["danger"],
        }.get(level, PALETTE["fg_primary"])

        def _insert():
            if not self.log_text:
                return
            # Filter by selected level
            selected = self.log_level_var.get() if self.log_level_var else "INFO"
            if LEVEL_ORDER.get(level, 1) < LEVEL_ORDER.get(selected, 1):
                return
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, line, level)
            self.log_text.tag_config(level, foreground=color)
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)
        self.master.after(0, _insert)
        logger.info(msg)

    def create_config_view(self):
        for w in self.config_tab.winfo_children():
            w.destroy()

        outer = tk.Frame(self.config_tab, bg=PALETTE["bg_base"])
        outer.pack(fill=tk.BOTH, expand=True, padx=30, pady=20)

        def _section(title, color_key="accent"):
            tk.Frame(outer, bg=PALETTE["border"], height=1).pack(fill="x", pady=(18, 6))
            _tk_label(outer, text=title,
                      bg=PALETTE["bg_base"], fg=PALETTE[color_key],
                      font=FONTS["ui_b"]).pack(anchor="w")

        def _row(label, widget_fn, hint=""):
            row = tk.Frame(outer, bg=PALETTE["bg_base"])
            row.pack(fill="x", pady=3)
            _tk_label(row, text=label,
                      bg=PALETTE["bg_base"], fg=PALETTE["fg_secondary"],
                      font=FONTS["ui"], width=20, anchor="w").pack(side="left")
            w = widget_fn(row)
            w.pack(side="left", padx=6)
            if hint:
                _tk_label(row, text=hint,
                          bg=PALETTE["bg_base"], fg=PALETTE["fg_muted"],
                          font=FONTS["ui_sm"]).pack(side="left", padx=4)
            return w

        # ── Proxy ─────────────────────────────────────────────────────────────
        _section("Proxy", "warn")

        proxy_url_var = tk.StringVar(value=self.proxy_server)
        proxy_entry = _row("Proxy URL:",
                           lambda p: _tk_entry(p, width=50),
                           hint="e.g. http://proxy.corp.com:8080")
        proxy_entry.insert(0, self.proxy_server)

        proxy_enabled_var = tk.IntVar(value=self.use_proxy_var.get())
        chk_row = tk.Frame(outer, bg=PALETTE["bg_base"])
        chk_row.pack(fill="x", pady=2)
        tk.Checkbutton(
            chk_row, text="Enable proxy on startup",
            variable=proxy_enabled_var,
            bg=PALETTE["bg_base"], fg=PALETTE["fg_primary"],
            selectcolor=PALETTE["bg_raised"],
            activebackground=PALETTE["bg_base"],
            activeforeground=PALETTE["accent"],
            font=FONTS["ui"], relief="flat", bd=0
        ).pack(side="left", padx=(168, 0))

        def _save_proxy():
            url = proxy_entry.get().strip()
            if url and not url.startswith(("http://", "https://")):
                messagebox.showerror(
                    "Invalid Proxy URL",
                    "Proxy URL must start with http:// or https://\n"
                    "Example: http://proxy.corp.com:8080")
                return
            self.proxy_server = url
            self.use_proxy_var.set(proxy_enabled_var.get())
            self._save_setting("proxy_url", url)
            self._save_setting("proxy_enabled", str(proxy_enabled_var.get()))
            # Apply immediately
            PureCloudPlatformClientV2.configuration.proxy = url if proxy_enabled_var.get() else None
            self.append_log(f"Proxy config saved: url={url or '(none)'} enabled={bool(proxy_enabled_var.get())}", "OK")
            if self.status_message_label:
                self.status_message_label.config(text="Config saved", fg=PALETTE["success"])
            messagebox.showinfo("Saved", "Proxy configuration saved.")

        btn_row = tk.Frame(outer, bg=PALETTE["bg_base"])
        btn_row.pack(fill="x", pady=(6, 0))
        _tk_button(btn_row, "Save Proxy", _save_proxy, kind="accent").pack(side="left", padx=(168, 0))

        # ── Appearance ────────────────────────────────────────────────────────
        _section("Appearance", "accent")

        current_theme = self._load_setting("theme", "light")
        theme_var = tk.StringVar(value=current_theme)
        t_row = tk.Frame(outer, bg=PALETTE["bg_base"])
        t_row.pack(fill="x", pady=4)
        _tk_label(t_row, text="Theme:",
                  bg=PALETTE["bg_base"], fg=PALETTE["fg_secondary"],
                  font=FONTS["ui"], width=20, anchor="w").pack(side="left")
        for val, label in (("light", "☀️  Light (default)"), ("dark", "🌙  Dark")):
            tk.Radiobutton(
                t_row, text=label, variable=theme_var, value=val,
                bg=PALETTE["bg_base"], fg=PALETTE["fg_primary"],
                selectcolor=PALETTE["bg_raised"],
                activebackground=PALETTE["bg_base"],
                activeforeground=PALETTE["accent"],
                font=FONTS["ui"], bd=0, highlightthickness=0
            ).pack(side="left", padx=(0, 14))

        def _save_theme():
            self._save_setting("theme", theme_var.get())
            messagebox.showinfo("Theme saved",
                f"Theme set to '{theme_var.get()}'.\nRestart to apply.")

        t_btn_row = tk.Frame(outer, bg=PALETTE["bg_base"])
        t_btn_row.pack(fill="x", pady=(4, 0))
        _tk_button(t_btn_row, "Save Theme", _save_theme, kind="accent").pack(side="left", padx=(168, 0))

        # ── Config file info ─────────────────────────────────────────────────
        _section("Storage", "fg_secondary")
        info_row = tk.Frame(outer, bg=PALETTE["bg_base"])
        info_row.pack(fill="x", pady=3)
        _tk_label(info_row, text="Config file:",
                  bg=PALETTE["bg_base"], fg=PALETTE["fg_secondary"],
                  font=FONTS["ui"], width=20, anchor="w").pack(side="left")
        _tk_label(info_row, text=AppConfig.CONFIG_FILE,
                  bg=PALETTE["bg_base"], fg=PALETTE["fg_primary"],
                  font=FONTS["mono_sm"]).pack(side="left")

        def _open_folder():
            import subprocess
            # Use list form — never build shell command with string interpolation
            subprocess.Popen(["explorer", AppConfig.CONFIG_DIR])

        _tk_button(outer, "Open config folder", _open_folder, kind="ghost").pack(
            anchor="w", padx=(168, 0), pady=(4, 0))

    def create_log_view(self):
        for w in self.log_tab.winfo_children():
            w.destroy()

        outer = tk.Frame(self.log_tab, bg=PALETTE["bg_base"])
        outer.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # ── Toolbar ──────────────────────────────────────────────────────────
        toolbar = tk.Frame(outer, bg=PALETTE["bg_base"])
        toolbar.pack(fill="x", pady=(0, 4))

        _tk_label(toolbar, text="Real-time log",
                  bg=PALETTE["bg_base"], fg=PALETTE["fg_secondary"],
                  font=FONTS["ui_b"]).pack(side="left", padx=(0, 12))

        # Log level filter
        _tk_label(toolbar, text="Level:",
                  bg=PALETTE["bg_base"], fg=PALETTE["fg_muted"],
                  font=FONTS["ui_sm"]).pack(side="left")

        self.log_level_var = tk.StringVar(value="INFO")
        LEVELS = ["DEBUG", "INFO", "OK", "WARN", "ERROR"]

        def _on_level_change(*_):
            pass  # filtering applied in append_log

        level_combo = ttk.Combobox(toolbar, textvariable=self.log_level_var,
                                   values=LEVELS, width=7, state="readonly",
                                   font=FONTS["ui_sm"])
        level_combo.pack(side="left", padx=(2, 8))

        def _clear_log():
            self.log_text.config(state=tk.NORMAL)
            self.log_text.delete("1.0", tk.END)
            self.log_text.config(state=tk.DISABLED)

        _tk_button(toolbar, "Clear", _clear_log, kind="ghost").pack(side="right")

        # ── Log text area ────────────────────────────────────────────────────
        self.log_text = scrolledtext.ScrolledText(
            outer, wrap=tk.WORD,
            bg=PALETTE["bg_surface"], fg=PALETTE["fg_primary"],
            font=FONTS["mono_sm"],
            relief="flat" if PALETTE["bg_base"] == DARK_PALETTE["bg_base"] else "sunken",
            bd=1, state=tk.DISABLED,
            insertbackground=PALETTE["accent"])
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.append_log("Pyramid API Management started", "INFO")

    def create_bottom_area(self):
        # ── Single status bar row ─────────────────────────────────────────────
        tk.Frame(self.master, bg=PALETTE["border"], height=1).pack(side="bottom", fill="x")

        self.bottom_frame = tk.Frame(self.master,
                                     bg=PALETTE["bg_raised"],
                                     highlightthickness=0)
        self.bottom_frame.pack(side="bottom", fill="x")

        bar = self.bottom_frame

        # Left: Cancel + Back (hidden until task running)
        self.cancel_button = _tk_button(bar, "⏹ Cancel", self.cancel_process, kind="danger")
        self.back_button   = _tk_button(bar, "← Back",  self.show_customer_selection_view, kind="ghost")

        # Right: Exit
        _tk_button(bar, "Exit", self.master.destroy, kind="ghost").pack(side="right", padx=4, pady=3)

        # Right: Progress bar
        _ps = ttk.Style()
        _ps.configure("sb.Horizontal.TProgressbar",
                       troughcolor=PALETTE["bg_raised"],
                       background=PALETTE["accent"],
                       bordercolor=PALETTE["border"],
                       thickness=8)
        self.progress_bar = ttk.Progressbar(
            bar, orient="horizontal", mode="indeterminate",
            length=120, style="sb.Horizontal.TProgressbar")
        self.progress_bar.pack(side="right", padx=6, pady=4)

        # Right: status text
        self.status_message_label = _tk_label(
            bar, text="Ready",
            bg=PALETTE["bg_raised"], fg=PALETTE["fg_secondary"],
            font=FONTS["ui_sm"])
        self.status_message_label.pack(side="right", padx=6, pady=3)

        # Right: proxy toggle
        proxy_check = tk.Checkbutton(
            bar, text="Use Proxy",
            variable=self.use_proxy_var,
            bg=PALETTE["bg_raised"], fg=PALETTE["fg_secondary"],
            selectcolor=PALETTE["bg_hover"],
            activebackground=PALETTE["bg_raised"],
            activeforeground=PALETTE["accent"],
            font=FONTS["ui_sm"], relief="flat", bd=0, cursor="hand2")
        proxy_check.pack(side="right", padx=4, pady=3)
        self.use_proxy_var.trace_add('write', lambda *a: self.apply_proxy_setting())
        self.ToolTip(proxy_check, f"Toggle HTTP proxy\n{self.proxy_server or 'No proxy configured'}")

        # Left: client name
        self.client_name_label = _tk_label(
            bar, text="No client selected",
            bg=PALETTE["bg_raised"], fg=PALETTE["accent"],
            font=FONTS["ui_sm"])
        self.client_name_label.pack(side="left", padx=8, pady=3)
        # hidden until task starts

    # ──────────────────────────────────────────────────────────────────────────
    # AUTHENTICATION (token-cached)
    # ──────────────────────────────────────────────────────────────────────────

    def authenticate_genesys(self, region_name=None, client_id=None, client_secret=None):
        if region_name is None:
            region_name   = self.selected_region_name
            client_id     = self.selected_client_id
            client_secret = self.selected_client_secret

        cache = self._token_cache
        if (cache['api_client'] and cache['region'] == region_name
                and cache['client_id'] == client_id
                and time.time() < cache['expires_at']):
            remaining = int(cache['expires_at'] - time.time())
            self.append_log(f"Token cache hit — expires in {remaining//3600}h {(remaining%3600)//60}m", "DEBUG")
            return cache['api_client']

        self.append_log(f"Authenticating  region={region_name}  client={client_id[:8]}…", "INFO")
        region_host = PureCloudPlatformClientV2.PureCloudRegionHosts[region_name]
        host_url = region_host.get_api_host()
        self.append_log(f"API host: {host_url}", "DEBUG")
        PureCloudPlatformClientV2.configuration.host = host_url

        try:
            self.append_log("Requesting client_credentials token…", "DEBUG")
            ac = PureCloudPlatformClientV2.api_client.ApiClient()\
                   .get_client_credentials_token(client_id, client_secret)
            self._token_cache = {
                'api_client': ac,
                'expires_at': time.time() + AppConfig.TOKEN_CACHE_TTL,
                'region':     region_name,
                'client_id':  client_id,
            }
            self.append_log(f"Token OK — cached for {AppConfig.TOKEN_CACHE_TTL//3600}h", "DEBUG")
            return ac
        except ApiException as e:
            self.append_log(f"ApiException: status={e.status}  reason={e.reason}", "ERROR")
            self.cancel_process(user=False,
                                message="Authentication failed (ApiException)",
                                error_message=str(e))
            return None
        except Exception as e:
            err = str(e)
            self.append_log(f"Exception: {err}", "ERROR")
            msg = "Unable to connect to proxy — try disabling it" if "proxy" in err.lower() else "Connection error"
            self.cancel_process(user=False, message=msg, error_message=err)
            return None

    # ──────────────────────────────────────────────────────────────────────────
    # PAGINATION HELPER
    # ──────────────────────────────────────────────────────────────────────────

    def _paginate(self, api_func, spinner_text="Fetching…", page_size=100, **kwargs):
        raw_json, all_entities = [], []
        page_number = 1
        first_page  = True

        self.append_log(f"Paginating {api_func.__name__} page_size={page_size}", "DEBUG")

        while True:
            for attempt in range(AppConfig.MAX_RETRIES):
                try:
                    self.append_log(f"  → page {page_number} attempt {attempt+1}", "DEBUG")
                    resp = api_func(page_size, page_number, **kwargs)
                    break
                except ApiException as e:
                    if e.status == 429:
                        wait = AppConfig.RETRY_BACKOFF ** attempt
                        self.append_log(f"Rate limited (429) — waiting {wait}s…", "WARN")
                        self.update_spinner(page_number, f"Rate limited — retrying in {wait}s")
                        time.sleep(wait)
                    else:
                        self.append_log(f"ApiException page={page_number}: status={e.status} {e.reason}", "ERROR")
                        raise
            else:
                raise Exception(f"Max retries exceeded ({api_func.__name__})")

            rd = json.loads(resp.to_json())
            raw_json.append(rd)
            entities = rd.get('entities', [])
            all_entities.extend(entities)
            total = rd.get('page_count', 1)
            total_hits = rd.get('total', rd.get('total_hits', len(entities)))

            # ── Per-page summary ─────────────────────────────────────────────
            first_name = entities[0].get('name', entities[0].get('id','?'))  if entities else '—'
            last_name  = entities[-1].get('name', entities[-1].get('id','?')) if entities else '—'
            self.append_log(
                f"  ← page {page_number}/{total}  got={len(entities)}  "
                f"cumulative={len(all_entities)}  total_hits={total_hits}  "
                f"first='{first_name}'  last='{last_name}'", "DEBUG")

            # ── First record full JSON (first page only) ──────────────────────
            if first_page and entities:
                first_page = False
                sample = entities[0]
                sample_str = json.dumps(sample, indent=2, default=str)
                # Log each line so it wraps nicely in the log widget
                self.append_log("  [sample first record]", "DEBUG")
                for line in sample_str.splitlines():
                    self.append_log(f"    {line}", "DEBUG")

            self.update_spinner((page_number / total) * 100,
                                f"{spinner_text}  ({page_number}/{total})")
            if page_number >= total:
                break
            page_number += 1

        self.append_log(f"Pagination complete: {len(all_entities)} total records", "INFO")
        return raw_json, all_entities

    # ──────────────────────────────────────────────────────────────────────────
    # API: USERS & DIRECTORY
    # ──────────────────────────────────────────────────────────────────────────

    def get_all_users_from_customer(self):
        self.append_log("UsersApi: initializing (active + inactive)", "DEBUG")
        ac = self.authenticate_genesys()
        if not ac: return []
        users_api = PureCloudPlatformClientV2.UsersApi(ac)
        expand    = ['lasttokenissued']
        result    = []
        for stat in ['active', 'inactive']:
            self.append_log(f"UsersApi: fetching state={stat} expand={expand}", "DEBUG")
            try:
                rj, entities = self._paginate(
                    lambda ps, pn, s=stat: users_api.get_users(
                        page_size=ps, page_number=pn,
                        state=s, expand=expand, sort_order="asc"),
                    spinner_text=f"Getting {stat} users", page_size=500)
                self.append_log(f"UsersApi: state={stat} → {len(entities)} users", "DEBUG")
                result.extend(rj)
            except ApiException as e:
                self.append_log(f"UsersApi ERROR state={stat}: {e.status} {e.reason}", "ERROR")
                self.cancel_process(user=False, message="UsersApi error", error_message=str(e))
        self.append_log(f"UsersApi: total page-sets returned: {len(result)}", "DEBUG")
        return result

    def get_all_usersqueues_from_customer(self):
        self.append_log("UsersQueues: fetching all users first…", "DEBUG")
        ac = self.authenticate_genesys()
        if not ac: return []
        routing_api = PureCloudPlatformClientV2.RoutingApi(ac)
        all_users   = self.get_all_users_from_customer()
        result, done = [], 0
        try:
            total = sum(len(u.get('entities',[])) for u in all_users)
            self.append_log(f"UsersQueues: resolving queues for {total} users", "DEBUG")
            for user in all_users:
                for entity in user.get('entities', []):
                    uid, pg, queues = entity['id'], 1, []
                    self.append_log(f"  → user {uid} ({entity.get('name','')})", "DEBUG")
                    while True:
                        qr = routing_api.get_user_queues(uid, page_size=100, page_number=pg)
                        queues.extend({'id': q.id, 'name': q.name} for q in qr.entities)
                        if pg >= qr.page_count: break
                        pg += 1
                    entity['queues'] = queues
                    self.append_log(f"     queues={len(queues)}", "DEBUG")
                    done += 1
                    self.update_spinner(done / max(total,1) * 100,
                                        f"Queues fetched: {done}/{total}")
                result.append(user)
        except ApiException as e:
            self.append_log(f"UsersQueues ERROR: {e.status} {e.reason}", "ERROR")
            self.cancel_process(user=False, message="Failed fetching user queues", error_message=str(e))
        self.append_log(f"UsersQueues: done. {done} users processed", "DEBUG")
        return result

    def get_all_external_contacts(self):
        self.append_log("ExternalContactsApi: cursor-based scan starting", "DEBUG")
        ac = self.authenticate_genesys()
        if not ac: return []
        api     = PureCloudPlatformClientV2.ExternalContactsApi(ac)
        raw, cursor, pg = [], None, 0
        while True:
            try:
                self.append_log(f"ExternalContacts: page={pg} cursor={cursor[:20] if cursor else 'None'}…", "DEBUG")
                r = api.get_externalcontacts_scan_contacts(limit=200) if cursor is None \
                    else api.get_externalcontacts_scan_contacts(limit=200, cursor=cursor)
                rd = json.loads(r.to_json())
                entities = rd.get('entities', [])
                raw.append(rd)
                self.append_log(f"ExternalContacts: page={pg} → {len(entities)} contacts", "DEBUG")
                nu = r.next_uri
                if nu and 'cursor=' in nu:
                    cursor = nu.split('cursor=')[1].split('&')[0]
                else:
                    self.update_spinner(100, "Contacts fetched")
                    self.append_log(f"ExternalContacts: complete — {sum(len(p.get('entities',[])) for p in raw)} total", "DEBUG")
                    break
                pg += 1
                self.update_spinner(pg, f"Contacts page {pg}")
            except ApiException as e:
                self.append_log(f"ExternalContacts ERROR: {e.status} {e.reason}", "ERROR")
                self.cancel_process(user=False, message="ExternalContacts error", error_message=str(e))
                return []
        return raw

    def get_all_groups(self):
        self.append_log("GroupsApi: starting", "DEBUG")
        ac = self.authenticate_genesys()
        if not ac: return []
        try:
            rj, entities = self._paginate(
                lambda ps, pn: PureCloudPlatformClientV2.GroupsApi(ac).get_groups(
                    page_size=ps, page_number=pn),
                spinner_text="Getting groups")
            self.append_log(f"GroupsApi: {len(entities)} groups", "DEBUG")
            return rj
        except ApiException as e:
            self.append_log(f"GroupsApi ERROR: {e.status} {e.reason}", "ERROR")
            self.cancel_process(user=False, message="GroupsApi error", error_message=str(e)); return []

    def get_all_teams(self):
        self.append_log("TeamsApi: starting", "DEBUG")
        ac = self.authenticate_genesys()
        if not ac: return []
        try:
            rj, entities = self._paginate(
                lambda ps, pn: PureCloudPlatformClientV2.TeamsApi(ac).get_teams(
                    page_size=ps, page_number=pn),
                spinner_text="Getting teams")
            self.append_log(f"TeamsApi: {len(entities)} teams", "DEBUG")
            return rj
        except ApiException as e:
            self.append_log(f"TeamsApi ERROR: {e.status} {e.reason}", "ERROR")
            self.cancel_process(user=False, message="TeamsApi error", error_message=str(e)); return []

    # ──────────────────────────────────────────────────────────────────────────
    # API: TELEPHONY & ARCHITECT
    # ──────────────────────────────────────────────────────────────────────────

    def get_telephony_providers_edges(self):
        self.append_log("TelephonyEdgeApi: get_telephony_providers_edges page_size=500", "DEBUG")
        ac = self.authenticate_genesys()
        if not ac: return []
        try:
            r = PureCloudPlatformClientV2.TelephonyProvidersEdgeApi(ac)\
                    .get_telephony_providers_edges(page_size=500)
            rd = json.loads(r.to_json())
            self.append_log(f"TelephonyEdgeApi: {len(rd.get('entities',[]))} edges", "DEBUG")
            return [rd]
        except ApiException as e:
            self.append_log(f"TelephonyEdgeApi ERROR: {e.status} {e.reason}", "ERROR")
            self.cancel_process(user=False, message="EdgeApi error", error_message=str(e)); return []

    def get_telephony_sites(self):
        self.append_log("TelephonySitesApi: starting", "DEBUG")
        ac = self.authenticate_genesys()
        if not ac: return []
        try:
            rj, entities = self._paginate(
                lambda ps, pn: PureCloudPlatformClientV2.TelephonyProvidersEdgeApi(ac)
                    .get_telephony_providers_edges_sites(page_size=ps, page_number=pn),
                spinner_text="Getting sites")
            self.append_log(f"TelephonySitesApi: {len(entities)} sites", "DEBUG")
            return rj
        except ApiException as e:
            self.append_log(f"TelephonySitesApi ERROR: {e.status} {e.reason}", "ERROR")
            self.cancel_process(user=False, message="Sites error", error_message=str(e)); return []

    def get_telephony_trunks(self):
        self.append_log("TelephonyTrunksApi: starting", "DEBUG")
        ac = self.authenticate_genesys()
        if not ac: return []
        try:
            rj, entities = self._paginate(
                lambda ps, pn: PureCloudPlatformClientV2.TelephonyProvidersEdgeApi(ac)
                    .get_telephony_providers_edges_trunks(page_size=ps, page_number=pn),
                spinner_text="Getting trunks")
            self.append_log(f"TelephonyTrunksApi: {len(entities)} trunks", "DEBUG")
            return rj
        except ApiException as e:
            self.append_log(f"TelephonyTrunksApi ERROR: {e.status} {e.reason}", "ERROR")
            self.cancel_process(user=False, message="Trunks error", error_message=str(e)); return []

    def get_telephony_dids(self):
        self.append_log("TelephonyDIDsApi: starting", "DEBUG")
        ac = self.authenticate_genesys()
        if not ac: return []
        try:
            rj, entities = self._paginate(
                lambda ps, pn: PureCloudPlatformClientV2.TelephonyProvidersEdgeApi(ac)
                    .get_telephony_providers_edges_dids(page_size=ps, page_number=pn),
                spinner_text="Getting DIDs")
            self.append_log(f"TelephonyDIDsApi: {len(entities)} DIDs", "DEBUG")
            return rj
        except ApiException as e:
            self.append_log(f"TelephonyDIDsApi ERROR: {e.status} {e.reason}", "ERROR")
            self.cancel_process(user=False, message="DIDs error", error_message=str(e)); return []

    def get_all_flows_from_customer(self):
        self.append_log("ArchitectApi: get_flows starting", "DEBUG")
        ac = self.authenticate_genesys()
        if not ac: return []
        arch_api, rj, pg = PureCloudPlatformClientV2.ArchitectApi(ac), [], 1
        try:
            while True:
                self.append_log(f"ArchitectApi: flows page={pg}", "DEBUG")
                r = arch_api.get_flows(page_number=pg, page_size=100)
                rd = json.loads(r.to_json())
                rj.append(rd)
                self.append_log(f"ArchitectApi: page={pg}/{r.page_count} entities={len(rd.get('entities',[]))}", "DEBUG")
                if pg >= r.page_count: break
                pg += 1
                self.update_spinner(pg / r.page_count * 100, "Getting flows")
        except ApiException as e:
            self.append_log(f"ArchitectApi flows ERROR: {e.status} {e.reason}", "ERROR")
            self.cancel_process(user=False, message="Flows error", error_message=str(e))
        self.append_log(f"ArchitectApi: flows complete — {pg} pages", "DEBUG")
        return rj

    def get_architect_ivrs(self):
        self.append_log("ArchitectApi: get_architect_ivrs starting", "DEBUG")
        ac = self.authenticate_genesys()
        if not ac: return []
        try:
            rj, entities = self._paginate(
                lambda ps, pn: PureCloudPlatformClientV2.ArchitectApi(ac)
                    .get_architect_ivrs(page_size=ps, page_number=pn),
                spinner_text="Getting IVRs")
            self.append_log(f"ArchitectApi: {len(entities)} IVRs", "DEBUG")
            return rj
        except ApiException as e:
            self.append_log(f"ArchitectApi IVRs ERROR: {e.status} {e.reason}", "ERROR")
            self.cancel_process(user=False, message="IVRs error", error_message=str(e)); return []

    def get_architect_schedules(self):
        self.append_log("ArchitectApi: get_architect_schedules starting", "DEBUG")
        ac = self.authenticate_genesys()
        if not ac: return []
        try:
            rj, entities = self._paginate(
                lambda ps, pn: PureCloudPlatformClientV2.ArchitectApi(ac)
                    .get_architect_schedules(page_size=ps, page_number=pn),
                spinner_text="Getting schedules")
            self.append_log(f"ArchitectApi: {len(entities)} schedules", "DEBUG")
            return rj
        except ApiException as e:
            self.append_log(f"ArchitectApi schedules ERROR: {e.status} {e.reason}", "ERROR")
            self.cancel_process(user=False, message="Schedules error", error_message=str(e)); return []

    def get_architect_schedulegroups(self):
        self.append_log("ArchitectApi: get_architect_schedulegroups starting", "DEBUG")
        ac = self.authenticate_genesys()
        if not ac: return []
        try:
            rj, entities = self._paginate(
                lambda ps, pn: PureCloudPlatformClientV2.ArchitectApi(ac)
                    .get_architect_schedulegroups(page_size=ps, page_number=pn),
                spinner_text="Getting schedule groups")
            self.append_log(f"ArchitectApi: {len(entities)} schedule groups", "DEBUG")
            return rj
        except ApiException as e:
            self.append_log(f"ArchitectApi schedulegroups ERROR: {e.status} {e.reason}", "ERROR")
            self.cancel_process(user=False, message="ScheduleGroups error", error_message=str(e)); return []

    # ──────────────────────────────────────────────────────────────────────────
    # API: ROUTING & QUEUES
    # ──────────────────────────────────────────────────────────────────────────

    def get_all_queues_from_customer(self):
        self.append_log("RoutingApi: get_routing_queues starting", "DEBUG")
        ac = self.authenticate_genesys()
        if not ac: return []
        try:
            rj, entities = self._paginate(
                lambda ps, pn: PureCloudPlatformClientV2.RoutingApi(ac)
                    .get_routing_queues(page_size=ps, page_number=pn),
                spinner_text="Getting queues")
            self.append_log(f"RoutingApi: {len(entities)} queues", "DEBUG")
            return rj
        except ApiException as e:
            self.append_log(f"RoutingApi queues ERROR: {e.status} {e.reason}", "ERROR")
            self.cancel_process(user=False, message="Queues error", error_message=str(e)); return []

    def get_all_skills_from_customer(self):
        self.append_log("RoutingApi: get_routing_skills starting", "DEBUG")
        ac = self.authenticate_genesys()
        if not ac: return []
        try:
            rj, entities = self._paginate(
                lambda ps, pn: PureCloudPlatformClientV2.RoutingApi(ac)
                    .get_routing_skills(page_size=ps, page_number=pn),
                spinner_text="Getting skills")
            self.append_log(f"RoutingApi: {len(entities)} skills", "DEBUG")
            return rj
        except ApiException as e:
            self.append_log(f"RoutingApi skills ERROR: {e.status} {e.reason}", "ERROR")
            self.cancel_process(user=False, message="Skills error", error_message=str(e)); return []

    def get_routing_wrapupcodes(self):
        self.append_log("RoutingApi: get_routing_wrapupcodes starting", "DEBUG")
        ac = self.authenticate_genesys()
        if not ac: return []
        try:
            rj, entities = self._paginate(
                lambda ps, pn: PureCloudPlatformClientV2.RoutingApi(ac)
                    .get_routing_wrapupcodes(page_size=ps, page_number=pn),
                spinner_text="Getting wrap-up codes")
            self.append_log(f"RoutingApi: {len(entities)} wrap-up codes", "DEBUG")
            return rj
        except ApiException as e:
            self.append_log(f"RoutingApi wrapupcodes ERROR: {e.status} {e.reason}", "ERROR")
            self.cancel_process(user=False, message="WrapUpCodes error", error_message=str(e)); return []

    def get_routing_languages(self):
        self.append_log("RoutingApi: get_routing_languages starting", "DEBUG")
        ac = self.authenticate_genesys()
        if not ac: return []
        try:
            rj, entities = self._paginate(
                lambda ps, pn: PureCloudPlatformClientV2.RoutingApi(ac)
                    .get_routing_languages(page_size=ps, page_number=pn),
                spinner_text="Getting routing languages")
            self.append_log(f"RoutingApi: {len(entities)} routing languages", "DEBUG")
            return rj
        except ApiException as e:
            self.append_log(f"RoutingApi languages ERROR: {e.status} {e.reason}", "ERROR")
            self.cancel_process(user=False, message="Languages error", error_message=str(e)); return []

    def get_queue_memberships(self, queue_id=None):
        self.append_log(f"RoutingApi: get_routing_queue_members queue_id={queue_id}", "DEBUG")
        ac = self.authenticate_genesys()
        if not ac: return []
        routing_api, members, pg = PureCloudPlatformClientV2.RoutingApi(ac), [], 1
        try:
            while True:
                self.append_log(f"  → queue members page={pg}", "DEBUG")
                r = routing_api.get_routing_queue_members(queue_id, page_number=pg, page_size=100)
                if not r.entities: break
                members.extend({
                    'id':             m.id,
                    'name':           m.name,
                    'routing_status': getattr(m.routing_status, 'status', 'N/A')
                                      if m.routing_status else 'N/A'
                } for m in r.entities)
                self.append_log(f"  ← page={pg}/{r.page_count} members={len(r.entities)} cumulative={len(members)}", "DEBUG")
                if pg >= r.page_count: break
                pg += 1
        except ApiException as e:
            self.append_log(f"RoutingApi queue members ERROR: {e.status} {e.reason}", "ERROR")
            self.cancel_process(user=False, message="QueueMembers error", error_message=str(e))
            return []
        self.append_log(f"RoutingApi: {len(members)} members total", "DEBUG")
        return members

    # ──────────────────────────────────────────────────────────────────────────
    # API: SECURITY
    # ──────────────────────────────────────────────────────────────────────────

    def get_oauth_clients(self):
        self.append_log("OAuthApi: get_oauth_clients starting", "DEBUG")
        ac = self.authenticate_genesys()
        if not ac: return []
        try:
            self.update_spinner(0, "Getting OAuth clients…")
            r = PureCloudPlatformClientV2.OAuthApi(ac).get_oauth_clients()
            rd = json.loads(r.to_json())
            count = len(rd.get('entities', []))
            self.append_log(f"OAuthApi: {count} OAuth clients", "DEBUG")
            self.update_spinner(100, "Done")
            return [{'entities': rd.get('entities', [])}]
        except ApiException as e:
            self.append_log(f"OAuthApi ERROR: {e.status} {e.reason}", "ERROR")
            self.cancel_process(user=False, message="OAuthApi error", error_message=str(e)); return []

    def get_authorization_roles(self):
        self.append_log("AuthorizationApi: get_authorization_roles starting", "DEBUG")
        ac = self.authenticate_genesys()
        if not ac: return []
        try:
            rj, entities = self._paginate(
                lambda ps, pn: PureCloudPlatformClientV2.AuthorizationApi(ac)
                    .get_authorization_roles(page_size=ps, page_number=pn),
                spinner_text="Getting authorization roles")
            self.append_log(f"AuthorizationApi: {len(entities)} roles", "DEBUG")
            return rj
        except ApiException as e:
            self.append_log(f"AuthorizationApi ERROR: {e.status} {e.reason}", "ERROR")
            self.cancel_process(user=False, message="AuthRoles error", error_message=str(e)); return []

    # ──────────────────────────────────────────────────────────────────────────
    # API: CONFIGURATION
    # ──────────────────────────────────────────────────────────────────────────

    def get_settings(self):
        return self.get_organization_info()

    def get_organization_info(self):
        self.append_log("OrganizationApi: get_organizations_me starting", "DEBUG")
        ac = self.authenticate_genesys()
        if not ac: return None
        try:
            self.update_spinner(0, "Fetching org info…")
            r = PureCloudPlatformClientV2.OrganizationApi(ac).get_organizations_me()
            rd = json.loads(r.to_json()) if hasattr(r, 'to_json') else {}
            self.append_log(f"OrganizationApi: org={rd.get('name','?')} id={rd.get('id','?')[:8]}…", "DEBUG")
            self.update_spinner(100, "Done")
            return r
        except ApiException as e:
            self.append_log(f"OrganizationApi ERROR: {e.status} {e.reason}", "ERROR")
            self.cancel_process(user=False, message="OrgInfo error", error_message=str(e))
            return str(e)

    def get_all_license_users(self):
        self.append_log("LicenseApi: get_license_users starting", "DEBUG")
        ac = self.authenticate_genesys()
        if not ac: return []
        api_inst, raw, pg = PureCloudPlatformClientV2.LicenseApi(ac), [], 1
        self.update_spinner(0, "Getting license users…")
        try:
            while True:
                self.append_log(f"LicenseApi: page={pg}", "DEBUG")
                r = api_inst.get_license_users(page_size=25, page_number=pg)
                rd = json.loads(r.to_json())
                raw.append(rd)
                self.append_log(f"  ← page={pg} entities={len(rd.get('entities',[]))}", "DEBUG")
                self.update_spinner(pg * 5, "Fetching license users…")
                if not r.next_page: break
                pg += 1
            self.update_spinner(100, "Done")
            self.append_log(f"LicenseApi: {pg} pages fetched", "DEBUG")
        except ApiException as e:
            self.append_log(f"LicenseApi ERROR: {e.status} {e.reason}", "ERROR")
            self.cancel_process(user=False, message="LicenseUsers error", error_message=str(e))
        return raw

    # ──────────────────────────────────────────────────────────────────────────
    # API: INTEGRATIONS
    # ──────────────────────────────────────────────────────────────────────────

    def get_all_integrations(self):
        self.append_log("IntegrationsApi: get_integrations starting", "DEBUG")
        ac = self.authenticate_genesys()
        if not ac: return []
        try:
            rj, entities = self._paginate(
                lambda ps, pn: PureCloudPlatformClientV2.IntegrationsApi(ac)
                    .get_integrations(page_size=ps, page_number=pn),
                spinner_text="Getting integrations")
            self.append_log(f"IntegrationsApi: {len(entities)} integrations", "DEBUG")
            return rj
        except ApiException as e:
            self.append_log(f"IntegrationsApi ERROR: {e.status} {e.reason}", "ERROR")
            self.cancel_process(user=False, message="Integrations error", error_message=str(e)); return []

    # ──────────────────────────────────────────────────────────────────────────
    # DATA PROCESSING
    # ──────────────────────────────────────────────────────────────────────────

    def process_data(self, raw_data_list, keys_removal=None):
        TRANSFORM = {
            'division':            ('simplify', 'name'),
            'last_token_issued':   ('simplify', 'date_issued'),
            'queues':              ('join',    ('name', ', ')),
            'schema':              ('simplify', 'name'),
            'external_organization':('simplify','name'),
            'address':             ('simplify', 'contact'),
            'integration_type':    ('simplify', 'id'),
        }

        def tv(v):
            if isinstance(v, (datetime.datetime, datetime.date)):
                return v.isoformat()
            if v in (None, '', {}, []):
                return 'N/A'
            return v

        def apply(e, rules):
            for field, (action, params) in rules.items():
                if action == 'simplify' and field in e and isinstance(e[field], dict):
                    e[field] = tv(e[field].get(params))
                elif action == 'join' and field in e and isinstance(e[field], list):
                    subf, delim = params
                    vals = [tv(i.get(subf)) for i in e[field] if isinstance(i, dict)]
                    e[field] = delim.join(x for x in vals if x != 'N/A') or 'N/A'
                else:
                    e[field] = tv(e.get(field))

        out = []
        if not isinstance(raw_data_list, list):
            return raw_data_list
        for rd in raw_data_list:
            if isinstance(rd, dict) and 'entities' in rd:
                for ent in rd['entities']:
                    pe = ent.copy()
                    if keys_removal:
                        for k in keys_removal:
                            pe.pop(k, None)
                    apply(pe, TRANSFORM)
                    out.append(pe)
            else:
                return raw_data_list
        return out


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  CUSTOM EXCEPTION
# ╚══════════════════════════════════════════════════════════════════════════════

class MyCustomError(Exception):
    pass


# ╔══════════════════════════════════════════════════════════════════════════════
# ║  ENTRY POINT
# ╚══════════════════════════════════════════════════════════════════════════════

def _check_terms_accepted() -> bool:
    """Return True if the user has previously accepted the terms of use."""
    import configparser, os
    cfg_dir  = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Pyramid")
    cfg_file = os.path.join(cfg_dir, "pyramid.cfg")
    cfg = configparser.ConfigParser()
    cfg.read(cfg_file)
    return cfg.get("Settings", "terms_accepted", fallback="0") == "1"


def _save_terms_accepted():
    """Persist terms acceptance to pyramid.cfg."""
    import configparser, os
    cfg_dir  = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Pyramid")
    cfg_file = os.path.join(cfg_dir, "pyramid.cfg")
    os.makedirs(cfg_dir, exist_ok=True)
    cfg = configparser.ConfigParser()
    cfg.read(cfg_file)
    if "Settings" not in cfg:
        cfg["Settings"] = {}
    cfg["Settings"]["terms_accepted"] = "1"
    with open(cfg_file, "w") as f:
        cfg.write(f)


def _show_terms_dialog(root: tk.Tk) -> bool:
    """
    Show a modal Terms of Use dialog on first run.
    Returns True if the user accepts, False if they decline.
    """
    accepted = tk.BooleanVar(value=False)

    dlg = tk.Toplevel(root)
    dlg.title("Terms of Use — Pyramid API Management")
    dlg.configure(bg=PALETTE["bg_base"])
    dlg.resizable(False, False)
    dlg.grab_set()

    # Centre on screen
    dlg.update_idletasks()
    w, h = 580, 460
    sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
    dlg.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # Header stripe
    tk.Frame(dlg, bg=PALETTE["accent"], height=4).pack(fill="x")

    # Logo / title
    top = tk.Frame(dlg, bg=PALETTE["bg_base"])
    top.pack(fill="x", padx=28, pady=(20, 0))
    tk.Label(top, text="Pyramid API Management",
             bg=PALETTE["bg_base"], fg=PALETTE["accent_hi"],
             font=("Segoe UI", 15, "bold")).pack(anchor="w")
    tk.Label(top, text="Terms of Use  •  First-run agreement",
             bg=PALETTE["bg_base"], fg=PALETTE["fg_muted"],
             font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 0))

    tk.Frame(dlg, bg=PALETTE["border"], height=1).pack(fill="x", padx=28, pady=12)

    # Terms text
    terms_text = (
        "By using this software you agree to the following:\n\n"

        "1.  AUTHORIZED USE ONLY\n"
        "    Use this tool only with organizations for which you hold valid\n"
        "    administrative credentials and explicit permission to access.\n"
        "    Unauthorized access to third-party systems may constitute a\n"
        "    criminal offence under applicable computer-fraud legislation\n"
        "    (e.g. CFAA, Computer Misuse Act, Lei nº 12.737/2012 — Brazil).\n\n"

        "2.  DATA PRIVACY\n"
        "    This tool may retrieve personal data (names, e-mails, login\n"
        "    history). You are solely responsible for handling that data in\n"
        "    compliance with applicable privacy law (LGPD, GDPR, etc.) and\n"
        "    your organization's data-protection policies.\n\n"

        "3.  NO WARRANTY — USE AT YOUR OWN RISK\n"
        "    This software is provided \"as is\", without warranty of any kind,\n"
        "    express or implied, including but not limited to warranties of\n"
        "    merchantability, fitness for a particular purpose, or non-infringement.\n"
        "    The author accepts no liability whatsoever for any direct, indirect,\n"
        "    incidental or consequential damages arising from the use or inability\n"
        "    to use this software. YOU USE THIS SOFTWARE ENTIRELY AT YOUR OWN RISK.\n\n"

        "4.  CREDENTIAL STORAGE\n"
        "    OAuth Client IDs and Secrets are stored in PLAIN TEXT in a local\n"
        "    configuration file (%APPDATA%\\Pyramid\\pyramid.cfg).\n"
        "    Protect that file using OS-level access controls. Do not use\n"
        "    this tool on shared or untrusted machines.\n\n"

        "5.  LICENSE\n"
        "    This software is distributed under the MIT License.\n"
        "    You are free to use, copy, modify, merge, publish, distribute,\n"
        "    sublicense and/or sell copies, provided this notice is retained.\n"
        "    Full license: https://opensource.org/licenses/MIT"
    )

    ta = scrolledtext.ScrolledText(
        dlg, wrap=tk.WORD, height=13,
        bg=PALETTE["bg_raised"], fg=PALETTE["fg_primary"],
        font=("Consolas", 9), relief="flat", bd=0,
        insertbackground=PALETTE["accent"],
        padx=12, pady=10,
    )
    ta.pack(fill="both", expand=True, padx=28)
    ta.insert(tk.END, terms_text)
    ta.config(state="disabled")

    tk.Frame(dlg, bg=PALETTE["border"], height=1).pack(fill="x", padx=28, pady=10)

    # Buttons
    btn_row = tk.Frame(dlg, bg=PALETTE["bg_base"])
    btn_row.pack(padx=28, pady=(0, 20), anchor="e")

    def _decline():
        accepted.set(False)
        dlg.destroy()

    def _accept():
        accepted.set(True)
        dlg.destroy()

    _tk_button(btn_row, "✗  Decline", _decline, kind="danger").pack(side="left", padx=(0, 8))
    _tk_button(btn_row, "✓  I Accept", _accept, kind="accent").pack(side="left")

    # Prevent closing via X without choosing
    dlg.protocol("WM_DELETE_WINDOW", _decline)

    root.wait_window(dlg)
    return accepted.get()


def main():
    root = tk.Tk()
    root.withdraw()   # hide main window until terms are resolved

    if not _check_terms_accepted():
        if not _show_terms_dialog(root):
            root.destroy()
            return
        _save_terms_accepted()

    root.deiconify()
    app  = GCApplication(root)
    root.mainloop()


if __name__ == "__main__":
    main()
