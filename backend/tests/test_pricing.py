from app.domain.pricing import calculate, format_margin

BASE = {"target_units": 3000, "unit_cost_idr": 35_000, "fixed_cost_idr": 12_000_000,
        "proposed_fee_idr": 150_000_000, "duration_weeks": 8}


def test_reference_scenario_is_exact():
    r = calculate(BASE)
    assert r.valid
    assert r.variable_cost_idr == 105_000_000
    assert r.total_cost_idr == 117_000_000
    assert r.gross_profit_idr == 33_000_000
    assert r.margin_bp == 2200
    assert r.to_dict()["margin_pct"] == "22.00%"
    assert all(isinstance(v, int) for v in (r.variable_cost_idr, r.total_cost_idr, r.margin_bp))


def test_margin_rounds_half_up_in_basis_points():
    # 4,002,000 / 40,000,000 = 1000.5 bp → 1001
    r = calculate(BASE | {"target_units": 1000, "unit_cost_idr": 23_998, "proposed_fee_idr": 40_000_000})
    assert r.total_cost_idr == 35_998_000
    assert r.margin_bp == 1001


def test_repeating_decimal_margin():
    r = calculate(BASE | {"target_units": 1000, "proposed_fee_idr": 60_000_000})
    assert r.margin_bp == 2167  # 21.666… %


def test_negative_margin_is_reported_not_hidden():
    r = calculate(BASE | {"target_units": 2000, "proposed_fee_idr": 80_000_000})
    assert r.valid and r.margin_bp == -250
    assert format_margin(r.margin_bp) == "-2.50%"


def test_zero_fee_is_rejected_instead_of_dividing_by_zero():
    r = calculate(BASE | {"proposed_fee_idr": 0})
    assert not r.valid
    assert [(i.field, i.code) for i in r.issues] == [("proposed_fee_idr", "ZERO")]


def test_invalid_inputs_are_listed_per_field():
    r = calculate({"target_units": -5, "unit_cost_idr": 35000.5, "fixed_cost_idr": True, "duration_weeks": 0})
    codes = {i.field: i.code for i in r.issues}
    assert codes == {"target_units": "NEGATIVE", "unit_cost_idr": "NOT_INTEGER", "fixed_cost_idr": "NOT_INTEGER",
                     "proposed_fee_idr": "REQUIRED", "duration_weeks": "ZERO"}
    assert r.total_cost_idr is None


def test_large_values_have_no_float_error():
    big = {"target_units": 9_999_999, "unit_cost_idr": 99_999_999, "proposed_fee_idr": 999_999_999_999_999}
    r = calculate(BASE | big)
    assert r.variable_cost_idr == 9_999_999 * 99_999_999
    assert r.total_cost_idr == 9_999_999 * 99_999_999 + 12_000_000
