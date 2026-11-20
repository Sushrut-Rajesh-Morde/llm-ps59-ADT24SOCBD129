import csv
import json
import os
import re
import tempfile
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Optional


DEPARTMENTS = ("Cardiology", "Dermatology", "General Medicine")
DOCTORS = {
    "Cardiology": "Dr. A. Mehta",
    "Dermatology": "Dr. S. Rao",
    "General Medicine": "Dr. K. Shah",
}
SLOT_TIMES = ("09:00", "10:30", "14:00", "15:30")
SLOT_FIELDS = (
    "slot_id",
    "date",
    "time",
    "department",
    "doctor_name",
    "is_booked",
    "patient_name",
    "patient_phone",
    "appointment_id",
)


class AppointmentError(ValueError):
    """Raised when an appointment cannot be booked."""


def _read_slots(csv_path: str) -> list[dict[str, str]]:
    with open(csv_path, newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames or not set(SLOT_FIELDS).issubset(reader.fieldnames):
            raise ValueError(f"Slots CSV must contain these columns: {', '.join(SLOT_FIELDS)}")
        return [
            {field: (row.get(field) or "").strip() for field in SLOT_FIELDS}
            for row in reader
        ]


def _write_slots(csv_path: str, slots: list[dict[str, str]]) -> None:
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            newline="",
            encoding="utf-8",
            dir=path.parent,
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary_path = file.name
            writer = csv.DictWriter(file, fieldnames=SLOT_FIELDS)
            writer.writeheader()
            writer.writerows(slots)
        os.replace(temporary_path, path)
    except OSError:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)
        raise


def _next_weekdays(start: date, count: int) -> list[date]:
    days = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def ensure_future_slots(csv_path: str, today: Optional[date] = None) -> None:
    """Create the CSV and add a fresh weekday schedule when no future free slots remain."""
    today = today or date.today()
    if not os.path.exists(csv_path):
        _write_slots(csv_path, [])

    slots = _read_slots(csv_path)
    has_future_availability = any(
        slot["is_booked"].lower() != "true"
        and _valid_date(slot["date"]) is not None
        and _valid_date(slot["date"]) >= today
        for slot in slots
    )
    if has_future_availability:
        return

    existing_ids = {slot["slot_id"] for slot in slots}
    for day in _next_weekdays(today + timedelta(days=1), 5):
        for department in DEPARTMENTS:
            for time in SLOT_TIMES:
                slot_id = f"{day:%Y%m%d}-{department[:3].upper()}-{time.replace(':', '')}"
                if slot_id in existing_ids:
                    continue
                slots.append(
                    {
                        "slot_id": slot_id,
                        "date": day.isoformat(),
                        "time": time,
                        "department": department,
                        "doctor_name": DOCTORS[department],
                        "is_booked": "false",
                        "patient_name": "",
                        "patient_phone": "",
                        "appointment_id": "",
                    }
                )
    _write_slots(csv_path, slots)


def _valid_date(value: str) -> Optional[date]:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def get_available_slots(
    csv_path: str,
    department: str,
    appointment_date: str,
    preferred_time: str = "",
) -> list[dict[str, str]]:
    slots = _read_slots(csv_path)
    available = [
        slot
        for slot in slots
        if slot["department"] == department
        and slot["date"] == appointment_date
        and slot["is_booked"].lower() != "true"
    ]
    return sorted(
        available,
        key=lambda slot: (
            slot["time"] != preferred_time,
            slot["time"],
            slot["slot_id"],
        ),
    )


def book_appointment(
    csv_path: str,
    slot_id: str,
    patient_name: str,
    patient_phone: str = "",
) -> dict[str, str]:
    patient_name = patient_name.strip()
    if not patient_name:
        raise AppointmentError("Patient name is required.")
    if len(patient_name) > 80:
        raise AppointmentError("Patient name must be 80 characters or fewer.")

    phone = patient_phone.strip()
    phone_digits = re.sub(r"\D", "", phone)
    if phone and not 7 <= len(phone_digits) <= 15:
        raise AppointmentError("Enter a phone number containing 7 to 15 digits.")

    slots = _read_slots(csv_path)
    selected = next((slot for slot in slots if slot["slot_id"] == slot_id), None)
    if selected is None:
        raise AppointmentError("The selected slot does not exist.")
    if selected["is_booked"].lower() == "true":
        raise AppointmentError("This slot has just been booked. Please choose another.")

    selected["is_booked"] = "true"
    selected["patient_name"] = patient_name
    selected["patient_phone"] = phone
    selected["appointment_id"] = uuid.uuid4().hex[:10].upper()
    _write_slots(csv_path, slots)
    return selected.copy()


def _labeled_value(text: str, labels: str) -> str:
    match = re.search(
        rf"(?im)(?:^|[.;,\n])\s*(?:{labels})\s*:\s*([^\r\n,;.]+)",
        text,
    )
    return match.group(1).strip() if match else ""


