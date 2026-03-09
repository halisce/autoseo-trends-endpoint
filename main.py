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

@app.route("/trends/all")
def trends_all():
    industries = load_industries()

    if not industries:
        return jsonify({"error": "No industries loaded"}), 500

    # Englische Keywords extrahieren
    english_keywords = list(industries.values())

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

    # Loop über alle Branchen
    for de_name, en_keyword in industries.items():

        if en_keyword not in data.columns:
            errors.append({
                "industry": de_name,
                "keyword": en_keyword,
                "error": "No trend data available"
            })
            continue

        series = data[en_keyword]

        if series.empty:
            errors.append({
                "industry": de_name,
                "keyword": en_keyword,
                "error": "No trend data available"
            })
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

    # Ranking nach Score
    results_sorted = sorted(results, key=lambda x: x["score"], reverse=True)

    return jsonify({
        "results": results_sorted,
        "errors": errors,
        "meta": {
            "ranked_by": "score_desc",
            "count": len(results_sorted)
        }
    })

@app.route("/briefing/industry")
def briefing_industry():
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

    # Trenddaten holen
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

    strength = classify_strength(score)

    # SEO Briefing generieren
    briefing = {
        "industry": name,
        "keyword": keyword,
        "trend": {
            "score": score,
            "momentum": momentum,
            "strength": strength
        },
        "search_intent": "informational",
        "primary_keyword": keyword,
        "secondary_keywords": [
            f"{keyword} market",
            f"{keyword} trends",
            f"{keyword} analysis",
            f"{keyword} forecast"
        ],
        "long_tail_keywords": [
            f"{keyword} growth opportunities",
            f"{keyword} challenges",
            f"{keyword} innovations",
            f"{keyword} market size"
        ],
        "outline": {
            "H1": f"{keyword.capitalize()} — Market Trends & Insights",
            "H2": [
                "Industry Overview",
                "Current Market Trends",
                "Growth Drivers",
                "Challenges & Risks",
                "Future Outlook",
                "Key Opportunities"
            ]
        },
        "recommendations": {
            "tone": "professional, analytical",
            "content_length": "1200–1800 words",
            "target_audience": "business decision makers, analysts, investors",
            "cta": "Download full market report"
        }
    }

    return jsonify(briefing)

@app.route("/briefing/all")
def briefing_all():
    industries = load_industries()

    if not industries:
        return jsonify({"error": "No industries loaded"}), 500

    results = []
    errors = []

    for de_name, en_keyword in industries.items():

        try:
            # Trenddaten holen
            pytrends = TrendReq(hl="en-US", tz=360)
            pytrends.build_payload([en_keyword], timeframe="now 7-d")
            data = pytrends.interest_over_time()

            if data.empty or en_keyword not in data.columns:
                errors.append({
                    "industry": de_name,
                    "keyword": en_keyword,
                    "error": "No trend data available"
                })
                continue

            score = int(data[en_keyword].iloc[-1])
            first = int(data[en_keyword].iloc[0])
            momentum = score - first

            def classify_strength(score):
                if score < 20:
                    return "weak"
                elif score < 60:
                    return "medium"
                else:
                    return "strong"

            strength = classify_strength(score)

            # SEO Briefing generieren
            briefing = {
                "industry": de_name,
                "keyword": en_keyword,
                "trend": {
                    "score": score,
                    "momentum": momentum,
                    "strength": strength
                },
                "search_intent": "informational",
                "primary_keyword": en_keyword,
                "secondary_keywords": [
                    f"{en_keyword} market",
                    f"{en_keyword} trends",
                    f"{en_keyword} analysis",
                    f"{en_keyword} forecast"
                ],
                "long_tail_keywords": [
                    f"{en_keyword} growth opportunities",
                    f"{en_keyword} challenges",
                    f"{en_keyword} innovations",
                    f"{en_keyword} market size"
                ],
                "outline": {
                    "H1": f"{en_keyword.capitalize()} — Market Trends & Insights",
                    "H2": [
                        "Industry Overview",
                        "Current Market Trends",
                        "Growth Drivers",
                        "Challenges & Risks",
                        "Future Outlook",
                        "Key Opportunities"
                    ]
                },
                "recommendations": {
                    "tone": "professional, analytical",
                    "content_length": "1200–1800 words",
                    "target_audience": "business decision makers, analysts, investors",
                    "cta": "Download full market report"
                }
            }

            results.append(briefing)

        except Exception as e:
            errors.append({
                "industry": de_name,
                "keyword": en_keyword,
                "error": str(e)
            })

    return jsonify({
        "briefings": results,
        "errors": errors,
        "meta": {
            "count": len(results),
            "errors_count": len(errors)
        }
    })

