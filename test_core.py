# -*- coding: utf-8 -*-
"""
核心逻辑自测脚本（不依赖图形界面）。

运行：python test_core.py
覆盖：重复规则展开 / 单次例外 / 自然语言解析 / 存储容错 / 提醒计算 / 节假日。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {extra}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


# ---------------------------------------------------------------- 重复展开 ----
def test_recurrence() -> None:
    from app.models import Event
    from app.recurrence import expand, expand_all

    section("重复规则展开")

    # 每天（母日程起始 03-02，故区间 03-01~03-05 内只展开 4 天）
    ev = Event(title="打卡", start=datetime(2026, 3, 2, 9, 0),
               end=datetime(2026, 3, 2, 9, 30), repeat="daily")
    occ = expand(ev, date(2026, 3, 1), date(2026, 3, 5))
    check("每天展开 4 天（从起始日算）", len(occ) == 4, f"实际 {len(occ)}")
    check("每天保留时间", occ[0].start.hour == 9 and occ[0].start.minute == 0)
    occ_all = expand(ev, date(2026, 3, 1), date(2026, 3, 31))
    check("每天整月展开 30 天", len(occ_all) == 30, f"实际 {len(occ_all)}")

    # 每周（周一、周三）
    ev2 = Event(title="周会", start=datetime(2026, 3, 2, 14, 0),
                end=datetime(2026, 3, 2, 15, 0), repeat="weekly",
                repeat_weekdays=[0, 2])
    occ2 = expand(ev2, date(2026, 3, 1), date(2026, 3, 15))
    dates = [o.start.date() for o in occ2]
    check("每周展开 4 次", len(occ2) == 4, f"实际 {len(occ2)} {dates}")
    check("每周落在周一/周三", all(d.weekday() in (0, 2) for d in dates), str(dates))

    # 每月
    ev3 = Event(title="月会", start=datetime(2026, 1, 15, 10, 0),
                end=datetime(2026, 1, 15, 11, 0), repeat="monthly")
    occ3 = expand(ev3, date(2026, 1, 1), date(2026, 6, 30))
    check("每月展开 6 次", len(occ3) == 6, f"实际 {len(occ3)}")
    check("每月保持 15 号", all(o.start.day == 15 for o in occ3))

    # 每年
    ev4 = Event(title="年会", start=datetime(2026, 6, 8, 18, 0),
                end=datetime(2026, 6, 8, 21, 0), repeat="yearly")
    occ4 = expand(ev4, date(2026, 1, 1), date(2029, 12, 31))
    check("每年展开 4 次", len(occ4) == 4, f"实际 {len(occ4)}")

    # 截止日期
    ev5 = Event(title="限时", start=datetime(2026, 3, 1, 8, 0),
                end=datetime(2026, 3, 1, 8, 30), repeat="daily",
                repeat_until="2026-03-05")
    occ5 = expand(ev5, date(2026, 3, 1), date(2026, 3, 31))
    check("重复截止生效", len(occ5) == 5, f"实际 {len(occ5)}")

    # 单次删除
    ev6 = Event(title="例外", start=datetime(2026, 3, 1, 8, 0),
                end=datetime(2026, 3, 1, 8, 30), repeat="daily",
                exceptions=["2026-03-03"])
    occ6 = expand(ev6, date(2026, 3, 1), date(2026, 3, 5))
    check("单次删除剔除该日", len(occ6) == 4 and
              all(o.start.date() != date(2026, 3, 3) for o in occ6), f"实际 {len(occ6)}")

    # 单次修改
    ev7 = Event(title="原标题", start=datetime(2026, 3, 1, 8, 0),
                end=datetime(2026, 3, 1, 8, 30), repeat="daily",
                overrides={"2026-03-02": {"title": "改过的", "start": "2026-03-02T16:00:00",
                                          "end": "2026-03-02T17:00:00"}})
    occ7 = expand(ev7, date(2026, 3, 1), date(2026, 3, 3))
    t2 = [o for o in occ7 if o.start.date() == date(2026, 3, 2)][0]
    check("单次修改标题生效", t2.title == "改过的", t2.title)
    check("单次修改时间生效", t2.start.hour == 16, str(t2.start))

    # 不重复
    ev8 = Event(title="单次", start=datetime(2026, 3, 1, 8, 0),
                end=datetime(2026, 3, 1, 9, 0))
    occ8 = expand(ev8, date(2026, 3, 1), date(2026, 3, 31))
    check("不重复只展开 1 次", len(occ8) == 1, f"实际 {len(occ8)}")

    # 跨天日程
    ev9 = Event(title="出差", start=datetime(2026, 3, 1, 9, 0),
                end=datetime(2026, 3, 3, 18, 0))
    occ9 = expand(ev9, date(2026, 3, 1), date(2026, 3, 10))
    check("跨天日程保持时长", (occ9[0].end - occ9[0].start).days == 2)

    # 排序
    occ10 = expand_all([ev2, ev], date(2026, 3, 1), date(2026, 3, 10))
    check("批量展开按时间排序", all(occ10[i].start <= occ10[i + 1].start
                                for i in range(len(occ10) - 1)))


# ---------------------------------------------------------------- 自然语言 ----
def test_nlp() -> None:
    from app.nlp import parse_quick

    section("自然语言解析")
    today = date(2026, 10, 21)  # 周三

    ev = parse_quick("明天下午3点开会", today)
    check("明天下午3点 -> 解析成功", ev is not None)
    if ev:
        check("明天下午3点 -> 日期", ev.start.date() == date(2026, 10, 22), str(ev.start))
        check("明天下午3点 -> 15:00", ev.start.hour == 15, str(ev.start))
        check("明天下午3点 -> 标题", ev.title == "开会", ev.title)

    ev = parse_quick("后天 10:00-11:30 项目评审", today)
    check("区间时间 -> 解析成功", ev is not None)
    if ev:
        check("区间时间 -> 开始 10:00", ev.start.hour == 10 and ev.start.minute == 0)
        check("区间时间 -> 结束 11:30", ev.end.hour == 11 and ev.end.minute == 30)
        check("区间时间 -> 标题", ev.title == "项目评审", ev.title)

    ev = parse_quick("下周一上午10点 客户拜访", today)
    check("下周一 -> 解析成功", ev is not None)
    if ev:
        check("下周一 -> 日期正确", ev.start.date() == date(2026, 10, 26), str(ev.start.date()))
        check("下周一 -> 10:00", ev.start.hour == 10)

    ev = parse_quick("3天后 晚上8点 聚餐", today)
    check("N天后 -> 解析成功", ev is not None)
    if ev:
        check("N天后 -> 日期", ev.start.date() == date(2026, 10, 24), str(ev.start.date()))
        check("N天后 -> 20:00", ev.start.hour == 20)

    ev = parse_quick("12月25日 上午10点 圣诞聚会", today)
    check("绝对日期 -> 解析成功", ev is not None)
    if ev:
        check("绝对日期 -> 12/25", ev.start.month == 12 and ev.start.day == 25)
        check("绝对日期 -> 10:00", ev.start.hour == 10)

    ev = parse_quick("明天 全天 出差", today)
    check("全天 -> 解析成功", ev is not None)
    if ev:
        check("全天标记", ev.all_day is True)

    ev = parse_quick("每天早上9点 打卡", today)
    check("重复规则 -> daily", ev is not None and ev.repeat == "daily",
          getattr(ev, "repeat", None))

    ev = parse_quick("每周一 站会", today)
    check("每周一 -> weekly", ev is not None and ev.repeat == "weekly" and 0 in ev.repeat_weekdays,
          getattr(ev, "repeat_weekdays", None))

    ev = parse_quick("随便写点什么")
    check("无法解析返回 None", ev is None, str(ev))
    ev = parse_quick("下周三晚上8点半 晚餐", today)
    if ev:
        check("半点解析", ev.start.minute == 30, str(ev.start))


# ---------------------------------------------------------------- 存储容错 ----
def test_storage() -> None:
    from app import config as cfg
    from app.models import Event, Todo
    from app.storage import Storage
    import pathlib

    section("存储层与容错")

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="calmemo_test_"))
    # 指向临时目录（storage 通过 config 模块动态取路径，此处重定向即可生效）
    cfg.EVENTS_FILE = tmp / "events.json"
    cfg.TODOS_FILE = tmp / "todos.json"
    cfg.TAGS_FILE = tmp / "tags.json"
    cfg.CONFIG_FILE = tmp / "config.json"
    cfg.REMINDER_STATE_FILE = tmp / "reminder_state.json"
    cfg.HOLIDAYS_FILE = tmp / "holidays.json"

    st = Storage()
    check("默认标签自动创建", len(st.tag_names()) >= 4, str(st.tag_names()))

    ev = Event(title="测试日程", start=datetime(2026, 3, 1, 9, 0),
               end=datetime(2026, 3, 1, 10, 0), tag="工作", priority="high")
    st.upsert_event(ev)
    st.upsert_todo(Todo(text="测试待办"))
    check("日程已保存", len(st.events) == 1)
    check("待办已保存", len(st.todos) == 1)

    # 重新加载验证落盘
    st2 = Storage()
    check("重载后日程仍在", len(st2.events) == 1 and st2.events[0].title == "测试日程")
    check("重载后标签仍在", st2.events[0].tag == "工作")

    # 损坏文件容错
    cfg.EVENTS_FILE.write_text("{ this is not valid json ]]", encoding="utf-8")
    st3 = Storage()
    check("文件损坏不崩溃，返回空列表", len(st3.events) == 0)
    check("损坏文件已备份", any(".corrupt_" in p.name for p in cfg.EVENTS_FILE.parent.iterdir()))

    # 配置项持久化
    st.set_config("always_on_top", True)
    st2b = Storage()
    check("配置单独持久化", st2b.get_config("always_on_top") is True)
    check("配置与数据分离（不同文件）", cfg.CONFIG_FILE != cfg.EVENTS_FILE)

    # 提醒触发记录
    st.mark_reminder_fired("k1")
    st.mark_reminder_fired("k2")
    st4 = Storage()
    check("提醒已触发记录持久化", "k1" in st4.fired_reminders())


# ---------------------------------------------------------------- 提醒引擎 ----
def test_reminder() -> None:
    from app import config as cfg
    from app.models import Event
    from app.storage import Storage
    from app.reminder import ReminderEngine, make_key
    import pathlib

    section("提醒引擎")

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="calmemo_rem_"))
    cfg.EVENTS_FILE = tmp / "events.json"
    cfg.TODOS_FILE = pathlib.Path(tmp) / "todos.json"
    cfg.TAGS_FILE = pathlib.Path(tmp) / "tags.json"
    cfg.CONFIG_FILE = pathlib.Path(tmp) / "config.json"
    cfg.REMINDER_STATE_FILE = pathlib.Path(tmp) / "reminder_state.json"
    cfg.HOLIDAYS_FILE = pathlib.Path(tmp) / "holidays.json"

    fired = []
    st = Storage()
    engine = ReminderEngine(st, lambda p: fired.extend(p))

    # 1 小时后开始、提前 15 分钟提醒 -> 现在就该触发
    now = datetime.now()
    ev = Event(title="马上提醒", start=now + timedelta(minutes=10),
               end=now + timedelta(minutes=70), reminders=[15])
    st.upsert_event(ev)
    engine.tick()
    check("提前提醒已触发", len(fired) == 1, f"实际 {len(fired)}")

    # 已触发的不再重复
    fired.clear()
    engine.tick()
    check("已触发不重复弹窗", len(fired) == 0, f"实际 {len(fired)}")

    # 未来很久的不触发
    fired.clear()
    ev2 = Event(title="很久以后", start=now + timedelta(days=5),
                end=now + timedelta(days=5, hours=1), reminders=[0])
    st.upsert_event(ev2)
    engine.tick()
    check("未来日程不触发", len(fired) == 0, f"实际 {len(fired)}")

    # 稍后提醒
    fired.clear()
    ev3 = Event(title="稍后", start=now + timedelta(minutes=5),
                end=now + timedelta(minutes=65), reminders=[15])
    st.upsert_event(ev3)
    engine.tick()
    check("稍后场景首次触发", len(fired) == 1)
    if fired:
        occ, minutes = fired[0]
        engine.snooze(occ.event.id, occ.date_str, minutes, 30)
        fired.clear()
        engine.tick()
        check("稍后提醒期间不重复弹窗", len(fired) == 0, f"实际 {len(fired)}")


# ---------------------------------------------------------------- 节假日 ----
def test_holidays() -> None:
    from app.holidays import HolidayProvider

    section("节假日")
    hp = HolidayProvider()
    check("元旦是节假日", hp.is_holiday(date(2026, 1, 1)))
    check("国庆是节假日", hp.is_holiday(date(2026, 10, 1)))
    # 10-13 是普通工作日（周三，假期已过）
    check("普通工作日不是节假日", not hp.is_holiday(date(2026, 10, 13)))
    # 10-17 是普通周六（10-10 是调休上班日，故不能用作普通周末样本）
    check("普通周六是休息日", hp.is_rest_day(date(2026, 10, 17)))
    check("普通工作日是上班日", hp.is_workday(date(2026, 10, 13)))
    check("调休上班日不是休息日", not hp.is_rest_day(date(2026, 10, 10)))
    check("调休上班日是上班日", hp.is_workday(date(2026, 10, 10)))
    check("调休上班日标记为班", hp.label_of(date(2026, 10, 10)) == "班",
          hp.label_of(date(2026, 10, 10)))
    check("节假日名称可取", hp.name_of(date(2026, 10, 1)) == "国庆节")


# ---------------------------------------------------------------- 模型 ----
def test_models() -> None:
    from app.models import Event, Todo, from_iso, to_iso

    section("模型序列化")
    ev = Event(title="往返", start=datetime(2026, 3, 1, 9, 0),
               end=datetime(2026, 3, 1, 10, 30), tag="会议",
               priority="high", reminders=[0, 15], repeat="weekly",
               repeat_weekdays=[0, 3], note="备注内容")
    d = ev.to_dict()
    ev2 = Event.from_dict(d)
    check("往返序列化一致", ev2.title == ev.title and ev2.note == ev.note)
    check("时间往返一致", ev2.start == ev.start and ev2.end == ev.end)
    check("提醒列表往返", ev2.reminders == [0, 15])
    check("重复规则往返", ev2.repeat == "weekly" and ev2.repeat_weekdays == [0, 3])
    check("ISO 解析", from_iso("2026-03-01T09:00:00") == datetime(2026, 3, 1, 9, 0))
    check("ISO 解析容错", from_iso("乱码") is None)

    td = Todo(text="待办 A")
    td2 = Todo.from_dict(td.to_dict())
    check("待办往返", td2.text == "待办 A" and td2.done is False)
    check("空待办被拒绝", Todo.from_dict({"text": "  "}) is None)


if __name__ == "__main__":
    print("日程备忘 —— 核心逻辑自测")
    test_models()
    test_recurrence()
    test_nlp()
    test_storage()
    test_reminder()
    test_holidays()
    print(f"\n{'=' * 46}")
    print(f"通过 {PASS} 项，失败 {FAIL} 项")
    print("=" * 46)
    sys.exit(1 if FAIL else 0)
