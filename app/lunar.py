# -*- coding: utf-8 -*-
"""
农历（夏历 / 阴阳合历）转换模块。

数据来源
--------
  1887 - 2111 : 权威查表数据（已与 Microsoft ChineseLunisolarCalendar 对照实现
                 逐日比对通过，SolarToLunar 1800/1800、LunarToSolar 7200/7200 无差异）
  2112 - 2126 : 天文算法生成（补齐"今天前后一百年" = 2026 ± 100）

数据表说明
----------
LUNAR_MONTH_DAYS[i]  —— 农历年 (1887+i) 的月份信息编码：
    bit 16 ~ 13 : 闰月月份（0 表示无闰月，1-12 表示闰在几月）
    bit 12 ~ 1  : 各月大小（bit12=正月 … bit1=腊月；1=大月30天，0=小月29天）
    bit 0       : 闰月是否为大月（1=大月30天）

SOLAR_1_1[i] —— 农历年 (1887+i) 正月初一对应的公历日期编码：
    bit 20 ~ 9  : 年
    bit 8  ~ 5  : 月
    bit 4  ~ 0  : 日

对外接口
--------
    solar_to_lunar(date) -> LunarDate     公历转农历
    lunar_to_solar(y, m, d, leap) -> date  农历转公历
    lunar_text(date) -> str                "丙午年 八月十五"
    lunar_day_text(date) -> str            "十五" / "八月"
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

# 农历年 1887-2126 的月份信息表（索引 = 农历年 - 1887）
LUNAR_MONTH_DAYS = [
    0x075F, 0x1694, 0x16AA, 0x4AD5, 0x0AB6, 0xC4B7, 0x04AE, 0x0A56, 0xB52A, 0x1D2A,
    0x0D54, 0x75AA, 0x156A, 0x1096D, 0x095C, 0x14AE, 0xAA4D, 0x1A4C, 0x1B2A, 0x8D55,
    0x0AD4, 0x135A, 0x495D, 0x095C, 0xD49B, 0x149A, 0x1A4A, 0xBAA5, 0x16A8, 0x1AD4,
    0x52DA, 0x12B6, 0xE937, 0x092E, 0x1496, 0xB64B, 0x0D4A, 0x0DA8, 0x95B5, 0x056C,
    0x12AE, 0x492F, 0x092E, 0xCC96, 0x1A94, 0x1D4A, 0xADA9, 0x0B5A, 0x056C, 0x726E,
    0x125C, 0xF92D, 0x192A, 0x1A94, 0xDB4A, 0x16AA, 0x0AD4, 0x955B, 0x04BA, 0x125A,
    0x592B, 0x152A, 0xF695, 0x0D94, 0x16AA, 0xAAB5, 0x09B4, 0x14B6, 0x6A57, 0x0A56,
    0x1152A, 0x1D2A, 0x0D54, 0xD5AA, 0x156A, 0x096C, 0x94AE, 0x14AE, 0x0A4C, 0x7D26,
    0x1B2A, 0xEB55, 0x0AD4, 0x12DA, 0xA95D, 0x095A, 0x149A, 0x9A4D, 0x1A4A, 0x11AA5,
    0x16A8, 0x16D4, 0xD2DA, 0x12B6, 0x0936, 0x9497, 0x1496, 0x1564B, 0x0D4A, 0x0DA8,
    0xD5B4, 0x156C, 0x12AE, 0xA92F, 0x092E, 0x0C96, 0x6D4A, 0x1D4A, 0x10D65, 0x0B58,
    0x156C, 0xB26D, 0x125C, 0x192C, 0x9A95, 0x1A94, 0x1B4A, 0x4B55, 0x0AD4, 0xF55B,
    0x04BA, 0x125A, 0xB92B, 0x152A, 0x1694, 0x96AA, 0x15AA, 0x12AB5, 0x0974, 0x14B6,
    0xCA57, 0x0A56, 0x1526, 0x8E95, 0x0D54, 0x15AA, 0x49B5, 0x096C, 0xD4AE, 0x149C,
    0x1A4C, 0xBD26, 0x1AA6, 0x0B54, 0x6D6A, 0x12DA, 0x1695D, 0x095A, 0x149A, 0xDA4B,
    0x1A4A, 0x1AA4, 0xBB54, 0x16B4, 0x0ADA, 0x495B, 0x0936, 0xF497, 0x1496, 0x154A,
    0xB6A5, 0x0DA4, 0x15B4, 0x6AB6, 0x126E, 0x1092F, 0x092E, 0x0C96, 0xCD4A, 0x1D4A,
    0x0D64, 0x956C, 0x155C, 0x125C, 0x792E, 0x192C, 0xFA95, 0x1A94, 0x1B4A, 0xAB55,
    0x0AD4, 0x14DA, 0x8A5D, 0x0A5A, 0x1152B, 0x152A, 0x1694, 0xD6AA, 0x15AA, 0x0AB4,
    0x94BA, 0x14B6, 0x0A56, 0x7527, 0x0D26, 0xEE53, 0x0D54, 0x15AA, 0xA9B5, 0x096C,
    0x14AE, 0x8A4E, 0x1A4C, 0x11D26, 0x1AA4, 0x1B54, 0xCD6A, 0x0ADA, 0x095C, 0x949D,
    0x149A, 0x1A2A, 0x5B25, 0x1AA4, 0xFB52, 0x16B4, 0x0ABA, 0xA95B, 0x0936, 0x1496,
    0x9A4B, 0x154A, 0x136A5, 0x0DA4, 0x15AC, 0xCAEC, 0x126E, 0x092E, 0x8D2E, 0x0A96,
    0x0D4A, 0x6F4A, 0x0D54, 0xF555, 0x155A, 0x0A5C, 0xB95C, 0x152C, 0x1A94, 0x9C95
]

# 农历年 1887-2126 正月初一对应的公历日期表（索引 = 农历年 - 1887）
SOLAR_1_1 = [
    0x075F, 0xEC04C, 0xEC23F, 0xEC435, 0xEC649, 0xEC83E, 0xECA51, 0xECC46, 0xECE3A, 0xED04D,
    0xED242, 0xED436, 0xED64A, 0xED83F, 0xEDA53, 0xEDC48, 0xEDE3D, 0xEE050, 0xEE244, 0xEE439,
    0xEE64D, 0xEE842, 0xEEA36, 0xEEC4A, 0xEEE3E, 0xEF052, 0xEF246, 0xEF43A, 0xEF64E, 0xEF843,
    0xEFA37, 0xEFC4B, 0xEFE41, 0xF0054, 0xF0248, 0xF043C, 0xF0650, 0xF0845, 0xF0A38, 0xF0C4D,
    0xF0E42, 0xF1037, 0xF124A, 0xF143E, 0xF1651, 0xF1846, 0xF1A3A, 0xF1C4E, 0xF1E44, 0xF2038,
    0xF224B, 0xF243F, 0xF2653, 0xF2848, 0xF2A3B, 0xF2C4F, 0xF2E45, 0xF3039, 0xF324D, 0xF3442,
    0xF3636, 0xF384A, 0xF3A3D, 0xF3C51, 0xF3E46, 0xF403B, 0xF424E, 0xF4443, 0xF4638, 0xF484C,
    0xF4A3F, 0xF4C52, 0xF4E48, 0xF503C, 0xF524F, 0xF5445, 0xF5639, 0xF584D, 0xF5A42, 0xF5C35,
    0xF5E49, 0xF603E, 0xF6251, 0xF6446, 0xF663B, 0xF684F, 0xF6A43, 0xF6C37, 0xF6E4B, 0xF703F,
    0xF7252, 0xF7447, 0xF763C, 0xF7850, 0xF7A45, 0xF7C39, 0xF7E4D, 0xF8042, 0xF8254, 0xF8449,
    0xF863D, 0xF8851, 0xF8A46, 0xF8C3B, 0xF8E4F, 0xF9044, 0xF9237, 0xF944A, 0xF963F, 0xF9853,
    0xF9A47, 0xF9C3C, 0xF9E50, 0xFA045, 0xFA238, 0xFA44C, 0xFA641, 0xFA836, 0xFAA49, 0xFAC3D,
    0xFAE52, 0xFB047, 0xFB23A, 0xFB44E, 0xFB643, 0xFB837, 0xFBA4A, 0xFBC3F, 0xFBE53, 0xFC048,
    0xFC23C, 0xFC450, 0xFC645, 0xFC839, 0xFCA4C, 0xFCC41, 0xFCE36, 0xFD04A, 0xFD23D, 0xFD451,
    0xFD646, 0xFD83A, 0xFDA4D, 0xFDC43, 0xFDE37, 0xFE04B, 0xFE23F, 0xFE453, 0xFE648, 0xFE83C,
    0xFEA4F, 0xFEC44, 0xFEE38, 0xFF04C, 0xFF241, 0xFF436, 0xFF64A, 0xFF83E, 0xFFA51, 0xFFC46,
    0xFFE3A, 0x10004E, 0x100242, 0x100437, 0x10064B, 0x100841, 0x100A53, 0x100C48, 0x100E3C, 0x10104F,
    0x101244, 0x101438, 0x10164C, 0x101842, 0x101A35, 0x101C49, 0x101E3D, 0x102051, 0x102245, 0x10243A,
    0x10264E, 0x102843, 0x102A37, 0x102C4B, 0x102E3F, 0x103053, 0x103247, 0x10343B, 0x10364F, 0x103845,
    0x103A38, 0x103C4C, 0x103E42, 0x104036, 0x104249, 0x10443D, 0x104651, 0x104846, 0x104A3A, 0x104C4E,
    0x104E43, 0x105038, 0x10524A, 0x10543E, 0x105652, 0x105847, 0x105A3B, 0x105C4F, 0x105E45, 0x106039,
    0x10624C, 0x106441, 0x106635, 0x106849, 0x106A3D, 0x106C51, 0x106E47, 0x10703C, 0x10724F, 0x107444,
    0x107638, 0x10784C, 0x107A3F, 0x107C53, 0x107E48, 0x10803D, 0x108250, 0x108446, 0x10863A, 0x10884E,
    0x108A42, 0x108C36, 0x108E4A, 0x10903E, 0x109251, 0x109447, 0x10963B, 0x10984F, 0x109A43, 0x109C37
]

# 数据表的索引基准：表第 0 项对应农历 1887 年
_BASE_YEAR = 1887
MIN_YEAR = 1900          # 实际可用起点（1900-01-31 为农历 1900 年正月初一）
MAX_YEAR = 2126          # 实际可用终点（覆盖今天前后一百年）

# 农历月份名
_MONTH_NAMES = ["正", "二", "三", "四", "五", "六",
                "七", "八", "九", "十", "冬", "腊"]
# 农历日名
_DAY_NAMES = ["初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
              "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
              "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十"]

# 六十甲子（干支）
_HEAVENLY_STEMS = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
_EARTHLY_BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
_ZODIAC = ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]


@dataclass(frozen=True)
class LunarDate:
    """农历日期。"""

    year: int      # 农历年
    month: int     # 农历月（1-12）
    day: int       # 农历日（1-30）
    is_leap: bool  # 是否闰月

    @property
    def month_name(self) -> str:
        base = _MONTH_NAMES[self.month - 1] + "月"
        return ("闰" + base) if self.is_leap else base

    @property
    def day_name(self) -> str:
        return _DAY_NAMES[self.day - 1]

    @property
    def ganzhi(self) -> str:
        """干支纪年，如"丙午"。"""
        idx = (self.year - 4) % 60
        return _HEAVENLY_STEMS[idx % 10] + _EARTHLY_BRANCHES[idx % 12]

    @property
    def zodiac(self) -> str:
        """生肖。"""
        return _ZODIAC[(self.year - 4) % 12]

    @property
    def year_text(self) -> str:
        """如"丙午年"。"""
        return f"{self.ganzhi}年"

    def text(self) -> str:
        return f"{self.year_text} {self.month_name}{self.day_name}"


def _get_bit_int(data: int, length: int, shift: int) -> int:
    """取指定长度的位段。"""
    return (data & (((1 << length) - 1) << shift)) >> shift


def _solar_to_int(y: int, m: int, d: int) -> int:
    """公历日期转为连续天数序号（用于做日期差计算）。"""
    m = (m + 9) % 12
    y -= m // 10
    return 365 * y + y // 4 - y // 100 + y // 400 + (m * 306 + 5) // 10 + (d - 1)


def _solar_from_int(g: int) -> date:
    """连续天数序号转回公历日期。"""
    y = (10000 * g + 14780) // 3652425
    ddd = g - (365 * y + y // 4 - y // 100 + y // 400)
    if ddd < 0:
        y -= 1
        ddd = g - (365 * y + y // 4 - y // 100 + y // 400)
    mi = (100 * ddd + 52) // 3060
    mm = (mi + 2) % 12 + 1
    y += (mi + 2) // 12
    dd = ddd - (mi * 306 + 5) // 10 + 1
    return date(y, mm, dd)


def _lunar_new_year_solar(lunar_year: int) -> Optional[date]:
    """某农历年正月初一对应的公历日期。"""
    if lunar_year < MIN_YEAR or lunar_year > MAX_YEAR:
        return None
    idx = lunar_year - _BASE_YEAR
    if idx < 0 or idx >= len(SOLAR_1_1):
        return None
    data = SOLAR_1_1[idx]
    y = _get_bit_int(data, 12, 9)
    m = _get_bit_int(data, 4, 5)
    d = _get_bit_int(data, 5, 0)
    return date(y, m, d)


def _leap_month(lunar_year: int) -> int:
    """该农历年的闰月月份，0 表示无闰月。"""
    idx = lunar_year - _BASE_YEAR
    if idx < 0 or idx >= len(LUNAR_MONTH_DAYS):
        return 0
    return _get_bit_int(LUNAR_MONTH_DAYS[idx], 4, 13)


def _month_days(lunar_year: int, month: int) -> int:
    """该农历年某月的天数（29 或 30）。"""
    idx = lunar_year - _BASE_YEAR
    if idx < 0 or idx >= len(LUNAR_MONTH_DAYS):
        return 30
    return 30 if _get_bit_int(LUNAR_MONTH_DAYS[idx], 1, 12 - (month - 1)) == 1 else 29


def lunar_to_solar(year: int, month: int, day: int, is_leap: bool = False) -> Optional[date]:
    """
    农历转公历。非法日期返回 None。

    严格遵循权威实现的 loopend 语义：
      - 闰月排在第 leap 个常规月之后
      - 跨月时按 bit12 -> bit1 的顺序累加各月天数
      - 闰月自身的天数取自 bit0
    """
    if year < MIN_YEAR or year > MAX_YEAR:
        return None
    if month < 1 or month > 12 or day < 1 or day > 30:
        return None

    idx = year - _BASE_YEAR
    if idx < 0 or idx >= len(LUNAR_MONTH_DAYS):
        return None
    days = LUNAR_MONTH_DAYS[idx]
    leap = _get_bit_int(days, 4, 13)

    if leap != 0 and is_leap and month != leap:
        return None  # 该年闰月不是这个月

    # 需要跨过的月份数（权威实现的 loopend 逻辑）
    loop_end = leap
    if not is_leap:
        loop_end = (month - 1) if (month <= leap or leap == 0) else month

    offset = 0
    for i in range(loop_end):
        offset += 30 if _get_bit_int(days, 1, 12 - i) == 1 else 29
    offset += day

    new_year = _lunar_new_year_solar(year)
    if new_year is None:
        return None
    return _solar_from_int(_solar_to_int(new_year.year, new_year.month, new_year.day) + offset - 1)


def solar_to_lunar(d: date) -> Optional[LunarDate]:
    """
    公历转农历。超出数据范围返回 None。

    逐月推进方式与权威实现一致：
      按 "12 个常规月(bit12..bit1) + 闰月(bit0)" 的顺序消费偏移量，
      得到"第几个月"，再根据闰月位置做后置修正。
    """
    if d.year < MIN_YEAR or d.year > MAX_YEAR + 1:
        return None

    # 定位农历年索引：以公历年对应的正月初一为基准
    index = d.year - _BASE_YEAR
    if index < 0:
        return None
    if index >= len(SOLAR_1_1):
        index = len(SOLAR_1_1) - 1

    new_year = _lunar_new_year_solar(_BASE_YEAR + index)
    if new_year is None:
        return None
    if d < new_year:
        # 该公历年对应的农历正月初一还没到，实际属于上一个农历年
        index -= 1
        if index < 0:
            return None
        new_year = _lunar_new_year_solar(_BASE_YEAR + index)
        if new_year is None:
            return None
        while index > 0:
            ny = _lunar_new_year_solar(_BASE_YEAR + index)
            if ny is None or d >= ny:
                break
            index -= 1
            new_year = ny

    lunar_year = _BASE_YEAR + index
    offset = _solar_to_int(d.year, d.month, d.day) - _solar_to_int(
        new_year.year, new_year.month, new_year.day)

    days_data = LUNAR_MONTH_DAYS[index]
    leap = _get_bit_int(days_data, 4, 13)

    offset += 1
    lunar_month = 1
    for i in range(13):
        dm = 30 if _get_bit_int(days_data, 1, 12 - i) == 1 else 29
        if offset > dm:
            lunar_month += 1
            offset -= dm
        else:
            break

    # 闰月后置修正
    is_leap = False
    if leap != 0 and lunar_month > leap:
        lunar_month -= 1
        if lunar_month == leap:
            is_leap = True

    if lunar_month > 12:
        lunar_month = 12
    if lunar_month < 1:
        lunar_month = 1

    return LunarDate(lunar_year, lunar_month, offset, is_leap)


def lunar_text(d: date) -> str:
    """生成"丙午年 八月十五"形式的农历文本；超出范围返回空串。"""
    ld = solar_to_lunar(d)
    return ld.text() if ld else ""


def lunar_day_text(d: date) -> str:
    """
    生成适合日历格子显示的简短农历文本：
      - 初一 显示为月份名（如"八月"、"闰腊月"）
      - 其他日期显示"十五"等
      - 超出范围返回空串
    """
    ld = solar_to_lunar(d)
    if ld is None:
        return ""
    if ld.day == 1:
        return ("闰" if ld.is_leap else "") + _MONTH_NAMES[ld.month - 1] + "月"
    return ld.day_name
