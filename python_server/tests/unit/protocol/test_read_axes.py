"""Unit tests for legacy v1 read_axes JSON payload encoding."""

import json

import pytest

from robot_controller.errors import InvalidAxesError
from robot_controller.protocol.read_axes import encode_read_axes


def test_encode_read_axes_returns_compact_top_level_json_object_bytes():
    payload = encode_read_axes({"HEAD_Y": 0, "BODY_Y": 2})

    assert payload == b'{"BODY_Y":2,"HEAD_Y":0}'
    assert payload.startswith(b"{")
    assert not payload.startswith(b"\x00\x00\x00")
    assert json.loads(payload.decode("utf-8")) == {
        "BODY_Y": 2,
        "HEAD_Y": 0,
    }


def test_encode_read_axes_preserves_negative_and_int32_boundary_values():
    payload = encode_read_axes(
        {
            "MIN": -2147483648,
            "NEGATIVE": -1,
            "MAX": 2147483647,
        }
    )
    assert json.loads(payload.decode("utf-8")) == {
        "MAX": 2147483647,
        "MIN": -2147483648,
        "NEGATIVE": -1,
    }


def test_encode_read_axes_handles_non_ascii_axis_name_as_utf8():
    payload = encode_read_axes({"首ヨー": -5})

    assert payload == '{"首ヨー":-5}'.encode("utf-8")
    assert b"\\u" not in payload


def test_encode_read_axes_is_deterministic_across_input_order():
    first = encode_read_axes({"Z": 1, "A": 2})
    second = encode_read_axes({"A": 2, "Z": 1})
    assert first == second == b'{"A":2,"Z":1}'


def test_encode_read_axes_accepts_empty_object():
    assert encode_read_axes({}) == b"{}"


@pytest.mark.parametrize("value", [True, False, 1.0, "1", None])
def test_encode_read_axes_rejects_non_integer_axis_value(value):
    with pytest.raises(InvalidAxesError) as exc_info:
        encode_read_axes({"HEAD_Y": value})
    assert exc_info.value.path == "$.HEAD_Y"
    assert exc_info.value.invalid_value == value


@pytest.mark.parametrize("name", [1, True, None, ("HEAD_Y",)])
def test_encode_read_axes_rejects_non_string_axis_name(name):
    with pytest.raises(InvalidAxesError) as exc_info:
        encode_read_axes({name: 1})
    assert exc_info.value.path == "$"
    assert exc_info.value.invalid_value == name


@pytest.mark.parametrize("axes", [[], "axes", None, 1])
def test_encode_read_axes_rejects_non_mapping_result(axes):
    with pytest.raises(InvalidAxesError) as exc_info:
        encode_read_axes(axes)
    assert exc_info.value.path == "$"

