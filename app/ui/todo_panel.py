# -*- coding: utf-8 -*-
"""
待办清单面板（侧边栏）。

功能：添加待办、勾选完成/取消、完成项灰色+删除线、筛选（全部/未完成/已完成）、删除。

改进点：
  - 勾选框使用现代圆角样式（app/ui/toggle.py）
  - 勾选框与文字点击均能切换，且状态与数据严格同步
  - 滚动条仅在内容超出可视区域时才显示
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional

from ..models import Todo
from ..themes import get_theme
from .toggle import CheckCircle
from . import typography

FILTERS = [("all", "全部"), ("undone", "未完成"), ("done", "已完成")]


class TodoPanel(tk.Frame):
    """待办面板。"""

    def __init__(self, master: tk.Misc, theme_name: str,
                 on_add: Callable[[str], None],
                 on_toggle: Callable[[Todo], None],
                 on_delete: Callable[[Todo], None]):
        super().__init__(master, bg=get_theme(theme_name)["bg"])
        self.theme = get_theme(theme_name)
        self.on_add = on_add
        self.on_toggle = on_toggle
        self.on_delete = on_delete

        self.todos: List[Todo] = []
        self.filter_key = "all"
        self._rows: List[tk.Frame] = []

        self._build()

    # ------------------------------------------------------------ 构建 ----
    def _build(self) -> None:
        t = self.theme
        from .rounded_button import RoundedButton

        # 添加框
        add_frame = tk.Frame(self, bg=t["bg"])
        add_frame.pack(fill="x", pady=(0, 6))
        self.var_new = tk.StringVar()
        self.entry = ttk.Entry(add_frame, textvariable=self.var_new, font=typography.small())
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", self._on_add_pressed)
        RoundedButton(add_frame, "添加", command=self._on_add_pressed, variant="primary",
                      theme=t, height=26, font_size=8, radius=6, padx=12).pack(side="left", padx=(4, 0))

        # 筛选行（胶囊式分段控件）
        filter_frame = tk.Frame(self, bg=t["bg"])
        filter_frame.pack(fill="x", pady=(0, 6))
        self._filter_buttons = {}
        for key, label in FILTERS:
            rb = tk.Label(filter_frame, text=label, bg=t["bg"], fg=t["text_dim"],
                          font=typography.caption(), padx=10, pady=4, cursor="hand2")
            rb.pack(side="left", padx=2)
            rb.bind("<Button-1>", lambda e, k=key: self.set_filter(k))
            self._filter_buttons[key] = rb

        # 列表区：Canvas + 内嵌 Frame
        # 说明：Canvas 默认请求高度很小，必须用 grid + rowconfigure(weight=1)
        # 让它真正占据父容器剩余空间，否则内部 Frame 内容会被压成 1 像素。
        list_wrap = tk.Frame(self, bg=t["bg"])
        list_wrap.pack(fill="both", expand=True)
        list_wrap.rowconfigure(0, weight=1)
        list_wrap.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(list_wrap, bg=t["bg"], highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(list_wrap, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._on_scroll_set)
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.list_frame = tk.Frame(self.canvas, bg=t["bg"])
        self._list_window = self.canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        self.list_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        # 鼠标滚轮滚动
        for w in (self.canvas, self.list_frame):
            w.bind("<MouseWheel>", self._on_wheel)
            w.bind("<Button-4>", self._on_wheel)
            w.bind("<Button-5>", self._on_wheel)
        # 滚动条默认隐藏，仅在需要时显示
        self._scrollbar_visible = False
        self.scrollbar.grid_remove()

        self.empty_label = tk.Label(self.list_frame, text="暂无待办事项", bg=t["bg"], fg=t["text_dim"],
                                    font=typography.small())

    # ------------------------------------------------------------ 滚动条 ----
    def _on_scroll_set(self, first, last):
        """
        滚动条同步回调。

        关键：仅当内容高度超出可视区域时才显示滚动条，
        否则一条待办时也会出现无意义的滚动条。
        """
        try:
            self.scrollbar.set(first, last)
            need = (first not in ("0.0", 0.0)) or (last not in ("1.0", 1.0))
            if need != self._scrollbar_visible:
                if need:
                    self.scrollbar.grid(row=0, column=1, sticky="ns")
                else:
                    self.scrollbar.grid_remove()
                self._scrollbar_visible = need
        except Exception:
            pass

    def _on_frame_configure(self, _evt=None) -> None:
        """
        内容高度变化时同步滚动区域。

        注意：**只在 scrollregion 真的变化时才写**。
        无条件 configure 会触发 canvas 的 Configure -> 又回到这里 -> 无限循环，
        这是 Tkinter resize 时的经典陷阱（表现为界面持续抖动）。
        """
        try:
            bbox = self.canvas.bbox("all")
            if not bbox:
                return
            region = f"{bbox[0]} {bbox[1]} {bbox[2]} {bbox[3]}"
            if region != getattr(self, "_applied_scrollregion", None):
                self.canvas.configure(scrollregion=region)
                self._applied_scrollregion = region
        except Exception:
            pass
        self._sync_scrollbar_visibility()

    def _sync_scrollbar_visibility(self) -> None:
        """内容未超出可视区域时隐藏滚动条。"""
        try:
            bbox = self.canvas.bbox("all")
            if not bbox:
                return
            content_h = bbox[3] - bbox[1]
            view_h = self.canvas.winfo_height()
            if view_h <= 1:
                return
            need = content_h > view_h + 2
            if need != self._scrollbar_visible:
                if need:
                    self.scrollbar.grid(row=0, column=1, sticky="ns")
                else:
                    self.scrollbar.grid_remove()
                self._scrollbar_visible = need
        except Exception:
            pass

    def _on_canvas_configure(self, event) -> None:
        """宽度变化时同步内嵌 Frame 宽度，避免横向滚动条。"""
        self.canvas.itemconfigure(self._list_window, width=event.width)
        self._sync_scrollbar_visibility()

    def _on_wheel(self, event) -> None:
        delta = 0
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        elif event.delta:
            delta = -1 if event.delta > 0 else 1
        if delta:
            self.canvas.yview_scroll(delta * 2, "units")

    # ------------------------------------------------------------ 数据 ----
    def set_todos(self, todos: List[Todo]) -> None:
        self.todos = todos
        self.render()

    def _filtered(self) -> List[Todo]:
        if self.filter_key == "undone":
            return [x for x in self.todos if not x.done]
        if self.filter_key == "done":
            return [x for x in self.todos if x.done]
        return list(self.todos)

    # ------------------------------------------------------------ 渲染 ----
    def render(self) -> None:
        for child in self.list_frame.winfo_children():
            child.destroy()
        self._rows = []

        items = self._filtered()
        if not items:
            self.empty_label = tk.Label(self.list_frame, text="暂无待办事项", bg=self.theme["bg"],
                                        fg=self.theme["text_dim"], font=typography.small())
            self.empty_label.pack(anchor="w", pady=6)
            self._sync_scrollbar_visibility()
            return

        for todo in items:
            self._render_row(todo)
        self._sync_scrollbar_visibility()

    def _render_row(self, todo: Todo) -> None:
        t = self.theme
        row = tk.Frame(self.list_frame, bg=t["bg"])
        row.pack(fill="x", pady=(1, typography.ITEM_GAP))
        self._rows.append(row)

        # 勾选框与文字分离：勾选框用圆角组件，点击文字也能切换
        var = tk.BooleanVar(value=todo.done)

        def toggle():
            # 切换数据状态并通知外部，由外部负责持久化与重绘
            self.on_toggle(todo)

        cb = CheckCircle(row, text=todo.text, variable=var, theme=t,
                        font_size=9, box_size=15, command=toggle)
        cb.pack(side="left", fill="x", expand=True)

        if todo.done:
            # CheckCircle 是 Canvas 组件，文字颜色用内部 _text_color 控制
            cb.set_text_color(t["text_dim"])
            try:
                cb.set_font(typography.overstrike(typography.small()))
            except Exception:
                pass
        else:
            cb.set_text_color(t["text"])

        if todo.tag:
            tag_lbl = tk.Label(row, text=todo.tag, bg=t["bg"], fg=t["text_dim"],
                               font=typography.caption())
            tag_lbl.pack(side="right", padx=(2, 4))

        del_btn = tk.Label(row, text="×", bg=t["bg"], fg=t["text_dim"],
                           font=typography.h1(), cursor="hand2", width=2)
        del_btn.pack(side="right")
        del_btn.bind("<Button-1>", lambda e, x=todo: self.on_delete(x))
        del_btn.bind("<Enter>", lambda e: del_btn.configure(fg=t["danger"]))
        del_btn.bind("<Leave>", lambda e: del_btn.configure(fg=t["text_dim"]))

    # ------------------------------------------------------------ 交互 ----
    def _on_add_pressed(self) -> None:
        text = self.var_new.get().strip()
        if not text:
            return
        self.var_new.set("")
        self.on_add(text)

    def set_filter(self, key: str) -> None:
        self.filter_key = key
        self._sync_filter_buttons()
        self.render()

    def _sync_filter_buttons(self) -> None:
        t = self.theme
        for k, btn in self._filter_buttons.items():
            active = (k == self.filter_key)
            btn.configure(bg=t["primary_light"] if active else t["bg"],
                          fg=t["primary"] if active else t["text_dim"])

    def set_theme(self, theme: dict) -> None:
        """主题切换时刷新配色。"""
        self.theme = theme
        self.configure(bg=theme.get("bg", "#FFFFFF"))
        self._sync_filter_buttons()
        self.render()
