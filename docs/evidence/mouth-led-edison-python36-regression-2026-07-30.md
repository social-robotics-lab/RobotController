# Sota Mouth LED Edison Python 3.6 Regression Test — 2026-07-30

## 1. Purpose

This document records a manually initiated Sota mouth LED hardware regression
executed directly by CPython 3.6.15 on the Intel Edison through the normal
environment configuration, Composition Root, Application Container, and
`SotaVsmdBackend`.

The run also confirms that bounded TriggerPointer polling resolves the
previously observed visibility delay between the successful AppManager
LOCK/CONVERT response and the VSMD TriggerPointer update.

## 2. Test environment

| Item | Observed value |
| --- | --- |
| Execution host | Intel Edison |
| OS | Yocto Linux |
| Architecture | `i686` |
| Kernel | `Linux 3.10.17-poky-edison+` |
| Python executable | `/home/root/bin/python3` |
| Python version | `3.6.15` |
| AppManager endpoint | `127.0.0.1:6495` |
| VSMD endpoint | `127.0.0.1:6498` |

SSH port forwarding was not used. Python, the Composition Root, AppManager,
VSMD, and the physical robot all ran locally on the Edison.

## 3. Verified invocation path

```text
/home/root/bin/python3
    -> robot_controller.diagnostics.mouth_led_backend_smoke
    -> environment configuration
    -> create_mock_application()
    -> MockApplication.mouth_led_backend
    -> SotaVsmdBackend.pulse_mouth_led()
    -> SotaMouthLedPulseOperation
    -> SotaAppManager
    -> local vsmd_edison
    -> physical mouth LED
```

This run did not invoke the mouth LED Backend through the production protocol,
command handler, Router, or TCP connection handler.

## 4. Test parameters

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

## 5. CLI result

The double opt-in configuration resolved to the Sota VSMD Backend, bounded
pointer polling converged, and the pulse completed:

```text
requested_backend_kind=sota_vsmd
resolved_backend_kind=sota_vsmd
live_hardware_write_enabled=true
mouth_led_backend_configured=true
live_write=true
lock_pointer_poll_attempt=1
lock_pointer_wait_duration_ms=13.00639659166336
lock_pointer_converged=true
lock_pointer_initial_value=0x01f4
lock_pointer_final_value=0x01f6
pulse_completed=true
result=success
```

`lock_pointer_poll_attempt=1` records that the first read after successful
LOCK/CONVERT still observed the previous pointer `0x01f4`. The next bounded
read observed the lease pointer `0x01f6` after approximately `13 ms`.

This directly confirms both the non-atomic visibility previously observed
between AppManager and VSMD and the effectiveness of the bounded polling
change.

## 6. Physical observation

The operator observed physical mouth LED illumination, hold, fade-down, and
turn-off:

```text
operator_observed_physical_illumination=true
```

## 7. Packet capture validation

The packet capture confirmed exactly one operation of each AppManager command:

```text
INTERP_LOCK count = 1
INTERP_CNV_KEY_2_ADDR count = 1
INTERP_UNLOCK count = 1
```

The same key was used for LOCK, CONVERT, and UNLOCK:

```text
python-led-317ff825419443cda72b5ea61081bd28
```

The confirmed sequence was:

```text
INTERP_LOCK
    -> INTERP_CNV_KEY_2_ADDR
    -> TriggerPointer read = 0x01f4
    -> bounded wait
    -> TriggerPointer read = 0x01f6
    -> selector write = 0x0c9c
    -> rise target write = 16
    -> rise timer write = 11
    -> hold
    -> fade-down target write = 0
    -> fade-down timer write = 11
    -> cleanup timer write = 0
    -> selector restore = 0x008a
    -> target restore = 0
    -> INTERP_UNLOCK
```

LOCK and CONVERT were not retried. Only TriggerPointer reads were repeated for
the same lease.

## 8. Read-only post-test observation

All three post-test samples confirmed the stable final state:

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

The observed sample intervals were:

```text
sample 0: 0.000000000 s
sample 1: 0.100200104 s
sample 2: 0.100202017 s
```

The observer confirmed final Output zero, the normal AudioDiff selector, and
the normal TriggerPointer after the pulse.

The observer CSV was generated directly on the Edison as UTF-8 text. It is
not the UTF-16 format produced by the earlier Windows PowerShell
`Tee-Object` capture.

## 9. Regression result

Edison-local CPython 3.6.15 execution, Composition Root selection, Backend
invocation, bounded pointer polling, the physical pulse, cleanup, routing
restoration, and lock release completed successfully:

```text
edison_python36_direct_execution = complete

thin_probe_uses_sota_vsmd_backend = complete
sota_vsmd_backend_regression_on_hardware = complete
composition_root_opt_in_in_code = complete
composition_root_fake_regression = complete
composition_root_opt_in = complete
```

The next gate remains pending:

```text
production_command_integration = pending
```

## 10. Scope limitations

This run did not validate:

* invocation through the production RobotController protocol;
* invocation through a command handler or Router;
* invocation through the TCP connection handler;
* any change to legacy protocol v1.

The production protocol remains disconnected from the mouth LED Backend. The
test was manually initiated and is not an automated hardware test.

## 11. Evidence files and SHA-256

Raw result, observer CSV, PCAP, and ASCII artifacts are intentionally not
added to Git. Their external filenames and recorded SHA-256 values are:

| Evidence file | SHA-256 |
| --- | --- |
| `mouth_led_edison_python36_polling_regression_result.txt` | `1866A1962FBAD54AECB6084654336CC8E2B30D68D56ED9A61094B2853EFBE2B9` |
| `mouth_led_edison_python36_polling_regression_observer.csv` | `C86EA4C80704FE3FBAE699548750FF3DE02BC0007B80FDFA253386F24EBC2968` |
| `mouth_led_edison_python36_polling_regression.pcap` | `F1A689BEB671C6754AD6B8C5359233069D7FC131A0865868F5415CDA1146A003` |
| `mouth_led_edison_python36_polling_regression_ascii.txt` | `DE1EF7F825A323B2117A1D78A624A69B73B01CF1E2866CA33199DB0C551373C1` |

Related Composition Root regression evidence:

[`mouth-led-composition-root-regression-2026-07-30.md`](mouth-led-composition-root-regression-2026-07-30.md)
