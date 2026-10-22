# -*- coding: utf-8 -*-
"""
轻量级悬浮提示（Tooltip）。
"""

from __future__ import annotations

import tkinter as tk
from typing import Optional
from . import typography


class Tooltip:
    """鼠标悬停时显示的小提示框。"""

    def __init__(self, widget: tk.Widget, text: str, theme: dict):
        self.widget = widget
        self.text = text
        self.theme = theme
        self.tip_window: Optional[tk.Toplevel] = None
        self._after_id: Optional[str] = None

    def show(self) -> None:
        if self.tip_window or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            self.tip_window = tk.Toplevel(self.widget)
            self.tip_window.wm_overrideredirect(True)
            self.tip_window.wm_geometry(f"+{x}+{y}")
            frame = tk.Frame(self.tip_window, bg=self.theme["border"])
            frame.pack()
            tk.Label(frame, text=self.text, bg=self.theme["bg"], fg=self.theme["text"],
                     justify="left", wraplength=320, padx=8, pady=5,
                     font=typography.small()).pack()
        except Exception:
            self.tip_window = None

    def hide(self) -> None:
        if self.tip_window:
            try:
                self.tip_window.destroy()
            except Exception:
                pass
            self.tip_window = None
