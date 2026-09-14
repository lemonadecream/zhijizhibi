"""Salary after-tax calculation engine (F19) -- pure, deterministic.

The program owns EVERY number here. The AI never computes or emits any amount.
This module is the single implementation of the F19 口径 from PRD V0.2 +
技术方案 + Phase 6 方案, version-stamped for reproducibility.

Computation (monthly, then annualized):
  1. insurance_base = clamp(user_base or monthly_base, city[floor, cap])
  2. insurance_personal = base * (养老8% + 医疗2% + 失业0.5% + 公积金 fund_rate)
  3. monthly_taxable = monthly_base - insurance_personal - 5000 - special_deduction
  4. monthly_tax = annual_tax(monthly_taxable * 12) / 12   (simplified 按月预缴)
  5. monthly_after_tax = monthly_base - insurance_personal - monthly_tax
  6. annual_after_tax = monthly_after_tax * 12 + annual_bonus_after_tax
     - annual_bonus = monthly_base * annual_bonus_months
     - annual_bonus_after_tax = bonus - annual_bonus_tax(bonus)   (单独计税)
  7. sign_on / equity_value are NOT included (one-off, display-only).

Output is a dict suitable for ``salary_calc.results`` + a param_snapshot.
"""
from __future__ import annotations

from app.services.salary_policy import (
    INSURANCE_RATES,
    POLICY_VERSION,
    TAX_VERSION,
    annual_bonus_tax,
    clamp_insurance_base,
    city_policy,
    monthly_tax_from_annual,
)


def _round2(x: float) -> float:
    return round(float(x) + 1e-9, 2)


def compute_salary(offer_salary: dict, *, city: str | None,
                   insurance_base: int | None, fund_rate: float | None,
                   special_deduction: int = 0) -> dict:
    """Compute after-tax income for one Offer. All amounts in 元 (CNY).

    Args:
      offer_salary: {monthly_base, annual_bonus_months, sign_on, equity_value}
      city: city name (drives social-insurance base clamp + default fund rate)
      insurance_base: optional explicit 五险一金 base; None -> use monthly_base
      fund_rate: optional 公积金 rate (0..1); None -> city default
      special_deduction: 专项附加扣除 (月, 元)

    Returns a results dict:
      {
        monthly_base, insurance_base, fund_rate,
        insurance: [{name, rate, amount}...],
        insurance_total, taxable_monthly, monthly_tax, monthly_after_tax,
        annual_bonus_months, annual_bonus_gross, annual_bonus_tax, annual_bonus_after_tax,
        annual_after_tax, sign_on, equity_value,
        tax_version, policy_version,
      }
    """
    monthly_base = float(offer_salary.get("monthly_base") or 0)
    annual_bonus_months = float(offer_salary.get("annual_bonus_months") or 0)
    sign_on = float(offer_salary.get("sign_on") or 0)
    equity_value = float(offer_salary.get("equity_value") or 0)

    policy = city_policy(city)
    effective_fund = float(fund_rate) if fund_rate is not None else policy["fund_rate"]
    effective_base = clamp_insurance_base(
        insurance_base if insurance_base is not None else int(monthly_base),
        city,
    )

    # --- insurance (personal portion) ---
    insurance_lines = []
    total = 0.0
    for name, rate in INSURANCE_RATES.items():
        amt = effective_base * rate
        insurance_lines.append({"name": name, "rate": rate, "amount": _round2(amt)})
        total += amt
    fund_amt = effective_base * effective_fund
    insurance_lines.append({"name": "housing_fund", "rate": effective_fund, "amount": _round2(fund_amt)})
    total += fund_amt
    insurance_total = _round2(total)

    # --- tax ---
    taxable_monthly = monthly_base - insurance_total - 5000 - float(special_deduction or 0)
    monthly_tax = _round2(max(0.0, monthly_tax_from_annual(taxable_monthly * 12)))
    monthly_after_tax = _round2(monthly_base - insurance_total - monthly_tax)

    # --- annual bonus (单独计税) ---
    annual_bonus_gross = _round2(monthly_base * annual_bonus_months)
    bonus_tax = _round2(annual_bonus_tax(annual_bonus_gross))
    annual_bonus_after_tax = _round2(annual_bonus_gross - bonus_tax)

    annual_after_tax = _round2(monthly_after_tax * 12 + annual_bonus_after_tax)

    return {
        "monthly_base": _round2(monthly_base),
        "insurance_base": effective_base,
        "fund_rate": effective_fund,
        "insurance": insurance_lines,
        "insurance_total": insurance_total,
        "taxable_monthly": _round2(taxable_monthly),
        "monthly_tax": monthly_tax,
        "monthly_after_tax": monthly_after_tax,
        "annual_bonus_months": annual_bonus_months,
        "annual_bonus_gross": annual_bonus_gross,
        "annual_bonus_tax": bonus_tax,
        "annual_bonus_after_tax": annual_bonus_after_tax,
        "annual_after_tax": annual_after_tax,
        "sign_on": _round2(sign_on),
        "equity_value": _round2(equity_value),
        "tax_version": TAX_VERSION,
        "policy_version": POLICY_VERSION,
    }


def build_param_snapshot(offer_salary: dict, *, city: str | None,
                         insurance_base: int | None, fund_rate: float | None,
                         special_deduction: int = 0) -> dict:
    """Full input snapshot for reproducibility / transparency."""
    policy = city_policy(city)
    return {
        "monthly_base": float(offer_salary.get("monthly_base") or 0),
        "annual_bonus_months": float(offer_salary.get("annual_bonus_months") or 0),
        "sign_on": float(offer_salary.get("sign_on") or 0),
        "equity_value": float(offer_salary.get("equity_value") or 0),
        "city": city,
        "insurance_base_input": insurance_base,
        "fund_rate_input": fund_rate,
        "fund_rate_effective": float(fund_rate) if fund_rate is not None else policy["fund_rate"],
        "special_deduction": int(special_deduction or 0),
        "tax_version": TAX_VERSION,
        "policy_version": POLICY_VERSION,
    }
