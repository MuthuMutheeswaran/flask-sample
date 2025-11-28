from flask import Flask, request, Response
import os
import requests
import time
import json

import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)

# ===================== GEMINI CONFIG =====================

# Get Gemini API key from environment variable (Render → Environment tab)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Primary model endpoint (current/recommended)
DEFAULT_MODEL_NAME = "gemini-2.5-flash"
MODEL_URL = f"https://generativelanguage.googleapis.com/v1/models/{DEFAULT_MODEL_NAME}:generateContent"

# Models list endpoint (used for fallback/discovery)
MODELS_LIST_URL = "https://generativelanguage.googleapis.com/v1/models"


# ===================== GOOGLE SHEETS CONFIG =====================

# These will come from Render env vars
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")  # full JSON string
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")                          # spreadsheet ID
TRIPPLAN_SHEET_NAME = os.environ.get("TRIPPLAN_SHEET_NAME", "TripPlans")    # sheet/tab name


def get_gspread_client():
    """
    Create a gspread client using service account JSON from env.
    This is called only when /get-trip-plan is used.
    """
    if not GOOGLE_SERVICE_ACCOUNT_JSON or not GOOGLE_SHEET_ID:
        raise RuntimeError("Google Sheets not configured (GOOGLE_SERVICE_ACCOUNT_JSON / GOOGLE_SHEET_ID missing).")

    sa_info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    creds = Credentials.from_service_account_info(sa_info, scopes=scopes)
    client = gspread.authorize(creds)
    return client


def find_trip_plan(start, travel, days, budget):
    """
    TripPlans sheet structure (row appended by Apps Script):

    [ Timestamp, Start Location, Travel Location, Days, Budget, Trip Plan ]
      A           B               C              D     E       F
    """
    client = get_gspread_client()
    sh = client.open_by_key(GOOGLE_SHEET_ID)
    ws = sh.worksheet(TRIPPLAN_SHEET_NAME)

    rows = ws.get_all_values()
    if len(rows) < 2:
        return ""

    data_rows = rows[1:]  # skip header

    start = (start or "").strip().lower()
    travel = (travel or "").strip().lower()
    days = str(days or "").strip()
    budget = str(budget or "").strip()

    START_COL = 1   # B
    TRAVEL_COL = 2  # C
    DAYS_COL = 3    # D
    BUDGET_COL = 4  # E
    PLAN_COL = 5    # F

    # Search from last row (latest entry)
    for r in reversed(data_rows):
        if len(r) <= PLAN_COL:
            continue

        r_start = str(r[START_COL] or "").strip().lower()
        r_travel = str(r[TRAVEL_COL] or "").strip().lower()
        r_days = str(r[DAYS_COL] or "").strip()
        r_budget = str(r[BUDGET_COL] or "").strip()

        if r_start == start and r_travel == travel and r_days == days and r_budget == budget:
            return str(r[PLAN_COL] or "")

    return ""


# ===================== BASIC ROUTES =====================

@app.route("/", methods=["GET"])
def home():
    return Response("Trip Planner API is running ✅", mimetype="text/plain")


# ===================== GEMINI HELPERS =====================

def call_generate(model_url: str, api_key: str, payload: dict, timeout: int = 30):
    """
    Call the generateContent endpoint and return (resp_obj, status_code).
    """
    try:
        r = requests.post(model_url, params={"key": api_key}, json=payload, timeout=timeout)
        return r, r.status_code
    except Exception as e:
        return {"error": f"Exception when calling model endpoint: {e}"}, 500


