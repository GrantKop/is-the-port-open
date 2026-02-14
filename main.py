import time
import socket
import threading
import configparser
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import os
import sys
import traceback

import customtkinter
import tkinter.messagebox as mbox

def _gui_excepthook(exc_type, exc, tb):
    msg = "".join(traceback.format_exception(exc_type, exc, tb))
    mbox.showerror("Unexpected Error", msg)

sys.excepthook = _gui_excepthook

ACCENT = "#3B82F6"   
ACCENT_2 = "#22D3EE"
SURFACE = "#111827"  
SURFACE_2 = "#0B1220"
CARD = "#141A2A"     
CARD_ALT = "#121829" 
BORDER = "#27324A"
TEXT_MUTED = "#9CA3AF"

APP_NAME = "IsThePortOpen"
INI_FILENAME  = "itpo.ini"


def get_config_path() -> str:
    home = Path.home()

    if sys.platform.startswith("win"):
        base = Path(os.getenv("APPDATA") or (home / "AppData" / "Roaming"))
        folder = base / APP_NAME
    elif sys.platform == "darwin":
        folder = home / "Library" / "Application Support" / APP_NAME
    else:
        base = Path(os.getenv("XDG_CONFIG_HOME") or (home / ".config"))
        folder = base / APP_NAME

    folder.mkdir(parents=True, exist_ok=True)
    return str(folder / INI_FILENAME)

INI_PATH = get_config_path()

@dataclass
class Target:
    name: str
    host: str
    port: int


def _read_ini(path: str) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
    cfg.optionxform = str
    p = Path(path)
    if p.exists():
        cfg.read(path)
    return cfg


def load_state(path: str = INI_PATH):
    cfg = _read_ini(path)

    timeout = cfg.getfloat("SETTINGS", "TIMEOUT_SECONDS", fallback=5.0)
    max_workers = cfg.getint("SETTINGS", "MAX_WORKERS", fallback=10)
    auto_refresh = cfg.getint("SETTINGS", "AUTO_REFRESH_SECONDS", fallback=0)

    targets: list[Target] = []
    if cfg.has_section("TARGETS"):
        for name, value in cfg["TARGETS"].items():
            raw = value.strip()
            if ":" not in raw:
                continue
            host, port_str = raw.rsplit(":", 1)
            host = host.strip()
            port_str = port_str.strip()
            try:
                port = int(port_str)
                if not (1 <= port <= 65535):
                    raise ValueError("port out of range")
            except Exception:
                continue

            if host and name.strip():
                targets.append(Target(name=name.strip(), host=host, port=port))

    return timeout, max_workers, auto_refresh, targets


def save_state(timeout: float, max_workers: int, auto_refresh: int, targets: list[Target], path: str = INI_PATH):
    cfg = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
    cfg.optionxform = str

    cfg["SETTINGS"] = {
        "TIMEOUT_SECONDS": str(timeout),
        "MAX_WORKERS": str(max_workers),
        "AUTO_REFRESH_SECONDS": str(auto_refresh),
    }

    cfg["TARGETS"] = {}
    for t in targets:
        cfg["TARGETS"][t.name] = f"{t.host}:{t.port}"

    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        cfg.write(f)
    Path(tmp_path).replace(path)

def check_tcp_open(host: str, port: int, timeout_seconds: float):
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            latency_ms = (time.perf_counter() - start) * 1000.0
            return "OPEN", latency_ms
    except socket.gaierror:
        return "DNS_FAIL", None
    except TimeoutError:
        return "TIMEOUT", None
    except OSError as e:
        if isinstance(e, ConnectionRefusedError):
            return "CLOSED", None
        return "ERROR", None

