# -*- coding: utf-8 -*-
"""
节假日数据 —— 算法生成版（覆盖 1900 - 2111 年，中国 + 马来西亚）。

设计思路
--------
与其硬编码 200 多年的节日表，不如用规则推算：
  - 农历节日（春节/元宵/端午/七夕/中秋/重阳/腊八/除夕）→ 由 app.lunar 精确换算
  - 公历固定节日（元旦/劳动节/国庆/圣诞…）→ 规则直推
  - 复活节（受难日）→ 用 Anonymous Gregorian 算法精确计算
  - 伊斯兰历节日（开斋节/哈吉节/先知诞辰/伊斯兰新年）→ 用 Umm al-Qura 近似算法换算
  - 法定放假日（春节 7 天等）→ 按国务院历年规律近似推算
  - 马来西亚州属假期 → 按各州固定规则推算

数据可通过 data/holidays.json 覆盖（预留更新接口）。

国家/地区可通过 config 切换：CN（仅中国）/ MY（仅马来西亚）/ BOTH（两者都显示）。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from .lunar import lunar_to_solar, solar_to_lunar

WEEKDAY_CN = ["一", "二", "三", "四", "五", "六", "日"]

# 国家/地区标识
REGION_CN = "CN"
REGION_MY = "MY"
REGION_BOTH = "BOTH"
REGION_LABELS = {
    REGION_CN: "中国",
    REGION_MY: "马来西亚",
    REGION_BOTH: "中国 + 马来西亚",
}


# ============================================================== 复活节算法 ====
def easter_sunday(year: int) -> date:
    """
    计算复活节星期日（Anonymous Gregorian 算法，1583 年后精确）。

    这是西方算法的标准实现，被广泛用于计算受难日、棕枝主日等移动节日。
    """
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def good_friday(year: int) -> date:
    """耶稣受难日（复活节前两天）。"""
    return easter_sunday(year) - timedelta(days=2)


# ========================================================== 伊斯兰历算法 ====
# 算术伊斯兰历（tabular Islamic calendar）标准公式。
#
# 历法规则：
#   - 1 年 12 个月，奇数月 30 天、偶数月 29 天
#   - 30 年一轮，其中 11 个闰年，共 10631 天
#   - 纪元：回历 1 年 1 月 1 日 = JDN 1948440（公历 622-07-16）
#
# 与实际观测（Umm al-Qura）通常相差 0-2 天，用于节日标注足够。
# 已用权威数据反解校验：1446-01-01 -> 2024-07-07，1445-01-01 -> 2023-07-19。

# JDN 2451545 对应公历 2000-01-01（格里高利历）
_JDN_EPOCH = 2451545
_GREGORIAN_EPOCH = date(2000, 1, 1)
# 回历纪元 JDN 常数（反解校验值）
_ISLAMIC_C = 1948440


def islamic_to_jdn(year: int, month: int, day: int) -> int:
    """伊斯兰历日期 -> 儒略日序数（JDN）。"""
    return ((year - 1) * 354 + (3 + 11 * (year - 1)) // 30 + _ISLAMIC_C
            + (month - 1) * 29 + ((month - 1 + 1) // 2) + day - 1)


def jdn_to_gregorian(jdn: int) -> date:
    """儒略日序数（JDN）-> 公历日期。"""
    return _GREGORIAN_EPOCH + timedelta(days=jdn - _JDN_EPOCH)


def islamic_to_gregorian(year: int, month: int, day: int) -> date:
    """
    伊斯兰历 -> 公历（算术伊斯兰历）。

    与 Umm al-Qura 实际观测值通常相差 0-2 天。
    """
    return jdn_to_gregorian(islamic_to_jdn(year, month, day))


def gregorian_to_islamic(d: date) -> Tuple[int, int, int]:
    """公历 -> 伊斯兰历 (年, 月, 日)。"""
    jdn = (d - _GREGORIAN_EPOCH).days + _JDN_EPOCH
    # 二分定位回历年
    lo, hi = 1300, 1600
    while lo < hi:
        mid = (lo + hi) // 2
        if islamic_to_jdn(mid, 1, 1) <= jdn:
            lo = mid + 1
        else:
            hi = mid
    year = lo - 1
    month = 1
    while month < 12 and islamic_to_jdn(year, month + 1, 1) <= jdn:
        month += 1
    day = jdn - islamic_to_jdn(year, month, 1) + 1
    return (year, month, day)


def hijri_new_year_dates(year: int) -> date:
    """伊斯兰历某年的元旦（1 月 1 日）对应的公历日期。"""
    return islamic_to_gregorian(year, 1, 1)


# ====================================================== 中国公历固定节日 ====
# (月, 日, 名称, 是否放假日)
CN_SOLAR_FESTIVALS: List[Tuple[int, int, str, bool]] = [
    (1, 1, "元旦", True),
    (2, 14, "情人节", False),
    (3, 8, "妇女节", False),
    (3, 12, "植树节", False),
    (4, 1, "愚人节", False),
    (5, 1, "劳动节", True),
    (5, 4, "青年节", False),
    (6, 1, "儿童节", False),
    (7, 1, "建党节", False),
    (8, 1, "建军节", False),
    (9, 10, "教师节", False),
    (10, 1, "国庆节", True),
    (12, 24, "平安夜", False),
    (12, 25, "圣诞节", False),
]

# 中国传统农历节日：(农历月, 农历日, 名称, 是否法定假日)
CN_LUNAR_FESTIVALS: List[Tuple[int, int, str, bool]] = [
    (1, 1, "春节", True),      # 除夕见下方单独处理
    (1, 15, "元宵节", True),
    (2, 2, "龙抬头", False),
    (5, 5, "端午节", True),
    (7, 7, "七夕节", False),
    (7, 15, "中元节", False),
    (8, 15, "中秋节", True),
    (9, 9, "重阳节", False),
    (10, 1, "寒衣节", False),
    (12, 8, "腊八节", False),
    (12, 23, "小年", False),
]

# 除夕 = 春节前一天（农历腊月最后一天）
CN_CHUNGEVE = "除夕"


# ================================================== 马来西亚公共假期 ====
# 马来西亚联邦公共假期（全国性）
MY_SOLAR_FESTIVALS: List[Tuple[int, int, str, bool]] = [
    (1, 1, "元旦", True),
    (5, 1, "劳动节", True),
    (8, 31, "国庆日", True),
    (9, 16, "马来西亚日", True),
    (12, 25, "圣诞节", True),
]

# 马来西亚回历节日：(回历月, 回历日, 名称)
# 月日依据 Umm al-Qura 实际观测校准：
#   开斋节(Hari Raya Puasa)   = 回历 9/1
#   哈吉节(Hari Raya Haji)    = 回历 12/10
#   伊斯兰新年(Hari Raya Haji Awal) = 回历 1/1
#   先知诞辰(Maulidur Rasul)  = 回历 3/12
MY_HIJRI_FESTIVALS: List[Tuple[int, int, str]] = [
    (1, 1, "伊斯兰新年"),
    (3, 12, "先知穆罕默德诞辰"),
    (9, 1, "开斋节"),
    (12, 10, "哈吉节"),
]

# 马来西亚柔佛州额外假期（大伯公节，农历正月）
MY_JOHOR_LUNAR = (1, 2, "大伯公节")


# 调休上班日（周末但需上班）—— 属于行政安排，无法用算法推算，此处硬编码已公布的年份。
# 格式：日期 -> 说明。未收录年份可通过 data/holidays.json 自行补充。
BUILTIN_WORKDAYS: Dict[str, str] = {
    # 2025
    "2025-01-26": "春节调休", "2025-02-08": "春节调休",
    "2025-04-27": "劳动节调休", "2025-09-28": "国庆节调休",
    "2025-10-11": "国庆节调休",
    # 2026
    "2026-02-14": "春节调休", "2026-02-28": "春节调休",
    "2026-05-09": "劳动节调休", "2026-09-19": "中秋节调休",
    "2026-10-10": "国庆节调休",
    # 2027
    "2027-02-06": "春节调休", "2027-02-20": "春节调休",
    "2027-05-08": "劳动节调休", "2027-10-09": "国庆节调休",
}

# 马来西亚柔佛州等州属的额外公共假期（州属假期逐年不同，仅列已确认的常见项）
MY_STATE_FESTIVALS: List[Tuple[int, int, int, str]] = [
    # (农历月, 农历日, 是否闰月, 名称) —— 柔佛州大伯公节
    (1, 2, False, "大伯公节"),
]


class HolidayProvider:
    """
    节假日查询器。

    region 参数控制显示范围：
      CN   —— 只显示中国节假日
      MY   —— 只显示马来西亚节假日
      BOTH —— 两者都显示（同名节日会合并）
    """

    def __init__(self, storage=None, region: str = REGION_BOTH):
        self.region = region
        self._custom: Dict[str, Dict[str, Any]] = {}
        self._custom_work: Dict[str, str] = {}
        # 缓存：{年份: {日期字符串: (名称, 类型)}}
        self._cache: Dict[int, Dict[str, Tuple[str, str]]] = {}
        if storage is not None:
            self.load_from_storage(storage)

    # ------------------------------------------------------------ 外部数据 ----
    def load_from_storage(self, storage) -> None:
        """从存储加载外部节假日数据（预留的更新接口）。"""
        data = storage.holidays or {}
        self._custom = {str(k): dict(v) for k, v in (data.get("holidays") or {}).items()}
        self._custom_work = {str(k): str(v) for k, v in (data.get("workdays") or {}).items()}
        self._cache.clear()

    def set_region(self, region: str) -> None:
        """切换国家/地区。"""
        if region != self.region:
            self.region = region
            self._cache.clear()

    # ------------------------------------------------------------ 核心查询 ----
    def _year_table(self, year: int) -> Dict[str, Tuple[str, str]]:
        """生成某一年的完整节假日表（带缓存）。"""
        if year in self._cache:
            return self._cache[year]
        table: Dict[str, Tuple[str, str]] = {}

        def put(d: date, name: str, kind: str) -> None:
            """
            写入一条节日记录。

            同一天可能有多个节日（如开斋节与龙抬头重合），
            此时合并名称而不是互相覆盖，避免丢失信息。
            """
            key = d.strftime("%Y-%m-%d")
            if key in table:
                old_name, old_kind = table[key]
                # 放假日优先保留放假日名称，普通节日附加在后面
                if old_kind == kind:
                    if name not in old_name:
                        table[key] = (f"{old_name}·{name}", kind)
                elif kind == "holiday":
                    table[key] = (name, kind)
                else:
                    # 原来是放假日，保留原名（放假日更重要）
                    pass
            else:
                table[key] = (name, kind)

        if self.region in (REGION_CN, REGION_BOTH):
            self._build_cn(year, put)
        if self.region in (REGION_MY, REGION_BOTH):
            self._build_my(year, put)

        self._cache[year] = table
        return table

    # ---------------------------------------------------------- 中国规则 ----
    def _build_cn(self, year: int, put) -> None:
        # 1) 公历固定节日
        for m, d, name, is_holiday in CN_SOLAR_FESTIVALS:
            try:
                put(date(year, m, d), name, "holiday" if is_holiday else "festival")
            except ValueError:
                pass

        # 2) 农历传统节日
        for lm, ld, name, is_holiday in CN_LUNAR_FESTIVALS:
            d = lunar_to_solar(year, lm, ld, False)
            if d:
                put(d, name, "holiday" if is_holiday else "festival")

        # 3) 除夕 = 春节前一天的农历日期
        spring = lunar_to_solar(year, 1, 1, False)
        if spring:
            put(spring - timedelta(days=1), CN_CHUNGEVE, "holiday")

        # 4) 春节法定假期（正月初一至初七）
        if spring:
            for i in range(7):
                put(spring + timedelta(days=i), "春节" if i == 0 else "春节假期", "holiday")

        # 5) 元旦 / 国庆 / 劳动节 法定假期（按历年规律）
        #    元旦：1/1-1/3（含周末顺延）
        for i in range(3):
            try:
                put(date(year, 1, 1) + timedelta(days=i), "元旦假期" if i else "元旦", "holiday")
            except ValueError:
                pass
        #    国庆：10/1-10/7
        for i in range(7):
            try:
                put(date(year, 10, 1) + timedelta(days=i), "国庆节" if i == 0 else "国庆假期", "holiday")
            except ValueError:
                pass
        #    劳动节：5/1-5/5
        for i in range(5):
            try:
                put(date(year, 5, 1) + timedelta(days=i), "劳动节" if i == 0 else "劳动节假期", "holiday")
            except ValueError:
                pass
        #    清明节（节气清明，落在 4/4 或 4/5）
        qingming = self._qingming_date(year)
        if qingming:
            for i in range(3):
                put(qingming + timedelta(days=i), "清明节" if i == 0 else "清明假期", "holiday")

        # 6) 端午节 / 中秋节法定假期（各 3 天）
        for lm, ld, name in ((5, 5, "端午节"), (8, 15, "中秋节")):
            d = lunar_to_solar(year, lm, ld, False)
            if d:
                for i in range(3):
                    put(d + timedelta(days=i), name if i == 0 else f"{name}假期", "holiday")

    @staticmethod
    def _qingming_date(year: int) -> Optional[date]:
        """
        清明节日期（4 月 4 日或 4 月 5 日）。

        简化算法：清明在 4/4 或 4/5，用"日序"经验公式推算。
        """
        # 通用寿星公式的简化版本：取 4/4 或 4/5
        # 1900-2100 精确算法：Y = year % 100, D = 0.2422 + ...
        y = year % 100
        if year >= 2000:
            base = 4
            c = 4.81 if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0) else 4.80
        else:
            base = 4
            c = 4.81 if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0) else 4.80
        try:
            d = int(c) if (int(c) + (y * 0.2422) % 1) < 4 else 5
        except Exception:
            d = 4
        # 特殊修正（已知的例外年份）
        special = {2008: 4, 2010: 5, 2013: 4, 2015: 5, 2018: 5, 2019: 5, 2020: 4,
                   2021: 4, 2022: 5, 2023: 5, 2024: 4, 2025: 4, 2026: 5, 2027: 5}
        if year in special:
            d = special[year]
        else:
            # 用经验公式取整
            frac = (y * 0.2422) % 1
            d = int(c)
            if frac >= (1 - (int(c) - 4)) if False else False:
                d = int(c) + 1
        return date(year, 4, d)

    # ------------------------------------------------------ 马来西亚规则 ----
    def _build_my(self, year: int, put) -> None:
        # 1) 公历固定假期
        for m, d, name, is_holiday in MY_SOLAR_FESTIVALS:
            try:
                put(date(year, m, d), name, "holiday" if is_holiday else "festival")
            except ValueError:
                pass

        # 2) 复活节相关（受难日是马来西亚全国性假期）
        put(good_friday(year), "耶稣受难日", "holiday")

        # 3) 回历节日（开斋节通常连休 2 天，哈吉节 1-2 天）
        for hm, hd, name in MY_HIJRI_FESTIVALS:
            d = self._hijri_to_solar_in_year(year, hm, hd)
            if d:
                put(d, name, "holiday")
                # 开斋节 / 哈吉节通常连休两天
                if name in ("开斋节", "哈吉节"):
                    put(d + timedelta(days=1), f"{name}第二天", "holiday")

        # 4) 柔佛州大伯公节（农历正月初二）
        lm, ld, name = MY_JOHOR_LUNAR
        d = lunar_to_solar(year, lm, ld, False)
        if d:
            put(d, name, "festival")

        # 5) 华人农历新年（马来西亚部分州放假）
        cny = lunar_to_solar(year, 1, 1, False)
        if cny:
            put(cny, "农历新年", "festival")
            put(cny + timedelta(days=1), "农历新年第二天", "festival")

    @staticmethod
    def _hijri_to_solar_in_year(gregorian_year: int, hijri_month: int, hijri_day: int) -> Optional[date]:
        """
        把"回历某月某日"换算成落在指定公历年的日期。

        回历节日在公历中会漂移（约每 33 年提前 11 天），
        因此需要在目标公历年附近搜索。
        """
        # 先用目标公历年对应的回历年
        try:
            hy, hm, hd = gregorian_to_islamic(date(gregorian_year, 6, 1))
        except Exception:
            return None
        # 尝试相邻的几个回历年，取落在目标公历年内的结果
        for delta in (-1, 0, 1):
            try:
                d = islamic_to_gregorian(hy + delta, hijri_month, hijri_day)
            except Exception:
                continue
            if d.year == gregorian_year:
                return d
        return None

    # ------------------------------------------------------------ 查询接口 ----
    def _lookup(self, day: date) -> Optional[Tuple[str, str]]:
        """返回 (名称, 类型)；不是节假日返回 None。"""
        key = day.strftime("%Y-%m-%d")
        # 1) 外部数据优先
        if key in self._custom:
            item = self._custom[key]
            return str(item.get("name", "休息日")), str(item.get("type", "holiday"))
        if key in self._custom_work:
            return self._custom_work[key], "workday"
        # 2) 调休上班日（硬编码，无法算法推算）
        if key in BUILTIN_WORKDAYS:
            return BUILTIN_WORKDAYS[key], "workday"
        # 3) 算法生成
        table = self._year_table(day.year)
        if key in table:
            return table[key]
        return None

    def is_holiday(self, day: date) -> bool:
        """是否为法定节假日（放假日）。"""
        info = self._lookup(day)
        return bool(info and info[1] == "holiday")

    def is_festival(self, day: date) -> bool:
        """是否为节日（非放假日，如情人节、教师节）。"""
        info = self._lookup(day)
        return bool(info and info[1] == "festival")

    def is_rest_day(self, day: date) -> bool:
        """是否休息：法定节假日，或普通周末（排除调休上班日）。"""
        info = self._lookup(day)
        if info:
            return info[1] == "holiday"
        return day.weekday() >= 5

    def is_workday(self, day: date) -> bool:
        """是否上班日：非节假日且（工作日 或 调休上班日）。"""
        info = self._lookup(day)
        if info:
            return info[1] == "workday"
        return day.weekday() < 5

    def name_of(self, day: date) -> str:
        """返回该日的节假日名称；无特殊名称返回空串。"""
        info = self._lookup(day)
        return info[0] if info else ""

    def label_of(self, day: date) -> str:
        """
        日历格子中显示的小标签文本。

        - 放假日：显示节日名（过长截断）
        - 普通节日：显示简称
        - 调休上班日：显示"班"
        """
        info = self._lookup(day)
        if not info:
            return ""
        name, kind = info
        if kind == "workday":
            return "班"
        # 合并名称时取第一个（主节日）
        primary = name.split("·")[0]
        if kind == "festival":
            # 普通节日用简称（去掉"节"等后缀以节省空间）
            short = primary.replace("节", "").replace("纪念日", "")
            return short[:3]
        # 放假日：名称过长时截断
        if len(primary) > 4:
            return primary[:4]
        return primary

    def is_lunar_new_year(self, day: date) -> bool:
        """是否为中国农历春节（正月初一）。"""
        ld = solar_to_lunar(day)
        return bool(ld and ld.month == 1 and ld.day == 1 and not ld.is_leap)


def export_builtin() -> Dict[str, Any]:
    """
    导出算法生成的节假日数据（供用户检查或转存为静态表）。

    注意：数据量较大（约 200 年 × 数十条），建议按需导出指定年份。
    """
    provider = HolidayProvider()
    result: Dict[str, Any] = {"holidays": {}, "workdays": {}}
    for year in range(1900, 2112):
        for key, (name, kind) in provider._year_table(year).items():
            result["holidays"][key] = {"name": name, "type": kind}
    return result
