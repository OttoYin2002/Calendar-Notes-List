# -*- coding: utf-8 -*-
"""
提醒弹窗。

强制要求：
  - 始终强制置顶（不受主窗口"置顶开关"影响，也高于主窗口的置顶层级）
  - 包含日程标题 + 备注
  - 提供三个按钮：关闭 / 稍后提醒(10分钟) / 稍后提醒(30分钟)
  - 播放提示音（可在设置中关闭）
"""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk
from typing import Callable, List, Optional, Tuple

from ..config import PRIORITIES, SNOOZE_OPTIONS
from ..recurrence import Occurrence
from ..sound import play_sound as _play_sound_module
from ..themes import get_theme
from . import typography


def play_sound(enabled: bool = True, kind: str = "bell") -> None:
    """
    播放提示音。

    委托给 app.sound 模块（支持多种音效），失败则静默忽略。
    """
    if not enabled:
        return
    try:
        _play_sound_module(kind)
    except Exception:
        pass


class ReminderPopup:
    """单条提醒弹窗。"""

    def __init__(self, master: tk.Tk, occurrence: Occurrence, minutes_before: int,
                 theme_name: str, sound_enabled: bool,
                 on_snooze: Callable[[Occurrence, int, int], None],
                 on_close: Callable[[], None],
                 sound_kind: str = "bell"):
        self.master = master
        self.occ = occurrence
        self.minutes_before = minutes_before
        self.theme = get_theme(theme_name)
        self.on_snooze = on_snooze
        self.on_close = on_close
        self._closed = False

        self.win = tk.Toplevel(master)
        self.win.title("日程提醒")
        self.win.withdraw()
        self.win.configure(bg=self.theme["bg"])
        self.win.resizable(False, False)
        self.win.transient(master)
        # 关键：提醒弹窗始终强制置顶
        self.win.attributes("-topmost", True)

        self._build()
        self._center()
        self.win.deiconify()
        self.win.lift()
        self._force_topmost()
        # 定时重申置顶，防止被其它置顶窗口挤下去
        self._topmost_job = self.win.after(1500, self._force_topmost)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Escape>", lambda e: self.close())
        play_sound(sound_enabled, sound_kind)

    # ------------------------------------------------------------ 构建 ----
    def _build(self) -> None:
        t = self.theme
        wrap = tk.Frame(self.win, bg=t["bg"], padx=18, pady=16)
        wrap.pack(fill="both", expand=True)

        # 标题行
        head = tk.Frame(wrap, bg=t["bg"])
        head.pack(fill="x")
        tk.Label(head, text="⏰ 日程提醒", bg=t["bg"], fg=t["primary"],
                 font=typography.h1('bold')).pack(side="left")
        tk.Label(head, text=self._time_label(), bg=t["bg"], fg=t["text_dim"],
                 font=typography.small()).pack(side="right")

        # 分隔线
        tk.Frame(wrap, bg=t["border"], height=1).pack(fill="x", pady=(10, 12))

        # 日程标题
        title = self.occ.title or "(无标题日程)"
        tk.Label(wrap, text=title, bg=t["bg"], fg=t["text"], wraplength=420, justify="left",
                 font=typography.h1()).pack(fill="x", anchor="w")

        # 附加信息行：时间 / 标签 / 优先级
        info = self._info_line()
        if info:
            tk.Label(wrap, text=info, bg=t["bg"], fg=t["text_dim"],
                     font=typography.small()).pack(fill="x", anchor="w", pady=(4, 0))

        # 备注
        note = (self.occ.note or "").strip()
        if note:
            tk.Label(wrap, text="备注：", bg=t["bg"], fg=t["text_dim"],
                     font=typography.small('bold')).pack(fill="x", anchor="w", pady=(10, 2))
            note_box = tk.Text(wrap, height=min(6, max(2, len(note) // 28 + 1)), width=46,
                               bg=t["bg_alt"], fg=t["text"], relief="flat", wrap="word",
                               font=typography.body(), padx=8, pady=6,
                               highlightthickness=1, highlightbackground=t["border"])
            note_box.insert("1.0", note)
            note_box.configure(state="disabled")
            note_box.pack(fill="x")

        # 按钮区
        btns = tk.Frame(wrap, bg=t["bg"])
        btns.pack(fill="x", pady=(16, 0))

        from .rounded_button import RoundedButton
        for minutes in SNOOZE_OPTIONS:
            RoundedButton(btns, f"稍后提醒 {minutes} 分钟",
                          command=lambda m=minutes: self._do_snooze(m),
                          variant="secondary", theme=t, height=32, font_size=9, radius=8,
                          padx=14).pack(side="left", padx=(0, 8))

        RoundedButton(btns, "关闭", command=self.close, variant="primary", theme=t,
                      height=32, font_size=9, radius=8, bold=True).pack(side="right")
        self.win.bind("<Return>", lambda e: self.close())

    def _style_secondary(self, widget) -> None:
        widget.configure(padding=(10, 5))

    def _time_label(self) -> str:
        occ = self.occ
        if occ.start.date() == occ.end.date():
            span = f"{occ.start.strftime('%Y-%m-%d %H:%M')} - {occ.end.strftime('%H:%M')}"
        else:
            span = f"{occ.start.strftime('%Y-%m-%d %H:%M')} - {occ.end.strftime('%m-%d %H:%M')}"
        if self.minutes_before:
            span += f"（提前 {self.minutes_before} 分钟提醒）"
        return span

    def _info_line(self) -> str:
        occ = self.occ
        parts = []
        if occ.tag:
            parts.append(f"标签：{occ.tag}")
        pname, psym = PRIORITIES.get(occ.priority, ("中", "●"))
        parts.append(f"优先级：{psym} {pname}")
        if occ.event.is_repeating:
            parts.append("重复日程")
        return "    |    ".join(parts)

    # ------------------------------------------------------------ 定位 ----
    def _center(self) -> None:
        """居中显示。窗口已映射，尺寸可靠。"""
        self.win.update_idletasks()
        self.win.update()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        screen_w = self.win.winfo_screenwidth()
        screen_h = self.win.winfo_screenheight()
        try:
            mx = self.master.winfo_rootx()
            mw = self.master.winfo_width()
            mh = self.master.winfo_height()
            my = self.master.winfo_rooty()
            if mw > 10 and mh > 10 and mx >= 0:
                x = mx + (mw - w) // 2
                y = my + (mh - h) // 3
            else:
                x = (screen_w - w) // 2
                y = (screen_h - h) // 3
        except Exception:
            x = (screen_w - w) // 2
            y = (screen_h - h) // 3
        x = max(0, min(x, screen_w - w))
        y = max(0, min(y, screen_h - h))
        self.win.geometry(f"{w}x{h}+{x}+{y}")

    def _force_topmost(self) -> None:
        """强制置顶（同时用 Win32 API 提升层级）。"""
        if self._closed:
            return
        try:
            self.win.attributes("-topmost", True)
            self.win.lift()
            try:
                from ..topmost import set_topmost
                set_topmost(self.win, True)
            except Exception:
                pass
            self._topmost_job = self.win.after(1500, self._force_topmost)
        except Exception:
            pass
    # ------------------------------------------------------------ 行为 ----
    def _do_snooze(self, minutes: int) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.win.after_cancel(self._topmost_job)
        except Exception:
            pass
        try:
            self.on_snooze(self.occ, self.minutes_before, minutes)
        except Exception as exc:
            print(f"[reminder-popup] 稍后提醒处理失败：{exc}")
        self._destroy()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.win.after_cancel(self._topmost_job)
        except Exception:
            pass
        try:
            self.on_close()
        except Exception:
            pass
        self._destroy()

    def _destroy(self) -> None:
        try:
            self.win.destroy()
        except Exception:
            pass
