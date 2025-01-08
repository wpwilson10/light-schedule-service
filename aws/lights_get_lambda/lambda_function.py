import json
import os
import boto3
import logging
import urllib3
from datetime import datetime, timedelta

from typing import Dict, Any, Optional


# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize S3 client
s3 = boto3.client("s3")

# Initialize HTTP client
http = urllib3.PoolManager()

# Environment variables for the bucket and key (configure these in AWS Lambda settings)
CONFIG_BUCKET_NAME = os.environ.get("CONFIG_BUCKET_NAME", "Default_S3_Bucket")
CONFIG_KEY_NAME = os.environ.get("CONFIG_KEY_NAME", "Config_Key")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler to return lighting configuration from S3 as a JSON payload for an 
    API Gateway GET request.

    Args:
        event (Dict[str, Any]): The event data passed by API Gateway.
        context (Any): The Lambda execution context.

    Returns:
        Dict[str, Any]: Response object to be returned to API Gateway.
    """
    try:
        # Log the incoming event
        logger.info("Received event: %s", json.dumps(event))

        # Validate the HTTP method
        http_method: str = event.get("requestContext", {}).get("http", {}).get("method")
        if http_method != "GET":
            return {
                "statusCode": 405,
                "body": json.dumps({"error": "Only GET method is allowed."}),
            }

        # Retrieve the object from S3
        response = s3.get_object(Bucket=CONFIG_BUCKET_NAME, Key=CONFIG_KEY_NAME)
        body = response["Body"].read().decode("utf-8")
        config_data = json.loads(body)

        # Get sunrise and sunset times
        sunrise, sunset, timezone_offset = get_sunrise_sunset(event)
        if sunrise and sunset:
            config_data['sunrise'] = sunrise
            config_data['sunset'] = sunset

            # Convert times to Unix timestamps
            sunrise_unix = convert_to_unix_timestamp(sunrise, timezone_offset)
            sunset_unix = convert_to_unix_timestamp(sunset, timezone_offset)
            config_data['sunrise_unix'] = sunrise_unix
            config_data['sunset_unix'] = sunset_unix

            # Convert scheduled times to Unix timestamps
            if 'schedule' in config_data:
                for schedule_item in config_data['schedule']:
                    if 'time' in schedule_item:
                        schedule_item['unix_time'] = convert_to_unix_timestamp(
                            schedule_item['time'], 
                            timezone_offset
                        )

        # Return the JSON payload
        return {
            "statusCode": 200,
            "body": json.dumps(config_data),
            "headers": {"Content-Type": "application/json"},
        }

    except s3.exceptions.NoSuchKey:
        logger.error("The requested key does not exist: %s", CONFIG_KEY_NAME)
        return {
            "statusCode": 404,
            "body": json.dumps({"error": "The requested resource was not found."}),
        }

    except Exception as e:
        logger.error("Error processing request: %s", e, exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal server error."}),
        }
    
def get_sunrise_sunset(event: dict[str, Any]) -> tuple[Optional[str], Optional[str], Optional[int]]:
    """
    Extracts the IP address from the event, fetches geolocation details, and retrieves
    sunrise and sunset times based on the latitude, longitude, and timezone.

    Args:
        event (dict[str, Any]): The event data passed by API Gateway.

    Returns:
        tuple[Optional[str], Optional[str], Optional[int]]: Sunrise and sunset times as HH:mm formatted strings, and the timezone offset in seconds
    """
    # Step 1: Extract IP from the event (request context)
    ip = get_ip_from_event(event)
    if not ip:
        logger.error("IP address not found in request.")
        return None, None, None

    # Step 2: Get geolocation details using ip-api
    geolocation_data = get_geolocation_data(ip)
    if not geolocation_data:
        logger.error(f"Failed to get geolocation for IP: {ip}")
        return None, None, None

    # Step 3: Extract latitude, longitude, and timezone from geolocation data
    lat, lon, timezone = extract_geolocation_details(geolocation_data)
    if not lat or not lon or not timezone:
        logger.error("Failed to extract necessary geolocation information.")
        return None, None, None

    # Get UTC offset from geolocation data
    timezone_offset = geolocation_data.get("offset")  # offset in seconds from UTC
    if timezone_offset is None:
        logger.error("Failed to get timezone offset from geolocation data.")
        return None, None, None

    # Step 4: Fetch sunrise and sunset times using latitude, longitude, and timezone
    sunrise_sunset_data = get_sunrise_sunset_data(lat, lon, timezone)
    if not sunrise_sunset_data:
        logger.error("Failed to get sunrise and sunset data.")
        return None, None, None

    # Step 5: Format the response with sunrise and sunset times
    sunrise: str = sunrise_sunset_data["results"].get("sunrise")
    sunset: str = sunrise_sunset_data["results"].get("sunset")

    # Convert times to HH:mm format
    sunrise_hhmm = convert_to_hhmm(sunrise)
    sunset_hhmm = convert_to_hhmm(sunset)
    
    return sunrise_hhmm, sunset_hhmm, timezone_offset

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

def get_ip_from_event(event: dict[str, Any]):
    """Extracts the IP address from the event's request context."""
    return event.get("requestContext", {}).get("http", {}).get("sourceIp")


def get_geolocation_data(ip: str):
    """Fetches geolocation details using ip-api based on the provided IP."""
    geolocation_url = f"http://ip-api.com/json/{ip}?fields=status,message,country,countryCode,regionName,city,zip,lat,lon,timezone,offset,query"
    try:
        geolocation_response = http.request('GET', geolocation_url)
        geolocation_data = json.loads(geolocation_response.data.decode('utf-8'))

        # Check if the status is 'success'
        if geolocation_data.get("status") == "success":
            return geolocation_data
        else:
            return None
    except urllib3.exceptions.RequestError:
        return None


def extract_geolocation_details(
    geolocation_data: dict[str, str]
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Extracts latitude, longitude, and timezone from the geolocation data."""
    lat = geolocation_data.get("lat")
    lon = geolocation_data.get("lon")
    timezone = geolocation_data.get("timezone")
    return lat, lon, timezone


def get_sunrise_sunset_data(
    lat: str, lon: str, timezone: str
) -> Optional[dict[str, Any]]:
    """Fetches sunrise and sunset times using the provided latitude, longitude, and timezone."""
    sunrise_sunset_url = (
        f"https://api.sunrise-sunset.org/json?lat={lat}&lng={lon}&tzid={timezone}"
    )
    try:
        sunrise_sunset_response = http.request('GET', sunrise_sunset_url)
        sunrise_sunset_data = json.loads(sunrise_sunset_response.data.decode('utf-8'))

        # Check if the status is 'OK'
        if sunrise_sunset_data.get("status") == "OK":
            return sunrise_sunset_data
        else:
            return None
    except urllib3.exceptions.RequestError:
        return None

