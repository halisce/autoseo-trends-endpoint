from flask import Flask, request, jsonify
from pytrends.request import TrendReq
from datetime import datetime
import csv
import requests

# Google Sheet URL
SHEET_URL = "https://docs.google.com/spreadsheets/d/1CRoq2Bym3lnaseml-WQM_S2w_adMRUFcyjadlrEr64w/export?format=csv"

# Load industries from Google Sheet
def load_industries():
    response = requests.get(SHEET_URL)
    response.raise_for_status()

    industries = []
    decoded = response.content.decode("utf-8").splitlines()
    reader = csv.DictReader(decoded)

    for row in reader:
        if row.get("active", "").strip().lower() == "true":
            industries.append(row["industry"].strip())

    return industries


app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({"status": "ok", "message": "AutoSEO Trends API is running"})


@app.route("/trends")
def trends():
    seed = request.args.get("seed")
    if not seed:
        return jsonify({"error": "Missing seed parameter"}), 400

    pytrends = TrendReq(hl='en-US', tz=360)
    pytrends.build_payload([seed], timeframe='now 7-d')

    data = pytrends.interest_over_time()

    if data.empty:
        return jsonify({"error": "No trend data found"}), 404

    score = int(data[seed].iloc[-1])
    week = datetime.utcnow().strftime("%Y-W%W")

    return jsonify({
        "keyword": seed,
        "score": score,
        "seed": seed,
        "week": week,
        "timestamp": datetime.utcnow().isoformat()
    })


# 👉 HIER kommt als Nächstes die Multi‑Keyword‑Route hin
# @app.route("/trends/multi")
# def trends_multi():
@app.route("/trends/multi")
@app.route("/trends/multi")
def trends_multi():
    keywords_param = request.args.get("keywords")
    if not keywords_param:
        return jsonify({"error": "Missing keywords parameter"}), 400

    requested = [k.strip() for k in keywords_param.split(",") if k.strip()]

    allowed = load_industries()
    invalid = [k for k in requested if k not in allowed]
    if invalid:
        return jsonify({
            "error": "Invalid keywords",
            "invalid": invalid,
            "allowed_keywords": allowed
        }), 400

    pytrends = TrendReq(hl='en-US', tz=360)
    pytrends.build_payload(requested, timeframe='now 7-d')

    data = pytrends.interest_over_time()
    if data.empty:
        return jsonify({"error": "No trend data found"}), 404

    week = datetime.utcnow().strftime("%Y-W%W")
    timestamp = datetime.utcnow().isoformat()

    def classify_strength(score: int) -> str:
        if score < 20:
            return "weak"
        elif score < 60:
            return "medium"
        else:
            return "strong"

    results = []
    for kw in requested:
        if kw in data.columns:
            series = data[kw]
            current = int(series.iloc[-1])
            first = int(series.iloc[0])
            momentum = current - first  # positive = steigt, negativ = fällt

            results.append({
                "keyword": kw,
                "score": current,
                "momentum": momentum,
                "strength": classify_strength(current),
                "week": week,
                "timestamp": timestamp
            })

    # Ranking nach aktuellem Score (absteigend)
    results_sorted = sorted(results, key=lambda x: x["score"], reverse=True)

    return jsonify({
        "results": results_sorted,
        "meta": {
            "ranked_by": "score_desc",
            "count": len(results_sorted)
        }
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
