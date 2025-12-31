import json
import os
import re
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
            from_course = f"{(course_info.get('prefix') or '').strip()} {str(course_info.get('courseNumber') or '').strip()}".strip()
            course_title = course_info.get("courseTitle", "")
            units = course_info.get("minUnits", "N/A")
            department = course_info.get("department", "")

            equivalents = []
            sending_art = (course.get("sendingArticulation") or {})
            for item in sending_art.get("items", []) or []:
                for to_course in item.get("items", []) or []:
                    eq_prefix = (to_course.get("prefix") or "").strip()
                    eq_num = str(to_course.get("courseNumber") or "").strip()
                    eq_title = (to_course.get("courseTitle") or "").strip()
                    label = f"{eq_prefix} {eq_num}".strip()
                    equivalents.append({"course": label, "title": eq_title})

            transfers.append({
                "from_course": from_course,
                "course_title": course_title,
                "units": units,
                "department": department,
                "equivalents": equivalents
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

def normalize(s: str) -> str:
    # Lowercase, trim, collapse whitespace. Also remove punctuation that commonly varies.
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

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

@app.post("/lookup")
def lookup():
    """
    Input:  { "from": "14", "to": "29", "query": "HORT 53" }
    Output: { "query": "...", "matches": [ {from_course, course_title, units, department, matched_equivalent} ... ] }
    """
    body = request.get_json(force=True) or {}
    from_code = str(body.get("from", "")).strip()
    to_code = str(body.get("to", "")).strip()
    query = str(body.get("query", "")).strip()

    if not from_code or not to_code or not query:
        return jsonify({"error": "Missing 'from', 'to', or 'query'"}), 400

    if from_code == to_code:
        return jsonify({"error": "From and To must be different schools"}), 400

    try:
        data = fetch_assist_transfers(from_code, to_code)
        if not data:
            return jsonify({"error": "No data returned from ASSIST for this pair"}), 404

        q = normalize(query)

        matches = []
        for t in data.get("transfers", []):
            for eq in (t.get("equivalents") or []):
                eq_course = normalize(eq.get("course"))
                eq_title = normalize(eq.get("title"))

                # Match if user typed exact course code OR exact title
                if q and (q == eq_course or q == eq_title):
                    matches.append({
                        "from_course": t.get("from_course"),
                        "course_title": t.get("course_title"),
                        "units": t.get("units"),
                        "department": t.get("department"),
                        "matched_equivalent": {
                            "course": eq.get("course"),
                            "title": eq.get("title")
                        }
                    })

        # Also helpful: if user types something like "hort 53" but file has "HORT 53"
        # we already normalized, so exact works.

        return jsonify({
            "query": query,
            "from_code": from_code,
            "to_code": to_code,
            "from_college": data.get("from_college"),
            "to_college": data.get("to_college"),
            "matches_count": len(matches),
            "matches": matches
        })
    except requests.HTTPError as e:
        return jsonify({"error": f"ASSIST API error: {str(e)}"}), 502
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(port=8000, debug=True)
