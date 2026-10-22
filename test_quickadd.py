# -*- coding: utf-8 -*-
"""
快捷添加（自然语言）端到端测试。

覆盖用户反馈的问题：
  "输入'本周五中午和Alex一起吃饭'，json 中有记录但日历不显示"

验证要点：
  1. 时段词不再丢失（"中午" -> 12:00，"下午" -> 14:00，"晚上" -> 19:00）
  2. 纯文字型输入也能解析出日期
  3. 快捷添加后，日历视图中**确实能看到**新建的日程（不只是 JSON 里有）
  4. JSON 持久化正常
  5. 各种口语表达的解析结果正确

运行：python test_quickadd.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import pathlib
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0

def _new_root(geometry: str = "1380x860+30+30", withdraw: bool = False):
    """创建独立的 Tk 根窗口（每个测试函数一个，避免相互干扰）。"""
    import tkinter as tk
    root = tk.Tk()
    if withdraw:
        root.withdraw()
    else:
        root.geometry(geometry)
    return root


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


# ============================================================ 解析层测试 ====
def test_period_words() -> None:
    """时段词不应被丢弃（"中午" 必须是 12:00，不能是 9:00）。"""
    from app.nlp import parse_quick

    section("时段词解析")
    today = date(2026, 10, 21)   # 周三

    cases = [
        ("本周五中午和Alex一起吃饭", 12, "和Alex一起吃饭"),
        ("本周五中午吃饭", 12, "吃饭"),
        ("今天中午吃饭", 12, "吃饭"),
        ("明天下午开会", 14, "开会"),
        ("今天上午站会", 9, "站会"),
        ("今天早上跑步", 8, "跑步"),
        ("今天晚上聚餐", 19, "聚餐"),
        ("今天傍晚喝茶", 18, "喝茶"),
        ("今天凌晨加班", 0, "加班"),
    ]
    for text, expect_hour, expect_title in cases:
        ev = parse_quick(text, today)
        if ev is None:
            check(f"{text!r} 解析成功", False, "返回 None")
            continue
        check(f"{text!r} -> {expect_hour}:00", ev.start.hour == expect_hour,
              f"实际 {ev.start}")
        check(f"{text!r} 标题为 {expect_title!r}", ev.title == expect_title,
              f"实际 {ev.title!r}")


def test_date_words() -> None:
    """日期词解析。"""
    from app.nlp import parse_quick

    section("日期词解析")
    today = date(2026, 10, 21)   # 周三

    cases = [
        ("今天开会", date(2026, 10, 21)),
        ("明天开会", date(2026, 10, 22)),
        ("后天开会", date(2026, 10, 23)),
        ("本周五开会", date(2026, 10, 23)),
        ("下周一开会", date(2026, 10, 26)),
        ("3天后开会", date(2026, 10, 24)),
    ]
    for text, expect_day in cases:
        ev = parse_quick(text, today)
        if ev is None:
            check(f"{text!r} 解析成功", False, "返回 None")
            continue
        check(f"{text!r} -> {expect_day}", ev.start.date() == expect_day,
              f"实际 {ev.start.date()}")


def test_explicit_time() -> None:
    """明确钟点的解析不能被时段词逻辑破坏。"""
    from app.nlp import parse_quick

    section("明确钟点解析")
    today = date(2026, 10, 21)

    cases = [
        ("明天下午3点开会", 15),
        ("今天上午9点站会", 9),
        ("今天晚上8点半聚餐", 20),
        ("明天10:30 客户拜访", 10),
        ("10:00-11:30 项目评审", 10),
    ]
    for text, expect_hour in cases:
        ev = parse_quick(text, today)
        if ev is None:
            check(f"{text!r} 解析成功", False, "返回 None")
            continue
        check(f"{text!r} -> {expect_hour} 点", ev.start.hour == expect_hour,
              f"实际 {ev.start}")


def test_nlp_fallback() -> None:
    """完全无法解析时应返回 None（由 UI 回退到完整表单）。"""
    from app.nlp import parse_quick

    section("无法解析时的回退")
    today = date(2026, 10, 21)
    ev = parse_quick("随便写点什么", today)
    check("无时间线索返回 None", ev is None, f"实际 {ev}")


# ============================================================ UI 层测试 ====
def test_quick_add_visible() -> None:
    """快捷添加后，日历视图里必须真的能看到该日程。"""
    import tkinter as tk
    from tkinter import messagebox as mb
    mb.showwarning = lambda *a, **k: None
    mb.showinfo = lambda *a, **k: None
    mb.askyesno = lambda *a, **k: True

    from app import config as cfg
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="calmemo_quick_"))
    for k, v in [("EVENTS_FILE", "e"), ("TODOS_FILE", "t"), ("TAGS_FILE", "g"),
                 ("CONFIG_FILE", "c"), ("REMINDER_STATE_FILE", "r"), ("HOLIDAYS_FILE", "h")]:
        setattr(cfg, k, tmp / f"{v}.json")

    from app.storage import Storage
    from app.ui.main_window import MainWindow

    root = _new_root()
    storage = Storage()
    app = MainWindow(root, storage)
    root.update()

    section("快捷添加后日历可见性")

    # 在日视图下添加一个"本周五"的日程 —— 这是用户报告的场景
    today = date.today()
    # 找一个未来的周五（同周内）
    friday = today + timedelta(days=(4 - today.weekday()) % 7 or 7)
    if friday == today:
        friday = today + timedelta(days=7)

    for view_name, view_key in (("日视图", "day"), ("周视图", "week"), ("月视图", "month")):
        app.switch_view(view_key)
        root.update()
        app.anchor_date = today
        app.refresh_views()
        root.update()

        # 关闭"快捷添加后确认"-> 直接创建（该测试关注日历可见性）
        app.quick_confirm_var.set(False)
        before = len(storage.events)
        # 通过输入框走完整链路
        app.quick_entry.delete(0, "end")
        app.quick_entry.insert(0, "本周五中午和Alex一起吃饭")
        app.quick_add_event()
        root.update()

        check(f"{view_name}: JSON 中新增了日程", len(storage.events) == before + 1,
              f"实际 {len(storage.events)}")

        # 关键断言：视图中能看到
        ev = storage.events[-1]
        occs = app._visible_occurrences(ev.start.date(), ev.start.date())
        check(f"{view_name}: 视图范围内能查到该日程", len(occs) >= 1, f"查到 {len(occs)} 条")

        # 检查当前视图的 occurrences 里是否包含
        if view_key == "day":
            view_occs = app.day_view._occurrences
        elif view_key == "week":
            view_occs = app.week_view._occurrences
        else:
            view_occs = app.month_view._occurrences
        titles = [o.title for o in view_occs]
        check(f"{view_name}: 日程出现在当前视图的日程列表中",
              ev.title in titles, f"当前视图 {titles}")

        # 移除这条，避免影响下一轮
        storage.events.pop()
        storage.save_events()
        app.anchor_date = today
        app.refresh_views()
        root.update()

    try:
        app.reminder_engine.stop()
    except Exception:
        pass
    try:
        app.reminder_engine.stop()
    except Exception:
        pass
    try:
        root.destroy()
    except Exception:
        pass


def test_persistence() -> None:
    """快捷添加的日程要能正确持久化。"""
    import tkinter as tk
    from tkinter import messagebox as mb
    mb.showwarning = lambda *a, **k: None
    mb.showinfo = lambda *a, **k: None

    from app import config as cfg
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="calmemo_persist_"))
    for k, v in [("EVENTS_FILE", "e"), ("TODOS_FILE", "t"), ("TAGS_FILE", "g"),
                 ("CONFIG_FILE", "c"), ("REMINDER_STATE_FILE", "r"), ("HOLIDAYS_FILE", "h")]:
        setattr(cfg, k, tmp / f"{v}.json")

    from app.storage import Storage
    from app.ui.main_window import MainWindow

    root = _new_root(withdraw=True)
    storage = Storage()
    app = MainWindow(root, storage)
    root.update()

    section("快捷添加持久化")
    app.quick_confirm_var.set(False)   # 直接创建模式
    app.quick_entry.insert(0, "本周五中午和Alex一起吃饭")
    app.quick_add_event()
    root.update()

    ev = storage.events[-1]
    # 重新加载 storage，验证落盘
    storage2 = Storage()
    check("重新加载后仍能读到该日程",
          any(e.title == ev.title for e in storage2.events),
          f"存储 {len(storage2.events)} 条")

    try:
        app.reminder_engine.stop()
    except Exception:
        pass
    try:
        app.reminder_engine.stop()
    except Exception:
        pass
    try:
        root.destroy()
    except Exception:
        pass


def test_untagged_visible() -> None:
    """没有标签的日程不能被标签筛选器藏起来（这是用户反馈的核心 bug）。"""
    section("无标签日程的可见性")
    import tkinter as tk
    from tkinter import messagebox as mb
    mb.showwarning = lambda *a, **k: None
    mb.showinfo = lambda *a, **k: None

    from app import config as cfg
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="calmemo_tag_"))
    for k, v in [("EVENTS_FILE", "e"), ("TODOS_FILE", "t"), ("TAGS_FILE", "g"),
                 ("CONFIG_FILE", "c"), ("REMINDER_STATE_FILE", "r"), ("HOLIDAYS_FILE", "h")]:
        setattr(cfg, k, tmp / f"{v}.json")

    from app.storage import Storage
    from app.ui.main_window import MainWindow

    root = _new_root(withdraw=True)
    storage = Storage()
    app = MainWindow(root, storage)
    root.update()

    app.quick_confirm_var.set(False)
    fp = app.filter_panel
    # 无标签日程
    check("无标签日程通过筛选", fp.is_active("normal", "") is True)
    # 有标签且在勾选列表里
    check("已勾选标签的日程通过筛选", fp.is_active("normal", "工作") is True)
    # 有标签但不在勾选列表里
    check("未勾选的标签被过滤", fp.is_active("normal", "不存在的标签") is False)

    # 只勾一个标签时，无标签日程仍应显示
    for var in fp.tag_vars.values():
        var.set(False)
    if "工作" in fp.tag_vars:
        fp.tag_vars["工作"].set(True)
    check("只筛一个标签时，无标签日程仍显示", fp.is_active("normal", "") is True)
    check("只筛一个标签时，其他标签被过滤", fp.is_active("normal", "私人") is False)

    try:
        app.reminder_engine.stop()
    except Exception:
        pass
    try:
        app.reminder_engine.stop()
    except Exception:
        pass
    try:
        root.destroy()
    except Exception:
        pass


def test_highlight() -> None:
    """新建的日程应被标记高亮并置顶显示。"""
    section("新建日程高亮")
    import tkinter as tk
    from tkinter import messagebox as mb
    mb.showwarning = lambda *a, **k: None
    mb.showinfo = lambda *a, **k: None

    from app import config as cfg
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="calmemo_hl_"))
    for k, v in [("EVENTS_FILE", "e"), ("TODOS_FILE", "t"), ("TAGS_FILE", "g"),
                 ("CONFIG_FILE", "c"), ("REMINDER_STATE_FILE", "r"), ("HOLIDAYS_FILE", "h")]:
        setattr(cfg, k, tmp / f"{v}.json")

    from app.storage import Storage
    from app.ui.main_window import MainWindow

    root = _new_root()
    storage = Storage()
    app = MainWindow(root, storage)
    root.update()

    app.switch_view("month")
    root.update()
    app.quick_confirm_var.set(False)   # 直接创建模式
    app.quick_entry.insert(0, "本周五中午和Alex一起吃饭")
    app.quick_add_event()
    root.update()

    ev = storage.events[-1]
    check("高亮 id 指向新建的日程", app.month_view.highlight_id == ev.id,
          f"{app.month_view.highlight_id} vs {ev.id}")
    check("视图跳到了新日程所在日期", app.anchor_date == ev.start.date(),
          f"{app.anchor_date} vs {ev.start.date()}")

    try:
        app.reminder_engine.stop()
    except Exception:
        pass
    try:
        app.reminder_engine.stop()
    except Exception:
        pass
    try:
        root.destroy()
    except Exception:
        pass


def main() -> int:
    print("快捷添加（自然语言）端到端测试")
    test_period_words()
    test_date_words()
    test_explicit_time()
    test_nlp_fallback()
    test_quick_add_visible()
    test_persistence()
    test_untagged_visible()
    test_highlight()
    print(f"\n{'=' * 46}")
    print(f"通过 {PASS} 项，失败 {FAIL} 项")
    print("=" * 46)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
