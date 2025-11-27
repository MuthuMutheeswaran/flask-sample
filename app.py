from flask import Flask, request, Response
import os
import requests

app = Flask(__name__)

# Get Gemini API key from environment variable (Render → Environment tab)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

MODEL_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash:generateContent"
)


@app.route("/", methods=["GET"])
def home():
    return Response("Trip Planner API is running ✅", mimetype="text/plain")


@app.route("/trip-plan", methods=["GET"])
def trip_plan():
    # ---------- SAFETY MESSAGE IF CALLED WRONG WAY ----------
    if not request.data and not request.form and not request.is_json:
        txt = (
            "This endpoint expects a POST request with: "
            "mode, start_location, travel_location, days, budget."
        )
        return Response(txt, mimetype="text/plain")

    # ---------- READ INPUT (JSON or form) ----------
    data = {}

    try:
        if request.is_json:
            data = request.get_json(silent=True) or {}
        else:
            # form-encoded (Zoho invokeurl default)
            data = request.form.to_dict() if request.form else {}
    except Exception as e:
        return Response(
            f"Error parsing request: {e}",
            mimetype="text/plain",
            status=400,
        )

    mode = str(data.get("mode", "")).strip()
    start_location = str(data.get("start_location", "")).strip()
    travel_location = str(data.get("travel_location", "")).strip()

    # days & budget as numbers
    try:
        days = int(data.get("days", 0))
    except Exception:
        days = 0

    try:
        budget = float(data.get("budget", 0))
    except Exception:
        budget = 0

    # ---------- MODE CHECK ----------
    if mode != "TRIP_PLAN":
        return Response("Unsupported mode", mimetype="text/plain", status=400)

    # ---------- BASIC VALIDATION ----------
    if not start_location or not travel_location or not days or not budget:
        return Response(
            "Invalid input. start_location, travel_location, days, budget are required.",
            mimetype="text/plain",
            status=400,
        )

    # ---------- BASE SUMMARY (Gemini-independent) ----------
    if days <= 0:
        return Response(
            "Days must be greater than 0.",
            mimetype="text/plain",
            status=400,
        )

    per_day_budget = int(round(budget / days))
    base_text = (
        f"Trip plan from {start_location} to {travel_location}\n\n"
        f"Days: {days}\n"
        f"Budget per person: ₹{int(budget)}\n"
        f"Approx budget per day (per person): ₹{per_day_budget}\n\n"
    )

    # ---------- API KEY CHECK ----------
    if not GEMINI_API_KEY:
        return Response(
            base_text + "[Server error: GEMINI_API_KEY not configured.]",
            mimetype="text/plain",
            status=500,
        )

    # ---------- PROMPT ----------
    prompt =(
"You are an expert Indian travel planner. Create a realistic day-wise trip itinerary.\n\n" +
"Start location: " + start_location + "\n" +
"Destination: " + travel_location + "\n" +
"Total Days: " + days + "\n" +
"Budget per person (INR): " + budget + "\n\n" +
"Rules:\n" +
"1) Choose real and popular places only inside the destination region.\n" +
"2) Add 2 or 3 best places per day with a short description and practical sequence.\n" +
"3) Adjust style based on budget but do NOT show cost or amount values.\n" +
"4) Keep plan realistic and not rushed.\n" +
"5) Do NOT use bullets (-, •) or Markdown formatting (#, **).\n" +
"6) Do NOT include costs, ticket prices, or spending summary.\n" +
"7) Output must be plain text only.\n\n" +
"Output format exactly like this:\n" +
"Trip plan for " + travel_location + " (" + days + " days)\n" +
"Day 1: Place 1, Place 2 (short description)\n" +
"Day 2: Place 3, Place 4 (short description)\n" +
"...\n" +
"Day " + days + ": ...\n" +
"Do not add any extra lines after this.")
    
    
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    params = {"key": GEMINI_API_KEY}

    # ---------- CALL GEMINI ----------
    try:
        r = requests.post(MODEL_URL, params=params, json=payload, timeout=30)
    except Exception as e:
        return Response(
            base_text + f"[Error calling AI API: {e}]",
            mimetype="text/plain",
            status=500,
        )

    # ---------- PARSE GEMINI RESPONSE ----------
    try:
        resp_json = r.json()
    except Exception as e:
        return Response(
            base_text + f"[Error reading AI response: {e}]",
            mimetype="text/plain",
            status=500,
        )

    ai_text = ""
    try:
        ai_text = (
            resp_json["candidates"][0]["content"]["parts"][0].get("text", "")
        )
    except Exception as e:
        ai_text = f"[No valid AI text. Error: {e}]"

    final_text = base_text + ai_text

    return Response(final_text, mimetype="text/plain")


if __name__ == "__main__":
    # For local testing only
    app.run(host="0.0.0.0", port=5000, debug=True)
