from flask import Flask, request, jsonify, Response
import requests
import json
import uuid
import time
import random
import threading
import io
import csv
import html
from collections import defaultdict

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

API_URL = "https://api.deepai.org/hacking_is_a_serious_crime"
API_KEY = "tryit-71209460785-0d83ccc5af9bd7a408f4328b46b4d79egfr"
SECRET_KEY = "734401"

session_id = str(uuid.uuid4())

headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*",
    "api-key": API_KEY,
    "Origin": "https://deepai.org"
}

BUILTIN_TOPICS = [
    "science", "history", "geography", "mathematics", "space",
    "technology", "sports", "movies", "music", "animals",
    "human body", "world capitals", "inventions", "literature", "computers",
    "video games", "food", "oceans", "weather", "famous people",
    "flags", "mythology", "dinosaurs", "cars", "art"
]

DIFFICULTY_LEVELS = ["easy", "medium", "hard"]

DIFFICULTY_SECONDS = {"easy": 20, "medium": 30, "hard": 45}

MAX_COUNT = 3
RATE_LIMIT_SECONDS = 2

SYSTEM_ROLE = (
    "You are QuizGen AI, a quiz generator bot. "
    "The user will give you any topic, a difficulty level, and a number of questions. "
    "Generate multiple-choice quiz questions. Respond ONLY with valid JSON, no extra text. "
    "For one question use exactly this format: "
    '{"questions": [{"question": "...", "options": ["A) ...", "B) ...", "C) ...", "D) ..."], '
    '"correct_option": "A", "explanation": "..."}]} '
    "correct_option must be a single letter A, B, C or D matching the right answer. "
    "Never repeat questions from earlier in the conversation."
)

chat_history = [
    {"role": "system", "content": SYSTEM_ROLE},
    {"role": "assistant", "content": "Ready. Send a topic and I will generate quiz questions."}
]

history_lock = threading.Lock()
history_store = []
banned_set = set()
ip_stats = defaultdict(lambda: {"requests": 0, "last_seen": "", "user_agent": ""})
rate_map = defaultdict(float)
admin_lock = threading.Lock()
stats_lock = threading.Lock()

STATS = {
    "total": 0, "success": 0, "errors": 0, "blocked": 0,
    "start_time": time.time(),
    "questions_generated": 0,
    "difficulty_counts": defaultdict(int),
    "topic_counts": defaultdict(int),
    "random_picks": 0
}

