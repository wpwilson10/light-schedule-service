from datetime import datetime, timezone, timedelta


def convert_to_hhmm(time_str: str) -> str:
    """Converts time from '4:41:25 PM' format to 'HH:mm' format."""
    time_obj = datetime.strptime(time_str, "%I:%M:%S %p")
    return time_obj.strftime("%H:%M")


def convert_to_unix_timestamp(time_str: str, utc_offset_seconds: int) -> int:
    """
    Converts time from 'HH:mm' format to Unix timestamp using local date and UTC offset.

    Args:
        time_str (str): Time in HH:mm format
        utc_offset_seconds (int): Offset from UTC in seconds
    """
    # Get current time in UTC
    now_utc = datetime.now(timezone.utc)

    # Convert to local time
    local_offset = timedelta(seconds=utc_offset_seconds)
    now_local = now_utc + local_offset
    today_local = now_local.date()

    # Parse the time
    hour, minute = map(int, time_str.split(":"))

    # Combine local date and time
    local_time = datetime.combine(
        today_local,
        datetime.min.time().replace(hour=hour, minute=minute),
        tzinfo=timezone(local_offset),
    )

    # Convert to UTC timestamp
    return int(local_time.astimezone(timezone.utc).timestamp())


def convert_to_tomorrow_unix_timestamp(time_str: str, utc_offset_seconds: int) -> int:
    """
    Converts time from 'HH:mm' format to tomorrow's Unix timestamp using UTC offset.

    Args:
        time_str (str): Time in HH:mm format
        utc_offset_seconds (int): Offset from UTC in seconds
    """
    # Get current time in UTC
    now_utc = datetime.now(timezone.utc)

    # Convert to local time
    local_offset = timedelta(seconds=utc_offset_seconds)
    now_local = now_utc + local_offset
    tomorrow_local = now_local.date() + timedelta(days=1)

    # Parse the time
    hour, minute = map(int, time_str.split(":"))

    # Combine local date and time
    local_time = datetime.combine(
        tomorrow_local,
        datetime.min.time().replace(hour=hour, minute=minute),
        tzinfo=timezone(local_offset),
    )

    # Convert to UTC timestamp
    return int(local_time.astimezone(timezone.utc).timestamp())
