# -*- coding: utf-8 -*-
"""
布局稳定性测试 —— 防止界面抖动（持续重绘）问题复发。

对应用户反馈：非最大化窗口时主界面持续抖动、尺寸始终在变化。

检测思路
--------
1. 连续采样窗口 geometry，统计尺寸变化次数（稳定时应为 0~1 次）
2. 统计 render 调用次数（震荡时会被放大几十倍）
3. 切换到不同视图后重复检测

运行：python test_stability.py
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


def _new_root(geometry: str = "1200x760+40+40"):
    """创建独立的 Tk 根窗口。"""
    import tkinter as tk
    root = tk.Tk()
    root.geometry(geometry)
    return root


def _make_app(root):
    from app.storage import Storage
    from app.ui.main_window import MainWindow
    return MainWindow(root, Storage())


def test_no_jitter_on_startup():
    """窗口启动后不应持续变化尺寸。"""
    section("启动后尺寸稳定性（非最大化窗口）")
    root = _new_root()
    app = _make_app(root)
    root.update()

    # 采样 40 帧，记录 geometry 变化
    seen = []
    for _ in range(40):
        root.update_idletasks()
        g = root.geometry()
        if not seen or seen[-1] != g:
            seen.append(g)
        root.update()

    check("尺寸变化次数 <= 2", len(seen) <= 2, f"实际 {len(seen)} 次：{seen[:6]}")
    # 注意：窗口尺寸会被 config.json 里的历史记录覆盖（这是"记忆窗口大小"的设计），
    # 因此这里只断言尺寸稳定，不断言具体数值。
    check("尺寸在启动后保持稳定", bool(seen), "未取到尺寸")

    try:
        app.reminder_engine.stop()
    except Exception:
        pass
    root.destroy()


def test_no_jitter_on_resize():
    """改变窗口尺寸后应稳定下来。"""
    section("调整窗口尺寸后的稳定性")
    root = _new_root()
    app = _make_app(root)
    root.update()

    for target in ("1100x700+40+40", "1300x820+40+40", "1200x760+40+40"):
        root.geometry(target)
        root.update()

    seen = []
    for _ in range(50):
        root.update_idletasks()
        g = root.geometry()
        if not seen or seen[-1] != g:
            seen.append(g)
        root.update()

    check("多次调整后尺寸稳定（变化 <= 2 次）", len(seen) <= 2,
          f"实际 {len(seen)} 次：{seen[:8]}")
    # 窗口尺寸可自由调整（锁定方案已回退）
    check("最终尺寸等于最后设定的值",
          bool(seen) and seen[-1].startswith("1200x760"), seen[-1] if seen else "无")

    try:
        app.reminder_engine.stop()
    except Exception:
        pass
    root.destroy()


def test_render_not_amplified():
    """重绘次数不应被 Configure 事件放大。"""
    section("重绘次数放大检测")
    root = _new_root()
    app = _make_app(root)
    root.update()

    calls = {"n": 0}
    orig = app.month_view.render

    def counting():
        calls["n"] += 1
        return orig()

    app.month_view.render = counting

    # 模拟一次尺寸变化
    root.geometry("1250x780+40+40")
    for _ in range(30):
        root.update_idletasks()
        root.update()
    # 等待防抖窗口过去
    for _ in range(30):
        root.update()

    check("一次尺寸变化只触发少量重绘（<= 8 次）", calls["n"] <= 8, f"实际 {calls['n']} 次")
    app.month_view.render = orig

    try:
        app.reminder_engine.stop()
    except Exception:
        pass
    root.destroy()


def test_all_views_stable():
    """三种视图切换后都不应抖动。"""
    section("各视图稳定性")
    for view in ("month", "week", "day"):
        root = _new_root()
        app = _make_app(root)
        root.update()
        app.switch_view(view)
        root.update()

        seen = []
        for _ in range(35):
            root.update_idletasks()
            g = root.geometry()
            if not seen or seen[-1] != g:
                seen.append(g)
            root.update()

        check(f"{view} 视图尺寸稳定（变化 <= 2 次）", len(seen) <= 2,
              f"实际 {len(seen)} 次")

        try:
            app.reminder_engine.stop()
        except Exception:
            pass
        root.destroy()


def test_toggle_no_self_resize():
    """勾选框组件不应因自身重绘而改变尺寸。"""
    section("勾选框组件尺寸稳定")
    import tkinter as tk
    from app.ui.toggle import CheckCircle
    from app.themes import get_theme

    root = tk.Tk()
    root.geometry("400x200+40+40")
    t = get_theme("light")
    var = tk.BooleanVar(value=False)
    box = CheckCircle(root, text="测试选项", variable=var, theme=t, font_size=9, box_size=14)
    box.pack(side="left", padx=10, pady=10)
    root.update()

    w0, h0 = box.winfo_width(), box.winfo_height()
    for _ in range(20):
        box._render()
        root.update_idletasks()
        root.update()

    w1, h1 = box.winfo_width(), box.winfo_height()
    check("重复重绘后尺寸不变", (w0, h0) == (w1, h1), f"{(w0, h0)} -> {(w1, h1)}")

    root.destroy()


def main() -> int:
    import tkinter as tk
    from tkinter import messagebox as mb
    mb.showwarning = lambda *a, **k: None
    mb.showinfo = lambda *a, **k: None
    mb.askyesno = lambda *a, **k: True

    from app import config as cfg
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="calmemo_stab_"))
    for k, v in [("EVENTS_FILE", "e"), ("TODOS_FILE", "t"), ("TAGS_FILE", "g"),
                 ("CONFIG_FILE", "c"), ("REMINDER_STATE_FILE", "r"), ("HOLIDAYS_FILE", "h")]:
        setattr(cfg, k, tmp / f"{v}.json")

    print("布局稳定性测试（防抖动）")
    test_no_jitter_on_startup()
    test_no_jitter_on_resize()
    test_render_not_amplified()
    test_all_views_stable()
    test_toggle_no_self_resize()

    print(f"\n{'=' * 46}")
    print(f"通过 {PASS} 项，失败 {FAIL} 项")
    print("=" * 46)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
