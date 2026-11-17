from pathlib import Path


def current_directory() -> Path:
    """Return the directory that the command runs in.

    Raises:
        FileNotFoundError: If it was removed, with a message that says so.
    """
    try:
        return Path.cwd()
    except FileNotFoundError as error:
        raise FileNotFoundError("The current directory does not exist any more.") from error
