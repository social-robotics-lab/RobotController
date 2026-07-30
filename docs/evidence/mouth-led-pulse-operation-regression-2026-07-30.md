# Sota Mouth LED Pulse Operation Regression Test — 2026-07-30

## 1. Purpose

This document records a manually initiated hardware regression after the
verified Sota mouth LED pulse sequence was extracted from the diagnostic CLI
into the reusable AppManager/VSMD pulse operation.

The test confirms that the thin diagnostic CLI still reaches the extracted
operation and preserves the previously verified physical behavior. The
diagnostic probe invoked the extracted `SotaMouthLedPulseOperation` directly.
This test did not exercise `SotaVsmdBackend.pulse_mouth_led()`. Consequently,
this run is evidence for the extracted operation and its AppManager/VSMD
lifecycle, but not for the `SotaVsmdBackend` wrapper itself.

## 2. Test environment

| Item | Observed value |
| --- | --- |
| Date | `2026-07-30` |
| Execution host | Windows development machine |
| Target | Vstone Sota / Intel Edison |
| Connection | SSH local port forwarding |
| AppManager forwarding | Windows `127.0.0.1:16495` to Edison `127.0.0.1:6495` |
| VSMD forwarding | Windows `127.0.0.1:16498` to Edison `127.0.0.1:6498` |
| CLI exit status | `0` |

The manually executed command was:

```powershell
python -m robot_controller.hardware.vsmd.app_manager_mouth_led_probe `
  --app-manager-host 127.0.0.1 `
  --app-manager-port 16495 `
  --vsmd-host 127.0.0.1 `
  --vsmd-port 16498 `
  --level 16 `
  --duration-ms 200 `
  --hold-ms 500 `
  --confirm-live-write
```

## 3. Test parameters

| Parameter | Value |
| --- | ---: |
| LED ID | `14` |
| Level | `16` |
| Rise | `200 ms` |
| Hold | `500 ms` |
| Fall | `200 ms` |
| MasterCtrlPeriod | `16667 us` |
| Rise timer ticks | `11` |
| Fall timer ticks | `11` |
| Allocated timer address | `0x01f6` |

The timer conversion was:

```text
floor(200000 / 16667) = 11 ticks
```

## 4. Initial state

```text
pre_selector=0x008a
pre_target=0
pre_output=0
pre_trigger_pointer=0x01f4

normalization_required=false
normalization_timer_ticks=11
normalization_completed=true
```

No pre-normalization write was required because the initial interpolation
Output was already zero. This differs from the 2026-07-29 regression, where
the initial Output was nonzero and normalization was exercised.

## 5. Rise result

```text
lock_acquired=true
timer_address=0x01f6
locked_trigger_pointer=0x01f6

rise_timer_ticks=11
rise_output=16
rise_remaining_before=0
rise_remaining_after=0
rise_remaining_time=0
rise_trigger_pointer=0x01f6
rise_timer_value=65535
rise_poll_attempt=0
rise_reached_target=true
interpolation_reached_target=true
rise_observation_read_duration_ms=154.618
```

The ordered, non-atomic observation was:

```text
pointer=0x01f6
remaining_before=0
output=16
remaining_after=0
timer_value=65535
read_duration_ms=154.618
```

The `0xffff` timer-slot value was recorded only as a diagnostic observation;
it was not used as a success condition.

## 6. Hold result

```text
hold_duration_ms=500
hold_completed=true
```

No additional write was reported during the hold phase.

## 7. Fade-down result

```text
fall_timer_ticks=11
off_output=0
off_remaining_before=0
off_remaining_after=0
off_remaining_time=0
off_trigger_pointer=0x01f6
off_timer_value=65535
off_poll_attempt=0
off_reached_target=true
fade_down_completed=true
interpolation_output_safe_zero=true
off_observation_read_duration_ms=284.099
```

The ordered, non-atomic observation was:

```text
pointer=0x01f6
remaining_before=0
output=0
remaining_after=0
timer_value=65535
read_duration_ms=284.099
```

The normal fade-down succeeded, so the emergency path was not used:

```text
emergency_fade_down_attempted=false
emergency_fade_down_completed=false
```