PAGE_STYLE = """
<style>
 *{box-sizing:border-box;}
 body{font-family:'Segoe UI',Arial,sans-serif;background:#0b0d20;color:#e8e9f3;margin:0;padding:30px 4vw;min-height:100vh;
      background-image:radial-gradient(circle at 15% 20%, rgba(124,108,255,.22), transparent 40%),
                       radial-gradient(circle at 85% 75%, rgba(64,224,208,.15), transparent 45%);
      background-attachment:fixed;animation:bgShift 14s ease-in-out infinite alternate;}
 @keyframes bgShift{0%{background-color:#0b0d20;}100%{background-color:#141032;}}
 @keyframes fadeIn{from{opacity:0;transform:translateY(22px);}to{opacity:1;transform:translateY(0);}}
 @keyframes glowPulse{0%,100%{box-shadow:0 0 14px rgba(124,108,255,.45);}50%{box-shadow:0 0 32px rgba(124,108,255,.85);}}
 @keyframes floatIn{from{opacity:0;transform:scale(.94);}to{opacity:1;transform:scale(1);}}
 @keyframes spin{to{transform:rotate(360deg);}}
 @keyframes shimmer{0%{background-position:-400px 0;}100%{background-position:400px 0;}}
 @keyframes bounce{0%,100%{transform:translateY(0);}50%{transform:translateY(-6px);}}
 h1{color:#9d8cff;margin:4px 0 22px;font-size:1.9em;animation:fadeIn .6s ease both;text-shadow:0 0 18px rgba(124,108,255,.5);}
 h2{color:#c8bfff;margin:4px 0 14px;font-size:1.15em;animation:fadeIn .7s ease both;}
 .card{background:linear-gradient(145deg, rgba(30,34,72,.9), rgba(22,25,58,.9));
       border:1px solid rgba(124,108,255,.28);border-radius:16px;padding:18px 22px;margin:16px 0;
       box-shadow:0 8px 26px rgba(0,0,0,.45);animation:floatIn .5s ease both;transition:transform .25s ease, box-shadow .25s ease;}
 .card:hover{transform:translateY(-3px);box-shadow:0 14px 34px rgba(124,108,255,.25);border-color:rgba(124,108,255,.55);}
 .card:nth-child(2){animation-delay:.08s;} .card:nth-child(3){animation-delay:.16s;} .card:nth-child(4){animation-delay:.24s;}
 .kv{padding:8px 0;border-bottom:1px solid rgba(70,76,140,.4);word-break:break-word;font-size:14.5px;animation:fadeIn .8s ease both;}
 .kv:last-child{border-bottom:none;}
 .kv b{color:#9d8cff;}
 pre{background:#07081a;padding:12px;border-radius:10px;overflow-x:auto;color:#9ee6a0;font-size:13px;white-space:pre-wrap;
     border:1px solid rgba(158,230,160,.15);}
 table{width:100%;border-collapse:collapse;margin-top:12px;}
 th{color:#9d8cff;text-transform:uppercase;font-size:11.5px;letter-spacing:1px;padding:12px 10px;border-bottom:2px solid rgba(124,108,255,.4);text-align:left;}
 td{padding:11px 10px;border-bottom:1px solid rgba(70,76,140,.4);font-size:14px;vertical-align:middle;}
 tr{transition:background .2s ease;} tr:hover{background:rgba(124,108,255,.09);}
 .badge{display:inline-block;background:rgba(124,108,255,.16);color:#c8bfff;border:1px solid rgba(124,108,255,.35);
        border-radius:20px;padding:4px 13px;margin:4px 5px 4px 0;font-size:13px;transition:all .2s ease;}
 .badge:hover{background:rgba(124,108,255,.35);transform:translateY(-2px);}
 .ok{color:#9ee6a0;font-weight:bold;} .err{color:#ff8a8a;font-weight:bold;}
 .banned{color:#ff8a8a;font-weight:bold;text-shadow:0 0 8px rgba(255,138,138,.6);}
 .active{color:#9ee6a0;font-weight:bold;text-shadow:0 0 8px rgba(158,230,160,.6);}
 .btn{display:inline-block;border-radius:10px;padding:8px 16px;text-decoration:none;font-size:13px;margin:4px 6px 4px 0;
      border:1px solid transparent;transition:all .2s ease;animation:fadeIn .6s ease both;}
 .btn:hover{transform:translateY(-2px) scale(1.04);}
 .btn-ban{background:linear-gradient(135deg,#a63d4d,#7a2735);color:#ffd9d9;border-color:#c4586a;}
 .btn-ban:hover{box-shadow:0 0 16px rgba(255,100,120,.6);}
 .btn-unban{background:linear-gradient(135deg,#2f8a4d,#1f5c34);color:#d9ffe3;border-color:#4dbd74;}
 .btn-unban:hover{box-shadow:0 0 16px rgba(90,230,140,.6);}
 .btn-warn{background:linear-gradient(135deg,#8a6a2f,#5c451c);color:#ffeec9;border-color:#bd9a4d;}
 .btn-warn:hover{box-shadow:0 0 16px rgba(255,210,110,.55);}
 .btn-blue{background:linear-gradient(135deg,#3d6ea6,#27496f);color:#d9edff;border-color:#5d94c4;}
 .btn-blue:hover{box-shadow:0 0 16px rgba(110,170,255,.55);}
 code{color:#ffd479;background:rgba(255,212,121,.1);padding:2px 7px;border-radius:6px;font-size:13.5px;}
 a{color:#9d8cff;}
 .top{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:20px;}
 .num{font-size:1.6em;color:#7ee0ff;font-weight:bold;text-shadow:0 0 14px rgba(126,224,255,.6);}
 .grid{display:flex;flex-wrap:wrap;gap:14px;}
 .grid .card{flex:1 1 180px;min-width:180px;text-align:center;animation:floatIn .6s ease both;}
 .pulse{animation:glowPulse 2.4s ease-in-out infinite;}
 .note{font-size:12.5px;color:#8b90b8;margin-top:10px;}
</style>
"""


def esc(value):
    return html.escape(str(value))


def pretty(value):
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)


def page(title, body):
    return Response(PAGE_STYLE + f"<h1>{esc(title)}</h1>{body}", mimetype="text/html")


def fake_404():
    return page("404 Not Found",
                "<div class='card'><p>The requested URL was not found on the server. "
                "If you entered the URL manually please check your spelling and try again.</p></div>"), 404


def get_client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.headers.get("X-Real-IP") or request.remote_addr or "unknown"


def check_rate_limit(user_ip):
    now = time.time()
    with stats_lock:
        if now - rate_map[user_ip] < RATE_LIMIT_SECONDS:
            return False
        rate_map[user_ip] = now
    return True


def parse_quiz(raw_text):
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        parsed = json.loads(text[start:end + 1])
    except Exception:
        return None
    items = parsed.get("questions") or [parsed]
    valid = []
    for item in items:
        question = item.get("question", "")
        options = item.get("options", [])
        correct = str(item.get("correct_option", "")).strip().upper()[:1]
        explanation = item.get("explanation", "")
        if question and options and correct in ["A", "B", "C", "D"]:
            valid.append({
                "question": question,
                "options": options,
                "correct_option": correct,
                "explanation": explanation
            })
    return valid if valid else None


def build_quiz_response(topic, difficulty, count, raw_reply):
    parsed = parse_quiz(raw_reply)
    seconds = DIFFICULTY_SECONDS.get(difficulty, 30)
    if parsed:
        questions = parsed[:count]
        for i in range(len(questions), count):
            questions.append({"question": "Not generated", "options": [],
                              "correct_option": "", "explanation": ""})
        for q in questions:
            if q["correct_option"]:
                q["seconds_to_answer"] = seconds
        return {
            "Topic": topic,
            "Difficulty": difficulty,
            "Total_Questions": len([q for q in questions if q["correct_option"]]),
            "Questions": questions,
            "Status": "success"
        }
    return {
        "Topic": topic,
        "Difficulty": difficulty,
        "Total_Questions": 0,
        "Questions": [{"question": raw_reply, "options": [],
                       "correct_option": "", "explanation": ""}],
        "Status": "success",
        "Note": "raw_response_returned_due_to_parse_issue"
    }


