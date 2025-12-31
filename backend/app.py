import json
import os
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app, origins=["http://localhost:3000"])

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Simple in-memory cache so you don't hammer the API while testing
CACHE = {}

@app.get("/schools")
def schools():
    path = os.path.join(BASE_DIR, "school_codes.txt")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return jsonify(data)

def fetch_assist_transfers(from_code: str, to_code: str):
    cache_key = f"{from_code}->{to_code}"
    if cache_key in CACHE:
        return CACHE[cache_key]

    url = f"https://assist.org/api/articulation/Agreements?Key=75/{from_code}/to/{to_code}/AllPrefixes"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    raw = r.json()

    if not raw or "result" not in raw:
        return None

    result = raw["result"]

    # These come back as JSON strings
    receiving = json.loads(result["receivingInstitution"])
    sending = json.loads(result["sendingInstitution"])
    academic_year = json.loads(result["academicYear"])
    articulations = json.loads(result["articulations"])

    transfers = []

    for dept in articulations:
        for course in dept.get("articulations", []):
            if course.get("type") != "Course":
                continue

            course_info = course.get("course", {}) or {}
            from_course = f"{course_info.get('prefix', '').strip()} {str(course_info.get('courseNumber', '')).strip()}".strip()
            course_title = course_info.get("courseTitle", "")
            units = course_info.get("minUnits", "N/A")
            department = course_info.get("department", "")

            equivalents = []
            sending_art = (course.get("sendingArticulation") or {})
            for item in sending_art.get("items", []) or []:
                for to_course in item.get("items", []) or []:
                    eq_prefix = (to_course.get("prefix") or "").strip()
                    eq_num = str(to_course.get("courseNumber") or "").strip()
                    eq_title = to_course.get("courseTitle") or ""
                    label = f"{eq_prefix} {eq_num}".strip()
                    equivalents.append({"course": label, "title": eq_title})

            transfers.append({
                "from_course": from_course,
                "course_title": course_title,
                "units": units,
                "department": department,
                "equivalents": equivalents  # list of {course, title}
            })

    payload = {
        "from_code": from_code,
        "to_code": to_code,
        "from_college": (sending.get("names") or [{}])[0].get("name"),
        "to_college": (receiving.get("names") or [{}])[0].get("name"),
        "academic_year": academic_year.get("code"),
        "transfers": transfers
    }

    CACHE[cache_key] = payload
    return payload

@app.post("/transfers")
def transfers():
    body = request.get_json(force=True) or {}
    from_code = str(body.get("from", "")).strip()
    to_code = str(body.get("to", "")).strip()

    if not from_code or not to_code:
        return jsonify({"error": "Missing 'from' or 'to' code"}), 400

    if from_code == to_code:
        return jsonify({"error": "From and To must be different schools"}), 400

    try:
        data = fetch_assist_transfers(from_code, to_code)
        if not data:
            return jsonify({"error": "No data returned from ASSIST for this pair"}), 404
        return jsonify(data)
    except requests.HTTPError as e:
        return jsonify({"error": f"ASSIST API error: {str(e)}"}), 502
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(port=8000, debug=True)
