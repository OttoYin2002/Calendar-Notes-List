# -*- coding: utf-8 -*-
"""
全局配置与路径解析。

设计要点：
1. 所有数据均保存在程序所在目录下的 data/ 子目录（打包成 exe 后即 exe 同级目录）。
2. 若程序目录不可写（例如被安装到 C:\\Program Files），自动降级到 %APPDATA%\\CalendarMemo。
3. 置顶 / 主题 / 声音等"配置项"与"业务数据"分开存放：
   - config.json  -> 配置（置顶状态、主题、音效）
   - events.json  -> 日程
   - todos.json   -> 待办
   - tags.json    -> 标签
   - holidays.json-> 节假日数据（可覆盖内置表）
   - reminder_state.json -> 提醒已触发记录（避免重启后重复弹窗）
"""

import os
import sys
from pathlib import Path

APP_NAME = "日程备忘"
APP_VERSION = "1.0.0"

# ---------------------------------------------------------------- 路径解析 ----


def is_frozen() -> bool:
    """是否为 PyInstaller 打包后的运行环境。"""
    return getattr(sys, "frozen", False)


def get_base_dir() -> Path:
    """程序根目录：打包后为 exe 所在目录，源码运行时为项目根目录。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _writable(path: Path) -> bool:
    """判断目录是否可写（用于决定数据存放位置）。"""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False


def get_data_dir() -> Path:
    """数据目录：优先程序同级 data/，不可写时降级到 %APPDATA%。"""
    base = get_base_dir()
    local = base / "data"
    if _writable(local):
        return local
    appdata = Path(os.environ.get("APPDATA", str(Path.home()))) / "CalendarMemo"
    appdata.mkdir(parents=True, exist_ok=True)
    return appdata


DATA_DIR = get_data_dir()
EVENTS_FILE = DATA_DIR / "events.json"
TODOS_FILE = DATA_DIR / "todos.json"
TAGS_FILE = DATA_DIR / "tags.json"
CONFIG_FILE = DATA_DIR / "config.json"
HOLIDAYS_FILE = DATA_DIR / "holidays.json"
REMINDER_STATE_FILE = DATA_DIR / "reminder_state.json"

# ---------------------------------------------------------------- 常量配置 ----

WINDOW_TITLE = f"{APP_NAME} v{APP_VERSION}"
# 窗口尺寸（可自由调整，尺寸与位置会被记忆）
# 1360x800 适配 1366x768 常见笔记本分辨率，保证侧边栏各区块与月视图 7 列不被压没。
# 窗口可自由缩放：尺寸变化走「防抖 + 抖动检测」，不会引起界面抖动。
DEFAULT_WIDTH = 1360
DEFAULT_HEIGHT = 800
# 最小尺寸：保证工具栏按钮与侧边栏各区块不被压没
MIN_WIDTH = 1120
MIN_HEIGHT = 700
SIDEBAR_WIDTH = 300

# 优先级定义：key -> (中文名, 标识符)
# 标识符刻意使用 ASCII 字符（* 数量表示紧急度）：
# 原因 —— 部分 Windows 字体环境下 ▲/●/▼ 等几何符号会渲染成方框或问号，
#        ASCII 标记可 100% 可靠渲染，跨 Win10/Win11 表现一致。
PRIORITIES = {
    "high": ("高", "***"),
    "normal": ("中", "**"),
    "low": ("低", "*"),
}
PRIORITY_ORDER = ["high", "normal", "low"]

# 重复规则：key -> (中文名, 单选框文字)
REPEAT_RULES = {
    "none": ("不重复", "不重复"),
    "daily": ("每天", "每天"),
    "weekly": ("每周", "每周"),
    "monthly": ("每月", "每月"),
    "yearly": ("每年", "每年"),
}

# 提醒提前量预设（分钟）—— 一条日程可同时勾选多个
REMINDER_PRESETS = [
    (0, "准时"),
    (5, "提前5分钟"),
    (15, "提前15分钟"),
    (30, "提前30分钟"),
    (60, "提前1小时"),
    (1440, "提前1天"),
]

# 稍后提醒的延后时长（分钟）
SNOOZE_OPTIONS = [10, 30]

# 主题
THEME_LIGHT = "light"
THEME_DARK = "dark"

# 提醒轮询间隔（秒）
REMINDER_INTERVAL = 15
# 启动后允许补弹的"宽限期"（分钟）：超过该宽限期的过期提醒不再补弹
REMINDER_GRACE_MINUTES = 60