def touch_ip(user_ip):
    with admin_lock:
        entry = ip_stats[user_ip]
        entry["requests"] += 1
        entry["last_seen"] = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        ua = request.headers.get("User-Agent", "")
        if ua:
            entry["user_agent"] = ua


def log_request(user_ip, endpoint, req_data, resp_data, status_code, duration):
    with history_lock:
        history_store.append({
            "id": len(history_store) + 1,
            "ip": user_ip,
            "endpoint": endpoint,
            "time": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
            "request": req_data,
            "response": resp_data,
            "status_code": status_code,
            "duration_seconds": round(duration, 3)
        })
    touch_ip(user_ip)


def generate_quiz(topic, difficulty, count):
    prompt = (f"Generate {count} unique quiz question(s) about: {topic}. "
              f"Difficulty level: {difficulty}. "
              f'Respond only with JSON: {{"questions": [{{"question": "...", '
              f'"options": ["A) ...", "B) ...", "C) ...", "D) ..."], '
              f'"correct_option": "A", "explanation": "..."}}]}}')
    chat_history.append({"role": "user", "content": prompt})
    payload = {
        "chat_style": "chat",
        "chatHistory": json.dumps(chat_history),
        "model": "standard",
        "session_uuid": session_id,
        "hacker_is_stinky": "very_stinky",
        "enabled_tools": json.dumps([])
    }
    try:
        response = requests.post(API_URL, data=payload, headers=headers, timeout=60)
        raw_text = response.text.strip()
        try:
            data = response.json()
            reply = data.get("output") or data.get("response") or data.get("text") or raw_text
        except Exception:
            reply = raw_text
        chat_history.append({"role": "assistant", "content": reply})
        if len(chat_history) > 40:
            del chat_history[2:len(chat_history) - 20]
        return reply, None
    except Exception as e:
        return None, str(e)


# ===================== PUBLIC PAGES =====================

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "Service": "QuizGen AI - Telegram Quiz Generator API",
        "Version": "6.0",
        "Endpoints": {
            "/quiz": "GET /quiz?topic=<anything> - quiz JSON (topic=random picks from 25 built-in topics)",
            "/categories": "GET /categories - list all built-in topics and difficulty levels",
            "/stats": "GET /stats - live server statistics dashboard",
            "/health": "GET /health - quick health check",
            "/docs": "GET /docs - full API documentation (HTML page)"
        },
        "Format": "JSON"
    })


@app.route("/quiz", methods=["GET"])
def quiz():
    start = time.time()
    user_ip = get_client_ip()

    with admin_lock:
        is_banned = user_ip in banned_set
    if is_banned:
        with stats_lock:
            STATS["total"] += 1
            STATS["blocked"] += 1
        result = {"Error": "Access denied", "Status": "error"}
        log_request(user_ip, "/quiz?ip_mode", {"ip": user_ip}, result, 403, time.time() - start)
        return jsonify(result), 403

    if not check_rate_limit(user_ip):
        result = {"Error": "Rate limit: wait 2 seconds between requests", "Status": "error"}
        return jsonify(result), 429

    topic = request.args.get("topic", "").strip().lower()
    difficulty = request.args.get("difficulty", "medium").strip().lower()
    count_param = request.args.get("count", "1").strip()
    shuffle = request.args.get("shuffle", "false").strip().lower() == "true"

    if not topic:
        result = {
            "Error": "Query parameter 'topic' is required",
            "Example": "/quiz?topic=anything or /quiz?topic=random&difficulty=hard&count=3",
            "Status": "error"
        }
        log_request(user_ip, "/quiz", {}, result, 400, time.time() - start)
        return jsonify(result), 400

    if difficulty not in DIFFICULTY_LEVELS:
        result = {"Error": f"Invalid difficulty. Choose one of: {DIFFICULTY_LEVELS}", "Status": "error"}
        log_request(user_ip, "/quiz", {"topic": topic}, result, 400, time.time() - start)
        return jsonify(result), 400

    try:
        count = int(count_param)
    except ValueError:
        count = 1
    count = max(1, min(count, MAX_COUNT))

    actual_topic = topic
    is_random = False
    if topic == "random":
        actual_topic = random.choice(BUILTIN_TOPICS)
        is_random = True

    with stats_lock:
        STATS["total"] += 1
        STATS["topic_counts"][actual_topic] += 1
        STATS["difficulty_counts"][difficulty] += 1
        if is_random:
            STATS["random_picks"] += 1

    raw_reply = None
    result = None
    error = None
    attempt = 0
    succeeded = False

    for attempt in range(2):
        raw_reply, error = generate_quiz(actual_topic, difficulty, count)
        if error is None:
            parsed_result = build_quiz_response(actual_topic, difficulty, count, raw_reply)
            if parsed_result["Total_Questions"] > 0 and parsed_result["Questions"][0]["correct_option"]:
                result = parsed_result
                succeeded = True
                break
            elif result is None:
                result = parsed_result
    if not succeeded:
        if error or result is None:
            with stats_lock:
                STATS["errors"] += 1
            result = {
                "Topic": actual_topic,
                "Difficulty": difficulty,
                "Error": error or "Failed to parse quiz after retries",
                "Status": "error"
            }
            log_request(user_ip, "/quiz", {"topic": topic, "actual_topic": actual_topic,
                                           "difficulty": difficulty, "count": count},
                        result, 500, time.time() - start)
            return jsonify(result), 500

    if shuffle:
        letters = ["A", "B", "C", "D"]
        for q in result["Questions"]:
            if q["options"]:
                idx = letters.index(q["correct_option"]) if q["correct_option"] in letters else -1
                if idx >= 0:
                    correct_text = q["options"][idx]
                    random.shuffle(q["options"])
                    q["correct_option"] = letters[q["options"].index(correct_text)]
                else:
                    random.shuffle(q["options"])

    with stats_lock:
        STATS["success"] += 1
        STATS["questions_generated"] += result.get("Total_Questions", 0)

    if is_random:
        result["Random_Pick"] = True
        result["Available_Topics_Count"] = len(BUILTIN_TOPICS)

    result["Requested_By"] = user_ip
    result["Attempt"] = attempt + 1

    log_request(user_ip, "/quiz", {"topic": topic, "actual_topic": actual_topic,
                                   "difficulty": difficulty, "count": count},
                result, 200, time.time() - start)
    return jsonify(result)


