from flask import Flask, request, redirect, render_template_string, jsonify
from datetime import datetime
import json
import os
import hashlib

app = Flask(__name__)

# Store logs in a JSON file (use a DB for production)
LOG_FILE = "clicks.json"

def load_logs():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            return json.load(f)
    return []

def save_log(entry):
    logs = load_logs()
    logs.append(entry)
    with open(LOG_FILE, "w") as f:
        json.dump(logs, f, indent=2)

# Admin password (set via environment variable)
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme123")

def parse_user_agent(ua):
    """Extract device, OS, and browser from User-Agent string."""
    device = "Unknown"
    os_name = "Unknown"
    browser = "Unknown"

    # OS detection
    if "iPhone" in ua:
        device = "iPhone"
        os_name = "iOS"
    elif "iPad" in ua:
        device = "iPad"
        os_name = "iOS"
    elif "Android" in ua:
        os_name = "Android"
        # Try to extract device model
        try:
            start = ua.index("Android")
            segment = ua[start:]
            if ";" in segment:
                parts = segment.split(";")
                if len(parts) > 1:
                    model = parts[1].strip()
                    if "Build" in model:
                        model = model[:model.index("Build")].strip()
                    if ")" in model:
                        model = model[:model.index(")")].strip()
                    device = model if model else "Android Device"
                else:
                    device = "Android Device"
            else:
                device = "Android Device"
        except:
            device = "Android Device"
    elif "Windows" in ua:
        device = "PC"
        os_name = "Windows"
        if "Windows NT 10.0" in ua:
            os_name = "Windows 10/11"
        elif "Windows NT 6.3" in ua:
            os_name = "Windows 8.1"
    elif "Macintosh" in ua:
        device = "Mac"
        os_name = "macOS"
    elif "Linux" in ua:
        device = "PC"
        os_name = "Linux"

    # Browser detection
    if "Edg/" in ua:
        browser = "Edge"
    elif "Chrome/" in ua and "Safari/" in ua:
        browser = "Chrome"
    elif "Firefox/" in ua:
        browser = "Firefox"
    elif "Safari/" in ua:
        browser = "Safari"
    elif "Opera" in ua or "OPR/" in ua:
        browser = "Opera"

    return device, os_name, browser


# ---- TRACKING ENDPOINT ----
@app.route("/t/<link_id>")
def track(link_id):
    """Track the click and redirect to the target URL."""
    # Load links config
    links = load_links()
    target = links.get(link_id)

    if not target:
        return "Link not found", 404

    ua = request.headers.get("User-Agent", "")
    device, os_name, browser = parse_user_agent(ua)

    entry = {
        "link_id": link_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "ip": request.headers.get("X-Forwarded-For", request.remote_addr),
        "user_agent": ua,
        "device": device,
        "os": os_name,
        "browser": browser,
        "referrer": request.headers.get("Referer", "Direct"),
        "language": request.headers.get("Accept-Language", "Unknown"),
    }

    save_log(entry)
    return redirect(target)


# ---- LINK MANAGEMENT ----
LINKS_FILE = "links.json"

