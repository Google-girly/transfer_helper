import json
import os
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)

# Allow your frontend (Node) to call this API
CORS(app, origins=["http://localhost:3000"])

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

@app.get("/schools")
def schools():
    path = os.path.join(BASE_DIR, "school_codes.txt")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)  # expects JSON array of objects
    return jsonify(data)

if __name__ == "__main__":
    app.run(port=8000, debug=True)
