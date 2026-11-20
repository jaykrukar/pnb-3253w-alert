"""Offline regression tests for the course tracker.

These tests never contact UConn or ntfy and never send notifications.
Run with: python -m unittest discover -s tests -v
"""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import tracker


class SeatParsingTests(unittest.TestCase):
    def test_live_seat_format(self):
        text = "PNB 3253W\nSeats: Max Enrollment: 40 / Seats Available: 3"
        self.assertEqual(tracker.seats_from_text(text), 3)

    def test_full_section(self):
        text = "Seats: Max Enrollment: 40 / Seats Available: 0"
        self.assertEqual(tracker.seats_from_text(text), 0)

    def test_invalid_capacity_is_not_treated_as_open(self):
        text = "Seats: Max Enrollment: 40 / Seats Available: 41"
        self.assertIsNone(tracker.seats_from_text(text))

    def test_separate_seat_section(self):
        text = "Seats\nEnrollment Capacity: 40\nEnrolled: 36\nWaitlist: 12"
        self.assertEqual(tracker.seats_from_text(text), 4)

    def test_reserved_seats_are_not_open_seats(self):
        text = "Reserved Seats\nSeats Available: 10\nWaitlist: 0"
        self.assertIsNone(tracker.seats_from_text(text))

    def test_missing_seat_data_is_unknown(self):
        self.assertIsNone(tracker.seats_from_text("PNB 3253W\nMeeting Information"))

    def test_explicitly_full_notes(self):
        notes = "Registration Notes\nThis section is full.\nDescription"
        self.assertTrue(tracker.section_is_explicitly_full(notes))

    def test_unrelated_full_note_is_ignored(self):
        notes = "Description\nThis section is full.\nMeeting Information"
        self.assertFalse(tracker.section_is_explicitly_full(notes))


class URLAndNotificationValidationTests(unittest.TestCase):
    def test_real_section_url_is_allowed(self):
        tracker.check_section_url(
            "https://classes.uconn.edu/?details&srcdb=1273&crn=4418"
        )

    def test_untrusted_host_is_blocked(self):
        with self.assertRaises(ValueError):
            tracker.check_section_url(
                "https://classes.uconn.edu.evil.example/?details&srcdb=1273&crn=4418"
            )

    def test_malformed_crn_is_blocked(self):
        with self.assertRaises(ValueError):
            tracker.check_section_url(
                "https://classes.uconn.edu/?details&srcdb=1273&crn=not-a-number"
            )

    def test_short_notification_topic_is_rejected_offline(self):
        with self.assertRaises(ValueError):
            tracker.publish("short", "hello", "test", "https://example.com")


class NotificationStateTests(unittest.TestCase):
    def test_open_only_alerts_on_transition_and_reopening(self):
        open_three = "PNB 3253W\nSeats: Max Enrollment: 40 / Seats Available: 3"
        full = "PNB 3253W\nSeats: Max Enrollment: 40 / Seats Available: 0"
        open_one = "PNB 3253W\nSeats: Max Enrollment: 40 / Seats Available: 1"

        with TemporaryDirectory() as tmp:
            state_file = Path(tmp) / ".tracker_state.json"
            with (
                patch.object(tracker, "STATE_PATH", state_file),
                patch.dict(os.environ, {"NTFY_TOPIC": "validtopic1234567890",
                                        "TEST_NOTIFICATION": "false"}),
                patch.object(tracker, "fetch_page_text", return_value=open_three) as fetch,
                patch.object(tracker, "publish") as notify,
            ):
                self.assertEqual(tracker.main(), 0)
                self.assertEqual(notify.call_count, 1)
                self.assertTrue(state_file.exists())
                self.assertEqual(tracker.main(), 0)
                self.assertEqual(notify.call_count, 1)

                fetch.return_value = full
                self.assertEqual(tracker.main(), 0)
                self.assertEqual(notify.call_count, 1)

                fetch.return_value = open_one
                self.assertEqual(tracker.main(), 0)
                self.assertEqual(notify.call_count, 2)

    def test_unknown_seat_count_fails_closed(self):
        with TemporaryDirectory() as tmp:
            with (
                patch.object(tracker, "STATE_PATH", Path(tmp) / "state.json"),
                patch.dict(os.environ, {"NTFY_TOPIC": "validtopic1234567890",
                                        "TEST_NOTIFICATION": "false"}),
                patch.object(tracker, "fetch_page_text",
                             return_value="PNB 3253W\nNo enrollment data loaded"),
                patch.object(tracker, "publish") as notify,
            ):
                with self.assertRaises(RuntimeError):
                    tracker.main()
                notify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
