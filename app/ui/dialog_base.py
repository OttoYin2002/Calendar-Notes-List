# -*- coding: utf-8 -*-
"""
弹窗基类 —— 统一解决 Tkinter 模态弹窗的三个经典坑。

坑 1：grab_set() 调用过早
    在窗口内容还没构建时就 grab，会 grab 到一个空窗口，
    表现为「屏幕被锁死，只在左上角闪一个输入框」。
    正确做法：先构建完内容、窗口显示出来之后再 grab。

坑 2：update_idletasks() 算不准窗口尺寸
    仅调用 update_idletasks() 时，复杂布局（grid + LabelFrame + Text）
    的请求尺寸可能尚未计算完成，导致 geometry() 把窗口压成极小的一条。
    正确做法：先 update() 让布局真正完成，再取 winfo_reqwidth/reqheight，
    并设置一个合理的最小尺寸兜底。

坑 3：居中时主窗口尚未显示
    主窗口刚创建时 winfo_rootx()/winfo_width() 返回 0/1，
    会把弹窗定位到屏幕左上角。
    正确做法：主窗口不可用时退回屏幕中心。

本模块提供 ModalDialog 基类，所有子弹窗继承它即可。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional

# 弹窗最小可用尺寸（防止被压扁）
MIN_DIALOG_WIDTH = 380
MIN_DIALOG_HEIGHT = 220


class ModalDialog:
    """
    安全的模态弹窗基类。

    使用方式：
        class MyDialog(ModalDialog):
            def __init__(self, master, theme_name):
                super().__init__(master, theme_name, "我的弹窗")
                self._build_body(self.body)
                self._finalize()      # 构建完成后调用，触发居中 + grab
    """

    def __init__(self, master: tk.Misc, theme_name: str, title: str,
                 min_width: int = MIN_DIALOG_WIDTH, min_height: int = MIN_DIALOG_HEIGHT,
                 resizable: bool = False, draggable: bool = True):
        from ..themes import get_theme

        self.master = master
        self.theme_name = theme_name
        self.theme = get_theme(theme_name)
        self.title = title
        self._min_width = min_width
        self._min_height = min_height
        self._grabbed = False
        self._drag_origin = None

        # 创建顶层窗口
        self.win = tk.Toplevel(master)
        self.win.title(title)
        self.win.configure(bg=self.theme["bg"])
        self.win.resizable(resizable, resizable)
        self.win.transient(master)

        # 主体容器（子类往里填内容）
        self.body = tk.Frame(self.win, bg=self.theme["bg"])
        self.body.pack(fill="both", expand=True, padx=18, pady=16)

        # ESC 关闭 + 关闭按钮协议
        self.win.bind("<Escape>", lambda e: self.on_cancel())
        self.win.protocol("WM_DELETE_WINDOW", self.on_cancel)

        if draggable:
            self._enable_drag()

    # ------------------------------------------------------------ 拖动 ----
    def _enable_drag(self) -> None:
        """
        让弹窗可以通过标题栏拖动。

        重要：拖拽**不能抢走输入控件的鼠标事件** —— 否则在 Entry / Text 里
        拖动鼠标选择文本时，整个窗口会跟着移动，文本无法被选中。
        解决方式：在拖拽起点判断事件是否发生在输入类控件上，
        若是则不启动拖拽，把事件交还给输入框正常处理。
        """
        self.win.bind("<ButtonPress-1>", self._on_drag_start, add="+")
        self.win.bind("<B1-Motion>", self._on_drag_move, add="+")
        self.win.bind("<ButtonRelease-1>", self._on_drag_end, add="+")

    @staticmethod
    def _is_input_widget(widget) -> bool:
        """
        判断事件源是否是输入类控件（Entry / Text / Combobox / Spinbox）。

        这类控件上的鼠标拖拽属于"选择文本"操作，不能被当成拖动窗口。
        """
        try:
            # 向上回溯父级：事件可能发生在输入框内部的某个子元素上
            w = widget
            for _ in range(6):
                if w is None:
                    break
                if isinstance(w, (ttk.Entry, ttk.Combobox, ttk.Spinbox, tk.Entry,
                                  tk.Text, tk.Listbox)):
                    return True
                # ttk 的输入控件是 TtkEntry / TtkCombobox 等内部类
                cls_name = w.__class__.__name__.lower()
                if any(k in cls_name for k in ("entry", "combobox", "spinbox", "text")):
                    return True
                w = getattr(w, "master", None)
        except Exception:
            pass
        return False

    def _on_drag_start(self, event) -> None:
        """记录拖动起点（输入类控件上不启动拖拽）。"""
        try:
            if self._is_input_widget(getattr(event, "widget", None)):
                self._drag_origin = None
                return
            self._drag_origin = (event.x_root, event.y_root,
                                 self.win.winfo_x(), self.win.winfo_y())
        except Exception:
            self._drag_origin = None

    def _on_drag_move(self, event) -> None:
        """移动窗口。"""
        if not self._drag_origin:
            return
        try:
            x0, y0, win_x, win_y = self._drag_origin
            self.win.geometry(f"+{win_x + (event.x_root - x0)}+{win_y + (event.y_root - y0)}")
        except Exception:
            pass

    def _on_drag_end(self, _event=None) -> None:
        """结束拖动。"""
        self._drag_origin = None

    # ------------------------------------------------------------ 构建流程 ----
    def _finalize(self) -> None:
        """
        子类构建完内容后调用：
        1) 让布局真正完成
        2) 居中显示
        3) 最后才 grab（避免锁死）
        """
        self.win.update_idletasks()
        self.win.update()          # 关键：确保几何计算完成
        # 先显示再定位：Toplevel 在被 withdraw 的主窗口下会继承隐藏状态
        try:
            if self.win.state() != "normal":
                self.win.deiconify()
        except Exception:
            pass
        self.win.update_idletasks()
        self.center_on_screen()
        self.win.lift()
        # 窗口映射后再次校正位置：Tk 在 deiconify 时可能按初始 geometry 重置，
        # 导致弹窗又落回左上角。
        self.center_on_screen()
        self._apply_grab()

    def _apply_grab(self) -> None:
        """窗口已可见后再 grab，确保不会锁死成空窗口。"""
        try:
            self.win.grab_set()
            self._grabbed = True
        except Exception:
            # grab 失败时降级为普通窗口，功能不受影响
            self._grabbed = False

    def center_on_screen(self) -> None:
        """
        把窗口居中显示。

        优先相对主窗口居中；主窗口位置不可用时退回屏幕中心。
        """
        try:
            self.win.update_idletasks()
            # 主窗口被 withdraw 时，Toplevel 会继承 withdrawn 状态而无法显示。
            # 这里强制恢复为 normal，确保弹窗可见。
            try:
                if self.win.state() != "normal":
                    self.win.deiconify()
            except Exception:
                pass
            w = self.win.winfo_reqwidth()
            h = self.win.winfo_reqheight()
            # 尺寸兜底：防止布局异常导致窗口过小
            w = max(w, self._min_width)
            h = max(h, self._min_height)

            screen_w = self.win.winfo_screenwidth()
            screen_h = self.win.winfo_screenheight()

            # 尝试相对主窗口居中
            try:
                mw = self.master.winfo_width()
                mh = self.master.winfo_height()
                mx = self.master.winfo_rootx()
                my = self.master.winfo_rooty()
                if mw > 10 and mh > 10 and mx >= 0:
                    x = mx + (mw - w) // 2
                    y = my + (mh - h) // 3
                else:
                    raise ValueError("主窗口几何不可用")
            except Exception:
                # 主窗口尚未显示 -> 屏幕居中
                x = (screen_w - w) // 2
                y = (screen_h - h) // 2

            # 约束在屏幕可见范围内
            x = max(0, min(x, screen_w - w))
            y = max(0, min(y, screen_h - h))
            self.win.geometry(f"{w}x{h}+{x}+{y}")
        except Exception as exc:
            print(f"[dialog] 居中失败：{exc}")

    # ------------------------------------------------------------ 行为 ----
    def on_cancel(self) -> None:
        """默认取消行为：关闭弹窗。子类可覆盖。"""
        self.close()

    def close(self) -> None:
        """安全关闭（先释放 grab 再销毁）。"""
        try:
            if self._grabbed:
                self.win.grab_release()
                self._grabbed = False
        except Exception:
            pass
        try:
            self.win.destroy()
        except Exception:
            pass
