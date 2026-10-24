"""Independent monetary examples: no provider calls and no working database."""
import importlib
import importlib.util
from decimal import Decimal, ROUND_HALF_UP

import pytest


def legal():
    assert importlib.util.find_spec("server.legal") is not None, "Legal calculation module is not implemented"
    return importlib.import_module("server.legal")


def calc(**changes):
    data = {"principal": 100_000_00, "due_on": "2026-10-01", "through_on": "2026-10-11", "reductions": [], "sanction": "art395"}
    data.update(changes)
    return legal().calculate_debt(**data)


def test_official_cache_has_versioned_2026_changes_and_actual_latest_rate():
    rules = legal().rules()
    assert rules["rates_verified_through"] == "2026-10-24"
    assert rules["rates_source"].startswith("https://www.cbr.ru/")
    rates = {row["from_on"]: row["annual_percent"] for row in rules["rate_periods"]}
    assert rates["2026-02-16"] == "15.50"
    assert rates["2026-06-22"] == "14.25"
    assert rates["2026-07-27"] == "14.00"


def test_interest_starts_after_due_date_and_uses_actual_365_days():
    result = calc()
    assert result["days"] == 10
    assert result["interest_amount"] == 38356  # 100000 RUB * 14% * 10/365
    assert result["penalty_amount"] == 0
    assert result["principal_amount"] == 10000000


def test_payment_day_is_included_and_reduction_applies_next_day():
    result = calc(reductions=[{"effective_on": "2026-10-06", "signed_reduction": 4000000}])
    expected = (Decimal(10000000)*Decimal('.14')*5/365 + Decimal(6000000)*Decimal('.14')*5/365).quantize(Decimal(1),rounding=ROUND_HALF_UP)
    assert result["interest_amount"] == int(expected)
    assert result["principal_amount"] == 6000000
    assert [row["days"] for row in result["line_items"]] == [5,5]


def test_on_payment_day_interest_keeps_previous_base_but_claim_principal_already_changes():
    result=calc(reductions=[{"effective_on":"2026-10-11","signed_reduction":4000000},{"effective_on":"2026-10-11","signed_reduction":-1000000}])
    assert result["principal_amount"]==7000000
    assert result["interest_amount"]==38356


def test_leap_year_and_new_year_split_without_360_day_approximation():
    result = calc(due_on="2023-12-30", through_on="2024-01-02")
    assert [row["denominator"] for row in result["line_items"]] == [365,366]
    expected = (Decimal(10000000)*Decimal('.16')/365 + Decimal(10000000)*Decimal('.16')*2/366).quantize(Decimal(1),rounding=ROUND_HALF_UP)
    assert result["interest_amount"] == int(expected)


def test_rate_change_is_split_on_its_effective_date():
    result = calc(due_on="2026-07-25", through_on="2026-07-28")
    assert [(row["from_on"],row["annual_percent"]) for row in result["line_items"]] == [("2026-07-26","14.25"),("2026-07-27","14.00")]


def test_contractual_daily_penalty_uses_principal_reductions_and_cap():
    result = calc(sanction="penalty",penalty_agreed=True,penalty_daily_percent="0.1",penalty_basis="Пункт 7.2 договора",penalty_cap_amount=80000,reductions=[{"effective_on":"2026-10-06","signed_reduction":4000000}])
    assert result["penalty_amount"] == 80000
    assert result["interest_amount"] == 0


def test_no_double_penalty_and_395_without_an_explicit_contractual_basis():
    with pytest.raises(ValueError,match="основан|договор|неустой"):
        calc(sanction="both",penalty_agreed=True,penalty_daily_percent="0.1",penalty_basis="Пункт 7.2")
    with pytest.raises(ValueError,match="основан|договор|неустой"):
        calc(penalty_agreed=True)
    result=calc(sanction="both",penalty_agreed=True,penalty_daily_percent="0.1",penalty_basis="Пункт 7.2",combination_basis="Пункт 7.3 прямо разрешает оба требования")
    assert result["interest_amount"] > 0 and result["penalty_amount"] == 100000


def test_excluded_moratorium_period_is_visible_and_not_charged():
    result=calc(excluded_periods=[{"from_on":"2026-10-04","to_on":"2026-10-06","basis":"Согласованный юристом период исключения"}])
    assert result["interest_amount"] == int((Decimal(10000000)*Decimal('.14')*7/365).quantize(Decimal(1),rounding=ROUND_HALF_UP))
    assert any(row["excluded"] and row["days"]==3 for row in result["line_items"])


def test_explicit_override_requires_complete_nonoverlapping_coverage_and_reason():
    custom=[{"from_on":"2026-10-02","to_on":"2026-10-11","annual_percent":"10.00","source":"https://www.cbr.ru/hd_base/KeyRate/"}]
    with pytest.raises(ValueError,match="основан|причин"):
        calc(rate_override=custom)
    assert calc(rate_override=custom,override_reason="Проверенная юристом история")['interest_amount']==27397
    for rows in (custom+custom,[{**custom[0],"from_on":"2026-10-03"}],[{**custom[0],"annual_percent":"NaN"}]):
        with pytest.raises(ValueError): calc(rate_override=rows,override_reason="Проверено")


def test_refund_signed_reduction_restores_principal_after_its_date():
    result=calc(reductions=[{"effective_on":"2026-09-30","signed_reduction":4000000},{"effective_on":"2026-10-06","signed_reduction":-1000000}])
    assert result["principal_amount"] == 7000000
    assert [row["principal_amount"] for row in result["line_items"]]==[6000000,7000000]


@pytest.mark.parametrize("amount,expected",[(1,1000000),(10000000,1000000),(10000001,1000000),(100000000,5500000),(1000000000,32500000),(5000000000,72500000),(999999999999999,1000000000)])
def test_arbitration_fee_bands_rounded_to_full_rubles(amount,expected):
    assert legal().arbitration_fee(amount,"claim")==expected


def test_court_order_fee_has_verified_8000_ruble_floor_and_limit_includes_sanctions():
    assert legal().arbitration_fee(10000000,"court_order")==800000
    assert legal().arbitration_fee(75000000,"court_order")==2125000
    assert calc(principal=75000000,sanction="none")["order_eligible"] is True
    assert calc(principal=75000000)["order_eligible"] is False


@pytest.mark.parametrize("changes",[{"principal":True},{"principal":100.5},{"through_on":"2026-09-30"},{"reductions":[{"effective_on":"2026-10-03","signed_reduction":10000001}]},{"penalty_daily_percent":"1e900","sanction":"penalty","penalty_agreed":True,"penalty_basis":"Пункт 1"}])
def test_invalid_financial_inputs_fail_instead_of_silently_changing_a_debt(changes):
    with pytest.raises(ValueError):calc(**changes)
