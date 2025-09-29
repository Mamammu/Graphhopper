import os
import sys
import time
import json
import urllib.parse
import requests

# Optional colors (fallback to no-color if not installed)
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    C_OK = Fore.GREEN
    C_WARN = Fore.YELLOW
    C_ERR = Fore.RED
    C_INFO = Fore.CYAN
    C_RST = Style.RESET_ALL
except Exception:
    C_OK = C_WARN = C_ERR = C_INFO = C_RST = ""

GRAPHOPPER_KEY = os.getenv("GRAPHHOPPER_KEY", "6c57578b-b515-4eac-9303-166acf4ca72b")
GEOCODE_URL = "https://graphhopper.com/api/1/geocode"
ROUTE_URL   = "https://graphhopper.com/api/1/route"

def _format_hit_display(hit: dict, fallback_name: str = "") -> str:
    name = hit.get("name", fallback_name)
    city = hit.get("city", "")
    state = hit.get("state", "")
    country = hit.get("country", "")
    parts = [v for v in [name, city, state, country] if v]
    return ", ".join(parts) or (name or fallback_name)

def geocode_suggestions(query: str, limit: int = 5) -> dict:
    """Return {'ok':bool, 'hits': [ {name, lat, lng}... ], 'msg': str}

    Uses GraphHopper geocoding to fetch multiple candidates to suggest similar places.
    """
    query = (query or "").strip()
    if not query:
        return {"ok": False, "hits": [], "msg": "Empty location."}
    params = {"q": query, "limit": max(1, min(10, int(limit or 5))), "key": GRAPHOPPER_KEY}
    try:
        r = requests.get(GEOCODE_URL, params=params, timeout=15)
        if r.status_code != 200:
            return {"ok": False, "hits": [], "msg": f"Geocode HTTP {r.status_code}: {r.text[:200]}"}
        data = r.json()
        hits_raw = data.get("hits", []) or []
        hits = []
        for h in hits_raw:
            pt = h.get("point", {}) or {}
            name = _format_hit_display(h, query)
            if pt.get("lat") is None or pt.get("lng") is None:
                continue
            hits.append({"name": name, "lat": pt.get("lat"), "lng": pt.get("lng")})
        if not hits:
            return {"ok": False, "hits": [], "msg": f"No geocoding results for '{query}'."}
        return {"ok": True, "hits": hits, "msg": ""}
    except requests.RequestException as e:
        return {"ok": False, "hits": [], "msg": f"Geocode error: {e}"}

def geocode_one(location: str) -> dict:
    """Return {'ok':bool, 'name':str, 'lat':float, 'lng':float, 'msg':str}"""
    location = (location or "").strip()
    if not location:
        return {"ok": False, "msg": "Empty location."}
    params = {"q": location, "limit": 1, "key": GRAPHOPPER_KEY}
    try:
        r = requests.get(GEOCODE_URL, params=params, timeout=15)
        if r.status_code != 200:
            return {"ok": False, "msg": f"Geocode HTTP {r.status_code}: {r.text[:200]}"}
        data = r.json()
        hits = data.get("hits", [])
        if not hits:
            return {"ok": False, "msg": f"No geocoding results for '{location}'."}
        h0 = hits[0]
        name = h0.get("name", location)
        state = h0.get("state", "")
        country = h0.get("country", "")
        display = ", ".join([v for v in [name, state, country] if v])
        pt = h0.get("point", {})
        return {"ok": True, "name": display or name, "lat": pt.get("lat"), "lng": pt.get("lng"), "msg": ""}
    except requests.RequestException as e:
        return {"ok": False, "msg": f"Geocode error: {e}"}

def route_points(points, vehicle="car"):
    """points: list of (lat,lng). Return {'ok':bool, 'data':dict, 'msg':str}"""
    params = {"key": GRAPHOPPER_KEY, "vehicle": vehicle, "points_encoded": "false"}  # unencoded for readability
    # Add multiple &point parameters
    # requests will handle multi-values if we pass a list of tuples
    point_params = [("point", f"{lat},{lng}") for lat, lng in points]
    try:
        r = requests.get(ROUTE_URL, params=[*params.items(), *point_params], timeout=30)
        if r.status_code != 200:
            return {"ok": False, "msg": f"Route HTTP {r.status_code}: {r.text[:200]}"}
        data = r.json()
        if not data.get("paths"):
            return {"ok": False, "msg": "No route found for the given points."}
        return {"ok": True, "data": data, "msg": ""}
    except requests.RequestException as e:
        return {"ok": False, "msg": f"Route error: {e}"}

def format_duration(ms: int) -> str:
    s = ms // 1000
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def print_summary(path, names):
    dist_m = path["distance"]
    time_ms = path["time"]
    km = dist_m / 1000
    miles = km / 1.60934
    print(f"{C_INFO}\n=== Route Summary ==={C_RST}")
    print(f"{C_OK}From:{C_RST} {names[0]}")
    for i in range(1, len(names)):
        print(f"  → {names[i]}")
    print(f"{C_OK}Vehicle:{C_RST} {path.get('profile','') or 'car'}")
    print(f"{C_OK}Distance:{C_RST} {km:.2f} km ({miles:.2f} mi)")
    print(f"{C_OK}Duration:{C_RST} {format_duration(time_ms)}")

