from unittest.mock import patch
from models import ConfigValue, LightConfig


# --- Helpers ---

def make_brightness_schedule(overrides: dict[str, dict[str, int]] | None = None) -> list[dict[str, str | int]]:
    """Build a standard 6-entry brightnessSchedule array with optional overrides."""
    defaults: list[dict[str, str | int]] = [
        {"time": "06:30", "unixTime": 1000, "warmBrightness": 20, "coolBrightness": 0, "label": "civil_twilight_begin"},
        {"time": "07:00", "unixTime": 2000, "warmBrightness": 75, "coolBrightness": 100, "label": "sunrise"},
        {"time": "19:30", "unixTime": 3000, "warmBrightness": 75, "coolBrightness": 100, "label": "sunset"},
        {"time": "20:00", "unixTime": 4000, "warmBrightness": 100, "coolBrightness": 0, "label": "civil_twilight_end"},
        {"time": "23:00", "unixTime": 5000, "warmBrightness": 100, "coolBrightness": 0, "label": "bed_time"},
        {"time": "23:30", "unixTime": 6000, "warmBrightness": 25, "coolBrightness": 0, "label": "night_time"},
    ]
    if overrides:
        for entry in defaults:
            label = entry["label"]
            if isinstance(label, str) and label in overrides:
                entry.update(overrides[label])
    return defaults


# --- Round-trip tests ---

class TestFromDictBrightnessSchedule:
    def test_reads_all_six_entries(self):
        data: dict[str, ConfigValue] = {"mode": "dayNight", "brightnessSchedule": make_brightness_schedule()}
        config = LightConfig.from_dict(data)

        assert config.civil_twilight_begin is not None
        assert config.sunrise is not None
        assert config.sunset is not None
        assert config.civil_twilight_end is not None
        assert config.bed_time is not None
        assert config.night_time is not None

        assert config.sunrise["warmBrightness"] == 75
        assert config.sunrise["coolBrightness"] == 100
        assert config.bed_time["warmBrightness"] == 100
        assert config.night_time["warmBrightness"] == 25

    def test_passes_unixTime_through(self):
        data: dict[str, ConfigValue] = {"mode": "dayNight", "brightnessSchedule": make_brightness_schedule()}
        config = LightConfig.from_dict(data)

        assert config.sunrise is not None
        assert config.sunset is not None
        assert config.night_time is not None
        assert config.sunrise["unixTime"] == 2000
        assert config.sunset["unixTime"] == 3000
        assert config.night_time["unixTime"] == 6000

    def test_ignores_unknown_labels(self):
        schedule = make_brightness_schedule() + [
            {"time": "12:00", "unixTime": 9999, "warmBrightness": 50, "coolBrightness": 50, "label": "custom_label"}
        ]
        data: dict[str, ConfigValue] = {"mode": "dayNight", "brightnessSchedule": schedule}
        config = LightConfig.from_dict(data)

        # Should not crash; standard labels still work
        assert config.sunrise is not None
        assert not hasattr(config, "custom_label") or getattr(config, "custom_label", None) is None

    def test_partial_schedule(self):
        schedule: list[dict[str, str | int]] = [
            {"time": "07:00", "unixTime": 2000, "warmBrightness": 75, "coolBrightness": 100, "label": "sunrise"},
            {"time": "19:30", "unixTime": 3000, "warmBrightness": 60, "coolBrightness": 80, "label": "sunset"},
        ]
        data: dict[str, ConfigValue] = {"mode": "dayNight", "brightnessSchedule": schedule}
        config = LightConfig.from_dict(data)

        assert config.sunrise is not None
        assert config.sunset is not None
        assert config.civil_twilight_begin is None
        assert config.civil_twilight_end is None
        assert config.bed_time is None
        assert config.night_time is None

    def test_empty_dict(self):
        config = LightConfig.from_dict({})
        empty = LightConfig.create_empty()

        assert config.mode == empty.mode
        assert config.sunrise is None
        assert config.sunset is None

    def test_none_input(self):
        config = LightConfig.from_dict(None)
        assert config.mode == LightConfig.DEFAULT_MODE
        assert config.sunrise is None


# --- Brightness preservation tests ---

