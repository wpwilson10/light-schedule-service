import json
import os
import boto3
import logging
import urllib3

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
    AWS Lambda handler to retrieve a JSON payload from S3 for an API Gateway GET request.

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
        sunrise, sunset = get_sunrise_sunset(event)
        if sunrise and sunset:
            config_data['sunrise'] = sunrise
            config_data['sunset'] = sunset

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
    
def get_sunrise_sunset(event: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    # Step 1: Extract IP from the event (request context)
    ip = get_ip_from_event(event)
    if not ip:
        logger.error("IP address not found in request.")
        return None, None

    # Step 2: Get geolocation details using ip-api
    geolocation_data = get_geolocation_data(ip)
    if not geolocation_data:
        logger.error(f"Failed to get geolocation for IP: {ip}")
        return None, None

    # Step 3: Extract latitude, longitude, and timezone from geolocation data
    lat, lon, timezone = extract_geolocation_details(geolocation_data)
    if not lat or not lon or not timezone:
        logger.error("Failed to extract necessary geolocation information.")
        return None, None

    # Step 4: Fetch sunrise and sunset times using latitude, longitude, and timezone
    sunrise_sunset_data = get_sunrise_sunset_data(lat, lon, timezone)
    if not sunrise_sunset_data:
        logger.error("Failed to get sunrise and sunset data.")
        return None, None

    # Step 5: Format the response with sunrise and sunset times
    sunrise: str = sunrise_sunset_data["results"].get("sunrise")
    sunset: str = sunrise_sunset_data["results"].get("sunset")
    
    return sunrise, sunset

def get_ip_from_event(event: dict[str, Any]):
    """Extracts the IP address from the event's request context."""
    return event.get("requestContext", {}).get("identity", {}).get("sourceIp")


def get_geolocation_data(ip: str):
    """Fetches geolocation details using ip-api based on the provided IP."""
    geolocation_url = f"http://ip-api.com/json/{ip}"
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

