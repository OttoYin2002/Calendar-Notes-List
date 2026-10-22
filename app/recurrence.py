# -*- coding: utf-8 -*-
"""
重复日程展开引擎。

母日程（母版）在 events.json 中只存一条记录，重复实例在渲染时按需展开。
这样既保证"编辑母日程可同步修改全部重复项"，也避免数据膨胀。

支持的重复规则：
  none    —— 不重复
  daily   —— 每天
  weekly  —— 每周（可指定星期几，0=周一 ... 6=周日）
  monthly —— 每月（同一日号；目标月份无该日则跳过，如 31 号）
  yearly  —— 每年（同一月日）
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import List, Tuple

from .models import Event

DATE_FMT = "%Y-%m-%d"


class Occurrence:
    """一次具体的日程实例（母日程 + 该次的实际起止时间）。"""

    __slots__ = ("event", "start", "end", "date_str", "is_override", "deleted")

    def __init__(self, event: Event, start: datetime, end: datetime,
                 date_str: str, is_override: bool = False, deleted: bool = False):
        self.event = event
        self.start = start
        self.end = end
        self.date_str = date_str
        self.is_override = is_override
        self.deleted = deleted

    @property
    def title(self) -> str:
        """实例标题（单次例外会覆盖母日程标题）。"""
        ov = self.event.overrides.get(self.date_str)
        if ov and "title" in ov:
            return ov["title"]
        return self.event.title

    @property
    def note(self) -> str:
        ov = self.event.overrides.get(self.date_str)
        if ov and "note" in ov:
            return ov["note"]
        return self.event.note

    @property
    def tag(self) -> str:
        ov = self.event.overrides.get(self.date_str)
        if ov and "tag" in ov:
            return ov["tag"]
        return self.event.tag

    @property
    def priority(self) -> str:
        ov = self.event.overrides.get(self.date_str)
        if ov and "priority" in ov:
            return ov["priority"]
        return self.event.priority

    @property
    def reminders(self) -> List[int]:
        ov = self.event.overrides.get(self.date_str)
        if ov and "reminders" in ov:
            return list(ov["reminders"])
        return list(self.event.reminders)

    def __repr__(self) -> str:  # 调试用
        return f"<Occurrence {self.title} @ {self.start}>"


def _duration(event: Event) -> timedelta:
    """母日程的持续时长（跨天时保留）。"""
    return event.end - event.start


def _candidate_dates(event: Event, range_start: date, range_end: date) -> List[date]:
    """根据重复规则生成候选日期列表。"""
    base = event.start.date()
    until = None
    if event.repeat_until:
        try:
            until = datetime.strptime(event.repeat_until, DATE_FMT).date()
        except ValueError:
            until = None

    dates: List[date] = []

    if event.repeat == "none":
        dates = [base]

    elif event.repeat == "daily":
        cur = base
        while cur <= range_end:
            dates.append(cur)
            cur += timedelta(days=1)

    elif event.repeat == "weekly":
        weekdays = sorted(set(event.repeat_weekdays)) or [event.start.weekday()]
        # 从 base 所在周的周一开始扫描
        week_start = base - timedelta(days=base.weekday())
        cur_week = week_start
        while cur_week <= range_end:
            for wd in weekdays:
                cand = cur_week + timedelta(days=wd)
                if cand < base:
                    continue
                if cand <= range_end:
                    dates.append(cand)
            cur_week += timedelta(days=7)

    elif event.repeat == "monthly":
        year, month = base.year, base.month
        while True:
            if date(year, month, 1) > range_end:
                break
            days_in_month = calendar.monthrange(year, month)[1]
            if base.day <= days_in_month:
                cand = date(year, month, base.day)
                if cand >= base and cand <= range_end:
                    dates.append(cand)
            month += 1
            if month > 12:
                year += 1
                month = 1

    elif event.repeat == "yearly":
        year = base.year
        while True:
            try:
                cand = date(year, base.month, base.day)
            except ValueError:
                year += 1
                continue
            if cand > range_end:
                break
            if cand >= base:
                dates.append(cand)
            year += 1

    # 应用"重复截止日期"
    if until is not None:
        dates = [d for d in dates if d <= until]
    # 限制到查询区间
    return [d for d in dates if range_start <= d <= range_end]


def expand(event: Event, range_start: date, range_end: date) -> List[Occurrence]:
    """
    展开某个母日程在 [range_start, range_end] 区间内的所有实例。

    返回的 Occurrence 已剔除被单独删除的日期（exceptions）。
    """
    if range_end < range_start:
        return []

    result: List[Occurrence] = []
    dur = _duration(event)
    time_of_day = event.start.time()

    for day in _candidate_dates(event, range_start, range_end):
        ds = day.strftime(DATE_FMT)
        if ds in event.exceptions:
            continue  # 该次被单独删除

        ov = event.overrides.get(ds)
        if ov:
            # 单次例外：使用覆盖后的起止时间
            st = ov.get("start")
            en = ov.get("end")
            start_dt = datetime.strptime(st, "%Y-%m-%dT%H:%M:%S") if st else datetime.combine(day, time_of_day)
            end_dt = datetime.strptime(en, "%Y-%m-%dT%H:%M:%S") if en else start_dt + dur
            result.append(Occurrence(event, start_dt, end_dt, ds, is_override=True))
        else:
            start_dt = datetime.combine(day, time_of_day)
            result.append(Occurrence(event, start_dt, start_dt + dur, ds))

    return result


def expand_all(events: List[Event], range_start: date, range_end: date) -> List[Occurrence]:
    """批量展开，返回按开始时间排序的实例列表。"""
    occ: List[Occurrence] = []
    for ev in events:
        occ.extend(expand(ev, range_start, range_end))
    occ.sort(key=lambda o: (o.start, o.title))
    return occ


def occurrences_on(events: List[Event], day: date) -> List[Occurrence]:
    """取某一天的全部实例。"""
    return expand_all(events, day, day)
