# Sota Mouth LED Production Command Visual Confirmation — 2026-07-30

## 1. Purpose

This document records a manually initiated physical confirmation of the
production v2 mouth LED command on the Intel Edison. The command was received
through the production TCP port, dispatched through the current command
route, and completed through the Composition Root supplied
`MouthLedBackend`.

This confirmation closes the production mouth LED golden-path gate. It does
not claim that the complete `VsmdSotaCommandTarget` or all production robot
commands have been integrated.

## 2. Test environment

| Item | Observed value |
| --- | --- |
| Test time | Approximately 2026-07-30 17:21 JST |
| Execution host | Intel Edison |
| Python version | CPython 3.6.15 |
| Production command endpoint | `127.0.0.1:22222` |
| AppManager endpoint | `127.0.0.1:6495` |
| VSMD endpoint | `127.0.0.1:6498` |

## 3. Verified invocation

The production command was:

```text
command=v2/mouth_led_pulse
request_id=edison-production-mouth-led-visual-002
level=16
rise_ms=200
hold_ms=1000
fall_ms=200
send_count=1
```

The verified route was:

```text
production TCP port 127.0.0.1:22222
    -> v2 production connection handler
    -> CurrentCommandRouter
    -> existing serialized command service
    -> MouthLedBackendCommandTarget
    -> Composition Root supplied MouthLedBackend
    -> SotaVsmdBackend.pulse_mouth_led()
    -> SotaMouthLedPulseOperation
    -> SotaAppManager at 127.0.0.1:6495
    -> vsmd_edison at 127.0.0.1:6498
    -> physical mouth LED
```

The production response was successful:

```text
status=success
pulse_completed=true
lock_pointer_converged=true
```

The operator confirmed physical turn-off after the complete pulse:

```text
operator_observed_physical_turn_off=true
```

## 4. Packet capture validation

Packet capture inspection confirmed exactly one execution of each AppManager
operation:

```text
INTERP_LOCK count = 1
INTERP_CNV_KEY_2_ADDR count = 1
INTERP_UNLOCK count = 1
```

LOCK, CONVERT, and UNLOCK used the same key. The confirmed LED and
interpolation sequence was:

```text
LED ID = 14
selector write = 0x0c9c
rise target write = 16
rise timer address = 0x01f6
rise timer write = 11 ticks
interpolation output reached = 16
hold = 1000 ms
fade-down completed
cleanup timer write = 0
cleanup target write = 0
selector restore = 0x008a
production response status = success
```

The capture therefore confirms one production command, one Backend pulse,
one AppManager lease, and one release. No automatic retry was observed.

## 5. Read-only post-test observation

All three observer samples confirmed the same safe final state:

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

The final Output was zero, routing was restored to AudioDiff, the normal
TriggerPointer was restored, and the lease was released.

## 6. Gate result

The production mouth LED golden path is complete:

```text
edison_python36_direct_execution = complete
composition_root_opt_in = complete
production_command_integration_in_code = complete
production_command_register_regression = complete
production_command_physical_confirmation = complete
production_command_integration = complete
phase7_mouth_led_golden_path = complete
```

The following gates remain pending:

```text
phase7_fault_recovery = pending
full_sota_command_target_integration = pending
```

## 7. Scope limitations

This test validates one production v2 command:
`v2/mouth_led_pulse`. It validates command reception, current-protocol
decoding, routing, serialized dispatch, the Composition Root supplied mouth
LED Backend, physical illumination and turn-off, cleanup, routing
restoration, and lock release.

It does not validate:

* full `VsmdSotaCommandTarget` Composition Root integration;
* legacy v1 Sota command execution;
* all servo, motion, audio, or other LED production commands;
* lock contention, non-LIFO release, or abnormal process termination;
* Phase 7 fault-recovery behavior.

## 8. Evidence files and SHA-256

Raw evidence files are intentionally not added to Git. Their external
filenames and recorded SHA-256 values are:

| Evidence file | SHA-256 |
| --- | --- |
| `mouth_led_production_visual_confirmation_operator.txt` | `886a373a2dc042619befd027fd3702f82b92855b894cef116ec8b02cb2647db4` |
| `mouth_led_production_visual_confirmation_result.txt` | `f65920123af681967836c93c60ff2fc56bf0f6217251bae02d7a9e6b7e03ce16` |
| `mouth_led_production_visual_confirmation_observer.csv` | `199438d34d58b9c3d6f45ed14c1e4e578b83b06073e8e4d83c7891dc92a1c14b` |
| `mouth_led_production_visual_confirmation_server.log` | `22882fbde622968c17223c5793a33eae7b0e2fe681d9062d7cd90c1ca204dda0` |
| `mouth_led_production_visual_confirmation_ascii.txt` | `cf18aa6b1cd1d6abe27bb946d3bdb7e5a334648c161adec064d317b4df09667f` |
| `mouth_led_production_visual_confirmation.pcap` | `6acf2fad9273bf1412e08cfbae50592d0b88ca9ba1e13e725264c39e601b1d9a` |

Related Edison-local Backend evidence:

[`mouth-led-edison-python36-regression-2026-07-30.md`](mouth-led-edison-python36-regression-2026-07-30.md)
