import json
import os
import boto3
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

        # Return the JSON payload
        return {
            "statusCode": 200,
            "body": body,
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
