# -*- coding: utf-8 -*-
"""
圆角按钮组件（基于 Canvas 自绘）。

Tkinter 原生 Button / ttk.Button 都是直角，视觉上比较生硬。
本模块用 Canvas 绘制真正的圆角矩形，并提供：
  - 多种视觉样式：primary（主色实心）/ secondary（描边）/ ghost（幽灵）/ danger（危险）
  - hover / pressed / disabled 状态反馈
  - 自动尺寸（按文字内容计算）
  - 随 DPI 缩放

用法：
    btn = RoundedButton(parent, "保存", command=on_save, variant="primary")
    btn.pack()
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from typing import Callable, Optional


class RoundedButton(tk.Canvas):
    """圆角按钮。"""

    def __init__(self, master, text: str, command: Optional[Callable[[], None]] = None,
                 variant: str = "secondary", theme: Optional[dict] = None,
                 width: Optional[int] = None, height: Optional[int] = None,
                 radius: int = 8, font_size: int = 9, bold: bool = False,
                 padx: int = 14, pady: int = 7, anchor: str = "center"):
        """
        :param variant: primary / secondary / ghost / danger / success
        :param width:   固定宽度（None 表示按内容自适应）
        :param height:  固定高度（None 表示按内容自适应）
        :param anchor:  center / w / e
        """
        self.theme = theme or {}
        self.command = command
        self.variant = variant
        self._text = text
        self._radius = radius
        self._font_size = font_size
        self._bold = bold
        self._padx = padx
        self._pady = pady
        self._hover = False
        self._pressed = False
        self._enabled = True
        self._fixed_width = width
        self._fixed_height = height
        self._anchor = anchor

        # 尺寸（设计稿像素，后续按 DPI 缩放）
        self._base_height = height or (font_size + pady * 2 + 10)

        super().__init__(master, height=self._base_height, width=width or 80,
                         highlightthickness=0, bd=0, bg=self.theme.get("bg", "#FFFFFF"),
                         cursor="hand2")

        self._setup_fonts()
        self._bind_events()
        self._render()

    # ------------------------------------------------------------ 初始化 ----
    def _setup_fonts(self) -> None:
        from ..dpi import font as dpi_font
        self._font = dpi_font(self._font_size, "bold" if self._bold else "normal")
        try:
            self._font_measure = tkfont.Font(font=self._font)
        except Exception:
            self._font_measure = None

    def _bind_events(self) -> None:
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Button-1>", self._on_click)

    # ------------------------------------------------------------ 颜色 ----
    def _colors(self) -> dict:
        """按状态返回 (填充色, 边框色, 文字色)。"""
        t = self.theme
        primary = t.get("primary", "#00489D")
        on_primary = t.get("on_primary", "#FFFFFF")
        danger = t.get("danger", "#C62828")
        success = t.get("success", "#2E7D32")
        border = t.get("border", "#D9E0E8")
        text = t.get("text", "#1A2333")
        text_dim = t.get("text_dim", "#6B7A8D")
        hover_bg = t.get("hover", "#EDF3FA")
        muted = t.get("muted", "#EDF1F6")

        if not self._enabled:
            return (muted, border, text_dim)

        if self.variant == "primary":
            base = t.get("primary_hover", "#003C86") if (self._hover or self._pressed) else primary
            return (base, base, on_primary)
        if self.variant == "danger":
            base = t.get("danger_hover", "#A81F1F") if (self._hover or self._pressed) else danger
            return (base, base, "#FFFFFF")
        if self.variant == "success":
            return (success, success, "#FFFFFF")
        if self.variant == "ghost":
            if self._hover or self._pressed:
                return (hover_bg, hover_bg, text)
            return (t.get("bg", "#FFFFFF"), t.get("bg", "#FFFFFF"), text_dim)
        # secondary：白底描边
        if self._pressed:
            return (muted, primary, primary)
        if self._hover:
            return (hover_bg, primary, primary)
        return (t.get("entry_bg", "#FFFFFF"), border, text)

    # ------------------------------------------------------------ 绘制 ----
    def _render(self) -> None:
        from ..dpi import scale_int
        self.delete("all")
        fill, outline, fg = self._colors()

        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1:
            w = self._fixed_width or self._natural_width()
        if h <= 1:
            h = self._fixed_height or self._base_height
        # 保证画布尺寸与绘制尺寸一致
        if self.winfo_width() != w or self.winfo_height() != h:
            try:
                self.configure(width=w, height=h)
            except Exception:
                pass

        r = min(scale_int(self._radius), w // 2, h // 2)
        # 圆角矩形：用多边形 + 圆角弧拼接
        self._draw_round_rect(2, 2, w - 3, h - 3, r, fill=fill,
                              outline=outline if self.variant == "secondary" else fill,
                              width=1)

        # 文字
        tx, ty = w // 2, h // 2
        anchor_opt = {"center": "center"}
        self.create_text(tx, ty, text=self._text, fill=fg, font=self._font,
                         anchor=anchor_opt.get(self._anchor, "center"))

    def _draw_round_rect(self, x1, y1, x2, y2, r, fill="", outline="", width=1):
        """绘制圆角矩形（4 段圆弧 + 4 段直线）。"""
        if r <= 0:
            self.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline, width=width)
            return
        points = [
            x1 + r, y1, x2 - r, y1,        # 上边
            x2, y1, x2, y1 + r,            # 右上角
            x2, y2 - r, x2, y2,            # 右边
            x2 - r, y2, x1 + r, y2,        # 下边
            x1, y2, x1, y2 - r,            # 左下角
            x1, y1 + r, x1, y1,            # 左边
        ]
        # 用平滑多边形实现圆角
        self.create_polygon(points, fill=fill, outline=outline, width=width, smooth=True)

    def _natural_width(self) -> int:
        """按文字内容计算自然宽度。"""
        from ..dpi import scale_int
        pad = scale_int(self._padx)
        if self._font_measure is not None:
            try:
                text_w = self._font_measure.measure(self._text)
            except Exception:
                text_w = len(self._text) * self._font_size * 8
        else:
            text_w = len(self._text) * self._font_size * 8
        return text_w + pad * 2

    # ------------------------------------------------------------ 事件 ----
    def _on_enter(self, _e=None) -> None:
        self._hover = True
        self._render()

    def _on_leave(self, _e=None) -> None:
        self._hover = False
        self._pressed = False
        self._render()

    def _on_press(self, _e=None) -> None:
        if self._enabled:
            self._pressed = True
            self._render()

    def _on_release(self, _e=None) -> None:
        self._pressed = False
        self._render()

    def _on_click(self, _e=None) -> None:
        if self._enabled and self.command:
            try:
                self.command()
            except Exception as exc:
                print(f"[button] 命令执行失败：{exc}")

    # ------------------------------------------------------------ API ----
    def set_text(self, text: str) -> None:
        self._text = text
        self._render()

    def set_command(self, command: Optional[Callable[[], None]]) -> None:
        self.command = command

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self._render()

    def set_theme(self, theme: dict) -> None:
        """主题切换时更新配色。"""
        self.theme = theme
        try:
            self.configure(bg=theme.get("bg", "#FFFFFF"))
        except Exception:
            pass
        self._render()
