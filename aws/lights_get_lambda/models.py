from collections.abc import Mapping
from typing import Any, NotRequired, TypedDict
from utils import convert_to_unix_timestamp
import time as time_module
import logging

# Configure logging
logger = logging.getLogger(__name__)

class ScheduleItem(TypedDict):
    """Represents a scheduled lighting configuration item."""

    time: str  # HH:mm format
    unixTime: int
    warmBrightness: int  # 0-100
    coolBrightness: int  # 0-100

class BrightnessScheduleEntry(TypedDict):
    """Represents an entry in the unified brightness schedule array."""
    time: str  # HH:mm format
    unixTime: int  # Unix timestamp
    warmBrightness: int  # 0-100
    coolBrightness: int  # 0-100
    label: str  # Entry identifier (e.g., "sunrise", "sunset")

# Type alias for heterogeneous JSON values in S3/API config data.
# Covers mode (str), serverTime (int), brightnessSchedule (list[dict]).
ConfigValue = str | int | list[dict[str, str | int]]

class LightConfigDict(TypedDict):
    """Output shape of to_dict() — the unified API response format."""
    mode: str
    serverTime: int
    brightnessSchedule: list[BrightnessScheduleEntry]

# AWS Lambda event — untyped external contract (AWS SDK does not ship typed events).
# Defined once here so `Any` doesn't repeat across every function signature.
LambdaEvent = dict[str, Any]

class LambdaResponse(TypedDict):
    """AWS Lambda response for API Gateway."""
    statusCode: int
    body: str
    headers: NotRequired[dict[str, str]]

class GeolocationResponse(TypedDict):
    """Response from ip-api.com geolocation API."""
    status: str
    lat: float
    lon: float
    timezone: str
    offset: int  # seconds from UTC

class SunriseSunsetResults(TypedDict):
    """Results object within sunrise-sunset.org API response."""
    sunrise: str
    sunset: str
    civil_twilight_begin: str
    civil_twilight_end: str

class SunriseSunsetResponse(TypedDict):
    """Response from api.sunrise-sunset.org."""
    status: str
    results: SunriseSunsetResults

# Add constants for default times
DEFAULT_BED_TIME = "23:00"
DEFAULT_NIGHT_TIME = "23:30"


class DaylightBrightness:
    """Default brightness values for different daylight events."""

    SUNRISE = (75, 100)  # (warm, cool)
    SUNSET = (75,100)
    CIVIL_TWILIGHT_BEGIN = (25, 0)
    CIVIL_TWILIGHT_END = (100, 0)
    BED_TIME = (100, 0)
    NIGHT_TIME = (25, 0)


