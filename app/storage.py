# -*- coding: utf-8 -*-
"""
本地 JSON 持久化存储层。

特性：
1. 完全离线：只读写本地文件，不发起任何网络请求。
2. 容错：文件损坏 / 字段缺失时自动备份损坏文件并重建空数据，程序不崩溃。
3. 分离存储：业务数据（events/todos/tags/holidays）与配置（config）分文件存放。
4. 原子写入：先写临时文件再替换，避免写入中断导致数据丢失。
"""

from __future__ import annotations

import json
import shutil
import time
from typing import Any, Dict, List

from . import config as _cfg
from .models import Event, Tag, Todo


def _path(name: str):
    """
    动态取配置文件路径。

    这里刻意不直接 `from .config import EVENTS_FILE`，
    而是运行时访问 config 模块属性，便于测试时重定向数据目录。
    """
    return getattr(_cfg, name)


def _read_json(path, default: Any) -> Any:
    """
    安全读取 JSON。文件不存在返回默认值；
    文件损坏则备份为 *.corrupt_<时间戳> 并返回默认值（保证软件不崩溃）。
    """
    try:
        if not path.exists():
            return default
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            return default
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        try:
            backup = path.with_suffix(path.suffix + f".corrupt_{int(time.time())}")
            shutil.copy2(path, backup)
            print(f"[storage] 数据文件损坏已备份至 {backup.name}：{exc}")
        except Exception:
            pass
        return default


def _write_json(path, data: Any) -> bool:
    """原子写入 JSON：先写 .tmp 再替换目标文件。"""
    try:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return True
    except OSError as exc:
        print(f"[storage] 写入失败 {path.name}：{exc}")
        return False


