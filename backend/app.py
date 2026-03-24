import json
import os
import re
import requests
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend", "public")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")

# Comma-separated list, e.g. "http://localhost:3000,https://your-app.onrender.com"
cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]
CORS(app, origins=cors_origins)

# Cache ASSIST articulation payloads (from/to transfers)
TRANSFERS_CACHE = {}

# Cache transferability (IGETC/CSUGE/CALGETC) lists: key = (institutionId, academicYearId, listType)
GE_CACHE = {}


# ---------------------------
# Utilities
# ---------------------------

def normalize(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

def normalize_course_code(s: str) -> str:
    """
    Normalize course code-ish inputs like:
      "engl1b" -> "ENGL 1B"
      " ENGL   1B " -> "ENGL 1B"
    We keep it simple: uppercase + single spaces.
    """
    s = (s or "").strip().upper()
    s = re.sub(r"\s+", " ", s)
    return s

def is_currently_approved(end_date_str: str) -> bool:
    """
    Same idea as your IGETC.py:
    - endDate missing/null => approved
    - endDate in future => approved
    - endDate in past => not approved
    """
    if not end_date_str:
        return True
    try:
        end_dt = datetime.fromisoformat(end_date_str)
        return end_dt > datetime.utcnow()
    except ValueError:
        return False

def fetch_api_data(url: str) -> dict:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


# ---------------------------
# Schools
# ---------------------------

@app.get("/")
def home():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/results")
def results_page():
    return send_from_directory(FRONTEND_DIR, "results.html")


@app.get("/health")
def health():
    return jsonify({"status": "ok"})

@app.get("/schools")
def schools():
    path = os.path.join(BASE_DIR, "school_codes.txt")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return jsonify(data)


# ---------------------------
# ASSIST articulation (transfers)
# ---------------------------

def fetch_assist_transfers(from_code: str, to_code: str):
    cache_key = f"{from_code}->{to_code}"
    if cache_key in TRANSFERS_CACHE:
        return TRANSFERS_CACHE[cache_key]

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
            course_title = (course_info.get("courseTitle") or "").strip()
            units = course_info.get("minUnits", "N/A")
            department = (course_info.get("department") or "").strip()

            equivalents = []
            sending_art = (course.get("sendingArticulation") or {})
            for item in sending_art.get("items", []) or []:
                for to_course in item.get("items", []) or []:
                    eq_prefix = (to_course.get("prefix") or "").strip()
                    eq_num = str(to_course.get("courseNumber") or "").strip()
                    eq_title = (to_course.get("courseTitle") or "").strip()
                    label = f"{eq_prefix} {eq_num}".strip()
                    if label or eq_title:
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

    TRANSFERS_CACHE[cache_key] = payload
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


# ---------------------------
# GE / IGETC / CALGETC lookup
# ---------------------------

def get_ge_courses(institution_id: int, academic_year_id: int, list_type: str) -> dict:
    """
    Fetch transferability courses (IGETC/CSUGE/CALGETC/etc) for an institution.
    Returns a dict containing:
      - institutionName, academicYear, listType
      - index_by_code: { "ENGL 1B": {transferAreas, isCurrentlyApproved, ...}, ... }
      - index_by_title: { "introduction to literature": {...}, ... }  (optional)
    """
    cache_key = (institution_id, academic_year_id, list_type)
    if cache_key in GE_CACHE:
        return GE_CACHE[cache_key]

    url = (
        "https://www.assist.org/api/transferability/courses"
        f"?institutionId={institution_id}"
        f"&academicYearId={academic_year_id}"
        f"&listType={list_type}"
    )

    data = fetch_api_data(url)

    courses_out = []
    # FIXED: Use "courseInformationList" instead of "courses"
    for c in (data.get("courseInformationList") or []):
        # FIXED: Build course name from identifier and courseTitle
        identifier = (c.get("identifier") or "").strip()
        title = (c.get("courseTitle") or "").strip()
        course_name = f"{identifier} - {title}".strip(" -")
        
        # FIXED: Extract transfer area codes properly
        transfer_areas = [
            a.get("code")
            for a in (c.get("transferAreas") or [])
            if a.get("code")
        ]

        end_date = c.get("endDate")
        courses_out.append({
            "course": course_name,
            "transferAreas": transfer_areas,
            "approvedDate": c.get("beginDate"),
            "approvedTerm": c.get("beginTermCode"),
            "removedDate": end_date,
            "removedTerm": c.get("endTermCode"),
            "isCurrentlyApproved": is_currently_approved(end_date),
        })

    # Build indexes for fast lookup
    index_by_code = {}
    index_by_title = {}

    for item in courses_out:
        full = item["course"]

        # Split "ENGL 1B - Something" into code + title if possible
        code_part = full
        title_part = ""

        if " - " in full:
            code_part, title_part = full.split(" - ", 1)
            code_part = code_part.strip()
            title_part = title_part.strip()

        code_norm = normalize_course_code(code_part)
        if code_norm:
            index_by_code[code_norm] = item

        title_norm = normalize(title_part)
        if title_norm:
            index_by_title[title_norm] = item

        # Also index by full string (sometimes user types entire thing)
        full_norm = normalize(full)
        if full_norm:
            index_by_title[full_norm] = item

    out = {
        "institutionName": data.get("institutionName"),
        "academicYear": (data.get("academicYear") or {}).get("code"),
        "listType": data.get("listType"),
        "index_by_code": index_by_code,
        "index_by_title": index_by_title,
    }

    GE_CACHE[cache_key] = out
    return out


def ge_lookup_for_equivalent(eq_course: str, eq_title: str, institution_id: int, academic_year_id: int, list_type: str):
    """
    Try to find GE/IGETC/CALGETC record for the equivalent course.
    Matches by:
      - course code (e.g. "ENGL 1B")
      - title (e.g. "Introduction to Literature")
    Returns GE record dict or None.
    """
    ge = get_ge_courses(institution_id, academic_year_id, list_type)

    code_norm = normalize_course_code(eq_course)
    title_norm = normalize(eq_title)

    rec = None
    if code_norm and code_norm in ge["index_by_code"]:
        rec = ge["index_by_code"][code_norm]
    elif title_norm and title_norm in ge["index_by_title"]:
        rec = ge["index_by_title"][title_norm]

    return rec


# ---------------------------
# Lookup batch (augment with GE/IGETC/CALGETC areas)
# ---------------------------

def find_matches_in_payload(payload: dict, query: str, ge_academic_year_id: int, ge_list_type: str):
    """
    For a given query, find articulation matches (equivalents),
    and attach GE/IGETC/CALGETC info for the matched equivalent course.
    """
    q_norm = normalize(query)
    q_code_norm = normalize_course_code(query)

    matches = []
    if not query.strip():
        return matches

    from_inst_id = int(payload["from_code"])  # using from_code as institutionId

    for t in payload.get("transfers", []):
        for eq in (t.get("equivalents") or []):
            eq_course = (eq.get("course") or "").strip()
            eq_title = (eq.get("title") or "").strip()

            eq_course_norm = normalize_course_code(eq_course)
            eq_title_norm = normalize(eq_title)

            # Match user input exactly (case-insensitive) by:
            # - code OR title
            is_match = False
            if q_code_norm and q_code_norm == eq_course_norm:
                is_match = True
            elif q_norm and (q_norm == eq_title_norm or q_norm == normalize(eq_course) or q_norm == normalize(f"{eq_course} - {eq_title}")):
                is_match = True

            if not is_match:
                continue

            # Attach GE record if found
            ge_rec = None
            try:
                ge_rec = ge_lookup_for_equivalent(
                    eq_course=eq_course,
                    eq_title=eq_title,
                    institution_id=from_inst_id,
                    academic_year_id=ge_academic_year_id,
                    list_type=ge_list_type
                )
            except Exception:
                # If GE lookup fails for this institution/list, we still return the match without GE info
                ge_rec = None

            matches.append({
                "from_course": t.get("from_course"),
                "course_title": t.get("course_title"),
                "units": t.get("units"),
                "department": t.get("department"),
                "matched_equivalent": {
                    "course": eq_course,
                    "title": eq_title
                },
                "ge": None if not ge_rec else {
                    "transferAreas": ge_rec.get("transferAreas") or [],
                    "isCurrentlyApproved": bool(ge_rec.get("isCurrentlyApproved")),
                    "approvedTerm": ge_rec.get("approvedTerm"),
                    "removedTerm": ge_rec.get("removedTerm"),
                    "approvedDate": ge_rec.get("approvedDate"),
                    "removedDate": ge_rec.get("removedDate"),
                }
            })

    return matches


@app.post("/lookup_batch")
def lookup_batch():
    """
    Input:
      {
        "from": "133",
        "to": "29",
        "queries": ["ENGL 1B", "Soil Science and Management"],

        // optional:
        "geAcademicYearId": 76,
        "geListType": "CALGETC"  // can be "IGETC", "CSUGE", "CALGETC", etc.
      }
    """
    body = request.get_json(force=True) or {}

    from_code = str(body.get("from", "")).strip()
    to_code = str(body.get("to", "")).strip()
    queries = body.get("queries", [])

    ge_academic_year_id = int(body.get("geAcademicYearId", 76))
    ge_list_type = str(body.get("geListType", "CALGETC")).strip() or "CALGETC"  # Changed default to CALGETC

    if not from_code or not to_code or not isinstance(queries, list):
        return jsonify({"error": "Missing 'from', 'to', or invalid 'queries' list"}), 400
    if from_code == to_code:
        return jsonify({"error": "From and To must be different schools"}), 400

    cleaned = []
    for q in queries:
        q = str(q or "").strip()
        if q:
            cleaned.append(q)
    cleaned = cleaned[:50]

    try:
        payload = fetch_assist_transfers(from_code, to_code)
        if not payload:
            return jsonify({"error": "No data returned from ASSIST for this pair"}), 404

        results = []
        for q in cleaned:
            matches = find_matches_in_payload(payload, q, ge_academic_year_id, ge_list_type)
            results.append({
                "query": q,
                "matches_count": len(matches),
                "matches": matches
            })

        return jsonify({
            "from_code": from_code,
            "to_code": to_code,
            "from_college": payload.get("from_college"),
            "to_college": payload.get("to_college"),
            "academic_year": payload.get("academic_year"),
            "geListType": ge_list_type,
            "geAcademicYearId": ge_academic_year_id,
            "results": results
        })

    except requests.HTTPError as e:
        return jsonify({"error": f"ASSIST API error: {str(e)}"}), 502
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True)