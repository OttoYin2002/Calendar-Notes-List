# -*- coding: utf-8 -*-
"""
防抖（debounce）工具。

背景
----
Tkinter 的 ``<Configure>`` 事件在窗口/控件尺寸变化时**高频触发**。
若在回调里直接做重活（重绘大网格、重排布局、重新计算尺寸），
会��成两个典型问题：

  1. **卡顿** —— 一次拖拽可能产生上百次事件，每次都全量重绘
  2. **抖动** —— 重绘本身改变了控件请求尺寸，又触发新的 Configure，形成循环

Tkinter 社区的通用解法：**把 resize 当作高频信号，只在"停下来之后"做一次重活**。

用法
----
    debouncer = Debouncer(root)
    debouncer.schedule(self._redraw, delay_ms=120)

    # 需要立即执行时
    debouncer.flush()
"""

from __future__ import annotations

import time
import tkinter as tk
from typing import Callable, Optional


class Debouncer:
    """防抖调度器。"""

    def __init__(self, root: tk.Misc):
        self.root = root
        self._job: Optional[str] = None
        self._last_call: float = 0.0
        self._pending: Optional[Callable] = None

    def schedule(self, fn: Callable, delay_ms: int = 120) -> None:
        """
        安排一次延迟执行（防抖）。

        连续调用时只有最后一次会真正执行。
        """
        self._pending = fn
        try:
            if self._job is not None:
                self.root.after_cancel(self._job)
        except Exception:
            pass
        self._job = self.root.after(delay_ms, self._fire)

    def _fire(self) -> None:
        self._job = None
        fn = self._pending
        self._pending = None
        if fn is None:
            return
        try:
            fn()
        except Exception as exc:
            print(f"[debounce] 执行失败：{exc}")

    def flush(self) -> None:
        """立即执行待处理的任务（若有）。"""
        try:
            if self._job is not None:
                self.root.after_cancel(self._job)
                self._job = None
        except Exception:
            pass
        fn = self._pending
        self._pending = None
        if fn is not None:
            try:
                fn()
            except Exception:
                pass

    def cancel(self) -> None:
        """取消待处理的任务。"""
        try:
            if self._job is not None:
                self.root.after_cancel(self._job)
        except Exception:
            pass
        self._job = None
        self._pending = None


class DragTracker:
    """
    拖拽状态跟踪。

    判断依据：两次尺寸变化的时间间隔。
    间隔很短（< threshold 秒）-> 用户正在拖拽；间隔变长 -> 拖拽结束。

    用途：拖拽期间**完全跳过重绘**，松手后再统一重绘一次。
    这是避免"窗口拖动时界面狂闪"的关键。
    """

    def __init__(self, threshold: float = 0.2):
        self.threshold = threshold
        self._last_change: float = 0.0
        self._dragging = False

    def note_change(self) -> bool:
        """
        记录一次尺寸变化。

        :returns: 当前是否处于拖拽状态
        """
        now = time.monotonic()
        if now - self._last_change < self.threshold:
            self._dragging = True
        else:
            self._dragging = False
        self._last_change = now
        return self._dragging

    @property
    def dragging(self) -> bool:
        return self._dragging

    def reset(self) -> None:
        """重置状态（拖拽结束 / 震荡解除时调用）。"""
        self._dragging = False
        self._last_change = 0.0
