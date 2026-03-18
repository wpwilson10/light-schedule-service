from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import boto3
import logging
import urllib3
from astral import Observer
from astral.sun import sun
from typing import TYPE_CHECKING
from models import (
    ConfigValue,
    GeolocationResponse,
    LambdaEvent,
    LambdaResponse,
    LightConfig,
)

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
            response = s3.get_object(Bucket=CONFIG_BUCKET_NAME, Key=CONFIG_KEY_NAME)
            body = response["Body"].read().decode("utf-8")
            data = json.loads(body)
        except (s3.exceptions.NoSuchKey, json.JSONDecodeError) as e:
            logger.warning(f"No valid configuration found: {e}, creating empty config")

        # Create LightConfig instance from S3 data or empty if none exists
        config_data = LightConfig.from_dict(data)

        # Fetch geolocation once for both timezone and sun-time lookups
        ip = get_ip_from_event(event)
        geolocation_data = get_geolocation_data(ip) if ip else None

        # Get timezone offset with fallback chain: geolocation → cached → UTC
        timezone_offset = get_timezone_offset_with_cache(geolocation_data, data)

        # Update schedule times (timezone_offset defaults to 0/UTC if all lookups fail)
        config_data.update_sleep_times(timezone_offset)

        # Cache timezone offset if geolocation succeeded and value changed
        if (
            geolocation_data
            and data.get("cached_timezone_offset") != geolocation_data["offset"]
        ):
            cache_timezone_offset(geolocation_data["offset"])

        # Get and update daylight times if available
        daylight_times = get_daylight_times(geolocation_data)
        if daylight_times:
            sunrise, sunset, twilight_begin, twilight_end = daylight_times
            config_data.update_daylight_times(
                sunrise, sunset, twilight_begin, twilight_end, timezone_offset
            )

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


def get_timezone_offset_with_cache(
    geolocation_data: GeolocationResponse | None,
    cached_config: dict[str, ConfigValue],
) -> int:
    """
    Get timezone offset with fallback chain: geolocation → cached → UTC (0).

    Args:
        geolocation_data: Response from ip-api.com, or None if lookup failed.
        cached_config: Previously stored S3 config that may contain cached timezone.

    Returns:
        Timezone offset in seconds from UTC. Falls back to 0 (UTC) if all lookups fail.
    """
    # Try geolocation first
    if geolocation_data is not None:
        offset = geolocation_data["offset"]
        logger.info("Using timezone offset from IP geolocation: %d", offset)
        return offset

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


def get_daylight_times(
    geolocation_data: GeolocationResponse | None,
) -> tuple[str, str, str, str] | None:
    """
    Computes sunrise, sunset, and civil twilight times locally using astral.

    Args:
        geolocation_data: Response from ip-api.com with lat/lon/offset,
            or None if geolocation lookup failed.

    Returns:
        Tuple of (sunrise, sunset, civil_twilight_begin, civil_twilight_end)
        in HH:MM format, or None if geolocation is unavailable or sun times
        cannot be computed (e.g. polar latitudes).
    """
    if geolocation_data is None:
        return None

    lat = geolocation_data["lat"]
    lon = geolocation_data["lon"]
    offset_seconds = geolocation_data["offset"]

    tz = timezone(timedelta(seconds=offset_seconds))
    today = datetime.now(tz).date()
    observer = Observer(latitude=lat, longitude=lon)

    try:
        sun_times = sun(observer, date=today, tzinfo=tz)
    except ValueError:
        # Polar latitude — no sunrise/set today
        logger.warning(
            "Cannot compute sun times for lat=%s lon=%s on %s", lat, lon, today
        )
        return None

    return (
        sun_times["sunrise"].strftime("%H:%M"),
        sun_times["sunset"].strftime("%H:%M"),
        sun_times["dawn"].strftime("%H:%M"),
        sun_times["dusk"].strftime("%H:%M"),
    )


def get_ip_from_event(event: LambdaEvent) -> str | None:
    """Extracts the IP address from the event's request context."""
    return event.get("requestContext", {}).get("http", {}).get("sourceIp")


def get_geolocation_data(ip: str) -> GeolocationResponse | None:
    """Fetches geolocation details using ip-api based on the provided IP."""
    geolocation_url = f"http://ip-api.com/json/{ip}?fields=status,message,country,countryCode,regionName,city,zip,lat,lon,timezone,offset,query"
    try:
        geolocation_response = http.request("GET", geolocation_url)

        if geolocation_response.status != 200:
            logger.warning(
                "Geolocation API returned status %d for IP %s",
                geolocation_response.status,
                ip,
            )
            return None

        geolocation_data: GeolocationResponse = json.loads(
            geolocation_response.data.decode("utf-8")
        )

        # Check if the status is 'success'
        if geolocation_data["status"] == "success":
            return geolocation_data
        else:
            return None
    except (urllib3.exceptions.RequestError, json.JSONDecodeError, KeyError) as e:
        logger.warning("Geolocation lookup failed for IP %s: %s", ip, e)
        return None