class TargetRow:
    def __init__(self, parent, target: Target, idx: int, on_delete):
        self.target = target
        self.on_delete = on_delete

        row_color = CARD if (idx % 2 == 0) else CARD_ALT

        self.frame = customtkinter.CTkFrame(
            parent,
            corner_radius=12,
            fg_color=row_color,
            border_width=1,
            border_color=BORDER,
        )
        self.frame.pack(fill="x", padx=10, pady=4)

        NAME_W = 170
        PORT_W = 80
        STATUS_W = 140
        PAD_L = 10

        self.name_label = customtkinter.CTkLabel(
            self.frame,
            text=target.name,
            font=("Arial", 15, "bold"),
            width=NAME_W,
            anchor="w",
            text_color="#E5E7EB",
        )
        self.name_label.grid(row=0, column=0, padx=(PAD_L, 8), pady=10, sticky="w")

        self.host_label = customtkinter.CTkLabel(
            self.frame,
            text=target.host,
            font=("Arial", 14),
            anchor="w",
            text_color=TEXT_MUTED,
        )
        self.host_label.grid(row=0, column=1, padx=8, pady=10, sticky="w")

        self.port_label = customtkinter.CTkLabel(
            self.frame,
            text=str(target.port),
            font=("Arial", 14),
            width=PORT_W,
            anchor="center",
            text_color=TEXT_MUTED,
        )
        self.port_label.grid(row=0, column=2, padx=8, pady=10)

        self.status_label = customtkinter.CTkLabel(
            self.frame,
            text="—",
            font=("Arial", 13, "bold"),
            width=STATUS_W,
            corner_radius=10,
            padx=10,
            pady=6,
            anchor="center",
            text_color="#E5E7EB",
            fg_color="#374151",
        )
        self.status_label.grid(row=0, column=3, padx=(8, 6), pady=10, sticky="e")

        self.delete_btn = customtkinter.CTkButton(
            self.frame,
            text="✕",
            width=36,
            height=30,
            corner_radius=10,
            fg_color="#374151",
            hover_color="#4B5563",
            text_color="#E5E7EB",
            command=self._delete_clicked,
        )
        self.delete_btn.grid(row=0, column=4, padx=(0, PAD_L), pady=10, sticky="e")

        self.frame.grid_columnconfigure(1, weight=1)

    def _delete_clicked(self):
        if self.on_delete:
            self.on_delete(self)

    def set_delete_enabled(self, enabled: bool):
        self.delete_btn.configure(state=("normal" if enabled else "disabled"))

    def set_checking(self):
        self.status_label.configure(
            text="Checking...",
            text_color="#E5E7EB",
            fg_color="#374151"
        )

    def set_result(self, status: str, latency_ms: float | None):
        if status == "OPEN":
            fg = "#064E3B"
            txt = "#34D399"
        elif status == "CLOSED":
            fg = "#7F1D1D"
            txt = "#FCA5A5"
        elif status == "TIMEOUT":
            fg = "#78350F"
            txt = "#FBBF24"
        elif status == "DNS_FAIL":
            fg = "#312E81"
            txt = "#A5B4FC"
        else:
            fg = "#374151"
            txt = "#E5E7EB"

        label = status
        if status == "OPEN" and latency_ms is not None:
            label = f"OPEN ({latency_ms:.0f}ms)"

        self.status_label.configure(text=label, text_color=txt, fg_color=fg)

    def destroy(self):
        self.frame.destroy()


class AddTargetDialog(customtkinter.CTkToplevel):
    def __init__(self, master, on_submit):
        super().__init__(master)
        self.on_submit = on_submit
        self.title("Add Target")
        self.geometry("420x240")
        self.resizable(False, False)
        self.configure(fg_color=SURFACE)

        self.grab_set()
        self.focus()

        title = customtkinter.CTkLabel(self, text="Add Target", font=("Arial", 18, "bold"), text_color=ACCENT_2)
        title.pack(pady=(8, 4))

        form = customtkinter.CTkFrame(self, corner_radius=12, fg_color=SURFACE_2, border_width=1, border_color=BORDER)
        form.pack(fill="x", padx=14, pady=1)

        form.grid_columnconfigure(0, weight=0)
        form.grid_columnconfigure(1, weight=1)

        label_font = ("Arial", 13, "bold")
        entry_font = ("Arial", 13)

        def mk_label(text, r):
            lbl = customtkinter.CTkLabel(form, text=text, font=label_font, text_color=ACCENT, anchor="w")
            lbl.grid(row=r, column=0, padx=(12, 10), pady=6, sticky="w")
            return lbl

        mk_label("Name:", 0)
        self.name = customtkinter.CTkEntry(form, placeholder_text="Name (e.g. Minecraft)", font=entry_font)
        self.name.grid(row=0, column=1, padx=(0, 12), pady=6, sticky="ew")

        mk_label("Host:", 1)
        self.host = customtkinter.CTkEntry(form, placeholder_text="Host (e.g. 1.2.3.4 or example.com)", font=entry_font)
        self.host.grid(row=1, column=1, padx=(0, 12), pady=6, sticky="ew")

        mk_label("Port:", 2)
        self.port = customtkinter.CTkEntry(form, placeholder_text="Port (1-65535)", font=entry_font)
        self.port.grid(row=2, column=1, padx=(0, 12), pady=6, sticky="ew")

        self.error = customtkinter.CTkLabel(self, text="", font=("Arial", 12), text_color="#FCA5A5")
        self.error.pack(pady=(1, 5))

        btns = customtkinter.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=0)

        cancel = customtkinter.CTkButton(
            btns, text="Cancel", width=120, height=34, corner_radius=12,
            fg_color="#374151", hover_color="#4B5563",
            command=self.destroy
        )
        cancel.grid(row=0, column=0, padx=8)

        add = customtkinter.CTkButton(
            btns, text="Add", width=120, height=34, corner_radius=12,
            fg_color=ACCENT, hover_color="#2563EB",
            command=self._submit
        )
        add.grid(row=0, column=1, padx=8)

        self.bind("<Return>", lambda e: self._submit())
        self.bind("<Escape>", lambda e: self.destroy())

    def _submit(self):
        if self.error.winfo_manager():
            self.error.pack_forget()

        name = self.name.get().strip()
        host = self.host.get().strip()
        port_str = self.port.get().strip()

        if not name:
            self.error.configure(text="Name is required.")
            return
        if not host:
            self.error.configure(text="Host is required.")
            return
        try:
            port = int(port_str)
            if not (1 <= port <= 65535):
                raise ValueError()
        except Exception:
            self.error.configure(text="Port must be a number from 1 to 65535.")
            return

        self.on_submit(Target(name=name, host=host, port=port))
        self.destroy()


