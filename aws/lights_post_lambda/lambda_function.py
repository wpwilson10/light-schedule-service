import json
import boto3
import os
import logging
from typing import Any, NotRequired, TypedDict
from mypy_boto3_s3 import S3Client

# Types duplicated from lights_get_lambda/models.py (separate Lambda packages)
ConfigValue = str | int | list[dict[str, str | int]]
LambdaEvent = dict[str, Any]  # AWS SDK does not ship typed events

class LambdaResponse(TypedDict):
    """AWS Lambda response for API Gateway."""
    statusCode: int
    body: str
    headers: NotRequired[dict[str, str]]

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize S3 client
s3: S3Client = boto3.client("s3")  # pyright: ignore[reportUnknownMemberType]

# Environment variables for the bucket and key (configure these in AWS Lambda settings)
CONFIG_BUCKET_NAME = os.environ.get("CONFIG_BUCKET_NAME", "Default_S3_Bucket")
CONFIG_KEY_NAME = os.environ.get("CONFIG_KEY_NAME", "Config_Key")
SECRET_TOKEN = os.environ.get("SECRET_TOKEN", "default-secret-token")

# Valid modes for the light schedule
VALID_MODES = {"dayNight", "scheduled", "demo"}

# Required fields for each brightness schedule entry
REQUIRED_ENTRY_FIELDS = {"time", "warmBrightness", "coolBrightness", "label"}


def lambda_handler(event: LambdaEvent, context: object) -> LambdaResponse:
    """
    AWS Lambda handler to save a JSON payload from an API Gateway POST request to S3.

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
        if http_method != "POST":
            return {
                "statusCode": 405,
                "body": json.dumps({"error": "Only POST method is allowed."}),
            }
        
        # Check the custom header for the pre-shared token
        headers = event.get("headers", {})
        # Lowercase is important for HTTP 2 protocol
        token = headers.get("x-custom-auth")

        # Validate the token
        if token != SECRET_TOKEN:
            logger.info(msg="Denied unauthorized request")
            return {"statusCode": 403, "body": "Unauthorized"}

        # Parse the body — json.loads returns Any; annotation provides the typed boundary
        body: dict[str, ConfigValue] = json.loads(event.get("body", "{}"))

        # Validate unified format
        validation_error = validate_unified_format(body)
        if validation_error:
            logger.warning(f"Validation failed: {validation_error}")
            return {
                "statusCode": 400,
                "body": json.dumps({"error": validation_error}),
            }

        # Preserve cached_timezone_offset from existing config if present
        try:
            existing_response = s3.get_object(Bucket=CONFIG_BUCKET_NAME, Key=CONFIG_KEY_NAME)
            existing_config: dict[str, ConfigValue] = json.loads(existing_response["Body"].read().decode("utf-8"))
            if "cached_timezone_offset" in existing_config:
                body["cached_timezone_offset"] = existing_config["cached_timezone_offset"]
        except Exception:
            pass  # No existing config or read error, proceed without cached timezone

        # Save the JSON payload to S3
        s3.put_object(
            Bucket=CONFIG_BUCKET_NAME,
            Key=CONFIG_KEY_NAME,
            Body=json.dumps(body),
            ContentType="application/json",
        )

        # Log successful save (validation guarantees brightnessSchedule is a list)
        schedule = body.get("brightnessSchedule")
        schedule_count = len(schedule) if isinstance(schedule, list) else 0
        logger.info(f"Schedule saved successfully: mode={body.get('mode')}, entries={schedule_count}")

        # Return a success response
        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Payload saved to S3 successfully."}),
        }

    except Exception as e:
        logger.error("Error processing request: %s", e, exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal server error."}),
        }


def validate_unified_format(body: dict[str, ConfigValue]) -> str | None:
    """
    Validates the unified brightnessSchedule format.

    Args:
        body: The request body to validate

    Returns:
        Error message string if validation fails, None if valid
    """
    # Validate mode field
    mode = body.get("mode")
    if mode is None:
        return "Missing required field: mode"
    if mode not in VALID_MODES:
        return f"Invalid mode: {mode}. Must be one of: {', '.join(VALID_MODES)}"

    # Validate brightnessSchedule array
    schedule = body.get("brightnessSchedule")
    if schedule is None:
        return "Missing required field: brightnessSchedule"
    if not isinstance(schedule, list):
        return "brightnessSchedule must be an array"

    # Validate each entry in the schedule
    # (entries are dict[str, str | int] per ConfigValue — no isinstance(dict) check needed)
    for i, entry in enumerate(schedule):
        # Check required fields
        missing_fields = REQUIRED_ENTRY_FIELDS - set(entry.keys())
        if missing_fields:
            return f"brightnessSchedule[{i}] missing required fields: {', '.join(missing_fields)}"

        # Validate time format (HH:mm)
        time_val = entry.get("time")
        if not isinstance(time_val, str) or not validate_time_format(time_val):
            return f"brightnessSchedule[{i}].time must be in HH:mm format"

        # Validate brightness values (0-100)
        for field in ["warmBrightness", "coolBrightness"]:
            val = entry.get(field)
            if not isinstance(val, int) or val < 0 or val > 100:
                return f"brightnessSchedule[{i}].{field} must be an integer between 0 and 100"

        # Validate label is a non-empty string
        label = entry.get("label")
        if not isinstance(label, str) or not label:
            return f"brightnessSchedule[{i}].label must be a non-empty string"

    return None


def validate_time_format(time_str: str) -> bool:
    """
    Validates that a string is in HH:mm format.

    Args:
        time_str: The time string to validate

    Returns:
        True if valid HH:mm format, False otherwise
    """
    if len(time_str) != 5 or time_str[2] != ':':
        return False
    try:
        hours, minutes = time_str.split(':')
        h = int(hours)
        m = int(minutes)
        return 0 <= h <= 23 and 0 <= m <= 59
    except ValueError:
        return False
