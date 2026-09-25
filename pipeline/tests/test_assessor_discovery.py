import pytest

from openpali.discovery.assessor import normalize_ain, profile, validate, valid_source_date


def test_requested_parcel_must_match():
    with pytest.raises(ValueError, match="match"):
        validate("parcel_ownershiphistory", "4412013017", {"AIN": "4412013018", "Parcel_OwnershipHistory": []})


@pytest.mark.parametrize("payload", [{"AIN": "4412013017"}, {"error": "unavailable"}, "<html>blocked</html>"])
def test_failure_or_changed_schema_is_not_empty_history(payload):
    with pytest.raises(ValueError):
        validate("parcel_assessmenthistory", "4412013017", payload)


def test_preparation_year_and_multiple_bills_remain_distinct():
    rows = [{"TaxYear": "2026", "BillStatusCodeDesc": "Active"},
            {"TaxYear": "2026", "BillStatusCodeDesc": "Inactive", "NewConstructionDate": "1/1/2007"},
            {"TaxYear": "2027"}]
    payloads = {"parceldetail": {"Parcel": {"CurrentRoll_BaseYear": "2026", "RollPreparation_BaseYear": "2027"}},
                "parcel_assessmenthistory": {"Parcel_AssessmentHistory": rows}}
    result = profile(payloads)
    assert result["current_roll_year"] == "2026"
    assert result["preparation_roll_year"] == "2027"
    assert result["assessment_rows_by_year"] == {"2026": 2, "2027": 1}
    assert len(rows) == 3


def test_ain_rejects_unrelated_digits_and_sql():
    assert normalize_ain("4412-013-017") == "4412013017"
    for value in ("x4412013017", "4412013017 OR 1=1", "441201301"):
        with pytest.raises(ValueError):
            normalize_ain(value)


def test_source_sentinels_and_impossible_dates_are_not_events():
    assert valid_source_date("04/20/2007")
    assert not valid_source_date("0")
    assert not valid_source_date("02/45/1967")
    result = profile({"parcel_assessmenthistory": {"Parcel_AssessmentHistory": [
        {"NewConstructionDate": "0"}, {"NewConstructionDate": "04/20/2007"}]}})
    assert result["construction_date_rows"] == 1
    assert result["construction_date_sentinels"] == {"0": 1}
