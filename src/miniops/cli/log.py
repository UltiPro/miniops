import logging
from collections import deque
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import override

from miniops.config.project import STATE_DIR, find_root

MAX_BYTES = 1_000_000
KEPT_RECORDS = 1000

_FORMAT = "%(asctime)s %(levelname)s [%(process)d] %(name)s: %(message)s"


class CommandLog(logging.Handler):
    """The log of one command. It reaches the log file only if something goes wrong.

    Records wait in memory. The first warning or error writes them to the file, and after
    that every record goes there directly. A command without problems leaves the file alone.
    """

    def __init__(self, file: Path) -> None:
        """Create a log that writes to ``file`` once it has a reason to."""
        super().__init__()
        self.setFormatter(logging.Formatter(_FORMAT))
        self.file = file
        self.saved = False
        self._waiting: deque[logging.LogRecord] = deque(maxlen=KEPT_RECORDS)
        self._writing = False

    @override
    def emit(self, record: logging.LogRecord) -> None:
        self._waiting.append(record)
        if not self._writing and record.levelno >= logging.WARNING:
            self._writing = True
            self._set_aside_a_full_file()
        if self._writing:
            self._write()

    def _set_aside_a_full_file(self) -> None:
        # The rename fails when there is no file yet, or when another miniOPs process is
        # writing to it (Windows). This command then adds to the file that is there.
        with suppress(OSError):
            if self.file.stat().st_size > MAX_BYTES:
                self.file.replace(self.file.with_name(f"{self.file.name}.1"))

    def _write(self) -> None:
        lines = []
        while self._waiting:
            record = self._waiting.popleft()
            try:
                lines.append(self.format(record))
            except Exception:
                self.handleError(record)
        if not lines:
            return
        # A command never fails because of its log.
        with suppress(OSError):
            self.file.parent.mkdir(parents=True, exist_ok=True)
            with self.file.open("a", encoding="utf-8", errors="backslashreplace") as file:
                file.writelines(f"{line}\n" for line in lines)
            self.saved = True


@contextmanager
def project_log(start: Path | None = None) -> Generator[CommandLog | None]:
    """Collect what miniOPs logs during a command, for the project that ``start`` is in.

    ``start`` is the current directory unless given. Yields None when there is no project.
    """
    file = _log_file(start)
    if file is None:
        yield None
        return
    command_log = CommandLog(file)
    logger = logging.getLogger("miniops")
    level = logger.level
    logger.addHandler(command_log)
    logger.setLevel(logging.DEBUG)
    try:
        yield command_log
    finally:
        logger.setLevel(level)
        logger.removeHandler(command_log)
        command_log.close()


def _log_file(start: Path | None) -> Path | None:
    # Path.cwd() fails when the current directory was removed.
    with suppress(OSError):
        root = find_root(start or Path.cwd())
        if root is not None:
            return root / STATE_DIR / "logs" / "miniops.log"
    return None
