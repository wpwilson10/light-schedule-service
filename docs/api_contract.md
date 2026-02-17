# Light Schedule API Contract

This document defines the unified API format for the light-schedule-service.

## Authentication

All requests require the `x-custom-auth` header:

```
x-custom-auth: <secret-token>
```

## Endpoints

### GET /lights

Retrieves the current lighting configuration.

### POST /lights

Saves a new lighting configuration.

## Unified Data Format

### Response Schema (GET)

```json
{
  "mode": "dayNight",
  "serverTime": 1706745600,
  "brightnessSchedule": [
    {"time": "06:30", "unixTime": 1706785800, "warmBrightness": 25, "coolBrightness": 0, "label": "civil_twilight_begin"},
    {"time": "07:00", "unixTime": 1706787600, "warmBrightness": 75, "coolBrightness": 100, "label": "sunrise"},
    {"time": "19:30", "unixTime": 1706832600, "warmBrightness": 75, "coolBrightness": 100, "label": "sunset"},
    {"time": "20:00", "unixTime": 1706834400, "warmBrightness": 100, "coolBrightness": 0, "label": "civil_twilight_end"},
    {"time": "23:00", "unixTime": 1706845200, "warmBrightness": 100, "coolBrightness": 0, "label": "bed_time"},
    {"time": "23:30", "unixTime": 1706847000, "warmBrightness": 25, "coolBrightness": 0, "label": "night_time"}
  ]
}
```

### Field Definitions

#### Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `mode` | string | Yes | Operating mode: `"dayNight"`, `"scheduled"`, or `"demo"` |
| `serverTime` | integer | Yes | Current server Unix timestamp (seconds since epoch) |
| `brightnessSchedule` | array | Yes | Unified array of all schedule entries, sorted chronologically by `unixTime` |

#### BrightnessScheduleEntry

Each entry in `brightnessSchedule`:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `time` | string | Yes | Time in HH:mm format (24-hour) |
| `unixTime` | integer | Yes | Unix timestamp for this entry |
| `warmBrightness` | integer | Yes | Warm LED brightness (0-100) |
| `coolBrightness` | integer | Yes | Cool LED brightness (0-100) |
| `label` | string | Yes | Entry identifier (see Standard Labels) |

#### Standard Labels

| Label | Description |
|-------|-------------|
| `civil_twilight_begin` | Dawn - start of civil twilight |
| `sunrise` | Sunrise time |
| `sunset` | Sunset time (may be adjusted to minimum 19:30) |
| `civil_twilight_end` | Dusk - end of civil twilight |
| `bed_time` | Bedtime transition (default: 23:00) |
| `night_time` | Night mode (default: 23:30) |

### Request Schema (POST)

POST requests use the same unified format. The server computes `unixTime` values from `time` strings based on client timezone (from IP geolocation).

```json
{
  "mode": "dayNight",
  "brightnessSchedule": [
    {"time": "06:30", "warmBrightness": 25, "coolBrightness": 0, "label": "civil_twilight_begin"},
    {"time": "07:00", "warmBrightness": 75, "coolBrightness": 100, "label": "sunrise"},
    {"time": "19:30", "warmBrightness": 75, "coolBrightness": 100, "label": "sunset"},
    {"time": "20:00", "warmBrightness": 100, "coolBrightness": 0, "label": "civil_twilight_end"},
    {"time": "23:00", "warmBrightness": 100, "coolBrightness": 0, "label": "bed_time"},
    {"time": "23:30", "warmBrightness": 25, "coolBrightness": 0, "label": "night_time"}
  ]
}
```

Note: `serverTime` and `unixTime` fields are ignored on POST. POST saves the payload to S3 as-is. `unixTime` values are recomputed on the next GET request based on current date and client timezone (from IP geolocation).

## Clock Synchronization

The `serverTime` field enables clock drift detection on embedded clients:

1. Client compares `serverTime` to local RTC
2. If drift exceeds 5 minutes, log a warning
3. Use `unixTime` values from `brightnessSchedule` directly for scheduling (no client-side timestamp computation needed)

## Mode Behavior

### dayNight Mode

- Sunrise/sunset times fetched from geolocation API based on client IP
- Minimum sunset time enforced at 19:30 (to prevent early darkness in winter)
- If sunset is adjusted, `civil_twilight_end` is set to 30 minutes after sunset

### scheduled Mode

- Uses user-defined entries from `brightnessSchedule`
- Times are not computed from geolocation
- Deferred — no frontend UI. The API accepts scheduled mode but there is no web interface for creating custom schedules.

### demo Mode

- Fast-cycling demonstration schedule for testing

## Data Flow

### GET Pipeline

```
S3 config → from_dict() → LightConfig (extracts entries by label from brightnessSchedule)
  → geolocation (IP → lat/lon) → sunrise/sunset API → update_daylight_times()
    (preserves user brightness values, updates times from astronomy data)
  → update_sleep_times() (preserves user bed_time/night_time, recomputes unixTime)
  → build_brightness_schedule() → sorted array → JSON response
```

### POST Pipeline

```
Frontend sends {mode, brightnessSchedule} → validate entries → save to S3 as-is
```

POST also preserves `cached_timezone_offset` from the existing S3 config.
