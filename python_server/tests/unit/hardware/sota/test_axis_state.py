"""Unit tests for mapping-explicit, hardware-free Sota axis state."""

import os
import subprocess
import sys

import pytest

from robot_controller.hardware.sota import axis_state
from robot_controller.hardware.sota.axis_conversion import (
    sota_internal_to_degrees,
)
from robot_controller.hardware.sota.axis_definitions import SOTA_AXIS_NAMES
from robot_controller.hardware.sota.axis_state import (
    FakeSotaRawAxisStateSource,
    SotaAxisReadIndexMapping,
    SotaRawAxisState,
    SotaRawAxisStateSource,
    create_sota_axis_read_index_mapping,
    decode_sota_axis_state,
    normalize_sota_raw_axis_positions,
    read_sota_axis_state,
)
from robot_controller.hardware.vsmd.sota_memory_map import (
    SERVO_READ_POSITION_LENGTH,
)


def raw_values(fill=0):
    return [fill] * SERVO_READ_POSITION_LENGTH


def test_normalize_detaches_list_as_immutable_exact_length_tuple():
    original = list(range(SERVO_READ_POSITION_LENGTH))

    normalized = normalize_sota_raw_axis_positions(original)
    original[0] = 1000

    assert isinstance(normalized, tuple)
    assert normalized == tuple(range(SERVO_READ_POSITION_LENGTH))
    with pytest.raises(TypeError):
        normalized[0] = 1


@pytest.mark.parametrize("length", [31, 33])
def test_normalize_rejects_wrong_length(length):
    with pytest.raises(ValueError, match="exactly 32"):
        normalize_sota_raw_axis_positions([0] * length)


@pytest.mark.parametrize("value", [True, False, 1.0, "1", None])
def test_normalize_rejects_non_integer_elements(value):
    values = raw_values()
    values[10] = value

    with pytest.raises(TypeError, match="raw positions must contain integers"):
        normalize_sota_raw_axis_positions(values)


def test_normalize_accepts_signed_s16_boundaries():
    values = raw_values()
    values[0] = -32768
    values[-1] = 32767

    normalized = normalize_sota_raw_axis_positions(values)

    assert normalized[0] == -32768
    assert normalized[-1] == 32767


@pytest.mark.parametrize("value", [-32769, 32768])
def test_normalize_rejects_values_outside_signed_s16(value):
    values = raw_values()
    values[5] = value

    with pytest.raises(ValueError, match="signed S16"):
        normalize_sota_raw_axis_positions(values)


@pytest.mark.parametrize(
    "values", ["0" * 32, b"0" * 32, bytearray(32), {0: 0}]
)
def test_normalize_rejects_inappropriate_iterable_containers(values):
    with pytest.raises(TypeError, match="raw positions must be an iterable"):
        normalize_sota_raw_axis_positions(values)


def test_raw_state_is_immutable_and_detached():
    original = raw_values()
    state = SotaRawAxisState(original)
    original[0] = 123

    assert state.raw_positions[0] == 0
    with pytest.raises(TypeError):
        state.raw_positions[0] = 1
    with pytest.raises(AttributeError):
        state.raw_positions = tuple(raw_values())


def test_decode_without_mapping_never_assigns_first_eight_values():
    values = raw_values()
    values[:8] = [175, 525, -9, 100, 200, 300, 400, 500]

    snapshot = decode_sota_axis_state(values)

    assert snapshot.positions_by_name == {}
    assert snapshot.mapped_axis_names == frozenset()
    assert snapshot.unmapped_axis_names == SOTA_AXIS_NAMES
    assert snapshot.mapping_available is False
    assert snapshot.mapping_complete is False


def test_empty_explicit_mapping_is_available_but_incomplete():
    mapping = create_sota_axis_read_index_mapping({})

    snapshot = decode_sota_axis_state(raw_values(), mapping)

    assert snapshot.positions_by_name == {}
    assert snapshot.mapped_axis_names == frozenset()
    assert snapshot.unmapped_axis_names == SOTA_AXIS_NAMES
    assert snapshot.mapping_available is True
    assert snapshot.mapping_complete is False


