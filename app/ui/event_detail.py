# -*- coding: utf-8 -*-
"""
日程详情弹窗。

展示标题、备注、时间、标签、优先级、重复规则、提醒设置；
提供"编辑"和"删除"按钮。

对重复日程，编辑/删除时询问用户是否同步应用到全部重复项。
"""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from typing import Callable, Optional

from ..config import PRIORITIES, REPEAT_RULES
from ..models import Event
from ..recurrence import Occurrence
from ..themes import get_theme
from .dialog_base import ModalDialog
from . import typography


class EventDetailDialog(ModalDialog):
    """日程详情窗口。"""

    def __init__(self, master: tk.Misc, theme_name: str, occurrence: Occurrence,
                 tag_color: str,
                 on_edit: Callable[[Occurrence, str], None],
                 on_delete: Callable[[Occurrence, str], None]):
        """
        :param occurrence: 具体的日程实例
        :param on_edit:    (实例, 作用域) 作用域为 "all" / "this"
        :param on_delete:  (实例, 作用域)
        """
        self.occ = occurrence
        self.tag_color = tag_color
        self.on_edit = on_edit
        self.on_delete = on_delete

        super().__init__(master, theme_name, title="日程详情",
                         min_width=460, min_height=380)

        self._build()
        self._finalize()

    # ------------------------------------------------------------ 构建 ----
    def _build(self) -> None:
        t = self.theme
        occ = self.occ
        wrap = tk.Frame(self.body, bg=t["bg"])
        wrap.pack(fill="both", expand=True)

        # 标签色条
        bar = tk.Frame(wrap, bg=self.tag_color, height=4)
        bar.pack(fill="x", pady=(0, 12))

        # 标题
        tk.Label(wrap, text=occ.title or "(无标题)", bg=t["bg"], fg=t["text"],
                 font=typography.h1(), wraplength=420,
                 justify="left").pack(fill="x", anchor="w")

        # 信息表格
        info = tk.Frame(wrap, bg=t["bg"])
        info.pack(fill="x", pady=(12, 0))
        self._row(info, "时间", self._time_text(), 0)
        self._row(info, "标签", occ.tag or "无", 1)
        prio_name, prio_sym = PRIORITIES.get(occ.priority, ("中", "●"))
        self._row(info, "优先级", f"{prio_sym} {prio_name}", 2)
        self._row(info, "重复", self._repeat_text(), 3)
        self._row(info, "提醒", self._reminder_text(), 4)

        # 备注
        note = (occ.note or "").strip()
        if note:
            tk.Frame(wrap, bg=t["border"], height=1).pack(fill="x", pady=typography.SECTION_GAP + 4)
            tk.Label(wrap, text="备注", bg=t["bg"], fg=t["text_dim"],
                     font=typography.small('bold')).pack(anchor="w")
            tk.Label(wrap, text=note, bg=t["bg"], fg=t["text"], wraplength=420,
                     justify="left", font=typography.body()).pack(anchor="w", pady=(4, 0))

        # 按钮
        btn_frame = tk.Frame(wrap, bg=t["bg"])
        btn_frame.pack(fill="x", pady=(20, 0))
        from .rounded_button import RoundedButton
        RoundedButton(btn_frame, "删除", command=self._on_delete_click, variant="danger",
                      theme=t, height=32, font_size=9, radius=8).pack(side="left")
        RoundedButton(btn_frame, "编辑", command=self._on_edit_click, variant="primary",
                      theme=t, height=32, font_size=9, radius=8, bold=True).pack(side="right")
        RoundedButton(btn_frame, "关闭", command=self.close, variant="secondary",
                      theme=t, height=32, font_size=9, radius=8).pack(side="right", padx=(0, 8))

    def _row(self, parent, key: str, value: str, row: int) -> None:
        t = self.theme
        tk.Label(parent, text=key, bg=t["bg"], fg=t["text_dim"], width=6, anchor="w",
                 font=typography.small()).grid(row=row, column=0, sticky="w", pady=typography.ITEM_GAP)
        tk.Label(parent, text=value, bg=t["bg"], fg=t["text"], anchor="w",
                 font=typography.small()).grid(row=row, column=1, sticky="w", pady=2)

    def _time_text(self) -> str:
        o = self.occ
        if o.start.date() == o.end.date():
            return f"{o.start.strftime('%Y-%m-%d (%a) %H:%M')} - {o.end.strftime('%H:%M')}"
        return f"{o.start.strftime('%Y-%m-%d %H:%M')} - {o.end.strftime('%Y-%m-%d %H:%M')}"

    def _repeat_text(self) -> str:
        ev = self.occ.event
        if ev.repeat == "none":
            return "不重复"
        label = REPEAT_RULES.get(ev.repeat, ("", ""))[0]
        if ev.repeat == "weekly":
            names = "".join("一二三四五六日"[i] for i in sorted(ev.repeat_weekdays))
            label += f"（周{names}）"
        if ev.repeat_until:
            label += f"，至 {ev.repeat_until}"
        return label

    def _reminder_text(self) -> str:
        rems = self.occ.reminders
        if not rems:
            return "不提醒"
        from ..config import REMINDER_PRESETS
        mapping = {m: lab for m, lab in REMINDER_PRESETS}
        return "、".join(mapping.get(m, f"提前{m}分钟") for m in sorted(rems))

    # ------------------------------------------------------------ 操作 ----
    def _ask_scope(self, action: str) -> Optional[str]:
        """
        重复日程的操作作用域询问。
        返回 "all"（全部重复项）/ "this"（仅此条）/ None（取消）。
        """
        if not self.occ.event.is_repeating:
            return "all"
        win = tk.Toplevel(self.win)
        win.title("重复日程")
        win.configure(bg=self.theme["bg"])
        win.resizable(False, False)
        win.transient(self.win)
        t = self.theme

        tk.Label(win, text="这是一条重复日程", bg=t["bg"], fg=t["text"],
                 font=typography.h2('bold')).pack(pady=(16, 6))
        tk.Label(win, text=f"要{action}全部重复项，还是仅此条？", bg=t["bg"], fg=t["text_dim"],
                 font=typography.small()).pack(pady=(0, 12))

        result = {"scope": None}

        def choose(scope: str):
            result["scope"] = scope
            try:
                win.grab_release()
            except Exception:
                pass
            win.destroy()

        btn = tk.Frame(win, bg=t["bg"])
        btn.pack(fill="x", padx=16, pady=(0, 16))
        ttk.Button(btn, text=f"{action}全部重复项", style="Primary.TButton",
                   command=lambda: choose("all")).pack(side="left", padx=(0, 8))
        ttk.Button(btn, text="仅此条", command=lambda: choose("this")).pack(side="left")
        ttk.Button(btn, text="取消", command=lambda: choose(None)).pack(side="right")

        win.bind("<Escape>", lambda e: choose(None))
        # 关键：先让布局完成并显示，再 grab —— 否则会 grab 到空窗口导致锁死
        win.update_idletasks()
        win.update()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        x = self.win.winfo_rootx() + (self.win.winfo_width() - w) // 2
        y = self.win.winfo_rooty() + (self.win.winfo_height() - h) // 2
        win.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")
        try:
            win.grab_set()
        except Exception:
            pass
        self.win.wait_window(win)
        return result["scope"]

    def _on_edit_click(self) -> None:
        scope = self._ask_scope("修改")
        if scope:
            self.on_edit(self.occ, scope)
            self.close()

    def _on_delete_click(self) -> None:
        scope = self._ask_scope("删除")
        if scope:
            self.on_delete(self.occ, scope)
            self.close()

    def _close(self) -> None:
        """兼容旧调用。"""
        self.close()

    def _close(self) -> None:
        try:
            self.win.destroy()
        except Exception:
            pass
