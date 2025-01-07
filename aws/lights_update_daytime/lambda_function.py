import json
import boto3
import os
import logging
import requests
from typing import Any, Optional

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize S3 client
s3 = boto3.client("s3")

# Environment variables for the bucket and key (configure these in AWS Lambda settings)
CONFIG_BUCKET_NAME = os.environ.get("CONFIG_BUCKET_NAME", "Default_S3_Bucket")
CONFIG_KEY_NAME = os.environ.get("CONFIG_KEY_NAME", "Config_Key")

def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    # Step 1: Extract IP from the event (request context)
    ip = get_ip_from_event(event)
    if not ip:
        return {
            "statusCode": 400,
            "body": json.dumps("IP address not found in request."),
        }

    # Step 2: Get geolocation details using ip-api
    geolocation_data = get_geolocation_data(ip)
    if not geolocation_data:
        return {
            "statusCode": 400,
            "body": json.dumps(f"Failed to get geolocation for IP: {ip}"),
        }

    # Step 3: Extract latitude, longitude, and timezone from geolocation data
    lat, lon, timezone = extract_geolocation_details(geolocation_data)
    if not lat or not lon or not timezone:
        return {
            "statusCode": 400,
            "body": json.dumps("Failed to extract necessary geolocation information."),
        }

    # Step 4: Fetch sunrise and sunset times using latitude, longitude, and timezone
    sunrise_sunset_data = get_sunrise_sunset_data(lat, lon, timezone)
    if not sunrise_sunset_data:
        return {
            "statusCode": 400,
            "body": json.dumps("Failed to get sunrise and sunset data."),
        }

    # Step 5: Format the response with sunrise and sunset times
    sunrise: str = sunrise_sunset_data["results"].get("sunrise")
    sunset: str = sunrise_sunset_data["results"].get("sunset")

    # Step 6: Get the JSON data from S3 bucket with the config key
    try:
        response = s3.get_object(Bucket=CONFIG_BUCKET_NAME, Key=CONFIG_KEY_NAME)
        config_data = json.loads(response['Body'].read().decode('utf-8'))
    except Exception as e:
        logger.error(f"Error fetching config data from S3: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps("Error fetching config data from S3")
        }

    # Step 7: Replace the sunrise and sunset fields in the config data
    config_data['sunrise'] = sunrise
    config_data['sunset'] = sunset

    # Step 8: Put the updated data back in the S3 bucket
    try:
        s3.put_object(Bucket=CONFIG_BUCKET_NAME, Key=CONFIG_KEY_NAME, Body=json.dumps(config_data))
    except Exception as e:
        logger.error(f"Error putting updated config data to S3: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps("Error putting updated config data to S3")
        }

    return {
        "statusCode": 200,
        "body": json.dumps("Lambda function executed successfully")
    }


def get_ip_from_event(event: dict[str, Any]):
    """Extracts the IP address from the event's request context."""
    return event.get("requestContext", {}).get("identity", {}).get("sourceIp")


def get_geolocation_data(ip: str):
    """Fetches geolocation details using ip-api based on the provided IP."""
    geolocation_url = f"http://ip-api.com/json/{ip}"
    try:
        geolocation_response = requests.get(geolocation_url)
        geolocation_data = geolocation_response.json()

        # Check if the status is 'success'
        if geolocation_data.get("status") == "success":
            return geolocation_data
        else:
            return None
    except requests.RequestException:
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
        sunrise_sunset_response = requests.get(sunrise_sunset_url)
        sunrise_sunset_data = sunrise_sunset_response.json()

        # Check if the status is 'OK'
        if sunrise_sunset_data.get("status") == "OK":
            return sunrise_sunset_data
        else:
            return None
    except requests.RequestException:
        return None