class SettingsDialog(customtkinter.CTkToplevel):
    def __init__(self, master, timeout: float, max_workers: int, auto_refresh: int, on_apply):
        super().__init__(master)
        self.on_apply = on_apply
        self.title("Settings")
        self.geometry("420x240")
        self.resizable(False, False)
        self.configure(fg_color=SURFACE)

        self.grab_set()
        self.focus()

        title = customtkinter.CTkLabel(self, text="Settings", font=("Arial", 18, "bold"), text_color=ACCENT_2)
        title.pack(pady=(8, 4))

        form = customtkinter.CTkFrame(self, corner_radius=12, fg_color=SURFACE_2, border_width=1, border_color=BORDER)
        form.pack(fill="x", padx=14, pady=1)

        form.grid_columnconfigure(0, weight=0)
        form.grid_columnconfigure(1, weight=1)

        label_font = ("Arial", 13, "bold")
        entry_font = ("Arial", 13)

        def mk_row(text, r, initial):
            lbl = customtkinter.CTkLabel(form, text=text, font=label_font, text_color=ACCENT, anchor="w")
            lbl.grid(row=r, column=0, padx=(12, 10), pady=6, sticky="w")
            ent = customtkinter.CTkEntry(form, font=entry_font)
            ent.grid(row=r, column=1, padx=(0, 12), pady=6, sticky="ew")
            ent.insert(0, str(initial))
            return ent

        self.timeout = mk_row("Timeout:", 0, timeout)
        self.max_workers = mk_row("Max workers:", 1, max_workers)
        self.auto_refresh = mk_row("Auto refresh:", 2, auto_refresh)

        self.error = customtkinter.CTkLabel(self, text="", font=("Arial", 12), text_color="#FCA5A5")
        self.error.pack(pady=(1, 5))

        btns = customtkinter.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=0)

        cancel = customtkinter.CTkButton(
            btns, text="Cancel", width=120, height=34, corner_radius=12,
            fg_color="#374151", hover_color="#4B5563",
            command=self.destroy
        )
        cancel.grid(row=0, column=0, padx=8)

        apply_btn = customtkinter.CTkButton(
            btns, text="Apply", width=120, height=34, corner_radius=12,
            fg_color=ACCENT, hover_color="#2563EB",
            command=self._apply
        )
        apply_btn.grid(row=0, column=1, padx=8)

        self.bind("<Return>", lambda e: self._apply())
        self.bind("<Escape>", lambda e: self.destroy())

    def _apply(self):
        try:
            timeout = float(self.timeout.get().strip())
            if timeout <= 0:
                raise ValueError()
        except Exception:
            self.error.configure(text="Timeout must be a positive number.")
            return

        try:
            max_workers = int(self.max_workers.get().strip())
            if max_workers < 1 or max_workers > 500:
                raise ValueError()
        except Exception:
            self.error.configure(text="Max workers must be an integer from 1 to 500.")
            return

        try:
            auto_refresh = int(self.auto_refresh.get().strip())
            if auto_refresh < 0:
                raise ValueError()
        except Exception:
            self.error.configure(text="Auto refresh must be 0 or a positive integer.")
            return

        self.on_apply(timeout, max_workers, auto_refresh)
        self.destroy()

