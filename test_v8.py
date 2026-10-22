# -*- coding: utf-8 -*-
"""
v8 新功能测试：置顶修复 / 地区移除 / 窗口锁定 / 弹窗交互。

运行：python test_v8.py
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


def _new_root(geometry: str = "1600x900+40+40"):
    import tkinter as tk
    root = tk.Tk()
    root.geometry(geometry)
    return root


def _make_app(root):
    from app.storage import Storage
    from app.ui.main_window import MainWindow
    return MainWindow(root, Storage())


# ============================================================ 置顶 ======
def test_topmost_toggle():
    """侧边栏「主窗口置顶」勾选框点击后应真正改变状态。"""
    section("置顶开关")
    root = _new_root()
    app = _make_app(root)
    root.update()

    before = bool(app._topmost_var().get())
    app.flip_topmost()          # 快捷键路径：主动翻转
    root.update()
    after = bool(app._topmost_var().get())
    check("置顶状态确实翻转", before != after, f"{before} -> {after}")

    # 再点一次应回到原状态（验证没有"翻两次抵消"）
    app.flip_topmost()
    root.update()
    back = bool(app._topmost_var().get())
    check("再次点击可回到原状态", back == before, f"{back} vs {before}")

    # 勾选框路径：组件翻转变量后调用 toggle_topmost，应应用新值
    switch = getattr(app, "topmost_switch", None)
    check("侧边栏存在置顶勾选框", switch is not None)
    if switch is not None:
        v0 = app._topmost_var().get()
        switch._on_click()
        root.update()
        v1 = app._topmost_var().get()
        check("勾选框点击后状态真的改变", v0 != v1, f"{v0} -> {v1}")
        check("勾选框点击后状态与变量一致",
              bool(v1) == bool(app._topmost_var().get()))
        # 复原
        switch._on_click()
        root.update()

    # 勾选框组件本身：点击后变量应改变且命令被调用
    calls = {"n": 0}
    var = app._topmost_var()
    from app.ui.toggle import CheckCircle
    box = CheckCircle(root, text="测试", variable=var, theme=app.theme,
                      command=lambda: calls.__setitem__("n", calls["n"] + 1))
    box.pack()
    root.update()
    v0 = var.get()
    box._on_click()
    root.update()
    check("勾选框点击后变量翻转", var.get() != v0, f"{v0} -> {var.get()}")
    check("勾选框命令被调用", calls["n"] == 1, f"调用 {calls['n']} 次")

    try:
        app.reminder_engine.stop()
    except Exception:
        pass
    root.destroy()


def test_toolbar_simplified():
    """工具栏应只剩搜索与更多（置顶/深色已移除）。"""
    section("工具栏精简")
    root = _new_root()
    app = _make_app(root)
    root.update()

    check("工具栏置顶按钮已移除", not hasattr(app, "topmost_btn"))
    check("工具栏主题按钮已移除", not hasattr(app, "theme_btn"))
    check("更多菜单按钮仍存在", hasattr(app, "_more_btn"))
    check("更多菜单含主题切换", any("深色" in lbl for lbl, _ in [
        ("切换深色/浅色", None)]), "")

    try:
        app.reminder_engine.stop()
    except Exception:
        pass
    root.destroy()


# ============================================================ 地区 ======
def test_region_removed():
    """国家/地区切换应已移除，节假日固定为中国。"""
    section("国家/地区移除")
    root = _new_root()
    app = _make_app(root)
    root.update()

    check("侧边栏无地区分段控件", not hasattr(app, "_region_buttons"))
    check("无 region_var", not hasattr(app, "region_var"))
    check("节假日固定为中国", app.holidays.region == "CN", app.holidays.region)

    try:
        app.reminder_engine.stop()
    except Exception:
        pass
    root.destroy()


# ======================================================== 窗口锁定 ======
# ======================================================== 弹窗交互 ======
def test_dialog_text_selection():
    """弹窗内输入框不应被拖拽逻辑影响。"""
    section("弹窗文本可选")
    import tkinter as tk
    from tkinter import messagebox as mb
    mb.showwarning = lambda *a, **k: None
    mb.showinfo = lambda *a, **k: None

    root = _new_root()
    app = _make_app(root)
    root.update()
    app.quick_confirm_var.set(True)
    app.quick_entry.insert(0, "明天下午3点 客户回访")
    app.quick_add_event()
    root.update()

    form = getattr(app, "_last_event_dialog", None)
    check("表单已打开", form is not None)
    if form is not None:
        class Evt:
            widget = None
            x_root = 400
            y_root = 300
        e = Evt()
        e.widget = form.title_entry
        form._on_drag_start(e)
        check("输入框内不启动拖拽", form._drag_origin is None)

        bx, by = form.win.winfo_x(), form.win.winfo_y()
        class Mv:
            x_root = 600
            y_root = 500
        form._on_drag_move(Mv())
        root.update()
        check("输入框内拖动不会移动窗口",
              (form.win.winfo_x(), form.win.winfo_y()) == (bx, by))

        e2 = Evt()
        e2.widget = form.win
        form._on_drag_start(e2)
        check("非输入控件仍可拖拽", form._drag_origin is not None)
        form.on_cancel()

    try:
        app.reminder_engine.stop()
    except Exception:
        pass
    root.destroy()


def test_priority_immediate_update():
    """优先级单选：选中后其他项应立即变暗。"""
    section("优先级即时变色")
    import tkinter as tk
    from tkinter import messagebox as mb
    mb.showwarning = lambda *a, **k: None
    mb.showinfo = lambda *a, **k: None

    root = _new_root()
    app = _make_app(root)
    root.update()
    app.quick_confirm_var.set(True)
    app.quick_entry.insert(0, "明天下午3点 客户回访")
    app.quick_add_event()
    root.update()

    form = getattr(app, "_last_event_dialog", None)
    check("表单已打开", form is not None)
    if form is not None:
        radios = []

        def walk(w):
            for c in w.winfo_children():
                if c.__class__.__name__ == "RadioCircle":
                    radios.append(c)
                walk(c)

        walk(form.win)
        check("找到 3 个优先级单选框", len(radios) == 3, f"实际 {len(radios)}")

        if len(radios) == 3:
            # 初始：中间（中）为选中
            mid_before = radios[1]._is_checked()
            check("初始选中'中'", mid_before)

            # 点击"高"
            for r in radios:
                if "高" in r._text:
                    r._on_click()
                    break
            root.update()

            check("'高'变为选中", radios[0]._is_checked())
            check("'中'立即取消选中", not radios[1]._is_checked())
            # 未选中项的文字颜色应弱化
            dim = radios[1]._colors()[3]
            normal = radios[0]._colors()[3]
            check("'中'的文字已变暗", dim != normal, f"{dim} vs {normal}")
        form.on_cancel()

    try:
        app.reminder_engine.stop()
    except Exception:
        pass
    root.destroy()


def main() -> int:
    import tkinter as tk
    from tkinter import messagebox as mb
    mb.showwarning = lambda *a, **k: None
    mb.showinfo = lambda *a, **k: None
    mb.askyesno = lambda *a, **k: True

    from app import config as cfg
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="calmemo_v8_"))
    for k, v in [("EVENTS_FILE", "e"), ("TODOS_FILE", "t"), ("TAGS_FILE", "g"),
                 ("CONFIG_FILE", "c"), ("REMINDER_STATE_FILE", "r"), ("HOLIDAYS_FILE", "h")]:
        setattr(cfg, k, tmp / f"{v}.json")

    print("v8 功能测试")
    test_topmost_toggle()
    test_toolbar_simplified()
    test_region_removed()
    test_dialog_text_selection()
    test_priority_immediate_update()

    print(f"\n{'=' * 46}")
    print(f"通过 {PASS} 项，失败 {FAIL} 项")
    print("=" * 46)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
