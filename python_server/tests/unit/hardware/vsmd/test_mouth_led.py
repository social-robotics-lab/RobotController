"""Sota mouth-LED state restoration with fake memory, lock, and timer."""

import struct

import pytest

from robot_controller.hardware.vsmd.errors import (
    VsmdLedLockUnavailableError,
    VsmdMouthLedCleanupError,
    VsmdUnexpectedMouthSelectorError,
    VsmdValidationError,
)
from robot_controller.hardware.vsmd.memory import VsmdMemoryAccess
from robot_controller.hardware.vsmd.mouth_led import (
    SotaMouthLedController,
    VsmdInterpolationTimer,
    VsmdLedLock,
    VsmdMemoryInterpolationTimer,
)
from robot_controller.hardware.vsmd.sota_memory_map import (
    INTERP_LED_OUTPUT_BASE,
    INTERP_TARGET_TIME_BASE,
    MOUTH_LED_AUDIO_SOURCE_ADDRESS,
    MOUTH_LED_NORMAL_SOURCE_ADDRESS,
    MOUTH_LED_SELECTOR_ADDRESS,
    SOTA_MOUTH_GLOBAL_LED_ID,
    SOTA_MOUTH_OUTPUT_ADDRESS,
    SOTA_MOUTH_TARGET_ADDRESS,
)
from robot_controller.hardware.vsmd.typed_memory import VsmdTypedMemory


class FakeMemory(VsmdMemoryAccess):
    def __init__(self, events, selector=138, target=0):
        self.events = events
        self.data = bytearray(b"\x00" * 65536)
        self.data[
            MOUTH_LED_SELECTOR_ADDRESS:MOUTH_LED_SELECTOR_ADDRESS + 2
        ] = struct.pack("<H", selector)
        self.data[
            SOTA_MOUTH_TARGET_ADDRESS:SOTA_MOUTH_TARGET_ADDRESS + 2
        ] = struct.pack("<h", target)
        self.writes = []
        self.write_failures = {}

    def read_bytes(self, address, size):
        self.events.append(("read", address, size))
        return bytes(self.data[address:address + size])

    def write_bytes(self, address, payload):
        payload = bytes(payload)
        self.events.append(("write", address, payload))
        self.writes.append((address, payload))
        error = self.write_failures.get(len(self.writes))
        if error is not None:
            raise error
        self.data[address:address + len(payload)] = payload


class FakeLock(VsmdLedLock):
    def __init__(self, events, acquire_error=None, release_error=None):
        self.events = events
        self.acquire_error = acquire_error
        self.release_error = release_error

    def acquire(self, key, led_ids):
        self.events.append(("acquire", key, tuple(led_ids)))
        if self.acquire_error is not None:
            raise self.acquire_error

    def release(self, key, led_ids):
        self.events.append(("release", key, tuple(led_ids)))
        if self.release_error is not None:
            raise self.release_error


class FakeTimer(VsmdInterpolationTimer):
    def __init__(self, events, error=None):
        self.events = events
        self.error = error

    def set_duration(self, led_id, duration_ms):
        self.events.append(("timer", led_id, duration_ms))
        if self.error is not None:
            raise self.error


def make_controller(selector=138, target=0, lock=None, timer=None):
    events = []
    raw_memory = FakeMemory(events, selector=selector, target=target)
    if lock is None:
        lock = FakeLock(events)
    if timer is None:
        timer = FakeTimer(events)
    controller = SotaMouthLedController(
        VsmdTypedMemory(raw_memory), timer, led_lock=lock
    )
    return controller, raw_memory, events


def unpack_u16(memory, address):
    return struct.unpack("<H", bytes(memory.data[address:address + 2]))[0]


def unpack_s16(memory, address):
    return struct.unpack("<h", bytes(memory.data[address:address + 2]))[0]


def test_lock_failure_causes_no_memory_access_or_write():
    events = []
    lock = FakeLock(events, acquire_error=RuntimeError("busy"))
    raw_memory = FakeMemory(events)
    controller = SotaMouthLedController(
        VsmdTypedMemory(raw_memory), FakeTimer(events), led_lock=lock
    )
    with pytest.raises(RuntimeError):
        controller.disable_voice_sync()
    assert events == [
        (
            "acquire",
            "robot-controller-python-mouth",
            (SOTA_MOUTH_GLOBAL_LED_ID,),
        )
    ]
    assert raw_memory.writes == []


def test_default_production_lock_fails_closed_before_memory_access():
    events = []
    raw_memory = FakeMemory(events)
    controller = SotaMouthLedController(
        VsmdTypedMemory(raw_memory), FakeTimer(events)
    )
    with pytest.raises(VsmdLedLockUnavailableError):
        controller.disable_voice_sync()
    assert events == []


def test_golden_behavior_saves_routes_sets_and_restores():
    controller, memory, events = make_controller(selector=138, target=0)
    controller.disable_voice_sync()
    assert controller.is_voice_sync_disabled
    assert unpack_u16(memory, MOUTH_LED_SELECTOR_ADDRESS) == 3228
    controller.set_brightness(16, 1000)
    assert unpack_s16(memory, SOTA_MOUTH_TARGET_ADDRESS) == 16
    controller.turn_off(0)
    assert unpack_s16(memory, SOTA_MOUTH_TARGET_ADDRESS) == 0
    controller.enable_voice_sync()
    assert not controller.is_voice_sync_disabled
    assert unpack_u16(memory, MOUTH_LED_SELECTOR_ADDRESS) == 138
    assert unpack_s16(memory, SOTA_MOUTH_TARGET_ADDRESS) == 0
    assert (
        "acquire",
        "robot-controller-python-mouth",
        (14,),
    ) in events
    assert (
        "release",
        "robot-controller-python-mouth",
        (14,),
    ) in events
    assert ("timer", 14, 1000) in events


