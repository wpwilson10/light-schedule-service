from __future__ import annotations

import json
import os
import boto3
import logging
import urllib3
from typing import TYPE_CHECKING
from models import (
    ConfigValue, GeolocationResponse, LambdaEvent, LambdaResponse,
    LightConfig, SunriseSunsetResponse,
)
from utils import convert_to_hhmm

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize S3 client
s3: S3Client = boto3.client("s3")  # pyright: ignore[reportUnknownMemberType]

# Initialize HTTP client
http = urllib3.PoolManager()

# Environment variables for the bucket and key (configure these in AWS Lambda settings)
CONFIG_BUCKET_NAME = os.environ.get("CONFIG_BUCKET_NAME", "Default_S3_Bucket")
CONFIG_KEY_NAME = os.environ.get("CONFIG_KEY_NAME", "Config_Key")

def lambda_handler(event: LambdaEvent, context: object) -> LambdaResponse:
    """
    AWS Lambda handler to return lighting configuration from S3 as a JSON payload for an
    API Gateway GET request.

    Args:
        event: API Gateway v2 event (untyped — AWS SDK does not ship typed events).
        context: Lambda execution context (unused).

    Returns:
        API Gateway response with statusCode, body, and optional headers.
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

        data: dict[str, ConfigValue] = {}
        try:
            # Retrieve the object from S3
            response = s3.get_object(Bucket=CONFIG_BUCKET_NAME, Key=CONFIG_KEY_NAME)
            body = response["Body"].read().decode("utf-8")
            data = json.loads(body)
        except (s3.exceptions.NoSuchKey, json.JSONDecodeError) as e:
            logger.warning(f"No valid configuration found: {e}, creating empty config")

        # Create LightConfig instance from S3 data or empty if none exists
        config_data = LightConfig.from_dict(data)

        # Get timezone offset with fallback chain: IP geolocation → cached → UTC
        timezone_offset = get_timezone_offset_with_cache(event, data)

        # Update schedule times (timezone_offset defaults to 0/UTC if all lookups fail)
        config_data.update_sleep_times(timezone_offset)

        # Get and update daylight times if available
        daylight_times = get_daylight_times(event)
        if daylight_times:
            sunrise, sunset, twilight_begin, twilight_end, tz_offset = daylight_times
            config_data.update_daylight_times(sunrise, sunset, twilight_begin,
                                            twilight_end, timezone_offset)
            # Cache timezone offset in S3 config if we got it from geolocation
            if data.get("cached_timezone_offset") != tz_offset:
                cache_timezone_offset(tz_offset)

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

def get_timezone_offset(event: LambdaEvent) -> int | None:
    """Get timezone offset from geolocation data."""
    ip = get_ip_from_event(event)
    if not ip:
        return None

    geolocation_data = get_geolocation_data(ip)
    if not geolocation_data:
        return None

    return geolocation_data["offset"]


def get_timezone_offset_with_cache(event: LambdaEvent, cached_config: dict[str, ConfigValue]) -> int:
    """
    Get timezone offset with fallback chain: IP geolocation → cached → UTC (0).

    Args:
        event: API Gateway event containing request context with source IP
        cached_config: Previously stored S3 config that may contain cached timezone

    Returns:
        Timezone offset in seconds from UTC. Falls back to 0 (UTC) if all lookups fail.
    """
    # Try IP geolocation first
    ip_offset = get_timezone_offset(event)
    if ip_offset is not None:
        logger.info(f"Using timezone offset from IP geolocation: {ip_offset}")
        return ip_offset

    # Fall back to cached timezone from S3 config
    cached_offset = cached_config.get("cached_timezone_offset")
    if isinstance(cached_offset, int):
        logger.info(f"Using cached timezone offset: {cached_offset}")
        return cached_offset

    # Fall back to UTC
    logger.warning("No timezone available, falling back to UTC (offset=0)")
    return 0


def cache_timezone_offset(offset: int) -> None:
    """
    Cache timezone offset in S3 config for future fallback use.

    Args:
        offset: Timezone offset in seconds from UTC
    """
    try:
        # Read current config
        config: dict[str, ConfigValue] = {}
        try:
            response = s3.get_object(Bucket=CONFIG_BUCKET_NAME, Key=CONFIG_KEY_NAME)
            body = response["Body"].read().decode("utf-8")
            config = json.loads(body)
        except Exception:
            pass

        # Update cached timezone
        config["cached_timezone_offset"] = offset

        # Write back to S3
        s3.put_object(
            Bucket=CONFIG_BUCKET_NAME,
            Key=CONFIG_KEY_NAME,
            Body=json.dumps(config),
            ContentType="application/json",
        )
        logger.info(f"Cached timezone offset {offset} to S3")
    except Exception as e:
        logger.warning(f"Failed to cache timezone offset: {e}")
    
def get_daylight_times(event: LambdaEvent) -> tuple[str, str, str, str, int] | None:
    """
    Extracts the IP address from the event, fetches geolocation details, and retrieves
    sunrise, sunset, and twilight times based on the latitude, longitude, and timezone.

    Args:
        event (LambdaEvent): The event data passed by API Gateway.

    Returns:
        tuple[str, str, str, str, int] | None:
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
    timezone_offset = geolocation_data["offset"]

    # Step 4: Fetch sunrise and sunset times using latitude, longitude, and timezone
    sunrise_sunset_data = get_sunrise_sunset_data(lat, lon, timezone)
    if not sunrise_sunset_data:
        logger.error("Failed to get sunrise and sunset data.")
        return None

    # Step 5: Format the response with sunrise, sunset, and twilight times
    results = sunrise_sunset_data["results"]
    sunrise = results["sunrise"]
    sunset = results["sunset"]
    civil_twilight_begin = results["civil_twilight_begin"]
    civil_twilight_end = results["civil_twilight_end"]

    # Convert times to HH:mm format
    sunrise_hhmm = convert_to_hhmm(sunrise)
    sunset_hhmm = convert_to_hhmm(sunset)
    twilight_begin_hhmm = convert_to_hhmm(civil_twilight_begin)
    twilight_end_hhmm = convert_to_hhmm(civil_twilight_end)
    
    return (sunrise_hhmm, sunset_hhmm, twilight_begin_hhmm, twilight_end_hhmm, timezone_offset)