def print_instructions(path):
    print(f"{C_INFO}\n=== Step-by-step Instructions ==={C_RST}")
    instr = path.get("instructions", [])
    for i, step in enumerate(instr, 1):
        text = step.get("text", "")
        dist_km = (step.get("distance", 0) / 1000.0)
        print(f"{i:>2}. {text}  [{dist_km:.2f} km]")

def write_report(filename, path, names):
    dist_m = path["distance"]
    time_ms = path["time"]
    km = dist_m / 1000
    miles = km / 1.60934
    lines = []
    lines.append("=== Route Summary ===")
    lines.append(f"From: {names[0]}")
    for i in range(1, len(names)):
        lines.append(f"  -> {names[i]}")
    lines.append(f"Vehicle: {path.get('profile','') or 'car'}")
    lines.append(f"Distance: {km:.2f} km ({miles:.2f} mi)")
    lines.append(f"Duration: {format_duration(time_ms)}")
    lines.append("")
    lines.append("=== Step-by-step Instructions ===")
    for i, step in enumerate(path.get("instructions", []), 1):
        text = step.get("text", "")
        dist_km = (step.get("distance", 0) / 1000.0)
        lines.append(f"{i:>2}. {text}  [{dist_km:.2f} km]")
    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return filename

def main():
    if GRAPHOPPER_KEY in ("", "YOUR_API_KEY"):
        print(f"{C_ERR}Please set GRAPHHOPPER_KEY environment variable or replace YOUR_API_KEY in the code.{C_RST}")
        sys.exit(1)

    profiles = {"car", "bike", "foot"}
    vehicle = input("Vehicle profile (car/bike/foot) [car]: ").strip().lower() or "car"
    if vehicle not in profiles:
        print(f"{C_WARN}Unknown vehicle; defaulting to 'car'.{C_RST}")
        vehicle = "car"

    print("\nEnter locations in order. Leave blank to finish.")
    names = []
    coords = []

    while True:
        prompt = "Start" if not names else f"Stop {len(names)}"
        loc = input(f"{prompt}: ").strip()
        if not loc:
            if len(names) < 2:
                print(f"{C_WARN}Need at least 2 locations. Please enter more.{C_RST}")
                continue
            break
        # Fetch suggestions for similar places and let user choose
        sugg = geocode_suggestions(loc, limit=5)
        if not sugg["ok"] or not sugg["hits"]:
            print(f"{C_ERR}{sugg['msg']}{C_RST}")
            # Let user re-enter location
            continue
        hits = sugg["hits"]
        print(f"{C_INFO}Did you mean:{C_RST}")
        for i, h in enumerate(hits, 1):
            print(f"  {i}. {h['name']}  ({h['lat']:.5f}, {h['lng']:.5f})")
        # Selection loop
        while True:
            choice = input(f"Select 1-{len(hits)} [1], or 0 to re-enter: ").strip()
            if choice == "":
                idx = 1
            else:
                if not choice.isdigit():
                    print(f"{C_WARN}Please enter a number between 0 and {len(hits)}.{C_RST}")
                    continue
                idx = int(choice)
            if idx == 0:
                # re-enter query
                break
            if 1 <= idx <= len(hits):
                sel = hits[idx - 1]
                names.append(sel["name"])
                coords.append((sel["lat"], sel["lng"]))
                print(f"{C_OK}✓{C_RST} {sel['name']}  ({sel['lat']:.5f}, {sel['lng']:.5f})")
                break
            else:
                print(f"{C_WARN}Out of range. Choose 1-{len(hits)} or 0 to re-enter.{C_RST}")
        # If user chose 0, restart to re-enter location
        if choice == "0":
            continue

    print(f"\n{C_INFO}Requesting route for {len(coords)} point(s)...{C_RST}")
    r = route_points(coords, vehicle=vehicle)
    if not r["ok"]:
        print(f"{C_ERR}{r['msg']}{C_RST}")
        sys.exit(2)

    path = r["data"]["paths"][0]
    print_summary(path, names)

    show_steps = (input("\nShow full step-by-step? (y/N): ").strip().lower() == "y")
    if show_steps:
        print_instructions(path)

    save = (input("\nSave report to file? (y/N): ").strip().lower() == "y")
    if save:
        ts = time.strftime("%Y%m%d_%H%M%S")
        fname = f"route_{ts}.txt"
        try:
            out = write_report(fname, path, names)
            print(f"{C_OK}Report saved to {out}{C_RST}")
        except Exception as e:
            print(f"{C_ERR}Failed to save report: {e}{C_RST}")

if __name__ == "__main__":
    main()