class App(customtkinter.CTk):
    def __init__(self):
        super().__init__()

        customtkinter.set_appearance_mode("Dark")
        customtkinter.set_default_color_theme("blue")

        self.title("Is The Port Open - v1.0")
        self.geometry("700x600")
        self.minsize(700, 600)
        self.resizable(False, True)
        self.configure(fg_color=SURFACE)

        self.timeout, self.max_workers, self.auto_refresh_seconds, targets = load_state()

        self.targets: list[Target] = list(targets)
        self.rows: list[TargetRow] = []

        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self.refresh_lock = threading.Lock()
        self.refresh_in_progress = False
        self._auto_after_id = None

        title = customtkinter.CTkLabel(
            self, text="Is The Port Open", font=("Arial", 22, "bold"),
            text_color=ACCENT_2
        )
        title.pack(pady=(14, 6))

        self.meta_label = customtkinter.CTkLabel(
            self, text="Last checked: —", font=("Arial", 12),
            text_color=TEXT_MUTED
        )
        self.meta_label.pack(pady=(0, 8))

        header = customtkinter.CTkFrame(
            self, corner_radius=12, fg_color=SURFACE_2, border_width=1, border_color=BORDER
        )
        header.pack(fill="x", padx=10, pady=(12, 0))

        NAME_W = 170
        PORT_W = 95
        STATUS_W = 140
        PAD_L = 30

        hdr_name = customtkinter.CTkLabel(
            header, text="Name", font=("Arial", 13, "bold"), text_color=ACCENT,
            width=NAME_W, anchor="w"
        )
        hdr_name.grid(row=0, column=0, padx=(PAD_L, 20), pady=8, sticky="w")

        hdr_host = customtkinter.CTkLabel(
            header, text="Host", font=("Arial", 13, "bold"), text_color=ACCENT,
            anchor="w"
        )
        hdr_host.grid(row=0, column=1, padx=8, pady=8, sticky="w")

        hdr_port = customtkinter.CTkLabel(
            header, text="Port", font=("Arial", 13, "bold"), text_color=ACCENT,
            width=PORT_W, anchor="center"
        )
        hdr_port.grid(row=0, column=2, padx=8, pady=8)

        hdr_status = customtkinter.CTkLabel(
            header, text="Status", font=("Arial", 13, "bold"), text_color=ACCENT,
            width=STATUS_W, anchor="center"
        )
        hdr_status.grid(row=0, column=3, padx=(4, 8), pady=8, sticky="e")

        hdr_del = customtkinter.CTkLabel(
            header, text="", width=36
        )
        hdr_del.grid(row=0, column=4, padx=(0, PAD_L), pady=8, sticky="e")

        header.grid_columnconfigure(1, weight=1)

        self.scroll = customtkinter.CTkScrollableFrame(self)
        self.scroll.pack(padx=10, pady=8, fill="both", expand=True)

        self.add_row_frame = customtkinter.CTkFrame(
            self.scroll,
            corner_radius=12,
            fg_color=SURFACE_2,
            border_width=1,
            border_color=BORDER,
        )
        self.add_btn = customtkinter.CTkButton(
            self.add_row_frame,
            text="+",
            width=44,
            height=40,
            corner_radius=12,
            font=("Arial", 18, "bold"),
            fg_color=ACCENT,
            hover_color="#2563EB",
            command=self.open_add_dialog,
        )

        controls = customtkinter.CTkFrame(self, fg_color="transparent")
        controls.pack(pady=14)

        self.settings_button = customtkinter.CTkButton(
            controls, text="Settings", command=self.open_settings,
            width=140, height=40, corner_radius=12,
            font=("Arial", 16, "bold"),
            fg_color="#374151", hover_color="#4B5563",
            text_color="#FFFFFF",
        )
        self.settings_button.grid(row=0, column=0, padx=10)

        self.refresh_button = customtkinter.CTkButton(
            controls, text="Refresh", command=self.refresh_async,
            width=140, height=40, corner_radius=12,
            font=("Arial", 16, "bold"),
            fg_color=ACCENT, hover_color="#2563EB",
            text_color="#FFFFFF",
        )
        self.refresh_button.grid(row=0, column=1, padx=10)

        self.rebuild_rows()

        self.refresh_async()
        self._schedule_auto_refresh()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def rebuild_rows(self):
        for r in self.rows:
            r.destroy()
        self.rows.clear()

        for i, t in enumerate(self.targets):
            self.rows.append(TargetRow(self.scroll, t, i, on_delete=self.delete_row))

        self.add_row_frame.pack(fill="x", padx=10, pady=(10, 10))
        self.add_btn.pack(pady=10)

    def delete_row(self, row: TargetRow):
        if self.refresh_in_progress:
            return 
        self.targets = [t for t in self.targets if not (t.name == row.target.name and t.host == row.target.host and t.port == row.target.port)]
        self.persist()
        self.rebuild_rows()

    def open_add_dialog(self):
        if self.refresh_in_progress:
            return
        AddTargetDialog(self, on_submit=self.add_target)

    def add_target(self, t: Target):
        existing = {x.name for x in self.targets}
        base = t.name
        if base in existing:
            n = 2
            while f"{base} ({n})" in existing:
                n += 1
            t.name = f"{base} ({n})"

        self.targets.append(t)
        self.persist()
        self.rebuild_rows()
        self.refresh_async()

    def open_settings(self):
        if self.refresh_in_progress:
            return
        SettingsDialog(
            self,
            timeout=self.timeout,
            max_workers=self.max_workers,
            auto_refresh=self.auto_refresh_seconds,
            on_apply=self.apply_settings
        )

    def apply_settings(self, timeout: float, max_workers: int, auto_refresh: int):
        old_workers = self.max_workers

        self.timeout = timeout
        self.max_workers = max_workers
        self.auto_refresh_seconds = auto_refresh

        if self.max_workers != old_workers:
            try:
                self.executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
            self.executor = ThreadPoolExecutor(max_workers=self.max_workers)

        self.persist()
        self._schedule_auto_refresh()

        self.refresh_async()

    def _schedule_auto_refresh(self):
        if self._auto_after_id is not None:
            try:
                self.after_cancel(self._auto_after_id)
            except Exception:
                pass
            self._auto_after_id = None

        if self.auto_refresh_seconds and self.auto_refresh_seconds > 0:
            self._auto_after_id = self.after(self.auto_refresh_seconds * 1000, self._auto_refresh_tick)

    def _auto_refresh_tick(self):
        self.refresh_async()
        self._schedule_auto_refresh()

    def persist(self):
        save_state(
            timeout=self.timeout,
            max_workers=self.max_workers,
            auto_refresh=self.auto_refresh_seconds,
            targets=self.targets,
            path=INI_PATH
        )

    def _set_editing_enabled(self, enabled: bool):
        self.add_btn.configure(state=("normal" if enabled else "disabled"))
        self.settings_button.configure(state=("normal" if enabled else "disabled"))
        for r in self.rows:
            r.set_delete_enabled(enabled)

    def refresh_async(self):
        if self.refresh_in_progress:
            return

        with self.refresh_lock:
            if self.refresh_in_progress:
                return
            self.refresh_in_progress = True

        self.refresh_button.configure(state="disabled")
        self._set_editing_enabled(False)

        for row in self.rows:
            row.set_checking()

        threading.Thread(target=self._refresh_worker, daemon=True).start()

    def _refresh_worker(self):
        try:
            futures = {}
            for row in list(self.rows):
                t = row.target
                fut = self.executor.submit(check_tcp_open, t.host, t.port, self.timeout)
                futures[fut] = row

            results = []
            for fut in as_completed(futures):
                row = futures[fut]
                status, latency = fut.result()
                results.append((row, status, latency))

            def apply_results():
                for row, status, latency in results:
                    row.set_result(status, latency)

                self.meta_label.configure(text=f"Last checked: {time.strftime('%Y-%m-%d %H:%M:%S')}")
                self.refresh_button.configure(state="normal")
                self._set_editing_enabled(True)
                self.refresh_in_progress = False

            self.after(0, apply_results)

        except Exception:
            def recover():
                self.refresh_button.configure(state="normal")
                self._set_editing_enabled(True)
                self.refresh_in_progress = False
            self.after(0, recover)

    def on_close(self):
        try:
            self.persist()
        except Exception:
            pass
        try:
            self.executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
