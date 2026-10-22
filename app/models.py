# -*- coding: utf-8 -*-
"""
数据模型定义：日程 Event、待办 Todo、标签 Tag。

全部使用 dataclass，提供 to_dict / from_dict 便于 JSON 序列化。
日程中的重复规则不预先展开存储，而是保存"母日程 + 规则"，
在渲染时由 recurrence.py 按需展开，编辑时可整体同步或单次例外。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

# ISO 格式字符串（秒精度，跨平台安全）
ISO_FMT = "%Y-%m-%dT%H:%M:%S"


def new_id() -> str:
    """生成短唯一 ID。"""
    return uuid.uuid4().hex[:12]


def now_iso() -> str:
    return datetime.now().strftime(ISO_FMT)


def to_iso(dt: datetime) -> str:
    return dt.strftime(ISO_FMT)


def from_iso(text: str) -> Optional[datetime]:
    """解析 ISO 字符串，失败返回 None（用于容错读取历史数据）。"""
    if not text:
        return None
    for fmt in (ISO_FMT, "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


@dataclass
class Tag:
    """标签：用于日程分类与颜色区分。"""

    name: str
    color: str = "#00489D"

    def to_dict(self) -> dict:
        return {"name": self.name, "color": self.color}

    @staticmethod
    def from_dict(data: dict) -> "Tag":
        return Tag(
            name=str(data.get("name", "未分类")),
            color=str(data.get("color", "#00489D")),
        )


@dataclass
class Event:
    """
    日程。

    重复日程以"母日程"形式存储：
      - repeat        : none/daily/weekly/monthly/yearly
      - repeat_weekdays: 每周重复时选中的星期（0=周一 ... 6=周日）
      - repeat_until  : 重复截止日期（None 表示无限）
      - exceptions    : 被单独删除的日期列表（ISO 日期）
      - overrides     : 被单独修改的实例 {日期: {字段覆盖}}
    """

    id: str = field(default_factory=new_id)
    title: str = ""
    note: str = ""
    start: datetime = field(default_factory=datetime.now)
    end: datetime = field(default_factory=datetime.now)
    tag: str = ""                 # 标签名，空表示无标签
    priority: str = "normal"      # high / normal / low
    repeat: str = "none"          # 重复规则
    repeat_weekdays: List[int] = field(default_factory=list)
    repeat_until: Optional[str] = None
    reminders: List[int] = field(default_factory=list)  # 提前提醒分钟数列表
    exceptions: List[str] = field(default_factory=list)   # 单独删除的日期
    overrides: Dict[str, dict] = field(default_factory=dict)  # 单独修改的实例
    all_day: bool = False        # 是否全天日程
    created_at: str = field(default_factory=now_iso)

    # ------------------------------------------------------------ 序列化 ----
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "note": self.note,
            "start": to_iso(self.start),
            "end": to_iso(self.end),
            "tag": self.tag,
            "priority": self.priority,
            "repeat": self.repeat,
            "repeat_weekdays": list(self.repeat_weekdays),
            "repeat_until": self.repeat_until,
            "reminders": list(self.reminders),
            "exceptions": list(self.exceptions),
            "overrides": dict(self.overrides),
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(data: dict) -> Optional["Event"]:
        start = from_iso(str(data.get("start", "")))
        end = from_iso(str(data.get("end", "")))
        if start is None or end is None:
            return None  # 缺少时间字段的脏数据直接丢弃
        if end < start:
            end = start
        return Event(
            id=str(data.get("id") or new_id()),
            title=str(data.get("title", "")),
            note=str(data.get("note", "")),
            start=start,
            end=end,
            tag=str(data.get("tag", "")),
            priority=str(data.get("priority", "normal")),
            repeat=str(data.get("repeat", "none")),
            repeat_weekdays=[int(x) for x in data.get("repeat_weekdays", []) or []],
            repeat_until=data.get("repeat_until"),
            reminders=[int(x) for x in data.get("reminders", []) or []],
            exceptions=[str(x) for x in data.get("exceptions", []) or []],
            overrides={str(k): dict(v) for k, v in (data.get("overrides") or {}).items()},
            all_day=bool(data.get("all_day", False)),
            created_at=str(data.get("created_at") or now_iso()),
        )

    # ------------------------------------------------------------ 便捷属性 ----
    @property
    def is_repeating(self) -> bool:
        return self.repeat != "none"

    def clone(self) -> "Event":
        """浅拷贝 + 深拷贝可变字段，用于生成独立实例。"""
        return Event(
            id=self.id,
            title=self.title,
            note=self.note,
            start=self.start,
            end=self.end,
            tag=self.tag,
            priority=self.priority,
            repeat=self.repeat,
            repeat_weekdays=list(self.repeat_weekdays),
            repeat_until=self.repeat_until,
            reminders=list(self.reminders),
            exceptions=list(self.exceptions),
            overrides={k: dict(v) for k, v in self.overrides.items()},
            all_day=self.all_day,
            created_at=self.created_at,
        )


@dataclass
class Todo:
    """待办事项：没有固定时间的任务清单。"""

    id: str = field(default_factory=new_id)
    text: str = ""
    done: bool = False
    tag: str = ""
    created_at: str = field(default_factory=now_iso)
    done_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "done": self.done,
            "tag": self.tag,
            "created_at": self.created_at,
            "done_at": self.done_at,
        }

    @staticmethod
    def from_dict(data: dict) -> Optional["Todo"]:
        text = str(data.get("text", "")).strip()
        if not text:
            return None
        return Todo(
            id=str(data.get("id") or new_id()),
            text=text,
            done=bool(data.get("done", False)),
            tag=str(data.get("tag", "")),
            created_at=str(data.get("created_at") or now_iso()),
            done_at=str(data.get("done_at", "")),
        )
