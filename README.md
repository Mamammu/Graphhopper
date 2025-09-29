### Graphhopper CLI Helper

A small CLI helper around GraphHopper Geocoding and Routing APIs. Enter multiple locations, pick from suggested similar places, and get a route summary and optional step-by-step instructions.

### Prerequisites
- Python 3.8+
- A GraphHopper API key

### Setup
```bash
# From the project directory
python -m venv .venv
.venv\\Scripts\\activate  # Windows PowerShell
pip install -r requirements.txt

# Set your API key (PowerShell)
$env:GRAPHHOPPER_KEY = "YOUR_API_KEY"
```

### Run
```bash
python grapphopper.py
```

### Sample I/O
Input (interactive):
```
Vehicle profile (car/bike/foot) [car]: car

Enter locations in order. Leave blank to finish.
Start: Paris
Did you mean:
  1. Paris, Île-de-France, France  (48.85661, 2.35222)
  2. Paris, Texas, United States   (33.66094, -95.55551)
Select 1-5 [1], or 0 to re-enter: 1
✓ Paris, Île-de-France, France (48.85661, 2.35222)
Stop 1: Berlin
Did you mean:
  1. Berlin, Germany (52.52001, 13.40495)
Select 1-5 [1], or 0 to re-enter: 1
✓ Berlin, Germany (52.52001, 13.40495)

Requesting route for 2 point(s)...

=== Route Summary ===
From: Paris, Île-de-France, France
  → Berlin, Germany
Vehicle: car
Distance: 1054.32 km (655.01 mi)
Duration: 09:45:18
```

Optionally:
```
Show full step-by-step? (y/N): y
=== Step-by-step Instructions ===
 1. Head east on ... [0.50 km]
 2. Merge onto ...  [12.30 km]
 ...
```

### Known Limits
- Geocoding suggestions: top 5 candidates only.
- Routing: basic profile selection (car/bike/foot); no advanced options.
- API rate limits and quotas apply per GraphHopper plan.
- Requires internet connectivity to call GraphHopper APIs.
- Coordinates are shown with 5 decimal places.

### Notes
- The `GRAPHHOPPER_KEY` can be set in the environment before running. If not set, the script will use the value embedded in code if present.
- Reports can be saved to a timestamped `.txt` via the final prompt.

