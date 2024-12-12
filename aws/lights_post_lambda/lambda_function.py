import json
import boto3
import os
import logging
from typing import Dict, Any

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize S3 client
s3 = boto3.client("s3")

# Environment variables for the bucket and key (configure these in AWS Lambda settings)
CONFIG_BUCKET_NAME = os.environ.get("CONFIG_BUCKET_NAME", "Default_S3_Bucket")
CONFIG_KEY_NAME = os.environ.get("CONFIG_KEY_NAME", "Config_Key")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler to save a JSON payload from an API Gateway PUT request to S3.

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
        if http_method != "POST":
            return {
                "statusCode": 405,
                "body": json.dumps({"error": "Only PUT method is allowed."}),
            }

        # Parse the body
        body = json.loads(event.get("body", "{}"))

        # Validate JSON payload
        if not isinstance(body, dict):
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Payload must be a valid JSON object."}),
            }

        # Save the JSON payload to S3
        s3.put_object(
            Bucket=CONFIG_BUCKET_NAME,
            Key=CONFIG_KEY_NAME,
            Body=json.dumps(body),
            ContentType="application/json",
        )

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
