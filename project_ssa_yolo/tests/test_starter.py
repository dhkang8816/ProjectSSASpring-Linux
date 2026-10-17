import unittest
from unittest.mock import patch

from apps.services import starter


class StarterTest(unittest.TestCase):
    def test_startup_melody_is_scheduled_once_after_services_are_ready(self):
        original_played = starter._startup_sound_played
        try:
            starter._startup_sound_played = False
            with patch.object(starter, "start_buzzer_service"), \
                    patch.object(starter, "start_sensor_service"), \
                    patch.object(starter, "start_notification_service"), \
                    patch.object(starter.runtime_settings, "BUZZER_STARTUP_SOUND_ENABLED", True), \
                    patch.object(starter, "play_startup_melody") as startup_melody:
                starter.start_services()
                starter.start_services()

            startup_melody.assert_called_once_with()
        finally:
            starter._startup_sound_played = original_played

    def test_start_services_marks_optional_worker_initialization_ready(self):
        with patch.object(starter, "start_buzzer_service"), \
                patch.object(starter, "start_sensor_service"), \
                patch.object(starter, "start_notification_service"), \
                patch.object(starter.runtime_settings, "BUZZER_STARTUP_SOUND_ENABLED", False):
            starter.start_services()

        status = starter.get_startup_status()
        self.assertEqual("READY", status["stage"])
        self.assertEqual(100, status["progress"])
        self.assertTrue(status["ready"])

    def test_shutdown_tone_runs_after_sensor_stop_and_before_buzzer_stop(self):
        calls = []
        with patch.object(starter, "stop_notification_service", side_effect=lambda: calls.append("notification")), \
                patch.object(starter, "stop_sensor_service", side_effect=lambda: calls.append("sensor")), \
                patch.object(starter, "play_shutdown_melody", side_effect=lambda timeout: calls.append(("shutdown", timeout))), \
                patch.object(starter, "is_buzzer_service_running", return_value=True), \
                patch.object(starter, "stop_buzzer_service", side_effect=lambda: calls.append("buzzer")), \
                patch.object(starter.runtime_settings, "BUZZER_SHUTDOWN_SOUND_ENABLED", True), \
                patch.object(starter.runtime_settings, "BUZZER_SHUTDOWN_SOUND_WAIT_SECONDS", 3.0):
            starter.stop_services()

        self.assertEqual(["notification", "sensor", ("shutdown", 3.0), "buzzer"], calls)

    def test_optional_io_disabled_does_not_start_discord_or_devices(self):
        with patch.object(starter.runtime_settings, "OPTIONAL_IO_ENABLED", False), \
                patch.object(starter, "start_notification_service") as discord, \
                patch.object(starter, "start_sensor_service") as sensor, \
                patch.object(starter, "start_buzzer_service") as buzzer:
            starter.start_services()
        discord.assert_not_called()
        sensor.assert_not_called()
        buzzer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
