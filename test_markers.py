# -*- coding: utf-8 -*-
"""
快捷输入增强功能测试。

覆盖：
  1. 中文日期表达（X号 / 本月X号 / 下月X号 / 月底 / 二十八号）
  2. 显式标记语法（#标签 !优先级 @日期 ~时长）
  3. 自然语言标签与优先级
  4. 「快捷添加后确认」开关的两种模式
  5. 新标签自动创建
  6. 解析结果不写入存储（确认模式下）

运行：python test_markers.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import pathlib
from datetime import date, datetime

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


TODAY = date(2026, 10, 21)   # 周三


# ============================================================ 解析层 ======
def test_cn_day() -> None:
    from app.nlp import parse_quick

    section("中文日期表达")
    cases = [
        ("本月28号下午2点拜访heveaboard", date(2026, 10, 28), "拜访heveaboard"),
        ("28号下午2点拜访客户", date(2026, 10, 28), "拜访客户"),
        ("10月28号下午2点拜访客户", date(2026, 10, 28), "拜访客户"),
        ("下月28号下午2点拜访客户", date(2026, 11, 28), "拜访客户"),
        ("二十八号下午2点开会", date(2026, 10, 28), "开会"),
        ("28日下午2点开会", date(2026, 10, 28), "开会"),
    ]
    for text, expect_day, expect_title in cases:
        ev = parse_quick(text, TODAY)
        if ev is None:
            check(f"{text!r} 解析成功", False, "返回 None")
            continue
        check(f"{text!r} -> {expect_day}", ev.start.date() == expect_day,
              f"实际 {ev.start.date()}")
        check(f"{text!r} 标题 {expect_title!r}", ev.title == expect_title,
              f"实际 {ev.title!r}")


def test_month_edge() -> None:
    from app.nlp import parse_quick

    section("月初/月底")
    ev = parse_quick("月底下午2点月末总结", TODAY)
    check("月底 -> 10-31", ev is not None and ev.start.date() == date(2026, 10, 31),
          f"实际 {ev.start if ev else None}")
    ev = parse_quick("月初上午10点启动会", TODAY)
    check("月初 -> 11-01（本月已过则顺延）",
          ev is not None and ev.start.date() == date(2026, 11, 1),
          f"实际 {ev.start if ev else None}")


def test_markers() -> None:
    from app.nlp import parse_quick

    section("显式标记语法")
    ev = parse_quick("#工作 !高 客户回访", TODAY)
    check("解析成功", ev is not None)
    if ev:
        check("标签 = 工作", ev.tag == "工作", ev.tag)
        check("优先级 = high", ev.priority == "high", ev.priority)
        check("标题去掉标记", ev.title == "客户回访", ev.title)
        check("默认时间 9:00", ev.start.hour == 9, str(ev.start))

    ev = parse_quick("#工作 !高 @10-28 ~1.5h 客户回访", TODAY)
    check("组合标记解析成功", ev is not None)
    if ev:
        check("日期 = 10-28", ev.start.date() == date(2026, 10, 28), str(ev.start))
        check("时长 1.5h = 90 分钟",
              (ev.end - ev.start).total_seconds() / 60 == 90,
              f"实际 {(ev.end - ev.start).total_seconds() / 60}")
        check("标签 = 工作", ev.tag == "工作", ev.tag)
        check("优先级 = high", ev.priority == "high", ev.priority)

    ev = parse_quick("@明天 下午3点 #采购 询价", TODAY)
    check("@明天 + 时间 + 标签", ev is not None and ev.start.date() == date(2026, 10, 22)
          and ev.start.hour == 15 and ev.tag == "采购",
          f"{ev.start if ev else None} tag={ev.tag if ev else None}")

    ev = parse_quick("~90 明天上午10点 方案讨论", TODAY)
    check("~90 裸数字按分钟", ev is not None and
          (ev.end - ev.start).total_seconds() / 60 == 90,
          f"实际 {(ev.end - ev.start).total_seconds() / 60 if ev else None}")

    ev = parse_quick("~2小时 明天上午10点 评审", TODAY)
    check("~2小时 = 120 分钟", ev is not None and
          (ev.end - ev.start).total_seconds() / 60 == 120,
          f"实际 {(ev.end - ev.start).total_seconds() / 60 if ev else None}")


def test_nl_meta() -> None:
    from app.nlp import parse_quick

    section("自然语言标签与优先级")
    ev = parse_quick("明天下午3点 紧急 客户来电", TODAY)
    check("'紧急' -> high", ev is not None and ev.priority == "high",
          ev.priority if ev else None)
    check("'紧急' 从标题移除", ev is not None and ev.title == "客户来电",
          ev.title if ev else None)

    ev = parse_quick("明天下午3点 低优先级 有空再聊", TODAY)
    check("'低优先级' -> low", ev is not None and ev.priority == "low",
          ev.priority if ev else None)

    ev = parse_quick("明天下午3点 工作标签 开会", TODAY)
    check("'工作标签' -> 标签 工作", ev is not None and ev.tag == "工作",
          ev.tag if ev else None)

    ev = parse_quick("明天下午3点 标签 采购 询价", TODAY)
    check("'标签 采购' -> 标签 采购", ev is not None and ev.tag == "采购",
          ev.tag if ev else None)


def test_marker_priority_over_nl() -> None:
    from app.nlp import parse_quick

    section("显式标记优先于自然语言")
    ev = parse_quick("明天下午3点 紧急 #工作 客户来电", TODAY)
    check("自然语言'紧急'不覆盖显式 !低",
          ev is not None and ev.priority == "high",   # 未给 ! 时用自然语言
          ev.priority if ev else None)
    ev = parse_quick("明天下午3点 紧急 !低 客户来电", TODAY)
    check("显式 !低 覆盖自然语言'紧急'",
          ev is not None and ev.priority == "low", ev.priority if ev else None)


# ============================================================ UI 层 ======
def build_app(root):
    from app.storage import Storage
    from app.ui.main_window import MainWindow
    return MainWindow(root, Storage())


def test_confirm_mode() -> None:
    """开启「快捷添加后确认」时：弹出表单、不写入存储。"""
    import tkinter as tk
    from tkinter import messagebox as mb
    mb.showwarning = lambda *a, **k: None
    mb.showinfo = lambda *a, **k: None
    mb.askyesno = lambda *a, **k: True

    from app import config as cfg
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="calmemo_mk_"))
    for k, v in [("EVENTS_FILE", "e"), ("TODOS_FILE", "t"), ("TAGS_FILE", "g"),
                 ("CONFIG_FILE", "c"), ("REMINDER_STATE_FILE", "r"), ("HOLIDAYS_FILE", "h")]:
        setattr(cfg, k, tmp / f"{v}.json")

    root = _new_root()
    app = build_app(root)
    root.update()

    section("快捷添加后确认（开启）")
    app.quick_confirm_var.set(True)
    before = len(app.storage.events)
    app.quick_entry.insert(0, "明天下午3点 #工作 客户回访")
    app.quick_add_event()
    root.update()

    check("未直接写入存储", len(app.storage.events) == before,
          f"实际 {len(app.storage.events)}")
    # 找到弹出的表单
    dlg = None
    for w in root.winfo_children():
        if isinstance(w, tk.Toplevel) and "日程" in str(w.title()):
            dlg = w
            break
    check("弹出了日程表单", dlg is not None)
    form = getattr(app, "_last_event_dialog", None)
    check("拿到表单实例", form is not None)
    if form is not None:
        check("标题已预填", form.var_title.get() == "客户回访",
              form.var_title.get())
        check("标签已预填", form.var_tag.get() == "工作", form.var_tag.get())
        check("优先级已预填", form.var_priority.get() == "normal",
              form.var_priority.get())
        # 明天（相对当前日期计算，避免测试随日期失效）
        from datetime import date, timedelta
        expect_day = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        check("日期已预填", form.var_start_date.get() == expect_day,
              f"{form.var_start_date.get()} vs {expect_day}")
        check("时间已预填", form.var_start_time.get() == "15:00",
              form.var_start_time.get())
        # 取消不应写入存储
        form.on_cancel()
        root.update()
        check("取消后未写入存储", len(app.storage.events) == before,
              f"实际 {len(app.storage.events)}")
    if dlg is not None:
        try:
            dlg.destroy()
        except Exception:
            pass
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


def test_direct_mode() -> None:
    """关闭「快捷添加后确认」时：直接创建。"""
    import tkinter as tk
    from tkinter import messagebox as mb
    mb.showwarning = lambda *a, **k: None
    mb.showinfo = lambda *a, **k: None

    from app import config as cfg
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="calmemo_mk2_"))
    for k, v in [("EVENTS_FILE", "e"), ("TODOS_FILE", "t"), ("TAGS_FILE", "g"),
                 ("CONFIG_FILE", "c"), ("REMINDER_STATE_FILE", "r"), ("HOLIDAYS_FILE", "h")]:
        setattr(cfg, k, tmp / f"{v}.json")

    root = _new_root()
    app = build_app(root)
    root.update()

    section("快捷添加后确认（关闭）")
    app.quick_confirm_var.set(False)
    before = len(app.storage.events)
    app.quick_entry.insert(0, "明天下午3点 #工作 客户回访")
    app.quick_add_event()
    root.update()

    check("直接写入了存储", len(app.storage.events) == before + 1,
          f"实际 {len(app.storage.events)}")
    if app.storage.events:
        ev = app.storage.events[-1]
        check("标签正确", ev.tag == "工作", ev.tag)
        check("标题正确", ev.title == "客户回访", ev.title)

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


def test_new_tag_autocreate() -> None:
    """快捷输入的新标签应自动创建并出现在筛选列表里。"""
    import tkinter as tk
    from tkinter import messagebox as mb
    mb.showwarning = lambda *a, **k: None
    mb.showinfo = lambda *a, **k: None

    from app import config as cfg
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="calmemo_mk3_"))
    for k, v in [("EVENTS_FILE", "e"), ("TODOS_FILE", "t"), ("TAGS_FILE", "g"),
                 ("CONFIG_FILE", "c"), ("REMINDER_STATE_FILE", "r"), ("HOLIDAYS_FILE", "h")]:
        setattr(cfg, k, tmp / f"{v}.json")

    root = _new_root()
    root.withdraw()
    app = build_app(root)
    root.update()

    section("新标签自动创建")
    app.quick_confirm_var.set(False)
    check("标签尚不存在", "客户A" not in app.storage.tag_names())
    app.quick_entry.insert(0, "明天下午3点 #客户A 回访")
    app.quick_add_event()
    root.update()
    check("新标签已创建", "客户A" in app.storage.tag_names(),
          str(app.storage.tag_names()))
    check("筛选器已同步", "客户A" in app.filter_panel.tag_vars,
          str(list(app.filter_panel.tag_vars.keys())))

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
    print("快捷输入增强功能测试")
    test_cn_day()
    test_month_edge()
    test_markers()
    test_nl_meta()
    test_marker_priority_over_nl()
    test_confirm_mode()
    test_direct_mode()
    test_new_tag_autocreate()
    print(f"\n{'=' * 46}")
    print(f"通过 {PASS} 项，失败 {FAIL} 项")
    print("=" * 46)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
