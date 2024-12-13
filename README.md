# light-schedule-service

Serverless REST API integrating functionalities from WpwilsonSite and Sunrise_Lamp.

## Description

This project provides a service that allows for saving and retrieving a configuration file for controlling the lighting control system implemented in [Sunrise_Lamp](https://github.com/wpwilson10/Sunrise_Lamp) using the core AWS infrastucture implemented in [WpwilsonSite](https://github.com/wpwilson10/WpwilsonSite). This service provides the integration between those projects using AWS Lambda functions to store and retrieve configuration files in Amazon S3, making it easy to manage and update lighting configurations remotely.

The architecture for this project follows [AWS's RESTful microservices scenario](https://docs.aws.amazon.com/wellarchitected/latest/serverless-applications-lens/restful-microservices.html) which is a serverless application framework and part of AWS's recommended Well-Architected Framework. By using an API Gateway which calls Lambda functions backed by an S3 bucket, this solution is scalable, distributed, and fault-tolerant by default.

![Architecture](./diagram.png)

## Setup

### Configuration

Create a terraform.tfvars file under ./terraform and configure as desired.

Required variables:

-   api_gateway - the ID of the API Gateway with which this service integrates

See variables.tf for more information.

### Deploy

Once the configuration above is complete, run the following commands from the ./terraform directory.

```
terraform init
terraform plan
terraform apply
```

## Usage

### Save Configuration

To save a configuration file, send a POST request to the endpoint exposed by the API Gateway with the configuration JSON as the body.

The format of the JSON payload should have a body which matches the following interfaces.

```
interface ScheduleData {
  mode: "dayNight" | "scheduled" | "demo"; // the mode of operation
  schedule: ScheduleEntry[];               // a list of ScheduleEntry defining brightness levels for a given time of day.
}

interface ScheduleEntry {
  id: number;                              // a unique identifier for the schedule entry
  time: string;                            // the time at which the lighting change should occur, formatted as HH:MM (e.g., "23:45").
  warmBrightness: number;                  // the brightness level for the warm light (0-100).
  coolBrightness: number;                  // the brightness level for the cool light (0-100).
}
```

For example:

```
POST https://api.example.com/lights

{
  "mode": "scheduled",
  "schedule": [
    {
      "id": 1,
      "time": "01:23",
      "warmBrightness": 75,
      "coolBrightness": 60
    },
    {
      "id": 2,
      "time": "23:45",
      "warmBrightness": 60,
      "coolBrightness": 70
    }
  ]
}
```

### Retrieve Configuration

To retrieve the current configuration, send a GET request to the Lambda endpoint. No body is required. This will return a configuration JSON object like described above.

For example:

```
GET https://api.example.com/lights
```
