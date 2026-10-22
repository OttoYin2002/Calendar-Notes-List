# -*- coding: utf-8 -*-
"""
日程备忘 —— 程序入口。

运行：
    python main.py

打包（Windows）：
    pyinstaller -F -w --name 日程备忘 main.py
"""

from __future__ import annotations

import sys
import traceback
from tkinter import messagebox


def _excepthook(exc_type, exc_value, exc_tb) -> None:
    """全局异常处理：弹出可读的错误提示，避免静默崩溃。"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    detail = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    print(detail)
    try:
        messagebox.showerror("程序错误",
                             f"发生未处理的错误：\n\n{exc_value}\n\n"
                             f"详细信息已输出到控制台。\n您的数据不会丢失。")
    except Exception:
        pass


def main() -> int:
    # 确保能以源码方式导入 app 包
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    # 关键：必须在创建 Tk 根窗口之前声明 DPI 感知，
    # 否则 Windows 会把窗口位图拉伸，界面在高分屏上会模糊。
    from app.dpi import enable_dpi_awareness
    enable_dpi_awareness()

    import tkinter as tk
    from app.config import APP_NAME, DATA_DIR
    from app.storage import Storage
    from app.ui.main_window import MainWindow

    root = tk.Tk()
    # 任务栏图标（使用 tkinter 自带图标，Windows 下会显示默认 Python 图标）
    try:
        root.iconname(APP_NAME)
    except Exception:
        pass

    storage = Storage()
    app = MainWindow(root, storage)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.excepthook = _excepthook
    sys.exit(main())