def load_links():
    if os.path.exists(LINKS_FILE):
        with open(LINKS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_links(links):
    with open(LINKS_FILE, "w") as f:
        json.dump(links, f, indent=2)


# ---- DASHBOARD ----
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Link Tracker Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; }
        h1 { color: #38bdf8; margin-bottom: 20px; }
        h2 { color: #94a3b8; margin: 20px 0 10px; font-size: 1.1em; }

        .stats { display: flex; gap: 15px; margin-bottom: 25px; flex-wrap: wrap; }
        .stat-card { background: #1e293b; padding: 15px 20px; border-radius: 10px; min-width: 120px; }
        .stat-card .number { font-size: 2em; font-weight: bold; color: #38bdf8; }
        .stat-card .label { color: #94a3b8; font-size: 0.85em; }

        .section { background: #1e293b; border-radius: 10px; padding: 20px; margin-bottom: 20px; }

        /* Create link form */
        .form-row { display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap; }
        input[type="text"] { background: #0f172a; border: 1px solid #334155; color: #e2e8f0; padding: 10px 14px; border-radius: 8px; flex: 1; min-width: 200px; }
        button { background: #38bdf8; color: #0f172a; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-weight: 600; }
        button:hover { background: #7dd3fc; }

        /* Links table */
        .link-item { background: #0f172a; padding: 12px; border-radius: 8px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
        .link-url { color: #38bdf8; word-break: break-all; font-size: 0.9em; }
        .link-target { color: #64748b; font-size: 0.8em; word-break: break-all; }
        .copy-btn { background: #334155; color: #e2e8f0; padding: 5px 12px; border-radius: 5px; font-size: 0.8em; cursor: pointer; border: none; }
        .copy-btn:hover { background: #475569; }

        /* Click logs */
        table { width: 100%; border-collapse: collapse; }
        th { text-align: left; padding: 10px; color: #94a3b8; border-bottom: 1px solid #334155; font-size: 0.85em; }
        td { padding: 10px; border-bottom: 1px solid #1e293b; font-size: 0.9em; }
        tr:hover { background: #1e293b; }

        .tag { background: #334155; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; }

        .empty { color: #64748b; text-align: center; padding: 40px; }

        @media (max-width: 600px) {
            table { font-size: 0.8em; }
            th, td { padding: 6px; }
        }
    </style>
</head>
<body>
    <h1>🔗 Link Tracker</h1>

    <div class="stats">
        <div class="stat-card">
            <div class="number">{{ total_clicks }}</div>
            <div class="label">Total Clicks</div>
        </div>
        <div class="stat-card">
            <div class="number">{{ unique_ips }}</div>
            <div class="label">Unique Visitors</div>
        </div>
        <div class="stat-card">
            <div class="number">{{ total_links }}</div>
            <div class="label">Active Links</div>
        </div>
    </div>

    <!-- Create new link -->
    <div class="section">
        <h2>Create Tracking Link</h2>
        <form method="POST" action="/dashboard/create">
            <div class="form-row">
                <input type="text" name="url" placeholder="Paste destination URL (e.g. https://google.com)" required>
                <input type="text" name="slug" placeholder="Custom slug (optional)">
                <button type="submit">Create Link</button>
            </div>
        </form>
    </div>

    <!-- Active links -->
    {% if links %}
    <div class="section">
        <h2>Your Links</h2>
        {% for slug, target in links.items() %}
        <div class="link-item">
            <div>
                <div class="link-url">{{ base_url }}/t/{{ slug }}</div>
                <div class="link-target">→ {{ target }}</div>
            </div>
            <button class="copy-btn" onclick="navigator.clipboard.writeText('{{ base_url }}/t/{{ slug }}')">Copy</button>
        </div>
        {% endfor %}
    </div>
    {% endif %}

    <!-- Click logs -->
    <div class="section">
        <h2>Recent Clicks</h2>
        {% if logs %}
        <div style="overflow-x: auto;">
        <table>
            <tr>
                <th>Time (UTC)</th>
                <th>Link</th>
                <th>IP</th>
                <th>Device</th>
                <th>OS</th>
                <th>Browser</th>
            </tr>
            {% for log in logs|reverse %}
            <tr>
                <td>{{ log.timestamp[:19] }}</td>
                <td><span class="tag">{{ log.link_id }}</span></td>
                <td>{{ log.ip }}</td>
                <td>{{ log.device }}</td>
                <td>{{ log.os }}</td>
                <td>{{ log.browser }}</td>
            </tr>
            {% endfor %}
        </table>
        </div>
        {% else %}
        <div class="empty">No clicks yet. Share a link to start tracking!</div>
        {% endif %}
    </div>
</body>
</html>
"""

@app.route("/dashboard")
def dashboard():
    # Simple password check via query param
    pw = request.args.get("pw", "")
    if pw != ADMIN_PASSWORD:
        return render_template_string("""
        <!DOCTYPE html><html><head><title>Login</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: sans-serif; background: #0f172a; color: #e2e8f0; display: flex; justify-content: center; align-items: center; height: 100vh; }
            form { background: #1e293b; padding: 30px; border-radius: 12px; }
            input { background: #0f172a; border: 1px solid #334155; color: #e2e8f0; padding: 10px; border-radius: 8px; width: 100%; margin: 10px 0; }
            button { background: #38bdf8; color: #0f172a; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; width: 100%; font-weight: 600; }
        </style></head><body>
        <form method="GET" action="/dashboard">
            <h2>🔒 Dashboard Login</h2>
            <input type="password" name="pw" placeholder="Enter password">
            <button type="submit">Enter</button>
        </form></body></html>
        """)

    logs = load_logs()
    links = load_links()
    unique_ips = len(set(l.get("ip", "") for l in logs))
    base_url = request.host_url.rstrip("/")

    return render_template_string(DASHBOARD_HTML,
        logs=logs,
        links=links,
        total_clicks=len(logs),
        unique_ips=unique_ips,
        total_links=len(links),
        base_url=base_url
    )


@app.route("/dashboard/create", methods=["POST"])
def create_link():
    pw = request.args.get("pw", request.form.get("pw", ""))
    url = request.form.get("url", "").strip()
    slug = request.form.get("slug", "").strip()

    if not url:
        return redirect(f"/dashboard?pw={ADMIN_PASSWORD}")

    if not slug:
        slug = hashlib.md5(url.encode()).hexdigest()[:6]

    links = load_links()
    links[slug] = url
    save_links(links)

    return redirect(f"/dashboard?pw={ADMIN_PASSWORD}")


@app.route("/")
def home():
    return redirect("/dashboard")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
