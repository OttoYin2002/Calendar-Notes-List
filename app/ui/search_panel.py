# -*- coding: utf-8 -*-
"""
全局搜索面板：搜索日程标题、备注、待办内容。

结果列表双击可定位到对应日期。
弹窗居中显示，支持拖动与调整大小。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from datetime import date
from typing import Callable, List, Optional

from ..models import Event, Todo
from . import typography
from .dialog_base import ModalDialog

# 搜索结果类型
RESULT_EVENT = "event"
RESULT_TODO = "todo"

# 弹窗尺寸
DIALOG_WIDTH = 660
DIALOG_HEIGHT = 480


class SearchPanel(ModalDialog):
    """搜索对话框。"""

    def __init__(self, master: tk.Misc, theme_name: str,
                 events: List[Event], todos: List[Todo],
                 on_pick_event: Callable[[Event], None],
                 on_pick_todo: Callable[[Todo], None],
                 on_pick_date: Optional[Callable[[date], None]] = None):
        self.events = events
        self.todos = todos
        self.on_pick_event = on_pick_event
        self.on_pick_todo = on_pick_todo
        self.on_pick_date = on_pick_date

        super().__init__(master, theme_name, "搜索",
                         min_width=520, min_height=380,
                         resizable=True, draggable=True)

        self._build()
        self._finalize()
        self.win.after(120, lambda: self.entry.focus_set())

    # ------------------------------------------------------------ 构建 ----
    def _build(self) -> None:
        t = self.theme

        # ---- 标题栏（可拖动区域） ----
        head = tk.Frame(self.body, bg=t["bg"])
        head.pack(fill="x", pady=(0, 12))
        tk.Label(head, text="全局搜索", bg=t["bg"], fg=t["primary"],
                 font=typography.h1()).pack(side="left")
        tk.Label(head, text="日程标题 / 备注 / 待办内容", bg=t["bg"], fg=t["text_dim"],
                 font=typography.small()).pack(side="left", padx=(12, 0))

        # ---- 搜索输入行 ----
        search_row = tk.Frame(self.body, bg=t["bg"])
        search_row.pack(fill="x", pady=(0, 10))

        self.var_query = tk.StringVar()
        self.entry = ttk.Entry(search_row, textvariable=self.var_query,
                               font=typography.body())
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.entry.bind("<Return>", lambda e: self.do_search())

        ttk.Button(search_row, text="搜索", style="Primary.TButton",
                   command=self.do_search).pack(side="left", padx=(10, 0))

        # ---- 提示行 ----
        self.hint = tk.Label(self.body, text="输入关键词后回车",
                             bg=t["bg"], fg=t["text_dim"],
                             font=typography.small(), anchor="w")
        self.hint.pack(fill="x", pady=(0, 8))

        # ---- 结果列表 ----
        list_wrap = tk.Frame(self.body, bg=t["bg"])
        list_wrap.pack(fill="both", expand=True)
        list_wrap.rowconfigure(0, weight=1)
        list_wrap.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(list_wrap, columns=("type", "date", "title", "detail"),
                                  show="headings", height=15)
        self.tree.heading("type", text="类型")
        self.tree.heading("date", text="日期")
        self.tree.heading("title", text="标题")
        self.tree.heading("detail", text="详情")
        self.tree.column("type", width=64, anchor="center", stretch=False)
        self.tree.column("date", width=118, anchor="center", stretch=False)
        self.tree.column("title", width=200, stretch=True)
        self.tree.column("detail", width=190, stretch=True)
        self.tree.grid(row=0, column=0, sticky="nsew")

        scroll = ttk.Scrollbar(list_wrap, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)

        self.tree.bind("<Double-Button-1>", lambda e: self._on_pick())
        self.tree.bind("<Return>", lambda e: self._on_pick())

    # ------------------------------------------------------------ 搜索 ----
    def do_search(self) -> None:
        q = self.var_query.get().strip().lower()
        for item in self.tree.get_children():
            self.tree.delete(item)
        if not q:
            self.hint.configure(text="输入关键词后回车")
            return

        count = 0
        # 日程
        for ev in self.events:
            hay = f"{ev.title}\n{ev.note}".lower()
            if q in hay:
                when = ev.start.strftime("%Y-%m-%d %H:%M")
                detail = (ev.note or "").replace("\n", " ")[:60]
                self.tree.insert("", "end", values=("日程", when, ev.title, detail),
                                 tags=(RESULT_EVENT, ev.id))
                count += 1
        # 待办
        for td in self.todos:
            if q in td.text.lower():
                when = td.created_at[:10]
                state = "已完成" if td.done else "未完成"
                self.tree.insert("", "end", values=("待办", when, td.text, state),
                                 tags=(RESULT_TODO, td.id))
                count += 1

        self.hint.configure(text=f"找到 {count} 条结果 · 双击可定位到对应日程")

    # ------------------------------------------------------------ 选择 ----
    def _on_pick(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        item = self.tree.item(sel[0])
        tags = item.get("tags") or ()
        if len(tags) >= 2:
            kind, obj_id = tags[0], tags[1]
            if kind == RESULT_EVENT:
                for ev in self.events:
                    if ev.id == obj_id:
                        if self.on_pick_date:
                            self.on_pick_date(ev.start.date())
                        self.on_pick_event(ev)
                        break
            elif kind == RESULT_TODO:
                for td in self.todos:
                    if td.id == obj_id:
                        self.on_pick_todo(td)
                        break
        self.close()
