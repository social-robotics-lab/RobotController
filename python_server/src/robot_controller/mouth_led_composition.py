"""Strict configuration and composition for the mouth LED backend."""

import collections
import math
import os
import typing

from robot_controller.errors import ConfigurationError
from robot_controller.hardware.mouth_led_backend import (
    MockMouthLedBackend,
    UnavailableMouthLedBackend,
)
from robot_controller.hardware.sota.backend import SotaVsmdBackend
from robot_controller.hardware.vsmd.app_manager_transport import (
    DEFAULT_APP_MANAGER_HOST,
    DEFAULT_APP_MANAGER_PORT,
    DEFAULT_APP_MANAGER_TIMEOUT_SECONDS,
)
from robot_controller.hardware.vsmd.constants import (
    DEFAULT_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_HOST,
    DEFAULT_MAX_LINE_LENGTH,
    DEFAULT_PORT,
    DEFAULT_READ_TIMEOUT_SECONDS,
    DEFAULT_WRITE_TIMEOUT_SECONDS,
)
from robot_controller.hardware.vsmd.sota_memory_map import (
    SOTA_MOUTH_GLOBAL_LED_ID,
)


BACKEND_UNAVAILABLE = "unavailable"
BACKEND_MOCK = "mock"
BACKEND_SOTA_VSMD = "sota_vsmd"
SUPPORTED_BACKEND_KINDS = (
    BACKEND_UNAVAILABLE,
    BACKEND_MOCK,
    BACKEND_SOTA_VSMD,
)

ENV_BACKEND_KIND = "ROBOT_MOUTH_LED_BACKEND"
ENV_LIVE_WRITE = "ROBOT_HARDWARE_LIVE_WRITE_ENABLED"
ENV_APP_MANAGER_HOST = "ROBOT_SOTA_APP_MANAGER_HOST"
ENV_APP_MANAGER_PORT = "ROBOT_SOTA_APP_MANAGER_PORT"
ENV_APP_MANAGER_TIMEOUT = "ROBOT_SOTA_APP_MANAGER_TIMEOUT"
ENV_VSMD_HOST = "ROBOT_SOTA_VSMD_HOST"
ENV_VSMD_PORT = "ROBOT_SOTA_VSMD_PORT"
ENV_VSMD_CONNECT_TIMEOUT = "ROBOT_SOTA_VSMD_CONNECT_TIMEOUT"
ENV_VSMD_READ_TIMEOUT = "ROBOT_SOTA_VSMD_READ_TIMEOUT"
ENV_VSMD_WRITE_TIMEOUT = "ROBOT_SOTA_VSMD_WRITE_TIMEOUT"
ENV_VSMD_MAX_LINE_LENGTH = "ROBOT_SOTA_VSMD_MAX_LINE_LENGTH"
ENV_MOUTH_LED_ID = "ROBOT_SOTA_MOUTH_LED_ID"


_MouthLedBackendSettingsBase = collections.namedtuple(
    "_MouthLedBackendSettingsBase",
    [
        "backend_kind",
        "live_hardware_write_enabled",
        "app_manager_host",
        "app_manager_port",
        "app_manager_timeout",
        "vsmd_host",
        "vsmd_port",
        "vsmd_connect_timeout",
        "vsmd_read_timeout",
        "vsmd_write_timeout",
        "vsmd_max_line_length",
        "mouth_led_id",
    ],
)


