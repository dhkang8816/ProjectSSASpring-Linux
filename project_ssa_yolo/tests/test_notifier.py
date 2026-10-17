import os
import io
import threading
from contextlib import redirect_stdout
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

from apps.services import notifier


class DiscordNotifierTest(unittest.TestCase):
    def test_missing_webhook_skips_network_call(self):
        with patch.object(notifier, "_webhook_url", return_value=""), \
                patch.object(notifier.requests, "post") as post:
            sent = notifier.send_discord_webhook("event")

        self.assertFalse(sent)
        post.assert_not_called()

    def test_existing_snapshot_is_sent_as_multipart_attachment(self):
        response = Mock()
        response.raise_for_status.return_value = None
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as image:
            image.write(b"test-image")
            image_path = image.name
        try:
            with patch.object(notifier, "_webhook_url", return_value="https://example.invalid/webhook"), \
                    patch.object(notifier.requests, "post", return_value=response) as post:
                sent = notifier.send_discord_webhook("event", image_path=image_path)

            self.assertTrue(sent)
            self.assertIn("files", post.call_args.kwargs)
            self.assertIn("payload_json", post.call_args.kwargs["data"])
        finally:
            os.unlink(image_path)

    def test_network_error_returns_false_without_raising_to_yolo(self):
        with patch.object(notifier, "_webhook_url", return_value="https://example.invalid/webhook"), \
                patch.object(notifier.requests, "post", side_effect=requests.RequestException("offline")):
            sent = notifier.send_discord_webhook("event")

        self.assertFalse(sent)

    def test_http_failure_never_logs_the_secret_webhook_url(self):
        secret_url = "https://example.invalid/private-test-secret"
        response = Mock(status_code=403)
        error = requests.HTTPError("forbidden " + secret_url, response=response)
        output = io.StringIO()
        with patch.object(notifier, "_webhook_url", return_value=secret_url), \
                patch.object(notifier.requests, "post", side_effect=error), redirect_stdout(output):
            self.assertFalse(notifier.send_discord_webhook("event"))
        self.assertNotIn(secret_url, output.getvalue())
        self.assertIn("HTTP 403", output.getvalue())

    def test_danger_event_reaches_mocked_callback_and_discord_even_when_spring_fails(self):
        from apps.services import oracle_service, yolo_detector
        completed = threading.Event()
        callback = Mock(status_code=500)
        delivery = Mock()
        delivery.raise_for_status.return_value = None
        posts = []
        def post(url, **kwargs):
            posts.append((url, kwargs))
            if url == "https://example.invalid/webhook":
                completed.set()
                return delivery
            return callback
        before = notifier.get_notification_status()["sentCount"]
        try:
            with patch.object(notifier, "_webhook_url", return_value="https://example.invalid/webhook"), \
                    patch.object(oracle_service, "get_active_drone_id", return_value="DRONE02"), \
                    patch.object(notifier.requests, "post", side_effect=post), \
                    patch.object(yolo_detector, "refresh_animal_targets_if_due"), \
                    patch.object(yolo_detector, "trigger_danger_sound"), \
                    patch.object(yolo_detector, "last_alarm_time", {}):
                notifier.start_notification_service()
                yolo_detector.process_detection_events(["blue_alien"], None, "video_2")
                self.assertTrue(completed.wait(3), "event did not reach the notification worker")
                oracle_service._report_queue.join()
                notifier._notification_queue.join()
                self.assertEqual(before + 1, notifier.get_notification_status()["sentCount"])
                self.assertEqual(2, len(posts))
                self.assertTrue(posts[0][0].endswith("/yolo/api/report"))
                self.assertNotIn("//yolo", posts[0][0])
                self.assertIn("DRONE02", posts[1][1]["json"]["content"])
        finally:
            notifier.stop_notification_service()

    def test_snapshot_failure_remains_an_error_but_does_not_discard_text_alert(self):
        from apps.services import oracle_service
        for report, arguments in [
            (oracle_service._send_log_to_oracle,
             dict(animal_type="0", detect_count=1, reason="shortage")),
            (oracle_service._send_danger_log_to_oracle, dict(danger_type=2)),
        ]:
            with self.subTest(report=report.__name__), \
                    patch.object(oracle_service, "get_active_drone_id", return_value="DRONE03"), \
                    patch.object(oracle_service, "_save_physical_snapshot",
                                 side_effect=oracle_service.runtime_settings.RuntimePathError("SSA_UPLOAD_ROOT cannot provide the snapshot directory")), \
                    patch.object(oracle_service, "enqueue_discord_alert") as enqueue, \
                    patch.object(oracle_service.requests, "post") as post:
                with self.assertRaises(oracle_service.runtime_settings.RuntimePathError):
                    report(frame=object(), source_key="video_3",
                           notification={"object_label": "test"}, **arguments)
                enqueue.assert_called_once()
                self.assertIsNone(enqueue.call_args.kwargs["image_path"])
                self.assertEqual("DRONE03", enqueue.call_args.kwargs["drone_id"])
                post.assert_not_called()

    def test_report_success_requires_success_json_not_login_html(self):
        from apps.services import oracle_service
        response = Mock(status_code=200)
        response.json.side_effect = ValueError("HTML login page")
        self.assertFalse(oracle_service._spring_report_succeeded(response))
        response.json.side_effect = None
        response.json.return_value = {"status": "SUCCESS"}
        self.assertTrue(oracle_service._spring_report_succeeded(response))
        self.assertFalse(oracle_service.SPRING_HOST.endswith("/"))


if __name__ == "__main__":
    unittest.main()