class Storage:
    """日程备忘的本地数据仓库（单例式使用，线程内加锁保证并发安全）。"""

    def __init__(self) -> None:
        import threading

        self._lock = threading.RLock()
        self._events: List[Event] = []
        self._todos: List[Todo] = []
        self._tags: List[Tag] = []
        self._config: Dict[str, Any] = {}
        self._reminder_state: Dict[str, Any] = {}
        self._holidays: Dict[str, Any] = {}
        self.load_all()

    # ------------------------------------------------------------ 载入 ----
    def load_all(self) -> None:
        with self._lock:
            self._load_events()
            self._load_todos()
            self._load_tags()
            self._load_config()
            self._load_reminder_state()
            self._load_holidays()

    def _load_events(self) -> None:
        raw = _read_json(_path("EVENTS_FILE"), {"events": []})
        items = raw.get("events", []) if isinstance(raw, dict) else raw
        result: List[Event] = []
        for item in items or []:
            try:
                ev = Event.from_dict(item)
                if ev is not None:
                    result.append(ev)
            except Exception as exc:
                print(f"[storage] 跳过异常日程记录：{exc}")
        self._events = result

    def _load_todos(self) -> None:
        raw = _read_json(_path("TODOS_FILE"), {"todos": []})
        items = raw.get("todos", []) if isinstance(raw, dict) else raw
        result: List[Todo] = []
        for item in items or []:
            try:
                td = Todo.from_dict(item)
                if td is not None:
                    result.append(td)
            except Exception as exc:
                print(f"[storage] 跳过异常待办记录：{exc}")
        self._todos = result

    def _load_tags(self) -> None:
        raw = _read_json(_path("TAGS_FILE"), {"tags": []})
        items = raw.get("tags", []) if isinstance(raw, dict) else raw
        result: List[Tag] = []
        for item in items or []:
            try:
                result.append(Tag.from_dict(item))
            except Exception:
                continue
        if not result:
            # 首次运行：写入默认标签
            result = [Tag("工作", "#00489D"), Tag("私人", "#2E7D32"),
                      Tag("采购", "#C62828"), Tag("会议", "#6A1B9A")]
            self._tags = result
            self.save_tags()
            return
        self._tags = result

    def _load_config(self) -> None:
        raw = _read_json(_path("CONFIG_FILE"), {})
        self._config = raw if isinstance(raw, dict) else {}

    def _load_reminder_state(self) -> None:
        raw = _read_json(_path("REMINDER_STATE_FILE"), {"fired": []})
        self._reminder_state = raw if isinstance(raw, dict) else {"fired": []}

    def _load_holidays(self) -> None:
        raw = _read_json(_path("HOLIDAYS_FILE"), {})
        self._holidays = raw if isinstance(raw, dict) else {}

    # ------------------------------------------------------------ 保存 ----
    def save_events(self) -> None:
        with self._lock:
            _write_json(_path("EVENTS_FILE"), {"version": 1, "events": [e.to_dict() for e in self._events]})

    def save_todos(self) -> None:
        with self._lock:
            _write_json(_path("TODOS_FILE"), {"version": 1, "todos": [t.to_dict() for t in self._todos]})

    def save_tags(self) -> None:
        with self._lock:
            _write_json(_path("TAGS_FILE"), {"version": 1, "tags": [t.to_dict() for t in self._tags]})

    def save_config(self) -> None:
        with self._lock:
            _write_json(_path("CONFIG_FILE"), self._config)

    def save_reminder_state(self) -> None:
        with self._lock:
            _write_json(_path("REMINDER_STATE_FILE"), self._reminder_state)

    def save_holidays(self) -> None:
        with self._lock:
            _write_json(_path("HOLIDAYS_FILE"), self._holidays)

    # ------------------------------------------------------ 业务读写接口 ----
    @property
    def events(self) -> List[Event]:
        with self._lock:
            return list(self._events)

    @property
    def todos(self) -> List[Todo]:
        with self._lock:
            return list(self._todos)

    @property
    def tags(self) -> List[Tag]:
        with self._lock:
            return list(self._tags)

    def get_event(self, event_id: str) -> Event | None:
        with self._lock:
            for ev in self._events:
                if ev.id == event_id:
                    return ev
        return None

    def upsert_event(self, event: Event) -> None:
        """新增或更新日程（按 id 匹配）。"""
        with self._lock:
            for idx, ev in enumerate(self._events):
                if ev.id == event.id:
                    self._events[idx] = event
                    break
            else:
                self._events.append(event)
        self.save_events()

    def delete_event(self, event_id: str) -> None:
        with self._lock:
            self._events = [e for e in self._events if e.id != event_id]
        self.save_events()

    def upsert_todo(self, todo: Todo) -> None:
        with self._lock:
            for idx, td in enumerate(self._todos):
                if td.id == todo.id:
                    self._todos[idx] = todo
                    break
            else:
                self._todos.append(todo)
        self.save_todos()

    def delete_todo(self, todo_id: str) -> None:
        with self._lock:
            self._todos = [t for t in self._todos if t.id != todo_id]
        self.save_todos()

    def tag_color(self, name: str) -> str:
        """按标签名取颜色；无标签返回中性灰。"""
        with self._lock:
            for tg in self._tags:
                if tg.name == name:
                    return tg.color
        return "#6B7A8D"

    def tag_names(self) -> List[str]:
        with self._lock:
            return [t.name for t in self._tags]

    def ensure_tag(self, name: str, color: Optional[str] = None) -> bool:
        """
        确保标签存在，不存在则创建。

        供快捷输入的 `#标签` 标记使用：用户输入 #新标签 时自动建标签，
        而不是静默丢弃（丢弃会导致日程的标签信息丢失）。

        :returns: True 表示新建了标签
        """
        name = (name or "").strip()
        if not name:
            return False
        with self._lock:
            for tg in self._tags:
                if tg.name == name:
                    return False
            self._tags.append(Tag(name, color or "#5B7FA6"))
        self.save_tags()
        return True

    # ---------------------------------------------------------- 配置项 ----
    def get_config(self, key: str, default=None):
        with self._lock:
            return self._config.get(key, default)

    def set_config(self, key: str, value) -> None:
        with self._lock:
            self._config[key] = value
        self.save_config()

    # -------------------------------------------------- 提醒触发状态记录 ----
    def fired_reminders(self) -> set:
        with self._lock:
            return set(self._reminder_state.get("fired", []))

    def mark_reminder_fired(self, key: str) -> None:
        with self._lock:
            fired = set(self._reminder_state.get("fired", []))
            fired.add(key)
            # 仅保留最近 500 条，防止文件无限增长
            self._reminder_state["fired"] = list(fired)[-500:]
        self.save_reminder_state()

    def clear_reminder_state(self) -> None:
        with self._lock:
            self._reminder_state = {"fired": []}
        self.save_reminder_state()

    # ------------------------------------------------------ 节假日数据 ----
    @property
    def holidays(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._holidays)

    def set_holidays(self, data: Dict[str, Any]) -> None:
        with self._lock:
            self._holidays = dict(data or {})
        self.save_holidays()
