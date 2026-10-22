# -*- coding: utf-8 -*-
"""
筛选面板 —— 优先级 + 标签筛选，并提供统计小面板。

勾选框使用现代圆角样式（app/ui/toggle.py），替代 Windows 传统方框。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional, Set

from ..config import PRIORITIES, PRIORITY_ORDER
from ..themes import get_theme
from .toggle import CheckCircle
from . import typography


class FilterPanel(tk.Frame):
    """优先级 + 标签 筛选。"""

    def __init__(self, master: tk.Misc, theme_name: str, tag_names: List[str],
                 on_change: Callable[[], None]):
        super().__init__(master, bg=get_theme(theme_name)["bg"])
        self.theme = get_theme(theme_name)
        self.on_change = on_change
        self.tag_names = tag_names

        self.priority_vars: Dict[str, tk.BooleanVar] = {}
        self.tag_vars: Dict[str, tk.BooleanVar] = {}
        self._priority_boxes: List[CheckCircle] = []
        self._tag_boxes: List[CheckCircle] = []
        self._tag_frame: Optional[tk.Frame] = None

        self._build()

    def _build(self) -> None:
        t = self.theme

        # 标题行：标题靠左，重置按钮靠右（省一行纵向空间）
        head = tk.Frame(self, bg=t["bg"])
        head.pack(fill="x", pady=(0, typography.ITEM_GAP))
        tk.Label(head, text="筛选", bg=t["bg"], fg=t["primary"],
                 font=typography.h2()).pack(side="left")
        from .rounded_button import RoundedButton
        RoundedButton(head, "重置", command=self.reset, variant="ghost",
                      theme=t, height=22, font_size=8, radius=5, padx=8).pack(side="right")

        # 优先级
        tk.Label(self, text="优先级", bg=t["bg"], fg=t["text_dim"],
                 font=typography.small('bold')).pack(anchor="w")
        prio_frame = tk.Frame(self, bg=t["bg"])
        prio_frame.pack(fill="x", pady=(2, 6))
        for key in PRIORITY_ORDER:
            name, sym = PRIORITIES[key]
            var = tk.BooleanVar(value=True)
            self.priority_vars[key] = var
            box = CheckCircle(prio_frame, text=f"{sym} {name}", variable=var,
                              theme=t, font_size=9, box_size=14, command=self.on_change)
            box.pack(side="left", padx=(0, 12))
            self._priority_boxes.append(box)

        # 标签
        tk.Label(self, text="标签", bg=t["bg"], fg=t["text_dim"],
                 font=typography.small('bold')).pack(anchor="w")
        self._tag_frame = tk.Frame(self, bg=t["bg"])
        self._tag_frame.pack(fill="x", pady=(2, 0))
        self.rebuild_tags(self.tag_names)

    def rebuild_tags(self, tag_names: List[str]) -> None:
        """标签集合变化时重建标签复选框。"""
        t = self.theme
        self.tag_names = list(tag_names)
        for child in self._tag_frame.winfo_children():
            child.destroy()
        self.tag_vars.clear()
        self._tag_boxes.clear()
        if not self.tag_names:
            tk.Label(self._tag_frame, text="（暂无标签）", bg=t["bg"], fg=t["text_dim"],
                     font=typography.caption()).pack(anchor="w")
            return
        for i, name in enumerate(self.tag_names):
            var = tk.BooleanVar(value=True)
            self.tag_vars[name] = var
            box = CheckCircle(self._tag_frame, text=name, variable=var,
                              theme=t, font_size=9, box_size=14, command=self.on_change)
            box.grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 10), pady=2)
            self._tag_boxes.append(box)

    def reset(self) -> None:
        for var in self.priority_vars.values():
            var.set(True)
        for var in self.tag_vars.values():
            var.set(True)
        for b in self._priority_boxes + self._tag_boxes:
            b._render()
        self.on_change()

    # ------------------------------------------------------------ 读取 ----
    def active_priorities(self) -> Set[str]:
        return {k for k, v in self.priority_vars.items() if v.get()}

    def active_tags(self) -> Set[str]:
        return {k for k, v in self.tag_vars.items() if v.get()}

    def is_active(self, priority: str, tag: str) -> bool:
        """
        判断某日程是否通过筛选。

        规则：
          - 优先级必须被勾选
          - 标签：带标签的日程按勾选的标签过滤；**没有标签的日程始终显示**
            （否则所有未打标签的日程会"神秘消失"，用户会以为没保存成功）
        """
        if priority not in self.active_priorities():
            return False
        if not tag:
            return True          # 无标签日程不参与标签过滤
        if not self.active_tags():
            return True          # 未勾选任何标签 = 不按标签过滤
        return tag in self.active_tags()


class StatsPanel(tk.Frame):
    """统计小面板：当月日程数量、完成待办数量。"""

    def __init__(self, master: tk.Misc, theme_name: str):
        super().__init__(master, bg=get_theme(theme_name)["bg"])
        self.theme = get_theme(theme_name)
        self._labels: Dict[str, tk.Label] = {}
        self._build()

    def _build(self) -> None:
        t = self.theme
        # 标题与数据同排（紧凑横条），节省侧边栏纵向空间
        head = tk.Frame(self, bg=t["bg"])
        head.pack(fill="x", pady=(0, typography.ITEM_GAP))
        tk.Label(head, text="统计", bg=t["bg"], fg=t["primary"],
                 font=typography.h2()).pack(side="left", padx=(0, 10))

        items = [("month_events", "本月"), ("week_events", "本周"),
                 ("todo_done", "已完成"), ("todo_undone", "未完成")]
        for key, label in items:
            cell = tk.Frame(head, bg=t["bg"])
            cell.pack(side="left", padx=(0, 10))
            val = tk.Label(cell, text="0", bg=t["bg"], fg=t["primary"],
                           font=typography.h3('bold'))
            val.pack(side="left", padx=(0, 3))
            tk.Label(cell, text=label, bg=t["bg"], fg=t["text_dim"],
                     font=typography.caption()).pack(side="left")
            self._labels[key] = val

    def update_stats(self, **kwargs) -> None:
        for key, val in kwargs.items():
            lbl = self._labels.get(key)
            if lbl is not None:
                lbl.configure(text=str(val))
