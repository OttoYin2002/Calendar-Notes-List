# -*- coding: utf-8 -*-
"""
主题（浅色 / 深色）定义与 ttk 样式应用。

配色遵循简洁的商务研报风格：
  浅色 —— 纯白底 + 深蓝主色 #00489D
  深色 —— 深灰底 + 亮蓝强调色
"""

from __future__ import annotations

from typing import Dict

from .config import THEME_DARK, THEME_LIGHT
from .ui import typography

LIGHT: Dict[str, str] = {
    "name": "浅色",
    "bg": "#FFFFFF",
    "bg_alt": "#F4F6F9",
    "panel": "#FAFBFD",
    "border": "#D9E0E8",
    "text": "#1A2333",
    "text_dim": "#6B7A8D",
    "primary": "#00489D",
    "primary_hover": "#003C86",
    "primary_light": "#E8F0FA",
    "on_primary": "#FFFFFF",
    "danger": "#C62828",
    "danger_hover": "#A81F1F",
    "success": "#2E7D32",
    "warn": "#B8860B",
    "tag_default": "#5B7FA6",
    "holiday": "#FDECEA",
    "holiday_text": "#C62828",
    "weekend": "#F7F9FB",
    "today": "#DCE9F8",
    "today_border": "#00489D",
    "weekend_text": "#9AA7B5",
    "sel": "#CCE0F5",
    "canvas": "#FFFFFF",
    "grid": "#E3E8EE",
    "grid_strong": "#C7D0DA",
    "hover": "#EDF3FA",
    "entry_bg": "#FFFFFF",
    "entry_text": "#1A2333",
    "muted": "#EDF1F6",
    "shadow": "#C9D4E0",
}

DARK: Dict[str, str] = {
    "name": "深色",
    "bg": "#1E2430",
    "bg_alt": "#252C3A",
    "panel": "#222936",
    "border": "#39424F",
    "text": "#E6EBF2",
    "text_dim": "#93A0B3",
    "primary": "#4A9EE8",
    "primary_hover": "#63B0F0",
    "primary_light": "#2C3A4C",
    "on_primary": "#0E1621",
    "danger": "#EF5350",
    "danger_hover": "#F06A67",
    "success": "#66BB6A",
    "warn": "#E0A83C",
    "tag_default": "#7A96B8",
    "holiday": "#3A2A2C",
    "holiday_text": "#EF8A87",
    "weekend": "#232A37",
    "today": "#25364B",
    "today_border": "#4A9EE8",
    "weekend_text": "#7B8899",
    "sel": "#2F4763",
    "canvas": "#1B212C",
    "grid": "#2C3441",
    "grid_strong": "#3C4655",
    "hover": "#2A3442",
    "entry_bg": "#232A37",
    "entry_text": "#E6EBF2",
    "muted": "#2A3240",
    "shadow": "#10151D",
}

THEMES: Dict[str, Dict[str, str]] = {
    THEME_LIGHT: LIGHT,
    THEME_DARK: DARK,
}


def get_theme(name: str) -> Dict[str, str]:
    return THEMES.get(name, LIGHT)


def is_dark(name: str) -> bool:
    return name == THEME_DARK