def test_original_selector_and_target_are_restored():
    controller, memory, unused_events = make_controller(
        selector=MOUTH_LED_NORMAL_SOURCE_ADDRESS, target=23
    )
    controller.disable_voice_sync()
    controller.set_brightness(16, 1)
    controller.close()
    assert unpack_u16(memory, MOUTH_LED_SELECTOR_ADDRESS) == 3228
    assert unpack_s16(memory, SOTA_MOUTH_TARGET_ADDRESS) == 23


def test_output_region_is_never_written():
    controller, memory, unused_events = make_controller()
    controller.disable_voice_sync()
    controller.set_brightness(16, 1000)
    controller.close()
    output_end = INTERP_LED_OUTPUT_BASE + 16 * 2
    assert SOTA_MOUTH_OUTPUT_ADDRESS == 3228
    assert all(
        not (INTERP_LED_OUTPUT_BASE <= address < output_end)
        for address, unused_payload in memory.writes
    )


def test_memory_timer_uses_verified_led_index_and_little_endian_u16():
    events = []
    memory = FakeMemory(events)
    timer = VsmdMemoryInterpolationTimer(VsmdTypedMemory(memory))
    timer.set_duration(14, 1000)
    assert memory.writes == [
        (INTERP_TARGET_TIME_BASE + 14 * 2, b"\xe8\x03")
    ]


def test_context_restores_after_body_exception():
    controller, memory, events = make_controller(target=7)
    with pytest.raises(RuntimeError):
        with controller:
            controller.set_brightness(16, 1)
            raise RuntimeError("body failed")
    assert unpack_u16(memory, MOUTH_LED_SELECTOR_ADDRESS) == 138
    assert unpack_s16(memory, SOTA_MOUTH_TARGET_ADDRESS) == 7
    assert any(event[0] == "release" for event in events)


def test_interpolation_failure_immediately_restores_and_releases():
    events = []
    memory = FakeMemory(events, target=7)
    timer = FakeTimer(events, error=RuntimeError("timer failed"))
    controller = SotaMouthLedController(
        VsmdTypedMemory(memory), timer, led_lock=FakeLock(events)
    )
    controller.disable_voice_sync()
    with pytest.raises(VsmdMouthLedCleanupError) as caught:
        controller.set_brightness(16, 1)
    assert isinstance(caught.value.operation_error, RuntimeError)
    assert isinstance(caught.value.cleanup_error, RuntimeError)
    assert unpack_u16(memory, MOUTH_LED_SELECTOR_ADDRESS) == 138
    assert unpack_s16(memory, SOTA_MOUTH_TARGET_ADDRESS) == 7
    assert not controller.is_voice_sync_disabled
    assert any(event[0] == "release" for event in events)


def test_context_restores_after_keyboard_interrupt():
    controller, memory, events = make_controller(target=9)
    with pytest.raises(KeyboardInterrupt):
        with controller:
            raise KeyboardInterrupt()
    assert unpack_u16(memory, MOUTH_LED_SELECTOR_ADDRESS) == 138
    assert unpack_s16(memory, SOTA_MOUTH_TARGET_ADDRESS) == 9
    assert any(event[0] == "release" for event in events)


def test_close_is_idempotent():
    controller, unused_memory, events = make_controller()
    controller.disable_voice_sync()
    controller.close()
    controller.close()
    assert len([event for event in events if event[0] == "release"]) == 1


def test_selector_restore_precedes_original_target_restore():
    controller, unused_memory, events = make_controller(target=11)
    controller.disable_voice_sync()
    events[:] = []
    controller.close()
    selector_index = events.index(
        (
            "write",
            MOUTH_LED_SELECTOR_ADDRESS,
            struct.pack("<H", MOUTH_LED_AUDIO_SOURCE_ADDRESS),
        )
    )
    target_index = events.index(
        (
            "write",
            SOTA_MOUTH_TARGET_ADDRESS,
            struct.pack("<h", 11),
        )
    )
    assert selector_index < target_index
    assert events[-1][0] == "release"


def test_release_is_attempted_when_restoration_write_fails():
    controller, memory, events = make_controller(target=5)
    controller.disable_voice_sync()
    memory.write_failures[len(memory.writes) + 1] = RuntimeError(
        "safe value failed"
    )
    with pytest.raises(RuntimeError):
        controller.close()
    assert any(event[0] == "release" for event in events)
    assert not controller.is_voice_sync_disabled


@pytest.mark.parametrize("selector", [0, 137, 139, 3227, 3229, 65535])
def test_unknown_original_selector_fails_closed(selector):
    controller, memory, events = make_controller(selector=selector)
    with pytest.raises(VsmdUnexpectedMouthSelectorError):
        controller.disable_voice_sync()
    assert memory.writes == []
    assert events[-1][0] == "release"


@pytest.mark.parametrize(
    "value,duration",
    [(-1, 1), (256, 1), (True, 1), (1, -1), (1, 65536), (1, True)],
)
def test_invalid_brightness_or_duration_is_rejected_without_target_write(
    value, duration
):
    controller, memory, unused_events = make_controller()
    controller.disable_voice_sync()
    write_count = len(memory.writes)
    with pytest.raises(VsmdValidationError):
        controller.set_brightness(value, duration)
    assert len(memory.writes) == write_count
