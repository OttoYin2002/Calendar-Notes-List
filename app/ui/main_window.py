# -*- coding: utf-8 -*-
"""
主窗口：组装侧边栏 + 视图区 + 工具栏。

布局：
  ┌────────────── 工具栏（视图切换 / 前后翻页 / 快捷添加 / 搜索 / 主题 / 置顶）─────────┐
  │ 侧边栏（导航+置顶+筛选+待办+统计） │  主区域（月/周/日视图）                        │
  └──────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import calendar
import os
import time
import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import filedialog, messagebox, ttk
from typing import Callable, List, Optional

from ..config import (
    APP_NAME,
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    MIN_HEIGHT,
    MIN_WIDTH,
    PRIORITIES,
    SIDEBAR_WIDTH,
    THEME_DARK,
    THEME_LIGHT,
    WINDOW_TITLE,
)
from ..dpi import fit_to_screen, init_dpi_scaling, scale_int
from ..holidays import HolidayProvider, REGION_CN
from ..models import Event, Todo, new_id
from ..nlp import parse_quick
from ..recurrence import Occurrence, expand_all
from ..reminder import ReminderEngine
from ..storage import Storage
from ..themes import apply_ttk_styles, get_theme
from ..topmost import bring_to_front, is_topmost, set_topmost
from .event_detail import EventDetailDialog
from .event_dialog import EventDialog
from .filter_panel import FilterPanel, StatsPanel
from .month_view import MonthView
from .reminder_popup import ReminderPopup
from .search_panel import SearchPanel
from .tag_manager import TagManagerDialog
from .time_grid import TimeGridView
from .todo_panel import TodoPanel
from . import typography

VIEW_MONTH = "month"
VIEW_WEEK = "week"
VIEW_DAY = "day"


class MainWindow:
    """日程备忘主窗口。"""

    def __init__(self, root: tk.Tk, storage: Storage):
        self.root = root
        self.storage = storage
        # 节假日提供器（固定使用中国标准）
        self.holidays = HolidayProvider(storage, REGION_CN)

        # 主题
        self.theme_name = storage.get_config("theme", THEME_LIGHT)
        self.theme = get_theme(self.theme_name)

        # 状态
        self.current_view = storage.get_config("view", VIEW_MONTH)
        self.anchor_date = date.today()
        self._popups: List[ReminderPopup] = []

        self.root.title(WINDOW_TITLE)
        # 按屏幕工作区自适应窗口尺寸（高分屏 / 小屏都不会溢出或过小）
        init_dpi_scaling(self.root)
        win_w, win_h = fit_to_screen(self.root, DEFAULT_WIDTH, DEFAULT_HEIGHT,
                                     MIN_WIDTH, MIN_HEIGHT)
        self.root.geometry(f"{win_w}x{win_h}")
        self.root.minsize(MIN_WIDTH, MIN_HEIGHT)
        self.root.configure(bg=self.theme["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self._on_close_request)
        apply_ttk_styles(self.root, self.theme)
        self._build_ui()

        # 提醒引擎（后台线程）
        self.reminder_engine = ReminderEngine(self.storage, self._on_reminder_fire)
        self.reminder_engine.start()

        # 系统托盘（可选）
        self.tray = None
        self._setup_tray()

        # 置顶状态恢复
        if self.storage.get_config("always_on_top", False):
            self.root.after(200, lambda: self.set_topmost(True, persist=False))

        # 键盘快捷键
        self.root.bind("<Control-n>", lambda e: self.quick_add_event())
        self.root.bind("<Control-f>", lambda e: self.open_search())
        self.root.bind("<Control-t>", lambda e: self.flip_topmost())
        self.root.bind("<Control-d>", lambda e: self.toggle_theme())

        self.refresh_all()
        self.root.after(100, self._restore_geometry)

    # ============================================================ UI 构建 ====
    def _build_ui(self) -> None:
        t = self.theme
        self.root.configure(bg=t["bg"])

        # ---------------- 工具栏 ----------------
        self._toolbar = tk.Frame(self.root, bg=t["bg_alt"], height=52)
        self._toolbar.pack(side="top", fill="x")
        self._toolbar.pack_propagate(False)
        self._build_toolbar_widgets()

        # ---------------- 主体 ----------------
        body = tk.Frame(self.root, bg=t["bg"])
        body.pack(side="top", fill="both", expand=True)

        # 侧边栏
        self.sidebar = tk.Frame(body, bg=t["panel"], width=SIDEBAR_WIDTH)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        self._build_sidebar()

        # 主区域
        self.main_area = tk.Frame(body, bg=t["bg"])
        self.main_area.pack(side="left", fill="both", expand=True)

        # 三个视图
        self.month_view = MonthView(self.main_area, self.theme_name, self.holidays,
                                    on_day_click=self.on_day_click,
                                    on_event_click=self.on_event_click,
                                    on_more_click=self.on_more_click,
                                    on_prev_month=self.go_prev,
                                    on_next_month=self.go_next)
        self.week_view = TimeGridView(self.main_area, self.theme_name, 7, self.holidays,
                                      on_event_click=self.on_event_click,
                                      on_empty_click=self.on_empty_click)
        self.day_view = TimeGridView(self.main_area, self.theme_name, 1, self.holidays,
                                     on_event_click=self.on_event_click,
                                     on_empty_click=self.on_empty_click)
        self.month_view.color_resolver = self._tag_color
        self.week_view.color_resolver = self._tag_color
        self.day_view.color_resolver = self._tag_color

        for v in (self.month_view, self.week_view, self.day_view):
            v.pack(fill="both", expand=True)

        # 状态栏
        self.status_bar = tk.Label(self.root, text="", bg=t["bg"], fg=t["text_dim"],
                                   anchor="w", padx=14, pady=4,
                                   font=typography.caption())
        self.status_bar.pack(side="bottom", fill="x")


    def _build_toolbar_widgets(self) -> None:
        """
        构建（或重建）工具栏控件。

        布局策略：用 grid 而非 pack 实现「弹性」——
          - 左区（标题/视图/导航/周期）固定，靠左
          - 中区（快速添加）自动伸展，窗口变窄时先压缩这里
          - 右区（搜索/更多/主题/置顶）固定，靠右
        这样窗口无论宽窄，各功能按钮都不会被裁掉。
        """
        t = self.theme
        toolbar = self._toolbar
        from .rounded_button import RoundedButton

        # ---------- 左区：标题 + 视图切换 + 导航 ----------
        left = tk.Frame(toolbar, bg=t["bg_alt"])
        left.grid(row=0, column=0, sticky="w")

        tk.Label(left, text=APP_NAME, bg=t["bg_alt"], fg=t["primary"],
                 font=typography.h1('bold')).pack(side="left", padx=(16, 16))

        seg = tk.Frame(left, bg=t["bg_alt"])
        seg.pack(side="left")
        self.view_buttons = {}
        for key, label in ((VIEW_MONTH, "月"), (VIEW_WEEK, "周"), (VIEW_DAY, "日")):
            btn = tk.Label(seg, text=label, bg=t["bg_alt"], fg=t["text_dim"],
                           font=typography.body('bold'), padx=14, pady=6,
                           cursor="hand2")
            btn.pack(side="left", padx=1)
            btn.bind("<Button-1>", lambda e, k=key: self.switch_view(k))
            self.view_buttons[key] = btn

        tk.Frame(left, bg=t["border"], width=1, height=26).pack(side="left", fill="y",
                                                                  padx=12, pady=13)

        RoundedButton(left, "<", command=self.go_prev, variant="secondary",
                      theme=t, width=34, height=30, font_size=11, radius=7).pack(side="left")
        RoundedButton(left, "今天", command=self.go_today, variant="secondary",
                      theme=t, height=30, font_size=9, radius=7).pack(side="left", padx=5)
        RoundedButton(left, ">", command=self.go_next, variant="secondary",
                      theme=t, width=34, height=30, font_size=11, radius=7).pack(side="left")

        self.period_label = tk.Label(left, text="", bg=t["bg_alt"], fg=t["text"],
                                     font=typography.h2('bold'))
        self.period_label.pack(side="left", padx=14)

        # ---------- 中区：快速添加（弹性伸展，窄窗口时先被压缩） ----------
        mid = tk.Frame(toolbar, bg=t["bg_alt"])
        mid.grid(row=0, column=1, sticky="ew", padx=12)
        toolbar.grid_columnconfigure(1, weight=1)

        self.quick_entry = ttk.Entry(mid, font=typography.small())
        self.quick_entry.pack(side="left", fill="x", expand=True, ipady=3)
        self.quick_entry.bind("<Return>", lambda e: self.quick_add_event())
        # 悬浮提示：告诉用户支持哪些语法
        from .tooltip import Tooltip
        self._quick_tip = Tooltip(
            self.quick_entry,
            "自然语言：明天下午3点开会 / 本周五中午吃饭\n"
            "显式标记：#标签  !高  @10-28  ~90（分钟）\n"
            "例：#工作 !高 @10-28 ~1.5h 客户回访",
            t)
        RoundedButton(mid, "添加", command=self.quick_add_event, variant="primary",
                      theme=t, height=30, font_size=9, radius=7).pack(side="left", padx=(6, 0))
        tk.Label(mid, text="快速添加", bg=t["bg_alt"], fg=t["text_dim"],
                 font=typography.small()).pack(side="left", padx=(8, 6))

        # ---------- 右区：搜索 / 更多 ----------
        # 工具栏只保留高频操作（搜索、快速添加），低频功能（主题切换等）收进「更多」，
        # 让界面更聚焦。
        right = tk.Frame(toolbar, bg=t["bg_alt"])
        right.grid(row=0, column=2, sticky="e", padx=(0, 14))

        RoundedButton(right, "搜索", command=self.open_search, variant="secondary",
                      theme=t, height=30, font_size=9, radius=7).pack(side="left", padx=(0, 6))

        # 「更多」下拉菜单：收纳低频功能（主题切换/导入/导出/标签管理/数据目录）
        self._more_btn = tk.Label(right, text="更多 ▾", bg=t["bg_alt"], fg=t["text_dim"],
                                  font=typography.small(), padx=10, pady=7, cursor="hand2")
        self._more_btn.pack(side="left")
        self._more_btn.bind("<Button-1>", self._toggle_more_menu)

    # ---------------------------------------------------------- 更多菜单 ----
    def _toggle_more_menu(self, _e=None) -> None:
        """弹出「更多」下拉菜单（收纳导入/导出/标签管理）。"""
        if getattr(self, "_more_menu", None) is not None:
            try:
                self._more_menu.destroy()
            except Exception:
                pass
            self._more_menu = None
            return

        t = self.theme
        menu = tk.Toplevel(self.root)
        menu.overrideredirect(True)
        menu.configure(bg=t["border"])

        try:
            bx = self._more_btn.winfo_rootx()
            by = self._more_btn.winfo_rooty() + self._more_btn.winfo_height()
        except Exception:
            bx, by = 100, 100

        panel = tk.Frame(menu, bg=t["entry_bg"], highlightthickness=1,
                         highlightbackground=t["border"], bd=0)
        panel.pack(fill="both", expand=True)

        items = [
            ("切换深色/浅色", self.toggle_theme),
            ("导入数据…", self.import_data),
            ("导出数据…", self.export_data),
            ("标签管理…", self.manage_tags),
            ("打开数据文件夹", self._open_data_folder),
        ]
        for label, cmd in items:
            entry = tk.Label(panel, text=label, bg=t["entry_bg"], fg=t["text"],
                             font=typography.small(), padx=18, pady=7, cursor="hand2",
                             anchor="w")
            entry.pack(fill="x")
            entry.bind("<Button-1>", lambda e, c=cmd: self._run_more_action(c))
            entry.bind("<Enter>", lambda e, w=entry: w.configure(bg=t["hover"]))
            entry.bind("<Leave>", lambda e, w=entry: w.configure(bg=t["entry_bg"]))

        self._more_menu = menu
        self.root.after(0, lambda: self._place_menu(menu, bx, by))

    def _place_menu(self, menu: tk.Toplevel, x: int, y: int) -> None:
        try:
            menu.update_idletasks()
            w = menu.winfo_reqwidth()
            h = menu.winfo_reqheight()
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            x = max(0, min(x, sw - w))
            y = max(0, min(y, sh - h))
            menu.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _run_more_action(self, cmd: Callable[[], None]) -> None:
        if getattr(self, "_more_menu", None) is not None:
            try:
                self._more_menu.destroy()
            except Exception:
                pass
            self._more_menu = None
        try:
            cmd()
        except Exception as exc:
            print(f"[menu] 操作失败：{exc}")

    def _open_data_folder(self) -> None:
        """在文件管理器中打开数据目录。"""
        try:
            import os
            import subprocess
            import sys
            from ..config import DATA_DIR
            path = str(DATA_DIR)
            if os.path.isdir(path):
                if sys.platform.startswith("win"):
                    os.startfile(path)  # type: ignore[attr-defined]
                else:
                    subprocess.Popen(["xdg-open", path])
            else:
                self._set_status(f"数据目录不存在：{path}")
        except Exception as exc:
            self._set_status(f"无法打开数据目录：{exc}")


    # ---------------------------------------------------------- 侧边栏 ----
    def _build_sidebar(self) -> None:
        """
        构建侧边栏。

        结构：外层 Canvas（可滚动）+ 内嵌 Frame（内容）。
        原因：侧边栏内容（窗口设置/筛选/统计/待办）在小窗口下可能超出高度，
        若不可滚动，底部区块（尤其待办清单）会被直接压没。
        """
        t = self.theme
        from .toggle import CheckCircle, RadioCircle

        # 侧边栏采用两段式布局：
        #   上半段（可滚动）—— 窗口设置 / 筛选 / 统计
        #   下半段（常驻）  —— 待办清单，始终可见不必滚动
        # 这样既保证低频设置可滚动访问，又让高频的待办清单不被挤出视野。
        self.sidebar.rowconfigure(0, weight=1)   # 上半段：吃掉剩余空间
        self.sidebar.rowconfigure(1, weight=0)   # 统计条：固定高度
        self.sidebar.rowconfigure(2, weight=0)   # 待办区：固定高度
        self.sidebar.columnconfigure(0, weight=1)

        # 外层滚动容器（上半段）
        sb_top = tk.Frame(self.sidebar, bg=t["panel"])
        sb_top.grid(row=0, column=0, sticky="nsew")
        self._sb_canvas = tk.Canvas(sb_top, bg=t["panel"], highlightthickness=0, bd=0)
        self._sb_scrollbar = ttk.Scrollbar(sb_top, orient="vertical",
                                          command=self._sb_canvas.yview)
        self._sb_canvas.configure(yscrollcommand=self._sb_scrollbar.set)
        self._sb_scrollbar.pack(side="right", fill="y")
        self._sb_canvas.pack(side="left", fill="both", expand=True)

        # 内容容器（放在 Canvas 里）
        sb = tk.Frame(self._sb_canvas, bg=t["panel"])
        self._sb_window = self._sb_canvas.create_window((0, 0), window=sb, anchor="nw")
        sb.bind("<Configure>", self._on_sb_configure)
        self._sb_canvas.bind("<Configure>", self._on_sb_canvas_configure)
        for w in (self._sb_canvas, sb):
            w.bind("<MouseWheel>", self._on_sb_wheel)
            w.bind("<Button-4>", self._on_sb_wheel)
            w.bind("<Button-5>", self._on_sb_wheel)

        # 置顶开关
        top_frame = typography.group_frame(sb, t, "窗口")
        top_frame.pack(fill="x", padx=10, pady=(10, typography.SECTION_GAP))

        self.topmost_switch = CheckCircle(top_frame, text="主窗口置顶",
                                          variable=self._topmost_var(),
                                          command=self.toggle_topmost, theme=t,
                                          font_size=9, box_size=15)
        self.topmost_switch.pack(anchor="w", padx=10, pady=(6, 2))
        self.topmost_status = tk.Label(top_frame, text="", bg=t["panel"], fg=t["text_dim"],
                                       font=typography.caption())
        self.topmost_status.pack(anchor="w", padx=30, pady=(0, 4))
        self._update_topmost_status()

        # 提示音
        self.sound_var = tk.BooleanVar(value=bool(self.storage.get_config("sound", True)))
        CheckCircle(top_frame, text="提醒提示音", variable=self.sound_var,
                    command=self._on_sound_toggle, theme=t,
                    font_size=9, box_size=15).pack(anchor="w", padx=10, pady=(0, 4))

        # 提示音种类（下拉框：省纵向空间，展开即可看到全部选项）
        from ..sound import SOUND_PRESETS
        sound_row = tk.Frame(top_frame, bg=t["panel"])
        sound_row.pack(fill="x", padx=10, pady=(2, 6))
        tk.Label(sound_row, text="音效", bg=t["panel"], fg=t["text_dim"],
                 font=typography.caption()).pack(side="left", padx=(0, 6))
        self.sound_kind = tk.StringVar(value=self._sound_label(
            self.storage.get_config("sound_kind", "bell")))
        self.sound_combo = ttk.Combobox(sound_row, textvariable=self.sound_kind,
                                        state="readonly", width=8,
                                        values=[label for _, label in SOUND_PRESETS],
                                        font=typography.small())
        self.sound_combo.pack(side="left", fill="x", expand=True)
        self.sound_combo.bind("<<ComboboxSelected>>", self._on_sound_kind_change)

        # 快捷添加后弹出表单确认（避免解析错误直接落盘）
        self.quick_confirm_var = tk.BooleanVar(
            value=bool(self.storage.get_config("quick_confirm", True)))
        CheckCircle(top_frame, text="快捷添加后确认", variable=self.quick_confirm_var,
                    command=self._on_quick_confirm_toggle, theme=t,
                    font_size=9, box_size=15).pack(anchor="w", padx=10, pady=(2, 6))

        # 国家/地区切换已移除 —— 节假日固定使用中国标准。
        # 需要马来西亚节假日时，可通过 config.json 的 "region": "MY" 手动配置。

        # 筛选
        filter_wrap = tk.Frame(sb, bg=t["panel"])
        filter_wrap.pack(fill="x", padx=10, pady=(0, typography.SECTION_GAP))
        self.filter_panel = FilterPanel(filter_wrap, self.theme_name,
                                         self.storage.tag_names(), self.refresh_views)
        self.filter_panel.pack(fill="x")

        # 统计：放在常驻区（待办清单上方），保证任何窗口高度下都可见
        stats_wrap = tk.Frame(self.sidebar, bg=t["panel"])
        stats_wrap.grid(row=1, column=0, sticky="ew", padx=10,
                        pady=(0, 4))
        self.stats_panel = StatsPanel(stats_wrap, self.theme_name)
        self.stats_panel.pack(fill="x")

        # 待办：固定在侧边栏底部，始终可见
        todo_wrap = typography.group_frame(self.sidebar, t, "待办清单")
        todo_wrap.grid(row=2, column=0, sticky="ew", padx=10,
                       pady=(0, typography.SECTION_GAP))
        todo_wrap.grid_propagate(False)
        self._todo_min_height = 220
        self._todo_fixed_height = 240
        self.todo_panel = TodoPanel(todo_wrap, self.theme_name,
                                    on_add=self.add_todo,
                                    on_toggle=self.toggle_todo,
                                    on_delete=self.delete_todo)
        self.todo_panel.pack(fill="both", expand=True, padx=6, pady=6)

    # ------------------------------------------------------ 侧边栏滚动 ----
    def _on_sb_configure(self, _evt=None) -> None:
        """
        侧边栏内容变化时同步滚动区域。

        注意：**只在 scrollregion 真的变化时才写**。
        无条件 configure 会触发 canvas 的 Configure -> 又回到这里 -> 无限循环。
        """
        try:
            bbox = self._sb_canvas.bbox("all")
            if bbox:
                region = f"{bbox[0]} {bbox[1]} {bbox[2]} {bbox[3]}"
                if region != getattr(self, "_applied_sb_region", None):
                    self._sb_canvas.configure(scrollregion=region)
                    self._applied_sb_region = region
        except Exception:
            pass
        self._sync_sb_height()

    def _sync_sb_height(self) -> None:
        """
        同步待办区高度。

        侧边栏为两段式：上半段（设置/筛选/统计）自动占满剩余空间并可滚动，
        下半段待办清单保持固定高度，保证始终可见。

        重要：**只在高度确实不同时才 configure**。
        无条件 configure 会触发新的 Configure 事件 -> 又回到本方法 -> 无限循环，
        表现为窗口持续抖动（这是 Tkinter resize 的经典陷阱）。
        """
        try:
            fixed = getattr(self, "_todo_fixed_height", None)
            if not fixed:
                return
            # 用已设置值比对（winfo_height 在布局未完成时可能还是旧值）
            if getattr(self, "_todo_applied_height", None) == fixed:
                return          # 已经设置过同样的高度，什么都不做
            self.todo_panel.configure(height=fixed)
            self._todo_applied_height = fixed
        except Exception:
            pass

    def _on_sb_canvas_configure(self, event) -> None:
        """侧边栏宽度变化时同步内嵌 Frame 宽度，并重算高度。"""
        try:
            self._sb_canvas.itemconfigure(self._sb_window, width=event.width)
        except Exception:
            pass
        self._sync_sb_height()

    def _on_sb_wheel(self, event) -> None:
        """侧边栏滚轮滚动。"""
        delta = 0
        if getattr(event, "num", None) == 4:
            delta = -1
        elif getattr(event, "num", None) == 5:
            delta = 1
        elif event.delta:
            delta = -1 if event.delta > 0 else 1
        if delta:
            try:
                self._sb_canvas.yview_scroll(delta * 2, "units")
            except Exception:
                pass
            return "break"

    def _on_todo_resize(self, event) -> None:
        """
        待办区尺寸调整。

        保证待办区不低于最小高度，避免窗口变矮时待办清单被完全压没。
        """
        try:
            if event.height < self._todo_min_height:
                self.todo_panel.pack_propagate(False)
                self.todo_panel.configure(height=self._todo_min_height)
            else:
                self.todo_panel.pack_propagate(True)
        except Exception:
            pass


    def _topmost_var(self) -> tk.BooleanVar:
        if not hasattr(self, "_topmost_v"):
            self._topmost_v = tk.BooleanVar(value=bool(self.storage.get_config("always_on_top", False)))
        return self._topmost_v

    # ============================================================ 数据刷新 ====
    def refresh_all(self) -> None:
        self.refresh_views()
        self.refresh_todos()
        self.refresh_stats()

    def _visible_occurrences(self, start: date, end: date) -> List[Occurrence]:
        """展开区间内全部实例，并按筛选条件过滤。"""
        occs = expand_all(self.storage.events, start, end)
        result = []
        for occ in occs:
            if self.filter_panel.is_active(occ.priority, occ.tag):
                result.append(occ)
        return result

    def refresh_views(self) -> None:
        """根据当前视图刷新显示。"""
        view = self.current_view
        if view == VIEW_MONTH:
            first = self.anchor_date.replace(day=1)
            last = first + timedelta(days=calendar.monthrange(first.year, first.month)[1] - 1)
            # 覆盖整月网格范围（周一开头）
            grid_start = first - timedelta(days=first.weekday())
            grid_end = grid_start + timedelta(days=41)
            occs = self._visible_occurrences(grid_start, grid_end)
            self.month_view.set_anchor(self.anchor_date)
            self.month_view.set_occurrences(occs)
            self.month_view.render()
            self.period_label.configure(text=f"{first.year}年 {first.month}月")
        elif view == VIEW_WEEK:
            start = self.anchor_date - timedelta(days=self.anchor_date.weekday())
            end = start + timedelta(days=6)
            occs = self._visible_occurrences(start, end)
            self.week_view.set_anchor(self.anchor_date)
            self.week_view.set_occurrences(occs)
            self.week_view.render()
            self.period_label.configure(text=f"{start.strftime('%m/%d')} - {end.strftime('%m/%d')}")
        else:
            day = self.anchor_date
            occs = self._visible_occurrences(day, day)
            self.day_view.set_anchor(day)
            self.day_view.set_occurrences(occs)
            self.day_view.render()
            self.period_label.configure(text=day.strftime("%Y年%m月%d日"))

        self._sync_view_buttons()
        self._show_view()

    def _show_view(self) -> None:
        views = {VIEW_MONTH: self.month_view, VIEW_WEEK: self.week_view, VIEW_DAY: self.day_view}
        for key, v in views.items():
            if key == self.current_view:
                v.pack(fill="both", expand=True)
            else:
                v.pack_forget()

    def _sync_view_buttons(self) -> None:
        t = self.theme
        for key, btn in self.view_buttons.items():
            active = key == self.current_view
            btn.configure(bg=t["primary"] if active else t["bg_alt"],
                          fg=t["on_primary"] if active else t["text_dim"])

    def refresh_todos(self) -> None:
        self.todo_panel.set_todos(self.storage.todos)

    def refresh_stats(self) -> None:
        first = self.anchor_date.replace(day=1)
        last = first + timedelta(days=calendar.monthrange(first.year, first.month)[1] - 1)
        month_occ = expand_all(self.storage.events, first, last)
        week_start = self.anchor_date - timedelta(days=self.anchor_date.weekday())
        week_occ = expand_all(self.storage.events, week_start, week_start + timedelta(days=6))
        todos = self.storage.todos
        self.stats_panel.update_stats(
            month_events=len(month_occ),
            week_events=len(week_occ),
            todo_done=sum(1 for x in todos if x.done),
            todo_undone=sum(1 for x in todos if not x.done),
        )

    # ============================================================ 交互动作 ====
    def switch_view(self, view: str) -> None:
        self.current_view = view
        self.storage.set_config("view", view)
        self.refresh_views()

    def go_today(self) -> None:
        self.anchor_date = date.today()
        self.refresh_all()

    def go_prev(self) -> None:
        if self.current_view == VIEW_MONTH:
            self.anchor_date = (self.anchor_date.replace(day=1) - timedelta(days=1)).replace(day=1)
        elif self.current_view == VIEW_WEEK:
            self.anchor_date -= timedelta(days=7)
        else:
            self.anchor_date -= timedelta(days=1)
        self.refresh_all()

    def go_next(self) -> None:
        if self.current_view == VIEW_MONTH:
            nxt = (self.anchor_date.replace(day=1) + timedelta(days=32)).replace(day=1)
            self.anchor_date = nxt
        elif self.current_view == VIEW_WEEK:
            self.anchor_date += timedelta(days=7)
        else:
            self.anchor_date += timedelta(days=1)
        self.refresh_all()

    def on_day_click(self, day: date) -> None:
        """点击日期格：跳到该日并弹出新建表单。"""
        self.anchor_date = day
        if self.current_view != VIEW_DAY:
            self.switch_view(VIEW_DAY)
        else:
            self.refresh_views()
        # date -> datetime，保证表单默认值类型一致
        self.open_event_dialog(default_date=datetime(day.year, day.month, day.day))

    def on_empty_click(self, dt: datetime) -> None:
        """时间轴空白处点击：新建该时刻的日程。"""
        self.open_event_dialog(default_date=dt)

    def on_more_click(self, day: date) -> None:
        """点击 "+N 条"：切到日视图查看全部。"""
        self.anchor_date = day
        self.switch_view(VIEW_DAY)

    def on_event_click(self, occ: Occurrence) -> None:
        """点击日程条目：打开详情。"""
        EventDetailDialog(
            self.root, self.theme_name, occ, self._tag_color(occ.tag),
            on_edit=self._edit_occurrence,
            on_delete=self._delete_occurrence,
        )

    # ---------------------------------------------------------- 日程增删改 ----
    def open_event_dialog(self, event: Optional[Event] = None, default_date=None):
        """
        打开新建/编辑表单。

        default_date 支持 date 或 datetime，统一转成 datetime 传入。
        """
        if isinstance(default_date, date) and not isinstance(default_date, datetime):
            default_date = datetime(default_date.year, default_date.month, default_date.day)
        EventDialog(
            self.root, self.theme_name,
            initial=event,
            default_date=default_date,
            tag_names=self.storage.tag_names(),
            on_save=self._save_event,
            on_tags_changed=self._apply_tags,
        )

    def _save_event(self, event: Event) -> None:
        self.storage.upsert_event(event)
        # 新建/编辑后跳到该日程所在日期并高亮，确保用户能看到结果
        self.anchor_date = event.start.date()
        self.month_view.highlight_id = event.id
        self.refresh_all()
        self._set_status(f"已保存日程：{event.title} @ {event.start.strftime('%m-%d %H:%M')}")

    def _edit_occurrence(self, occ: Occurrence, scope: str) -> None:
        """编辑重复日程实例。scope: all=全部重复项 / this=仅此条。"""
        ev = self.storage.get_event(occ.event.id)
        if ev is None:
            return
        if scope == "all":
            # 编辑母日程
            self.open_event_dialog(event=ev.clone())
        else:
            # 仅此条：把当前实例的时间作为独立日程创建
            new_ev = Event(
                title=occ.title,
                note=occ.note,
                start=occ.start,
                end=occ.end,
                tag=occ.tag,
                priority=occ.priority,
                repeat="none",
                reminders=list(occ.reminders),
            )
            self.storage.upsert_event(new_ev)
            # 母日程中排除该日期
            if occ.date_str not in ev.exceptions:
                ev.exceptions.append(occ.date_str)
            self.storage.upsert_event(ev)
            self.refresh_all()
            self._set_status(f"已创建独立日程：{occ.title}（仅 {occ.date_str}）")

    def _delete_occurrence(self, occ: Occurrence, scope: str) -> None:
        """删除重复日程实例。"""
        ev = self.storage.get_event(occ.event.id)
        if ev is None:
            return
        if scope == "all":
            self.storage.delete_event(ev.id)
            self._set_status(f"已删除日程：{ev.title}")
        else:
            if occ.date_str not in ev.exceptions:
                ev.exceptions.append(occ.date_str)
            self.storage.upsert_event(ev)
            self._set_status(f"已删除 {occ.date_str} 的重复项")
        self.refresh_all()

    # ---------------------------------------------------------- 待办增删改 ----
    def add_todo(self, text: str) -> None:
        todo = Todo(text=text)
        self.storage.upsert_todo(todo)
        self.refresh_todos()
        self.refresh_stats()
        self._set_status(f"已添加待办：{text}")

    def toggle_todo(self, todo: Todo) -> None:
        cur = self.storage.todos
        target = None
        for t in cur:
            if t.id == todo.id:
                target = t
                break
        if target is None:
            return
        target.done = not target.done
        target.done_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S") if target.done else ""
        self.storage.upsert_todo(target)
        self.refresh_todos()
        self.refresh_stats()

    def delete_todo(self, todo: Todo) -> None:
        self.storage.delete_todo(todo.id)
        self.refresh_todos()
        self.refresh_stats()

    # ---------------------------------------------------------- 快捷添加 ----
    def quick_add_event(self) -> None:
        """
        自然语言快捷添加。

        两种模式（由侧边栏「快捷添加后确认」开关控制）：
          - 开启（默认）：解析后弹出完整表单并预填，用户确认无误再保存
                          —— 避免自然语言歧义导致时间/标签写错
          - 关闭：解析成功后直接创建并刷新视图（更快，但无误判保护）
        """
        text = self.quick_entry.get().strip()
        if not text:
            self.open_event_dialog(default_date=datetime.now())
            return
        event = parse_quick(text, today=date.today(),
                            known_tags=self.storage.tag_names())
        if event is None:
            self._set_status("无法识别，请使用完整表单")
            messagebox.showinfo("无法识别",
                                "未能识别该输入的日期/时间。\n\n"
                                "自然语言示例：\n"
                                "  明天下午3点开会\n"
                                "  本周五中午和Alex一起吃饭\n"
                                "  10:00-11:30 项目评审\n\n"
                                "显式标记（零歧义）：\n"
                                "  #标签  标签名\n"
                                "  !高    优先级（高/中/低）\n"
                                "  @10-28 精确日期\n"
                                "  ~90    时长（分钟）\n"
                                "  例：#工作 !高 @10-28 ~1.5h 客户回访",
                                parent=self.root)
            self.open_event_dialog(default_date=datetime.now())
            return
        event.title = event.title or text

        # 新标签自动创建（否则标签信息会丢失）
        if event.tag and event.tag not in self.storage.tag_names():
            if self.storage.ensure_tag(event.tag):
                self.filter_panel.rebuild_tags(self.storage.tag_names())

        # 模式一：弹出表单让用户确认（默认）
        if self.quick_confirm_var.get():
            self.quick_entry.delete(0, "end")
            self._last_event_dialog = EventDialog(
                self.root, self.theme_name,
                initial=event,               # 预填解析结果
                tag_names=self.storage.tag_names(),
                on_save=self._save_event,
                on_tags_changed=self._apply_tags,
            )
            self._set_status("已解析，请在表单中确认后保存")
            return

        # 模式二：直接创建
        self.storage.upsert_event(event)
        self.quick_entry.delete(0, "end")

        # 关键：把视图跳到新日程所在日期，否则用户会以为"没添加成功"。
        #  - 月视图：跳到该月即可（整月可见）
        #  - 周视图：跳到该周（本周内可见）
        #  - 日视图：必须切到那一天，否则停留在今天就看不到未来的日程
        target = event.start.date()
        self.anchor_date = target
        # 标记新日程：月视图中置顶显示并加高亮边框
        self.month_view.highlight_id = event.id
        if self.current_view == VIEW_DAY:
            self.switch_view(VIEW_DAY)
        else:
            self.refresh_views()

        self._set_status(f"已创建日程：{event.title} @ {event.start.strftime('%m-%d %H:%M')}")

    def _on_quick_confirm_toggle(self) -> None:
        """切换「快捷添加后确认」开关。"""
        val = bool(self.quick_confirm_var.get())
        self.storage.set_config("quick_confirm", val)
        self._set_status("快捷添加后将弹出表单确认" if val else "快捷添加将直接保存")

    # ---------------------------------------------------------- 搜索 ----
    def open_search(self) -> None:
        SearchPanel(
            self.root, self.theme_name,
            events=self.storage.events, todos=self.storage.todos,
            on_pick_event=lambda ev: self.on_event_click(
                Occurrence(ev, ev.start, ev.end, ev.start.strftime("%Y-%m-%d"))),
            on_pick_todo=lambda td: self.todo_panel.set_filter("all"),
            on_pick_date=lambda d: self._goto_date(d),
        )

    def _goto_date(self, d: date) -> None:
        self.anchor_date = d
        self.switch_view(VIEW_DAY)
        self.refresh_all()

    # ---------------------------------------------------------- 标签管理 ----
    def manage_tags(self) -> None:
        TagManagerDialog(self.root, self.theme_name, self.storage.tag_names(),
                         self._apply_tags)

    def _apply_tags(self, tag_map: dict) -> None:
        from ..models import Tag
        # 保存标签
        for name, color in tag_map.items():
            found = False
            for tg in self.storage.tags:
                if tg.name == name:
                    tg.color = color
                    found = True
                    break
            if not found:
                self.storage._tags.append(Tag(name, color))
        # 删除已移除的标签（同时清理日程上的引用）
        current = set(tag_map.keys())
        removed = [t.name for t in self.storage.tags if t.name not in current]
        for name in removed:
            for ev in self.storage.events:
                if ev.tag == name:
                    ev.tag = ""
            self.storage._tags = [t for t in self.storage.tags if t.name in current]
        self.storage.save_tags()
        self.storage.save_events()
        self.filter_panel.rebuild_tags(self.storage.tag_names())
        self.refresh_all()

    # ---------------------------------------------------------- 置顶 ----
    def set_topmost(self, on_top: bool, persist: bool = True) -> None:
        """设置主窗口置顶状态。"""
        set_topmost(self.root, on_top)
        try:
            self.root.attributes("-topmost", on_top)
        except Exception:
            pass
        # 变量可能已由勾选框翻转过，这里只在值不一致时纠正，避免多余重绘
        if bool(self._topmost_var().get()) != bool(on_top):
            self._topmost_var().set(on_top)
        if persist:
            self.storage.set_config("always_on_top", on_top)
        self._update_topmost_btn()
        self._set_status("已置顶" if on_top else "已取消置顶")

    def toggle_topmost(self) -> None:
        """
        置顶开关回调。

        两种调用路径：
          1) 勾选框点击 —— CheckCircle._toggle() 已经把变量翻转过了，
             此时直接应用变量当前值即可（**不能再翻转**，否则正反两次
             翻转净效果为零，表现为"点了没反应"）
          2) 快捷键 / 代码直接调用 —— 变量没变，需要主动翻转
        用 self._hover 状态无法区分，改为：勾选框路径传参标记。
        """
        self.set_topmost(bool(self._topmost_var().get()))

    def flip_topmost(self) -> None:
        """主动翻转置顶状态（供快捷键等非勾选框路径调用）。"""
        self.set_topmost(not bool(self._topmost_var().get()))

    def _update_topmost_btn(self) -> None:
        """置顶状态反馈：更新侧边栏勾选框与状态文字。"""
        on = self._topmost_var().get()
        t = self.theme
        # 工具栏的置顶按钮已移除，这里只负责同步侧边栏状态
        switch = getattr(self, "topmost_switch", None)
        if switch is not None:
            try:
                switch.set_theme(t)
            except Exception:
                pass
        self._update_topmost_status()

    def _update_topmost_status(self) -> None:
        on = self._topmost_var().get()
        t = self.theme
        # 未置顶时文案更简短；置顶时给出明确反馈。
        self.topmost_status.configure(text="已置顶（位于所有窗口顶层）" if on else "普通窗口层级",
                                      fg=t["primary"] if on else t["text_dim"])

    # ---------------------------------------------------------- 主题 ----
    def toggle_theme(self) -> None:
        self.theme_name = THEME_DARK if self.theme_name == THEME_LIGHT else THEME_LIGHT
        self.storage.set_config("theme", self.theme_name)
        self.apply_theme()

    def destroy(self) -> None:
        """
        销毁主窗口（停止后台线程 + 释放资源）。

        供测试与优雅退出使用；不会销毁外部传入的 root 之外的东西。
        """
        try:
            self.reminder_engine.stop()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def apply_theme(self) -> None:
        """重新应用主题（销毁并重建所有界面组件）。"""
        self.theme = get_theme(self.theme_name)
        t = self.theme
        apply_ttk_styles(self.root, t)
        self.root.configure(bg=t["bg"])

        # 销毁侧边栏、主区域、工具栏内容并重建
        for child in list(self.sidebar.winfo_children()):
            child.destroy()
        for child in list(self.main_area.winfo_children()):
            child.destroy()
        for child in list(self._toolbar.winfo_children()):
            child.destroy()

        # 重建视图对象
        self.month_view = MonthView(self.main_area, self.theme_name, self.holidays,
                                    on_day_click=self.on_day_click,
                                    on_event_click=self.on_event_click,
                                    on_more_click=self.on_more_click,
                                    on_prev_month=self.go_prev,
                                    on_next_month=self.go_next)
        self.week_view = TimeGridView(self.main_area, self.theme_name, 7, self.holidays,
                                      on_event_click=self.on_event_click,
                                      on_empty_click=self.on_empty_click)
        self.day_view = TimeGridView(self.main_area, self.theme_name, 1, self.holidays,
                                     on_event_click=self.on_event_click,
                                     on_empty_click=self.on_empty_click)
        self.month_view.color_resolver = self._tag_color
        self.week_view.color_resolver = self._tag_color
        self.day_view.color_resolver = self._tag_color

        # 重建工具栏控件
        self._build_toolbar_widgets()
        # 重建侧边栏
        self._build_sidebar()
        self.refresh_all()
    # ---------------------------------------------------------- 导入导出 ----
    def export_data(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="导出备份",
            defaultextension=".json",
            initialfile=f"日程备忘备份_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            return
        data = {
            "app": APP_NAME,
            "version": 1,
            "exported_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "events": [e.to_dict() for e in self.storage.events],
            "todos": [t.to_dict() for t in self.storage.todos],
            "tags": [t.to_dict() for t in self.storage.tags],
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                import json
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            messagebox.showerror("导出失败", f"无法写入文件：\n{exc}", parent=self.root)
            return
        self._set_status(f"已导出到：{path}")
        messagebox.showinfo("导出成功", f"备份已保存到：\n{path}", parent=self.root)

    def import_data(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.root,
            title="导入备份",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                import json
                data = json.load(f)
        except Exception as exc:
            messagebox.showerror("导入失败", f"文件读取失败或格式错误：\n{exc}", parent=self.root)
            return

        if not isinstance(data, dict) or "events" not in data:
            messagebox.showerror("导入失败", "文件格式不正确，缺少 events 字段。", parent=self.root)
            return

        mode = self._ask_import_mode()
        if not mode:
            return

        if mode == "overwrite":
            # 覆盖：清空原有数据
            self.storage._events = []
            self.storage._todos = []
            self.storage._tags = []

        # 合并导入
        existing_event_ids = {e.id for e in self.storage.events}
        for item in data.get("events", []):
            ev = Event.from_dict(item)
            if ev is None:
                continue
            if ev.id in existing_event_ids:
                ev.id = new_id()  # 冲突则重新生成 ID，避免覆盖已有日程
            self.storage._events.append(ev)
        existing_todo_ids = {t.id for t in self.storage.todos}
        for item in data.get("todos", []):
            td = Todo.from_dict(item)
            if td is None:
                continue
            if td.id in existing_todo_ids:
                td.id = new_id()
            self.storage._todos.append(td)
        existing_tags = {t.name for t in self.storage.tags}
        for item in data.get("tags", []):
            tag = Tag.from_dict(item)
            if tag.name not in existing_tags:
                self.storage._tags.append(tag)

        self.storage.save_events()
        self.storage.save_todos()
        self.storage.save_tags()
        self.filter_panel.rebuild_tags(self.storage.tag_names())
        self.refresh_all()
        self._set_status(f"已导入：{path}")
        messagebox.showinfo("导入成功", f"数据已导入。\n方式：{'覆盖' if mode == 'overwrite' else '合并'}",
                            parent=self.root)

    def _ask_import_mode(self) -> Optional[str]:
        """询问导入方式：merge 合并 / overwrite 覆盖。"""
        win = tk.Toplevel(self.root)
        win.title("导入方式")
        win.configure(bg=self.theme["bg"])
        win.resizable(False, False)
        win.transient(self.root)
        t = self.theme
        tk.Label(win, text="选择导入方式", bg=t["bg"], fg=t["text"],
                 font=typography.h2('bold')).pack(pady=(16, 8))
        result = {"mode": None}

        def choose(m):
            result["mode"] = m
            try:
                win.grab_release()
            except Exception:
                pass
            win.destroy()

        frame = tk.Frame(win, bg=t["bg"])
        frame.pack(fill="x", padx=16, pady=(0, 8))
        ttk.Button(frame, text="合并导入\n（保留现有数据）", command=lambda: choose("merge")).pack(
            side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(frame, text="覆盖原有\n（清空后导入）", command=lambda: choose("overwrite")).pack(
            side="left", fill="x", expand=True)
        ttk.Button(win, text="取消", command=lambda: choose(None)).pack(pady=(4, 16))
        win.bind("<Escape>", lambda e: choose(None))
        # 关键：布局完成并显示后再 grab，避免锁死
        win.update_idletasks()
        win.update()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - w) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - h) // 2
        win.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")
        try:
            win.grab_set()
        except Exception:
            pass
        self.root.wait_window(win)
        return result["mode"]

    # ---------------------------------------------------------- 提醒 ----
    def _on_reminder_fire(self, pending) -> None:
        """提醒引擎（后台线程）回调 —— 切回主线程弹窗。"""
        self.root.after(0, lambda: self._show_reminders(pending))

    def _show_reminders(self, pending) -> None:
        for occ, minutes in pending:
            popup = ReminderPopup(
                self.root, occ, minutes, self.theme_name,
                sound_enabled=bool(self.sound_var.get()),
                sound_kind=self.sound_kind.get(),
                on_snooze=self._on_snooze,
                on_close=lambda: None,
            )
            self._popups.append(popup)
        # 清理已关闭的弹窗引用
        self._popups = [p for p in self._popups if not p._closed]
        if pending:
            self._set_status(f"⏰ 提醒：{pending[0][0].title}")

    def _on_snooze(self, occ: Occurrence, minutes_before: int, delay: int) -> None:
        self.reminder_engine.snooze(occ.event.id, occ.date_str, minutes_before, delay)
        self._set_status(f"已推迟 {delay} 分钟提醒：{occ.title}")

    def _on_sound_toggle(self) -> None:
        self.storage.set_config("sound", bool(self.sound_var.get()))

    def _on_sound_kind_change(self, _event=None) -> None:
        """切换提示音种类（立即试听）。"""
        from ..sound import SOUND_PRESETS, play_sound
        label = self.sound_kind.get()
        # 下拉框存的是显示名，需映射回内部 key
        key = label
        for k, lb in SOUND_PRESETS:
            if lb == label:
                key = k
                break
        self.storage.set_config("sound_kind", key)
        play_sound(key)
        self._set_status(f"提示音已切换：{label}")

    @staticmethod
    def _sound_label(kind: str) -> str:
        from ..sound import SOUND_PRESETS
        for k, label in SOUND_PRESETS:
            if k == kind:
                return label
        return kind

    # ---------------------------------------------------------- 托盘 ----
    def _setup_tray(self) -> None:
        from ..tray import TrayManager, TRAY_AVAILABLE
        if not TRAY_AVAILABLE:
            self._set_status("提示：未安装 pystray，关闭窗口将直接退出（pip install pystray pillow 可启用托盘）")
            return
        self.tray = TrayManager(
            on_open=self._restore_from_tray,
            on_toggle_topmost=self.flip_topmost,
            on_quit=self._quit_app,
        )
        if self.tray.start(APP_NAME):
            self._set_status("已启动系统托盘，关闭窗口将最小化到托盘")

    def _restore_from_tray(self) -> None:
        bring_to_front(self.root)
        self._set_status("已从托盘恢复")

    def _on_close_request(self) -> None:
        """关闭窗口：若有托盘则最小化到托盘，否则退出。"""
        if self.tray and self.tray.icon is not None:
            self.root.withdraw()
            self._set_status("已最小化到托盘，后台继续监听提醒")
        else:
            if messagebox.askyesno("退出", "是否退出程序？\n（未启用系统托盘，退出后不再提醒）",
                                   parent=self.root):
                self._quit_app()

    def _quit_app(self) -> None:
        """彻底退出。"""
        try:
            self.reminder_engine.stop()
        except Exception:
            pass
        if self.tray:
            self.tray.stop()
        try:
            self.root.destroy()
        except Exception:
            pass
        os._exit(0)

    # ---------------------------------------------------------- 杂项 ----
    def _tag_color(self, tag_name: str) -> str:
        if not tag_name:
            return self.theme["tag_default"]
        return self.storage.tag_color(tag_name)

    def _set_status(self, text: str) -> None:
        try:
            self.status_bar.configure(text=text)
        except Exception:
            pass

    def _restore_geometry(self) -> None:
        """恢复上次窗口位置与尺寸。"""
        geom = self.storage.get_config("geometry")
        if geom:
            try:
                self.root.geometry(geom)
            except Exception:
                pass
        self.root.bind("<Configure>", self._on_configure, add="+")

    def _on_configure(self, event) -> None:
        """
        窗口尺寸变化处理。

        三层防护，缺一不可：
          1) 尺寸未变直接返回 —— 挡掉绝大多数重复事件
          2) 抖动检测 —— 若尺寸在 3 像素内反复跳动（典型的布局震荡），
             停止重绘，避免界面持续抖动
          3) 防抖 120ms —— 合并拖拽产生的连续事件
        """
        if event.widget is not self.root:
            return
        w = event.widget.winfo_width()
        h = event.widget.winfo_height()
        if w <= 1 or h <= 1:
            return

        # 尺寸未变化 -> 不做任何事
        if (w, h) == getattr(self, "_last_size", None):
            return
        self._last_size = (w, h)

        # ---- 拖拽检测 ----
        # 连续 200ms 内的多次尺寸变化 = 用户正在拖拽窗口边缘。
        # 拖拽过程中**完全不做重绘**（Tkinter 社区通用实践：resize 是高频信号，
        # 在回调里做重活会导致明显卡顿）。等用户松手后再统一重绘一次。
        now = time.monotonic()
        last_change = getattr(self, "_last_size_change_at", 0.0)
        self._last_size_change_at = now
        if now - last_change < 0.2:
            self._is_dragging = True
        else:
            self._is_dragging = False

        if self._is_dragging:
            # 拖拽中：只重置防抖定时器，绝不重绘
            self._schedule_resize(160)
            return

        # ---- 抖动检测 ----
        # 连续多次尺寸变化但总幅度极小（<= 3px）-> 判定为布局震荡，冻结重绘
        hist = getattr(self, "_size_history", None)
        if hist is None:
            hist = []
        hist.append((w, h))
        if len(hist) > 8:
            hist.pop(0)
        self._size_history = hist

        if len(hist) >= 4:
            xs = [p[0] for p in hist]
            ys = [p[1] for p in hist]
            if (max(xs) - min(xs)) <= 3 and (max(ys) - min(ys)) <= 3:
                self._jitter_frozen = True
            else:
                self._jitter_frozen = False
        else:
            self._jitter_frozen = False

        if getattr(self, "_jitter_frozen", False):
            return

        self._schedule_resize(120)

    def _schedule_resize(self, delay_ms: int) -> None:
        """
        安排一次尺寸刷新（防抖）。

        成熟做法：取消上一次待执行的定时器，排入新的。
        连续 resize 事件只会保留最后���次。
        """
        try:
            if getattr(self, "_resize_job", None):
                self.root.after_cancel(self._resize_job)
        except Exception:
            pass
        self._resize_job = self.root.after(delay_ms, self._apply_resize)

    def _apply_resize(self) -> None:
        """窗口尺寸稳定后执行重绘。"""
        self._resize_job = None
        # 震荡解除后清空历史，允许后续正常重绘
        if getattr(self, "_jitter_frozen", False):
            self._size_history = []
            self._jitter_frozen = False
        try:
            # 侧边栏高度需要随窗口高度重新分配（设置区 vs 待办区）
            if getattr(self, "_sync_sb_height", None):
                self._sync_sb_height()
        except Exception:
            pass
        try:
            # 只重绘视图，不动数据（避免重新展开重复日程的开销）
            view = {"month": self.month_view, "week": self.week_view, "day": self.day_view}.get(
                self.current_view)
            if view is not None:
                # 走视图自己的防抖调度（schedule_render），
                # 避免主窗口与视图各自渲染造成重复绘制。
                if hasattr(view, "schedule_render"):
                    view.schedule_render()
                elif hasattr(view, "render"):
                    view.render()
        except Exception:
            pass
        # 记录窗口位置（延迟写入配置文件）
        try:
            self._save_geometry_job = self.root.after(500, self._save_geometry)
        except Exception:
            pass

    def _save_geometry(self) -> None:
        """保存窗口位置与尺寸。"""
        try:
            self.storage.set_config("geometry", self.root.winfo_geometry())
        except Exception:
            pass
