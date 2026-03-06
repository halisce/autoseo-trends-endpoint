from flask import Flask, request, jsonify
from pytrends.request import TrendReq
from datetime import datetime

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
