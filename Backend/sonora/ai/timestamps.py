"""Timestamp helpers shared by prompts, output validation and the API."""

import bisect
import re
from collections.abc import Sequence

# Accepts what models actually produce: "04:10", "4:10", "[04:10]", "1:02:03", "04:10.5".
_TIMESTAMP_RE = re.compile(r"^\[?\s*(?:(\d{1,2}):)?(\d{1,3}):(\d{2})(?:[.,]\d+)?\s*\]?$")

# Model timestamps further than this from any real segment are treated as invented.
SNAP_TOLERANCE_SECONDS = 30.0


def format_timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def parse_timestamp(value: object) -> int | None:
    """Seconds for a timestamp-like value, or None when it can't be interpreted."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return int(value) if value >= 0 else None
    if not isinstance(value, str):
        return None
    match = _TIMESTAMP_RE.match(value.strip())
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    if int(seconds) >= 60 or (hours is not None and int(minutes) >= 60):
        return None
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds)


def snap_to_segment(
    seconds: int | None, starts: Sequence[float], tolerance: float = SNAP_TOLERANCE_SECONDS
) -> int | None:
    """Maps a model-produced timestamp onto the nearest real segment start (sorted ``starts``)."""
    if seconds is None or not starts:
        return None
    index = bisect.bisect_left(starts, seconds)
    neighbours = [starts[i] for i in (index - 1, index) if 0 <= i < len(starts)]
    nearest = min(neighbours, key=lambda start: abs(start - seconds))
    return int(nearest) if abs(nearest - seconds) <= tolerance else None