def test_partial_synthetic_mapping_decodes_only_selected_axes():
    values = raw_values()
    values[20] = 175
    values[3] = -9
    mapping = create_sota_axis_read_index_mapping(
        {"HEAD_Y": 20, "L_ELBO": 3}
    )

    snapshot = decode_sota_axis_state(values, mapping)

    assert snapshot.mapped_axis_names == frozenset(["HEAD_Y", "L_ELBO"])
    assert snapshot.unmapped_axis_names == SOTA_AXIS_NAMES - frozenset(
        ["HEAD_Y", "L_ELBO"]
    )
    assert snapshot.mapping_available is True
    assert snapshot.mapping_complete is False
    head_y = snapshot.positions_by_name["HEAD_Y"]
    assert head_y.axis.name == "HEAD_Y"
    assert head_y.raw_index == 20
    assert head_y.internal_value == 175
    assert head_y.degrees == 9
    left_elbow = snapshot.positions_by_name["L_ELBO"]
    assert left_elbow.raw_index == 3
    assert left_elbow.internal_value == -9
    assert left_elbow.degrees == 0


def test_complete_reordered_synthetic_mapping_makes_no_id_index_assumption():
    synthetic_mapping = {
        "HEAD_R": 13,
        "HEAD_P": 27,
        "HEAD_Y": 9,
        "R_ELBO": 18,
        "R_SHOU": 1,
        "L_ELBO": 22,
        "L_SHOU": 4,
        "BODY_Y": 31,
    }
    values = raw_values()
    for offset, raw_index in enumerate(synthetic_mapping.values()):
        values[raw_index] = (offset + 1) * 10
    mapping = create_sota_axis_read_index_mapping(synthetic_mapping)

    snapshot = decode_sota_axis_state(values, mapping)

    assert snapshot.mapped_axis_names == SOTA_AXIS_NAMES
    assert snapshot.unmapped_axis_names == frozenset()
    assert snapshot.mapping_available is True
    assert snapshot.mapping_complete is True
    for name, raw_index in synthetic_mapping.items():
        assert snapshot.positions_by_name[name].raw_index == raw_index
        assert snapshot.positions_by_name[name].internal_value == values[
            raw_index
        ]


def test_mapping_is_immutable_and_detached_from_original_dict():
    original = {"HEAD_Y": 20}
    mapping = create_sota_axis_read_index_mapping(original)
    original["HEAD_Y"] = 1

    assert mapping.indices_by_name["HEAD_Y"] == 20
    with pytest.raises(TypeError):
        mapping.indices_by_name["HEAD_Y"] = 2
    with pytest.raises(AttributeError):
        mapping.indices_by_name = {}


@pytest.mark.parametrize("mapping", [None, [], (), "HEAD_Y"])
def test_mapping_factory_rejects_non_mappings(mapping):
    with pytest.raises(TypeError, match="index mapping must be a mapping"):
        create_sota_axis_read_index_mapping(mapping)


@pytest.mark.parametrize("name", [True, 1, b"HEAD_Y", None])
def test_mapping_factory_rejects_non_string_names(name):
    with pytest.raises(TypeError, match="axis names must be strings"):
        create_sota_axis_read_index_mapping({name: 1})


def test_mapping_factory_preserves_unknown_name_key_error():
    with pytest.raises(KeyError):
        create_sota_axis_read_index_mapping({"UNKNOWN": 1})


@pytest.mark.parametrize("raw_index", [True, False, 1.0, "1", None])
def test_mapping_factory_rejects_non_integer_indices(raw_index):
    with pytest.raises(TypeError, match="raw indices must be integers"):
        create_sota_axis_read_index_mapping({"HEAD_Y": raw_index})


@pytest.mark.parametrize("raw_index", [-1, 32])
def test_mapping_factory_rejects_indices_outside_raw_snapshot(raw_index):
    with pytest.raises(ValueError, match="raw index must be between"):
        create_sota_axis_read_index_mapping({"HEAD_Y": raw_index})


def test_mapping_factory_rejects_duplicate_raw_indices():
    with pytest.raises(ValueError, match="raw indices must be unique"):
        create_sota_axis_read_index_mapping({"HEAD_Y": 5, "HEAD_P": 5})


