# -*- coding: utf-8 -*-
"""
时间轴日程的列布局算法。

解决的问题
----------
同一时间段内的多个日程不能互相遮挡，应左右并排显示。

算法（经典 calendar column packing）
------------------------------------
1. 按开始时间排序；开始时间相同时，结束时间晚的排前面
2. 维护"已占用的列"列表，每个元素是该列最后一个日程的结束时间
3. 对每个日程：
   - 找到第一个"结束时间 <= 当前日程开始时间"的空闲列 -> 放入该列
   - 若没有空闲列 -> 新开一列
4. 同一"冲突组"（互相重叠的日程集合）共享同一个总列数，
   这样只有 2 个日程重叠时不会把整列都占满
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Sequence, Tuple

from ..recurrence import Occurrence


def _minutes(occ: Occurrence) -> Tuple[int, int]:
    """返回 (开始分钟数, 结束分钟数)，均以当天 00:00 为基准。"""
    start = occ.start.hour * 60 + occ.start.minute
    end = occ.end.hour * 60 + occ.end.minute
    if occ.end.date() > occ.start.date():
        end = 24 * 60
    if end <= start:
        end = start + 30
    return start, end


def _overlaps(a: Occurrence, b: Occurrence) -> bool:
    """两个日程是否在时间上重叠（相接不算重叠）。"""
    a_start, a_end = _minutes(a)
    b_start, b_end = _minutes(b)
    return a_start < b_end and b_start < a_end


def layout_columns(occurrences: Sequence[Occurrence]
                   ) -> List[Tuple[Occurrence, int, int]]:
    """
    计算每个日程的列位置。

    返回 [(日程, 列索引, 该冲突组的总列数), ...]
    """
    items = list(occurrences)
    if not items:
        return []

    # 排序：开始时间早的在前；相同时结束时间晚的在前（更"重"的先占列）
    items.sort(key=lambda o: (_minutes(o)[0], -_minutes(o)[1], o.title or ""))

    # 分组：把互相"连锁重叠"的日程划为同一组
    # 判定方式：与组内【任意】日程重叠即归入该组（而非只看组的最大结束时间），
    # 这样 A(9-11) B(10-12) C(11-13) 会被正确识别为连锁冲突。
    groups: List[List[Occurrence]] = []
    for occ in items:
        placed = False
        for group in groups:
            if any(_overlaps(occ, other) for other in group):
                group.append(occ)
                placed = True
                break
        if not placed:
            groups.append([occ])

    result: List[Tuple[Occurrence, int, int]] = []
    for group in groups:
        # 组内按列分配
        col_ends: List[int] = []      # 每列最后一个日程的结束时间
        assignments: List[Tuple[Occurrence, int]] = []
        for occ in group:
            start, end = _minutes(occ)
            placed = False
            for ci, col_end in enumerate(col_ends):
                if col_end <= start:
                    col_ends[ci] = end
                    assignments.append((occ, ci))
                    placed = True
                    break
            if not placed:
                col_ends.append(end)
                assignments.append((occ, len(col_ends) - 1))
        total = len(col_ends)
        result.extend((occ, ci, total) for occ, ci in assignments)

    return result


def layout_columns_by_day(occurrences: Sequence[Occurrence]) -> dict:
    """
    按日期分组的列布局。

    返回 {date: [(日程, 列索引, 总列数), ...]}
    """
    by_day: dict = {}
    for occ in occurrences:
        by_day.setdefault(occ.start.date(), []).append(occ)
    return {day: layout_columns(items) for day, items in by_day.items()}
