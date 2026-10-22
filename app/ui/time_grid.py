# -*- coding: utf-8 -*-
"""
周视图 / 日视图。

采用"时间轴 + 日程块"布局：
  - 左侧时间刻度列（00:00 - 24:00）
  - 右侧按天分列，每天一列
  - 日程块按时段绝对定位，可点击查看详情
  - 支持滚动条纵向滚动
日视图复用同一组件，列数为 1。
"""

from __future__ import annotations

import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import ttk
from typing import Callable, List, Optional

from ..config import PRIORITIES
from ..holidays import HolidayProvider
from ..recurrence import Occurrence
from ..themes import get_theme
from .layout import layout_columns as _layout_columns
from . import typography

HOUR_HEIGHT = 46      # 每小时像素高度
HEADER_HEIGHT = 40    # 表头高度
GUTTER_WIDTH = 56     # 时间刻度列宽


class TimeGridView(tk.Frame):
    """时间轴视图（周视图 days=7，日视图 days=1）。"""

    def __init__(self, master: tk.Misc, theme_name: str, days: int, holidays: HolidayProvider,
                 on_event_click: Callable[[Occurrence], None],
                 on_empty_click: Callable[[datetime], None]):
        super().__init__(master, bg=get_theme(theme_name)["bg"])
        self.theme = get_theme(theme_name)
        self.days = days
        self.holidays = holidays
        self.on_event_click = on_event_click
        self.on_empty_click = on_empty_click

        self.anchor: date = date.today()
        self._occurrences: List[Occurrence] = []
        self._canvas: Optional[tk.Canvas] = None
        self._blocks: List[int] = []
        self._build()

    # ------------------------------------------------------------ 构建 ----
    def _build(self) -> None:
        t = self.theme
        self.canvas = tk.Canvas(self, bg=t["canvas"], highlightthickness=0,
                                bd=0, cursor="arrow")
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self._canvas = self.canvas

        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", self._on_wheel)
        self.canvas.bind("<Button-5>", self._on_wheel)
        # 拖动滚动
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)

    def _on_canvas_configure(self, event) -> None:
        """
        Canvas 尺寸变化处理。

        注意：render() 会 delete 全部图元并重绘，这会改变 Canvas 的请求尺寸，
        从而再次触发 <Configure>。若不加判断就会形成无限循环（窗口持续抖动）。
        措施：
          1) 尺寸未变直接返回
          2) 统一走 schedule_render() 做防抖，合并连续事件
        """
        # 渲染期间忽略尺寸事件（render 会重建全部图元，必然触发 Configure）
        if getattr(self, "_rendering", False):
            return
        try:
            w, h = event.width, event.height
            if w <= 1 or h <= 1:
                return
            if (w, h) == getattr(self, "_last_canvas_size", None):
                return
            self._last_canvas_size = (w, h)
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
            if getattr(self, "_render_job", None):
                self.after_cancel(self._render_job)
            self._render_job = self.after(delay, self._do_render)
        except Exception:
            self._do_render()

    def _do_render(self) -> None:
        """尺寸稳定后重绘。"""
        self._render_job = None
        try:
            self.render()
        except Exception:
            pass

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

    def _on_press(self, event) -> None:
        self._drag_y = event.y
        self._drag_from = self.canvas.yview()[0]

    def _on_drag(self, event) -> None:
        if not hasattr(self, "_drag_y"):
            return
        diff = (event.y - self._drag_y)
        total = self.canvas.winfo_height() or 1
        span = max(1.0, (self.canvas.bbox("all")[3] if self.canvas.bbox("all") else total))
        self.canvas.yview_moveto(self._drag_from - diff / span)

    # ------------------------------------------------------------ 渲染 ----
    def set_anchor(self, d: date) -> None:
        self.anchor = d

    def set_occurrences(self, occs: List[Occurrence]) -> None:
        self._occurrences = occs

    def _day_list(self) -> List[date]:
        if self.days == 1:
            return [self.anchor]
        start = self.anchor - timedelta(days=self.anchor.weekday())
        return [start + timedelta(days=i) for i in range(self.days)]

    def render(self) -> None:
        self._rendering = True
        try:
            self._render_inner()
        finally:
            self._rendering = False

    def _render_inner(self) -> None:
        t = self.theme
        c = self.canvas
        c.delete("all")
        self._blocks = []

        days = self._day_list()
        width = max(c.winfo_width(), 600)
        day_width = (width - GUTTER_WIDTH) // max(1, len(days))
        total_height = HEADER_HEIGHT + 24 * HOUR_HEIGHT
        # 表头
        for i, day in enumerate(days):
            x0 = GUTTER_WIDTH + i * day_width
            is_today = day == date.today()
            is_holiday = self.holidays.is_holiday(day)
            bg = t["today"] if is_today else (t["holiday"] if is_holiday else t["canvas"])
            c.create_rectangle(x0, 0, x0 + day_width, HEADER_HEIGHT, fill=bg, outline=t["grid"])
            label = day.strftime("%m-%d")
            if is_today:
                label = "今天 " + label
            c.create_text(x0 + day_width / 2, 13, text=label, fill=t["primary"] if is_today else t["text"],
                          font=typography.small('bold'))
            # 第二行：节假日名 或 农历
            sub = self.holidays.label_of(day)
            if not sub:
                sub = self._lunar_label(day)
            if sub:
                is_hol = self.holidays.is_holiday(day)
                c.create_text(x0 + day_width / 2, 29, text=sub,
                              fill=t["holiday_text"] if is_hol else t["text_dim"],
                              font=typography.caption())
            else:
                c.create_text(x0 + day_width / 2, 29, text="周" + "一二三四五六日"[day.weekday()],
                              fill=t["text_dim"], font=typography.caption())

        # 时间刻度
        for hour in range(25):
            y = HEADER_HEIGHT + hour * HOUR_HEIGHT
            c.create_line(GUTTER_WIDTH, y, width, y, fill=t["grid"])
            if hour < 24:
                c.create_text(GUTTER_WIDTH - 6, y + 3, anchor="ne",
                              text=f"{hour:02d}:00", fill=t["text_dim"],
                              font=typography.caption())

        # 分隔线
        for i in range(len(days) + 1):
            x = GUTTER_WIDTH + i * day_width
            c.create_line(x, 0, x, total_height, fill=t["grid_strong"])

        # 今日红线
        now = datetime.now()
        if date.today() in days:
            idx = days.index(date.today())
            x = GUTTER_WIDTH + idx * day_width
            y = HEADER_HEIGHT + (now.hour * 60 + now.minute) / 60 * HOUR_HEIGHT
            c.create_line(x, y, x + day_width, y, fill=t["danger"], width=2)

        # 日程块
        by_day: dict[date, List[Occurrence]] = {}
        for occ in self._occurrences:
            by_day.setdefault(occ.start.date(), []).append(occ)

        for i, day in enumerate(days):
            x0 = GUTTER_WIDTH + i * day_width
            day_occs = by_day.get(day, [])
            for occ, col, total_cols in _layout_columns(day_occs):
                self._draw_block(c, occ, x0, day_width, col, total_cols)

        c.configure(scrollregion=(0, 0, width, total_height))
        # 首次渲染滚动到 08:00 附近
        if not self._blocks:
            try:
                self.canvas.yview_moveto(max(0.0, (HEADER_HEIGHT + 7 * HOUR_HEIGHT) / total_height))
            except Exception:
                pass

    def _draw_block(self, c: tk.Canvas, occ: Occurrence, x0: int, day_width: int,
                    col: int = 0, total_cols: int = 1) -> None:
        """
        绘制单个日程块。

        col / total_cols 用于处理时间重叠：同一冲突组的日程左右并排，
        每个日程占据 1/total_cols 的列宽，互不遮挡。
        """
        t = self.theme
        color = self._tag_color(occ)
        prio_sym = PRIORITIES.get(occ.priority, ("中", "**"))[1]

        start_min = occ.start.hour * 60 + occ.start.minute
        end_min = occ.end.hour * 60 + occ.end.minute
        if occ.end.date() > occ.start.date():
            end_min = 24 * 60
        if end_min <= start_min:
            end_min = start_min + 30

        y0 = HEADER_HEIGHT + start_min / 60 * HOUR_HEIGHT
        y1 = HEADER_HEIGHT + end_min / 60 * HOUR_HEIGHT
        height = max(18, y1 - y0)

        # 列宽分配：按总列数等分，重叠时并排显示
        total_cols = max(1, total_cols)
        slot_w = (day_width - 6) / total_cols
        w = max(28, slot_w - 3)
        x = x0 + 3 + col * slot_w

        # 每个日程块使用唯一 tag，便于单独绑定点击事件
        tag = f"occ_{id(occ)}_{occ.date_str}_{occ.start.hour}{occ.start.minute}"
        c.create_rectangle(x, y0, x + w, y0 + height, fill=color, outline="",
                           width=0, tags=(tag,))

        # 按块高决定显示几行，避免文字溢出块外
        max_chars = max(3, int((w - 10) / 8))

        def _fit(text: str) -> str:
            return text if len(text) <= max_chars else text[:max_chars - 1] + "…"

        if height >= 46:
            # 大块：标题 + 时间 + 备注，共三行
            c.create_text(x + 5, y0 + 9, text=_fit(f"{prio_sym} {occ.title}"), anchor="w",
                          fill="#FFFFFF", font=typography.caption(), tags=(tag,))
            c.create_text(x + 5, y0 + 24, anchor="w",
                          text=f"{occ.start.strftime('%H:%M')}-{occ.end.strftime('%H:%M')}",
                          fill="#E4EEFA", font=typography.caption(), tags=(tag,))
            if occ.note:
                c.create_text(x + 5, y0 + 37, anchor="w", text=_fit(occ.note),
                              fill="#D6E4F5", font=typography.caption(), tags=(tag,))
        elif height >= 24:
            # 中块：标题 + 时间两行
            c.create_text(x + 5, y0 + 9, text=_fit(f"{prio_sym} {occ.title}"), anchor="w",
                          fill="#FFFFFF", font=typography.caption(), tags=(tag,))
            c.create_text(x + 5, y0 + 24, anchor="w",
                          text=f"{occ.start.strftime('%H:%M')}-{occ.end.strftime('%H:%M')}",
                          fill="#E4EEFA", font=typography.caption(), tags=(tag,))
        else:
            # 小块：仅标题，单行居中
            c.create_text(x + 5, y0 + height / 2, text=_fit(f"{prio_sym} {occ.title}"),
                          anchor="w", fill="#FFFFFF", font=typography.caption(),
                          tags=(tag,))

        self._blocks.append(tag)

        # 点击绑定：使用 tag_bind（注意：必须是字符串 tag，不能传 item id）
        c.tag_bind(tag, "<Button-1>", lambda e, o=occ: self.on_event_click(o))

    def _lunar_label(self, day: date) -> str:
        """生成农历显示文本。"""
        from ..lunar import lunar_day_text
        try:
            return lunar_day_text(day)
        except Exception:
            return ""

    def _tag_color(self, occ: Occurrence) -> str:
        getter = getattr(self, "color_resolver", None)
        if callable(getter):
            return getter(occ.tag)
        return self.theme["tag_default"]