def test_decode_uses_java_reverse_conversion_without_external_clamp():
    values = raw_values()
    values[20] = 175
    values[21] = 525
    values[22] = -9
    values[23] = 32767
    mapping = create_sota_axis_read_index_mapping(
        {"HEAD_Y": 20, "HEAD_R": 21, "L_ELBO": 22, "L_SHOU": 23}
    )

    snapshot = decode_sota_axis_state(values, mapping)

    assert snapshot.positions_by_name["HEAD_Y"].degrees == 9
    assert snapshot.positions_by_name["HEAD_R"].degrees == 29
    assert snapshot.positions_by_name["L_ELBO"].degrees == 0
    assert snapshot.positions_by_name["L_SHOU"].degrees == 3276


def test_decode_calls_converter_once_per_mapped_axis(monkeypatch):
    calls = []

    def recording_converter(axis, internal_value):
        calls.append((axis.name, internal_value))
        return sota_internal_to_degrees(axis, internal_value)

    monkeypatch.setattr(
        axis_state, "sota_internal_to_degrees", recording_converter
    )
    mapping = create_sota_axis_read_index_mapping(
        {"HEAD_Y": 20, "L_ELBO": 3}
    )

    decode_sota_axis_state(raw_values(), mapping)

    assert len(calls) == 2
    assert set(calls) == set([("HEAD_Y", 0), ("L_ELBO", 0)])


def test_snapshot_and_mapped_positions_are_immutable():
    mapping = create_sota_axis_read_index_mapping({"HEAD_Y": 20})
    snapshot = decode_sota_axis_state(raw_values(), mapping)
    position = snapshot.positions_by_name["HEAD_Y"]

    with pytest.raises(TypeError):
        snapshot.positions_by_name["HEAD_Y"] = position
    with pytest.raises(AttributeError):
        position.degrees = 10
    with pytest.raises(AttributeError):
        snapshot.mapped_axis_names.add("HEAD_P")
    with pytest.raises(AttributeError):
        snapshot.unmapped_axis_names.remove("HEAD_P")
    with pytest.raises(AttributeError):
        snapshot.mapping_complete = True


def test_fake_source_detaches_configuration_and_counts_reads():
    configured = raw_values()
    configured[20] = 175
    source = FakeSotaRawAxisStateSource(configured)
    configured[20] = 0

    result = source.read_raw_positions()

    assert source.read_count == 1
    assert result[20] == 175


def test_read_helper_reads_source_exactly_once_and_decodes():
    configured = raw_values()
    configured[20] = 175
    source = FakeSotaRawAxisStateSource(configured)
    mapping = create_sota_axis_read_index_mapping({"HEAD_Y": 20})

    snapshot = read_sota_axis_state(source, mapping)

    assert source.read_count == 1
    assert snapshot.positions_by_name["HEAD_Y"].degrees == 9


def test_read_helper_propagates_source_exception_without_retry():
    failure = RuntimeError("synthetic read failure")
    source = FakeSotaRawAxisStateSource(raw_values(), exception=failure)

    with pytest.raises(RuntimeError) as exc_info:
        read_sota_axis_state(source)

    assert exc_info.value is failure
    assert source.read_count == 1


def test_read_helper_validates_invalid_source_result():
    class InvalidSource(SotaRawAxisStateSource):
        def read_raw_positions(self):
            return [0] * 31

    with pytest.raises(ValueError, match="exactly 32"):
        read_sota_axis_state(InvalidSource())


def test_read_helper_rejects_non_source_object():
    with pytest.raises(TypeError, match="source must implement"):
        read_sota_axis_state(object())


def test_module_has_no_default_axis_read_index_mapping():
    assert not any(
        isinstance(value, SotaAxisReadIndexMapping)
        for value in vars(axis_state).values()
    )


def test_module_import_does_not_load_hardware_access_modules_or_threads():
    source_root = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            os.pardir,
            os.pardir,
            os.pardir,
            os.pardir,
            "src",
        )
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = source_root
    script = "\n".join(
        [
            "import sys",
            "import threading",
            "before = tuple(threading.enumerate())",
            "import robot_controller.hardware.sota.axis_state",
            "forbidden = (",
            "    'fcntl',",
            "    'socket',",
            "    'robot_controller.process_lock',",
            "    'robot_controller.hardware.sota.backend',",
            "    'robot_controller.hardware.vsmd.transport',",
            "    'robot_controller.hardware.vsmd.app_manager_transport',",
            ")",
            "assert not any(name in sys.modules for name in forbidden)",
            "assert tuple(threading.enumerate()) == before",
        ]
    )

    subprocess.check_call([sys.executable, "-c", script], env=environment)
