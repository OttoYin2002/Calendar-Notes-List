# -*- coding: utf-8 -*-
"""
全局字体与排版规范。

设计原则
--------
1. **同层级用同一字号** —— 界面里的"标题"看起来必须像一组，
   "说明文字"也必须像一组，而不是随手写 7/8/9/10 混用。
2. **只允许通过本模块取字号**，业务代码不再出现魔法数字。
3. 字号档位随 DPI 自动缩放（见 app/dpi.py）。

字号档位
--------
    DISPLAY  17  统计大数字等强视觉元素
    H1       14  弹窗主标题、区块大标题
    H2       11  侧边栏区块标题、LabelFrame 标题
    H3       10  次级小标题
    BODY     10  正文
    SMALL     9  辅助说明、提示文字
    CAPTION   8  极小标注（时间戳、角标）

行距 / 留白
----------
    LINE_GAP     正文字号对应的行距倍数（用于 Text 组件）
    SECTION_GAP  区块之间的垂直间距
    ITEM_GAP     区块内条目之间的间距
"""

from __future__ import annotations

from typing import Tuple

# ---------------------------------------------------------------- 字体族 ----
FONT_FAMILY = "Microsoft YaHei UI"
FONT_FAMILY_MONO = "Consolas"

# ------------------------------------------------------------ 字号档位 ----
# 基准字号（未缩放）
_SIZES = {
    "DISPLAY": 17,
    "H1": 14,
    "H2": 11,
    "H3": 10,
    "BODY": 10,
    "SMALL": 9,
    "CAPTION": 8,
}

# ------------------------------------------------------------- 间距常量 ----
SECTION_GAP = 10      # 区块之间
ITEM_GAP = 4          # 区块内条目之间
LINE_GAP = 1.35       # 正文行距倍数
LINE_GAP_TIGHT = 1.15  # 密集列表行距倍数

# 控件内边距
PAD_X = 10
PAD_Y = 6


def _scale() -> float:
    """当前 DPI 缩放系数。"""
    try:
        from ..dpi import get_scale
        return get_scale()
    except Exception:
        return 1.0


def size(name: str) -> int:
    """按档位名取缩放后的字号。"""
    base = _SIZES.get(name.upper())
    if base is None:
        raise KeyError(f"未知字号档位：{name}（可用：{', '.join(_SIZES)}）")
    return max(7, int(round(base * _scale())))


def font(name: str, weight: str = "normal") -> Tuple[str, int, str]:
    """
    取字体元组，直接传给 Tk 的 font= 参数。

    :param name:   字号档位名
    :param weight: "normal" / "bold"
    """
    return (FONT_FAMILY, size(name), weight)


def font_mono(name: str = "BODY", weight: str = "normal") -> Tuple[str, int, str]:
    """等宽字体（用于时间、代码等需要对齐的场景）。"""
    return (FONT_FAMILY_MONO, size(name), weight)


# 便捷别名（语义化命名，调用处可读性更好）
def display(weight: str = "bold") -> Tuple[str, int, str]:
    return font("DISPLAY", weight)


def h1(weight: str = "bold") -> Tuple[str, int, str]:
    return font("H1", weight)


def h2(weight: str = "bold") -> Tuple[str, int, str]:
    return font("H2", weight)


def h3(weight: str = "bold") -> Tuple[str, int, str]:
    return font("H3", weight)


def body(weight: str = "normal") -> Tuple[str, int, str]:
    return font("BODY", weight)


def small(weight: str = "normal") -> Tuple[str, int, str]:
    return font("SMALL", weight)


def caption(weight: str = "normal") -> Tuple[str, int, str]:
    return font("CAPTION", weight)


def overstrike(base: Tuple[str, int, str]) -> Tuple[str, int, str]:
    """给字体加删除线（待办完成态）。"""
    return (base[0], base[1], base[2] + " overstrike")


# ------------------------------------------------------------ 分组容器 ----

def group_frame(parent, theme: dict, text: str, **kwargs):
    """
    创建统一样式的 LabelFrame（分组容器）。

    统一三件事，保证界面上的"分组框"看起来是一套：
      1) 标题字号一致（H2）
      2) 标题靠左上（labelanchor="nw"），符合现代 UI 习惯
      3) 内边距一致，内部元素不会贴着边框
    """
    import tkinter as tk
    return tk.LabelFrame(
        parent,
        text=text,
        bg=theme.get("panel", theme.get("bg", "#FFFFFF")),
        fg=theme.get("text", "#1A2333"),
        font=h2(),
        bd=1,
        relief="flat",
        highlightthickness=0,
        labelanchor="nw",
        padx=8,
        pady=6,
        **kwargs,
    )