@app.route("/categories", methods=["GET"])
def categories():
    return jsonify({
        "Built_In_Topics": BUILTIN_TOPICS,
        "Total_Topics": len(BUILTIN_TOPICS),
        "Difficulty_Levels": DIFFICULTY_LEVELS,
        "Seconds_To_Answer": DIFFICULTY_SECONDS,
        "Note": "Use /quiz?topic=random to pick one of these randomly. Any other topic value is also accepted.",
        "Status": "success"
    })


@app.route("/health", methods=["GET"])
def health():
    with stats_lock:
        total = STATS["total"]
    return jsonify({
        "Status": "alive",
        "Version": "6.0",
        "Total_Requests_Served": total,
        "Time_UTC": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    })


@app.route("/stats", methods=["GET"])
def stats():
    is_json = request.args.get("format", "").strip().lower() == "json"
    with stats_lock:
        snapshot = {
            "total": STATS["total"], "success": STATS["success"], "errors": STATS["errors"],
            "blocked": STATS["blocked"], "start_time": STATS["start_time"],
            "questions_generated": STATS["questions_generated"],
            "difficulty_counts": dict(STATS["difficulty_counts"]),
            "topic_counts": dict(STATS["topic_counts"]),
            "random_picks": STATS["random_picks"]
        }
    with admin_lock:
        banned_count = len(banned_set)
    with history_lock:
        unique_ips = len({r["ip"] for r in history_store})
        history_size = len(history_store)
    uptime = time.time() - snapshot["start_time"]
    success_rate = 0
    if snapshot["total"] > 0:
        success_rate = round(snapshot["success"] / snapshot["total"] * 100, 1)
    data = {
        "Total_Requests": snapshot["total"],
        "Successful": snapshot["success"],
        "Errors": snapshot["errors"],
        "Blocked_Attempts": snapshot["blocked"],
        "Success_Rate_Percent": success_rate,
        "Questions_Generated": snapshot["questions_generated"],
        "Uptime_Seconds": round(uptime, 1),
        "Uptime_Human": time.strftime("%Hh %Mm %Ss", time.gmtime(uptime)),
        "Tracked_IPs": unique_ips,
        "Banned_IPs": banned_count,
        "History_Records_Unlimited": history_size,
        "Random_Picks": snapshot["random_picks"],
        "Status": "success"
    }
    if is_json:
        return jsonify(data)

    cards = "<div class='grid'>"
    for label, value_key in [("Total Requests", "Total_Requests"), ("Successful", "Successful"),
                             ("Errors", "Errors"), ("Blocked", "Blocked_Attempts"),
                             ("Success %", "Success_Rate_Percent"), ("Questions", "Questions_Generated"),
                             ("Tracked IPs", "Tracked_IPs"), ("Banned IPs", "Banned_IPs")]:
        cards += (f"<div class='card pulse'><div class='num'>{data[value_key]}</div>"
                  f"<div class='note'>{esc(label)}</div></div>")
    cards += "</div>"

    rows = ""
    for k in ["Uptime_Human", "History_Records_Unlimited", "Random_Picks"]:
        rows += f"<div class='kv'><b>{k.replace('_', ' ')}:</b> {data[k]}</div>"
    tbox = "".join(f"<span class='badge'>{esc(a)}: {b}</span>" for a, b in snapshot["topic_counts"].items()) or "none yet"
    dbox = "".join(f"<span class='badge'>{esc(a)}: {b}</span>" for a, b in snapshot["difficulty_counts"].items()) or "none yet"
    rows += f"<div class='kv'><b>Topic Breakdown:</b> {tbox}</div>"
    rows += f"<div class='kv'><b>Difficulty Breakdown:</b> {dbox}</div>"
    return page("📊 Live Server Stats", cards + f"<div class='card'>{rows}</div>")


