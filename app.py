import os
from datetime import date, timedelta
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from appointment_bot import (
    DEPARTMENTS,
    AppointmentError,
    ensure_future_slots,
    extract_appointment_details,
    get_available_slots,
    book_appointment,
)


STORE_PATH = os.path.join(os.path.dirname(__file__), "slots.csv")
load_dotenv(Path(__file__).with_name(".env"))

st.set_page_config(page_title="Hospital Appointment Bot", page_icon="🏥")
st.title("Hospital Appointment Bot")
st.caption("Find an available doctor’s appointment and book it in a few steps.")

with st.sidebar:
    st.header("Language model")
    api_key = st.text_input(
        "Gemini API key",
        value=os.environ.get("GEMINI_API_KEY", ""),
        type="password",
        help="Optional. Without a key, the app uses its clearly labeled local demo parser.",
    )
    if api_key:
        st.caption("Gemini extraction is enabled for this session.")
    else:
        st.info("Demo mode: enter details using the labeled example below.")

try:
    ensure_future_slots(STORE_PATH)
except (OSError, ValueError) as exc:
    st.error(f"Could not load appointment slots: {exc}")
    st.stop()

if st.session_state.get("last_booking"):
    booking = st.session_state.pop("last_booking")
    st.success(
        f"Appointment booked. Confirmation: {booking['appointment_id']} — "
        f"{booking['date']} at {booking['time']} with {booking['doctor_name']}."
    )

st.subheader("1. Describe the appointment you need")
example_date = date.today() + timedelta(days=1)
while example_date.weekday() >= 5:
    example_date += timedelta(days=1)
st.write(
    "For demo mode, use a clear request such as: "
    "“My name is Alex Morgan. Department: Cardiology. "
    f"Date: {example_date.isoformat()}. Time: 9:00 AM. "
    "Phone: +1 555 010 1234.”"
)

with st.form("request_form"):
    request_text = st.text_area(
        "Patient request",
        placeholder="Include your name, department, preferred date and time, and phone number.",
        height=120,
    )
    extract_clicked = st.form_submit_button("Extract appointment details")

if extract_clicked:
    try:
        details = extract_appointment_details(request_text, api_key=api_key or None)
    except (ValueError, RuntimeError) as exc:
        st.error(f"Could not extract appointment details: {exc}")
    else:
        st.session_state["appointment_details"] = details

details = st.session_state.get("appointment_details")
if details:
    st.subheader("2. Review and choose an available slot")
    st.json(details)

    department_index = (
        DEPARTMENTS.index(details["department"])
        if details.get("department") in DEPARTMENTS
        else 0
    )
    with st.form("booking_form"):
        patient_name = st.text_input("Patient name", value=details.get("name", ""))
        department = st.selectbox(
            "Department", DEPARTMENTS, index=department_index
        )
        preferred_date = details.get("preferred_date", "")
        try:
            initial_date = date.fromisoformat(preferred_date)
            if initial_date < date.today():
                initial_date = date.today()
        except (TypeError, ValueError):
            initial_date = date.today()
        appointment_date = st.date_input(
            "Preferred date", value=initial_date, min_value=date.today()
        )
        patient_phone = st.text_input("Phone number (optional)", value=details.get("phone", ""))

        available = get_available_slots(
            STORE_PATH,
            department=department,
            appointment_date=appointment_date.isoformat(),
            preferred_time=details.get("preferred_time", ""),
        )
        if available:
            preferred_time = details.get("preferred_time", "")

            def slot_label(slot):
                recommendation = (
                    " — preferred time"
                    if preferred_time and slot["time"] == preferred_time
                    else ""
                )
                return (
                    f"{slot['time']} — {slot['doctor_name']}"
                    f"{recommendation}"
                )

            selected_slot = st.selectbox(
                "Available appointment slot",
                available,
                format_func=slot_label,
            )
        else:
            selected_slot = None
            st.info("No free slots for this department and date. Choose another date.")

        book_clicked = st.form_submit_button(
            "Book appointment", disabled=not available
        )

    if book_clicked and selected_slot:
        try:
            booking = book_appointment(
                STORE_PATH,
                slot_id=selected_slot["slot_id"],
                patient_name=patient_name,
                patient_phone=patient_phone,
            )
        except (AppointmentError, OSError, ValueError) as exc:
            st.error(f"Could not book the appointment: {exc}")
        else:
            st.session_state["last_booking"] = booking
            st.session_state.pop("appointment_details", None)
            st.rerun()

with st.expander("Available departments"):
    st.write(", ".join(DEPARTMENTS))

st.caption(
    "Educational demo only. Do not enter real patient information; this app stores "
    "booking details in a local CSV and is not designed for clinical or production use."
)
