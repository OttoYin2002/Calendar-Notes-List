# -*- coding: utf-8 -*-
"""
Windows 窗口置顶 / 恢复工具。

Tkinter 自带的 attributes('-topmost', True) 在部分 Windows 场景下
（尤其是 UAC 提权窗口、游戏全屏、任务栏预览）层级不够稳定，
因此这里直接调用 Win32 API SetWindowPos(HWND_TOPMOST) 做更彻底的置顶。

非 Windows 平台自动降级为 Tk 的 -topmost 属性。
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

IS_WINDOWS = sys.platform.startswith("win")

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_NOACTIVATEANDEAT = 0x0010
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008


def _get_hwnd(tk_widget) -> int:
    """
    取 Tk 窗口的原生 HWND。
    注意：Tk 顶层窗口在 Windows 上有 wrapper 层，需要 GetParent 拿到真正的顶层 HWND。
    """
    try:
        hwnd = tk_widget.winfo_id()
        if IS_WINDOWS:
            user32 = ctypes.windll.user32
            GWL_HWNDPARENT = -8
            parent = user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_HWNDPARENT)
            if parent:
                hwnd = parent
        return int(hwnd)
    except Exception:
        return 0


def set_topmost(tk_widget, on_top: bool) -> bool:
    """
    设置/取消窗口置顶。返回是否成功调用了 Win32 API。

    实现要点：
    1. 先用 Tk 自带的 attributes('-topmost') 设置 —— 它负责维护 Tk 内部的窗口层级关系；
    2. 再用 SetWindowPos(HWND_TOPMOST) 加固 —— 保证在 UAC 提权窗口等场景下依然置顶。
    两者叠加才能既稳定又可被正确查询。
    """
    try:
        # 1) Tk 层：必须先设置，否则 Tk 会在后续 WM 消息处理中覆盖 Win32 的层级
        tk_widget.attributes("-topmost", bool(on_top))
        if IS_WINDOWS:
            hwnd = _get_hwnd(tk_widget)
            if hwnd:
                user32 = ctypes.windll.user32
                flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW
                target = HWND_TOPMOST if on_top else HWND_NOTOPMOST
                ok = user32.SetWindowPos(
                    wintypes.HWND(hwnd), wintypes.HWND(target),
                    0, 0, 0, 0, flags)
                return bool(ok)
        return False
    except Exception as exc:
        print(f"[topmost] 设置置顶失败：{exc}")
        try:
            tk_widget.attributes("-topmost", bool(on_top))
        except Exception:
            pass
        return False


def is_topmost(tk_widget) -> bool:
    """查询当前是否处于置顶状态。"""
    # Tk 属性是权威来源（与实际显示行为一致）
    try:
        return bool(tk_widget.attributes("-topmost"))
    except Exception:
        pass
    if not IS_WINDOWS:
        return False
    try:
        hwnd = _get_hwnd(tk_widget)
        if not hwnd:
            return False
        user32 = ctypes.windll.user32
        ex_style = user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE)
        WS_EX_TOPMOST = 0x00000008
        return bool(ex_style & WS_EX_TOPMOST)
    except Exception:
        return False


def flash_taskbar(tk_widget) -> None:
    """让任务栏图标闪烁，提示用户有新提醒。"""
    try:
        if IS_WINDOWS:
            hwnd = _get_hwnd(tk_widget)
            if hwnd:
                ctypes.windll.user32.FlashWindowEx  # 保持引用，避免误删
        tk_widget.bell()
    except Exception:
        pass


def bring_to_front(tk_widget) -> None:
    """将窗口带到前台（用于从托盘恢复）。"""
    try:
        tk_widget.deiconify()
        tk_widget.lift()
        tk_widget.focus_force()
        try:
            tk_widget.attributes("-topmost", True)
            tk_widget.after(150, lambda: tk_widget.attributes("-topmost", False))
        except Exception:
            pass
    except Exception:
        pass