@app.route("/docs", methods=["GET"])
def docs():
    is_json = request.args.get("format", "").strip().lower() == "json"
    data = {
        "Service": "QuizGen AI",
        "Version": "6.0",
        "Format": "JSON from /quiz /categories /health, HTML dashboards for /stats and /docs",
        "Public_Endpoints": {
            "/quiz": {
                "Method": "GET",
                "Description": "Generate quiz questions on ANY topic. If topic=random, one of the 25 built-in topics is chosen randomly.",
                "Query_Params": {
                    "topic": "Required. Any topic, or 'random'.",
                    "difficulty": "Optional. easy | medium | hard. Default: medium.",
                    "count": "Optional. Number of questions 1-3. Default: 1.",
                    "shuffle": "Optional. true/false. Shuffles option order AND remaps correct_option. Default: false."
                },
                "Example_Requests": [
                    "/quiz?topic=space",
                    "/quiz?topic=random",
                    "/quiz?topic=random&difficulty=hard&count=3",
                    "/quiz?topic=python programming&count=2&shuffle=true"
                ],
                "Status_Codes": {
                    "200": "success",
                    "400": "missing topic or invalid difficulty",
                    "403": "access denied (banned IP)",
                    "429": "rate limited (2 seconds between requests)",
                    "500": "upstream API error"
                }
            },
            "/categories": {"Method": "GET", "Description": "List the built-in topics, difficulty levels and answer timers."},
            "/stats": {"Method": "GET", "Description": "Live statistics dashboard. Add ?format=json for raw JSON."},
            "/health": {"Method": "GET", "Description": "Quick health check - returns alive status."},
            "/docs": {"Method": "GET", "Description": "This documentation page. Add ?format=json for raw JSON."}
        }
    }
    if is_json:
        return jsonify(data)

    body = ""
    for endpoint, info in data["Public_Endpoints"].items():
        body += f"<div class='card'><h2>{esc(endpoint)}</h2><div class='kv'><b>Method:</b> {info['Method']}</div>"
        body += f"<div class='kv'><b>Description:</b> {esc(info['Description'])}</div>"
        if "Query_Params" in info:
            body += "<div class='kv'><b>Query Params:</b><pre>" + esc(pretty(info["Query_Params"])) + "</pre></div>"
        if "Example_Requests" in info:
            body += "<div class='kv'><b>Examples:</b>" + "".join(
                f"<span class='badge'><code>{esc(e)}</code></span>" for e in info["Example_Requests"]) + "</div>"
        if "Status_Codes" in info:
            body += "<div class='kv'><b>Status Codes:</b> " + ", ".join(
                f"{esc(k)} = {esc(v)}" for k, v in info["Status_Codes"].items()) + "</div>"
        body += "</div>"
    body += "<div class='card'><h2>Built-In Topics (topic=random)</h2>" + "".join(
        f"<span class='badge'>{esc(t)}</span>" for t in BUILTIN_TOPICS) + "</div>"
    body += "<div class='card'><h2>Difficulty Levels &amp; Timers</h2>" + "".join(
        f"<span class='badge'>{esc(d)}: {s}s per question</span>" for d, s in DIFFICULTY_SECONDS.items()) + "</div>"
    body += f"<div class='card'><h2>Limits</h2><div class='kv'><b>Max count per request:</b> {MAX_COUNT}</div>"
    body += f"<div class='kv'><b>Rate limit:</b> 1 request per IP every {RATE_LIMIT_SECONDS} seconds</div></div>"
    return page("📖 API Docs", body)


# ===================== PRIVATE PAGES (KEY REQUIRED) =====================

def admin_guard():
    key = request.args.get("key", "").strip()
    if key != SECRET_KEY:
        return False
    return True


def admin_gate():
    if not admin_guard():
        return fake_404()
    return None


def ip_status_maps():
    with history_lock:
        records = list(history_store)
    with admin_lock:
        bans_now = set(banned_set)
        tracked_now = {ip: dict(v) for ip, v in ip_stats.items()}
    summary = {}
    for r in records:
        entry = summary.setdefault(r["ip"], {
            "requests": 0, "errors": 0, "endpoints": set(),
            "first_seen": r["time"], "last_seen": r["time"]
        })
        entry["requests"] += 1
        entry["last_seen"] = r["time"]
        entry["endpoints"].add(r["endpoint"])
        if r["status_code"] != 200:
            entry["errors"] += 1
    return records, summary, bans_now, tracked_now


def ban_button(ip, banned_now):
    if banned_now:
        return f"<a class='btn btn-unban' href='/unban?ip={ip}&key={SECRET_KEY}'>Unban</a>"
    return f"<a class='btn btn-ban' href='/ban?ip={ip}&key={SECRET_KEY}'>Ban</a>"


def status_badge(banned_now):
    if banned_now:
        return "<span class='banned'>Banned</span>"
    return "<span class='active'>Active</span>"