class MouthLedBackendSettings(_MouthLedBackendSettingsBase):
    """Immutable validated settings used by the normal composition root."""

    __slots__ = ()

    def __new__(
        cls,
        backend_kind=BACKEND_UNAVAILABLE,
        live_hardware_write_enabled=False,
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
    ):
        # type: (str, bool, str, int, float, str, int, float, float, float, int, int) -> MouthLedBackendSettings
        if backend_kind not in SUPPORTED_BACKEND_KINDS:
            raise ConfigurationError(
                "unsupported mouth LED backend kind: {0!r}".format(
                    backend_kind
                )
            )
        if not isinstance(live_hardware_write_enabled, bool):
            raise ConfigurationError(
                "live hardware write setting must be boolean"
            )
        _validate_host("AppManager host", app_manager_host)
        _validate_port("AppManager port", app_manager_port)
        _validate_positive_finite(
            "AppManager timeout", app_manager_timeout
        )
        _validate_host("VSMD host", vsmd_host)
        _validate_port("VSMD port", vsmd_port)
        _validate_positive_finite(
            "VSMD connect timeout", vsmd_connect_timeout
        )
        _validate_positive_finite(
            "VSMD read timeout", vsmd_read_timeout
        )
        _validate_positive_finite(
            "VSMD write timeout", vsmd_write_timeout
        )
        _validate_positive_integer(
            "VSMD maximum line length", vsmd_max_line_length
        )
        if (
            isinstance(mouth_led_id, bool)
            or not isinstance(mouth_led_id, int)
            or mouth_led_id != SOTA_MOUTH_GLOBAL_LED_ID
        ):
            raise ConfigurationError(
                "mouth LED ID must be the verified value {0}".format(
                    SOTA_MOUTH_GLOBAL_LED_ID
                )
            )
        return _MouthLedBackendSettingsBase.__new__(
            cls,
            backend_kind,
            live_hardware_write_enabled,
            app_manager_host,
            app_manager_port,
            float(app_manager_timeout),
            vsmd_host,
            vsmd_port,
            float(vsmd_connect_timeout),
            float(vsmd_read_timeout),
            float(vsmd_write_timeout),
            vsmd_max_line_length,
            mouth_led_id,
        )


_MouthLedBackendDiagnosticsBase = collections.namedtuple(
    "_MouthLedBackendDiagnosticsBase",
    [
        "requested_backend_kind",
        "resolved_backend_kind",
        "live_hardware_write_enabled",
        "mouth_led_backend_configured",
        "unavailable_reason",
    ],
)


class MouthLedBackendDiagnostics(_MouthLedBackendDiagnosticsBase):
    """Non-secret result of resolving one backend selection."""

    __slots__ = ()


_MouthLedBackendResolutionBase = collections.namedtuple(
    "_MouthLedBackendResolutionBase", ["backend", "diagnostics"]
)


class MouthLedBackendResolution(_MouthLedBackendResolutionBase):
    """A composed backend and its startup-safe diagnostics."""

    __slots__ = ()


def load_mouth_led_backend_settings(environ=None):
    # type: (typing.Optional[typing.Mapping[str, str]]) -> MouthLedBackendSettings
    """Load strict environment settings without opening any connection."""
    source = os.environ if environ is None else environ
    return MouthLedBackendSettings(
        backend_kind=source.get(ENV_BACKEND_KIND, BACKEND_UNAVAILABLE),
        live_hardware_write_enabled=_parse_boolean(
            ENV_LIVE_WRITE, source.get(ENV_LIVE_WRITE, "false")
        ),
        app_manager_host=source.get(
            ENV_APP_MANAGER_HOST, DEFAULT_APP_MANAGER_HOST
        ),
        app_manager_port=_parse_integer(
            ENV_APP_MANAGER_PORT,
            source.get(ENV_APP_MANAGER_PORT, str(DEFAULT_APP_MANAGER_PORT)),
        ),
        app_manager_timeout=_parse_float(
            ENV_APP_MANAGER_TIMEOUT,
            source.get(
                ENV_APP_MANAGER_TIMEOUT,
                str(DEFAULT_APP_MANAGER_TIMEOUT_SECONDS),
            ),
        ),
        vsmd_host=source.get(ENV_VSMD_HOST, DEFAULT_HOST),
        vsmd_port=_parse_integer(
            ENV_VSMD_PORT, source.get(ENV_VSMD_PORT, str(DEFAULT_PORT))
        ),
        vsmd_connect_timeout=_parse_float(
            ENV_VSMD_CONNECT_TIMEOUT,
            source.get(
                ENV_VSMD_CONNECT_TIMEOUT,
                str(DEFAULT_CONNECT_TIMEOUT_SECONDS),
            ),
        ),
        vsmd_read_timeout=_parse_float(
            ENV_VSMD_READ_TIMEOUT,
            source.get(
                ENV_VSMD_READ_TIMEOUT,
                str(DEFAULT_READ_TIMEOUT_SECONDS),
            ),
        ),
        vsmd_write_timeout=_parse_float(
            ENV_VSMD_WRITE_TIMEOUT,
            source.get(
                ENV_VSMD_WRITE_TIMEOUT,
                str(DEFAULT_WRITE_TIMEOUT_SECONDS),
            ),
        ),
        vsmd_max_line_length=_parse_integer(
            ENV_VSMD_MAX_LINE_LENGTH,
            source.get(
                ENV_VSMD_MAX_LINE_LENGTH,
                str(DEFAULT_MAX_LINE_LENGTH),
            ),
        ),
        mouth_led_id=_parse_integer(
            ENV_MOUTH_LED_ID,
            source.get(ENV_MOUTH_LED_ID, str(SOTA_MOUTH_GLOBAL_LED_ID)),
        ),
    )


