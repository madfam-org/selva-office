"""Tests for MexicanBusinessCalendarTool -- business days, holidays, CFDI deadlines."""

from __future__ import annotations

import pytest

from selva_tools.builtins import get_builtin_tools
from selva_tools.builtins.calendar_tools import (
    MEXICAN_HOLIDAYS,
    MexicanBusinessCalendarTool,
    _is_business_day,
    _is_mexican_holiday,
    _next_business_day,
)

# -- Registration test --------------------------------------------------------


def test_tool_registered() -> None:
    tools = get_builtin_tools()
    names = [t.name for t in tools]
    assert "mexican_business_calendar" in names


# -- Holiday detection --------------------------------------------------------


def test_new_year_is_holiday() -> None:
    from datetime import date

    is_hol, name = _is_mexican_holiday(date(2026, 1, 1))
    assert is_hol
    assert "Nuevo" in name


def test_independence_day_is_holiday() -> None:
    from datetime import date

    is_hol, name = _is_mexican_holiday(date(2026, 9, 16))
    assert is_hol
    assert "Independencia" in name


def test_regular_day_not_holiday() -> None:
    from datetime import date

    is_hol, _ = _is_mexican_holiday(date(2026, 4, 14))
    assert not is_hol


def test_christmas_is_holiday() -> None:
    from datetime import date

    is_hol, name = _is_mexican_holiday(date(2026, 12, 25))
    assert is_hol
    assert "Navidad" in name


# -- Business day detection ---------------------------------------------------


def test_weekday_is_business_day() -> None:
    from datetime import date

    # 2026-04-14 is a Tuesday
    assert _is_business_day(date(2026, 4, 14))


def test_saturday_not_business_day() -> None:
    from datetime import date

    # 2026-04-18 is Saturday
    assert not _is_business_day(date(2026, 4, 18))


def test_sunday_not_business_day() -> None:
    from datetime import date

    # 2026-04-19 is Sunday
    assert not _is_business_day(date(2026, 4, 19))


def test_holiday_not_business_day() -> None:
    from datetime import date

    # May 1 (Dia del Trabajo)
    assert not _is_business_day(date(2026, 5, 1))


# -- Next business day -------------------------------------------------------


def test_next_business_day_from_friday() -> None:
    from datetime import date

    # 2026-04-17 is Friday; next should be Monday 2026-04-20
    nbd = _next_business_day(date(2026, 4, 17))
    assert nbd == date(2026, 4, 20)


def test_next_business_day_from_tuesday() -> None:
    from datetime import date

    # 2026-04-14 is Tuesday; next should be Wednesday 2026-04-15
    nbd = _next_business_day(date(2026, 4, 14))
    assert nbd == date(2026, 4, 15)


def test_next_business_day_skips_holiday() -> None:
    from datetime import date

    # 2026-04-30 is Thursday, May 1 is a holiday (Dia del Trabajo)
    # next should skip to May 4 (Monday)
    nbd = _next_business_day(date(2026, 4, 30))
    assert nbd == date(2026, 5, 4)


# -- Tool execution -----------------------------------------------------------


@pytest.mark.asyncio
async def test_is_business_day_action() -> None:
    tool = MexicanBusinessCalendarTool()
    result = await tool.execute(action="is_business_day", date="2026-04-14")
    assert result.success
    assert result.data["is_business_day"] is True
    assert result.data["date"] == "2026-04-14"


@pytest.mark.asyncio
async def test_is_business_day_weekend() -> None:
    tool = MexicanBusinessCalendarTool()
    result = await tool.execute(action="is_business_day", date="2026-04-18")
    assert result.success
    assert result.data["is_business_day"] is False
    assert result.data["is_weekend"] is True


@pytest.mark.asyncio
async def test_is_business_day_holiday() -> None:
    tool = MexicanBusinessCalendarTool()
    result = await tool.execute(action="is_business_day", date="2026-01-01")
    assert result.success
    assert result.data["is_business_day"] is False
    assert result.data["is_holiday"] is True
    assert "holiday_name" in result.data


@pytest.mark.asyncio
async def test_next_business_day_action() -> None:
    tool = MexicanBusinessCalendarTool()
    result = await tool.execute(action="next_business_day", date="2026-04-17")
    assert result.success
    assert result.data["next_business_day"] == "2026-04-20"


@pytest.mark.asyncio
async def test_holidays_in_month() -> None:
    tool = MexicanBusinessCalendarTool()
    result = await tool.execute(action="holidays_in_month", date="2026-01-15")
    assert result.success
    assert result.data["month"] == 1
    holidays = result.data["holidays"]
    assert len(holidays) >= 1
    assert any(h["name"] == "Anio Nuevo" for h in holidays)


@pytest.mark.asyncio
async def test_cfdi_deadline() -> None:
    tool = MexicanBusinessCalendarTool()
    result = await tool.execute(action="cfdi_deadline", date="2026-04-01")
    assert result.success
    assert result.data["type"] == "ISR provisional"
    # The 17th of April 2026 is a Friday, which is a business day
    assert result.data["cfdi_deadline"] == "2026-04-17"


@pytest.mark.asyncio
async def test_cfdi_deadline_weekend_adjustment() -> None:
    tool = MexicanBusinessCalendarTool()
    # January 2026: 17th is Saturday -> should move to Monday 19th
    result = await tool.execute(action="cfdi_deadline", date="2026-01-01")
    assert result.success
    deadline = result.data["cfdi_deadline"]
    # Verify it is a weekday
    from datetime import date as date_type

    d = date_type.fromisoformat(deadline)
    assert d.weekday() < 5


@pytest.mark.asyncio
async def test_unknown_action() -> None:
    tool = MexicanBusinessCalendarTool()
    result = await tool.execute(action="unknown_action")
    assert not result.success
    assert "Unknown action" in result.error


@pytest.mark.asyncio
async def test_invalid_date_format() -> None:
    tool = MexicanBusinessCalendarTool()
    result = await tool.execute(action="is_business_day", date="not-a-date")
    assert not result.success
    assert "Invalid date" in result.error


@pytest.mark.asyncio
async def test_schema_structure() -> None:
    tool = MexicanBusinessCalendarTool()
    schema = tool.parameters_schema()
    assert "action" in schema["properties"]
    assert "date" in schema["properties"]
    assert "action" in schema["required"]
    enum_values = schema["properties"]["action"]["enum"]
    assert "is_business_day" in enum_values
    assert "cfdi_deadline" in enum_values


def test_mexican_holidays_coverage() -> None:
    """All 7 mandatory LFT Art. 74 holidays are present."""
    assert len(MEXICAN_HOLIDAYS) == 7
    # Check specific dates
    assert (1, 1) in MEXICAN_HOLIDAYS
    assert (5, 1) in MEXICAN_HOLIDAYS
    assert (9, 16) in MEXICAN_HOLIDAYS
    assert (12, 25) in MEXICAN_HOLIDAYS
