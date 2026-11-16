from collections.abc import Sequence
from datetime import datetime, tzinfo


def columns(rows: Sequence[Sequence[str]]) -> str:
    """Line up rows of text in columns."""
    widths = [max(map(len, column)) for column in zip(*rows, strict=True)]
    return "\n".join(
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip()
        for row in rows
    )


def when(moment: datetime | None, zone: tzinfo | None = None) -> str:
    """Show a moment to the minute, in local time unless a zone is given. None is a dash."""
    return "-" if moment is None else moment.astimezone(zone).strftime("%Y-%m-%d %H:%M")
