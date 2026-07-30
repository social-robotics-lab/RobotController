# Sota Mouth LED Composition Root Regression Test — 2026-07-30

## 1. Purpose

This document records a manually initiated hardware regression of the
explicitly opted-in Sota mouth LED Backend through the normal environment
configuration, Composition Root, and Application Container.

The verified invocation path was:

```text
environment configuration
    -> create_mock_application()
    -> MockApplication.mouth_led_backend
    -> SotaVsmdBackend.pulse_mouth_led()
    -> SotaMouthLedPulseOperation
    -> SotaAppManager
    -> vsmd_edison
    -> physical mouth LED
```

This run validates Backend selection and physical control through the
Composition Root path. It does not validate invocation from the production
protocol, command handler, Router, or TCP connection handler.

## 2. Configuration resolution

The double opt-in configuration resolved successfully:

```text
requested_backend_kind=sota_vsmd
resolved_backend_kind=sota_vsmd
live_hardware_write_enabled=true
mouth_led_backend_configured=true
live_write=true
```

The Composition Root created `SotaVsmdBackend`, and the Application Container
supplied that Backend to the smoke CLI. The smoke CLI did not construct the
Sota Backend directly.

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

The timer conversion remained within the previously verified behavior:

```text
floor(200000 / 16667) = 11 ticks
```

## 4. Pulse result

The Composition Root path completed the pulse successfully:

```text
pulse_completed=true
result=success
```

The operator observed the complete physical sequence: rise, illumination,
hold, fade-down, and turn-off.

```text
operator_observed_physical_illumination=true
```

## 5. Read-only post-test observation

All three post-test observer samples reported the following stable state:

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

The final Output was zero, the selector was restored to AudioDiff, and
TriggerPointer was restored to `0x01f4`.

The observer was configured for a requested interval of `100 ms`. The measured
intervals were approximately `437.600 ms` and `335.589 ms`. The `100 ms` value
is the requested interval, not a real-time guarantee; sequential reads through
SSH forwarding have documented best-effort timing.

The observer CSV was saved as UTF-16 by PowerShell `Tee-Object`. This encoding
is part of the external evidence format and does not change the observed
values.

## 6. Packet capture validation

Inspection of the packet capture confirmed:

* exactly one `INTERP_LOCK`;
* exactly one `INTERP_UNLOCK`;
* the LOCK and UNLOCK used the same key;
* the LED ID was `14`;
* the selector was changed to `0x0c9c`;
* rise Target `16` was written;
* rise timer `11` ticks was written;
* fade-down Target `0` was written;
* fade-down timer `11` ticks was written;
* cleanup wrote timer `0`;
* the selector was restored to `0x008a`;
* the final Target was `0`;
* the read-only observer confirmed final Output `0`.

The lock key was:

```text
python-led-0a33d0df7852440ab51a38362e7b39c5
```

The single LOCK/UNLOCK pair completed, and the matching key confirms that the
same AppManager lease was released.

## 7. Regression result

The double opt-in configuration, Composition Root selection, Application
Container exposure, Backend pulse, physical illumination, cleanup, routing
restoration, and lock release all completed successfully:

```text
composition_root_opt_in_in_code = complete
composition_root_fake_regression = complete
composition_root_opt_in = complete

thin_probe_uses_sota_vsmd_backend = complete
sota_vsmd_backend_regression_on_hardware = complete
```

The following gates remain pending:

```text
edison_python36_direct_execution = pending
production_command_integration = pending
```

## 8. Scope limitations

This run did not validate:

* Edison-local CPython 3.6 execution;
* invocation through the production RobotController protocol;
* invocation through a command handler or Router;
* invocation through the TCP connection handler;
* any change to the production protocol or legacy protocol v1.

The production protocol remains disconnected from the mouth LED Backend. The
test was manually initiated and is not an automated hardware test.

## 9. Evidence files and SHA-256

Raw result, observer CSV, PCAP, and ASCII artifacts are intentionally not
added to Git. Their external filenames and recorded SHA-256 values are:

| Evidence file | SHA-256 |
| --- | --- |
| `mouth_led_composition_root_regression_result.txt` | `8AE1C4FD05554D68064CACC64CB9FABD7996A747C4D4D738D8793630A4E54D11` |
| `mouth_led_composition_root_regression_observer.csv` | `8FCF4C7C162D3E523432F2CC8D78E5624DBC05BD6D9D9417B7EE0FA6AB8C9576` |
| `mouth_led_composition_root_regression.pcap` | `05646A4D37DA11DF5F692C1F08F6CEE0E66AA263E4BAF24A7802285CF849F92F` |
| `mouth_led_composition_root_regression_ascii.txt` | `254C62FB79D6DD2CD179580EBB221EA59DF8968E83DAF4DFD06A8DB58E5079FB` |

Related operation-level regression evidence:

[`mouth-led-pulse-operation-regression-2026-07-30.md`](mouth-led-pulse-operation-regression-2026-07-30.md)