def get_ip_from_event(event: LambdaEvent) -> str | None:
    """Extracts the IP address from the event's request context."""
    return event.get("requestContext", {}).get("http", {}).get("sourceIp")


def get_geolocation_data(ip: str) -> GeolocationResponse | None:
    """Fetches geolocation details using ip-api based on the provided IP."""
    geolocation_url = f"http://ip-api.com/json/{ip}?fields=status,message,country,countryCode,regionName,city,zip,lat,lon,timezone,offset,query"
    try:
        geolocation_response = http.request('GET', geolocation_url)
        geolocation_data: GeolocationResponse = json.loads(geolocation_response.data.decode('utf-8'))

        # Check if the status is 'success'
        if geolocation_data["status"] == "success":
            return geolocation_data
        else:
            return None
    except urllib3.exceptions.RequestError:
        return None


def extract_geolocation_details(
    geolocation_data: GeolocationResponse,
) -> tuple[float, float, str]:
    """Extracts latitude, longitude, and timezone from the geolocation data."""
    return geolocation_data["lat"], geolocation_data["lon"], geolocation_data["timezone"]


def get_sunrise_sunset_data(
    lat: float, lon: float, timezone: str,
) -> SunriseSunsetResponse | None:
    """Fetches sunrise and sunset times using the provided latitude, longitude, and timezone."""
    sunrise_sunset_url = (
        f"https://api.sunrise-sunset.org/json?lat={lat}&lng={lon}&tzid={timezone}"
    )
    try:
        sunrise_sunset_response = http.request('GET', sunrise_sunset_url)
        sunrise_sunset_data: SunriseSunsetResponse = json.loads(sunrise_sunset_response.data.decode('utf-8'))

        # Check if the status is 'OK'
        if sunrise_sunset_data["status"] == "OK":
            return sunrise_sunset_data
        else:
            return None
    except urllib3.exceptions.RequestError:
        return None

