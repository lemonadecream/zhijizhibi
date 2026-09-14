"""Deterministic salary / tax / social-insurance policy constants (F19).

This module is the SINGLE source of truth for all after-tax income math in
Phase 6. It is a plain Python constants module (NOT a DB table) per the
Phase 6 方案 -- lightweight, version-stamped, and easy to update when policy
changes. The program ALWAYS computes the numbers here; the AI never touches
any of it.

Calibration note (MVP): these are SIMPLIFIED, static 2024-era estimates for
horizontal Offer comparison, NOT a tax-authority-grade calculator. The UI must
label results as 「估算结果，仅用于 Offer 横向比较」.

Sections:
  * INSURANCE_RATES   -- personal rates for 养老/医疗/失业 (公积金 is per-city/offer)
  * CITY_POLICY       -- per-city social-insurance base cap/floor + default fund rate
  * ANNUAL_TAX_BRACKETS -- 年度综合所得 7-level progressive table
  * TAX_VERSION / POLICY_VERSION -- version stamps embedded in every calc snapshot
"""
from __future__ import annotations


# ----------------------------- version stamps -----------------------------
TAX_VERSION = "2024"
POLICY_VERSION = "2024"

# 起征点（基本减除费用），月 5000
MONTHLY_THRESHOLD = 5000


# ----------------------------- 五险一金 personal rates -----------------------------
# 个人缴纳比例（百分比 -> 小数）
INSURANCE_RATES = {
    "pension": 0.08,   # 养老 8%
    "medical": 0.02,   # 医疗 2%
    "unemployment": 0.005,  # 失业 0.5%
    # 工伤 / 生育：个人不缴
}

# 公积金默认比例（按城市默认；offer 可覆盖 fund_rate）
DEFAULT_FUND_RATE = 0.07  # 7%


# ----------------------------- 城市社保政策 -----------------------------
# 缴费基数上下限 = 社平工资 × 倍数。这里用估算的「社平工资」直接给出上下限。
# floor = 下限 (社平×0.6), cap = 上限 (社平×3)。无数据的城市用通用默认值。
# fund_rate 为该城市公积金默认比例。
_CITY_RAW = {
    # city: (base_floor, base_cap, default_fund_rate)
    "北京": (6326, 31626, 0.12),
    "上海": (7384, 36921, 0.07),
    "广州": (5284, 26421, 0.05),
    "深圳": (2360, 26421, 0.05),
    "杭州": (3957, 19785, 0.12),
    "成都": (4071, 20355, 0.05),
    "武汉": (3740, 18699, 0.08),
    "南京": (4250, 21250, 0.08),
    "西安": (3926, 19631, 0.05),
    "苏州": (4250, 21250, 0.08),
}

# 通用默认（未列出的城市）
_DEFAULT_FLOOR = 4000
_DEFAULT_CAP = 20000
_DEFAULT_CITY_FUND = DEFAULT_FUND_RATE


def city_policy(city: str | None) -> dict:
    """Return {floor, cap, fund_rate} for the given city (or defaults)."""
    if city and city in _CITY_RAW:
        floor, cap, fund = _CITY_RAW[city]
    else:
        floor, cap, fund = _DEFAULT_FLOOR, _DEFAULT_CAP, _DEFAULT_CITY_FUND
    return {"floor": floor, "cap": cap, "fund_rate": float(fund)}


def clamp_insurance_base(base: int | None, city: str | None) -> int:
    """Clamp the insurance base to the city's [floor, cap] range.

    If ``base`` is None, fall back to the city cap (i.e. assume the user earns
    at/above the cap -- conservative for the estimate). This keeps the calc
    deterministic even when the user leaves the base blank.
    """
    floor, cap, _ = city_policy(city).values() if False else (
        city_policy(city)["floor"], city_policy(city)["cap"], city_policy(city)["fund_rate"]
    )
    if base is None:
        return cap
    return max(floor, min(base, cap))


# ----------------------------- 年度综合所得累进税率表 -----------------------------
# (不超过, 税率, 速算扣除数) -- 全年应纳税所得额（元）
ANNUAL_TAX_BRACKETS = [
    (36000, 0.03, 0),
    (144000, 0.10, 2520),
    (300000, 0.20, 16920),
    (420000, 0.25, 31920),
    (660000, 0.30, 52920),
    (960000, 0.35, 85920),
    (float("inf"), 0.45, 181920),
]


def annual_tax(taxable_annual: float) -> float:
    """Compute annual individual-income tax from annual taxable income.

    Uses the 7-level progressive table with quick-deduction. Negative taxable
    income is clamped to 0 (no tax, no refund in this simplified model).
    """
    t = max(0.0, float(taxable_annual))
    for threshold, rate, quick in ANNUAL_TAX_BRACKETS:
        if t <= threshold:
            return max(0.0, t * rate - quick)
    return 0.0  # unreachable, but safe


def monthly_tax_from_annual(taxable_annual: float) -> float:
    """Simplified MVP: tax annual taxable income, divide by 12 for the month.

    This is the PRD-approved simplified口径 (按月预缴、按年汇算的近似): we apply
    the ANNUAL table to the 12-month taxable sum, then spread evenly. Good enough
    for horizontal comparison; not a payroll engine.
    """
    return annual_tax(taxable_annual) / 12.0


# ----------------------------- 年终奖单独计税 -----------------------------
def annual_bonus_tax(bonus: float) -> float:
    """年终奖单独计税（按月度税率表，不并入综合所得）。

    算法：bonus / 12 找月度税率档，bonus × 税率 - 速算扣除。月度税率表用年度表
    的「除以12」等价形式（2024 政策口径）。
    """
    b = max(0.0, float(bonus))
    if b <= 0:
        return 0.0
    monthly = b / 12.0
    # 月度税率表（对应年度表 / 12）
    if monthly <= 3000:
        rate, quick = 0.03, 0
    elif monthly <= 12000:
        rate, quick = 0.10, 210
    elif monthly <= 25000:
        rate, quick = 0.20, 1410
    elif monthly <= 35000:
        rate, quick = 0.25, 2660
    elif monthly <= 55000:
        rate, quick = 0.30, 4410
    elif monthly <= 80000:
        rate, quick = 0.35, 7160
    else:
        rate, quick = 0.45, 15160
    return max(0.0, b * rate - quick)