@app.route("/admin", methods=["GET"])
def admin_home():
    gate = admin_gate()
    if gate:
        return gate
    is_json = request.args.get("format", "").strip().lower() == "json"
    records, summary, bans_now, tracked_now = ip_status_maps()
    result = {
        "Service": "QuizGen AI Admin",
        "Total_Requests": len(records),
        "Unique_IPs": len(summary),
        "Known_IPs_From_Tracking": sorted(tracked_now.keys()),
        "Banned_IPs": sorted(bans_now),
        "Total_Banned": len(bans_now),
        "Private_Endpoints": [
            "/admin?key=KEY (this page)", "/history?key=KEY", "/export?key=KEY&format=json|csv",
            "/ban?ip=IP&key=KEY", "/unban?ip=IP&key=KEY", "/ban-all?key=KEY",
            "/unban-all?key=KEY", "/banned-users?key=KEY", "/clear-history?key=KEY",
            "/reset-stats?key=KEY"
        ],
        "Status": "success"
    }
    if is_json:
        return jsonify(result)

    body = "<div class='grid'>"
    body += f"<div class='card pulse'><div class='num'>{len(records)}</div><div class='note'>Total Requests</div></div>"
    body += f"<div class='card pulse'><div class='num'>{len(summary)}</div><div class='note'>Unique IPs</div></div>"
    body += f"<div class='card pulse'><div class='num'>{len(bans_now)}</div><div class='note'>Banned IPs</div></div>"
    body += "</div>"
    body += ("<div class='card'><h2>Control Panel</h2>"
             f"<a class='btn btn-blue' href='/history?key={SECRET_KEY}'>History</a>"
             f"<a class='btn btn-blue' href='/banned-users?key={SECRET_KEY}'>Ban List</a>"
             f"<a class='btn btn-blue' href='/export?key={SECRET_KEY}&format=json'>Export JSON</a>"
             f"<a class='btn btn-blue' href='/export?key={SECRET_KEY}&format=csv'>Export CSV</a>"
             f"<a class='btn btn-ban' href='/ban-all?key={SECRET_KEY}'>Ban All</a>"
             f"<a class='btn btn-unban' href='/unban-all?key={SECRET_KEY}'>Unban All</a>"
             f"<a class='btn btn-unban' href='/clear-history?key={SECRET_KEY}'>Clear History</a>"
             f"<a class='btn btn-warn' href='/reset-stats?key={SECRET_KEY}'>Reset Stats</a></div>")
    return page("🛠️ Admin Dashboard", body)


@app.route("/history", methods=["GET"])
def history():
    gate = admin_gate()
    if gate:
        return gate

    filter_ip = request.args.get("ip", "").strip()
    endpoint_filter = request.args.get("endpoint", "").strip()
    status_filter = request.args.get("status", "").strip()
    search = request.args.get("search", "").strip()
    limit_param = request.args.get("limit", "").strip()
    is_json = request.args.get("format", "").strip().lower() == "json"

    records, summary, bans_now, tracked_now = ip_status_maps()

    if filter_ip:
        records = [r for r in records if r["ip"] == filter_ip]
        total_ip_requests = len(records)
        bnow = filter_ip in bans_now
        stats_now = tracked_now.get(filter_ip, {})
        if limit_param.isdigit():
            records = records[-int(limit_param):]
        if is_json:
            return jsonify({
                "IP": filter_ip,
                "Status": "Banned" if bnow else "Active",
                "Total_Requests": total_ip_requests,
                "Tracked_Info": stats_now,
                "History": records,
                "Status_Flag": "success"
            })
        status_html = status_badge(bnow)
        summary_rows = ""
        for k, v in sorted(stats_now.items()):
            summary_rows += f"<div class='kv'><b>{esc(k)}:</b> {esc(v)}</div>"
        rows = ""
        for r in reversed(records):
            okc = r["status_code"] == 200
            cls = "ok" if okc else "err"
            rows += (f"<div class='card'>"
                     f"<div class='kv'><b>#{r['id']}</b> - {esc(r['time'])} UTC - "
                     f"<span class='{cls}'>{r['status_code']}</span></div>"
                     f"<div class='kv'><b>Endpoint:</b> {esc(r['endpoint'])}</div>"
                     f"<div class='kv'><b>Request:</b><pre>{esc(pretty(r['request']))}</pre></div>"
                     f"<div class='kv'><b>Response:</b><pre>{esc(pretty(r['response']))}</pre></div>"
                     f"<div class='kv'><b>Duration:</b> {r['duration_seconds']}s</div></div>")
        if not rows:
            rows = "<div class='card'><p>No records found for this IP.</p></div>"
        return page(f"🕵️ History - {esc(filter_ip)} ({total_ip_requests})",
                    f"<div class='card'><h2 style='margin-top:0'>{esc(filter_ip)}</h2>"
                    f"<div class='kv'><b>Status:</b> {status_html}</div>"
                    f"<div class='kv'><b>Action:</b> {ban_button(filter_ip, bnow)}</div>{summary_rows}"
                    f"<div class='kv'><b>Shown:</b> {len(records)} of {total_ip_requests}</div></div>" + rows)

    if endpoint_filter:
        records = [r for r in records if endpoint_filter.lower() in r["endpoint"].lower()]
    if status_filter:
        records = [r for r in records if str(r["status_code"]) == status_filter]
    if search:
        records = [r for r in records if search.lower() in json.dumps(r["request"]).lower()
                   or search.lower() in json.dumps(r["response"]).lower()]
    if limit_param.isdigit():
        records = records[-int(limit_param):]

    if is_json:
        json_ips = {}
        for ip, e in summary.items():
            json_ips[ip] = {
                "requests": e["requests"],
                "first_seen": e["first_seen"],
                "last_seen": e["last_seen"],
                "endpoints": sorted(e["endpoints"]),
                "errors": e["errors"],
                "status": "Banned" if ip in bans_now else "Active"
            }
        return jsonify({
            "Total_Requests": len(records) if (endpoint_filter or status_filter or search) else len(history_store),
            "Unique_IPs": len(summary),
            "IP_Summary": json_ips,
            "Banned_IPs": sorted(bans_now),
            "Applied_Filters": {"endpoint": endpoint_filter, "status_code": status_filter, "search": search},
            "History": records,
            "Status": "success"
        })

    table = "<div class='card'><h2 style='margin-top:0'>All IPs &amp; Stats</h2>"
    table += ("<table><tr><th>IP</th><th>Status</th><th>Requests</th><th>Errors</th>"
              "<th>Endpoints</th><th>First Seen</th><th>Last Seen</th><th>Actions</th></tr>")
    for ip, e in sorted(summary.items(), key=lambda x: x[1]["requests"], reverse=True):
        bnow = ip in bans_now
        table += ("<tr>"
                  f"<td><code>{esc(ip)}</code></td>"
                  f"<td>{status_badge(bnow)}</td>"
                  f"<td>{e['requests']}</td>"
                  f"<td>{e['errors']}</td>"
                  f"<td>{esc(', '.join(sorted(e['endpoints'])))}</td>"
                  f"<td>{esc(e['first_seen'])}</td>"
                  f"<td>{esc(e['last_seen'])}</td>"
                  f"<td>{ban_button(ip, bnow)}</td></tr>")
    table += "</table>"
    table += ("<div style='margin-top:14px'>"
              f"<a class='btn btn-ban' href='/ban-all?key={SECRET_KEY}'>Ban All</a> "
              f"<a class='btn btn-unban' href='/unban-all?key={SECRET_KEY}'>Unban All</a> "
              f"<a class='btn btn-warn' href='/banned-users?key={SECRET_KEY}'>Ban List</a> "
              f"<a class='btn btn-blue' href='/admin?key={SECRET_KEY}'>Admin</a></div></div>")
    rows = ""
    for r in reversed(records):
        okc = r["status_code"] == 200
        cls = "ok" if okc else "err"
        rows += (f"<div class='card'>"
                 f"<div class='kv'><b>#{r['id']}</b> - {esc(r['time'])} UTC - "
                 f"<span class='{cls}'>{r['status_code']}</span></div>"
                 f"<div class='kv'><b>IP:</b> {esc(r['ip'])}</div>"
                 f"<div class='kv'><b>Endpoint:</b> {esc(r['endpoint'])}</div>"
                 f"<div class='kv'><b>Request:</b><pre>{esc(pretty(r['request']))}</pre></div>"
                 f"<div class='kv'><b>Response:</b><pre>{esc(pretty(r['response']))}</pre></div>"
                 f"<div class='kv'><b>Duration:</b> {r['duration_seconds']}s</div>"
                 f"<div style='margin-top:8px'>{ban_button(r['ip'], r['ip'] in bans_now)}</div></div>")
    if not rows:
        rows = "<div class='card'><p>No history yet.</p></div>"
    return page(f"🕵️ Request History ({len(records)} shown)",
                table + rows)