def discover_and_pick_model(api_key: str):
    """
    Call the Models endpoint to list available models and pick a likely valid gemini model.
    Preference order:
      1. gemini-2.5-flash
      2. gemini-*flash*
      3. gemini-*
      4. first model returned
    Returns model name or None.
    """
    try:
        r = requests.get(MODELS_LIST_URL, params={"key": api_key}, timeout=15)
        r.raise_for_status()
        data = r.json()
        models = []

        if isinstance(data, dict):
            if "models" in data and isinstance(data["models"], list):
                models = data["models"]
            elif "model" in data and isinstance(data["model"], list):
                models = data["model"]
            else:
                for v in data.values():
                    if isinstance(v, list):
                        models = v
                        break

        names = []
        for m in models:
            if isinstance(m, dict) and "name" in m:
                nm = m["name"]
                try:
                    nm_id = nm.split("/")[-1]
                except Exception:
                    nm_id = nm
                names.append(nm_id)
            elif isinstance(m, str):
                names.append(m.split("/")[-1])

        if not names:
            return None

        for pref in [DEFAULT_MODEL_NAME, "flash", "gemini"]:
            for name in names:
                lower = name.lower()
                if pref == DEFAULT_MODEL_NAME and lower == DEFAULT_MODEL_NAME:
                    return name
                if pref == "flash" and "flash" in lower and "gemini" in lower:
                    return name
                if pref == "gemini" and "gemini" in lower:
                    return name

        return names[0]
    except Exception:
        return None


# ===================== /trip-plan (Gemini) =====================

@app.route("/trip-plan", methods=["GET", "POST"])
def trip_plan():
    # ---------- READ INPUT ----------
    data = {}

    try:
        if request.is_json:
            data = request.get_json(silent=True) or {}
        elif request.form:
            data = request.form.to_dict()
        elif request.args:
            data = request.args.to_dict()
        else:
            txt = (
                "This endpoint expects: mode, start_location, travel_location, days, budget "
                "via JSON body, form-data, or query parameters."
            )
            return Response(txt, mimetype="text/plain", status=400)
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

    # --------- Budget support for both range string & numeric ---------
raw_budget = data.get("budget", "").strip()

# "3000 - 6000" , "3000-6000" , "₹3000 – ₹6000" support
if any(x in raw_budget for x in ["-", "–"]):
    for ch in ["₹", ","]:
        raw_budget = raw_budget.replace(ch, "")

    parts = raw_budget.replace("–", "-").split("-")
    try:
        min_b = float(parts[0].strip())
        max_b = float(parts[1].strip())
        budget = (min_b + max_b) / 2  # midpoint
    except:
        budget = 0
