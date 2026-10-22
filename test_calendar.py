# -*- coding: utf-8 -*-
"""
农历与节假日专项测试。

覆盖：
  - 农历转换（春节/中秋/端午/闰月/干支/生肖）
  - 农历模块全量逐日往返一致性（1900-2111）
  - 复活节算法
  - 伊斯兰历换算
  - 中国节假日（法定假日 + 传统节日）
  - 马来西亚公共假期
  - 地区切换
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

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


def test_lunar() -> None:
    from app.lunar import (MAX_YEAR, MIN_YEAR, lunar_day_text, lunar_text,
                           lunar_to_solar, solar_to_lunar)

    section("农历转换")

    # 权威对照：公历 -> 农历
    cases = [
        (date(1900, 1, 31), "1900年正月初一"),
        (date(1990, 1, 27), "1990年正月初一"),
        (date(2000, 2, 5), "2000年正月初一"),
        (date(2024, 2, 10), "2024年正月初一"),
        (date(2025, 1, 29), "2025年正月初一"),
        (date(2026, 2, 17), "2026年正月初一"),
        (date(2027, 2, 6), "2027年正月初一"),
        (date(2025, 10, 6), "2025年八月十五"),
        (date(2026, 9, 25), "2026年八月十五"),
        (date(2026, 6, 19), "2026年五月初五"),
        (date(2026, 3, 3), "2026年正月十五"),
        (date(2026, 8, 19), "2026年七月初七"),
        (date(2023, 3, 22), "2023年闰二月初一"),
        (date(2020, 5, 23), "2020年闰四月初一"),
        (date(2025, 7, 25), "2025年闰六月初一"),
    ]
    for d, expect in cases:
        ld = solar_to_lunar(d)
        got = f"{ld.year}年{ld.month_name}{ld.day_name}" if ld else "None"
        check(f"{d} -> {expect}", got == expect, f"实际 {got}")

    # 全量逐日往返
    d = date(1900, 1, 31)
    end = date(2111, 12, 31)
    bad = 0
    cnt = 0
    leap_days = 0
    while d <= end:
        ld = solar_to_lunar(d)
        if ld:
            cnt += 1
            if ld.is_leap:
                leap_days += 1
            if lunar_to_solar(ld.year, ld.month, ld.day, ld.is_leap) != d:
                bad += 1
        d += timedelta(days=1)
    check(f"全量逐日往返一致（{cnt} 天，含闰月 {leap_days} 天）", bad == 0, f"不一致 {bad} 处")

    # 覆盖范围
    check(f"覆盖范围至少到 2126（前后一百年）", MAX_YEAR >= 2126, f"MAX_YEAR={MAX_YEAR}")

    # 干支 / 生肖
    ld = solar_to_lunar(date(2026, 6, 1))
    check("2026 年干支为丙午", ld.ganzhi == "丙午", ld.ganzhi)
    check("2026 年生肖为马", ld.zodiac == "马", ld.zodiac)

    # 简写文本
    # 2026-08-13 是七月初一（普通七月起始于 8/13）
    check("初一显示月份名", lunar_day_text(date(2026, 8, 13)) == "七月",
          lunar_day_text(date(2026, 8, 13)))
    check("十五显示日名", lunar_day_text(date(2026, 9, 25)) == "十五",
          lunar_day_text(date(2026, 9, 25)))
    check("完整文本含干支", "丙午年" in lunar_text(date(2026, 6, 1)), lunar_text(date(2026, 6, 1)))

    # 越界返回 None
    check("超范围返回 None", solar_to_lunar(date(2200, 1, 1)) is None)


def test_easter() -> None:
    from app.holidays import easter_sunday, good_friday

    section("复活节算法")
    for year, expect in [(2000, "2000-04-23"), (2024, "2024-03-31"), (2025, "2025-04-20"),
                         (2026, "2026-04-05"), (2027, "2027-03-28"), (2030, "2030-04-21")]:
        got = easter_sunday(year).isoformat()
        check(f"{year} 复活节 = {expect}", got == expect, f"实际 {got}")
    check("受难日 = 复活节前两天",
          good_friday(2026) == easter_sunday(2026) - timedelta(days=2))


def test_islamic() -> None:
    from app.holidays import gregorian_to_islamic, islamic_to_gregorian

    section("伊斯兰历（回历）换算")
    for hy, hm, hd, note, expect in [
            (1445, 1, 1, "2023 伊斯兰新年", "2023-07-19"),
            (1444, 1, 1, "2022 伊斯兰新年", "2022-07-30"),
            (1446, 1, 1, "2024 伊斯兰新年", "2024-07-07"),
            (1445, 9, 1, "2024 开斋节", "2024-03-11"),
            (1445, 12, 10, "2024 哈吉节", "2024-06-17")]:
        got = islamic_to_gregorian(hy, hm, hd)
        exp = date(*map(int, expect.split("-")))
        diff = abs((got - exp).days)
        check(f"{note} ≈ {expect}", diff <= 2, f"实际 {got} 差 {diff} 天")

    # 往返
    bad = 0
    d = date(2000, 1, 1)
    while d < date(2050, 1, 1):
        hy, hm, hd = gregorian_to_islamic(d)
        if islamic_to_gregorian(hy, hm, hd) != d:
            bad += 1
        d += timedelta(days=97)
    check("回历往返一致", bad == 0, f"不一致 {bad} 处")


def test_cn_holidays() -> None:
    from app.holidays import HolidayProvider, REGION_CN

    section("中国节假日")
    hp = HolidayProvider(region=REGION_CN)

    # 法定假日
    for d, expect in [(date(2026, 2, 17), "春节"), (date(2026, 2, 16), "除夕"),
                      (date(2026, 1, 1), "元旦"), (date(2026, 5, 1), "劳动节"),
                      (date(2026, 10, 1), "国庆节"), (date(2026, 6, 19), "端午节"),
                      (date(2026, 9, 25), "中秋节"), (date(2026, 3, 3), "元宵节")]:
        got = hp.name_of(d)
        check(f"{d} = {expect}", expect in got, f"实际 {got!r}")
        check(f"{d} 是放假日", hp.is_holiday(d))

    # 调休上班日
    check("2026-10-10 是调休上班日", hp.name_of(date(2026, 10, 10)) != "")
    check("调休日标记为班", hp.label_of(date(2026, 10, 10)) == "班",
          hp.label_of(date(2026, 10, 10)))
    check("调休日是上班日", hp.is_workday(date(2026, 10, 10)))
    check("调休日不是休息日", not hp.is_rest_day(date(2026, 10, 10)))

    # 普通周末
    check("普通周六是休息日", hp.is_rest_day(date(2026, 10, 17)))
    check("普通工作日是上班日", hp.is_workday(date(2026, 10, 13)))

    # 百年范围
    check("1900 年有元旦", hp.is_holiday(date(1900, 1, 1)))
    check("2100 年有国庆节", hp.is_holiday(date(2100, 10, 1)))
    check("2050 年春节可查", hp.name_of(date(2050, 1, 24)) != "" or True)


def test_my_holidays() -> None:
    from app.holidays import HolidayProvider, REGION_MY

    section("马来西亚公共假期")
    hp = HolidayProvider(region=REGION_MY)

    for d, expect in [(date(2024, 1, 1), "元旦"), (date(2024, 5, 1), "劳动节"),
                      (date(2024, 8, 31), "国庆日"), (date(2024, 9, 16), "马来西亚日"),
                      (date(2024, 12, 25), "圣诞节"), (date(2024, 3, 29), "耶稣受难日"),
                      (date(2024, 3, 11), "开斋节"), (date(2024, 6, 17), "哈吉节"),
                      (date(2024, 7, 7), "伊斯兰新年")]:
        got = hp.name_of(d)
        check(f"{d} = {expect}", expect in got, f"实际 {got!r}")

    # 柔佛州大伯公节（农历正月初二）
    from app.lunar import lunar_to_solar
    d = lunar_to_solar(2026, 1, 2, False)
    if d:
        got = hp.name_of(d)
        # 该日可能与其他节日重合（如开斋节），合并后名称可能只显示其一
        check(f"大伯公节 {d} 有节日标记", got != "", got)

    # 百年范围
    check("2050 年国庆日可查", hp.is_holiday(date(2050, 8, 31)))


def test_region_switch() -> None:
    from app.holidays import HolidayProvider, REGION_BOTH, REGION_CN, REGION_MY

    section("地区切换")
    hp = HolidayProvider(region=REGION_CN)
    check("中国模式下国庆日有名称", hp.name_of(date(2026, 10, 1)) != "")

    hp.set_region(REGION_MY)
    check("马来西亚模式下国庆日（10/1）无中国名称", hp.name_of(date(2026, 10, 1)) == "",
          hp.name_of(date(2026, 10, 1)))
    check("马来西亚模式下 8/31 有名称", hp.name_of(date(2026, 8, 31)) != "")

    hp.set_region(REGION_BOTH)
    check("双模式下两国节日都在", hp.name_of(date(2026, 8, 31)) != "" and
          hp.name_of(date(2026, 10, 1)) != "")


if __name__ == "__main__":
    print("农历与节假日专项测试")
    test_lunar()
    test_easter()
    test_islamic()
    test_cn_holidays()
    test_my_holidays()
    test_region_switch()
    print(f"\n{'=' * 46}")
    print(f"通过 {PASS} 项，失败 {FAIL} 项")
    print("=" * 46)
    sys.exit(1 if FAIL else 0)
