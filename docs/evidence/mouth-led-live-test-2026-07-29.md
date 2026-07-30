# Sota mouth LED live test evidence (2026-07-29)

## Scope and environment

This document records a manually initiated live diagnostic. It is not an
automated hardware test and is not part of the production Composition Root.

| Item | Observed value |
| --- | --- |
| Date | 2026-07-29 |
| Sota IP | `192.168.11.4` |
| Execution path | Windows Python → SSH local forwarding → Sota |
| MasterCtrlPeriod | `16667 us` |
| LED ID | `14` |
| Requested level | `16` |
| Transition duration | `200 ms` |
| Hold duration | `500 ms` |
| Timer ticks | `floor(200000 / 16667) = 11` |
| Lease timer address | `0x01f6` |
| CLI exit status | `0` |

The operator visually confirmed physical mouth LED illumination:

```text
operator_observed_physical_illumination = true
```

The CLI continues to print `physical_illumination=not_verified`, because the
program cannot observe physical light output by itself.

## Probe result

```text
pre_selector=0x008a
pre_target=0
pre_output=16
pre_trigger_pointer=0x01f4

normalization_required=true
normalization_timer_ticks=11
normalized_output=0
normalized_remaining_before=0
normalized_remaining_after=0
normalized_trigger_pointer=0x01f6
normalized_timer_value=65535
normalization_completed=true

rise_timer_ticks=11
rise_output=16
rise_remaining_before=0
rise_remaining_after=0
rise_trigger_pointer=0x01f6
rise_timer_value=65535
rise_reached_target=true
interpolation_reached_target=true

hold_duration_ms=500
hold_completed=true

fall_timer_ticks=11
off_output=0
off_remaining_before=0
off_remaining_after=0
off_trigger_pointer=0x01f6
off_timer_value=65535
fade_down_completed=true
interpolation_output_safe_zero=true

emergency_fade_down_attempted=false
pulse_completed=true
control_sequence_completed=true
cleanup_completed=true

lease_state=released
release_result=OK
lock_released=true

post_selector=0x008a
post_target=0
post_output=0
post_trigger_pointer=0x01f4

routing_state_restored=true
result=success
```

LOCK and UNLOCK were each completed once. The normal path did not execute the
emergency fade-down.

## Post-test read-only observation

Three post-test samples all reported:

```text
MasterCtrlPeriod = 16667
AudioDiff = 0
selector = 138 / 0x008a
target = 0
output = 0
trigger_pointer = 500 / 0x01f4
trigger_timer_value = 65535 / 0xffff
remaining_time = 0
```

This confirms that routing returned to AudioDiff, the interpolation target and
output were zero, and the TriggerPointer returned to `0x01f4`.

## Confirmed behavior and remaining uncertainty

Confirmed on the tested Sota:

* The Python → SotaAppManager → VSMD → mouth LED path produced physical light.
* `floor(200000 / 16667) = 11` control ticks produced the expected transition.
* Selector `0x0c9c` routes `InterpLEDOutput[14]` to the mouth LED.
* Selector `0x008a` restores the AudioDiff route.
* Timer value zero alone does not return Interpolation Output to zero.
* Positive-timer normalization before selector switching and positive-timer
  fade-down produced a safe final Output of zero.
* Sequential reads are not atomic snapshots. Completion was accepted only when
  the reads before and after Output both reported RemainingTime zero.
* The timer slot contained `0xffff` after completed interpolation.

The exact firmware meaning of timer slot value `0xffff` remains unverified.

## Timing note

Observed sequential-read durations were:

| Phase | Observation duration |
| --- | ---: |
| Normalization | `286.932 ms` |
| Rise | `222.331 ms` |
| Fall | `242.134 ms` |

`hold_ms=500` is therefore the minimum hold started after rise confirmation.
It does not guarantee that physical maximum brightness is held for exactly
500 ms. These measurements include Windows-to-Sota SSH forwarding latency.
Running directly on Sota may reduce read latency.

## Gate status

```text
physical_illumination_observed = complete
bounded_rise_hold_fall_sequence = complete
safe_output_zero_after_probe = complete
```

## External evidence inventory

Raw PCAP and large ASCII artifacts are intentionally not stored in Git.
SHA-256 values can be added after the user supplies them.

| Evidence file | SHA-256 |
| --- | --- |
| `mouth_led_normalized_pulse_result.txt` | `5D0882D07B0D20E3905E12B94E405C3A3971F19115F229B641E9C74968FF989F` |
| `mouth_led_normalized_pulse.pcap` | `6277925FB0E406A67E1ECB6361D919D319D001FFA23B62992863ACF3A3ED5457` |
| `mouth_led_normalized_pulse_ascii.txt` | `9A40EBC0351BE10D80463348D196FF369958E6C2EE0261C2DA8F1234AE7BBCE8` |
