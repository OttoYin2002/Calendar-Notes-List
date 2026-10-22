# -*- coding: utf-8 -*-
"""
自然语言快捷添加解析器。

支持示例：
  "明天下午3点开会"            -> 明天下午 15:00 开始，默认 1 小时
  "后天 10:00-11:30 项目评审"   -> 后天 10:00-11:30
  "下周一下午2点 客户拜访"      -> 下周一 14:00
  "3天后 晚上8点 聚餐"          -> 3天后 20:00
  "12月25日 上午10点 圣诞聚会"  -> 12月25日 10:00
  "明天 全天 出差"              -> 明天的全天日程
  "每天早上9点 打卡"            -> 每天 09:00（重复规则）

解析失败返回 None，调用方应回退到完整表单。
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Optional, Tuple

from .models import Event

CN_NUM = {"零": 0, "一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

# 星期映射：中文星期 -> 0=周一 ... 6=周日（与 date.weekday() 一致）
WD_CN = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}


def _wd_to_index(ch: str) -> Optional[int]:
    """中文/数字星期字符 -> 0~6（0=周一）。"""
    if ch in WD_CN:
        return WD_CN[ch]
    if ch.isdigit():
        return (int(ch) - 1) % 7
    return None

REL_DAYS = {
    "今天": 0, "今日": 0, "本日": 0,
    "明天": 1, "明日": 1, "后天": 2, "大后天": 3, "昨天": -1, "前天": -2,
}

PERIOD_OFFSETS = {
    "凌晨": 0, "早上": 8, "早晨": 8, "清晨": 6, "上午": 9, "中午": 12,
    "下午": 12, "傍晚": 18, "晚上": 12, "夜里": 12, "晚": 12, "下午傍晚": 18,
}

# 各时段词在「没有具体钟点」时的代表时刻。
# 例如「本周五中午吃饭」-> 12:00（而不是被丢弃后落到默认 9:00）。
PERIOD_DEFAULT_HOUR = {
    "凌晨": 0, "清晨": 6, "早上": 8, "早晨": 8, "上午": 9,
    "中午": 12, "下午": 14, "下午傍晚": 17, "傍晚": 18,
    "晚上": 19, "夜里": 21, "晚": 19,
}

# 常见口语时间点
NUM_HOUR = {
    "三": 3, "三点": 3, "八": 8, "八点": 8, "九": 9, "九点": 9, "十": 10, "十点": 10,
    "十一": 11, "十二": 12, "一": 1, "一点": 1, "两": 2, "二": 2, "两点": 2, "五": 5, "五点": 5,
    "六": 6, "六点": 6, "七": 7, "七点": 7,
}


def _cn_to_int(text: str) -> Optional[int]:
    """把中文数字（0-23 范围内够用）转成整数。"""
    text = text.strip()
    if text.isdigit():
        return int(text)
    if text in CN_NUM:
        return CN_NUM[text]
    if text.startswith("十") and len(text) == 2:
        return 10 + CN_NUM.get(text[1], 0)
    if text.endswith("十") and len(text) == 2:
        return CN_NUM.get(text[0], 0) * 10
    if len(text) == 3 and text[1] == "十":
        return CN_NUM.get(text[0], 0) * 10 + CN_NUM.get(text[2], 0)
    return None


# 自然语言优先级关键词 -> 标准键
# 注意：顺序有意义，长的表达放前面，避免"高优先级"被"高"抢先匹配
NL_PRIORITY_WORDS = [
    ("高优先级", "high"), ("非常重要", "high"), ("紧急重要", "high"),
    ("不重要", "low"), ("低优先级", "low"), ("不着急", "low"), ("不急", "low"),
    ("一般优先", "normal"), ("优先级高", "high"), ("优先级低", "low"),
    ("重要", "high"), ("紧急", "high"), ("关键", "high"),
    ("普通", "normal"), ("一般", "normal"), ("正常", "normal"), ("常规", "normal"),
    ("次要", "low"), ("有空", "low"),
]

# 自然语言标签表述：<标签名>标签 / 标签<标签名>
# 注意：标签名不允许含数字，否则"明天下午3点标签"会把时间当成标签名。
NL_TAG_PATTERNS = [
    re.compile(r"([一-龥A-Za-z]{1,6})\s*标签"),
    re.compile(r"标签\s*([一-龥A-Za-z]{1,6})"),
]

# 不能作为标签名的词（时间/日期/动词等），避免"标签 明天"这类误判
_TAG_STOPWORDS = {
    "明", "今天", "明天", "后天", "昨天", "前天", "上午", "下午", "中午", "晚上",
    "早上", "傍晚", "凌晨", "点", "开会", "拜访", "会议", "日程", "提醒", "今天",
    "本月", "下月", "上月", "周", "星期", "礼拜", "号", "日",
}


def _is_valid_tag_name(name: str) -> bool:
    """判断提取到的字符串是否像一个合法的标签名。"""
    if not name or len(name) > 6:
        return False
    if name in _TAG_STOPWORDS:
        return False
    # 含数字且不是纯英文/中文词（如"下午3点"）-> 不是标签
    if any(ch.isdigit() for ch in name):
        return False
    # 含明显的时间后缀
    if name.endswith(("点", "分", "号", "日")):
        return False
    return True


def _parse_meta_words(text: str) -> Tuple[Optional[str], Optional[str], str]:
    """
    从自然语言中提取标签与优先级。

    返回 (标签, 优先级, 去掉这些词后的文本)。
    """
    remain = text
    tag: Optional[str] = None
    priority: Optional[str] = None

    # 优先级
    for word, key in NL_PRIORITY_WORDS:
        if word in remain:
            priority = key
            remain = remain.replace(word, " ", 1)
            break

    # 标签：优先匹配已知标签名，其次匹配"XX标签"句式
    for pat in NL_TAG_PATTERNS:
        m = pat.search(remain)
        if m:
            name = m.group(1).strip()
            if _is_valid_tag_name(name):
                tag = name
                remain = remain[:m.start()] + " " + remain[m.end():]
                break
            # 提取到的不是合法标签名 -> 尝试下一个模式
            continue

    remain = re.sub(r"\s+", " ", remain).strip()
    return tag, priority, remain


def _month_edge(today: date, kind: str = "start", offset: int = 0) -> date:
    """
    计算某月的月初 / 月底。

    :param kind:   "start" 月初，"end" 月底
    :param offset: 0=本月，1=下月，-1=上月
    """
    import calendar as _cal
    y = today.year
    m = today.month + offset
    while m > 12:
        m -= 12
        y += 1
    while m < 1:
        m += 12
        y -= 1
    if kind == "end":
        return date(y, m, _cal.monthrange(y, m)[1])
    return date(y, m, 1)


# 中文数字 -> 阿拉伯数字（用于"二十八号"这类表达）
_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
               "六": 6, "七": 7, "八": 8, "九": 9}


def _cn_number(text: str) -> Optional[int]:
    """把中文数字转成整数，支持 一 ~ 九十九。"""
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text in _CN_DIGITS:
        return _CN_DIGITS[text]
    if "十" in text:
        head, _, tail = text.partition("十")
        tens = _CN_DIGITS.get(head, 1) if head else 1
        ones = _CN_DIGITS.get(tail, 0) if tail else 0
        return tens * 10 + ones
    if len(text) == 1:
        return _CN_DIGITS.get(text)
    return None


def _parse_cn_day(text: str, today: date) -> Optional[Tuple[date, Tuple[int, int]]]:
    """
    解析中文"几号"表达。

    支持：
      本月28号 / 这个月28号 / 28号 / 28日
      下月28号 / 下个月28号
      上月28号
      二十八号

    返回 (日期, 匹配区间) 或 None。
    """
    # 前缀：明确"本月/下月/上月"
    prefix_pat = r"(本月|这个月|这月|下月|下个月|下月个|上月|上个月)"
    m = re.search(prefix_pat + r"\s*(\d{1,2}|[一二两三四五六七八九十]{1,3})\s*[日号]", text)
    if m:
        num = _cn_number(m.group(2))
        if num and 1 <= num <= 31:
            prefix = m.group(1)
            offset = 0
            if prefix.startswith("下"):
                offset = 1
            elif prefix.startswith("上"):
                offset = -1
            base = _month_edge(today, "start", offset=offset)
            try:
                d = base.replace(day=num)
            except ValueError:
                return None
            if offset == 0 and d < today:
                # 本月该日已过 -> 顺延到下月
                d = _month_edge(today, "start", offset=1).replace(day=num)
            return d, (m.start(), m.end())

    # 裸 "28号" / "28日"：本月；若已过则下月
    m = re.search(r"(\d{1,2}|[一二两三四五六七八九十]{1,3})\s*[日号](?!\d)", text)
    if m:
        num = _cn_number(m.group(1))
        if num and 1 <= num <= 31:
            try:
                d = today.replace(day=num)
            except ValueError:
                return None
            if d < today:
                d = _month_edge(today, "start", offset=1).replace(day=num)
            return d, (m.start(), m.end())
    return None


def _parse_date_part(text: str, today: date) -> Tuple[Optional[date], str]:
    """
    从文本中解析日期。返回 (日期, 去掉日期后的剩余文本)。
    未找到日期时返回 (None, 原文)。
    """
    remain = text

    # 1) 绝对日期：2026-10-21 / 2026/10/21 / 10月21日 / 10-21
    m = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?", remain)
    if m:
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return d, remain[:m.start()] + remain[m.end():]
        except ValueError:
            pass

    m = re.search(r"(\d{1,2})月(\d{1,2})[日号]", remain)
    if m:
        try:
            d = date(today.year, int(m.group(1)), int(m.group(2)))
            if d < today:
                d = date(today.year + 1, int(m.group(1)), int(m.group(2)))
            return d, remain[:m.start()] + remain[m.end():]
        except ValueError:
            pass

    m = re.search(r"(\d{1,2})[-/](\d{1,2})(?![\d:/-])", remain)
    if m:
        try:
            d = date(today.year, int(m.group(1)), int(m.group(2)))
            if d < today:
                d = date(today.year + 1, int(m.group(1)), int(m.group(2)))
            return d, remain[:m.start()] + remain[m.end():]
        except ValueError:
            pass

    # 2) 相对日期
    for word, delta in REL_DAYS.items():
        if word in remain:
            d = today + timedelta(days=delta)
            return d, remain.replace(word, " ", 1)

    # 2.5) 中文"几号/几日"：本月X号 / 下月X号 / 上月X号 / 裸X号
    #      必须放在"每周X"之前，避免"周"字干扰
    cn_day = _parse_cn_day(remain, today)
    if cn_day is not None:
        d, span = cn_day
        return d, remain[:span[0]] + remain[span[1]:]

    # 2.6) 月底 / 月初 / 月末 / 下月初
    for word, calc in (("月底", "end"), ("月末", "end"), ("月尾", "end"),
                       ("月初", "start"), ("月初头", "start")):
        if word in remain:
            d = _month_edge(today, calc, offset=0)
            # 本月的这个时间点已过 -> 顺延到下个月
            if calc == "start" and d < today:
                d = _month_edge(today, "start", offset=1)
            return d, remain.replace(word, " ", 1)
    if "下月初" in remain:
        return _month_edge(today, "start", offset=1), remain.replace("下月初", " ", 1)
    if "下个月底" in remain or "下月月底" in remain:
        return _month_edge(today, "end", offset=1), \
            remain.replace("下个月底", " ", 1).replace("下月月底", " ", 1)

    # 3) N天后 / N天以后
    m = re.search(r"(\d+)\s*天[后以]后?", remain)
    if m:
        d = today + timedelta(days=int(m.group(1)))
        return d, remain[:m.start()] + remain[m.end():]

    # 4) 每周X / 本周X / 周X / 星期X
    week_match = re.search(r"(下|这|本|上)?\s*(周|星期|礼拜)\s*([一二三四五六日天1-7])", remain)
    if week_match:
        prefix = week_match.group(1) or ""
        wd = _wd_to_index(week_match.group(3))
        if wd is not None:
            if prefix == "下":
                # 下周X：先定位到下一个周一，再加偏移
                base = today + timedelta(days=7 - today.weekday())
                d = base + timedelta(days=wd)
            elif prefix == "上":
                base = today - timedelta(days=today.weekday() + 7)
                d = base + timedelta(days=wd)
            else:  # 本周/这周
                d = today + timedelta(days=(wd - today.weekday()) % 7)
            return d, remain[:week_match.start()] + remain[week_match.end():]

    # 5) 下个月同一天（简化处理）
    if "下个月" in remain:
        d = (today.replace(day=1) + timedelta(days=32)).replace(day=min(today.day, 28))
        return d, remain.replace("下个月", " ", 1)

    return None, remain


def _parse_time_part(text: str) -> Tuple[Optional[time], Optional[time], str]:
    """
    解析时间。返回 (开始时间, 结束时间, 剩余文本)。
    支持 "下午3点" "10:00" "10:00-11:30" "晚上8点半" "3点" 等。
    """
    remain = text
    start_t: Optional[time] = None
    end_t: Optional[time] = None

    # 1) 带区间的：HH:MM-HH:MM
    m = re.search(r"(\d{1,2})\s*[:：]\s*(\d{2})\s*[-~至到]\s*(\d{1,2})\s*[:：]\s*(\d{2})", remain)
    if m:
        h1, mi1, h2, mi2 = (int(x) for x in m.groups())
        if 0 <= h1 <= 23 and 0 <= mi1 <= 59 and 0 <= h2 <= 23 and 0 <= mi2 <= 59:
            start_t = time(h1, mi1)
            end_t = time(h2, mi2)
            return start_t, end_t, remain[:m.start()] + remain[m.end():]

    # 2) 识别时段词（下午/晚上…），用于 12 小时制换算
    period = None
    period_span = None
    for key in ("下午傍晚", "凌晨", "清晨", "早晨", "早上", "上午", "中午", "傍晚", "晚上", "夜里", "下午"):
        if key in remain:
            period = key
            idx = remain.index(key)
            period_span = (idx, idx + len(key))
            break

    def _strip_period(txt: str) -> str:
        """把已识别的时段词从文本中移除，避免残留在标题里。"""
        if period_span is None:
            return txt
        s, e = period_span
        return txt[:s] + " " + txt[e:]

    # 3) HH:MM
    m = re.search(r"(\d{1,2})\s*[:：]\s*(\d{2})", remain)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            start_t = time(h, mi)
            return start_t, end_t, _strip_period(remain[:m.start()] + remain[m.end():])

    # 4) 中文小时：X点 / X点半 / X点Y分
    m = re.search(r"([0-9]{1,2}|[一二两三四五六七八九十]{1,3})\s*[点时]\s*(半|([0-9]{1,2}|[一二三四五六七八九十]{1,3})\s*分?)?", remain)
    if m:
        hour = _cn_to_int(m.group(1))
        if hour is not None and 0 <= hour <= 24:
            minute = 0
            if m.group(2):
                if m.group(2) == "半":
                    minute = 30
                else:
                    mv = _cn_to_int(m.group(3) or "")
                    if mv is not None and 0 <= mv <= 59:
                        minute = mv
            if hour == 24:
                hour = 0
            # 时段换算：下午/晚上 + 1..11 -> +12；中午 12 点保持 12
            if period in ("下午", "傍晚", "晚上", "夜里") and hour < 12:
                hour += 12
            elif period == "中午" and hour < 12:
                hour = 12
            elif period == "凌晨" and hour == 12:
                hour = 0
            start_t = time(hour, minute)
            return start_t, end_t, _strip_period(remain[:m.start()] + remain[m.end():])

    # 5) 口语整点：上午九点 / 晚上八点
    m = re.search(r"(上午|早上|早晨|中午|下午|晚上|夜里)\s*([零一两二三四五六七八九十]{1,3})", remain)
    if m:
        hour = _cn_to_int(m.group(2))
        if hour is not None and 0 <= hour <= 23:
            if m.group(1) in ("下午", "晚上", "夜里") and hour < 12:
                hour += 12
            elif m.group(1) == "中午" and hour < 12:
                hour = 12
            start_t = time(hour, 0)
            return start_t, end_t, remain[:m.start()] + remain[m.end():]

    # 6) 只有时段词，无具体时刻 -> 用该时段的代表时刻
    #    例如「本周五中午吃饭」-> 12:00；「明天上午开会」-> 09:00
    #    绝不能丢弃时段词退回默认 9:00，否则「中午」会被解析成早上。
    if period:
        default_hour = PERIOD_DEFAULT_HOUR.get(period)
        if default_hour is not None:
            start_t = time(default_hour, 0)
        return start_t, end_t, _strip_period(remain)

    return None, None, remain


REPEAT_WORDS = {
    "每天": "daily", "每日": "daily", "天天": "daily",
    "每周": "weekly", "每星期": "weekly", "每礼拜": "weekly",
    "每月": "monthly", "每年": "yearly", "工作日每天": "daily",
}


def parse_quick(text: str, today: Optional[date] = None,
                known_tags: Optional[List[str]] = None) -> Optional[Event]:
    """
    解析快捷输入，成功返回 Event，失败返回 None（调用方回退到完整表单）。

    解析优先级：显式标记（#标签 !高 @日期 ~时长） > 自然语言表达。
    """
    if not text or not text.strip():
        return None

    today = today or date.today()
    raw = text.strip()

    # ---- 第一步：提取显式标记（零歧义，优先采用）----
    from .markers import parse_markers
    markers, raw = parse_markers(raw, today, known_tags)

    # ---- 第二步：自然语言标签 / 优先级 ----
    nl_tag, nl_priority, raw = _parse_meta_words(raw)

    # 合并：显式标记优先
    tags = markers.tags or ([nl_tag] if nl_tag else [])
    priority = markers.priority or nl_priority

    # 识别重复规则
    repeat = "none"
    repeat_weekdays = []

    # 先处理 "每周X" / "每周一、三" —— 必须在通用重复词之前，
    # 否则 "每周" 会先被替换掉，导致星期信息丢失。
    # 注意：这里必须要求"每"后面跟"周/星期/礼拜"，
    # 否则 "每天9点" 会被误判为 weekly。
    m = re.search(r"每\s*(?:周|星期|礼拜)\s*([一二三四五六日天1-7])(?:[、,，和/]\s*([一二三四五六日天1-7]))?", raw)
    if m:
        repeat = "weekly"
        chars = [m.group(1)]
        if m.group(2):
            chars.append(m.group(2))
        for c in chars:
            wd = _wd_to_index(c)
            if wd is not None and wd not in repeat_weekdays:
                repeat_weekdays.append(wd)
        raw = raw[:m.start()] + " " + raw[m.end():]
    else:
        # 通用重复词
        for word, rule in REPEAT_WORDS.items():
            if word in raw:
                repeat = rule
                raw = raw.replace(word, " ", 1)
                break

    # 识别"全天"
    all_day = False
    if "全天" in raw or "一整天" in raw:
        all_day = True
        raw = raw.replace("全天", " ").replace("一整天", " ")

    day, raw = _parse_date_part(raw, today)
    start_t, end_t, raw = _parse_time_part(raw)

    # 显式 @日期 优先于自然语言解析出的日期
    if markers.date is not None:
        day = markers.date

    # 标题：清理剩余文本
    title = re.sub(r"[，,。.、;；:：!！?？\s]+", " ", raw).strip()
    title = re.sub(r"^(?:在|于)\s*", "", title).strip()

    # 至少要识别出日期或时间之一，否则解析失败
    # 注意：重复规则本身隐含"从今天开始"的语义，因此也算识别成功
    # 显式标记（#标签 !高）本身也是一种有效输入 -> 给默认时间即可
    has_marker = bool(tags) or bool(priority) or markers.date is not None \
        or markers.duration_minutes is not None
    if day is None and start_t is None and repeat == "none" and not has_marker:
        return None

    if day is None and repeat != "none":
        # 重复日程未定起始日 -> 推算合理的首次发生日期
        if repeat == "weekly" and repeat_weekdays:
            # 下一次符合指定星期的日期
            offsets = sorted((wd - today.weekday()) % 7 or 7 for wd in repeat_weekdays)
            day = today + timedelta(days=offsets[0])
        else:
            day = today
    elif day is None:
        # 只识别到时间（或只有标记）：默认今天；若时间已过则顺延到明天
        day = today
        if start_t and datetime.combine(today, start_t) < datetime.now():
            day = today + timedelta(days=1)
    if all_day:
        start_t, end_t = time(0, 0), time(23, 59)

    start_dt = datetime.combine(day, start_t or time(9, 0))
    if end_t is not None:
        end_dt = datetime.combine(day, end_t)
    elif markers.duration_minutes:
        # 显式 ~时长 优先于默认 1 小时
        end_dt = start_dt + timedelta(minutes=markers.duration_minutes)
    else:
        end_dt = start_dt + timedelta(hours=1)
    if end_dt <= start_dt:
        end_dt = start_dt + timedelta(hours=1)

    if not title:
        title = "新建日程"

    return Event(
        title=title,
        note="",
        start=start_dt,
        end=end_dt,
        repeat=repeat,
        repeat_weekdays=repeat_weekdays,
        all_day=all_day,
        tag=tags[0] if tags else "",
        priority=priority or "normal",
    )
