"""Verified Sota memory-map addresses exposed by ``vsmd_edison``."""

from robot_controller.hardware.vsmd.typed_memory import (
    calculate_indexed_address,
)


AUDIO_DIFF_VALUE_ADDRESS = 138

MOUTH_LED_SELECTOR_ADDRESS = 292
MOUTH_LED_AUDIO_SOURCE_ADDRESS = 138
MOUTH_LED_NORMAL_SOURCE_ADDRESS = 3228

INTERP_TARGET_TIME_BASE = 496
INTERP_TARGET_TIME_LENGTH = 32

INTERP_LED_TARGET_BASE = 2688
INTERP_LED_TARGET_LENGTH = 16

INTERP_LED_OUTPUT_BASE = 3200
INTERP_LED_OUTPUT_LENGTH = 16

SERVO_READ_POSITION_BASE = 3712
SERVO_READ_POSITION_LENGTH = 32

SOTA_SECOND_LED_DRIVER_MOUTH_LOCAL_INDEX = 6
SOTA_MOUTH_GLOBAL_LED_ID = 14
SOTA_MOUTH_OUTPUT_ADDRESS = calculate_indexed_address(
    INTERP_LED_OUTPUT_BASE, SOTA_MOUTH_GLOBAL_LED_ID, 2
)
SOTA_MOUTH_TARGET_ADDRESS = calculate_indexed_address(
    INTERP_LED_TARGET_BASE, SOTA_MOUTH_GLOBAL_LED_ID, 2
)
SOTA_MOUTH_TARGET_TIME_ADDRESS = calculate_indexed_address(
    INTERP_TARGET_TIME_BASE, SOTA_MOUTH_GLOBAL_LED_ID, 2
)
# Verified directly for LED 14 by the 2026-07-29 AppManager lock capture.
# The array base/allocation rule remains intentionally unspecified.
SOTA_MOUTH_TRIGGER_POINTER_ADDRESS = 0x0B9C

if SOTA_MOUTH_OUTPUT_ADDRESS != MOUTH_LED_NORMAL_SOURCE_ADDRESS:
    raise AssertionError("verified Sota mouth output address invariant failed")
