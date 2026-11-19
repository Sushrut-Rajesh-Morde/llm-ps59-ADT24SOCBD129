# Hospital Appointment Bot

A small Streamlit project that extracts appointment preferences, shows available doctor slots, and books a selected slot by updating `slots.csv`.

## Run locally

1. Use Python 3.10 or later.
2. Install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Start the app:

   ```powershell
   python -m streamlit run app.py
   ```

4. For Gemini extraction, enter a Gemini API key in the sidebar or set `GEMINI_API_KEY` before starting the app. Without a key, the app switches to its local demo parser; use the labeled request format shown on screen. Gemini errors are reported rather than silently switching modes.

The app creates `slots.csv` with a weekday schedule on first run, and adds a fresh schedule when no future free slots remain. Booking updates the selected row and stores a confirmation ID. Keep a backup of the CSV if you want to preserve demo bookings.

## Try these requests

- `My name is Alex Morgan. Department: Cardiology. Date: <upcoming weekday date>. Time: 9:00 AM. Phone: +1 555 010 1234.`
- `Name: Priya Shah; Department: Dermatology; Date: <upcoming weekday date>; Time: 10:30 AM; Phone: 9876543210`
- `I am Sam Lee. I need General Medicine tomorrow at 10:30 AM.`
- `Name: Mira Patel; Department: Cardiology; Date: <upcoming weekday date>; Time: 09:00`
- `My name is Dev Kumar. I need to see a skin doctor next Monday at 9 AM.`

Replace `<upcoming weekday date>` with a future weekday in `YYYY-MM-DD` format (the app's example uses the next weekday). In demo mode, use ISO dates to ensure the date is understood. The local parser supports common date phrases, but is intentionally limited; Gemini handles more natural phrasing.

## Tests

Run the standard-library tests with:

```powershell
python -m unittest discover -s tests -v
```

## Safety and scope

This is an educational prototype, not a medical system. Do not enter real patient information. Booking information is stored as plain text in a local CSV; the app has no authentication, encryption, or production-grade multi-user coordination. It does not provide medical advice.
