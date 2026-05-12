"""
番茄钟 2.0 — 桌面番茄钟计时器
功能：番茄工作法计时、任务管理、每日统计、自定义设置、键盘快捷键
"""

import tkinter as tk
import json
import os
import time
import winsound
from datetime import date

# ─── File Paths ──────────────────────────────────────────
DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(DIR, "config.json")
STATS_PATH = os.path.join(DIR, "stats.json")

# ─── Color Palette (Catppuccin Mocha) ────────────────────
BG          = "#1e1e2e"
SURFACE     = "#181825"
FG          = "#cdd6f4"
SUBTLE      = "#a6adc8"
DIM         = "#6c7086"
WORK_CLR    = "#f38ba8"
BREAK_CLR   = "#a6e3a1"
LONG_CLR    = "#89b4fa"
ACCENT      = "#89b4fa"
BTN_BG      = "#313244"
BTN_HOVER   = "#45475a"
BTN_ACTIVE  = "#585b70"
TRACK       = "#313244"
SUCCESS     = "#a6e3a1"
WARN        = "#f9e2af"
SEPARATOR   = "#313244"
SURFACE2    = "#585b70"

# ─── Defaults ────────────────────────────────────────────
DEFAULT_CONFIG = {
    "work_min": 25,
    "short_break_min": 5,
    "long_break_min": 15,
    "auto_start": False,
    "sound_enabled": True,
}
DEFAULT_STATS = {"total_completed": 0, "total_focus_seconds": 0, "days": {}}

PHASES = {
    "WORK":        {"label": "🍅 工作中",   "key": "work_min",        "color": WORK_CLR},
    "SHORT_BREAK": {"label": "☕ 短休息",   "key": "short_break_min", "color": BREAK_CLR},
    "LONG_BREAK":  {"label": "🎉 长休息",   "key": "long_break_min",  "color": LONG_CLR},
}


# ─── Scrollable Frame ────────────────────────────────────