def _local_extract(text: str, today: date) -> dict[str, str]:
    name = _labeled_value(text, r"name|patient")
    if not name:
        match = re.search(
            r"\b(?:my name is|i am|i'm)\s+([A-Za-z][A-Za-z'-]*(?:\s+[A-Za-z][A-Za-z'-]*){0,3})",
            text,
            flags=re.IGNORECASE,
        )
        name = match.group(1).strip() if match else ""

    department_text = _labeled_value(text, r"department|specialty").lower()
    if not department_text:
        department_text = text.lower()
    department = ""
    for candidate, words in (
        ("Cardiology", ("cardiology", "cardiologist", "cardio", "heart")),
        ("Dermatology", ("dermatology", "dermatologist", "skin")),
        (
            "General Medicine",
            ("general medicine", "general physician", "physician", "general"),
        ),
    ):
        if any(re.search(rf"\b{re.escape(word)}\b", department_text) for word in words):
            department = candidate
            break

    date_text = _labeled_value(text, r"date|day").lower()
    if not date_text:
        date_text = text.lower()
    appointment_date = ""
    iso_match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", date_text)
    if iso_match and _valid_date(iso_match.group()) is not None:
        appointment_date = iso_match.group()
    elif re.search(r"\btomorrow\b", date_text):
        appointment_date = (today + timedelta(days=1)).isoformat()
    elif re.search(r"\btoday\b", date_text):
        appointment_date = today.isoformat()
    else:
        weekday_match = re.search(
            r"\b(next\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            date_text,
        )
        if weekday_match:
            weekdays = {
                "monday": 0,
                "tuesday": 1,
                "wednesday": 2,
                "thursday": 3,
                "friday": 4,
                "saturday": 5,
                "sunday": 6,
            }
            target = weekdays[weekday_match.group(2)]
            offset = (target - today.weekday()) % 7
            if offset == 0 or weekday_match.group(1):
                offset += 7
            appointment_date = (today + timedelta(days=offset)).isoformat()

    time_text = _labeled_value(text, r"time")
    if not time_text:
        time_text = text
    time_match = re.search(
        r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\b",
        time_text,
        flags=re.IGNORECASE,
    )
    preferred_time = ""
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or "00")
        meridiem = time_match.group(3).lower()[0]
        if 1 <= hour <= 12 and minute < 60:
            hour = hour % 12 + (12 if meridiem == "p" else 0)
            preferred_time = f"{hour:02d}:{minute:02d}"
    else:
        time_match = re.search(r"\b([01]\d|2[0-3]):([0-5]\d)\b", time_text)
        if time_match:
            preferred_time = f"{int(time_match.group(1)):02d}:{time_match.group(2)}"

    phone = _labeled_value(text, r"phone|mobile|contact")
    return {
        "name": name,
        "department": department,
        "preferred_date": appointment_date,
        "preferred_time": preferred_time,
        "phone": phone,
    }


def extract_appointment_details(
    text: str,
    api_key: Optional[str] = None,
    today: Optional[date] = None,
) -> dict[str, str]:
    if not text.strip():
        raise ValueError("Enter a patient request first.")
    if not api_key:
        return _local_extract(text, today or date.today())

    try:
        from google import genai
        from google.genai import errors, types
    except ImportError as exc:
        raise RuntimeError(
            "Gemini support is not installed. Run `pip install -r requirements.txt`."
        ) from exc

    prompt = f"""Extract appointment details from the patient request below.
Return only a JSON object with exactly these string keys:
name, department, preferred_date, preferred_time, phone.
Use an empty string when a value is missing. Department must be one of:
{", ".join(DEPARTMENTS)}.
Convert dates to YYYY-MM-DD and times to 24-hour HH:MM. Today is {(today or date.today()).isoformat()}.
Do not infer personal details that were not given.

Patient request:
{text}"""
    try:
        response = genai.Client(api_key=api_key).models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
    except errors.APIError as exc:
        raise RuntimeError(f"Gemini request failed: {exc}") from exc

    if not response.text:
        raise RuntimeError("Gemini returned an empty response.")
    try:
        extracted = json.loads(response.text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Gemini returned invalid JSON.") from exc
    if not isinstance(extracted, dict):
        raise RuntimeError("Gemini response must be a JSON object.")

    result = {}
    for field in ("name", "department", "preferred_date", "preferred_time", "phone"):
        value = extracted.get(field, "")
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise RuntimeError(f"Gemini returned an invalid {field} value.")
        result[field] = value.strip()
    if result["department"] not in DEPARTMENTS:
        result["department"] = ""
    if result["preferred_date"] and _valid_date(result["preferred_date"]) is None:
        result["preferred_date"] = ""
    if result["preferred_time"] and not re.fullmatch(
        r"(?:[01]\d|2[0-3]):[0-5]\d", result["preferred_time"]
    ):
        result["preferred_time"] = ""
    return result
