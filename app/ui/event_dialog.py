# -*- coding: utf-8 -*-
"""
日程新增 / 编辑表单。

字段：标题、备注、开始日期、开始时间、结束日期、结束时间、是否提醒、
      提醒提前量（可多选）、重复规则、重复截止、标签、优先级。

校验：
  - 标题不能为空
  - 结束时间不能早于开始时间（跨天日程允许，结束日期需晚于开始日期）
  - 每周重复至少选择一个星期
"""

from __future__ import annotations

import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, ttk
from typing import Callable, List, Optional

from ..config import PRIORITIES, PRIORITY_ORDER, REMINDER_PRESETS, REPEAT_RULES
from ..models import Event
from ..themes import get_theme
from .dialog_base import ModalDialog
from . import typography

WEEKDAY_CN = ["一", "二", "三", "四", "五", "六", "日"]


class EventDialog(ModalDialog):
    """新建 / 编辑日程的模态表单。"""

    def __init__(self, master: tk.Misc, theme_name: str,
                 initial: Optional[Event] = None,
                 default_date: Optional[datetime] = None,
                 tag_names: Optional[List[str]] = None,
                 on_save: Optional[Callable[[Event], None]] = None,
                 on_tags_changed: Optional[Callable[[dict], None]] = None):
        """
        :param initial:     传入则进入编辑模式
        :param default_date: 新建时的默认日期
        :param on_save:    保存回调（接收 Event）
        """
        self.initial = initial
        self.on_save = on_save
        # 标签管理弹窗保存后的回调（把新增/改名/颜色写回主程序）
        self.on_tags_changed = on_tags_changed
        self._pending_tag_map = None
        self.tag_names = tag_names or []
        self.result: Optional[Event] = None

        # 先初始化变量（_build 依赖它们），再构建界面
        self._init_vars(initial, default_date)

        super().__init__(master, theme_name,
                         title="编辑日程" if initial else "新建日程",
                         min_width=520, min_height=560)

        self._build()
        # 关键：内容构建完成后再居中 + grab（否则会锁死成空窗口）
        self._finalize()

        # 首次聚焦标题
        self.win.after(120, lambda: self.title_entry.focus_set())

    # ------------------------------------------------------------ 变量 ----
    def _init_vars(self, initial: Optional[Event], default_date: Optional[datetime]) -> None:
        if initial:
            ev = initial
            self.var_title = tk.StringVar(value=ev.title)
            self.var_note = tk.StringVar(value=ev.note)
            self.var_start_date = tk.StringVar(value=ev.start.strftime("%Y-%m-%d"))
            self.var_start_time = tk.StringVar(value=ev.start.strftime("%H:%M"))
            self.var_end_date = tk.StringVar(value=ev.end.strftime("%Y-%m-%d"))
            self.var_end_time = tk.StringVar(value=ev.end.strftime("%H:%M"))
            self.var_repeat = tk.StringVar(value=REPEAT_RULES.get(ev.repeat, REPEAT_RULES["none"])[0])
            self.var_repeat_until = tk.StringVar(value=ev.repeat_until or "")
            # 标签：即使不在已知列表里也保留（快捷输入的新标签需要能显示出来）
            self.var_tag = tk.StringVar(value=ev.tag or "")
            self.var_priority = tk.StringVar(value=ev.priority)
            self.reminder_vars = {}
            for minutes, label in REMINDER_PRESETS:
                self.reminder_vars[minutes] = tk.BooleanVar(value=minutes in ev.reminders)
            self.weekday_vars = {i: tk.BooleanVar(value=i in ev.repeat_weekdays) for i in range(7)}
        else:
            base = default_date or datetime.now()
            start = base.replace(second=0, microsecond=0)
            end = start + timedelta(hours=1)
            self.var_title = tk.StringVar()
            self.var_note = tk.StringVar()
            self.var_start_date = tk.StringVar(value=start.strftime("%Y-%m-%d"))
            self.var_start_time = tk.StringVar(value=start.strftime("%H:%M"))
            self.var_end_date = tk.StringVar(value=end.strftime("%Y-%m-%d"))
            self.var_end_time = tk.StringVar(value=end.strftime("%H:%M"))
            self.var_repeat = tk.StringVar(value=REPEAT_RULES["none"][0])
            self.var_repeat_until = tk.StringVar()
            self.var_tag = tk.StringVar()
            self.var_priority = tk.StringVar(value="normal")
            self.reminder_vars = {m: tk.BooleanVar(value=(m == 0)) for m, _ in REMINDER_PRESETS}
            self.weekday_vars = {i: tk.BooleanVar(value=(i == start.weekday())) for i in range(7)}

    # ------------------------------------------------------------ 构建 ----
    def _build(self) -> None:
        t = self.theme
        wrap = tk.Frame(self.body, bg=t["bg"])
        wrap.pack(fill="both", expand=True)

        # 弹窗主标题（与其它弹窗保持一致的层级）
        tk.Label(wrap, text="编辑日程" if self.initial else "新建日程",
                 bg=t["bg"], fg=t["primary"],
                 font=typography.h1()).grid(row=0, column=0, columnspan=4,
                                            sticky="w", pady=(0, typography.SECTION_GAP))

        # 标题
        tk.Label(wrap, text="标题", bg=t["bg"], fg=t["text_dim"],
                 font=typography.small('bold')).grid(row=1, column=0, sticky="w", pady=(0, 8))
        self.title_entry = ttk.Entry(wrap, textvariable=self.var_title, width=44)
        self.title_entry.grid(row=1, column=1, columnspan=3, sticky="ew", pady=(0, 8))

        # 备注
        tk.Label(wrap, text="备注", bg=t["bg"], fg=t["text_dim"],
                 font=typography.small('bold')).grid(row=2, column=0, sticky="nw", pady=(0, 8))
        self.note_text = tk.Text(wrap, height=4, width=44, bg=t["entry_bg"], fg=t["entry_text"],
                                 relief="flat", wrap="word", font=typography.body(),
                                 insertbackground=t["text"], padx=6, pady=4,
                                 highlightthickness=1, highlightbackground=t["border"],
                                 highlightcolor=t["primary"])
        self.note_text.insert("1.0", self.var_note.get())
        self.note_text.grid(row=2, column=1, columnspan=3, sticky="ew", pady=(0, 8))

        # ---- 时间区 ----
        time_frame = typography.group_frame(wrap, t, "时间")
        time_frame.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(4, 10))
        ttk.Label(time_frame, text="开始").grid(row=0, column=0, sticky="w", padx=10, pady=6)
        ttk.Entry(time_frame, textvariable=self.var_start_date, width=13).grid(row=0, column=1, sticky="w")
        ttk.Entry(time_frame, textvariable=self.var_start_time, width=8).grid(row=0, column=2, sticky="w", padx=6)
        ttk.Label(time_frame, text="结束").grid(row=0, column=3, sticky="w", padx=(10, 0))
        ttk.Entry(time_frame, textvariable=self.var_end_date, width=13).grid(row=0, column=4, sticky="w")
        ttk.Entry(time_frame, textvariable=self.var_end_time, width=8).grid(row=0, column=5, sticky="w", padx=6)
        tk.Label(time_frame, text="格式：YYYY-MM-DD  HH:MM", bg=t["panel"], fg=t["text_dim"],
                 font=typography.caption()).grid(row=1, column=1, columnspan=5, sticky="w",
                                                      padx=10, pady=(0, 6))

        # ---- 重复区 ----
        rep_frame = typography.group_frame(wrap, t, "重复")
        rep_frame.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(0, 10))
        ttk.Label(rep_frame, text="规则").grid(row=0, column=0, sticky="w", padx=10, pady=6)
        self.repeat_combo = ttk.Combobox(rep_frame, textvariable=self.var_repeat, width=12,
                                         state="readonly", values=[v[0] for v in REPEAT_RULES.values()])
        self.repeat_combo.grid(row=0, column=1, sticky="w")
        self.repeat_combo.bind("<<ComboboxSelected>>", lambda e: self._sync_repeat_ui())
        ttk.Label(rep_frame, text="截止日期（可选）").grid(row=0, column=2, sticky="e", padx=(18, 6))
        ttk.Entry(rep_frame, textvariable=self.var_repeat_until, width=13).grid(row=0, column=3, sticky="w")

        # 每周星期几
        self.weekday_frame = tk.Frame(rep_frame, bg=t["panel"])
        self.weekday_frame.grid(row=1, column=0, columnspan=4, sticky="w", padx=10, pady=(4, 8))
        ttk.Label(self.weekday_frame, text="每周：").grid(row=0, column=0, sticky="w", padx=(0, 4))
        from .toggle import CheckCircle
        self._weekday_boxes = []
        for i, cn in enumerate(WEEKDAY_CN):
            box = CheckCircle(self.weekday_frame, text=cn, variable=self.weekday_vars[i],
                              theme=t, font_size=9, box_size=14)
            box.grid(row=0, column=i + 1, padx=2)
            self._weekday_boxes.append(box)
        self._sync_repeat_ui()

        # ---- 提醒区 ----
        rem_frame = typography.group_frame(wrap, t, "提醒")
        rem_frame.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(0, 10))
        for idx, (minutes, label) in enumerate(REMINDER_PRESETS):
            box = CheckCircle(rem_frame, text=label, variable=self.reminder_vars[minutes],
                              theme=t, font_size=9, box_size=15)
            box.grid(row=idx // 3, column=idx % 3, sticky="w", padx=12, pady=4)

        # ---- 分类区 ----
        cls_frame = typography.group_frame(wrap, t, "分类")
        cls_frame.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(0, 12))

        ttk.Label(cls_frame, text="标签").grid(row=0, column=0, sticky="w", padx=10, pady=6)
        # 下拉选项 = 已知标签 + 当前标签（快捷输入的新标签也能显示）
        tag_options = list(self.tag_names)
        cur_tag = self.var_tag.get()
        if cur_tag and cur_tag not in tag_options:
            tag_options.append(cur_tag)
        self.tag_combo = ttk.Combobox(cls_frame, textvariable=self.var_tag, width=14, state="readonly",
                                       values=[""] + tag_options)
        self.tag_combo.grid(row=0, column=1, sticky="w")
        from .rounded_button import RoundedButton
        RoundedButton(cls_frame, "管理标签", command=self._on_manage_tags, variant="secondary",
                      theme=t, height=26, font_size=8, radius=6, padx=10).grid(
            row=0, column=2, sticky="w", padx=8)

        # 优先级：每个选项独立一列，避免堆叠重叠
        ttk.Label(cls_frame, text="优先级").grid(row=1, column=0, sticky="w", padx=10, pady=6)
        from .toggle import RadioCircle
        for idx, key in enumerate(PRIORITY_ORDER):
            name, sym = PRIORITIES[key]
            box = RadioCircle(cls_frame, text=f"{sym} {name}", value=key,
                              variable=self.var_priority, theme=t, font_size=9, box_size=15)
            box.grid(row=1, column=1 + idx, sticky="w", padx=(0, 18))

        # ---- 按钮 ----
        btn_frame = tk.Frame(wrap, bg=t["bg"])
        btn_frame.grid(row=7, column=0, columnspan=4, sticky="e", pady=(4, 0))
        from .rounded_button import RoundedButton
        RoundedButton(btn_frame, "取消", command=self._on_cancel, variant="secondary",
                      theme=t, height=32, font_size=9, radius=8).pack(side="right")
        RoundedButton(btn_frame, "保存", command=self._on_save, variant="primary",
                      theme=t, height=32, font_size=9, radius=8, bold=True).pack(side="right", padx=(0, 8))

        wrap.columnconfigure(1, weight=1)
        wrap.columnconfigure(2, weight=1)
        wrap.columnconfigure(3, weight=1)

    def _sync_repeat_ui(self) -> None:
        """根据重复规则显示/隐藏"每周星期几"。"""
        if self.var_repeat.get() == REPEAT_RULES["weekly"][0]:
            self.weekday_frame.grid()
        else:
            self.weekday_frame.grid_remove()

    def _on_manage_tags(self) -> None:
        """打开标签管理弹窗。"""
        from .tag_manager import TagManagerDialog
        # 注意：TagManagerDialog 需要 theme_name（字符串），不是主题 dict
        TagManagerDialog(self.win, self.theme_name, self.tag_names, self._apply_tags)

    def _apply_tags(self, tag_map) -> None:
        """标签管理弹窗保存后的回调。

        tag_map 可以是 name->color 字典，也可以是名称列表（兼容旧协议）。
        """
        if isinstance(tag_map, dict):
            names = list(tag_map.keys())
            # 记录下来，保存日程时一并写回主程序
            self._pending_tag_map = dict(tag_map)
        else:
            names = list(tag_map or [])
        self.tag_names = names
        current = self.var_tag.get()
        self.tag_combo["values"] = [""] + names
        if current not in names:
            self.var_tag.set("")
        else:
            self.var_tag.set(current)

    # ------------------------------------------------------------ 校验保存 ----
    def _parse_dt(self, date_str: str, time_str: str) -> Optional[datetime]:
        try:
            d = datetime.strptime(date_str.strip(), "%Y-%m-%d")
            t = datetime.strptime(time_str.strip(), "%H:%M")
            return d.replace(hour=t.hour, minute=t.minute)
        except ValueError:
            return None

    def _on_save(self) -> None:
        t = self.theme
        title = self.var_title.get().strip()
        if not title:
            messagebox.showwarning("无法保存", "请填写日程标题。", parent=self.win)
            return

        start = self._parse_dt(self.var_start_date.get(), self.var_start_time.get())
        end = self._parse_dt(self.var_end_date.get(), self.var_end_time.get())
        if start is None or end is None:
            messagebox.showwarning("格式错误",
                                   "日期格式应为 YYYY-MM-DD，时间格式应为 HH:MM。",
                                   parent=self.win)
            return
        if end < start:
            messagebox.showwarning("时间冲突", "结束时间不能早于开始时间，请检查。", parent=self.win)
            return

        # 重复规则
        repeat_key = "none"
        for key, (label, _) in REPEAT_RULES.items():
            if label == self.var_repeat.get():
                repeat_key = key
                break

        weekdays = [i for i, v in self.weekday_vars.items() if v.get()]
        if repeat_key == "weekly" and not weekdays:
            messagebox.showwarning("缺少设置", "每周重复请至少选择一个星期。", parent=self.win)
            return

        repeat_until = self.var_repeat_until.get().strip()
        if repeat_until:
            try:
                datetime.strptime(repeat_until, "%Y-%m-%d")
            except ValueError:
                messagebox.showwarning("格式错误", "重复截止日期格式应为 YYYY-MM-DD。", parent=self.win)
                return

        reminders = sorted([m for m, v in self.reminder_vars.items() if v.get()])

        note = self.note_text.get("1.0", "end").strip()

        if self.initial:
            ev = self.initial.clone()
            ev.title = title
            ev.note = note
            ev.start = start
            ev.end = end
            ev.repeat = repeat_key
            ev.repeat_weekdays = weekdays
            ev.repeat_until = repeat_until or None
            ev.reminders = reminders
            ev.tag = self.var_tag.get()
            ev.priority = self.var_priority.get()
        else:
            ev = Event(
                title=title,
                note=note,
                start=start,
                end=end,
                repeat=repeat_key,
                repeat_weekdays=weekdays,
                repeat_until=repeat_until or None,
                reminders=reminders,
                tag=self.var_tag.get(),
                priority=self.var_priority.get(),
            )

        self.result = ev
        # 标签管理有改动时，先把标签配置写回主程序
        if self._pending_tag_map and self.on_tags_changed:
            try:
                self.on_tags_changed(self._pending_tag_map)
            except Exception:
                pass
        if self.on_save:
            self.on_save(ev)
        self.close()

    def _on_cancel(self) -> None:
        self.result = None
        self.close()

    def on_cancel(self) -> None:
        """ESC / 关闭按钮 —— 走基类协议。"""
        self._on_cancel()
