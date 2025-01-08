import json
import os
import boto3
import logging
import urllib3
from datetime import datetime, timedelta
from typing import Any, Optional
from models import LightConfig
from utils import convert_to_hhmm


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

def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
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

        try:
            # Retrieve the object from S3
            response = s3.get_object(Bucket=CONFIG_BUCKET_NAME, Key=CONFIG_KEY_NAME)
            body = response["Body"].read().decode("utf-8")
            data = json.loads(body)
        except (s3.exceptions.NoSuchKey, json.JSONDecodeError) as e:
            logger.warning(f"No valid configuration found: {e}, creating empty config")
            data = {}

        # Create LightConfig instance from S3 data or empty if none exists
        config_data = LightConfig.from_dict(data)
        
        # Get timezone offset from geolocation
        timezone_offset = get_timezone_offset(event)
        
        # Update schedule times if timezone offset is available
        if timezone_offset is not None:
            config_data.update_schedule_times(timezone_offset)
            config_data.update_sleep_times(timezone_offset)

        # Get and update daylight times if available
        daylight_times = get_daylight_times(event)
        if daylight_times:
            sunrise, sunset, twilight_begin, twilight_end, tz_offset = daylight_times
            config_data.update_daylight_times(sunrise, sunset, twilight_begin, 
                                            twilight_end, timezone_offset)

        # Return the JSON payload
        return {
            "statusCode": 200,
            "body": json.dumps(config_data.to_dict()),
            "headers": {"Content-Type": "application/json"},
        }

    except Exception as e:
        logger.error("Error processing request: %s", e, exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal server error"}),
        }

def get_timezone_offset(event: dict[str, Any]) -> Optional[int]:
    """Get timezone offset from geolocation data."""
    ip = get_ip_from_event(event)
    if not ip:
        return None

    geolocation_data = get_geolocation_data(ip)
    if not geolocation_data:
        return None

    return geolocation_data.get("offset")  # offset in seconds from UTC
    
def get_daylight_times(event: dict[str, Any]) -> Optional[tuple[str, str, str, str, int]]:
    """
    Extracts the IP address from the event, fetches geolocation details, and retrieves
    sunrise, sunset, and twilight times based on the latitude, longitude, and timezone.

    Args:
        event (dict[str, Any]): The event data passed by API Gateway.

    Returns:
        Optional[tuple[str, str, str, str, int]]: 
            If successful, returns a tuple containing:
            - sunrise time (HH:mm)
            - sunset time (HH:mm)
            - civil twilight begin time (HH:mm)
            - civil twilight end time (HH:mm)
            - timezone offset in seconds
            If any step fails, returns None.
    """
    # Step 1: Extract IP from the event (request context)
    ip = get_ip_from_event(event)
    if not ip:
        logger.error("IP address not found in request.")
        return None

    # Step 2: Get geolocation details using ip-api
    geolocation_data = get_geolocation_data(ip)
    if not geolocation_data:
        logger.error(f"Failed to get geolocation for IP: {ip}")
        return None

    # Step 3: Extract latitude, longitude, and timezone from geolocation data
    lat, lon, timezone = extract_geolocation_details(geolocation_data)
    if not lat or not lon or not timezone:
        logger.error("Failed to extract necessary geolocation information.")
        return None

    # Get UTC offset from geolocation data
    timezone_offset = geolocation_data.get("offset")  # offset in seconds from UTC
    if timezone_offset is None:
        logger.error("Failed to get timezone offset from geolocation data.")
        return None

    # Step 4: Fetch sunrise and sunset times using latitude, longitude, and timezone
    sunrise_sunset_data = get_sunrise_sunset_data(lat, lon, timezone)
    if not sunrise_sunset_data:
        logger.error("Failed to get sunrise and sunset data.")
        return None

    # Step 5: Format the response with sunrise, sunset, and twilight times
    sunrise: str = sunrise_sunset_data["results"].get("sunrise")
    sunset: str = sunrise_sunset_data["results"].get("sunset")
    civil_twilight_begin: str = sunrise_sunset_data["results"].get("civil_twilight_begin")
    civil_twilight_end: str = sunrise_sunset_data["results"].get("civil_twilight_end")

    # Convert times to HH:mm format
    sunrise_hhmm = convert_to_hhmm(sunrise)
    sunset_hhmm = convert_to_hhmm(sunset)
    twilight_begin_hhmm = convert_to_hhmm(civil_twilight_begin)
    twilight_end_hhmm = convert_to_hhmm(civil_twilight_end)
    
    return (sunrise_hhmm, sunset_hhmm, twilight_begin_hhmm, twilight_end_hhmm, timezone_offset)

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

