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


def describe(error: OSError) -> str:
    """Return the message of a problem of the system, with its files as they are."""
    # str() adds the number of the error and shows a path as Python code, with every
    # backslash doubled on Windows.
    if error.strerror is None:
        return str(error)
    files = (error.filename, error.filename2)
    names = " -> ".join(str(name) for name in files if name is not None)
    return f"{error.strerror}: {names}" if names else error.strerror
