"""
Spritpreise Europa - Flask Webapp
Standort automatisch via IP · Diesel & E10 Preise
"""

from flask import Flask, render_template, jsonify, request
import requests
import os

app = Flask(__name__)

TANKERKOENIG_API_KEY = os.environ.get("TANKERKOENIG_API_KEY", "00000000-0000-0000-0000-000000000000")
DEFAULT_RADIUS = 30  # km

# ── EU Fallback Daten (KW11/2026) ──────────────────────
EU_FALLBACK = [
    {"country": "Austria",     "diesel": 1.590, "euro95": 1.630},
    {"country": "Belgium",     "diesel": 1.699, "euro95": 1.789},
    {"country": "Bulgaria",    "diesel": 1.374, "euro95": 1.373},
    {"country": "Croatia",     "diesel": 1.451, "euro95": 1.559},
    {"country": "Cyprus",      "diesel": 1.372, "euro95": 1.465},
    {"country": "Czechia",     "diesel": 1.448, "euro95": 1.537},
    {"country": "Denmark",     "diesel": 1.724, "euro95": 1.890},
    {"country": "Estonia",     "diesel": 1.540, "euro95": 1.610},
    {"country": "Finland",     "diesel": 1.674, "euro95": 1.837},
    {"country": "France",      "diesel": 1.717, "euro95": 1.806},
    {"country": "Germany",     "diesel": 1.655, "euro95": 1.799},
    {"country": "Greece",      "diesel": 1.584, "euro95": 1.812},
    {"country": "Hungary",     "diesel": 1.461, "euro95": 1.521},
    {"country": "Ireland",     "diesel": 1.741, "euro95": 1.828},
    {"country": "Italy",       "diesel": 1.683, "euro95": 1.822},
    {"country": "Latvia",      "diesel": 1.552, "euro95": 1.641},
    {"country": "Lithuania",   "diesel": 1.519, "euro95": 1.599},
    {"country": "Luxembourg",  "diesel": 1.412, "euro95": 1.478},
    {"country": "Malta",       "diesel": 1.299, "euro95": 1.482},
    {"country": "Netherlands", "diesel": 1.829, "euro95": 2.081},
    {"country": "Poland",      "diesel": 1.384, "euro95": 1.426},
    {"country": "Portugal",    "diesel": 1.700, "euro95": 1.811},
    {"country": "Romania",     "diesel": 1.378, "euro95": 1.467},
    {"country": "Slovakia",    "diesel": 1.461, "euro95": 1.568},
    {"country": "Slovenia",    "diesel": 1.540, "euro95": 1.584},
    {"country": "Spain",       "diesel": 1.538, "euro95": 1.649},
    {"country": "Sweden",      "diesel": 1.768, "euro95": 1.888},
]


def get_location_from_ip(ip):
    """Standort via IP ermitteln (ip-api.com, kostenlos)."""
    # Bei lokalem Entwickeln (127.0.0.1) Stuttgart als Standard
    if ip in ("127.0.0.1", "::1", "localhost"):
        return {"lat": 48.7670, "lng": 9.1827, "city": "Stuttgart", "region": "Baden-Württemberg", "country": "Germany"}
    resp = requests.get(f"http://ip-api.com/json/{ip}", timeout=8)
    data = resp.json()
    if data.get("status") != "success":
        raise Exception("Standort nicht ermittelbar")
    return {
        "lat":         data["lat"],
        "lng":         data["lon"],
        "city":        data.get("city", ""),
        "region":      data.get("regionName", ""),
        "country":     data.get("country", ""),
        "countryCode": data.get("countryCode", ""),
    }


def get_stations(lat, lng, radius):
    """Tankstellen via Tankerkönig API laden."""
    resp = requests.get(
        "https://creativecommons.tankerkoenig.de/json/list.php",
        params={
            "lat":    lat,
            "lng":    lng,
            "rad":    radius,
            "type":   "all",
            "sort":   "dist",
            "apikey": TANKERKOENIG_API_KEY,
        },
        timeout=15
    )
    return resp.json()


def get_eu_prices():
    """EU-Preise laden, Fallback auf statische Daten."""
    try:
        resp = requests.get(
            "https://www.fuel-prices.eu/api/v1/eu-fuel-prices/latest",
            headers={"Accept": "application/json"},
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return EU_FALLBACK


# ── Routen ─────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/location")
def api_location():
    """Gibt Standort des Besuchers zurück."""
    # X-Forwarded-For für Proxies (Render.com etc.)
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if ip and "," in ip:
        ip = ip.split(",")[0].strip()
    try:
        loc = get_location_from_ip(ip)
        return jsonify({"ok": True, **loc})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/stations")
def api_stations():
    """Tankstellen im Umkreis laden."""
    try:
        lat = float(request.args.get("lat"))
        lng = float(request.args.get("lng"))
        rad = float(request.args.get("rad", DEFAULT_RADIUS))
        data = get_stations(lat, lng, rad)
        if not data.get("ok"):
            return jsonify({"ok": False, "error": data.get("message", "API Fehler")}), 500

        stations = data.get("stations", [])

        # Nur offene Stationen mit Preisen, sortiert nach Diesel
        open_stations = [
            s for s in stations
            if s.get("isOpen") and isinstance(s.get("diesel"), float)
        ]
        open_stations.sort(key=lambda x: x.get("diesel", 9999))

        return jsonify({"ok": True, "stations": stations, "open": open_stations})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/eu")
def api_eu():
    """EU-Preise laden."""
    try:
        data = get_eu_prices()
        return jsonify({"ok": True, "data": data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/reversegeo")
def api_reversegeo():
    """Stadtname via Koordinaten ermitteln (für GPS-Standort)."""
    try:
        lat = request.args.get("lat")
        lng = request.args.get("lng")
        resp = requests.get(
            f"http://ip-api.com/json/?fields=city,regionName,country,countryCode",
            timeout=8
        )
        # ip-api gibt bei Koordinaten-Anfrage keinen direkten Endpoint
        # Wir nutzen nominatim (OpenStreetMap) für Reverse Geocoding
        resp2 = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lng, "format": "json"},
            headers={"User-Agent": "SpritpreiseEuropa/1.0"},
            timeout=8
        )
        data = resp2.json()
        addr = data.get("address", {})
        country_code = addr.get("country_code", "").upper()
        return jsonify({
            "ok": True,
            "city":        addr.get("city") or addr.get("town") or addr.get("village", ""),
            "region":      addr.get("state", ""),
            "country":     addr.get("country", ""),
            "countryCode": country_code,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
