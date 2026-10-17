import threading
import time
import unittest
from unittest.mock import Mock, patch

from apps import runtime_settings
from apps.services import buzzer_helper, sensor_helper


class BuzzerHelperTest(unittest.TestCase):
    def setUp(self):
        buzzer_helper.set_buzzer_enabled(True)
        buzzer_helper.set_collision_level("SAFE")

    def tearDown(self):
        buzzer_helper.set_buzzer_enabled(True)
        buzzer_helper.set_collision_level("SAFE")

    def test_disabled_sound_does_not_start_a_worker_or_enqueue(self):
        buzzer_helper.set_buzzer_enabled(False)
        with patch.object(buzzer_helper, "start_buzzer_service") as start_worker:
            accepted = buzzer_helper._enqueue("animal")

        self.assertFalse(accepted)
        start_worker.assert_not_called()

    def test_collision_sound_is_enqueued_only_when_level_changes(self):
        with patch.object(buzzer_helper, "_enqueue") as enqueue:
            buzzer_helper.set_collision_level("DANGER")
            buzzer_helper.set_collision_level("DANGER")

        enqueue.assert_called_once_with("collision:DANGER")

    def test_mpremote_uses_current_python_module_not_shell_path_lookup(self):
        completed = Mock()
        with patch.object(buzzer_helper.subprocess, "run", return_value=completed) as run:
            returned = buzzer_helper.run_mpremote(("version",), timeout=3, capture_output=True)

        self.assertIs(completed, returned)
        command = run.call_args.args[0]
        self.assertEqual([*buzzer_helper._MPREMOTE_PREFIX, "version"], command)
        self.assertFalse(run.call_args.kwargs["shell"])

    def test_buzzer_command_uses_the_shared_runtime_com_port(self):
        with patch.object(runtime_settings, "ESP32_COM_PORT", "COM77"), \
                patch.object(buzzer_helper, "run_mpremote") as run_mpremote:
            buzzer_helper._run_mpremote_command("animal")

        self.assertEqual("COM77", run_mpremote.call_args.args[0][1])

    def test_startup_melody_uses_the_existing_queue_path(self):
        with patch.object(buzzer_helper, "_enqueue", return_value=True) as enqueue:
            queued = buzzer_helper.play_startup_melody()

        self.assertTrue(queued)
        enqueue.assert_called_once_with("startup")

    def test_startup_command_resynchronizes_the_board_before_resume_alerts(self):
        command = buzzer_helper._COMMANDS["startup"]

        self.assertNotIn("resume", command)
        self.assertEqual("exec", command[0])
        self.assertIn("main.play_startup_melody()", command[-1])

    def test_shutdown_melody_waits_for_its_queued_command(self):
        def enqueue(alert_type, completed):
            self.assertEqual("shutdown", alert_type)
            completed.set()
            return True

        with patch.object(buzzer_helper, "_enqueue", side_effect=enqueue):
            self.assertTrue(buzzer_helper.play_shutdown_melody(0.01))

    def test_shutdown_command_uses_the_existing_resumed_board_session(self):
        command = buzzer_helper._COMMANDS["shutdown"]

        self.assertEqual("resume", command[0])
        self.assertIn("main.play_shutdown_melody()", command[-1])

    def test_sensor_and_buzzer_mpremote_calls_are_serialized_by_one_lock(self):
        active_calls = 0
        maximum_parallel_calls = 0
        guard = threading.Lock()
        completed = Mock(stdout="{}")

        def fake_subprocess_run(*args, **kwargs):
            nonlocal active_calls, maximum_parallel_calls
            with guard:
                active_calls += 1
                maximum_parallel_calls = max(maximum_parallel_calls, active_calls)
            time.sleep(0.03)
            with guard:
                active_calls -= 1
            return completed

        # This test exercises queue serialization, independently of local USB devices.
        with patch.object(runtime_settings, "validate_serial_port", side_effect=lambda value: value), \
                patch.object(buzzer_helper.subprocess, "run", side_effect=fake_subprocess_run):
            sensor_thread = threading.Thread(target=sensor_helper._read_from_esp32)
            buzzer_thread = threading.Thread(
                target=buzzer_helper._run_mpremote_command,
                args=("startup",),
            )
            sensor_thread.start()
            buzzer_thread.start()
            sensor_thread.join()
            buzzer_thread.join()

        self.assertEqual(1, maximum_parallel_calls)


if __name__ == "__main__":
    unittest.main()