@app.route("/export", methods=["GET"])
def export_history():
    gate = admin_gate()
    if gate:
        return gate
    fmt = request.args.get("format", "json").strip().lower()
    with history_lock:
        records = list(history_store)
    if fmt == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["id", "time_utc", "ip", "endpoint", "status_code", "duration_seconds",
                         "request", "response"])
        for r in records:
            writer.writerow([r["id"], r["time"], r["ip"], r["endpoint"], r["status_code"],
                             r["duration_seconds"], json.dumps(r["request"]), json.dumps(r["response"])])
        return Response(buffer.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=history.csv"})
    return jsonify({"Total_Records": len(records), "History": records, "Status": "success"})


@app.route("/banned-users", methods=["GET"])
def banned_users():
    gate = admin_gate()
    if gate:
        return gate
    is_json = request.args.get("format", "").strip().lower() == "json"
    with admin_lock:
        snapshot_bans = sorted(banned_set)
    result = {"Total_Banned": len(snapshot_bans), "Banned_IPs": snapshot_bans, "Status": "success"}
    if is_json:
        return jsonify(result)
    rows = f"<div class='card'><h2 style='margin-top:0'>Ban List ({len(snapshot_bans)})</h2>"
    if snapshot_bans:
        for ip in snapshot_bans:
            rows += (f"<div class='kv'><b><code>{esc(ip)}</code></b> "
                     f"<a class='btn btn-unban' href='/unban?ip={ip}&key={SECRET_KEY}'>Unban</a></div>")
    else:
        rows += "<p>No banned IPs. Ban list is empty. 😌</p>"
    rows += "</div>"
    rows += (f"<div><a class='btn btn-unban' href='/unban-all?key={SECRET_KEY}'>Unban All</a> "
             f"<a class='btn btn-blue' href='/history?key={SECRET_KEY}'>History</a> "
             f"<a class='btn btn-blue' href='/admin?key={SECRET_KEY}'>Admin</a></div>")
    return page("🚫 Banned Users", rows)


@app.route("/ban", methods=["GET"])
@app.route("/unban", methods=["GET"])
def ban_single():
    gate = admin_gate()
    if gate:
        return gate
    action_path = request.path.strip("/")
    target_ip = request.args.get("ip", "").strip()
    is_json = request.args.get("format", "").strip().lower() == "json"
    if not target_ip:
        result = {"Error": "Query parameter 'ip' is required",
                  "Example": f"/{action_path}?ip=1.2.3.4&key=KEY", "Status": "error"}
        if is_json:
            return jsonify(result), 400
        return page("Admin", f"<div class='card'><p class='err'>ip parameter is required. "
                             f"Example: <code>/{action_path}?ip=1.2.3.4&amp;key=...</code></p></div>"), 400
    with admin_lock:
        if action_path == "ban":
            banned_set.add(target_ip)
            msg = f"IP {target_ip} is now banned"
        else:
            changed = target_ip in banned_set
            banned_set.discard(target_ip)
            msg = (f"IP {target_ip} unbanned" if changed else f"IP {target_ip} was not in the ban list")
        total = len(banned_set)
    result = {"Action": action_path, "IP": target_ip, "Message": msg, "Total_Banned": total, "Status": "success"}
    if is_json:
        return jsonify(result)
    emoji = "🔨" if action_path == "ban" else "🔓"
    return page(f"{emoji} Admin Action",
                f"<div class='card'><div class='kv'><b>Message:</b> {esc(msg)}</div>"
                f"<div class='kv'><b>Total Banned:</b> {total}</div>"
                f"<div style='margin-top:10px'>"
                f"<a class='btn btn-warn' href='/banned-users?key={SECRET_KEY}'>Ban List</a> "
                f"<a class='btn btn-blue' href='/history?key={SECRET_KEY}'>History</a> "
                f"<a class='btn btn-blue' href='/admin?key={SECRET_KEY}'>Admin</a></div></div>")


@app.route("/ban-all", methods=["GET"])
def ban_all():
    gate = admin_gate()
    if gate:
        return gate
    is_json = request.args.get("format", "").strip().lower() == "json"
    records, summary, bans_now, tracked_now = ip_status_maps()
    known = set(summary.keys()) | set(tracked_now.keys())
    with admin_lock:
        for ip in known:
            banned_set.add(ip)
        snapshot_bans = sorted(banned_set)
    result = {"Action": "ban-all", "Banned_All_These_IPs": snapshot_bans,
              "Total_Banned": len(snapshot_bans), "Status": "success"}
    if is_json:
        return jsonify(result)
    box = "".join(f"<span class='badge err'>{esc(ip)}</span>" for ip in snapshot_bans) or "none"
    return page("🔨 Ban All",
                f"<div class='card'><div class='kv'><b>All known IPs banned:</b> {box}</div>"
                f"<div style='margin-top:10px'>"
                f"<a class='btn btn-warn' href='/banned-users?key={SECRET_KEY}'>Ban List</a> "
                f"<a class='btn btn-blue' href='/admin?key={SECRET_KEY}'>Admin</a></div></div>")


@app.route("/unban-all", methods=["GET"])
def unban_all():
    gate = admin_gate()
    if gate:
        return gate
    is_json = request.args.get("format", "").strip().lower() == "json"
    with admin_lock:
        unbanned = sorted(banned_set)
        banned_set.clear()
    result = {"Action": "unban-all", "Unbanned_These_IPs": unbanned, "Total_Banned": 0, "Status": "success"}
    if is_json:
        return jsonify(result)
    box = "".join(f"<span class='badge'>{esc(ip)}</span>" for ip in unbanned) or "none"
    return page("🔓 Unban All",
                f"<div class='card'><div class='kv'><b>Unbanned all:</b> {box}</div>"
                f"<div class='kv'><b>Total Banned:</b> 0</div>"
                f"<div style='margin-top:10px'>"
                f"<a class='btn btn-warn' href='/banned-users?key={SECRET_KEY}'>Ban List</a> "
                f"<a class='btn btn-blue' href='/admin?key={SECRET_KEY}'>Admin</a></div></div>")


@app.route("/clear-history", methods=["GET"])
def clear_history():
    gate = admin_gate()
    if gate:
        return gate
    is_json = request.args.get("format", "").strip().lower() == "json"
    with history_lock:
        cleared = len(history_store)
        history_store.clear()
    result = {"Cleared_Records": cleared, "Total_Banned": None, "Message": "History cleared (unlimited mode was active)", "Status": "success"}
    if is_json:
        return jsonify(result)
    return page("🧹 History Cleared",
                f"<div class='card'><div class='kv'><b>Cleared Records:</b> {cleared}</div>"
                f"<div style='margin-top:10px'>"
                f"<a class='btn btn-blue' href='/history?key={SECRET_KEY}'>History</a> "
                f"<a class='btn btn-blue' href='/admin?key={SECRET_KEY}'>Admin</a></div></div>")


@app.route("/reset-stats", methods=["GET"])
def reset_stats():
    gate = admin_gate()
    if gate:
        return gate
    is_json = request.args.get("format", "").strip().lower() == "json"
    with stats_lock:
        for k in ["total", "success", "errors", "blocked", "questions_generated", "random_picks"]:
            STATS[k] = 0
        STATS["difficulty_counts"].clear()
        STATS["topic_counts"].clear()
    result = {"Message": "Statistics reset to zero (uptime unchanged)", "Status": "success"}
    if is_json:
        return jsonify(result)
    return page("♻️ Stats Reset",
                f"<div class='card'><p>All counters are back to zero. Uptime is unchanged.</p>"
                f"<div style='margin-top:10px'>"
                f"<a class='btn btn-blue' href='/stats'>Stats</a> "
                f"<a class='btn btn-blue' href='/admin?key={SECRET_KEY}'>Admin</a></div></div>")


# ===================== CATCH-ALL (hides everything) =====================

@app.route("/<path:unknown_path>", methods=["GET"])
def catch_all(unknown_path):
    return fake_404()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