class LightConfig:
    """Represents the complete lighting configuration."""
    DEFAULT_MODE = "dayNight"
    MIN_SUNSET_TIME = "19:30"  # 7:30 PM
    TWILIGHT_END_OFFSET = 30   # minutes after sunset

    def __init__(self, mode: str, schedule: list[ScheduleItem]):
        self.mode: str = mode
        self.schedule: list[ScheduleItem] = schedule
        self.sunrise: ScheduleItem | None = None
        self.sunset: ScheduleItem | None = None
        self.civil_twilight_begin: ScheduleItem | None = None
        self.civil_twilight_end: ScheduleItem | None = None
        self.bed_time: ScheduleItem | None = None
        self.night_time: ScheduleItem | None = None

    @classmethod
    def create_empty(cls) -> "LightConfig":
        """Creates a new LightConfig with default values."""
        return cls(mode=cls.DEFAULT_MODE, schedule=[])

    # Standard labels for dayNight mode entries
    STANDARD_LABELS = [
        'civil_twilight_begin', 'sunrise', 'sunset',
        'civil_twilight_end', 'bed_time', 'night_time',
    ]

    @classmethod
    def from_dict(cls, data: Mapping[str, ConfigValue] | None) -> 'LightConfig':
        """Creates a LightConfig instance from a dictionary.

        Expects unified format: data contains 'brightnessSchedule' array with labeled entries.
        """
        if not data:
            return cls.create_empty()

        mode_raw = data.get('mode', cls.DEFAULT_MODE)
        mode = mode_raw if isinstance(mode_raw, str) else cls.DEFAULT_MODE
        config = cls(mode=mode, schedule=[])

        brightness_schedule = data.get('brightnessSchedule')
        if isinstance(brightness_schedule, list):
            for entry in brightness_schedule:
                label = entry.get('label')
                if isinstance(label, str) and label in cls.STANDARD_LABELS:
                    setattr(config, label, ScheduleItem(
                        time=str(entry.get('time', '')),
                        unixTime=int(entry.get('unixTime', 0)),
                        warmBrightness=int(entry.get('warmBrightness', 0)),
                        coolBrightness=int(entry.get('coolBrightness', 0)),
                    ))

        return config

    def to_dict(self) -> LightConfigDict:
        """Converts the config to the unified API format for JSON serialization.

        Returns only:
        - mode: operating mode
        - serverTime: current Unix timestamp
        - brightnessSchedule: array of all schedule entries sorted by time
        """
        return {
            'mode': self.mode,
            'serverTime': self.get_server_time(),
            'brightnessSchedule': self.build_brightness_schedule(),
        }

    def __create_or_update_schedule_item(
        self,
        existing_item: ScheduleItem | None,
        time: str,
        timezone_offset: int,
        default_bright_warm: int,
        default_bright_cool: int,
    ) -> ScheduleItem:
        """Creates a new schedule item or updates existing one preserving brightness values."""

        if existing_item:
            # Update time but preserve brightness
            return ScheduleItem(
                time=time,
                unixTime=convert_to_unix_timestamp(time, timezone_offset),
                warmBrightness=existing_item['warmBrightness'],
                coolBrightness=existing_item['coolBrightness']
            )
        else:
            # Create new item with default brightness
            return ScheduleItem(
                time=time,
                unixTime=convert_to_unix_timestamp(time, timezone_offset),
                warmBrightness=default_bright_warm,
                coolBrightness=default_bright_cool,
            )

    def update_sleep_times(self, timezone_offset: int) -> None:
        """Updates sleep-related times while preserving existing values."""
        # Only update if items don't exist
        if not self.bed_time:
            self.bed_time = ScheduleItem(
                time=DEFAULT_BED_TIME,
                unixTime=convert_to_unix_timestamp(DEFAULT_BED_TIME, timezone_offset),
                warmBrightness=DaylightBrightness.BED_TIME[0],
                coolBrightness=DaylightBrightness.BED_TIME[1],
            )
        else:
            # Update only the unixTime
            self.bed_time['unixTime'] = convert_to_unix_timestamp(
                self.bed_time['time'],
                timezone_offset
            )

        if not self.night_time:
            self.night_time = ScheduleItem(
                time=DEFAULT_NIGHT_TIME,
                unixTime=convert_to_unix_timestamp(DEFAULT_NIGHT_TIME, timezone_offset),
                warmBrightness=DaylightBrightness.NIGHT_TIME[0],
                coolBrightness=DaylightBrightness.NIGHT_TIME[1],
            )
        else:
            # Update only the unixTime
            self.night_time['unixTime'] = convert_to_unix_timestamp(
                self.night_time['time'],
                timezone_offset
            )

    def __enforce_minimum_time(
        self, time_str: str, minimum_time: str
    ) -> tuple[str, bool]:
        """
        Ensures a time is not earlier than the minimum time.
        Returns tuple of (adjusted_time, was_adjusted)
        """
        time_parts = list(map(int, time_str.split(':')))
        min_parts = list(map(int, minimum_time.split(':')))

        # Convert to minutes for comparison
        time_mins = time_parts[0] * 60 + time_parts[1]
        min_mins = min_parts[0] * 60 + min_parts[1]

        if time_mins < min_mins:
            return minimum_time, True
        return time_str, False

    def __adjust_twilight_end(self, sunset_time: str) -> str:
        """Calculates twilight end time based on sunset."""
        sunset_parts = list(map(int, sunset_time.split(':')))
        total_minutes = sunset_parts[0] * 60 + sunset_parts[1] + self.TWILIGHT_END_OFFSET

        # Convert back to HH:mm format
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours:02d}:{minutes:02d}"

    def update_daylight_times(
        self,
        sunrise: str,
        sunset: str,
        twilight_begin: str,
        twilight_end: str,
        timezone_offset: int,
    ) -> None:
        """Updates daylight-related schedule items preserving brightness values."""
        # Enforce minimum sunset time and adjust twilight end only if sunset was adjusted
        adjusted_sunset, was_adjusted = self.__enforce_minimum_time(
            sunset, self.MIN_SUNSET_TIME
        )
        adjusted_twilight_end = (
            self.__adjust_twilight_end(adjusted_sunset)
            if was_adjusted
            else twilight_end
        )

        # Update schedule items preserving brightness values
        self.sunrise = self.__create_or_update_schedule_item(
            self.sunrise, sunrise, timezone_offset, *DaylightBrightness.SUNRISE
        )
        self.sunset = self.__create_or_update_schedule_item(
            self.sunset, adjusted_sunset, timezone_offset, *DaylightBrightness.SUNSET
        )
        self.civil_twilight_begin = self.__create_or_update_schedule_item(
            self.civil_twilight_begin,
            twilight_begin,
            timezone_offset,
            *DaylightBrightness.CIVIL_TWILIGHT_BEGIN,
        )
        self.civil_twilight_end = self.__create_or_update_schedule_item(
            self.civil_twilight_end,
            adjusted_twilight_end,
            timezone_offset,
            *DaylightBrightness.CIVIL_TWILIGHT_END,
        )

    def build_brightness_schedule(self) -> list[BrightnessScheduleEntry]:
        """
        Builds a unified brightness schedule array from all named schedule items.

        Collects civil_twilight_begin, sunrise, sunset, civil_twilight_end,
        bed_time, and night_time into a single array sorted by unixTime.

        Returns:
            List of BrightnessScheduleEntry dicts sorted chronologically.
        """
        entries: list[BrightnessScheduleEntry] = []

        # Map of field names to their labels in the output
        field_label_map = {
            'civil_twilight_begin': 'civil_twilight_begin',
            'sunrise': 'sunrise',
            'sunset': 'sunset',
            'civil_twilight_end': 'civil_twilight_end',
            'bed_time': 'bed_time',
            'night_time': 'night_time',
        }

        for field_name, label in field_label_map.items():
            item: ScheduleItem | None = getattr(self, field_name, None)
            if item is not None:
                try:
                    entries.append(BrightnessScheduleEntry(
                        time=item['time'],
                        unixTime=item['unixTime'],
                        warmBrightness=item['warmBrightness'],
                        coolBrightness=item['coolBrightness'],
                        label=label
                    ))
                except KeyError as e:
                    logger.warning(f"Skipping malformed schedule item '{field_name}': missing key {e}")

        # Sort by unixTime for chronological order
        entries.sort(key=lambda e: e['unixTime'])
        return entries

    def get_server_time(self) -> int:
        """Returns the current Unix timestamp."""
        return int(time_module.time())
