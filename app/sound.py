# -*- coding: utf-8 -*-
"""
提醒提示音模块。

设计目标
--------
1. 不依赖任何外部音频文件（避免分发时缺文件 / 路径失效）
2. 用 Windows 内置系统声音 + 合成音，保证任何机器都有声音
3. 跨平台优雅降级（非 Windows 静默忽略，不影响功能）

可用音效
--------
  bell    —— 铃声（默认）：双音交替，柔和不刺耳
  water   —— 水滴：下滑音，短促清脆
  chime   —— 风铃：三音上行
  ding    —— 提示音：Windows 系统"叮"声
  alarm   —— 闹钟：Windows 系统"闹钟"声
  none    —— 静音

实现方式
--------
  - 优先使用 winsound.PlaySound 播放 Windows 系统声音别名
  - 自定义音效用 winsound.Beep 合成（频率-时长序列）
  - 全部在后台线程播放，不阻塞 UI
"""

from __future__ import annotations

import sys
import threading
from typing import List, Optional, Tuple

IS_WINDOWS = sys.platform.startswith("win")

# (键, 显示名)
SOUND_PRESETS: List[Tuple[str, str]] = [
    ("bell", "铃声"),
    ("water", "水滴"),
    ("chime", "风铃"),
    ("ding", "提示音"),
    ("alarm", "闹钟"),
    ("none", "静音"),
]

DEFAULT_SOUND = "bell"

# 各音效的 (频率Hz, 时长ms) 序列
_BELL = [(880, 180), (0, 90), (1175, 260)]
_WATER = [(1400, 70), (900, 110)]
_CHIME = [(988, 130), (1319, 130), (1568, 320)]
_SYSTEM_ALIASES = {
    "ding": "Asterisk",
    "alarm": "Alarm",
}


def play_sound(kind: str = DEFAULT_SOUND) -> None:
    """
    播放提示音（后台线程，不阻塞 UI）。

    任何异常都静默忽略 —— 提示音失败不应影响提醒功能本身。
    """
    if kind == "none":
        return

    def _worker() -> None:
        try:
            if not IS_WINDOWS:
                return
            import winsound

            alias = _SYSTEM_ALIASES.get(kind)
            if alias:
                # SND_ALIAS | SND_ASYNC：调用系统声音，不阻塞
                winsound.PlaySound(alias, winsound.SND_ALIAS | winsound.SND_ASYNC)
                return

            sequence = {
                "bell": _BELL,
                "water": _WATER,
                "chime": _CHIME,
            }.get(kind)
            if not sequence:
                return
            for freq, ms in sequence:
                if freq > 0:
                    winsound.Beep(freq, ms)
                else:
                    # 静音间隔
                    import time
                    time.sleep(ms / 1000.0)
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()


def preview(kind: str) -> None:
    """试听音效（供 UI 调用）。"""
    play_sound(kind)
