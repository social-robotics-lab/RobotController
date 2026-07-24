"""Central legacy v1 command metadata and frame limits."""

import collections
import types


PAYLOAD_NONE = "none"
PAYLOAD_JSON = "json"
PAYLOAD_WAV = "wav"

DEFAULT_COMMAND_MAX_LENGTH = 64
DEFAULT_JSON_MAX_LENGTH = 1024 * 1024
DEFAULT_WAV_MAX_LENGTH = 20 * 1024 * 1024


_CommandSpecBase = collections.namedtuple(
    "_CommandSpecBase", ["name", "payload_kind", "expects_response"]
)


class CommandSpec(_CommandSpecBase):
    """Immutable metadata for one legacy v1 command."""

    __slots__ = ()

    @property
    def payload_required(self):
        # type: () -> bool
        """Return whether the command requires a second frame."""
        return self.payload_kind != PAYLOAD_NONE


COMMAND_SPECS = types.MappingProxyType(
    {
        "play_wav": CommandSpec("play_wav", PAYLOAD_WAV, False),
        "stop_wav": CommandSpec("stop_wav", PAYLOAD_NONE, False),
        "play_pose": CommandSpec("play_pose", PAYLOAD_JSON, False),
        "stop_pose": CommandSpec("stop_pose", PAYLOAD_NONE, False),
        "play_motion": CommandSpec("play_motion", PAYLOAD_JSON, False),
        "stop_motion": CommandSpec("stop_motion", PAYLOAD_NONE, False),
        "play_idle_motion": CommandSpec(
            "play_idle_motion", PAYLOAD_JSON, False
        ),
        "stop_idle_motion": CommandSpec(
            "stop_idle_motion", PAYLOAD_NONE, False
        ),
        "read_axes": CommandSpec("read_axes", PAYLOAD_NONE, True),
    }
)


_LegacyV1LimitsBase = collections.namedtuple(
    "_LegacyV1LimitsBase",
    ["command_max_length", "json_max_length", "wav_max_length"],
)


class LegacyV1Limits(_LegacyV1LimitsBase):
    """Immutable configured frame limits for a legacy v1 session."""

    __slots__ = ()

    def __new__(
        cls,
        command_max_length=DEFAULT_COMMAND_MAX_LENGTH,
        json_max_length=DEFAULT_JSON_MAX_LENGTH,
        wav_max_length=DEFAULT_WAV_MAX_LENGTH,
    ):
        # type: (int, int, int) -> LegacyV1Limits
        values = (
            command_max_length,
            json_max_length,
            wav_max_length,
        )
        for value in values:
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError("legacy v1 frame limits must be integers")
            if value < 0:
                raise ValueError(
                    "legacy v1 frame limits must not be negative"
                )
        return _LegacyV1LimitsBase.__new__(cls, *values)

    def payload_max_length(self, payload_kind):
        # type: (str) -> int
        """Return the configured maximum for a payload metadata kind."""
        if payload_kind == PAYLOAD_JSON:
            return self.json_max_length
        if payload_kind == PAYLOAD_WAV:
            return self.wav_max_length
        raise ValueError(
            "Payload kind {0!r} has no payload limit".format(payload_kind)
        )


DEFAULT_LIMITS = LegacyV1Limits()
