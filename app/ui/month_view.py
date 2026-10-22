# -*- coding: utf-8 -*-
"""
月视图。

7 列 x 6 行网格，每格显示：
  - 日期数字（今天高亮 / 周末与节假日标色）
  - 当天日程条目（色块按标签颜色区分，标题前带优先级符号）
  - 超出容量时显示 "+N 条"（点击展开当天列表）
"""

from __future__ import annotations

import calendar
import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import ttk
from typing import Callable, List, Optional

from ..config import PRIORITIES
from ..holidays import HolidayProvider
from ..recurrence import Occurrence
from ..themes import get_theme
from . import typography

WEEK_HEADERS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
MAX_VISIBLE = 3


class MonthView(tk.Frame):
    """月视图组件。"""

    def __init__(self, master: tk.Misc, theme_name: str, holidays: HolidayProvider,
                 on_day_click: Callable[[date], None],
                 on_event_click: Callable[[Occurrence], None],
                 on_more_click: Callable[[date], None],
                 on_prev_month: Optional[Callable[[], None]] = None,
                 on_next_month: Optional[Callable[[], None]] = None):
        super().__init__(master, bg=get_theme(theme_name)["bg"])
        self.theme = get_theme(theme_name)
        self.holidays = holidays
        self.on_day_click = on_day_click
        self.on_event_click = on_event_click
        self.on_more_click = on_more_click
        self.on_prev_month = on_prev_month or (lambda: None)
        self.on_next_month = on_next_month or (lambda: None)

        self.anchor: date = date.today()
        self._occurrences: List[Occurrence] = []
        # 刚新建的日程 id：置顶显示并加高亮边框，让用户立刻看到
        self.highlight_id: Optional[str] = None

        self._build()
        self.bind("<Configure>", lambda e: self._relayout())

    # ------------------------------------------------------------ 构建 ----
    def _build(self) -> None:
        t = self.theme
        # 星期表头
        self.header = tk.Frame(self, bg=t["bg_alt"], height=28)
        self.header.pack(fill="x")
        for i, name in enumerate(WEEK_HEADERS):
            lbl = tk.Label(self.header, text=name, bg=t["bg_alt"],
                           fg=t["text_dim"] if i >= 5 else t["text"],
                           font=typography.small('bold'))
            lbl.pack(side="left", fill="x", expand=True)
            self.header.pack_propagate(False)

        # 网格容器
        self.grid_frame = tk.Frame(self, bg=t["border"])
        self.grid_frame.pack(fill="both", expand=True)
        self.cells: List[tk.Frame] = []
        for _ in range(42):
            cell = tk.Frame(self.grid_frame, bg=t["bg"], highlightthickness=1,
                            highlightbackground=t["grid"])
            self.cells.append(cell)
            self._init_cell_chrome(cell)

        # 网格布局在这里一次性完成。
        # 关键：不能在 <Configure> 回调里重新 grid —— 那会改变布局从而再次触发
        # Configure 事件，形成无限循环，表现为窗口持续抖动。
        self._layout_grid()

        # 鼠标滚轮切换月份（UI 规范要求）
        self.grid_frame.bind("<MouseWheel>", self._on_wheel)
        self.grid_frame.bind("<Button-4>", self._on_wheel)
        self.grid_frame.bind("<Button-5>", self._on_wheel)
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Button-4>", self._on_wheel)
        self.bind("<Button-5>", self._on_wheel)

    def _layout_grid(self) -> None:
        """把 42 个格子按 7×6 放入网格，并设置等分权重（只调用一次）。"""
        for r in range(6):
            for c in range(7):
                self.cells[r * 7 + c].grid(row=r, column=c, sticky="nsew")
        for c in range(7):
            self.grid_frame.grid_columnconfigure(c, weight=1, uniform="col")
        for r in range(6):
            self.grid_frame.grid_rowconfigure(r, weight=1, uniform="row")

    def _on_wheel(self, event) -> None:
        """滚轮上/下翻切换月份。"""
        delta = 0
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        elif event.delta:
            delta = -1 if event.delta > 0 else 1
        if not delta:
            return
        # 防止滚轮事件继续冒泡到父容器
        try:
            return "break"
        except Exception:
            pass
        if delta < 0:
            self.on_prev_month()
        else:
            self.on_next_month()

    def _relayout(self, event=None) -> None:
        """
        窗口尺寸变化处理。

        注意：这里**绝不能重新 grid 单元格**（会改变布局 -> 再次触发 Configure ->
        无限循环 -> 窗口持续抖动）。布局在 _build 时已一次性完成。
        本方法只负责在尺寸真正变化时安排一次重绘（防抖）。
        """
        # 渲染期间忽略尺寸事件：render 会创建/销毁大量子控件，
        # 这些操作本身会触发 Configure，若不拦截会形成"渲染->配置->再渲染"循环。
        if getattr(self, "_rendering", False):
            return
        try:
            w = self.winfo_width()
            h = self.winfo_height()
            if w <= 1 or h <= 1:
                return
            if (w, h) == getattr(self, "_last_layout_size", None):
                return
            self._last_layout_size = (w, h)
            self.schedule_render()
        except Exception:
            pass

    def schedule_render(self, delay: int = 140) -> None:
        """
        安排一次重绘（防抖）。

        统一入口：无论是自身尺寸变化还是外部（主窗口 resize）请求，
        都走这里，保证同一时间窗口内只渲染一次。
        """
        try:
            if getattr(self, "_relayout_job", None):
                self.after_cancel(self._relayout_job)
            self._relayout_job = self.after(delay, self._do_relayout)
        except Exception:
            self._do_relayout()

    def _do_relayout(self) -> None:
        """尺寸稳定后重绘内容。"""
        self._relayout_job = None
        try:
            self.render()
        except Exception:
            pass

    # ------------------------------------------------------------ 渲染 ----
    def set_anchor(self, d: date) -> None:
        self.anchor = d

    def set_occurrences(self, occs: List[Occurrence]) -> None:
        self._occurrences = occs

    def render(self) -> None:
        """重绘整个月视图。"""
        self._rendering = True
        try:
            self._render_inner()
        finally:
            self._rendering = False

    def _render_inner(self) -> None:
        t = self.theme
        first = self.anchor.replace(day=1)
        start = first - timedelta(days=first.weekday())
        today = date.today()

        by_day: dict[date, List[Occurrence]] = {}
        for occ in self._occurrences:
            by_day.setdefault(occ.start.date(), []).append(occ)
        for day in by_day:
            by_day[day].sort(key=lambda o: o.start)

        for idx, cell in enumerate(self.cells):
            day = start + timedelta(days=idx)
            self._render_cell(cell, day, by_day.get(day, []), today)

    def _init_cell_chrome(self, cell: tk.Frame) -> None:
        """
        一次性创建格子的固定结构（日期数字行 + 日程块容器 + 溢出标签）。

        性能要点
        --------
        早前每次重绘都会 destroy 掉 42 个格子的全部子控件再重建，
        单次 render 约 365ms（其中 460ms/5次 全在 destroy 与 bind 上），
        拖动窗口时明显卡顿。

        现在改为：
          - 固定结构（日期行等）**只创建一次**，重绘时只更新属性
          - 日程块用**控件池**复用，避免反复 create/destroy
        """
        t = self.theme
        bg = t["bg"]

        # 日期数字行
        top = tk.Frame(cell, bg=bg)
        top.pack(fill="x", padx=4, pady=(2, 0))
        num_lbl = tk.Label(top, text="", bg=bg, fg=t["text"],
                           font=typography.font("H3", "normal"))
        num_lbl.pack(side="left")
        # 今天 / 节假日 / 农历 的标记（按需显示）
        badge_lbl = tk.Label(top, text="", bg=bg, fg=t["text_dim"],
                             font=typography.caption(), padx=3)
        badge_lbl.pack(side="left", padx=(4, 0))

        # 日程块容器（池化复用）
        chips_box = tk.Frame(cell, bg=bg)
        chips_box.pack(fill="both", expand=True)

        # "+N 条" 标签
        more_lbl = tk.Label(chips_box, text="", bg=bg, fg=t["primary"],
                            font=typography.caption('bold'), cursor="hand2")
        more_lbl.pack(anchor="w", padx=6)

        cell._chrome = {
            "top": top,
            "num": num_lbl,
            "badge": badge_lbl,
            "chips_box": chips_box,
            "more": more_lbl,
            "pool": [],          # 日程块控件池
        }
        # 日程块容器的父级需要接收"点击空白新建"与滚轮事件。
        # 由于日程块是 chips_box 的子控件，点击会冒泡到 cell，
        # 这里统一在 cell 上绑定一次即可，无需给每个子控件重复绑定。
        cell._day_ref = None   # 渲染时填入具体日期
        cell.bind("<Button-1>", self._on_cell_click)
        cell.bind("<Double-Button-1>", self._on_cell_click)
        cell.bind("<MouseWheel>", self._on_wheel)
        cell.bind("<Button-4>", self._on_wheel)
        cell.bind("<Button-5>", self._on_wheel)
        more_lbl.bind("<Button-1>", self._on_more_click)
        more_lbl.bind("<MouseWheel>", self._on_wheel)
        more_lbl.bind("<Button-4>", self._on_wheel)
        more_lbl.bind("<Button-5>", self._on_wheel)

    def _on_cell_click(self, event) -> None:
        """点击格子空白处 -> 新建该日日程。"""
        day = getattr(event.widget, "_day_ref", None)
        if day is not None:
            self.on_day_click(day)

    def _on_more_click(self, event) -> None:
        """点击"+N 条" -> 查看该日全部日程。"""
        widget = event.widget
        day = None
        # 从标签向上回溯所属格子
        w = widget
        while w is not None:
            if hasattr(w, "_day_ref") and getattr(w, "_day_ref", None) is not None:
                day = w._day_ref
                break
            w = getattr(w, "master", None)
        if day is not None:
            self.on_more_click(day)

    def _render_cell(self, cell: tk.Frame, day: date, occs: List[Occurrence], today: date) -> None:
        t = self.theme
        ch = cell._chrome
        cell._day_ref = day
        in_month = (day.month == self.anchor.month and day.year == self.anchor.year)
        is_today = (day == today)
        is_holiday = self.holidays.is_holiday(day)
        is_weekend = day.weekday() >= 5
        # 调休上班日：显示"班"字，优先于农历
        is_makeup_workday = (not is_holiday) and self.holidays.label_of(day) == "班"

        # 背景色
        if is_today:
            bg = t["today"]
        elif is_holiday:
            bg = t["holiday"]
        elif is_weekend:
            bg = t["weekend"]
        else:
            bg = t["bg"]
        cell.configure(bg=bg, highlightbackground=t["today_border"] if is_today else t["grid"],
                       highlightthickness=2 if is_today else 1)

        # ---- 日期数字行（复用控件，只更新属性） ----
        top = ch["top"]
        top.configure(bg=bg)
        num_lbl = ch["num"]
        num_lbl.configure(text=str(day.day), bg=bg,
                          font=typography.font("H3", "bold" if (is_today or in_month) else "normal"))
        day_color = t["text"] if in_month else t["text_dim"]
        if is_holiday:
            day_color = t["holiday_text"]
        elif is_today:
            day_color = t["primary"]
        num_lbl.configure(fg=day_color)

        badge = ch["badge"]
        hol_label = self.holidays.label_of(day)
        if is_makeup_workday:
            badge.configure(text="班", bg=bg, fg=t["warn"],
                            font=typography.caption())
        elif hol_label:
            badge.configure(text=hol_label, bg=bg,
                            fg=t["holiday_text"] if is_holiday else t["text_dim"],
                            font=typography.caption())
        else:
            lunar_text = self._lunar_label(day)
            badge.configure(
                text=lunar_text or "",
                bg=bg,
                fg=(t["weekend_text"] if not in_month else t["text_dim"]),
                font=typography.caption())

        # 今天的"今"标记用高亮底色
        if is_today:
            badge.configure(bg=t["primary"], fg="#FFFFFF",
                            font=typography.caption('bold'))

        # ---- 日程条目（池化复用） ----
        # 刚新建的日程优先显示（用户最关心"我刚加的那条"），
        # 否则它可能排在第 4 位之后被 "+N 条" 折叠，看起来像没添加成功。
        occs = sorted(occs, key=lambda o: (o.event.id != self.highlight_id, o.start))
        visible = occs[:MAX_VISIBLE]

        chips_box = ch["chips_box"]
        chips_box.configure(bg=bg)
        pool = ch["pool"]
        while len(pool) < len(visible):
            pool.append(self._make_chip(chips_box))
        for i, occ in enumerate(visible):
            self._update_chip(pool[i], occ, bg, is_new=(occ.event.id == self.highlight_id))
        for extra in pool[len(visible):]:
            extra.pack_forget()

        # "+N 条" 标签
        more = ch["more"]
        more.configure(bg=bg)
        if len(occs) > MAX_VISIBLE:
            more.configure(text=f"+{len(occs) - MAX_VISIBLE} 条")
            if not more.winfo_ismapped():
                more.pack(anchor="w", padx=6)
        else:
            if more.winfo_ismapped():
                more.pack_forget()

    def _make_chip(self, parent: tk.Frame) -> tk.Label:
        """
        创建一个日程块控件（加入池）。

        事件绑定只做一次；重绘时通过 _update_chip 更新内容并重新绑定点击回调。
        滚轮事件不单独绑定 —— 会冒泡到 cell / grid_frame 上的统一处理。
        """
        t = self.theme
        chip = tk.Label(parent, text="", bg=t["tag_default"], fg="#FFFFFF",
                        font=typography.caption(), anchor="w",
                        padx=4, pady=1, cursor="hand2", wraplength=0)
        chip.pack(fill="x", padx=3, pady=1)
        return chip

    def _update_chip(self, chip: tk.Label, occ: Occurrence, cell_bg: str,
                     is_new: bool = False) -> None:
        """更新池中已有的日程块（不创建新控件）。"""
        t = self.theme
        color = self._tag_color(occ)
        prio_name, prio_sym = PRIORITIES.get(occ.priority, ("中", "**"))
        time_text = occ.start.strftime("%H:%M")
        # 标题过长时先截断标题，保留时间与优先级前缀
        text = f"{prio_sym} {time_text} {occ.title}"

        # 按格子实际宽度截断，避免文字溢出到相邻格子。
        # 首次渲染时 winfo_width() 尚未生效（返回 1），此时退化为按父容器估算。
        cell_w = chip.master.winfo_width()
        if cell_w <= 1:
            parent_w = self.grid_frame.winfo_width()
            cell_w = parent_w // 7 if parent_w > 1 else 140
        avail = max(30, cell_w - 16)
        # 8px 约为一个 ASCII 字符宽度
        max_chars = max(6, avail // 8)
        if len(text) > max_chars:
            text = text[:max_chars - 1] + "…"

        chip.configure(text=text, bg=color, fg="#FFFFFF",
                       font=typography.caption())
        if is_new:
            # 刚新建的日程：加高亮边框，视觉上明确指示
            chip.configure(highlightthickness=2, highlightbackground=t["primary"],
                           highlightcolor=t["primary"])
        else:
            chip.configure(highlightthickness=0)
        if not chip.winfo_ismapped():
            chip.pack(fill="x", padx=3, pady=1)

        # 点击回调需要指向当前日程，重新绑定（同名 tag 会覆盖，不会累积）
        chip.bind("<Button-1>", lambda e, o=occ: self.on_event_click(o))
        chip.bind("<Double-Button-1>", lambda e, o=occ: self.on_event_click(o))
        # 悬停提示（备注）
        tip = getattr(chip, "_tip", None)
        if occ.note:
            if tip is None:
                tip = self._make_tooltip(chip, occ.title + "\n" + occ.note)
                chip._tip = tip
                chip.bind("<Enter>", lambda e, tp=tip: tp.show())
                chip.bind("<Leave>", lambda e, tp=tip: tp.hide())
            else:
                try:
                    tip.text = occ.title + "\n" + occ.note
                except Exception:
                    pass

    def _lunar_label(self, day: date) -> str:
        """
        生成农历显示文本。

        - 初一显示月份名（如"八月"、"闰腊月"）
        - 初十/二十显示"十"/"二十"简写
        - 其余显示"十五"等
        """
        from ..lunar import lunar_day_text
        try:
            return lunar_day_text(day)
        except Exception:
            return ""

    def _tag_color(self, occ: Occurrence) -> str:
        # 由主程序注入颜色解析（避免视图直接依赖 storage）
        getter = getattr(self, "color_resolver", None)
        if callable(getter):
            return getter(occ.tag)
        return self.theme["tag_default"]

    def _make_tooltip(self, widget, text: str):
        from .tooltip import Tooltip
        return Tooltip(widget, text, self.theme)
