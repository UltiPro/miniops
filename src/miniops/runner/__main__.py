import io
import logging
import sys
from pathlib import Path

from miniops.core.errors import ProtocolError, describe
from miniops.runner.jobs import run

logger = logging.getLogger("miniops.runner")


def main() -> None:
    """Run the job file named on the command line: ``python -m miniops.runner <job file>``.

    The exit code is 0 when the job succeeded and 1 otherwise.
    """
    # What the runner prints is the log of the training. It goes to stdout, where a container
    # logs, always in UTF-8, so that the host reads it the same way on every system.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.captureWarnings(True)
    if len(sys.argv) != 2:
        logger.error("Usage: python -m miniops.runner <job file>")
        raise SystemExit(1)
    try:
        result = run(Path(sys.argv[1]))
    except (ProtocolError, OSError) as error:
        logger.error("%s", describe(error) if isinstance(error, OSError) else error)
        raise SystemExit(1) from None
    raise SystemExit(0 if result.failure is None else 1)


if __name__ == "__main__":
    main()
