from pathlib import Path
from typing import Protocol


class Executor(Protocol):
    """Runs a training or tuning job on a target: in a subprocess, a container or a cloud job."""

    def run(self, job: Path, workdir: Path) -> Path:
        """Run the job described in the ``job`` file and return the path of its result file.

        An executor never touches the metadata store. The host reads the result file and
        records what it says.
        """
