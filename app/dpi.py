# -*- coding: utf-8 -*-
"""
Windows 高 DPI 感知与界面缩放。

问题背景
--------
Tkinter 默认是 "DPI unaware" 进程，Windows 会把整个窗口位图拉伸到目标分辨率，
在 125% / 150% 缩放的屏幕上表现为「界面模糊、发虚」。

解决思路
--------
1. 在创建 Tk 根窗口 **之前** 调用 Win32 API 把进程标记为 Per-Monitor DPI Aware，
   这样 Windows 不再拉伸位图，交给应用自己按真实像素绘制。
2. 读取屏幕实际 DPI，计算缩放系数。
3. Tk 的 `tk scaling` 设为 dpi/72，让以「磅」为单位的字体自动变大。
4. 窗口初始尺寸按屏幕工作区比例计算，避免超出屏幕或过小。

同时提供：
  - scale_font()  —— 统一的字体构造（自动应用缩放）
  - fit_to_screen() —— 按屏幕工作区计算合适的窗口尺寸
"""

from __future__ import annotations

import ctypes
import sys
from typing import Optional, Tuple

IS_WINDOWS = sys.platform.startswith("win")

# 缩放系数（1.0 = 100%）
_dpi_scale: float = 1.0
_dpi_awareness_set: bool = False


# ------------------------------------------------------------ DPI 感知 ----

def enable_dpi_awareness() -> bool:
    """
    声明进程为 Per-Monitor DPI Aware。

    必须在创建任何 Tk 窗口之前调用，否则设置不生效。

    返回是否成功设置。
    """
    global _dpi_awareness_set
    if _dpi_awareness_set:
        return True
    if not IS_WINDOWS:
        _dpi_awareness_set = True
        return True
    try:
        # Windows 10 1703+ : Per-Monitor V2（最完整）
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
            _dpi_awareness_set = True
            return True
        except Exception:
            pass
        # Windows 8.1+ : Per-Monitor
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            _dpi_awareness_set = True
            return True
        except Exception:
            pass
        # Vista+ : System DPI Aware
        try:
            ctypes.windll.user32.SetProcessDPIAware()
            _dpi_awareness_set = True
            return True
        except Exception:
            pass
    except Exception as exc:
        print(f"[dpi] 设置 DPI 感知失败：{exc}")
    _dpi_awareness_set = True
    return False


def get_dpi() -> int:
    """获取主显示器的实际 DPI（默认 96）。"""
    if not IS_WINDOWS:
        return 96
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return dpi if dpi > 0 else 96
    except Exception:
        return 96


def init_dpi_scaling(root=None) -> float:
    """
    初始化 DPI 缩放。

    传入 root（Tk 实例）时会同步设置 Tk 的 scaling，
    使以「磅」为单位的字体随 DPI 自动放大。

    返回缩放系数（1.0 = 100%）。
    """
    global _dpi_scale
    dpi = get_dpi()
    _dpi_scale = dpi / 96.0
    # 限制极端值，避免极端缩放破坏布局
    _dpi_scale = max(1.0, min(_dpi_scale, 3.0))
    if root is not None:
        try:
            root.tk.call("tk", "scaling", dpi / 72.0)
        except Exception:
            pass
    return _dpi_scale


def get_scale() -> float:
    """获取当前缩放系数。"""
    return _dpi_scale


def scale(value: float) -> float:
    """把设计稿像素值按缩放系数换算。"""
    return value * _dpi_scale


def scale_int(value: int) -> int:
    """把设计稿像素值按缩放系数换算为整数。"""
    return int(round(value * _dpi_scale))


# ------------------------------------------------------------ 字体 ----

# 项目统一使用的字体族（Windows 自带）
FONT_FAMILY = "Microsoft YaHei UI"
# 数字/等宽场景（如时间刻度）
FONT_FAMILY_NUM = "Consolas"


def scale_font(size: int, weight: str = "normal", family: str = FONT_FAMILY,
               italic: bool = False) -> Tuple[str, int, str]:
    """
    构造随 DPI 缩放的字体元组。

    :param size:   设计稿字号（磅），会按 DPI 缩放
    :param weight: "normal" / "bold"
    :param family: 字体族
    """
    scaled = max(7, int(round(size * _dpi_scale)))
    if weight == "bold":
        return (family, scaled, "bold")
    if italic:
        return (family, scaled, "italic")
    return (family, scaled, "normal")


def font(size: int, weight: str = "normal", family: str = FONT_FAMILY,
         italic: bool = False) -> Tuple[str, int, str]:
    """scale_font 的别名，调用处更简洁。"""
    return scale_font(size, weight, family, italic)


# ------------------------------------------------------------ 窗口尺寸 ----

def fit_to_screen(root, prefer_width: int, prefer_height: int,
                  min_width: int, min_height: int) -> Tuple[int, int]:
    """
    按屏幕工作区计算合适的窗口尺寸。

    规则：
      - 不超过工作区的 92%（留出边距）
      - 不小于最小尺寸
      - 尽量使用期望尺寸
    """
    try:
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
    except Exception:
        return (prefer_width, prefer_height)

    max_w = int(screen_w * 0.92)
    max_h = int(screen_h * 0.90)

    w = min(prefer_width, max_w)
    h = min(prefer_height, max_h)
    w = max(w, min(min_width, max_w))
    h = max(h, min(min_height, max_h))
    return (w, h)


def get_work_area(root) -> Tuple[int, int, int, int]:
    """
    获取屏幕工作区（排除任务栏）的尺寸。

    返回 (宽, 高, 左, 上)。非 Windows 或获取失败时返回整屏尺寸。
    """
    try:
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
    except Exception:
        return (1920, 1080, 0, 0)
    if not IS_WINDOWS:
        return (sw, sh, 0, 0)
    try:
        SPI_GETWORKAREA = 0x0030
        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
        rect = RECT()
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w > 0 and h > 0:
            return (w, h, rect.left, rect.top)
    except Exception:
        pass
    return (sw, sh, 0, 0)