@app.route("/article/industry")
def article_industry():
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

    # Trenddaten holen
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

    strength = classify_strength(score)

    # Professioneller Blogartikel (generisch, ohne Zahlen)
    title = f"{keyword.capitalize()} Industry: Current Trends and Market Outlook"

    meta_description = (
        f"An analytical overview of the {keyword} industry, including current trends, "
        f"market drivers, challenges, and future outlook."
    )

    introduction = (
        f"The {keyword} industry continues to play a significant role across multiple sectors. "
        f"As markets evolve and new technologies emerge, organizations operating in this field "
        f"must stay informed about current developments and strategic opportunities. "
        f"This article provides a professional overview of the latest trends and insights shaping the industry."
    )

    trend_section = (
        f"Recent trend data indicates a {strength} level of interest in the {keyword} sector. "
        f"The current trend score suggests stable engagement, while the momentum value highlights "
        f"how interest has shifted over the past week. Although these indicators do not represent "
        f"market size or financial performance, they offer a useful perspective on general attention "
        f"and emerging discussions within the industry."
    )

    drivers_section = (
        f"The {keyword} industry is influenced by a variety of market drivers. "
        f"Technological advancements continue to shape operational processes and product innovation. "
        f"Shifts in consumer expectations, regulatory developments, and sustainability requirements "
        f"also contribute to the evolving landscape. Organizations that adapt proactively to these drivers "
        f"are better positioned to maintain competitiveness."
    )

    challenges_section = (
        f"Despite ongoing progress, the industry faces several challenges. "
        f"Supply chain uncertainties, geopolitical factors, and increasing cost pressures "
        f"can create operational constraints. Additionally, rapid technological change requires "
        f"continuous investment in skills and infrastructure. Addressing these challenges effectively "
        f"is essential for long‑term stability."
    )

    outlook_section = (
        f"The future outlook for the {keyword} industry remains positive, with continued innovation "
        f"expected to drive new opportunities. Organizations that prioritize digital transformation, "
        f"strategic partnerships, and sustainable practices are likely to benefit from emerging trends. "
        f"While uncertainties remain, the sector shows potential for steady development."
    )

    opportunities_section = (
        f"Key opportunities in the {keyword} sector include expanding into new markets, "
        f"leveraging data‑driven decision‑making, and adopting advanced technologies. "
        f"Companies that align their strategies with evolving customer needs and regulatory expectations "
        * "can strengthen their competitive position and unlock additional growth potential."
    )

    conclusion = (
        f"In summary, the {keyword} industry continues to evolve in response to technological, "
        f"economic, and regulatory developments. By understanding current trends and preparing for "
        f"future challenges, organizations can position themselves for sustainable success."
    )

    cta = "For a deeper analysis and additional insights, download the full market report."

    article = {
        "title": title,
        "meta_description": meta_description,
        "industry": name,
        "keyword": keyword,
        "trend": {
            "score": score,
            "momentum": momentum,
            "strength": strength
        },
        "article": {
            "introduction": introduction,
            "sections": {
                "Industry Overview": introduction,
                "Trend Analysis": trend_section,
                "Market Drivers": drivers_section,
                "Challenges & Risks": challenges_section,
                "Future Outlook": outlook_section,
                "Key Opportunities": opportunities_section
            },
            "conclusion": conclusion,
            "cta": cta
        }
    }

    return jsonify(article)