class ScrollableFrame(tk.Frame):
    """A frame whose contents can be scrolled."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        self.scrollbar = tk.Scrollbar(self, orient="vertical",
                                       bg=BTN_BG, troughcolor=BG, activebackground=BTN_HOVER)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.inner.bind("<Configure>", self._on_inner_configure)
        self._inner_win = self.canvas.create_window(
            (0, 0), window=self.inner, anchor="nw", tags="inner")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self._bind_wheel()

    def _on_inner_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.itemconfig("inner", width=self.canvas.winfo_width())

    def _bind_wheel(self):
        def on_wheel(event):
            self.canvas.yview_scroll(-1 * (event.delta // 120), "units")
        self.canvas.bind_all("<MouseWheel>", on_wheel, add="+")

    def destroy(self):
        self.canvas.unbind_all("<MouseWheel>")
        super().destroy()


# ─── Main App ────────────────────────────────────────────

class PomodoroApp:

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("番茄钟")
        self.root.geometry("420x700")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.center_window()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Load data
        self.config = self.load_config()
        self.stats = self.load_stats()
        self.today = date.today().isoformat()
        self._ensure_today()

        # Timer state
        self.phase = "WORK"
        self.state = "IDLE"          # IDLE | RUNNING | PAUSED
        self.completed = 0
        self.session_idx = 0
        self.total = self._phase_secs("WORK")
        self.remaining = float(self.total)
        self._end_time = 0.0
        self._job = None
        self._flash_job = None
        self._settings_win = None

        # Tasks
        self.tasks = self._load_today_tasks()
        self._task_widgets = []

        # Build & go
        self.build_ui()
        self.sync_ui()
        self.root.bind("<space>", lambda e: self.toggle_start())
        self.root.bind("<r>", lambda e: self.reset())
        self.root.bind("<s>", lambda e: self.skip())
        self.root.bind("<Escape>", lambda e: self._close_settings())
        self.root.mainloop()

    # ── Window helpers ────────────────────────────────────

    def center_window(self):
        self.root.update_idletasks()
        w, h = 420, 700
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    # ── Persistence ───────────────────────────────────────

    def load_config(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except (FileNotFoundError, json.JSONDecodeError):
            return dict(DEFAULT_CONFIG)

    def save_config(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def load_stats(self):
        try:
            with open(STATS_PATH, "r", encoding="utf-8") as f:
                return {**DEFAULT_STATS, **json.load(f)}
        except (FileNotFoundError, json.JSONDecodeError):
            return dict(DEFAULT_STATS)

    def save_stats(self):
        try:
            with open(STATS_PATH, "w", encoding="utf-8") as f:
                json.dump(self.stats, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _ensure_today(self):
        if self.today not in self.stats["days"]:
            self.stats["days"][self.today] = {"completed": 0, "focus_seconds": 0}

    def _load_today_tasks(self):
        self._ensure_today()
        return self.stats["days"][self.today].get("tasks", [])

    def _save_today_tasks(self):
        self._ensure_today()
        self.stats["days"][self.today]["tasks"] = self.tasks
        self.save_stats()

    def _phase_secs(self, name):
        key = PHASES[name]["key"]
        return self.config.get(key, DEFAULT_CONFIG[key]) * 60

    # ── UI Build ──────────────────────────────────────────

    def build_ui(self):
        # ── Header ─────────────────────────────────────
        hdr = tk.Frame(self.root, bg=BG)
        hdr.pack(fill="x", padx=24, pady=(18, 0))

        tk.Label(hdr, text="🍅 番茄钟", font=("Segoe UI", 18, "bold"),
                 bg=BG, fg=FG).pack(side="left")

        btn_hdr = tk.Frame(hdr, bg=BG)
        btn_hdr.pack(side="right")

        self.pin_btn = tk.Label(btn_hdr, text="📌", font=("Segoe UI", 13),
                                bg=BG, fg=DIM, cursor="hand2")
        self.pin_btn.pack(side="left", padx=(0, 10))
        self.pin_btn.bind("<Button-1>", lambda e: self.toggle_pin())
        self._hover_fg(self.pin_btn, SUBTLE, DIM)

        self.gear_btn = tk.Label(btn_hdr, text="⚙️", font=("Segoe UI", 13),
                                 bg=BG, fg=DIM, cursor="hand2")
        self.gear_btn.pack(side="left")
        self.gear_btn.bind("<Button-1>", lambda e: self.open_settings())
        self._hover_fg(self.gear_btn, SUBTLE, DIM)

        # ── Timer Canvas ───────────────────────────────
        self.c_size = 240
        cf = tk.Frame(self.root, bg=BG)
        cf.pack(pady=(20, 0))

        self.canvas = tk.Canvas(cf, width=self.c_size, height=self.c_size,
                                bg=BG, highlightthickness=0)
        self.canvas.pack()

        pad = 14
        aw = 10
        self.arc_bbox = (pad, pad, self.c_size - pad, self.c_size - pad)
        self.canvas.create_arc(self.arc_bbox, start=0, extent=360,
                               outline=TRACK, width=aw, style="arc")
        self.progress = self.canvas.create_arc(
            self.arc_bbox, start=90, extent=0,
            outline=WORK_CLR, width=aw, style="arc")

        cx = self.c_size // 2
        self.time_text = self.canvas.create_text(
            cx, cx - 6, text="25:00", font=("Segoe UI", 48, "bold"),
            fill=FG, anchor="center")
        self.phase_text = self.canvas.create_text(
            cx, cx + 34, text="工作中", font=("Segoe UI", 13),
            fill=WORK_CLR, anchor="center")

        # ── Session info ───────────────────────────────
        info_row = tk.Frame(self.root, bg=BG)
        info_row.pack(pady=(4, 0))
        self.session_label = tk.Label(info_row, text="第 1/4 轮 · 今日 0 个",
                                      font=("Segoe UI", 10), bg=BG, fg=DIM)
        self.session_label.pack()

        # ── Separator ──────────────────────────────────
        tk.Frame(self.root, bg=SEPARATOR, height=1).pack(fill="x", padx=30, pady=(8, 0))

        # ── Controls ───────────────────────────────────
        ctrl = tk.Frame(self.root, bg=BG)
        ctrl.pack(pady=(10, 0))

        self.start_btn = self._btn(ctrl, "▶  开始", self.toggle_start)
        self.start_btn.pack(side="left", padx=4)
        self.reset_btn = self._btn(ctrl, "⟳  重置", self.reset)
        self.reset_btn.pack(side="left", padx=4)
        self.skip_btn = self._btn(ctrl, "⏭  跳过", self.skip)
        self.skip_btn.pack(side="left", padx=4)

        # ── Quick toggles ─────────────────────────────
        qt = tk.Frame(self.root, bg=BG)
        qt.pack(pady=(4, 0))

        self.auto_var = tk.BooleanVar(value=self.config.get("auto_start", False))
        tk.Checkbutton(qt, text="自动继续", variable=self.auto_var,
                       bg=BG, fg=DIM, selectcolor=BG,
                       activebackground=BG, activeforeground=ACCENT,
                       font=("Segoe UI", 9), cursor="hand2",
                       command=self._toggle_auto).pack(side="left", padx=8)

        self.sound_var = tk.BooleanVar(value=self.config.get("sound_enabled", True))
        tk.Checkbutton(qt, text="声音提示", variable=self.sound_var,
                       bg=BG, fg=DIM, selectcolor=BG,
                       activebackground=BG, activeforeground=ACCENT,
                       font=("Segoe UI", 9), cursor="hand2",
                       command=self._toggle_sound).pack(side="left", padx=8)

        # ── Task Section ───────────────────────────────
        ts = tk.Frame(self.root, bg=BG)
        ts.pack(fill="both", padx=24, pady=(8, 0), expand=True)

        th = tk.Frame(ts, bg=BG)
        th.pack(fill="x")
        tk.Label(th, text="📋 今日任务", font=("Segoe UI", 11, "bold"),
                 bg=BG, fg=FG).pack(side="left")
        self.task_count = tk.Label(th, text="0/0", font=("Segoe UI", 9), bg=BG, fg=DIM)
        self.task_count.pack(side="right")

        # Task input
        ti = tk.Frame(ts, bg=BG)
        ti.pack(fill="x", pady=(5, 5))

        self.task_entry = tk.Entry(ti, font=("Segoe UI", 10),
                                   bg=SURFACE, fg=DIM, insertbackground=FG,
                                   bd=0, relief="flat", highlightthickness=1,
                                   highlightbackground=SEPARATOR, highlightcolor=ACCENT)
        self.task_entry.pack(side="left", fill="x", expand=True, ipadx=8, ipady=4)
        self.task_entry.insert(0, "添加新任务...")
        self.task_entry.bind("<FocusIn>", self._entry_focus_in)
        self.task_entry.bind("<FocusOut>", self._entry_focus_out)
        self.task_entry.bind("<Return>", lambda e: self.add_task())

        add_lbl = tk.Label(ti, text="＋", font=("Segoe UI", 16),
                           bg=BTN_BG, fg=FG, cursor="hand2", padx=6)
        add_lbl.pack(side="right", padx=(6, 0))
        add_lbl.bind("<Button-1>", lambda e: self.add_task())
        self._hover_bg(add_lbl, BTN_HOVER, BTN_BG)

        # Scrollable task list
        self.task_scroll = ScrollableFrame(ts)
        self.task_scroll.pack(fill="both", expand=True)
        self.refresh_tasks()

        # ── Stats Bar (bottom) ─────────────────────────
        sb = tk.Frame(self.root, bg=SURFACE, height=38)
        sb.pack(fill="x", side="bottom")

        tk.Label(sb, text="✅", font=("Segoe UI", 10), bg=SURFACE, fg=SUBTLE)\
            .pack(side="left", padx=(16, 2), pady=8)
        self.completed_label = tk.Label(sb, text="今日 0 个完成",
                                        font=("Segoe UI", 10), bg=SURFACE, fg=SUBTLE)
        self.completed_label.pack(side="left", pady=8)

        tk.Frame(sb, bg=SEPARATOR, width=1, height=18).pack(side="left", padx=12, pady=10)

        tk.Label(sb, text="⏱", font=("Segoe UI", 10), bg=SURFACE, fg=SUBTLE)\
            .pack(side="left", padx=(0, 2), pady=8)
        self.focus_label = tk.Label(sb, text="专注 0m",
                                    font=("Segoe UI", 10), bg=SURFACE, fg=SUBTLE)
        self.focus_label.pack(side="left", pady=8)

        self.total_label = tk.Label(sb, text="累计 0 个",
                                    font=("Segoe UI", 10), bg=SURFACE, fg=DIM)
        self.total_label.pack(side="right", padx=16, pady=8)

        # ── Footer hint ────────────────────────────────
        tk.Label(self.root, text="Space: 开始/暂停 · R: 重置 · S: 跳过",
                 font=("Segoe UI", 8), bg=BG, fg=SEPARATOR)\
            .pack(side="bottom", pady=(0, 4))

    # ── UI Helpers ────────────────────────────────────────

    def _btn(self, parent, text, cmd):
        btn = tk.Button(parent, text=text,
                        font=("Segoe UI", 10, "bold"),
                        bg=BTN_BG, fg=FG,
                        activebackground=ACCENT, activeforeground=BG,
                        bd=0, padx=14, pady=6, cursor="hand2", command=cmd)
        btn.bind("<Enter>", lambda e: e.widget.config(bg=BTN_HOVER))
        btn.bind("<Leave>", lambda e: e.widget.config(bg=BTN_BG))
        btn.bind("<ButtonPress-1>", lambda e: e.widget.config(bg=BTN_ACTIVE))
        btn.bind("<ButtonRelease-1>", lambda e: e.widget.config(bg=BTN_HOVER))
        return btn

    def _hover_fg(self, w, on, off):
        w.bind("<Enter>", lambda e: w.config(fg=on))
        w.bind("<Leave>", lambda e: w.config(fg=off))

    def _hover_bg(self, w, on, off):
        w.bind("<Enter>", lambda e: w.config(bg=on))
        w.bind("<Leave>", lambda e: w.config(bg=off))

    # ── UI Sync ───────────────────────────────────────────

    def sync_ui(self):
        p = PHASES[self.phase]
        clr = p["color"]

        label = p["label"]
        if self.state == "PAUSED":
            label += "  ⏸"
        self.canvas.itemconfig(self.phase_text, text=label, fill=clr)

        m, s = divmod(int(self.remaining), 60)
        self.canvas.itemconfig(self.time_text, text=f"{m:02d}:{s:02d}")

        prog = 1.0 - (self.remaining / self.total) if self.total > 0 else 0.0
        self.canvas.itemconfig(self.progress, outline=clr, extent=-360.0 * prog)

        disp = min(self.session_idx + 1, 4)
        today_done = self.stats["days"].get(self.today, {}).get("completed", 0)
        self.session_label.config(text=f"第 {disp}/4 轮 · 今日 {today_done} 个")

        self._update_stats_bar()

    def _update_stats_bar(self):
        day = self.stats["days"].get(self.today, {})
        done = day.get("completed", 0)
        secs = day.get("focus_seconds", 0)
        h, m = divmod(secs // 60, 60)
        focus = f"专注 {h}h{m}m" if h else f"专注 {m}m"
        self.completed_label.config(text=f"今日 {done} 个完成")
        self.focus_label.config(text=focus)
        self.total_label.config(text=f"累计 {self.stats['total_completed']} 个")

    # ── Timer ─────────────────────────────────────────────

    def toggle_start(self):
        if self.state in ("IDLE", "PAUSED"):
            self.state = "RUNNING"
            self._end_time = time.time() + self.remaining
            self.start_btn.config(text="⏸  暂停")
            self._tick()
        elif self.state == "RUNNING":
            self.state = "PAUSED"
            self.start_btn.config(text="▶  继续")
            if self._job:
                self.root.after_cancel(self._job)
                self._job = None
        self.sync_ui()

    def reset(self):
        self._cancel_job()
        self._stop_flash()
        self.state = "IDLE"
        self.remaining = float(self.total)
        self.start_btn.config(text="▶  开始")
        self.sync_ui()

    def skip(self):
        self._cancel_job()
        self._stop_flash()
        self._on_time_up(skip=True)

    def _tick(self):
        if self.state != "RUNNING":
            return
        self.remaining = max(0.0, self._end_time - time.time())
        self.sync_ui()
        if self.remaining <= 0:
            self._on_time_up()
        else:
            self._job = self.root.after(50, self._tick)

    def _cancel_job(self):
        if self._job:
            self.root.after_cancel(self._job)
            self._job = None

    def _on_time_up(self, skip=False):
        self._job = None
        self.state = "IDLE"
        self.start_btn.config(text="▶  开始")

        if self.phase == "WORK":
            self.completed += 1
            self.session_idx += 1
            self._ensure_today()
            self.stats["days"][self.today]["completed"] += 1
            self.stats["total_completed"] += 1
            work_s = self._phase_secs("WORK")
            self.stats["days"][self.today]["focus_seconds"] += work_s
            self.stats["total_focus_seconds"] += work_s
            self.save_stats()

        if self.phase == "WORK":
            self.phase = "LONG_BREAK" if self.session_idx >= 4 else "SHORT_BREAK"
            if self.session_idx >= 4:
                self.session_idx = 0
        else:
            self.phase = "WORK"

        self.total = self._phase_secs(self.phase)
        self.remaining = float(self.total)
        self.sync_ui()

        if not skip:
            self._notify()

        if self.config.get("auto_start") and not skip:
            self.root.after(1000, self.toggle_start)

    # ── Tasks ─────────────────────────────────────────────

    def _entry_focus_in(self, event=None):
        if self.task_entry.get() == "添加新任务...":
            self.task_entry.delete(0, "end")
            self.task_entry.config(fg=FG)

    def _entry_focus_out(self, event=None):
        if not self.task_entry.get().strip():
            self.task_entry.delete(0, "end")
            self.task_entry.insert(0, "添加新任务...")
            self.task_entry.config(fg=DIM)
        else:
            self.task_entry.config(fg=FG)

    def add_task(self):
        text = self.task_entry.get().strip()
        if text and text != "添加新任务...":
            self.tasks.append({"text": text, "done": False})
            self._save_today_tasks()
            self.refresh_tasks()
        self.task_entry.delete(0, "end")
        self.task_entry.insert(0, "添加新任务...")
        self.task_entry.config(fg=DIM)

    def toggle_task(self, idx):
        if 0 <= idx < len(self.tasks):
            self.tasks[idx]["done"] ^= True
            self._save_today_tasks()
            self.refresh_tasks()

    def delete_task(self, idx):
        if 0 <= idx < len(self.tasks):
            self.tasks.pop(idx)
            self._save_today_tasks()
            self.refresh_tasks()

    def refresh_tasks(self):
        for w in self._task_widgets:
            w.destroy()
        self._task_widgets.clear()

        container = self.task_scroll.inner
        for i, t in enumerate(self.tasks):
            row = tk.Frame(container, bg=BG)
            row.pack(fill="x", pady=1)

            # Checkbox icon
            icon = "☑" if t["done"] else "☐"
            cb = tk.Label(row, text=icon, font=("Segoe UI", 13),
                          bg=BG, fg=SUCCESS if t["done"] else SUBTLE,
                          cursor="hand2", width=2)
            cb.pack(side="left")
            cb.bind("<Button-1>", lambda e, idx=i: self.toggle_task(idx))

            # Text
            fg_c = DIM if t["done"] else FG
            lbl = tk.Label(row, text=t["text"],
                           font=("Segoe UI", 10,
                                 "overstrike" if t["done"] else "normal"),
                           bg=BG, fg=fg_c, anchor="w")
            lbl.pack(side="left", fill="x", expand=True, padx=(2, 0))
            lbl.bind("<Button-1>", lambda e, idx=i: self.toggle_task(idx))

            # Delete
            dl = tk.Label(row, text="✕", font=("Segoe UI", 10),
                          bg=BG, fg=DIM, cursor="hand2", padx=4)
            dl.pack(side="right")
            dl.bind("<Button-1>", lambda e, idx=i: self.delete_task(idx))
            self._hover_fg(dl, WARN, DIM)

            self._task_widgets.append(row)

        done = sum(1 for t in self.tasks if t["done"])
        total = len(self.tasks)
        self.task_count.config(text=f"{done}/{total}" if total else "0/0")

    # ── Settings ──────────────────────────────────────────

    def _close_settings(self):
        if self._settings_win and self._settings_win.winfo_exists():
            self._settings_win.destroy()
            self._settings_win = None

    def open_settings(self):
        if self._settings_win and self._settings_win.winfo_exists():
            self._settings_win.lift()
            return

        win = tk.Toplevel(self.root)
        win.title("设置")
        win.geometry("340x400")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()
        x = self.root.winfo_x() + (self.root.winfo_width() - 340) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 400) // 2
        win.geometry(f"+{x}+{y}")
        self._settings_win = win

        tk.Label(win, text="⏱ 番茄钟设置", font=("Segoe UI", 15, "bold"),
                 bg=BG, fg=FG).pack(pady=(16, 10))

        # Duration rows
        sf = tk.Frame(win, bg=BG)
        sf.pack(padx=30, fill="x")

        vars_ = {}
        for label, key, default, lo, hi in [
            ("🍅 工作时间", "work_min", 25, 1, 99),
            ("☕ 短休息",   "short_break_min", 5, 1, 30),
            ("🎉 长休息",   "long_break_min", 15, 1, 60),
        ]:
            row = tk.Frame(sf, bg=BG)
            row.pack(fill="x", pady=5)
            tk.Label(row, text=label, font=("Segoe UI", 10),
                     bg=BG, fg=FG).pack(side="left")
            var = tk.StringVar(value=str(self.config.get(key, default)))
            sp = tk.Spinbox(row, from_=lo, to=hi, textvariable=var,
                            width=5, font=("Segoe UI", 10),
                            bg=SURFACE, fg=FG, buttonbackground=BTN_BG,
                            bd=0, relief="flat", highlightthickness=1,
                            highlightbackground=SEPARATOR, highlightcolor=ACCENT)
            sp.pack(side="right")
            tk.Label(row, text="分钟", font=("Segoe UI", 9),
                     bg=BG, fg=DIM).pack(side="right", padx=(4, 6))
            vars_[key] = var

        tk.Frame(win, bg=SEPARATOR, height=1).pack(fill="x", padx=30, pady=(10, 8))

        of = tk.Frame(win, bg=BG)
        of.pack(padx=30, fill="x")

        auto_sv = tk.BooleanVar(value=self.config.get("auto_start", False))
        tk.Checkbutton(of, text="⏩ 自动进入下一阶段",
                       variable=auto_sv, onvalue=True, offvalue=False,
                       bg=BG, fg=FG, selectcolor=BG, activebackground=BG,
                       font=("Segoe UI", 10), cursor="hand2")\
            .pack(anchor="w", pady=2)

        sound_sv = tk.BooleanVar(value=self.config.get("sound_enabled", True))
        tk.Checkbutton(of, text="🔔 声音提示",
                       variable=sound_sv, onvalue=True, offvalue=False,
                       bg=BG, fg=FG, selectcolor=BG, activebackground=BG,
                       font=("Segoe UI", 10), cursor="hand2")\
            .pack(anchor="w", pady=2)

        def save():
            self.config["work_min"] = max(1, int(vars_["work_min"].get()))
            self.config["short_break_min"] = max(1, int(vars_["short_break_min"].get()))
            self.config["long_break_min"] = max(1, int(vars_["long_break_min"].get()))
            self.config["auto_start"] = auto_sv.get()
            self.config["sound_enabled"] = sound_sv.get()
            self.auto_var.set(self.config["auto_start"])
            self.sound_var.set(self.config["sound_enabled"])
            self.save_config()
            if self.state == "IDLE":
                self.total = self._phase_secs(self.phase)
                self.remaining = float(self.total)
                self.sync_ui()
            win.destroy()

        bf = tk.Frame(win, bg=BG)
        bf.pack(pady=(16, 0))
        tk.Button(bf, text="✓ 保存", font=("Segoe UI", 10, "bold"),
                  bg=ACCENT, fg=BG, bd=0, padx=24, pady=5,
                  cursor="hand2", command=save).pack(side="left", padx=4)
        tk.Button(bf, text="✕ 取消", font=("Segoe UI", 10),
                  bg=BTN_BG, fg=FG, bd=0, padx=24, pady=5,
                  cursor="hand2", command=win.destroy).pack(side="left", padx=4)

    # ── Toggles ───────────────────────────────────────────

    def _toggle_auto(self):
        self.config["auto_start"] = self.auto_var.get()
        self.save_config()

    def _toggle_sound(self):
        self.config["sound_enabled"] = self.sound_var.get()
        self.save_config()

    # ── Pin ───────────────────────────────────────────────

    def toggle_pin(self):
        on = not self.root.attributes("-topmost")
        self.root.attributes("-topmost", on)
        self.pin_btn.config(fg=ACCENT if on else DIM)

    # ── Notifications ─────────────────────────────────────

    def _notify(self):
        if self.config.get("sound_enabled", True):
            try:
                if self.phase == "WORK":
                    winsound.Beep(880, 150)
                    self.root.after(200, lambda: winsound.Beep(1100, 250))
                else:
                    winsound.Beep(660, 150)
                    self.root.after(200, lambda: winsound.Beep(880, 250))
            except Exception:
                self.root.bell()

        self._start_flash()
        self._show_notification()

    def _show_notification(self):
        notif = tk.Toplevel(self.root)
        notif.overrideredirect(True)
        notif.configure(bg=SURFACE)
        notif.transient(self.root)
        x = self.root.winfo_x() + (self.root.winfo_width() - 240) // 2
        y = self.root.winfo_y() + self.root.winfo_height() // 3
        notif.geometry(f"240x90+{x}+{y}")

        p = PHASES[self.phase]
        tk.Label(notif, text="⏰", font=("Segoe UI", 26),
                 bg=SURFACE, fg=FG).pack(pady=(10, 0))
        tk.Label(notif, text=f"{p['label']} 时间到！",
                 font=("Segoe UI", 12, "bold"), bg=SURFACE, fg=p["color"]).pack()
        notif.after(2500, notif.destroy)

    def _start_flash(self):
        self._flash_count = 0
        self._flash_step()

    def _flash_step(self):
        if self._flash_count >= 6:
            self._stop_flash()
            return
        if self._flash_count % 2 == 0:
            self.root.title(f"⏰ {PHASES[self.phase]['label']}时间到！")
        else:
            self.root.title("番茄钟")
        self._flash_count += 1
        self._flash_job = self.root.after(500, self._flash_step)

    def _stop_flash(self):
        if self._flash_job:
            self.root.after_cancel(self._flash_job)
            self._flash_job = None
        self.root.title("番茄钟")

    # ── Cleanup ───────────────────────────────────────────

    def _on_close(self):
        self._cancel_job()
        self._stop_flash()
        self.save_stats()
        self.save_config()
        self.root.destroy()


if __name__ == "__main__":
    PomodoroApp()