def resolve_mouth_led_backend(
    settings,
    unavailable_factory=UnavailableMouthLedBackend,
    mock_factory=MockMouthLedBackend,
    sota_factory=SotaVsmdBackend,
):
    # type: (MouthLedBackendSettings, typing.Any, typing.Any, typing.Any) -> MouthLedBackendResolution
    """Resolve the configured backend without invoking a hardware operation."""
    if not isinstance(settings, MouthLedBackendSettings):
        raise TypeError("settings must be MouthLedBackendSettings")
    requested = settings.backend_kind
    reason = None  # type: typing.Optional[str]
    if requested == BACKEND_UNAVAILABLE:
        backend = unavailable_factory()
        resolved = BACKEND_UNAVAILABLE
        reason = "mouth LED backend is not configured"
        configured = False
    elif requested == BACKEND_MOCK:
        backend = mock_factory()
        resolved = BACKEND_MOCK
        configured = True
    elif not settings.live_hardware_write_enabled:
        reason = (
            "Sota VSMD backend requested, but live hardware write is disabled."
        )
        backend = unavailable_factory(reason)
        resolved = BACKEND_UNAVAILABLE
        configured = False
    else:
        backend = sota_factory(
            app_manager_host=settings.app_manager_host,
            app_manager_port=settings.app_manager_port,
            app_manager_timeout=settings.app_manager_timeout,
            vsmd_host=settings.vsmd_host,
            vsmd_port=settings.vsmd_port,
            vsmd_connect_timeout=settings.vsmd_connect_timeout,
            vsmd_read_timeout=settings.vsmd_read_timeout,
            vsmd_write_timeout=settings.vsmd_write_timeout,
            vsmd_max_line_length=settings.vsmd_max_line_length,
            mouth_led_id=settings.mouth_led_id,
        )
        resolved = BACKEND_SOTA_VSMD
        configured = True
    return MouthLedBackendResolution(
        backend,
        MouthLedBackendDiagnostics(
            requested,
            resolved,
            settings.live_hardware_write_enabled,
            configured,
            reason,
        ),
    )


def _parse_boolean(name, value):
    # type: (str, str) -> bool
    if value == "true":
        return True
    if value == "false":
        return False
    raise ConfigurationError(
        "{0} must be exactly 'true' or 'false'".format(name)
    )


def _parse_integer(name, value):
    # type: (str, str) -> int
    try:
        parsed = int(value, 10)
    except (TypeError, ValueError):
        raise ConfigurationError("{0} must be an integer".format(name))
    if str(parsed) != value:
        raise ConfigurationError("{0} must be an integer".format(name))
    return parsed


def _parse_float(name, value):
    # type: (str, str) -> float
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ConfigurationError("{0} must be a number".format(name))


def _validate_host(name, value):
    # type: (str, str) -> None
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError("{0} must be non-empty".format(name))


def _validate_port(name, value):
    # type: (str, int) -> None
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 1
        or value > 65535
    ):
        raise ConfigurationError(
            "{0} must be between 1 and 65535".format(name)
        )


def _validate_positive_finite(name, value):
    # type: (str, float) -> None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ConfigurationError(
            "{0} must be finite and greater than zero".format(name)
        )


def _validate_positive_integer(name, value):
    # type: (str, int) -> None
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise ConfigurationError(
            "{0} must be a positive integer".format(name)
        )
