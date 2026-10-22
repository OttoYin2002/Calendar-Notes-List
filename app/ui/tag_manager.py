# -*- coding: utf-8 -*-
"""
标签管理对话框：新增 / 重命名 / 删除标签，并自定义颜色。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, messagebox, ttk
from typing import Callable, List, Optional

from ..models import Tag
from ..themes import get_theme
from .dialog_base import ModalDialog
from . import typography

# 预置可选色板
PALETTE = [
    "#00489D", "#1F6FB2", "#2E7D32", "#7CB342", "#B8860B", "#C62828",
    "#AD1457", "#6A1B9A", "#00838F", "#455A64", "#5D4037", "#37474F",
]


class TagManagerDialog(ModalDialog):
    """标签管理窗口。"""

    def __init__(self, master: tk.Misc, theme_name: str, tag_names: List[str],
                 on_save: Optional[Callable[[List[str]], None]] = None):
        self.on_save = on_save
        # 本地副本：name -> color
        self.tags: dict[str, str] = {n: "#00489D" for n in tag_names}
        self.selected: Optional[str] = None

        super().__init__(master, theme_name, title="标签管理",
                         min_width=420, min_height=420)

        self._build()
        self._finalize()

    def _build(self) -> None:
        t = self.theme
        wrap = tk.Frame(self.body, bg=t["bg"])
        wrap.pack(fill="both", expand=True)

        tk.Label(wrap, text="标签管理", bg=t["bg"], fg=t["primary"],
                 font=typography.h1('bold')).pack(anchor="w")

        list_frame = tk.Frame(wrap, bg=t["bg"])
        list_frame.pack(fill="both", expand=True, pady=(10, 8))

        self.listbox = tk.Listbox(list_frame, width=24, height=8, bg=t["entry_bg"],
                                  fg=t["entry_text"], relief="flat", highlightthickness=1,
                                  highlightbackground=t["border"], selectbackground=t["primary"],
                                  selectforeground=t["on_primary"], font=typography.body(),
                                  activestyle="none")
        self.listbox.pack(side="left", fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        scroll.pack(side="left", fill="y")
        self.listbox.config(yscrollcommand=scroll.set)

        # 新增
        add_frame = tk.Frame(wrap, bg=t["bg"])
        add_frame.pack(fill="x", pady=(4, 0))
        self.var_new = tk.StringVar()
        entry = ttk.Entry(add_frame, textvariable=self.var_new, width=16)
        entry.pack(side="left")
        entry.bind("<Return>", lambda e: self._on_add())
        ttk.Button(add_frame, text="添加", command=self._on_add).pack(side="left", padx=6)
        ttk.Button(add_frame, text="删除", command=self._on_delete).pack(side="left")

        # 颜色
        color_frame = tk.Frame(wrap, bg=t["bg"])
        color_frame.pack(fill="x", pady=(10, 0))
        tk.Label(color_frame, text="颜色", bg=t["bg"], fg=t["text"],
                 font=typography.small('bold')).pack(side="left")
        self.swatch = tk.Label(color_frame, text="      ", bg=t["primary"], width=6,
                               relief="flat")
        self.swatch.pack(side="left", padx=(6, 10))
        ttk.Button(color_frame, text="选择颜色", command=self._on_pick_color).pack(side="left")
        ttk.Button(color_frame, text="预设色板", command=self._on_palette).pack(side="left", padx=6)

        # 按钮
        btn_frame = tk.Frame(wrap, bg=t["bg"])
        btn_frame.pack(fill="x", pady=(14, 0))
        ttk.Button(btn_frame, text="取消", command=self._close).pack(side="right")
        ttk.Button(btn_frame, text="保存", style="Primary.TButton",
                   command=self._on_save).pack(side="right", padx=(0, 8))

        self._refresh_list()

    def _refresh_list(self) -> None:
        self.listbox.delete(0, "end")
        for name in self.tags:
            self.listbox.insert("end", name)

    def _on_select(self, _evt=None) -> None:
        sel = self.listbox.curselection()
        if sel:
            self.selected = self.listbox.get(sel[0])
            self.swatch.configure(bg=self.tags.get(self.selected, "#00489D"))

    def _on_add(self) -> None:
        name = self.var_new.get().strip()
        if not name:
            return
        if name in self.tags:
            messagebox.showinfo("提示", "该标签已存在。", parent=self.win)
            return
        # 自动分配一个未使用的预设色
        used = set(self.tags.values())
        color = next((c for c in PALETTE if c not in used), PALETTE[0])
        self.tags[name] = color
        self.var_new.set("")
        self._refresh_list()
        # 选中新项
        names = list(self.tags)
        if names:
            self.listbox.selection_set(names.index(name))
            self.listbox.see(names.index(name))
            self._on_select()

    def _on_delete(self) -> None:
        sel = self.listbox.curselection()
        if not sel:
            return
        name = self.listbox.get(sel[0])
        if messagebox.askyesno("删除标签", f"确定删除标签「{name}」？\n已有日程的该标签会被清除。",
                               parent=self.win):
            self.tags.pop(name, None)
            self.selected = None
            self._refresh_list()

    def _on_pick_color(self) -> None:
        if not self.selected:
            messagebox.showinfo("提示", "请先在列表中选择一个标签。", parent=self.win)
            return
        color = colorchooser.askcolor(color=self.tags.get(self.selected), parent=self.win)
        if color and color[1]:
            self.tags[self.selected] = color[1]
            self.swatch.configure(bg=color[1])

    def _on_palette(self) -> None:
        if not self.selected:
            messagebox.showinfo("提示", "请先在列表中选择一个标签。", parent=self.win)
            return
        win = tk.Toplevel(self.win)
        win.title("选择预设颜色")
        win.configure(bg=self.theme["bg"])
        win.transient(self.win)
        frame = tk.Frame(win, bg=self.theme["bg"], padx=12, pady=12)
        frame.pack()
        for color in PALETTE:
            b = tk.Button(frame, bg=color, width=3, height=2, relief="flat", bd=0,
                          command=lambda c=color: (self.tags.__setitem__(self.selected, c),
                                                   self.swatch.configure(bg=c), win.destroy()))
            b.pack(side="left", padx=2, pady=2)

    def _on_save(self) -> None:
        if self.on_save:
            self.on_save(self.tags)
        self.close()

    def _close(self) -> None:
        """兼容旧调用。"""
        self.close()
