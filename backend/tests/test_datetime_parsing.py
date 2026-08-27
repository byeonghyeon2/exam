from datetime import datetime, timedelta

import pytest

from app.cli import _parse_datetime
from app.importers.dataset_importer import _dt


@pytest.mark.parametrize("parse", [_parse_datetime, _dt])
@pytest.mark.parametrize("value", [None, ""])
def test_empty_datetime(parse, value):
    assert parse(value) is None


@pytest.mark.parametrize("parse", [_parse_datetime, _dt])
@pytest.mark.parametrize("value", [
    "2026-08-27T12:34:56Z", "2026-08-27T12:34:56+00:00",
    "2026-08-27T12:34:56.123456Z", "2026-08-27T12:34:56+09:00",
    "2026-08-27T12:34:56", "2026-08-27",
])
def test_iso_datetime_behavior_is_preserved(parse, value):
    assert parse(value) == datetime.fromisoformat(value.replace("Z", "+00:00"))  # noqa: FURB162


@pytest.mark.parametrize("parse", [_parse_datetime, _dt])
def test_z_is_utc_and_invalid_input_is_rejected(parse):
    assert parse("2026-08-27T12:34:56Z").utcoffset() == timedelta(0)
    with pytest.raises(ValueError):
        parse("not-a-date")
