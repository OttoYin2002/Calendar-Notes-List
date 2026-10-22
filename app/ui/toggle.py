# -*- coding: utf-8 -*-
"""
现代圆角勾选框 / 单选框组件（Canvas 自绘）。

Tkinter 原生 Checkbutton 是 Windows 传统方形勾选框，视觉较旧。
本模块提供更简洁清新的样式：

  CheckCircle —— 圆角方形勾选框（圆角 + 勾号）
  RadioCircle —— 圆形单选框（外圈 + 内点）

特性：
  - 真正的圆角/圆形，跨 Windows 版本渲染一致
  - hover / pressed / disabled 状态反馈
  - 点击文字与点击框体都能切换
  - 支持随 DPI 缩放
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from typing import Callable, List, Optional, Tuple

# 勾号路径（相对框体的比例坐标）
_TICK_PATH = [
    (0.22, 0.52), (0.42, 0.72), (0.78, 0.28),
]


class _ToggleBase(tk.Canvas):
    """勾选框基类。"""

    def __init__(self, master, text: str = "", variable: Optional[tk.Variable] = None,
                 value: Optional[str] = None, command: Optional[Callable[[], None]] = None,
                 theme: Optional[dict] = None, font_size: int = 9,
                 box_size: int = 16, gap: int = 7, on_value=None,
                 bold: bool = False):
        self.theme = theme or {}
        self.command = command
        self._text = text
        self._value = value
        self._on_value = on_value
        self._hover = False
        self._pressed = False
        self._box_size = box_size
        self._gap = gap
        self._font_size = font_size
        self._bold = bold
        self._text_color: Optional[str] = None   # 覆盖文字颜色
        self.variable = variable

        super().__init__(master, highlightthickness=0, bd=0, bg=self.theme.get("bg", "#FFFFFF"),
                         cursor="hand2")
        self._setup_font()
        # 尺寸在这里一次性设定（创建后不再改动）——
        # 运行期若修改自身尺寸会触发 <Configure> 事件循环。
        try:
            self.configure(width=self._natural_width(), height=box_size + 6)
        except Exception:
            pass
        self._bind_events()
        self._render()

    def _setup_font(self) -> None:
        from ..dpi import font as dpi_font
        self._font = dpi_font(self._font_size, "bold" if self._bold else "normal")
        try:
            self._measure = tkfont.Font(font=self._font)
        except Exception:
            self._measure = None

    def _text_width(self) -> int:
        if not self._text:
            return 0
        if self._measure is not None:
            try:
                return self._measure.measure(self._text)
            except Exception:
                pass
        return len(self._text) * self._font_size * 8

    def _natural_width(self) -> int:
        return self._box_size + (self._gap + self._text_width() if self._text else 0)

    def _bind_events(self) -> None:
        self.bind("<Configure>", lambda e: self._render())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Button-1>", self._on_click)
        self._watch_variable()

    def _watch_variable(self) -> None:
        """
        监听 variable 变化并重绘。

        必要性：单选框组（RadioCircle）共享同一个 variable，
        点击"高"后只有被点击的那个会重绘，其他项要等鼠标移上去才更新样式
        （表现为"中"的按钮不会立刻变暗）。
        监听 variable 后，任一成员变化都会让全组同步刷新。
        """
        var = self.variable
        if var is None:
            return
        try:
            var.trace_add("write", lambda *args: self._safe_render())
        except Exception:
            pass

    def _safe_render(self) -> None:
        """重绘（吞掉控件已销毁时的异常）。"""
        try:
            if self.winfo_exists():
                self._render()
        except Exception:
            pass

    # ------------------------------------------------------------ 状态 ----
    def _colors(self) -> Tuple[str, str, str, str]:
        """返回 (填充色, 边框色, 勾选标记色, 文字色)。"""
        t = self.theme
        primary = t.get("primary", "#00489D")
        primary_light = t.get("primary_light", "#DCE9F8")
        border = t.get("border", "#D9E0E8")
        text = t.get("text", "#1A2333")
        text_dim = t.get("text_dim", "#6B7A8D")
        hover_bg = t.get("hover", "#EDF3FA")
        muted = t.get("muted", "#EDF1F6")

        if not self._is_enabled():
            return (muted, border, text_dim, text_dim)

        if self._is_checked():
            fill = primary
            if self._hover or self._pressed:
                fill = t.get("primary_hover", "#003C86")
            return (fill, fill, "#FFFFFF", text if not self._is_dim_text() else text_dim)
        # 未选中
        # 文字用弱化色（text_dim）：单选组里"未选中"的项应当明显淡于选中项，
        # 否则用户选了"高"之后，"中"看起来还是深色，要等鼠标移上去才变淡。
        if self._pressed:
            return (primary_light, primary, primary, text)
        if self._hover:
            return (hover_bg, primary, primary, text)
        return (t.get("entry_bg", "#FFFFFF"), border, primary, text_dim)

    def _is_enabled(self) -> bool:
        return True

    def _is_checked(self) -> bool:
        raise NotImplementedError

    def _is_dim_text(self) -> bool:
        return False

    # ------------------------------------------------------------ 绘制 ----
    def _render(self) -> None:
        """
        重绘勾选框。

        重要：本方法**绝不能调用 self.configure(width/height)** ——
        那会改变自身尺寸并触发新的 <Configure> 事件，
        而 <Configure> 又会调用本方法，形成无限循环（表现为界面持续抖动）。
        尺寸只在创建时设定一次，这里只读不写。
        """
        self.delete("all")
        fill, outline, mark, text_color = self._colors()
        bs = self._box_size
        w = self.winfo_width()
        if w <= 1:
            w = self._natural_width()
        h = self.winfo_height()
        if h <= 1:
            h = bs + 6

        cy = h // 2
        self._draw_box(2, cy - bs // 2, bs, fill, outline, mark)
        if self._text:
            tc = self._text_color or text_color
            self.create_text(bs + self._gap, cy, text=self._text, anchor="w",
                             fill=tc, font=self._font)

    def _draw_box(self, x, y, size, fill, outline, mark) -> None:
        raise NotImplementedError

    # ------------------------------------------------------------ 事件 ----
    def _on_enter(self, _e=None) -> None:
        self._hover = True
        self._render()

    def _on_leave(self, _e=None) -> None:
        self._hover = False
        self._pressed = False
        self._render()

    def _on_press(self, _e=None) -> None:
        self._pressed = True
        self._render()

    def _on_release(self, _e=None) -> None:
        self._pressed = False
        self._render()

    def _on_click(self, _e=None) -> None:
        self._toggle()
        if self.command:
            try:
                self.command()
            except Exception as exc:
                print(f"[toggle] 命令执行失败：{exc}")

    def _toggle(self) -> None:
        raise NotImplementedError

    # ------------------------------------------------------------ API ----
    def set_text(self, text: str) -> None:
        self._text = text
        self._render()

    def set_text_color(self, color: str) -> None:
        """设置文字颜色（Canvas 用 create_text 的 fill，不支持 fg）。"""
        self._text_color = color
        self._render()

    def set_font(self, font) -> None:
        """设置字体。"""
        try:
            self._font = font
            self._measure = tkfont.Font(font=font)
        except Exception:
            pass
        self._render()

    def set_theme(self, theme: dict) -> None:
        self.theme = theme
        try:
            self.configure(bg=theme.get("bg", "#FFFFFF"))
        except Exception:
            pass
        self._render()


class CheckCircle(_ToggleBase):
    """圆角方形勾选框。"""

    def _is_checked(self) -> bool:
        if self.variable is not None:
            return bool(self.variable.get())
        return bool(self._on_value)

    def _toggle(self) -> None:
        if self.variable is not None:
            self.variable.set(not self.variable.get())
        else:
            self._on_value = not self._on_value

    def _draw_box(self, x, y, size, fill, outline, mark) -> None:
        r = max(3, size // 4)
        # 圆角矩形
        points = [
            x + r, y, x + size - r, y,
            x + size, y, x + size, y + r,
            x + size, y + size - r, x + size, y + size,
            x + size - r, y + size, x + r, y + size,
            x, y + size, x, y + size - r,
            x, y + r, x, y,
        ]
        self.create_polygon(points, fill=fill, outline=outline, width=1, smooth=True)
        # 勾号
        if self._is_checked():
            coords = []
            for fx, fy in _TICK_PATH:
                coords.append(x + size * fx)
                coords.append(y + size * fy)
            self.create_line(coords, fill=mark, width=2, capstyle="round", joinstyle="round")


class RadioCircle(_ToggleBase):
    """圆形单选框。"""

    def _is_checked(self) -> bool:
        if self.variable is not None and self._value is not None:
            return self.variable.get() == self._value
        return bool(self._on_value)

    def _toggle(self) -> None:
        if self.variable is not None and self._value is not None:
            self.variable.set(self._value)
        else:
            self._on_value = True

    def _draw_box(self, x, y, size, fill, outline, mark) -> None:
        cx, cy = x + size / 2, y + size / 2
        r = size / 2 - 1
        self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=fill, outline=outline, width=1)
        if self._is_checked():
            ir = size * 0.24
            self.create_oval(cx - ir, cy - ir, cx + ir, cy + ir, fill=mark, outline=mark)


class CheckGroup(tk.Frame):
    """
    圆角勾选框组（多选）。

    用法：
        group = CheckGroup(parent, ["准时", "提前5分钟"], theme=t)
        group.set_checked({0})
        group.on_change = lambda indices: ...
    """

    def __init__(self, master, items: List[str], theme: Optional[dict] = None,
                 font_size: int = 9, columns: int = 3, on_change: Optional[Callable[[List[int]], None]] = None,
                 box_size: int = 15, bold: bool = False):
        super().__init__(master, bg=(theme or {}).get("bg", "#FFFFFF"))
        self.theme = theme or {}
        self.items = items
        self.on_change = on_change
        self._vars: List[tk.BooleanVar] = []
        self._boxes: List[CheckCircle] = []

        for i, label in enumerate(items):
            var = tk.BooleanVar(value=False)
            self._vars.append(var)
            box = CheckCircle(self, text=label, variable=var, theme=self.theme,
                              font_size=font_size, box_size=box_size, bold=bold,
                              command=self._emit)
            box.grid(row=i // columns, column=i % columns, sticky="w", padx=(0, 14), pady=3)
            self._boxes.append(box)

    def _emit(self) -> None:
        if self.on_change:
            try:
                self.on_change(self.checked_indices())
            except Exception:
                pass

    def checked_indices(self) -> List[int]:
        return [i for i, v in enumerate(self._vars) if v.get()]

    def set_checked(self, indices) -> None:
        for i, v in enumerate(self._vars):
            v.set(i in set(indices))
        for b in self._boxes:
            b._render()

    def set_theme(self, theme: dict) -> None:
        self.theme = theme
        self.configure(bg=theme.get("bg", "#FFFFFF"))
        for b in self._boxes:
            b.set_theme(theme)