class TestBrightnessPreservation:
    def test_update_daylight_times_preserves_brightness(self):
        data: dict[str, ConfigValue] = {"mode": "dayNight", "brightnessSchedule": make_brightness_schedule(
            overrides={"sunrise": {"warmBrightness": 50, "coolBrightness": 80}}
        )}
        config = LightConfig.from_dict(data)

        config.update_daylight_times(
            sunrise="06:45", sunset="19:00", twilight_begin="06:15",
            twilight_end="19:45", timezone_offset=0
        )

        assert config.sunrise is not None
        assert config.sunrise["warmBrightness"] == 50
        assert config.sunrise["coolBrightness"] == 80

    def test_update_sleep_times_preserves_brightness(self):
        data: dict[str, ConfigValue] = {"mode": "dayNight", "brightnessSchedule": make_brightness_schedule(
            overrides={"bed_time": {"warmBrightness": 80, "coolBrightness": 10}}
        )}
        config = LightConfig.from_dict(data)

        config.update_sleep_times(timezone_offset=0)

        assert config.bed_time is not None
        assert config.bed_time["warmBrightness"] == 80
        assert config.bed_time["coolBrightness"] == 10


# --- Full round-trip test ---

class TestFullRoundTrip:
    def test_brightness_survives_full_pipeline(self):
        """Simulate: from_dict → update_daylight_times → update_sleep_times → build_brightness_schedule"""
        custom_brightness = {
            "civil_twilight_begin": {"warmBrightness": 10, "coolBrightness": 5},
            "sunrise": {"warmBrightness": 50, "coolBrightness": 80},
            "sunset": {"warmBrightness": 60, "coolBrightness": 90},
            "civil_twilight_end": {"warmBrightness": 70, "coolBrightness": 15},
            "bed_time": {"warmBrightness": 80, "coolBrightness": 10},
            "night_time": {"warmBrightness": 15, "coolBrightness": 0},
        }
        data: dict[str, ConfigValue] = {"mode": "dayNight", "brightnessSchedule": make_brightness_schedule(overrides=custom_brightness)}
        config = LightConfig.from_dict(data)

        config.update_daylight_times(
            sunrise="06:45", sunset="19:00", twilight_begin="06:15",
            twilight_end="19:45", timezone_offset=0
        )
        config.update_sleep_times(timezone_offset=0)

        output = config.build_brightness_schedule()
        output_by_label = {e["label"]: e for e in output}

        for label, expected in custom_brightness.items():
            assert output_by_label[label]["warmBrightness"] == expected["warmBrightness"], f"{label} warmBrightness mismatch"
            assert output_by_label[label]["coolBrightness"] == expected["coolBrightness"], f"{label} coolBrightness mismatch"


# --- Output format tests ---

class TestBuildBrightnessSchedule:
    def _build_config_with_all_fields(self) -> LightConfig:
        data: dict[str, ConfigValue] = {"mode": "dayNight", "brightnessSchedule": make_brightness_schedule()}
        config = LightConfig.from_dict(data)
        config.update_sleep_times(timezone_offset=0)
        return config

    def test_field_names(self):
        config = self._build_config_with_all_fields()
        entries = config.build_brightness_schedule()

        for entry in entries:
            assert "time" in entry
            assert "unixTime" in entry
            assert "warmBrightness" in entry
            assert "coolBrightness" in entry
            assert "label" in entry
            # Verify no snake_case fields
            assert "unix_time" not in entry
            assert "warm_brightness" not in entry
            assert "cool_brightness" not in entry

    def test_no_conversion_unixTime_passthrough(self):
        data: dict[str, ConfigValue] = {"mode": "dayNight", "brightnessSchedule": make_brightness_schedule()}
        config = LightConfig.from_dict(data)
        entries = config.build_brightness_schedule()
        entry_by_label = {e["label"]: e for e in entries}

        assert entry_by_label["sunrise"]["unixTime"] == 2000
        assert entry_by_label["sunset"]["unixTime"] == 3000

    def test_sorted_by_time(self):
        config = self._build_config_with_all_fields()
        entries = config.build_brightness_schedule()
        unix_times = [e["unixTime"] for e in entries]

        assert unix_times == sorted(unix_times)

    def test_to_dict_shape(self):
        config = self._build_config_with_all_fields()
        with patch.object(config, 'get_server_time', return_value=12345):
            result = config.to_dict()

        assert set(result.keys()) == {"mode", "serverTime", "brightnessSchedule"}
        assert result["mode"] == "dayNight"
        assert result["serverTime"] == 12345
        assert isinstance(result["brightnessSchedule"], list)