@app.route("/article/top")
def article_top():
    industries = load_industries()
    if not industries:
        return jsonify({"error": "No industries loaded"}), 500

    # Trenddaten für alle Branchen holen
    english_keywords = list(industries.values())
    pytrends = TrendReq(hl="en-US", tz=360)
    pytrends.build_payload(english_keywords, timeframe="now 7-d")
    data = pytrends.interest_over_time()

    if data.empty:
        return jsonify({"error": "No trend data available"}), 500

    # Top-Branche bestimmen
    top_industry = None
    top_keyword = None
    top_score = -1
    top_first = None

    for de_name, en_keyword in industries.items():
        if en_keyword not in data.columns:
            continue

        series = data[en_keyword]
        if series.empty:
            continue

        current = int(series.iloc[-1])
        first = int(series.iloc[0])

        if current > top_score:
            top_score = current
            top_first = first
            top_industry = de_name
            top_keyword = en_keyword

    if not top_industry:
        return jsonify({"error": "No valid trend data"}), 500

    momentum = top_score - top_first

    def classify_strength(score):
        if score < 20:
            return "weak"
        elif score < 60:
            return "medium"
        else:
            return "strong"

    strength = classify_strength(top_score)

    # Artikel generieren
    keyword = top_keyword
    name = top_industry

    title = f"{keyword.capitalize()} Industry: Current Trends and Market Outlook"

    meta_description = (
        f"A professional overview of the {keyword} industry, focusing on automation, "
        f"current trends, key drivers, challenges and future outlook."
    )

    introduction = (
        f"The {keyword} industry is undergoing continuous transformation as organizations "
        f"seek to improve efficiency, reliability and competitiveness. Automation plays a "
        f"central role in this development, influencing production, operations and strategic "
        f"decision‑making. This article provides a professional overview of current trends "
        f"and the evolving role of automation in the sector."
    )

    trend_section = (
        f"Recent trend indicators point to a {strength} level of interest in the {keyword} industry. "
        f"While these values do not represent market size or financial performance, they offer "
        f"useful insight into the level of attention and discussion surrounding the sector. "
        f"The observed momentum highlights how interest has shifted over the recent period and "
        f"can serve as a signal for emerging topics and strategic priorities."
    )

    drivers_section = (
        f"Automation in the {keyword} industry is driven by several key factors. "
        f"Technological innovation enables more efficient processes, higher quality standards "
        f"and improved transparency across operations. At the same time, changing customer "
        f"expectations, regulatory requirements and competitive pressure encourage organizations "
        f"to modernize their systems and adopt data‑driven approaches."
    )

    challenges_section = (
        f"Despite its potential, the adoption of automation also presents challenges. "
        f"Integrating new technologies into existing infrastructures can be complex and resource‑intensive. "
        f"Organizations must address skills gaps, manage change within their workforce and ensure "
        f"that security and compliance requirements are met. A structured, long‑term approach is "
        f"essential to realizing the full benefits of automation."
    )

    outlook_section = (
        f"The outlook for automation in the {keyword} industry remains positive. "
        f"As digital tools, analytics and intelligent systems continue to mature, "
        f"organizations will gain new opportunities to optimize operations and develop innovative services. "
        f"Those that invest in scalable architectures, partnerships and continuous learning are likely "
        f"to be better positioned for future developments."
    )

    opportunities_section = (
        f"Key opportunities include the automation of repetitive tasks, enhanced monitoring and control, "
        f"and the use of data to support strategic decisions. By aligning automation initiatives with "
        f"clear business objectives, organizations in the {keyword} sector can improve efficiency, "
        f"reduce operational risk and create a more resilient foundation for growth."
    )

    conclusion = (
        f"In summary, automation is a central theme in the ongoing evolution of the {keyword} industry. "
        f"By understanding current trends, addressing implementation challenges and focusing on long‑term "
        f"value creation, organizations can strengthen their position in a dynamic and competitive environment."
    )

    # Social-Media-Post
    social_post = (
        f"📈 Weekly Trend Insight: {name}\n\n"
        f"This week's strongest sector is the **{name}** industry. "
        f"Automation, digital transformation and evolving market dynamics continue to shape its direction.\n\n"
        f"Read the full analysis below."
    )

    # Artikel als EIN Textblock
    article_text = (
        f"{title}\n\n"
        f"{introduction}\n\n"
        f"---\n\n"
        f"## Trend Analysis\n{trend_section}\n\n"
        f"## Automation Drivers\n{drivers_section}\n\n"
        f"## Challenges and Implementation Risks\n{challenges_section}\n\n"
        f"## Future Outlook\n{outlook_section}\n\n"
        f"## Key Opportunities\n{opportunities_section}\n\n"
        f"---\n\n"
        f"{conclusion}\n\n"
        f"**{meta_description}**"
    )

    return jsonify({
        "industry": name,
        "keyword": keyword,
        "title": title,
        "meta_description": meta_description,
        "social_post": social_post,
        "article_text": article_text,
        "trend_score": top_score,
        "trend_momentum": momentum,
        "trend_strength": strength,
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

