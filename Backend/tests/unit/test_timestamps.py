import pytest

from sonora.ai.timestamps import format_timestamp, parse_timestamp, snap_to_segment


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (0, "00:00"),
        (5.9, "00:05"),
        (250, "04:10"),
        (3599, "59:59"),
        (3880, "1:04:40"),
        (-3, "00:00"),
    ],
)
def test_format(seconds: float, text: str) -> None:
    assert format_timestamp(seconds) == text


@pytest.mark.parametrize(
    ("value", "seconds"),
    [
        ("04:10", 250),
        ("4:10", 250),
        (" [04:10] ", 250),
        ("04:10.75", 250),
        ("1:04:40", 3880),
        ("125:30", 7530),
        (41, 41),
        (41.9, 41),
    ],
)
def test_parse_accepts_model_output_variants(value: object, seconds: int) -> None:
    assert parse_timestamp(value) == seconds


@pytest.mark.parametrize(
    "value", ["04:70", "1:75:00", "abc", "", "4", None, True, -1, [], "04:10pm"]
)
def test_parse_rejects_nonsense(value: object) -> None:
    assert parse_timestamp(value) is None


def test_snap_picks_the_nearest_segment_start() -> None:
    starts = [12.0, 41.0, 80.0, 88.0]
    assert snap_to_segment(41, starts) == 41
    assert snap_to_segment(45, starts) == 41
    assert snap_to_segment(85, starts) == 88
    assert snap_to_segment(0, starts) == 12
    assert snap_to_segment(100, starts) == 88


def test_snap_drops_invented_or_missing_timestamps() -> None:
    starts = [12.0, 41.0]
    assert snap_to_segment(500, starts) is None
    assert snap_to_segment(None, starts) is None
    assert snap_to_segment(12, []) is None
    assert snap_to_segment(60, starts, tolerance=5) is None
