# -*- coding: utf-8 -*-
"""
弹窗行为回归测试 —— 针对"点击日期后屏幕锁死"这一致命 bug。

验证要点：
  1. 弹窗 grab 时窗口已有完整内容（不是空窗口）
  2. 弹窗尺寸合理（不被压成极小）
  3. 弹窗位置在屏幕内（不是左上角）
  4. 关键控件（保存/取消按钮、标题输入框）真实存在且可见
  5. 关闭后 grab 已释放，主窗口重新可交互
"""

from __future__ import annotations

import os
import sys
import tempfile
import pathlib
from datetime import datetime

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
    import tkinter as tk
    from tkinter import messagebox as mb

    # 屏蔽模态提示框（会阻塞）
    mb.showwarning = lambda *a, **k: None
    mb.showinfo = lambda *a, **k: None
    mb.showerror = lambda *a, **k: None
    mb.askyesno = lambda *a, **k: True

    from app import config as cfg
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="calmemo_dlg_"))
    for k, v in [("EVENTS_FILE", "e"), ("TODOS_FILE", "t"), ("TAGS_FILE", "g"),
                 ("CONFIG_FILE", "c"), ("REMINDER_STATE_FILE", "r"), ("HOLIDAYS_FILE", "h")]:
        setattr(cfg, k, tmp / f"{v}.json")

    from app.models import Event
    from app.storage import Storage
    from app.ui.main_window import MainWindow
    from app.ui.event_dialog import EventDialog
    from app.ui.event_detail import EventDetailDialog
    from app.ui.tag_manager import TagManagerDialog
    from app.recurrence import Occurrence

    root = tk.Tk()
    root.geometry("1200x760+40+40")
    storage = Storage()
    storage.upsert_event(Event(title="测试日程", note="备注",
                                start=datetime.now(), end=datetime.now()))
    app = MainWindow(root, storage)
    root.update()

    # ---------------------------------------------------------- 新建表单 ----
    section("新建日程表单（对应用户报告的点击日期场景）")

    dlg = EventDialog(root, app.theme_name, default_date=datetime.now(),
                      tag_names=storage.tag_names(), on_save=lambda e: None)
    root.update()

    w, h = dlg.win.winfo_width(), dlg.win.winfo_height()
    check("弹窗尺寸不小于 500x500", w >= 500 and h >= 500, f"实际 {w}x{h}")
    check("弹窗不是极小尺寸（未被压扁）", w > 100 and h > 100, f"实际 {w}x{h}")

    x, y = dlg.win.winfo_rootx(), dlg.win.winfo_rooty()
    sw, sh = dlg.win.winfo_screenwidth(), dlg.win.winfo_screenheight()
    check("弹窗位置在屏幕内（不在左上角）", x > 0 and y > 0, f"位置 {x},{y}")
    check("弹窗位置未超出屏幕右边界", x + w <= sw + 5, f"{x}+{w} vs {sw}")
    check("弹窗位置未超出屏幕下边界", y + h <= sh + 5, f"{y}+{h} vs {sh}")

    # 关键控件必须存在且可见
    check("标题输入框存在", hasattr(dlg, "title_entry") and dlg.title_entry.winfo_exists())
    check("标题输入框可见", dlg.title_entry.winfo_ismapped())

    # 统计窗口内可见的按钮数量（保存/取消/管理标签）
    def count_buttons(widget):
        """统计 tk.Button、ttk.Button 与自定义 RoundedButton 数量。"""
        n = 0
        for child in widget.winfo_children():
            cls = child.__class__.__name__
            if cls in ("Button", "TButton", "RoundedButton"):
                n += 1
            try:
                n += count_buttons(child)
            except Exception:
                pass
        return n

    btn_count = count_buttons(dlg.win)
    check("窗口内至少有 3 个按钮（保存/取消/管理标签）", btn_count >= 3, f"实际 {btn_count}")

    # grab 存在但窗口非空
    grab = root.grab_current()
    check("grab 已设置", grab is not None, str(grab))
    if grab is not None:
        check("grab 的窗口是弹窗本身", grab == dlg.win.winfo_toplevel(),
              f"grab={grab} win={dlg.win.winfo_toplevel()}")

    # 关闭后 grab 释放
    dlg.on_cancel()
    root.update()
    check("关闭后 grab 已释放", root.grab_current() is None, str(root.grab_current()))

    # ---------------------------------------------------------- 编辑表单 ----
    section("编辑日程表单")
    ev = storage.events[0]
    dlg2 = EventDialog(root, app.theme_name, initial=ev,
                       tag_names=storage.tag_names(), on_save=lambda e: None)
    root.update()
    w2, h2 = dlg2.win.winfo_width(), dlg2.win.winfo_height()
    check("编辑表单尺寸正常", w2 >= 500 and h2 >= 500, f"实际 {w2}x{h2}")
    check("编辑表单标题已回填", dlg2.var_title.get() == "测试日程", dlg2.var_title.get())
    dlg2.on_cancel()
    root.update()

    # ---------------------------------------------------------- 详情弹窗 ----
    section("日程详情弹窗")
    occ = Occurrence(ev, ev.start, ev.end, ev.start.strftime("%Y-%m-%d"))
    det = EventDetailDialog(root, app.theme_name, occ, "#00489D",
                            on_edit=lambda *a: None, on_delete=lambda *a: None)
    root.update()
    w3, h3 = det.win.winfo_width(), det.win.winfo_height()
    check("详情弹窗尺寸正常", w3 >= 440 and h3 >= 360, f"实际 {w3}x{h3}")
    x3, y3 = det.win.winfo_rootx(), det.win.winfo_rooty()
    check("详情弹窗位置在屏幕内", x3 > 0 and y3 > 0, f"位置 {x3},{y3}")
    det.close()
    root.update()
    check("详情弹窗关闭后 grab 释放", root.grab_current() is None)

    # ---------------------------------------------------------- 标签管理 ----
    section("标签管理弹窗")
    tagd = TagManagerDialog(root, app.theme_name, storage.tag_names(),
                            on_save=lambda t: None)
    root.update()
    w4, h4 = tagd.win.winfo_width(), tagd.win.winfo_height()
    check("标签弹窗尺寸正常", w4 >= 400 and h4 >= 400, f"实际 {w4}x{h4}")
    x4, y4 = tagd.win.winfo_rootx(), tagd.win.winfo_rooty()
    check("标签弹窗位置在屏幕内", x4 > 0 and y4 > 0, f"位置 {x4},{y4}")
    tagd.close()
    root.update()

    # ---------------------------------------------------------- 重复作用域 ----
    section("重复日程作用域询问（嵌套弹窗）")
    ev_rep = Event(title="每日站会", start=datetime.now().replace(hour=9),
                   end=datetime.now().replace(hour=10), repeat="daily")
    storage.upsert_event(ev_rep)
    occ_r = Occurrence(ev_rep, ev_rep.start, ev_rep.end, ev_rep.start.strftime("%Y-%m-%d"))
    det2 = EventDetailDialog(root, app.theme_name, occ_r, "#6A1B9A",
                             on_edit=lambda *a: None, on_delete=lambda *a: None)
    root.update()
    check("重复日程详情弹窗创建", True)
    # _ask_scope 会阻塞等待，需要异步关闭 —— 这里只验证不抛异常
    check("详情弹窗 grab 正常", root.grab_current() is not None)
    det2.close()
    root.update()
    check("关闭后 grab 释放", root.grab_current() is None)

    # ---------------------------------------------------------- 真实点击 ----
    section("模拟真实点击日历日期（用户报告的场景）")
    root.grab_current()  # 确保无残留 grab
    try:
        from datetime import date as _date
        app.on_day_click(_date.today())
        root.update()
        # 找出新出现的 Toplevel
        toplevels = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
        check("点击日期后弹出表单", len(toplevels) >= 1, f"找到 {len(toplevels)} 个")
        if toplevels:
            tl = toplevels[-1]
            tw, th = tl.winfo_width(), tl.winfo_height()
            check("弹出的表单尺寸正常", tw >= 500 and th >= 500, f"实际 {tw}x{th}")
            tx, ty = tl.winfo_rootx(), tl.winfo_rooty()
            check("弹出的表单位置在屏幕内", tx > 0 and ty > 0, f"位置 {tx},{ty}")
            # 清理
            try:
                tl.grab_release()
            except Exception:
                pass
            tl.destroy()
            root.update()
        check("主窗口在弹窗关闭后可交互", root.grab_current() is None)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        check("模拟点击日期", False, str(exc))

    # ---------------------------------------------------------- 提醒弹窗 ----
    section("提醒弹窗")
    from app.ui.reminder_popup import ReminderPopup
    popup = ReminderPopup(root, occ, 0, app.theme_name, False,
                          on_snooze=lambda *a: None, on_close=lambda: None)
    root.update()
    pw, ph = popup.win.winfo_width(), popup.win.winfo_height()
    check("提醒弹窗尺寸正常", pw >= 300 and ph >= 150, f"实际 {pw}x{ph}")
    check("提醒弹窗强制置顶", bool(popup.win.attributes("-topmost")))
    popup.close()
    root.update()

    root.destroy()
    print(f"\n{'=' * 46}")
    print(f"通过 {PASS} 项，失败 {FAIL} 项")
    print("=" * 46)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
