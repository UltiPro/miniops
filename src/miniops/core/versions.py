import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Self

# No leading zeros, so "1.02.0" and "1.2.0" cannot both name the same version.
_PATTERN = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")


class Bump(StrEnum):
    """The part of a version number that a change raises."""

    PATCH = "patch"
    MINOR = "minor"
    MAJOR = "major"


@dataclass(frozen=True, order=True)
class SemVer:
    """A model version number such as ``1.2.0``."""

    major: int
    minor: int
    patch: int

    def __post_init__(self) -> None:
        if min(self.major, self.minor, self.patch) < 0:
            raise ValueError(
                f"Version parts cannot be negative: {self.major}.{self.minor}.{self.patch}"
            )

    @classmethod
    def parse(cls, text: str) -> Self:
        """Read a version from text such as ``"1.2.0"``.

        Raises:
            ValueError: If the text is not MAJOR.MINOR.PATCH.
        """
        match = _PATTERN.fullmatch(text)
        if match is None:
            raise ValueError(
                f"Not a valid version: {text!r}. Expected MAJOR.MINOR.PATCH, for example 1.0.0."
            )
        major, minor, patch = (int(part) for part in match.groups())
        return cls(major, minor, patch)

    def bump(self, kind: Bump) -> Self:
        """Return the next version for the given kind of change."""
        if kind is Bump.MAJOR:
            return type(self)(self.major + 1, 0, 0)
        if kind is Bump.MINOR:
            return type(self)(self.major, self.minor + 1, 0)
        return type(self)(self.major, self.minor, self.patch + 1)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


FIRST_VERSION = SemVer(1, 0, 0)
