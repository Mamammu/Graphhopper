import os
import sys
import time
import json
import urllib.parse
import requests
import csv
from tkinter import *
from tkinter import ttk, messagebox, filedialog
from threading import Thread

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

def export_route_txt(filename, path, names):
    """Export route to TXT format"""
    return write_report(filename, path, names)

def export_route_json(filename, path, names, route_data):
    """Export route to JSON format"""
    dist_m = path["distance"]
    time_ms = path["time"]
    km = dist_m / 1000
    miles = km / 1.60934
    
    export_data = {
        "route_summary": {
            "from": names[0],
            "to": names[-1] if len(names) > 1 else names[0],
            "waypoints": names,
            "vehicle": path.get('profile', 'car'),
            "distance_km": round(km, 2),
            "distance_miles": round(miles, 2),
            "distance_meters": dist_m,
            "duration_ms": time_ms,
            "duration_formatted": format_duration(time_ms)
        },
        "instructions": [
            {
                "step": i,
                "text": step.get("text", ""),
                "distance_km": round(step.get("distance", 0) / 1000.0, 2),
                "distance_m": step.get("distance", 0)
            }
            for i, step in enumerate(path.get("instructions", []), 1)
        ],
        "full_route_data": route_data
    }
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)
    return filename

def export_route_csv(filename, path, names):
    """Export route to CSV format"""
    dist_m = path["distance"]
    time_ms = path["time"]
    km = dist_m / 1000
    miles = km / 1.60934
    
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        # Route summary
        writer.writerow(["Route Summary"])
        writer.writerow(["From", names[0]])
        for i in range(1, len(names)):
            writer.writerow(["Waypoint", names[i]])
        writer.writerow(["Vehicle", path.get('profile', 'car')])
        writer.writerow(["Distance (km)", f"{km:.2f}"])
        writer.writerow(["Distance (miles)", f"{miles:.2f}"])
        writer.writerow(["Duration", format_duration(time_ms)])
        writer.writerow([])
        # Instructions
        writer.writerow(["Step", "Instruction", "Distance (km)"])
        for i, step in enumerate(path.get("instructions", []), 1):
            text = step.get("text", "")
            dist_km = step.get("distance", 0) / 1000.0
            writer.writerow([i, text, f"{dist_km:.2f}"])
    return filename

class RoutePlannerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("🗺️ GraphHopper")
        self.root.geometry("1000x750")
        self.root.resizable(True, True)
        
        # Color scheme
        self.colors = {
            'bg': '#f0f0f0',
            'header_bg': '#2c3e50',
            'header_fg': '#ffffff',
            'primary': '#3498db',
            'primary_hover': '#2980b9',
            'success': '#27ae60',
            'success_hover': '#229954',
            'warning': '#f39c12',
            'warning_hover': '#e67e22',
            'danger': '#e74c3c',
            'danger_hover': '#c0392b',
            'section_bg': '#ffffff',
            'text': '#2c3e50',
            'text_light': '#7f8c8d',
            'border': '#d5dbdb',
            'selected': '#3498db',
            'listbox_bg': '#ffffff',
            'listbox_select': '#e3f2fd',
            'entry_bg': '#ffffff'
        }
        
        # Set background
        root.configure(bg=self.colors['bg'])
        
        # Data storage
        self.locations = []  # List of {"name": str, "lat": float, "lng": float}
        self.current_suggestions = []
        self.route_data = None
        self.route_path = None
        
        # Configure style
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure custom styles
        self.setup_styles(style)
        
        # Header
        header_frame = Frame(root, bg=self.colors['header_bg'], height=60)
        header_frame.pack(fill=X)
        header_frame.pack_propagate(False)
        header_label = Label(header_frame, text="🗺️ GraphHopper", 
                            font=("Segoe UI", 18, "bold"), 
                            bg=self.colors['header_bg'], 
                            fg=self.colors['header_fg'])
        header_label.pack(pady=15)
        
        # Create main frame with padding
        main_frame = Frame(root, bg=self.colors['bg'], padx=15, pady=15)
        main_frame.pack(fill=BOTH, expand=True)
        
        # Create content container
        content_frame = Frame(main_frame, bg=self.colors['bg'])
        content_frame.pack(fill=BOTH, expand=True)
        
        # Vehicle selection section
        vehicle_section = Frame(content_frame, bg=self.colors['bg'], relief=FLAT, bd=0)
        vehicle_section.pack(fill=X, pady=(0, 10))
        vehicle_container = Frame(vehicle_section, bg=self.colors['border'], padx=1, pady=1)
        vehicle_container.pack(fill=X)
        vehicle_inner = Frame(vehicle_container, bg=self.colors['section_bg'], padx=15, pady=12)
        vehicle_inner.pack(fill=X)
        
        vehicle_label = Label(vehicle_inner, text="🚗 Vehicle Profile", 
                             font=("Segoe UI", 11, "bold"), 
                             bg=self.colors['section_bg'], 
                             fg=self.colors['text'])
        vehicle_label.pack(side=LEFT, padx=(0, 15))
        
        self.vehicle_var = StringVar(value="car")
        vehicle_frame = Frame(vehicle_inner, bg=self.colors['section_bg'])
        vehicle_frame.pack(side=LEFT)
        
        vehicle_icons = {"car": "🚗", "bike": "🚴", "foot": "🚶"}
        for vehicle in ["car", "bike", "foot"]:
            rb = Radiobutton(vehicle_frame, 
                            text=f"{vehicle_icons.get(vehicle, '')} {vehicle.capitalize()}", 
                            variable=self.vehicle_var, 
                            value=vehicle,
                            font=("Segoe UI", 10),
                            bg=self.colors['section_bg'],
                            fg=self.colors['text'],
                            activebackground=self.colors['section_bg'],
                            activeforeground=self.colors['primary'],
                            selectcolor=self.colors['section_bg'],
                            cursor="hand2")
            rb.pack(side=LEFT, padx=8)
        
        # Location search section
        search_section = Frame(content_frame, bg=self.colors['bg'], relief=FLAT, bd=0)
        search_section.pack(fill=X, pady=(0, 10))
        search_container = Frame(search_section, bg=self.colors['border'], padx=1, pady=1)
        search_container.pack(fill=X)
        search_inner = Frame(search_container, bg=self.colors['section_bg'], padx=15, pady=12)
        search_inner.pack(fill=X)
        search_inner.columnconfigure(1, weight=1)
        
        search_label = Label(search_inner, text="🔍 Search Location", 
                            font=("Segoe UI", 11, "bold"), 
                            bg=self.colors['section_bg'], 
                            fg=self.colors['text'])
        search_label.grid(row=0, column=0, sticky=W, padx=(0, 15))
        
        input_frame = Frame(search_inner, bg=self.colors['section_bg'])
        input_frame.grid(row=0, column=1, sticky=(W, E), padx=(0, 10))
        input_frame.columnconfigure(0, weight=1)
        
        self.location_entry = Entry(input_frame, font=("Segoe UI", 10), 
                                    relief=SOLID, bd=1, bg=self.colors['entry_bg'],
                                    fg=self.colors['text'],
                                    insertbackground=self.colors['text'])
        self.location_entry.grid(row=0, column=0, sticky=(W, E), padx=(0, 8), ipady=6)
        self.location_entry.bind("<Return>", lambda e: self.search_location())
        
        search_btn = Button(input_frame, text="🔍 Search", command=self.search_location,
                           font=("Segoe UI", 10, "bold"),
                           bg=self.colors['primary'],
                           fg='white',
                           activebackground=self.colors['primary_hover'],
                           activeforeground='white',
                           relief=FLAT,
                           padx=20,
                           pady=6,
                           cursor="hand2")
        search_btn.grid(row=0, column=1)
        
        # Suggestions section
        suggestions_section = Frame(content_frame, bg=self.colors['bg'], relief=FLAT, bd=0)
        suggestions_section.pack(fill=X, pady=(0, 10))
        suggestions_container = Frame(suggestions_section, bg=self.colors['border'], padx=1, pady=1)
        suggestions_container.pack(fill=X)
        suggestions_inner = Frame(suggestions_container, bg=self.colors['section_bg'], padx=15, pady=12)
        suggestions_inner.pack(fill=BOTH, expand=True)
        suggestions_inner.columnconfigure(0, weight=1)
        
        sugg_label = Label(suggestions_inner, text="📍 Suggestions", 
                          font=("Segoe UI", 11, "bold"), 
                          bg=self.colors['section_bg'], 
                          fg=self.colors['text'])
        sugg_label.grid(row=0, column=0, sticky=W, pady=(0, 8))
        
        listbox_frame = Frame(suggestions_inner, bg=self.colors['section_bg'])
        listbox_frame.grid(row=1, column=0, sticky=(W, E), pady=(0, 8))
        listbox_frame.columnconfigure(0, weight=1)
        
        self.suggestions_listbox = Listbox(listbox_frame, height=5, 
                                          font=("Segoe UI", 10),
                                          bg=self.colors['listbox_bg'],
                                          fg=self.colors['text'],
                                          selectbackground=self.colors['selected'],
                                          selectforeground='white',
                                          relief=SOLID,
                                          bd=1,
                                          highlightthickness=0)
        self.suggestions_listbox.grid(row=0, column=0, sticky=(W, E))
        scrollbar_sugg = ttk.Scrollbar(listbox_frame, orient=VERTICAL, 
                                       command=self.suggestions_listbox.yview)
        scrollbar_sugg.grid(row=0, column=1, sticky=(N, S))
        self.suggestions_listbox.config(yscrollcommand=scrollbar_sugg.set)
        self.suggestions_listbox.bind("<Double-Button-1>", lambda e: self.add_location())
        
        add_btn = Button(suggestions_inner, text="➕ Add Selected", command=self.add_location,
                        font=("Segoe UI", 10, "bold"),
                        bg=self.colors['success'],
                        fg='white',
                        activebackground=self.colors['success_hover'],
                        activeforeground='white',
                        relief=FLAT,
                        padx=15,
                        pady=6,
                        cursor="hand2")
        add_btn.grid(row=2, column=0, pady=(0, 5))
        
        # Selected locations section
        locations_section = Frame(content_frame, bg=self.colors['bg'], relief=FLAT, bd=0)
        locations_section.pack(fill=X, pady=(0, 10))
        locations_container = Frame(locations_section, bg=self.colors['border'], padx=1, pady=1)
        locations_container.pack(fill=X)
        locations_inner = Frame(locations_container, bg=self.colors['section_bg'], padx=15, pady=12)
        locations_inner.pack(fill=BOTH, expand=True)
        locations_inner.columnconfigure(0, weight=1)
        
        loc_label = Label(locations_inner, text="🗺️ Selected Locations", 
                         font=("Segoe UI", 11, "bold"), 
                         bg=self.colors['section_bg'], 
                         fg=self.colors['text'])
        loc_label.grid(row=0, column=0, sticky=W, pady=(0, 8))
        
        loc_listbox_frame = Frame(locations_inner, bg=self.colors['section_bg'])
        loc_listbox_frame.grid(row=1, column=0, sticky=(W, E), pady=(0, 10))
        loc_listbox_frame.columnconfigure(0, weight=1)
        
        self.locations_listbox = Listbox(loc_listbox_frame, height=4, 
                                        font=("Segoe UI", 10),
                                        bg=self.colors['listbox_bg'],
                                        fg=self.colors['text'],
                                        selectbackground=self.colors['selected'],
                                        selectforeground='white',
                                        relief=SOLID,
                                        bd=1,
                                        highlightthickness=0)
        self.locations_listbox.grid(row=0, column=0, sticky=(W, E))
        scrollbar_loc = ttk.Scrollbar(loc_listbox_frame, orient=VERTICAL, 
                                     command=self.locations_listbox.yview)
        scrollbar_loc.grid(row=0, column=1, sticky=(N, S))
        self.locations_listbox.config(yscrollcommand=scrollbar_loc.set)
        
        loc_buttons_frame = Frame(locations_inner, bg=self.colors['section_bg'])
        loc_buttons_frame.grid(row=2, column=0, pady=(0, 5))
        
        remove_btn = Button(loc_buttons_frame, text="➖ Remove", command=self.remove_location,
                           font=("Segoe UI", 10),
                           bg=self.colors['warning'],
                           fg='white',
                           activebackground=self.colors['warning_hover'],
                           activeforeground='white',
                           relief=FLAT,
                           padx=12,
                           pady=6,
                           cursor="hand2")
        remove_btn.pack(side=LEFT, padx=3)
        
        clear_btn = Button(loc_buttons_frame, text="🗑️ Clear All", command=self.clear_locations,
                          font=("Segoe UI", 10),
                          bg=self.colors['danger'],
                          fg='white',
                          activebackground=self.colors['danger_hover'],
                          activeforeground='white',
                          relief=FLAT,
                          padx=12,
                          pady=6,
                          cursor="hand2")
        clear_btn.pack(side=LEFT, padx=3)
        
        calculate_btn = Button(loc_buttons_frame, text="🚀 Calculate Route", 
                              command=self.calculate_route,
                              font=("Segoe UI", 11, "bold"),
                              bg=self.colors['primary'],
                              fg='white',
                              activebackground=self.colors['primary_hover'],
                              activeforeground='white',
                              relief=FLAT,
                              padx=20,
                              pady=8,
                              cursor="hand2")
        calculate_btn.pack(side=LEFT, padx=10)
        
        # Route display section
        route_section = Frame(content_frame, bg=self.colors['bg'], relief=FLAT, bd=0)
        route_section.pack(fill=BOTH, expand=True, pady=(0, 10))
        route_container = Frame(route_section, bg=self.colors['border'], padx=1, pady=1)
        route_container.pack(fill=BOTH, expand=True)
        route_inner = Frame(route_container, bg=self.colors['section_bg'], padx=15, pady=12)
        route_inner.pack(fill=BOTH, expand=True)
        route_inner.columnconfigure(0, weight=1)
        route_inner.rowconfigure(1, weight=1)
        
        route_label = Label(route_inner, text="📊 Route Information", 
                           font=("Segoe UI", 11, "bold"), 
                           bg=self.colors['section_bg'], 
                           fg=self.colors['text'])
        route_label.grid(row=0, column=0, sticky=W, pady=(0, 8))
        
        # Create notebook for route summary and instructions
        notebook = ttk.Notebook(route_inner)
        notebook.grid(row=1, column=0, sticky=(W, E, N, S))
        
        # Summary tab
        summary_frame = Frame(notebook, bg=self.colors['listbox_bg'], padx=10, pady=10)
        notebook.add(summary_frame, text="📋 Summary")
        self.summary_text = Text(summary_frame, wrap=WORD, 
                                font=("Segoe UI", 11),
                                bg=self.colors['listbox_bg'],
                                fg=self.colors['text'],
                                relief=FLAT,
                                bd=0,
                                padx=10,
                                pady=10,
                                state=DISABLED)
        summary_scroll = ttk.Scrollbar(summary_frame, orient=VERTICAL, 
                                      command=self.summary_text.yview)
        self.summary_text.config(yscrollcommand=summary_scroll.set)
        self.summary_text.pack(side=LEFT, fill=BOTH, expand=True)
        summary_scroll.pack(side=RIGHT, fill=Y)
        
        # Instructions tab
        instructions_frame = Frame(notebook, bg=self.colors['listbox_bg'], padx=10, pady=10)
        notebook.add(instructions_frame, text="📝 Instructions")
        self.instructions_text = Text(instructions_frame, wrap=WORD, 
                                     font=("Segoe UI", 10),
                                     bg=self.colors['listbox_bg'],
                                     fg=self.colors['text'],
                                     relief=FLAT,
                                     bd=0,
                                     padx=10,
                                     pady=10,
                                     state=DISABLED)
        instructions_scroll = ttk.Scrollbar(instructions_frame, orient=VERTICAL, 
                                           command=self.instructions_text.yview)
        self.instructions_text.config(yscrollcommand=instructions_scroll.set)
        self.instructions_text.pack(side=LEFT, fill=BOTH, expand=True)
        instructions_scroll.pack(side=RIGHT, fill=Y)
        
        # Export section
        export_section = Frame(content_frame, bg=self.colors['bg'], relief=FLAT, bd=0)
        export_section.pack(fill=X, pady=(0, 10))
        export_container = Frame(export_section, bg=self.colors['border'], padx=1, pady=1)
        export_container.pack(fill=X)
        export_inner = Frame(export_container, bg=self.colors['section_bg'], padx=15, pady=12)
        export_inner.pack(fill=X)
        
        export_label = Label(export_inner, text="💾 Export Route", 
                            font=("Segoe UI", 11, "bold"), 
                            bg=self.colors['section_bg'], 
                            fg=self.colors['text'])
        export_label.pack(side=LEFT, padx=(0, 15))
        
        export_btn_frame = Frame(export_inner, bg=self.colors['section_bg'])
        export_btn_frame.pack(side=LEFT)
        
        export_buttons = [
            ("📄 TXT", "txt", self.colors['primary']),
            ("📊 JSON", "json", self.colors['success']),
            ("📈 CSV", "csv", self.colors['warning'])
        ]
        
        for btn_text, fmt, color in export_buttons:
            btn = Button(export_btn_frame, text=btn_text, 
                        command=lambda f=fmt: self.export_route(f),
                        font=("Segoe UI", 10, "bold"),
                        bg=color,
                        fg='white',
                        activebackground=color,
                        activeforeground='white',
                        relief=FLAT,
                        padx=15,
                        pady=6,
                        cursor="hand2")
            btn.pack(side=LEFT, padx=5)
        
        # Status bar
        status_frame = Frame(root, bg=self.colors['header_bg'], height=30)
        status_frame.pack(fill=X, side=BOTTOM)
        status_frame.pack_propagate(False)
        self.status_var = StringVar(value="✅ Ready")
        status_bar = Label(status_frame, textvariable=self.status_var, 
                          bg=self.colors['header_bg'], 
                          fg=self.colors['header_fg'],
                          font=("Segoe UI", 9),
                          anchor=W,
                          padx=10)
        status_bar.pack(fill=X)
    
    def setup_styles(self, style):
        """Configure ttk styles for a modern look"""
        style.configure('TFrame', background=self.colors['section_bg'])
        style.configure('TLabel', background=self.colors['section_bg'], 
                       foreground=self.colors['text'], font=("Segoe UI", 10))
        style.configure('TButton', font=("Segoe UI", 10))
        style.configure('TNotebook', background=self.colors['section_bg'], borderwidth=0)
        style.configure('TNotebook.Tab', padding=[20, 10], font=("Segoe UI", 10))
        style.map('TNotebook.Tab',
                 background=[('selected', self.colors['primary'])],
                 foreground=[('selected', 'white')])
    
    def search_location(self):
        query = self.location_entry.get().strip()
        if not query:
            messagebox.showwarning("Warning", "Please enter a location to search.")
            return
        
        self.status_var.set("🔍 Searching for locations...")
        self.root.update()
        
        def do_search():
            try:
                sugg = geocode_suggestions(query, limit=5)
                self.root.after(0, self.update_suggestions, sugg)
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Search failed: {e}"))
                self.root.after(0, lambda: self.status_var.set("❌ Search failed"))
        
        Thread(target=do_search, daemon=True).start()
    
    def update_suggestions(self, sugg):
        self.suggestions_listbox.delete(0, END)
        self.current_suggestions = []
        
        if not sugg["ok"]:
            messagebox.showerror("Error", sugg.get("msg", "Failed to get suggestions"))
            self.status_var.set("❌ Search failed")
            return
        
        self.current_suggestions = sugg["hits"]
        for hit in sugg["hits"]:
            self.suggestions_listbox.insert(END, hit["name"])
        
        if sugg["hits"]:
            self.suggestions_listbox.selection_set(0)
            self.status_var.set(f"✅ Found {len(sugg['hits'])} suggestion(s)")
        else:
            self.status_var.set("⚠️ No suggestions found")
    
    def add_location(self):
        selection = self.suggestions_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a location from suggestions.")
            return
        
        idx = selection[0]
        if idx < len(self.current_suggestions):
            hit = self.current_suggestions[idx]
            self.locations.append(hit)
            self.locations_listbox.insert(END, hit["name"])
            self.status_var.set(f"✅ Added: {hit['name']}")
            self.location_entry.delete(0, END)
            self.suggestions_listbox.delete(0, END)
            self.current_suggestions = []
    
    def remove_location(self):
        selection = self.locations_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a location to remove.")
            return
        
        idx = selection[0]
        self.locations_listbox.delete(idx)
        self.locations.pop(idx)
        self.status_var.set("✅ Location removed")
    
    def clear_locations(self):
        if self.locations:
            if messagebox.askyesno("Confirm", "Clear all locations?"):
                self.locations.clear()
                self.locations_listbox.delete(0, END)
                self.route_data = None
                self.route_path = None
                self.clear_route_display()
                self.status_var.set("✅ All locations cleared")
    
    def calculate_route(self):
        if len(self.locations) < 2:
            messagebox.showwarning("Warning", "Please add at least 2 locations to calculate a route.")
            return
        
        vehicle = self.vehicle_var.get()
        coords = [(loc["lat"], loc["lng"]) for loc in self.locations]
        names = [loc["name"] for loc in self.locations]
        
        self.status_var.set("🚀 Calculating route...")
        self.root.update()
        
        def do_calculate():
            try:
                r = route_points(coords, vehicle=vehicle)
                self.root.after(0, self.update_route, r, names)
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Route calculation failed: {e}"))
                self.root.after(0, lambda: self.status_var.set("❌ Route calculation failed"))
        
        Thread(target=do_calculate, daemon=True).start()
    
    def update_route(self, route_result, names):
        if not route_result["ok"]:
            messagebox.showerror("Error", route_result.get("msg", "Failed to calculate route"))
            self.status_var.set("❌ Route calculation failed")
            return
        
        self.route_data = route_result["data"]
        self.route_path = route_result["data"]["paths"][0]
        self.display_route(self.route_path, names)
        self.status_var.set("✅ Route calculated successfully")
    
    def display_route(self, path, names):
        dist_m = path["distance"]
        time_ms = path["time"]
        km = dist_m / 1000
        miles = km / 1.60934
        vehicle = path.get('profile', 'car')
        vehicle_icon = {"car": "🚗", "bike": "🚴", "foot": "🚶"}.get(vehicle, "🚗")
        
        # Update summary with better formatting
        self.summary_text.config(state=NORMAL)
        self.summary_text.delete(1.0, END)
        
        summary = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        summary += "           ROUTE SUMMARY\n"
        summary += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        summary += "📍 ROUTE:\n"
        summary += f"   From: {names[0]}\n"
        for i in range(1, len(names)):
            summary += f"   → To: {names[i]}\n"
        
        summary += f"\n{vehicle_icon} VEHICLE: {vehicle.upper()}\n"
        summary += f"📏 DISTANCE: {km:.2f} km ({miles:.2f} miles)\n"
        summary += f"⏱️  DURATION: {format_duration(time_ms)}\n"
        summary += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        
        self.summary_text.insert(1.0, summary)
        self.summary_text.config(state=DISABLED)
        
        # Update instructions with better formatting
        self.instructions_text.config(state=NORMAL)
        self.instructions_text.delete(1.0, END)
        
        instructions = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        instructions += "      STEP-BY-STEP INSTRUCTIONS\n"
        instructions += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for i, step in enumerate(path.get("instructions", []), 1):
            text = step.get("text", "")
            dist_km = step.get("distance", 0) / 1000.0
            instructions += f"Step {i:>3}: {text}\n"
            instructions += f"          Distance: {dist_km:.2f} km\n\n"
        
        self.instructions_text.insert(1.0, instructions)
        self.instructions_text.config(state=DISABLED)
    
    def clear_route_display(self):
        self.summary_text.config(state=NORMAL)
        self.summary_text.delete(1.0, END)
        self.summary_text.config(state=DISABLED)
        
        self.instructions_text.config(state=NORMAL)
        self.instructions_text.delete(1.0, END)
        self.instructions_text.config(state=DISABLED)
    
    def export_route(self, format_type):
        if not self.route_path or not self.locations:
            messagebox.showwarning("Warning", "Please calculate a route first.")
            return
        
        names = [loc["name"] for loc in self.locations]
        vehicle = self.vehicle_var.get()
        
        # Get filename from user
        extensions = {
            "txt": "*.txt",
            "json": "*.json",
            "csv": "*.csv"
        }
        
        filename = filedialog.asksaveasfilename(
            defaultextension=f".{format_type}",
            filetypes=[(format_type.upper(), extensions[format_type]), ("All files", "*.*")],
            title=f"Export route as {format_type.upper()}"
        )
        
        if not filename:
            return
        
        self.status_var.set(f"💾 Exporting to {format_type.upper()}...")
        self.root.update()
        
        try:
            if format_type == "txt":
                export_route_txt(filename, self.route_path, names)
            elif format_type == "json":
                export_route_json(filename, self.route_path, names, self.route_data)
            elif format_type == "csv":
                export_route_csv(filename, self.route_path, names)
            
            messagebox.showinfo("Success", f"✅ Route exported successfully to:\n{filename}")
            self.status_var.set(f"✅ Exported to {filename}")
        except Exception as e:
            messagebox.showerror("Error", f"❌ Failed to export route: {e}")
            self.status_var.set("❌ Export failed")

def main_gui():
    """Launch the GUI version"""
    if GRAPHOPPER_KEY in ("", "YOUR_API_KEY"):
        messagebox.showerror("Error", "Please set GRAPHHOPPER_KEY environment variable or replace YOUR_API_KEY in the code.")
        return
    
    root = Tk()
    app = RoutePlannerGUI(root)
    root.mainloop()

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
    # Check for command line argument to use CLI mode
    if len(sys.argv) > 1 and sys.argv[1].lower() in ["--cli", "-c", "cli"]:
        main()
    else:
        # Default to GUI mode
        main_gui()
