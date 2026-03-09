from flask import Flask, request, jsonify
from pytrends.request import TrendReq
import csv
import requests
from datetime import datetime

app = Flask(__name__)

# Google Sheet CSV URL
SHEET_URL = "https://docs.google.com/spreadsheets/d/1CRoq2Bym3lnaseml-WQM_S2w_adMRUFcyjadlrEr64w/export?format=csv"


# ---------------------------------------------------------
# Load industries from Google Sheet
# ---------------------------------------------------------
def load_industries():
    try:
        response = requests.get(SHEET_URL)
        response.raise_for_status()

        decoded = response.content.decode("utf-8").splitlines()
        reader = csv.DictReader(decoded)

        industries = {}
        for row in reader:
            if row.get("active", "").strip().lower() == "true":
                de = row["industry"].strip()
                en = row["keyword"].strip()
                industries[de] = en

        return industries

    except Exception as e:
        print("Error loading industries:", e)
        return {}

# ---------------------------------------------------------
# Single keyword route
# ---------------------------------------------------------
@app.route("/trends")
def trends():
    seed = request.args.get("seed")
    if not seed:
        return jsonify({"error": "Missing seed parameter"}), 400

    pytrends = TrendReq(hl="en-US", tz=360)
    pytrends.build_payload([seed], timeframe="now 7-d")

    data = pytrends.interest_over_time()

    if data.empty or seed not in data.columns:
        return jsonify({"error": "No trend data found"}), 404

    score = int(data[seed].iloc[-1])
    timestamp = datetime.utcnow().isoformat()

    return jsonify({
        "keyword": seed,
        "score": score,
        "timestamp": timestamp
    })


# ---------------------------------------------------------
# Multi keyword route (robust version)
# ---------------------------------------------------------
@app.route("/trends/multi")
def trends_multi():
    keywords_param = request.args.get("keywords")
    if not keywords_param:
        return jsonify({"error": "Missing keywords parameter"}), 400

    # User gibt deutsche Branchen ein
    requested = [k.strip() for k in keywords_param.split(",") if k.strip()]

    # Branchen + englische Keywords laden
    industries = load_industries()

    # Ungültige Branchen prüfen
    invalid = [k for k in requested if k not in industries]
    if invalid:
        return jsonify({
            "error": "Invalid industries",
            "invalid": invalid,
            "allowed": list(industries.keys())
        }), 400

    # Englische Keywords extrahieren
    english_keywords = [industries[k] for k in requested]

    pytrends = TrendReq(hl="en-US", tz=360)
    pytrends.build_payload(english_keywords, timeframe="now 7-d")

    data = pytrends.interest_over_time()

    week = datetime.utcnow().strftime("%Y-W%W")
    timestamp = datetime.utcnow().isoformat()

    def classify_strength(score):
        if score < 20:
            return "weak"
        elif score < 60:
            return "medium"
        else:
            return "strong"

    results = []
    errors = []

    # Loop über deutsche Branchen, aber Trends über englische Keywords
    for de_name in requested:
        en_keyword = industries[de_name]

        if en_keyword not in data.columns:
            errors.append({"industry": de_name, "keyword": en_keyword, "error": "No trend data available"})
            continue

        series = data[en_keyword]

        if series.empty:
            errors.append({"industry": de_name, "keyword": en_keyword, "error": "No trend data available"})
            continue

        current = int(series.iloc[-1])
        first = int(series.iloc[0])
        momentum = current - first

        results.append({
            "industry": de_name,
            "keyword": en_keyword,
            "score": current,
            "momentum": momentum,
            "strength": classify_strength(current),
            "week": week,
            "timestamp": timestamp
        })

    results_sorted = sorted(results, key=lambda x: x["score"], reverse=True)

    return jsonify({
        "results": results_sorted,
        "errors": errors,
        "meta": {
            "ranked_by": "score_desc",
            "count": len(results_sorted)
        }
    })


@app.route("/industries")
def industries():
    items = load_industries()
    return jsonify({
        "industries": list(items.keys()),
        "count": len(items)
    })

@app.route("/trends/industry")
def trends_industry():
    name = request.args.get("name")
    if not name:
        return jsonify({"error": "Missing name parameter"}), 400

    industries = load_industries()

    if name not in industries:
        return jsonify({
            "error": "Invalid industry name",
            "allowed": list(industries.keys())
        }), 400

    keyword = industries[name]

    pytrends = TrendReq(hl="en-US", tz=360)
    pytrends.build_payload([keyword], timeframe="now 7-d")

    data = pytrends.interest_over_time()

    if data.empty or keyword not in data.columns:
        return jsonify({"error": "No trend data available"}), 404

    score = int(data[keyword].iloc[-1])
    first = int(data[keyword].iloc[0])
    momentum = score - first

    def classify_strength(score):
        if score < 20:
            return "weak"
        elif score < 60:
            return "medium"
        else:
            return "strong"

    return jsonify({
        "industry": name,
        "keyword": keyword,
        "score": score,
        "momentum": momentum,
        "strength": classify_strength(score),
        "timestamp": datetime.utcnow().isoformat()
    })


# ---------------------------------------------------------
# Root route
# ---------------------------------------------------------
@app.route("/")
def home():
    return jsonify({"status": "API running"})


# ---------------------------------------------------------
# Run app
# ---------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

