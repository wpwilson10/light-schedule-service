from datetime import datetime, timedelta


def convert_to_hhmm(time_str: str) -> str:
    """Converts time from '4:41:25 PM' format to 'HH:mm' format."""
    time_obj = datetime.strptime(time_str, '%I:%M:%S %p')
    return time_obj.strftime('%H:%M')

def convert_to_unix_timestamp(time_str: str, utc_offset_seconds: int) -> int:
    """
    Converts time from 'HH:mm' format to Unix timestamp using today's date and UTC offset.
    
    Args:
        time_str (str): Time in HH:mm format
        utc_offset_seconds (int): Offset from UTC in seconds
    """
    # Get today's date
    today = datetime.now().date()
    
    # Parse the time
    hour, minute = map(int, time_str.split(':'))
    
    # Combine date and time
    local_time = datetime.combine(today, datetime.min.time().replace(hour=hour, minute=minute))
    
    # Convert to UTC by subtracting the offset
    utc_time = local_time - timedelta(seconds=utc_offset_seconds)
    
    # Convert to Unix timestamp
    return int(utc_time.timestamp())

def convert_to_tomorrow_unix_timestamp(time_str: str, utc_offset_seconds: int) -> int:
    """
    Converts time from 'HH:mm' format to tomorrow's Unix timestamp using UTC offset.
    
    Args:
        time_str (str): Time in HH:mm format
        utc_offset_seconds (int): Offset from UTC in seconds
    """
    # Get tomorrow's date
    tomorrow = datetime.now().date() + timedelta(days=1)
    
    # Parse the time
    hour, minute = map(int, time_str.split(':'))
    
    # Combine date and time
    local_time = datetime.combine(tomorrow, datetime.min.time().replace(hour=hour, minute=minute))
    
    # Convert to UTC by subtracting the offset
    utc_time = local_time - timedelta(seconds=utc_offset_seconds)
    
    # Convert to Unix timestamp
    return int(utc_time.timestamp())