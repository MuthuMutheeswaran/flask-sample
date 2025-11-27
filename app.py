from flask import Flask, request, Response
import os
import requests
import time

app = Flask(__name__)

# Get Gemini API key from environment variable (Render → Environment tab)
GEMINI_API_KEY = "AIzaSyC2uCDMhV_dpVAcasMSfqy3Crqn0THnvuw"

# Primary model endpoint (current/recommended). You can change this to another valid model.
# Note: keep the pattern https://generativelanguage.googleapis.com/v1/models/{model}:generateContent
DEFAULT_MODEL_NAME = "gemini-2.5-flash"
MODEL_URL = f"https://generativelanguage.googleapis.com/v1/models/{DEFAULT_MODEL_NAME}:generateContent"

# Models list endpoint (used for fallback/discovery)
MODELS_LIST_URL = "https://generativelanguage.googleapis.com/v1/models"


@app.route("/", methods=["GET"])
def home():
    return Response("Trip Planner API is running ✅", mimetype="text/plain")


def call_generate(model_url: str, api_key: str, payload: dict, timeout: int = 30):
    """
    Call the generateContent endpoint and return (resp_obj, status_code).
    """
    try:
        r = requests.post(model_url, params={"key": api_key}, json=payload, timeout=timeout)
        # return both response object and status code so caller can inspect
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

        # Response shape typically has 'models' list or similar
        if isinstance(data, dict):
            # try common keys
            if "models" in data and isinstance(data["models"], list):
                models = data["models"]
            elif "model" in data and isinstance(data["model"], list):
                models = data["model"]
            else:
                # sometimes it's a direct list
                # if top-level looks like list, handle it
                # fall back to scanning values for 'name'
                for v in data.values():
                    if isinstance(v, list):
                        models = v
                        break

        # extract names
        names = []
        for m in models:
            if isinstance(m, dict) and "name" in m:
                # name sometimes comes as "models/gemini-2.5-flash"
                nm = m["name"]
                # normalize to just model id (take last segment after '/')
                try:
                    nm_id = nm.split("/")[-1]
                except Exception:
                    nm_id = nm
                names.append(nm_id)
            elif isinstance(m, str):
                # sometimes API returns plain strings
                names.append(m.split("/")[-1])
        # Try to pick best match
        if not names:
            return None

        # preference
        for pref in [DEFAULT_MODEL_NAME, "flash", "gemini"]:
            for name in names:
                lower = name.lower()
                if pref == DEFAULT_MODEL_NAME and lower == DEFAULT_MODEL_NAME:
                    return name
                if pref == "flash" and "flash" in lower and "gemini" in lower:
                    return name
                if pref == "gemini" and "gemini" in lower:
                    return name

        # fallback: return first
        return names[0]
    except Exception:
        return None


@app.route("/trip-plan", methods=["GET", "POST"])
def trip_plan():
    # ---------- READ INPUT (JSON, form, or query params) ----------
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

    if days <= 0:
        return Response(
            "Days must be greater than 0.",
            mimetype="text/plain",
            status=400,
        )

    # ---------- BASE SUMMARY (Gemini-independent) ----------
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

    # ---------- PROMPT (with final approximate total) ----------
    prompt = (
        "You are an expert Indian travel planner. Create a realistic day-wise trip itinerary for a trip in India, "
        "and give an approximate total spend at the end.\n\n"
        f"Start location: {start_location}\n"
        f"Destination: {travel_location}\n"
        f"Total Days: {days}\n"
        f"Budget per person (INR): {budget}\n\n"
        "Rules:\n"
        "1) Choose real and popular places only inside the destination region.\n"
        "2) Add 2 or 3 best places per day with a short description and practical sequence.\n"
        "3) Keep the plan realistic and not rushed.\n"
        "4) Consider a normal Indian traveller: simple hotels or homestays for low budgets, better stays for higher budgets.\n"
        "5) The approximate total spend you give must be less than or equal to the given budget.\n"
        "6) You can only give ONE final total value, not a full price breakdown.\n"
        "7) Output must be plain text only (no bullets, no Markdown symbols like -, •, #, **).\n\n"
        "Output format exactly like this:\n"
        f"Trip plan for {travel_location} ({days} days)\n"
        "Day 1: Place 1, Place 2 (short description)\n"
        "Day 2: Place 3, Place 4 (short description)\n"
        "...\n"
        f"Day {days}: ...\n"
        "Estimated total spend per person: ₹XXXX (approx, within the given budget).\n"
        "Do not add any extra lines after this."
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ],
                # role is optional, but some endpoints expect 'role'
                "role": "user",
            }
        ]
    }

    # ---------- FIRST ATTEMPT USING DEFAULT MODEL_URL ----------
    resp, status = call_generate(MODEL_URL, GEMINI_API_KEY, payload)
    # If we get 404 or model-not-found, attempt discovery and retry
    if status == 404 or (isinstance(resp, requests.Response) and resp.ok is False and "not found" in resp.text.lower()):
        # try to discover a supported model
        picked = discover_and_pick_model(GEMINI_API_KEY)
        if not picked:
            # could not discover any model; return error and the raw response for debugging
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

        # build new URL and retry
        retry_model_url = f"https://generativelanguage.googleapis.com/v1/models/{picked}:generateContent"
        # small pause to be nice to API
        time.sleep(0.5)
        resp2, status2 = call_generate(retry_model_url, GEMINI_API_KEY, payload)

        # handle retry response
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

    # ---------- Otherwise parse the original response ----------
    # If resp is a requests.Response object, parse JSON
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

    # If resp is error dict
    return Response(base_text + f"[Error calling AI API: {resp}]", mimetype="text/plain", status=500)


if __name__ == "__main__":
    # For local testing only
    app.run(host="0.0.0.0", port=5000, debug=True)
