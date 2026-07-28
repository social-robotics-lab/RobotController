"""Executable invariants for the verified Sota VSMD memory map."""

from robot_controller.hardware.vsmd import sota_memory_map as memory_map


def test_mouth_output_address_invariant():
    assert (
        memory_map.INTERP_LED_OUTPUT_BASE
        + memory_map.SOTA_MOUTH_GLOBAL_LED_ID * 2
        == memory_map.MOUTH_LED_NORMAL_SOURCE_ADDRESS
        == memory_map.SOTA_MOUTH_OUTPUT_ADDRESS
        == 3228
    )


def test_confirmed_mouth_identifiers_are_distinct_and_named():
    assert memory_map.SOTA_SECOND_LED_DRIVER_MOUTH_LOCAL_INDEX == 6
    assert memory_map.SOTA_MOUTH_GLOBAL_LED_ID == 14
    assert memory_map.MOUTH_LED_AUDIO_SOURCE_ADDRESS == 138

