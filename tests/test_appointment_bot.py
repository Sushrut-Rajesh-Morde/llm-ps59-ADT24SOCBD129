import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from appointment_bot import (
    AppointmentError,
    book_appointment,
    ensure_future_slots,
    extract_appointment_details,
    get_available_slots,
)


class AppointmentBotTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.csv_path = str(Path(self.temp_dir.name) / "slots.csv")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_local_extraction_parses_labeled_request(self):
        result = extract_appointment_details(
            "My name is Alex Morgan. Department: Cardiology. "
            "Date: 2026-11-23. Time: 9:00 AM. Phone: +1 555 010 1234.",
            today=date(2026, 11, 20),
        )
        self.assertEqual(
            result,
            {
                "name": "Alex Morgan",
                "department": "Cardiology",
                "preferred_date": "2026-11-23",
                "preferred_time": "09:00",
                "phone": "+1 555 010 1234",
            },
        )

    def test_local_extraction_parses_semicolon_separated_fields(self):
        result = extract_appointment_details(
            "Name: Priya Shah; Department: Dermatology; Date: 2026-11-24; "
            "Time: 10:30 AM; Phone: 9876543210",
            today=date(2026, 11, 20),
        )
        self.assertEqual(result["name"], "Priya Shah")
        self.assertEqual(result["department"], "Dermatology")
        self.assertEqual(result["preferred_date"], "2026-11-24")
        self.assertEqual(result["preferred_time"], "10:30")
        self.assertEqual(result["phone"], "9876543210")

    def test_schedule_creation_is_idempotent(self):
        ensure_future_slots(self.csv_path, today=date(2026, 11, 20))
        with open(self.csv_path, newline="", encoding="utf-8") as file:
            first_slots = list(csv.DictReader(file))
        first_count = len(first_slots)
        ensure_future_slots(self.csv_path, today=date(2026, 11, 20))
        with open(self.csv_path, newline="", encoding="utf-8") as file:
            second_count = sum(1 for _ in csv.DictReader(file))
        self.assertEqual(first_count, 5 * 3 * 4)
        self.assertEqual(second_count, first_count)
        self.assertTrue(all(slot["date"] > "2026-11-20" for slot in first_slots))

    def test_booking_updates_csv_and_removes_slot_from_availability(self):
        ensure_future_slots(self.csv_path, today=date(2026, 11, 20))
        slots = get_available_slots(
            self.csv_path, "Cardiology", "2026-11-23", "09:00"
        )
        booking = book_appointment(
            self.csv_path,
            slot_id=slots[0]["slot_id"],
            patient_name="Alex Morgan",
            patient_phone="+1 555 010 1234",
        )
        self.assertTrue(booking["appointment_id"])
        remaining = get_available_slots(
            self.csv_path, "Cardiology", "2026-11-23", "09:00"
        )
        self.assertEqual(len(remaining), len(slots) - 1)

    def test_already_booked_slot_cannot_be_booked_again(self):
        ensure_future_slots(self.csv_path, today=date(2026, 11, 20))
        slot = get_available_slots(
            self.csv_path, "Cardiology", "2026-11-23"
        )[0]
        book_appointment(self.csv_path, slot["slot_id"], "Alex Morgan")
        with self.assertRaisesRegex(AppointmentError, "just been booked"):
            book_appointment(self.csv_path, slot["slot_id"], "Sam Lee")

    def test_invalid_phone_is_rejected(self):
        ensure_future_slots(self.csv_path, today=date(2026, 11, 20))
        slot = get_available_slots(
            self.csv_path, "Cardiology", "2026-11-23"
        )[0]
        with self.assertRaisesRegex(AppointmentError, "7 to 15 digits"):
            book_appointment(self.csv_path, slot["slot_id"], "Alex Morgan", "123")


if __name__ == "__main__":
    unittest.main()
