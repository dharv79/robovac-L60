from enum import IntEnum, StrEnum


class RoboVacEntityFeature(IntEnum):
    """Supported features of the RoboVac entity."""

    EDGE = 1
    SMALL_ROOM = 2
    CLEANING_TIME = 4
    CLEANING_AREA = 8
    DO_NOT_DISTURB = 16
    AUTO_RETURN = 32
    CONSUMABLES = 64
    ROOM = 128
    ZONE = 256
    MAP = 512
    BOOST_IQ = 1024


class RobovacCommand(StrEnum):
    START_PAUSE = "start_pause"
    DIRECTION = "direction"
    MODE = "mode"
    STATUS = "status"
    RETURN_HOME = "return_home"
    FAN_SPEED = "fan_speed"
    LOCATE = "locate"
    BATTERY = "battery"
    ERROR = "error"
    CLEANING_AREA = "cleaning_area"
    CLEANING_TIME = "cleaning_time"
    AUTO_RETURN = "auto_return"
    DO_NOT_DISTURB = "do_not_disturb"
    BOOST_IQ = "boost_iq"
    CONSUMABLES = "consumables"
    LAST_PROMPT = "last_prompt"


class ModeKey(StrEnum):
    """Semantic names for the DPS 152 values the entity sends or labels."""

    START_AUTO = "start_auto"
    PAUSE = "pause"
    RESUME = "resume"
    STOP_RETURN = "stop_return"
    RETURN_HOME = "return_home"
    STANDBY = "standby"


# Shared defaults: the L60-family protobuf values. A model's `mode_values`
# overrides these key by key; a model without the attribute uses them as is.
DEFAULT_MODE_VALUES = {
    ModeKey.START_AUTO: "BBoCCAE=",
    ModeKey.PAUSE: "AggN",
    ModeKey.RESUME: "AggO",
    ModeKey.STOP_RETURN: "AggP",
    ModeKey.RETURN_HOME: "AggG",
    ModeKey.STANDBY: "AA==",
}

MODE_LABELS = {
    ModeKey.START_AUTO: "Start auto",
    ModeKey.PAUSE: "Pause",
    ModeKey.RESUME: "Resume",
    ModeKey.STOP_RETURN: "Stop return to dock",
    ModeKey.RETURN_HOME: "Stop / Go to charge",
    ModeKey.STANDBY: "Standby",
}


def resolve_mode_values(model) -> dict[str, str]:
    """Semantic key -> raw DPS 152 value for a model class."""
    return {**DEFAULT_MODE_VALUES, **getattr(model, "mode_values", {})}


def resolve_mode_labels(model) -> dict[str, str]:
    """Raw DPS 152 value -> human-readable label for a model class."""
    return {raw: MODE_LABELS[key] for key, raw in resolve_mode_values(model).items()}
