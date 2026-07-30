"""Opt-in Sota VSMD backend; it is not wired into the Composition Root."""

import threading
import time
import typing

from robot_controller.hardware.mouth_led_backend import (
    MouthLedBackend,
    validate_mouth_led_pulse,
)
from robot_controller.hardware.vsmd.app_manager_lock import AppManagerLedLock
from robot_controller.hardware.vsmd.app_manager_mouth_led_pulse import (
    SotaMouthLedPulseOperation,
)
from robot_controller.hardware.vsmd.app_manager_transport import (
    AppManagerTcpTransport,
    DEFAULT_APP_MANAGER_HOST,
    DEFAULT_APP_MANAGER_PORT,
    DEFAULT_APP_MANAGER_TIMEOUT_SECONDS,
)
from robot_controller.hardware.vsmd.app_manager_vsmd_lock import (
    AppManagerVsmdLedLock,
)
from robot_controller.hardware.vsmd.constants import (
    DEFAULT_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_HOST,
    DEFAULT_MAX_LINE_LENGTH,
    DEFAULT_PORT,
    DEFAULT_READ_TIMEOUT_SECONDS,
    DEFAULT_WRITE_TIMEOUT_SECONDS,
)
from robot_controller.hardware.vsmd.memory import VsmdMemoryClient
from robot_controller.hardware.vsmd.sota_memory_map import (
    SOTA_MOUTH_GLOBAL_LED_ID,
)
from robot_controller.hardware.vsmd.transport import VsmdTcpTransport
from robot_controller.hardware.vsmd.typed_memory import VsmdTypedMemory


class SotaVsmdBackend(MouthLedBackend):
    """Reusable Sota backend for the physically verified mouth LED pulse."""

    def __init__(
        self,
        app_manager_host=DEFAULT_APP_MANAGER_HOST,
        app_manager_port=DEFAULT_APP_MANAGER_PORT,
        app_manager_timeout=DEFAULT_APP_MANAGER_TIMEOUT_SECONDS,
        vsmd_host=DEFAULT_HOST,
        vsmd_port=DEFAULT_PORT,
        vsmd_connect_timeout=DEFAULT_CONNECT_TIMEOUT_SECONDS,
        vsmd_read_timeout=DEFAULT_READ_TIMEOUT_SECONDS,
        vsmd_write_timeout=DEFAULT_WRITE_TIMEOUT_SECONDS,
        vsmd_max_line_length=DEFAULT_MAX_LINE_LENGTH,
        mouth_led_id=SOTA_MOUTH_GLOBAL_LED_ID,
        vsmd_transport_factory=VsmdTcpTransport,
        app_manager_transport_factory=AppManagerTcpTransport,
        memory_factory=None,
        sleep_function=time.sleep,
        monotonic_function=time.monotonic,
        operation_factory=SotaMouthLedPulseOperation,
        preflight_callback=None,
    ):
        # type: (str, int, float, str, int, float, float, float, int, int, typing.Any, typing.Any, typing.Any, typing.Any, typing.Any, typing.Any, typing.Any) -> None
        if (
            isinstance(mouth_led_id, bool)
            or not isinstance(mouth_led_id, int)
            or mouth_led_id != SOTA_MOUTH_GLOBAL_LED_ID
        ):
            raise ValueError(
                "mouth_led_id must be the verified Sota mouth LED ID {0}".format(
                    SOTA_MOUTH_GLOBAL_LED_ID
                )
            )
        self._app_manager_options = {
            "host": app_manager_host,
            "port": app_manager_port,
            "timeout": app_manager_timeout,
        }
        self._vsmd_options = {
            "host": vsmd_host,
            "port": vsmd_port,
            "connect_timeout": vsmd_connect_timeout,
            "read_timeout": vsmd_read_timeout,
            "write_timeout": vsmd_write_timeout,
            "max_line_length": vsmd_max_line_length,
        }
        self._vsmd_transport_factory = vsmd_transport_factory
        self._app_manager_transport_factory = (
            app_manager_transport_factory
        )
        self._memory_factory = (
            self._default_memory_factory
            if memory_factory is None
            else memory_factory
        )
        self._sleep_function = sleep_function
        self._monotonic_function = monotonic_function
        self._operation_factory = operation_factory
        self._mouth_led_id = mouth_led_id
        self._preflight_callback = preflight_callback
        self._last_pulse_diagnostics = None  # type: typing.Any
        for name, dependency in (
            ("vsmd_transport_factory", vsmd_transport_factory),
            (
                "app_manager_transport_factory",
                app_manager_transport_factory,
            ),
            ("memory_factory", self._memory_factory),
            ("sleep_function", sleep_function),
            ("monotonic_function", monotonic_function),
            ("operation_factory", operation_factory),
        ):
            if not callable(dependency):
                raise TypeError("{0} must be callable".format(name))
        if (
            preflight_callback is not None
            and not callable(preflight_callback)
        ):
            raise TypeError("preflight_callback must be callable or None")
        self._pulse_lock = threading.Lock()

    @property
    def mouth_led_id(self):
        # type: () -> int
        """Return the verified mouth LED ID fixed for this backend."""
        return self._mouth_led_id

    @property
    def last_pulse_diagnostics(self):
        # type: () -> typing.Any
        """Return partial operation diagnostics for the latest pulse attempt."""
        return self._last_pulse_diagnostics

    def pulse_mouth_led(self, level, rise_ms, hold_ms, fall_ms):
        # type: (int, int, int, int) -> typing.Any
        validate_mouth_led_pulse(level, rise_ms, hold_ms, fall_ms)
        with self._pulse_lock:
            self._last_pulse_diagnostics = None
            vsmd_transport = self._vsmd_transport_factory(
                **self._vsmd_options
            )
            app_manager_transport = self._app_manager_transport_factory(
                **self._app_manager_options
            )
            led_lock = AppManagerVsmdLedLock(
                AppManagerLedLock(transport=app_manager_transport)
            )
            with vsmd_transport:
                memory = self._memory_factory(vsmd_transport)
                operation = self._operation_factory(
                    memory,
                    led_lock,
                    level,
                    rise_ms,
                    hold_ms=hold_ms,
                    fall_ms=fall_ms,
                    sleep_function=self._sleep_function,
                    monotonic_function=self._monotonic_function,
                )
                self._last_pulse_diagnostics = operation
                if self._preflight_callback is None:
                    return operation.run()
                return operation.run(
                    preflight_callback=self._preflight_callback
                )

    @staticmethod
    def _default_memory_factory(transport):
        # type: (VsmdTcpTransport) -> VsmdTypedMemory
        return VsmdTypedMemory(VsmdMemoryClient(transport))