else:
    try:
        budget = float(raw_budget)
    except:
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

    if days <= 0:
        return Response(
            "Days must be greater than 0.",
            mimetype="text/plain",
            status=400,
        )

    # ---------- BASE SUMMARY ----------
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
    prompt = (
        "You are an expert Indian travel planner. Produce a day-wise list of 2 or 3 real and popular places for the given destination. "
        "Do NOT include any descriptions, timings, travel instructions, or price/expense information. Do NOT output an estimated total spend.\n\n"
        f"Start location: {start_location}\n"
        f"Destination: {travel_location}\n"
        f"Total Days: {days}\n"
        f"Budget per person (INR): {budget}\n\n"
        "Rules:\n"
        "1) For each day give exactly 2 or 3 place names only (no extra text for each place).\n"
        "2) Use real and popular places inside the destination region only.\n"
        "3) Keep the plan realistic — sequence doesn't need explanation, just place names.\n"
        "4) Output must be plain text only (no bullets, no Markdown symbols, no numbers other than day numbers).\n\n"
        "Output format exactly like this:\n"
        f"Trip plan for {travel_location} ({days} days)\n"
        "Day 1: Place A, Place B, Place C\n"
        "Day 2: Place D, Place E\n"
        "...\n"
        f"Day {days}: Place X, Place Y\n"
        "Do not add any other lines, not even an estimated total spend."
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ],
                "role": "user",
            }
        ]
    }

    # ---------- FIRST ATTEMPT ----------
    resp, status = call_generate(MODEL_URL, GEMINI_API_KEY, payload)

    # 404 / model not found → discover model and retry
    if status == 404 or (isinstance(resp, requests.Response) and (not resp.ok) and "not found" in resp.text.lower()):
        picked = discover_and_pick_model(GEMINI_API_KEY)
        if not picked:
            debug_info = ""
            try:
                debug_info = resp.json()
            except Exception:
                debug_info = str(resp)
            return Response(
                base_text
                + "\n[Gemini error response]\n"
                + f"Initial model returned 404. Could not auto-discover a replacement model.\n\nRaw response: {debug_info}",
                mimetype="text/plain",
                status=500,
            )

        retry_model_url = f"https://generativelanguage.googleapis.com/v1/models/{picked}:generateContent"
        time.sleep(0.5)
        resp2, status2 = call_generate(retry_model_url, GEMINI_API_KEY, payload)

        if isinstance(resp2, requests.Response):
            try:
                resp_json = resp2.json()
            except Exception as e:
                return Response(
                    base_text + f"[Error reading AI response after retry: {e}]",
                    mimetype="text/plain",
                    status=500,
                )

            if "candidates" not in resp_json:
                return Response(
                    base_text + "\n[Gemini error response after retry]\n" + str(resp_json),
                    mimetype="text/plain",
                    status=500,
                )

            ai_text = ""
            try:
                ai_text = resp_json["candidates"][0]["content"]["parts"][0].get("text", "")
            except Exception as e:
                ai_text = f"[No valid AI text after retry. Error: {e}]"

            final_text = base_text + ai_text
            return Response(final_text, mimetype="text/plain")

        else:
            return Response(
                base_text + f"[Error calling AI on retry: {resp2}]",
                mimetype="text/plain",
                status=500,
            )

    # ---------- Parse original response ----------
    if isinstance(resp, requests.Response):
        try:
            resp_json = resp.json()
        except Exception as e:
            return Response(
                base_text + f"[Error reading AI response: {e}]",
                mimetype="text/plain",
                status=500,
            )

        if "candidates" not in resp_json:
            return Response(
                base_text + "\n[Gemini error response]\n" + str(resp_json),
                mimetype="text/plain",
                status=500,
            )

        ai_text = ""
        try:
            ai_text = resp_json["candidates"][0]["content"]["parts"][0].get("text", "")
        except Exception as e:
            ai_text = f"[No valid AI text. Error: {e}]"

        final_text = base_text + ai_text
        return Response(final_text, mimetype="text/plain")

    return Response(base_text + f"[Error calling AI API: {resp}]", mimetype="text/plain", status=500)


# ===================== /get-trip-plan (Google Sheet) =====================

@app.route("/get-trip-plan", methods=["GET", "POST"])
def get_trip_plan_route():
    """
    Input (JSON or form):
      - start_location
      - travel_location
      - days
      - budget

    Output: plain text -> Trip Plan (from Google Sheet)
    """
    try:
        if request.is_json:
            data = request.get_json(silent=True) or {}
        elif request.form:
            data = request.form.to_dict()
        else:
            data = {}
    except Exception as e:
        return Response(
            f"Error parsing request body: {e}",
            mimetype="text/plain",
            status=400,
        )

    start_loc = data.get("start_location", "")
    travel_loc = data.get("travel_location", "")
    days = data.get("days", "")
    budget = data.get("budget", "")

    if not (start_loc and travel_loc and days and budget):
        return Response(
            "Missing one or more parameters: start_location, travel_location, days, budget",
            status=400,
            mimetype="text/plain",
        )

    try:
        plan_text = find_trip_plan(start_loc, travel_loc, days, budget)
    except Exception as e:
        return Response(
            f"[Error reading Google Sheet: {e}]",
            status=500,
            mimetype="text/plain",
        )

    if not plan_text:
        plan_text = ""  # Deluge side la fallback handle panna

    return Response(plan_text, status=200, mimetype="text/plain")


# ===================== MAIN =====================

if __name__ == "__main__":
    # For local testing
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
