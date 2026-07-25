"""Legacy v1 read_axes response payload encoding."""

import json
import typing

from robot_controller.errors import InvalidAxesError


def encode_read_axes(axes):
    # type: (typing.Mapping[str, int]) -> bytes
    """Encode validated axes as deterministic UTF-8 JSON object bytes.

    The returned bytes contain no legacy frame header. Framing remains the
    responsibility of the existing session layer.
    """
    try:
        items = axes.items()
    except AttributeError:
        raise InvalidAxesError("$", axes, "a mapping of axis names to integers")

    validated = {}
    for name, value in items:
        if not isinstance(name, str):
            raise InvalidAxesError("$", name, "a string axis name")
        path = "$." + name
        if isinstance(value, bool) or not isinstance(value, int):
            raise InvalidAxesError(
                path, value, "an integer axis value, excluding bool"
            )
        validated[name] = value

    text = json.dumps(
        validated,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    try:
        return text.encode("utf-8", errors="strict")
    except UnicodeEncodeError as error:
        raise InvalidAxesError(
            "$", "<unencodable axis name>", "UTF-8 encodable axis names"
        ) from error

