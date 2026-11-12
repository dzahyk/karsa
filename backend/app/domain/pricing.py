"""Deterministic feasibility & pricing engine.

All money is whole Indonesian rupiah held as Python ``int`` (no floats anywhere in this module).
Margin is computed with ``Decimal`` and reported in basis points, rounded half-up.

Formulas (spec §1.2, AC03):
    variable_cost = target_units × unit_cost
    total_cost    = variable_cost + fixed_cost
    gross_margin  = (proposed_fee − total_cost) / proposed_fee × 100%
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import ROUND_HALF_UP, Decimal

FORMULA_VERSION = "pricing-formula/1"
MAX_UNITS = 10_000_000
MAX_IDR = 1_000_000_000_000_000  # Rp1 quadrillion — a sanity ceiling, not a business rule


@dataclass(frozen=True)
class PricingInputs:
    target_units: int
    unit_cost_idr: int
    fixed_cost_idr: int
    proposed_fee_idr: int
    duration_weeks: int


@dataclass(frozen=True)
class PricingIssue:
    field: str
    code: str
    message: str


@dataclass
class PricingResult:
    valid: bool
    inputs: dict
    variable_cost_idr: int | None = None
    total_cost_idr: int | None = None
    gross_profit_idr: int | None = None
    margin_bp: int | None = None  # basis points; 2200 == 22.00 %
    issues: list[PricingIssue] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)
    formula_version: str = FORMULA_VERSION

    def to_dict(self) -> dict:
        d = asdict(self)
        d["margin_pct"] = format_margin(self.margin_bp)
        return d


def _is_int(v: object) -> bool:
    # bool is a subclass of int; reject it explicitly
    return isinstance(v, int) and not isinstance(v, bool)


def validate(raw: dict) -> tuple[PricingInputs | None, list[PricingIssue]]:
    issues: list[PricingIssue] = []
    spec = {
        "target_units": (1, MAX_UNITS, "Target must be a whole number of at least 1."),
        "unit_cost_idr": (0, MAX_IDR, "Unit cost must be a whole rupiah amount of 0 or more."),
        "fixed_cost_idr": (0, MAX_IDR, "Fixed cost must be a whole rupiah amount of 0 or more."),
        "proposed_fee_idr": (1, MAX_IDR, "Proposed fee must be greater than Rp0 to compute a margin."),
        "duration_weeks": (1, 520, "Duration must be between 1 and 520 weeks."),
    }
    clean: dict[str, int] = {}
    for name, (lo, hi, msg) in spec.items():
        v = raw.get(name)
        if v is None:
            issues.append(PricingIssue(name, "REQUIRED", msg))
        elif not _is_int(v):
            issues.append(PricingIssue(name, "NOT_INTEGER", msg))
        elif v < lo or v > hi:
            code = "NEGATIVE" if v < 0 else ("ZERO" if v == 0 else "OUT_OF_RANGE")
            issues.append(PricingIssue(name, code, msg))
        else:
            clean[name] = v
    if issues:
        return None, issues
    return PricingInputs(**clean), []


def calculate(raw: dict) -> PricingResult:
    inputs, issues = validate(raw)
    if inputs is None:
        return PricingResult(valid=False, inputs=dict(raw), issues=issues)

    variable = inputs.target_units * inputs.unit_cost_idr
    total = variable + inputs.fixed_cost_idr
    profit = inputs.proposed_fee_idr - total
    margin = (Decimal(profit) * 10_000 / Decimal(inputs.proposed_fee_idr)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    trace = [
        f"variable_cost = {inputs.target_units:,} × Rp{inputs.unit_cost_idr:,} = Rp{variable:,}",
        f"total_cost = Rp{variable:,} + Rp{inputs.fixed_cost_idr:,} = Rp{total:,}",
        f"gross_margin = (Rp{inputs.proposed_fee_idr:,} − Rp{total:,}) ÷ Rp{inputs.proposed_fee_idr:,}"
        f" = {format_margin(int(margin))}",
    ]
    return PricingResult(
        valid=True,
        inputs=asdict(inputs),
        variable_cost_idr=variable,
        total_cost_idr=total,
        gross_profit_idr=profit,
        margin_bp=int(margin),
        trace=trace,
    )


def format_margin(bp: int | None) -> str | None:
    if bp is None:
        return None
    sign = "-" if bp < 0 else ""
    a = abs(bp)
    return f"{sign}{a // 100}.{a % 100:02d}%"