## 8. Cleanup and lock release

```text
pulse_completed=true
control_sequence_completed=true
cleanup_completed=true
lease_state=released
release_result=OK
lock_released=true
result=success
```

The normal operation, controller cleanup, and single lease release all
completed successfully.

## 9. Final state

```text
post_selector=0x008a
post_target=0
post_output=0
post_trigger_pointer=0x01f4
state_restored=true
routing_state_restored=true
interpolation_output_restored=true
```

The selector returned to AudioDiff, Output remained at the safe value zero,
and TriggerPointer returned from the allocated timer `0x01f6` to `0x01f4`.

## 10. Read-only post-test observation

Three post-test read-only samples were stable:

```text
master_control_period_us=16667
audio_diff=0
selector=138
target=0
output=0
trigger_pointer=500
trigger_timer_value=65535
remaining_time=0
```

Equivalent hexadecimal values are:

```text
selector=0x008a
trigger_pointer=0x01f4
trigger_timer_value=0xffff
```

The observer was configured for a `100 ms` interval. Observed intervals of
`382.8655 ms` and `474.1169 ms` are consistent with its documented
best-effort behavior when sequential reads cross SSH forwarding.

## 11. Physical observation

The operator observed the mouth LED illuminate, hold, fade down, and turn off:

```text
operator_observed_physical_illumination=true
```

The CLI correctly continued to report:

```text
physical_illumination=not_verified
```

This is expected because the program cannot observe physical light output.

## 12. Packet capture

The operator captured Edison loopback traffic for TCP ports 6495 and 6498:

```text
packets captured: 410
packets received by filter: 820
packets dropped by kernel: 0
pcap validation exit code: 0
```

The capture was readable with `tcpdump -r`. This document does not attempt to
reconstruct or assert every TCP write from the packet stream; success is based
on the structured CLI result, stable post-test reads, physical observation,
and capture validity.

## 13. Regression result

The extracted AppManager/VSMD pulse operation passed the physical regression:

```text
validated_operation_extracted_from_probe = complete
thin_probe_uses_extracted_operation = complete
pulse_operation_regression_on_hardware = complete
physical_illumination_observed = complete
bounded_rise_hold_fall_sequence = complete
safe_output_zero_after_probe = complete
```

The following gates remain pending because the current CLI bypasses
`SotaVsmdBackend` and the production Composition Root remains unchanged:

```text
thin_probe_uses_sota_vsmd_backend = pending
sota_vsmd_backend_regression_on_hardware = pending
composition_root_opt_in = pending
edison_python36_direct_execution = pending
production_command_integration = pending
```

## 14. Scope limitations

This run did not validate:

* selection of `SotaVsmdBackend` by the Composition Root;
* direct invocation of `SotaVsmdBackend.pulse_mouth_led()`;
* Edison-local CPython 3.6 execution;
* invocation through a production RobotController command;
* a normalization-required initial state;
* any production default change from the current unavailable/unwired state.

The test was manually initiated. It is not an automated hardware test.

## 15. Evidence files

Raw result, PCAP, and optional ASCII dump artifacts are intentionally not
added to Git. Their expected external filenames are:

```text
mouth_led_backend_regression_result.txt
mouth_led_backend_regression.pcap
mouth_led_backend_regression_ascii.txt
```

SHA-256 values remain placeholders until supplied by the operator:

| Evidence file | SHA-256 |
| --- | --- |
| `mouth_led_backend_regression_result.txt` | `911C402CFF4DB636C3B5D6FF6ED67B548F1A0ECABADE240B6F9FAA75F20F8BCD` |
| `mouth_led_backend_regression.pcap` | `AD8C8C29EEB846F8661C2A6720A61FB3B4F2AD4A4AF1E4FD05212F95E33903E1` |
| `mouth_led_backend_regression_ascii.txt` | `186E744E39DC0F3B4F42CDB13CD4AD40CF90BA46E8A58F6B18F15504A95BCF37` |

Related initial live-test evidence:

[`mouth-led-live-test-2026-07-29.md`](mouth-led-live-test-2026-07-29.md)