def apply_ttk_styles(root, theme: Dict[str, str]) -> None:
    """把主题应用到 ttk 控件（Style 需要在 root 之后创建）。"""
    from tkinter import ttk

    style = ttk.Style(root)
    try:
        style.theme_use("clam")  # clam 允许完全自定义颜色
    except Exception:
        pass

    style.configure(".", background=theme["bg"], foreground=theme["text"],
                    fieldbackground=theme["entry_bg"], bordercolor=theme["border"],
                    lightcolor=theme["bg"], darkcolor=theme["border"])

    style.configure("TFrame", background=theme["bg"])
    style.configure("Panel.TFrame", background=theme["panel"])
    style.configure("Toolbar.TFrame", background=theme["bg_alt"])

    style.configure("TLabel", background=theme["bg"], foreground=theme["text"])
    style.configure("Dim.TLabel", background=theme["bg"], foreground=theme["text_dim"])
    style.configure("PanelDim.TLabel", background=theme["panel"], foreground=theme["text_dim"])
    style.configure("Title.TLabel", background=theme["bg"], foreground=theme["text"],
                    font=typography.display('bold'))
    style.configure("Section.TLabel", background=theme["bg"], foreground=theme["primary"],
                    font=typography.body('bold'))
    style.configure("PanelTitle.TLabel", background=theme["panel"], foreground=theme["primary"],
                    font=typography.body('bold'))

    style.configure("TButton", background=theme["bg_alt"], foreground=theme["text"],
                    borderwidth=1, focusthickness=0, padding=(10, 5))
    style.map("TButton",
              background=[("active", theme["hover"]), ("pressed", theme["border"])],
              foreground=[("disabled", theme["text_dim"])])

    style.configure("Primary.TButton", background=theme["primary"], foreground=theme["on_primary"],
                    borderwidth=0, padding=(12, 6), font=typography.small('bold'))
    style.map("Primary.TButton",
              background=[("active", theme["primary_hover"]), ("pressed", theme["primary_hover"])],
              foreground=[("active", theme["on_primary"])])

    style.configure("Danger.TButton", background=theme["danger"], foreground="#FFFFFF",
                    borderwidth=0, padding=(10, 5))
    style.map("Danger.TButton",
              background=[("active", theme["danger_hover"]), ("pressed", theme["danger_hover"])])

    style.configure("Ghost.TButton", background=theme["bg"], foreground=theme["text_dim"],
                    borderwidth=0, padding=(6, 3))
    style.map("Ghost.TButton",
              background=[("active", theme["hover"])],
              foreground=[("active", theme["text"])])

    style.configure("TCheckbutton", background=theme["bg"], foreground=theme["text"],
                    focusthickness=0)
    style.map("TCheckbutton", background=[("active", theme["bg"])])

    style.configure("TRadiobutton", background=theme["bg"], foreground=theme["text"],
                    focusthickness=0)
    style.map("TRadiobutton", background=[("active", theme["bg"])])

    style.configure("TEntry", fieldbackground=theme["entry_bg"], foreground=theme["entry_text"],
                    bordercolor=theme["border"], insertcolor=theme["text"],
                    lightcolor=theme["border"], darkcolor=theme["border"])
    style.map("TEntry", bordercolor=[("focus", theme["primary"])],
              lightcolor=[("focus", theme["primary"])], darkcolor=[("focus", theme["primary"])])

    style.configure("TCombobox", fieldbackground=theme["entry_bg"], background=theme["entry_bg"],
                    foreground=theme["entry_text"], arrowcolor=theme["text_dim"],
                    bordercolor=theme["border"], selectbackground=theme["primary"],
                    selectforeground=theme["on_primary"])
    style.map("TCombobox", fieldbackground=[("readonly", theme["entry_bg"])],
              foreground=[("readonly", theme["entry_text"])],
              bordercolor=[("focus", theme["primary"])],
              arrowcolor=[("active", theme["primary"])])

    style.configure("TNotebook", background=theme["bg"], borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure("TNotebook.Tab", background=theme["bg_alt"], foreground=theme["text_dim"],
                    padding=(12, 6), borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", theme["bg"])],
              foreground=[("selected", theme["primary"])])

    style.configure("TProgressbar", background=theme["primary"], troughcolor=theme["muted"],
                    bordercolor=theme["muted"], lightcolor=theme["primary"],
                    darkcolor=theme["primary"])

    style.configure("TSeparator", background=theme["border"])

    style.configure("Treeview", background=theme["bg"], fieldbackground=theme["bg"],
                    foreground=theme["text"], borderwidth=0, rowheight=26)
    style.map("Treeview", background=[("selected", theme["sel"])],
              foreground=[("selected", theme["text"])])
    style.configure("Treeview.Heading", background=theme["bg_alt"], foreground=theme["text_dim"],
                    borderwidth=0, relief="flat", font=typography.small('bold'))
    style.map("Treeview.Heading", background=[("active", theme["hover"])])

    style.configure("TScrollbar", background=theme["muted"], troughcolor=theme["bg_alt"],
                    bordercolor=theme["bg_alt"], arrowcolor=theme["text_dim"],
                    lightcolor=theme["muted"], darkcolor=theme["muted"])
    style.map("TScrollbar", background=[("active", theme["border"])])

    style.configure("TMenubutton", background=theme["bg_alt"], foreground=theme["text"],
                    borderwidth=1, arrowcolor=theme["text_dim"], padding=(8, 4))
    style.map("TMenubutton", background=[("active", theme["hover"])])
