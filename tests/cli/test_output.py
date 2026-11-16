from datetime import UTC, datetime, timedelta, timezone

from miniops.cli.output import columns, when

NOON = datetime(2026, 11, 16, 12, 0, 30, tzinfo=UTC)


def test_columns_are_as_wide_as_their_widest_cell() -> None:
    text = columns([("Model", "Task"), ("churn", "regression"), ("demand-forecast", "-")])

    assert text.splitlines() == [
        f"{'Model':<15}  Task",
        f"{'churn':<15}  regression",
        "demand-forecast  -",
    ]


def test_a_line_does_not_end_with_spaces() -> None:
    text = columns([("Version", "Aliases"), ("1.0.0", "")])

    assert text.splitlines() == ["Version  Aliases", "1.0.0"]


def test_a_moment_is_shown_to_the_minute_in_the_given_zone() -> None:
    assert when(NOON, timezone(timedelta(hours=9))) == "2026-11-16 21:00"
    assert when(NOON, timezone(timedelta(hours=-13))) == "2026-11-15 23:00"


def test_a_moment_is_shown_in_local_time_by_default() -> None:
    shown = datetime.strptime(when(NOON), "%Y-%m-%d %H:%M")

    assert shown.astimezone() == NOON.replace(second=0)


def test_no_moment_is_a_dash() -> None:
    assert when(None) == "-"
