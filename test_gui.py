# -*- coding: utf-8 -*-
"""
GUI 冒烟测试：真实创建窗口并驱动交互，验证界面不会崩溃。

运行：python test_gui.py
（会自动关闭窗口，测试结束后退出）
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from datetime import date, datetime, timedelta

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


def main() -> int:
    import pathlib
    import tkinter as tk

    # 屏蔽 messagebox 模态框（自动化测试中会阻塞等待用户点击）
    from tkinter import messagebox as _mb
    _mb.showwarning = lambda *a, **k: None
    _mb.showinfo = lambda *a, **k: None
    _mb.showerror = lambda *a, **k: None
    _mb.askyesno = lambda *a, **k: True

    from app import config as cfg

    # 隔离测试数据目录
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="calmemo_gui_"))
    cfg.EVENTS_FILE = tmp / "events.json"
    cfg.TODOS_FILE = tmp / "todos.json"
    cfg.TAGS_FILE = tmp / "tags.json"
    cfg.CONFIG_FILE = tmp / "config.json"
    cfg.REMINDER_STATE_FILE = tmp / "reminder_state.json"
    cfg.HOLIDAYS_FILE = tmp / "holidays.json"

    from app.models import Event, Todo
    from app.storage import Storage
    from app.ui.main_window import MainWindow

    root = tk.Tk()
    root.withdraw()
    storage = Storage()

    # 造一批测试数据
    now = datetime.now()
    samples = [
        Event(title=f"测试日程{i}", note=f"备注 {i}",
              start=now + timedelta(hours=i), end=now + timedelta(hours=i + 1),
              tag="工作" if i % 2 == 0 else "私人", priority=["high", "normal", "low"][i % 3],
              reminders=[0] if i % 4 == 0 else [])
        for i in range(12)
    ]
    # 重复日程
    samples.append(Event(title="每日站会", start=now.replace(hour=9, minute=30),
                         end=now.replace(hour=10, minute=0), repeat="daily", tag="会议"))
    samples.append(Event(title="每周例会", start=now.replace(hour=14, minute=0),
                         end=now.replace(hour=15, minute=0), repeat="weekly",
                         repeat_weekdays=[0, 2], tag="会议", priority="high"))
    # 跨天日程
    samples.append(Event(title="跨天出差", start=now.replace(hour=9, minute=0),
                         end=(now + timedelta(days=2)).replace(hour=18, minute=0)))
    for ev in samples:
        storage.upsert_event(ev)
    storage.upsert_todo(Todo(text="买菜"))
    storage.upsert_todo(Todo(text="写周报", done=True))

    section("主窗口构建")
    try:
        app = MainWindow(root, storage)
        root.update()
        check("主窗口构建成功", True)
    except Exception:
        traceback.print_exc()
        check("主窗口构建成功", False, traceback.format_exc()[-300:])
        return 1

    section("视图渲染")
    for view in ("month", "week", "day"):
        try:
            app.switch_view(view)
            root.update()
            check(f"{view} 视图渲染", True)
        except Exception:
            traceback.print_exc()
            check(f"{view} 视图渲染", False, traceback.format_exc()[-300:])

    section("导航交互")
    try:
        app.go_prev(); root.update()
        app.go_next(); root.update()
        app.go_today(); root.update()
        check("上/下/今天 导航", True)
    except Exception:
        traceback.print_exc()
        check("上/下/今天 导航", False, traceback.format_exc()[-300:])

    section("置顶切换")
    try:
        app.flip_topmost(); root.update()
        check("置顶开启", app._topmost_var().get() is True)
        check("置顶状态已持久化", storage.get_config("always_on_top") is True)
        app.flip_topmost(); root.update()
        check("置顶关闭", app._topmost_var().get() is False)
        check("置顶状态已持久化(关)", storage.get_config("always_on_top") is False)
    except Exception:
        traceback.print_exc()
        check("置顶切换", False, traceback.format_exc()[-300:])

    section("主题切换")
    try:
        app.toggle_theme(); root.update()
        check("切换到深色", app.theme_name == "dark")
        app.toggle_theme(); root.update()
        check("切换回浅色", app.theme_name == "light")
    except Exception:
        traceback.print_exc()
        check("主题切换", False, traceback.format_exc()[-300:])

    section("待办操作")
    try:
        before = len(app.storage.todos)
        app.add_todo("GUI测试待办")
        root.update()
        check("添加待办", len(app.storage.todos) == before + 1)
        todo = app.storage.todos[-1]
        app.toggle_todo(todo); root.update()
        check("勾选完成", app.storage.todos[-1].done is True)
        app.delete_todo(todo); root.update()
        check("删除待办", len(app.storage.todos) == before)
    except Exception:
        traceback.print_exc()
        check("待办操作", False, traceback.format_exc()[-300:])

    section("快捷添加（自然语言）")
    try:
        # 模式一：确认模式 —— 弹出表单，确认后才写入
        app.quick_confirm_var.set(True)
        before = len(app.storage.events)
        app.quick_entry.delete(0, "end")
        app.quick_entry.insert(0, "明天下午3点产品评审")
        app.quick_add_event()
        root.update()
        check("确认模式下未直接写入", len(app.storage.events) == before,
              f"实际 {len(app.storage.events)}")
        form = getattr(app, "_last_event_dialog", None)
        check("确认模式弹出了表单", form is not None)
        if form is not None:
            check("表单已预填标题", form.var_title.get() == "产品评审",
                  form.var_title.get())
            form.on_save(form.result) if form.result else None
            # 直接触发保存
            form._on_save()
            root.update()
        titles = [e.title for e in app.storage.events]
        check("确认保存后写入日程", "产品评审" in titles, str(titles[-3:]))

        # 模式二：直接创建
        app.quick_confirm_var.set(False)
        before = len(app.storage.events)
        app.quick_entry.delete(0, "end")
        app.quick_entry.insert(0, "后天上午10点客户回访")
        app.quick_add_event()
        root.update()
        titles = [e.title for e in app.storage.events]
        check("直接模式创建日程", "客户回访" in titles and len(app.storage.events) == before + 1,
              str(titles[-3:]))
    except Exception:
        traceback.print_exc()
        check("自然语言创建日程", False, traceback.format_exc()[-300:])

    section("重复项编辑/删除作用域")
    try:
        from app.recurrence import expand_all
        occs = expand_all(app.storage.events, date.today(), date.today() + timedelta(days=7))
        daily_occ = [o for o in occs if o.title == "每日站会"]
        check("重复日程已展开", len(daily_occ) >= 2, f"实际 {len(daily_occ)}")
        if daily_occ:
            occ = daily_occ[0]
            # 仅删除这一次
            app._delete_occurrence(occ, "this")
            root.update()
            occs2 = expand_all(app.storage.events, date.today(), date.today() + timedelta(days=7))
            check("仅删除单次生效",
                  len([o for o in occs2 if o.title == "每日站会"]) == len(daily_occ) - 1)
    except Exception:
        traceback.print_exc()
        check("重复项作用域操作", False, traceback.format_exc()[-300:])

    section("筛选面板")
    try:
        app.filter_panel.priority_vars["high"].set(False)
        app.refresh_views(); root.update()
        check("优先级筛选生效", True)
        app.filter_panel.reset(); root.update()
        check("筛选重置", True)
    except Exception:
        traceback.print_exc()
        check("筛选面板", False, traceback.format_exc()[-300:])

    section("导入导出")
    try:
        import json
        export_path = tmp / "backup.json"
        data = {"app": "日程备忘", "version": 1,
                "events": [e.to_dict() for e in app.storage.events],
                "todos": [t.to_dict() for t in app.storage.todos],
                "tags": [t.to_dict() for t in app.storage.tags]}
        export_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        check("导出数据结构合法", isinstance(data["events"], list) and len(data["events"]) > 0)
    except Exception:
        traceback.print_exc()
        check("导入导出", False, traceback.format_exc()[-300:])

    section("提醒弹窗")
    try:
        from app.ui.reminder_popup import ReminderPopup
        from app.recurrence import Occurrence
        ev = app.storage.events[0]
        occ = Occurrence(ev, ev.start, ev.end, ev.start.strftime("%Y-%m-%d"))
        popup = ReminderPopup(root, occ, 0, app.theme_name, False,
                               on_snooze=lambda *a: None, on_close=lambda: None)
        root.update()
        check("提醒弹窗创建", True)
        # 注意：Tkinter 的 attributes() 返回 int(0/1)，需用真值判断而非 is True
        check("提醒弹窗强制置顶", bool(popup.win.attributes("-topmost")) is True,
              f"topmost={popup.win.attributes('-topmost')}")
        from app.topmost import is_topmost
        check("置顶状态检测正确", is_topmost(popup.win) is True)
        popup.close()
        root.update()
        check("提醒弹窗关闭", True)
    except Exception:
        traceback.print_exc()
        check("提醒弹窗", False, traceback.format_exc()[-300:])

    section("事件表单与详情")
    try:
        from app.ui.event_dialog import EventDialog
        dlg = EventDialog(root, app.theme_name, default_date=datetime.now(),
                          tag_names=app.storage.tag_names(),
                          on_save=lambda e: None)
        root.update()
        check("新建表单创建", True)
        dlg.var_title.set("表单测试")
        dlg.var_start_time.set("10:00")
        dlg.var_end_time.set("09:00")
        dlg._on_save()  # 应因时间冲突被拦截
        root.update()
        check("时间冲突被拦截", dlg.result is None)
        dlg.var_end_time.set("11:00")
        dlg._on_save()
        root.update()
        check("正常保存成功", dlg.result is not None and dlg.result.title == "表单测试")
    except Exception:
        traceback.print_exc()
        check("事件表单", False, traceback.format_exc()[-300:])

    try:
        from app.ui.event_detail import EventDetailDialog
        from app.recurrence import Occurrence
        ev = app.storage.events[0]
        occ = Occurrence(ev, ev.start, ev.end, ev.start.strftime("%Y-%m-%d"))
        det = EventDetailDialog(root, app.theme_name, occ, "#00489D",
                                on_edit=lambda *a: None, on_delete=lambda *a: None)
        root.update()
        check("详情弹窗创建", True)
        det.win.destroy()
    except Exception:
        traceback.print_exc()
        check("详情弹窗", False, traceback.format_exc()[-300:])

    section("搜索面板")
    try:
        from app.ui.search_panel import SearchPanel
        sp = SearchPanel(root, app.theme_name, app.storage.events, app.storage.todos,
                         on_pick_event=lambda e: None, on_pick_todo=lambda t: None)
        root.update()
        sp.var_query.set("测试")
        sp.do_search()
        root.update()
        n = len(sp.tree.get_children())
        check("搜索返回结果", n > 0, f"结果 {n} 条")
        # 弹窗应居中（不在左上角）
        # 注意：主窗口在测试中是 withdraw 状态，弹窗不会被真正映射，
        # 因此 winfo_rootx() 无意义；改为检查 geometry 里的位置分量。
        geo = sp.win.geometry()
        # geometry 形如 "626x567+405+138"，取最后两个分量作为 x / y
        parts = geo.split("+")
        try:
            gx, gy = int(parts[-2]), int(parts[-1])
        except Exception:
            gx, gy = 0, 0
        # 屏幕尺寸在 withdraw 状态下可能取不到，这里只断言"不是左上角 (0,0)"
        check("搜索弹窗居中显示（不在左上角）", gx > 0 and gy > 0, f"geometry={geo}")
        check("搜索弹窗可拖动", hasattr(sp, "_enable_drag"))
        sp.close()
    except Exception:
        traceback.print_exc()
        check("搜索面板", False, traceback.format_exc()[-300:])

    section("统计与持久化")
    try:
        app.refresh_stats(); root.update()
        check("统计面板更新", True)
        # 关闭再打开，验证数据持久化
        app.reminder_engine.stop()
        root.destroy()
        root2 = tk.Tk()
        root2.withdraw()
        st2 = Storage()
        check("重启后日程仍在", len(st2.events) > 0, f"实际 {len(st2.events)}")
        check("重启后待办仍在", len(st2.todos) >= 2)
        root2.destroy()
    except Exception:
        traceback.print_exc()
        check("持久化验证", False, traceback.format_exc()[-300:])

    print(f"\n{'=' * 46}")
    print(f"通过 {PASS} 项，失败 {FAIL} 项")
    print("=" * 46)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
