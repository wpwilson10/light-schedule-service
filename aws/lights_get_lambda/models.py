from typing import Literal, Optional, TypedDict
from utils import convert_to_unix_timestamp

class ScheduleItem(TypedDict):
    """Represents a scheduled lighting configuration item."""
    time: str  # HH:mm format
    unix_time: int
    warmBrightness: int  # 0-100
    coolBrightness: int  # 0-100

# Add constants for default times
DEFAULT_BED_TIME = "23:00"
DEFAULT_NIGHT_TIME = "23:30"

class DaylightBrightness:
    """Default brightness values for different daylight events."""
    SUNRISE = (75, 100)  # (warm, cool)
    SUNSET = (75,100)
    CIVIL_TWILIGHT_BEGIN = (100, 0)
    CIVIL_TWILIGHT_END = (100, 0)
    BED_TIME = (100, 0)
    NIGHT_TIME = (25, 0)

class LightConfig:
    """Represents the complete lighting configuration."""
    DEFAULT_MODE = "dayNight"  # Add default mode
    MIN_SUNSET_TIME = "19:30"  # 7:30 PM
    TWILIGHT_END_OFFSET = 30   # minutes after sunset

    def __init__(self, mode: Literal["dayNight", "schedule", "demo"], schedule: list[ScheduleItem]):
        self.mode: Literal["dayNight", "schedule", "demo"] = mode
        self.schedule: list[ScheduleItem] = schedule
        self.sunrise: Optional[ScheduleItem] = None
        self.sunset: Optional[ScheduleItem] = None
        self.civil_twilight_begin: Optional[ScheduleItem] = None
        self.civil_twilight_end: Optional[ScheduleItem] = None
        self.bed_time: Optional[ScheduleItem] = None
        self.night_time: Optional[ScheduleItem] = None
        self.natural_sunset: Optional[ScheduleItem] = None
        self.natural_twilight_end: Optional[ScheduleItem] = None

    @classmethod
    def create_empty(cls) -> 'LightConfig':
        """Creates a new LightConfig with default values."""
        return cls(mode=cls.DEFAULT_MODE, schedule=[])

    @classmethod
    def from_dict(cls, data: dict) -> 'LightConfig':
        """Creates a LightConfig instance from a dictionary."""
        if not data:
            return cls.create_empty()

        config = cls(
            data.get('mode', cls.DEFAULT_MODE),
            data.get('schedule', [])
        )
        # Copy any existing schedule items, use None as default
        for field in ['sunrise', 'sunset', 'civil_twilight_begin', 
                     'civil_twilight_end', 'bed_time', 'night_time']:
            setattr(config, field, data.get(field))
        return config

    def to_dict(self) -> dict:
        """Converts the config to a dictionary for JSON serialization."""
        return {
            'mode': self.mode,
            'schedule': self.schedule,
            'sunrise': self.sunrise,
            'sunset': self.sunset,
            'natural_sunset': self.natural_sunset,
            'civil_twilight_begin': self.civil_twilight_begin,
            'civil_twilight_end': self.civil_twilight_end,
            'natural_twilight_end': self.natural_twilight_end,
            'bed_time': self.bed_time,
            'night_time': self.night_time
        }

    def __create_schedule_item(self, time: str, timezone_offset: int, 
                           brightness_warm: int = 0, brightness_cool: int = 0) -> ScheduleItem:
        """Creates a ScheduleItem with the given parameters."""
        return {
            'time': time,
            'unix_time': convert_to_unix_timestamp(time, timezone_offset),
            'warmBrightness': brightness_warm,
            'coolBrightness': brightness_cool
        }

    def update_schedule_times(self, timezone_offset: int) -> None:
        """Updates all schedule items with Unix timestamps."""
        for item in self.schedule:
            if 'time' in item:
                item['unix_time'] = convert_to_unix_timestamp(item['time'], timezone_offset)

    def update_sleep_times(self, timezone_offset: int) -> None:
        """Updates sleep-related schedule items."""
        bed_time = getattr(self.bed_time or {}, 'time', DEFAULT_BED_TIME)
        night_time = getattr(self.night_time or {}, 'time', DEFAULT_NIGHT_TIME)

        self.bed_time = self.__create_schedule_item(
            bed_time, 
            timezone_offset, 
            *DaylightBrightness.BED_TIME
        )
        self.night_time = self.__create_schedule_item(
            night_time, 
            timezone_offset, 
            *DaylightBrightness.NIGHT_TIME
        )

    def __enforce_minimum_time(self, time_str: str, minimum_time: str) -> str:
        """Ensures a time is not earlier than the minimum time."""
        time_parts = list(map(int, time_str.split(':')))
        min_parts = list(map(int, minimum_time.split(':')))
        
        # Convert to minutes for comparison
        time_mins = time_parts[0] * 60 + time_parts[1]
        min_mins = min_parts[0] * 60 + min_parts[1]
        
        if time_mins < min_mins:
            return minimum_time
        return time_str

    def __adjust_twilight_end(self, sunset_time: str) -> str:
        """Calculates twilight end time based on sunset."""
        sunset_parts = list(map(int, sunset_time.split(':')))
        total_minutes = sunset_parts[0] * 60 + sunset_parts[1] + self.TWILIGHT_END_OFFSET
        
        # Convert back to HH:mm format
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return f"{hours:02d}:{minutes:02d}"

    def update_daylight_times(self, sunrise: str, sunset: str,
                            twilight_begin: str, twilight_end: str,
                            timezone_offset: int) -> None:
        """Updates daylight-related schedule items."""
        # Store natural times first
        self.natural_sunset = self.__create_schedule_item(
            sunset, timezone_offset,
            *DaylightBrightness.SUNSET
        )
        self.natural_twilight_end = self.__create_schedule_item(
            twilight_end, timezone_offset,
            *DaylightBrightness.CIVIL_TWILIGHT_END
        )

        # Enforce minimum sunset time and adjust twilight end
        adjusted_sunset = self.__enforce_minimum_time(sunset, self.MIN_SUNSET_TIME)
        adjusted_twilight_end = self.__adjust_twilight_end(adjusted_sunset)

        # Create schedule items with adjusted times
        self.sunrise = self.__create_schedule_item(
            sunrise, timezone_offset, 
            *DaylightBrightness.SUNRISE
        )
        self.sunset = self.__create_schedule_item(
            adjusted_sunset, timezone_offset, 
            *DaylightBrightness.SUNSET
        )
        self.civil_twilight_begin = self.__create_schedule_item(
            twilight_begin, timezone_offset, 
            *DaylightBrightness.CIVIL_TWILIGHT_BEGIN
        )
        self.civil_twilight_end = self.__create_schedule_item(
            adjusted_twilight_end, timezone_offset, 
            *DaylightBrightness.CIVIL_TWILIGHT_END
        )
