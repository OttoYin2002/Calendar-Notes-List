# -*- coding: utf-8 -*-
"""
重叠日程并排布局算法测试。

运行：python test_layout.py
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {extra}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def make_occ(title: str, h1: int, m1: int, h2: int, m2: int, day: date = date(2026, 10, 21)):
    """构造一个日程实例（用真实 Event + Occurrence）。"""
    from app.models import Event
    from app.recurrence import Occurrence
    ev = Event(title=title,
               start=datetime(day.year, day.month, day.day, h1, m1),
               end=datetime(day.year, day.month, day.day, h2, m2))
    return Occurrence(ev, ev.start, ev.end, day.strftime("%Y-%m-%d"))


def test_no_overlap() -> None:
    from app.ui.layout import layout_columns

    section("无重叠 —— 各自占满整列")
    occs = [make_occ("A", 9, 0, 10, 0), make_occ("B", 11, 0, 12, 0)]
    result = layout_columns(occs)
    check("两个不重叠日程各占 1 列", all(c == 0 and tot == 1 for _, c, tot in result),
          str(result))


def test_two_overlap() -> None:
    from app.ui.layout import layout_columns

    section("两个重叠 —— 左右并排")
    occs = [make_occ("A", 10, 0, 11, 0), make_occ("B", 10, 0, 11, 0)]
    result = layout_columns(occs)
    cols = sorted(c for _, c, _ in result)
    check("两个重叠日程分到不同列", cols == [0, 1], str(result))
    check("总列数为 2", all(tot == 2 for _, _, tot in result), str(result))
    # 验证 x 坐标不重叠
    xs = []
    for occ, col, tot in result:
        xs.append(col)
    check("列索引不重复", len(set(xs)) == len(xs), str(xs))


def test_three_overlap() -> None:
    from app.ui.layout import layout_columns

    section("三个完全重叠 —— 三列并排")
    occs = [make_occ("A", 10, 0, 11, 0), make_occ("B", 10, 0, 11, 0), make_occ("C", 10, 0, 11, 0)]
    result = layout_columns(occs)
    cols = sorted(c for _, c, _ in result)
    check("三个日程分到 3 列", cols == [0, 1, 2], str(result))
    check("总列数为 3", all(tot == 3 for _, _, tot in result), str(result))


def test_partial_overlap() -> None:
    from app.ui.layout import layout_columns

    section("部分重叠 —— A与B重叠，C与B重叠但与A不重叠")
    # A: 9-11, B: 10-12, C: 11-13
    # A 与 C 首尾相接（11:00），不算重叠 -> C 可复用 A 的列
    # 这与 Google Calendar 等主流日历的列分配行为一致
    occs = [make_occ("A", 9, 0, 11, 0), make_occ("B", 10, 0, 12, 0), make_occ("C", 11, 0, 13, 0)]
    result = layout_columns(occs)
    by_title = {o.title: (c, tot) for o, c, tot in result}
    check("冲突组总列数为 2", all(tot == 2 for _, _, tot in result), str(result))
    check("A 与 B 分到不同列", by_title["A"][0] != by_title["B"][0], str(by_title))
    check("C 与 A 同列（首尾相接不冲突）", by_title["C"][0] == by_title["A"][0], str(by_title))
    check("C 与 B 不同列", by_title["C"][0] != by_title["B"][0], str(by_title))


def test_chain_overlap() -> None:
    from app.ui.layout import layout_columns

    section("真正的连锁重叠（三者互相重叠）")
    # A: 9-12, B: 10-13, C: 11-14 —— 两两都重叠
    occs = [make_occ("A", 9, 0, 12, 0), make_occ("B", 10, 0, 13, 0), make_occ("C", 11, 0, 14, 0)]
    result = layout_columns(occs)
    cols = sorted(c for _, c, _ in result)
    check("三个日程分到 3 个不同列", cols == [0, 1, 2], str(result))
    check("总列数为 3", all(tot == 3 for _, _, tot in result), str(result))


def test_group_isolation() -> None:
    from app.ui.layout import layout_columns

    section("不同冲突组独立计算列数")
    # 组1: A/B 重叠 (9-11)，组2: C/D 重叠 (14-16)
    occs = [make_occ("A", 9, 0, 11, 0), make_occ("B", 9, 0, 11, 0),
            make_occ("C", 14, 0, 16, 0), make_occ("D", 14, 0, 16, 0)]
    result = layout_columns(occs)
    by_title = {o.title: (c, tot) for o, c, tot in result}
    check("组1 总列数为 2", by_title["A"][1] == 2 and by_title["B"][1] == 2, str(by_title))
    check("组2 总列数为 2", by_title["C"][1] == 2 and by_title["D"][1] == 2, str(by_title))
    check("组1 占用列 0/1", sorted([by_title["A"][0], by_title["B"][0]]) == [0, 1], str(by_title))
    check("组2 占用列 0/1（独立编号）",
          sorted([by_title["C"][0], by_title["D"][0]]) == [0, 1], str(by_title))


def test_touching_not_overlap() -> None:
    from app.ui.layout import layout_columns

    section("首尾相接不算重叠")
    # A: 9-10, B: 10-11 —— 应该能放在同一列
    occs = [make_occ("A", 9, 0, 10, 0), make_occ("B", 10, 0, 11, 0)]
    result = layout_columns(occs)
    check("相接的日程共用同一列", all(c == 0 for _, c, _ in result), str(result))
    check("相接的日程总列数为 1", all(tot == 1 for _, _, tot in result), str(result))


def test_nested() -> None:
    from app.ui.layout import layout_columns

    section("嵌套重叠（长日程内含短日程）")
    # A: 9-12（长）, B: 10-11（短，被包含）
    occs = [make_occ("A", 9, 0, 12, 0), make_occ("B", 10, 0, 11, 0)]
    result = layout_columns(occs)
    cols = sorted(c for _, c, _ in result)
    check("嵌套的两个日程分到不同列", cols == [0, 1], str(result))


def test_by_day() -> None:
    from app.ui.layout import layout_columns_by_day

    section("按日期分组")
    d1 = date(2026, 10, 21)
    d2 = date(2026, 10, 22)
    occs = [make_occ("A", 9, 0, 10, 0, d1), make_occ("B", 9, 0, 10, 0, d1),
            make_occ("C", 9, 0, 10, 0, d2)]
    result = layout_columns_by_day(occs)
    check("分成 2 天", len(result) == 2, str(list(result.keys())))
    check("第一天 2 个日程 2 列",
          all(tot == 2 for _, _, tot in result[d1]), str(result[d1]))
    check("第二天 1 个日程 1 列",
          all(tot == 1 for _, _, tot in result[d2]), str(result[d2]))


if __name__ == "__main__":
    print("重叠日程并排布局算法测试")
    test_no_overlap()
    test_two_overlap()
    test_three_overlap()
    test_partial_overlap()
    test_chain_overlap()
    test_group_isolation()
    test_touching_not_overlap()
    test_nested()
    test_by_day()
    print(f"\n{'=' * 46}")
    print(f"通过 {PASS} 项，失败 {FAIL} 项")
    print("=" * 46)
    sys.exit(1 if FAIL else 0)
