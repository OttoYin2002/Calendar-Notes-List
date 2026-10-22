# -*- coding: utf-8 -*-
"""
提醒引擎（独立后台线程）。

要点：
1. 后台线程只负责"算时间"，不碰任何 Tk 对象；到点后通过 root.after(0, ...) 回到主线程弹窗。
2. 重复日程的提醒按"实例"计算：每次实例的开始时间 - 提前分钟数 = 触发时间。
3. 已触发记录写入 reminder_state.json，避免重启后重复弹窗。
4. "稍后提醒" 通过 snooze_until 延后，同一条提醒不会被立刻重复触发。
"""

from __future__ import annotations

import threading
from datetime import date, datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple

from .config import REMINDER_GRACE_MINUTES, REMINDER_INTERVAL
from .models import Event
from .recurrence import Occurrence, expand_all

# 触发键：事件ID + 实例日期 + 提前分钟数
def make_key(event_id: str, date_str: str, minutes_before: int) -> str:
    return f"{event_id}@{date_str}@{minutes_before}"


class ReminderEngine:
    """定时检查到期提醒的后台引擎。"""

    def __init__(self, storage, on_fire: Callable[[List[Tuple[Occurrence, int]]], None]):
        """
        :param storage: Storage 实例
        :param on_fire: 触发回调，参数为 [(Occurrence, 提前分钟数), ...]
        """
        self.storage = storage
        self.on_fire = on_fire
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        # 稍后提醒的延后记录 {key: datetime}
        self._snoozes: Dict[str, datetime] = {}
        self._last_tick = datetime.now()
        self._started = False

    # ------------------------------------------------------------ 生命周期 ----
    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="reminder-engine", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    # ------------------------------------------------------------ 主循环 ----
    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.tick()
            except Exception as exc:
                print(f"[reminder] 线程异常：{exc}")
            self._stop_event.wait(REMINDER_INTERVAL)

    # ------------------------------------------------------------ 核心逻辑 ----
    def tick(self) -> None:
        """执行一次检查（测试时可直接调用）。"""
        now = datetime.now()
        last = self._last_tick
        self._last_tick = now

        fired = self.storage.fired_reminders()
        events = self.storage.events
        if not events:
            return

        # 提前一天提醒的最远提前量是 1440 分钟，因此向后扫描 2 天足够
        scan_start = (now - timedelta(days=2)).date()
        scan_end = (now + timedelta(days=2)).date()
        occurrences = expand_all(events, scan_start, scan_end)

        pending: List[Tuple[Occurrence, int]] = []
        for occ in occurrences:
            for minutes_before in occ.reminders:
                key = make_key(occ.event.id, occ.date_str, minutes_before)
                if key in fired:
                    continue
                # 触发时间 = 实例开始时间 - 提前分钟
                trigger_at = occ.start - timedelta(minutes=minutes_before)
                if trigger_at > now:
                    continue  # 还没到点
                # 过期太久不再补弹（宽限期）
                if now - trigger_at > timedelta(minutes=REMINDER_GRACE_MINUTES):
                    # 直接标记为已触发，避免每秒重复判断
                    self.storage.mark_reminder_fired(key)
                    continue
                # 稍后提醒延后处理
                with self._lock:
                    snoozed_until = self._snoozes.get(key)
                if snoozed_until is not None:
                    if now < snoozed_until:
                        continue  # 延后未到时间
                    self._snoozes.pop(key, None)
                pending.append((occ, minutes_before))

        if pending:
            for occ, minutes in pending:
                self.storage.mark_reminder_fired(make_key(occ.event.id, occ.date_str, minutes))
            self.on_fire(pending)

    # ------------------------------------------------------------ 稍后提醒 ----
    def snooze(self, event_id: str, date_str: str, minutes_before: int, delay_minutes: int) -> None:
        """把某条提醒延后 delay_minutes 分钟。"""
        key = make_key(event_id, date_str, minutes_before)
        with self._lock:
            self._snoozes[key] = datetime.now() + timedelta(minutes=delay_minutes)
        # 解除已触发标记，延后到期后可再次弹窗
        fired = self.storage.fired_reminders()
        fired.discard(key)
        with self.storage._lock:
            self.storage._reminder_state["fired"] = list(fired)[-500:]
        self.storage.save_reminder_state()

    def unsnooze_all(self) -> None:
        with self._lock:
            self._snoozes.clear()
