import pytest

from miniops.core.versions import FIRST_VERSION, Bump, SemVer


def test_parse_reads_three_numbers() -> None:
    assert SemVer.parse("1.20.3") == SemVer(1, 20, 3)


@pytest.mark.parametrize(
    "text", ["", "1.0", "1.0.0.0", "v1.0.0", "1.0.0a1", "01.0.0", "1.0.0 ", "1.-1.0"]
)
def test_parse_rejects_anything_else(text: str) -> None:
    with pytest.raises(ValueError, match="Not a valid version"):
        SemVer.parse(text)


def test_negative_parts_are_rejected() -> None:
    with pytest.raises(ValueError, match="negative"):
        SemVer(1, -1, 0)


def test_text_form_round_trips() -> None:
    assert str(SemVer.parse("2.0.11")) == "2.0.11"


def test_versions_order_by_number_not_by_text() -> None:
    versions = [SemVer.parse(text) for text in ("1.10.0", "1.2.0", "2.0.0", "1.2.1")]

    assert [str(version) for version in sorted(versions)] == ["1.2.0", "1.2.1", "1.10.0", "2.0.0"]


@pytest.mark.parametrize(
    ("kind", "expected"),
    [(Bump.PATCH, "1.2.4"), (Bump.MINOR, "1.3.0"), (Bump.MAJOR, "2.0.0")],
)
def test_bump_raises_one_part_and_resets_the_lower_ones(kind: Bump, expected: str) -> None:
    assert str(SemVer(1, 2, 3).bump(kind)) == expected


def test_a_new_model_starts_at_one_zero_zero() -> None:
    assert str(FIRST_VERSION) == "1.0.0"
