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

- api_gateway - the ID of the API Gateway with which this service integrates

See variables.tf for more information.

### Deploy

Once the configuration above is complete, run the following commands from the ./terraform directory.

```
terraform init
terraform plan
terraform apply
```

## Usage

### Required Headers

All requests must include the following authentication header:

```
x-custom-auth: your-secret-token
```

### Save Configuration

To save a configuration file, send a POST request to the endpoint exposed by the API Gateway with the configuration JSON as the body.

The format of the JSON payload should match the following interfaces:

```typescript
interface ScheduleEntry {
  time: string; // Time in 24-hour format (HH:MM)
  warmBrightness: number; // Warm light brightness (0-100)
  coolBrightness: number; // Cool light brightness (0-100)
  unix_time: number; // Unix timestamp for this entry
}

interface ScheduleData {
  mode: 'dayNight' | 'scheduled' | 'demo'; // Operating mode
  schedule: ScheduleEntry[]; // User-defined schedule entries
  sunrise: ScheduleEntry; // Sunrise settings
  sunset: ScheduleEntry; // Sunset settings
  natural_sunset: ScheduleEntry; // Natural sunset settings
  civil_twilight_begin: ScheduleEntry; // Civil twilight begin settings
  civil_twilight_end: ScheduleEntry; // Civil twilight end settings
  natural_twilight_end: ScheduleEntry; // Natural twilight end settings
  bed_time: ScheduleEntry; // Bedtime settings
  night_time: ScheduleEntry; // Night time settings
  update_time: string; // Scheduled update time (HH:MM)
  update_time_unix: number; // Next update Unix timestamp
}
```

Example request:

```
POST https://api.example.com/lights
x-custom-auth: your-secret-token

{
  "mode": "dayNight",
  "schedule": [],
  "sunrise": {
    "time": "06:30",
    "warmBrightness": 75,
    "coolBrightness": 100,
    "unix_time": 1677133800
  },
  "sunset": {
    "time": "19:30",
    "warmBrightness": 75,
    "coolBrightness": 100,
    "unix_time": 1677180600
  },
  // ... other schedule entries ...
  "update_time": "06:00",
  "update_time_unix": 1677132000
}
```

### Retrieve Configuration

To retrieve the current configuration:

```
GET https://api.example.com/lights
x-custom-auth: your-secret-token
```

The response will contain a complete ScheduleData object as described above.

## Features

The service handles time updates automatically in several ways:

### Schedule Time Updates

- Fixed schedule entries maintain their HH:MM times but get updated unix timestamps daily
- Unix timestamps are calculated based on the user's timezone (derived from IP address)
- The schedule list is executed based on unix timestamps for the current day

#### DayNight Mode

When operating in "dayNight" mode:

- Sunrise/sunset times are fetched based on the user's geolocation (from IP address)
- Daytime events (sunrise, sunset, dusk, dawn) are updated with actual times for the current location
- Each light event gets a unix timestamp for the current day
- A minimum sunset time of 19:30 is enforced to prevent early darkness in winter
- If sunset is before 19:30, dusk is set to 30 minutes after sunset
- Default sleep schedule (bed_time: 23:00, night_time: 23:30) is applied if not set

#### Update Schedule

- The service automatically updates times daily at 06:00 (configurable)
- The update_time_unix field indicates when the next update will occur
- All unix timestamps are recalculated during the daily update
