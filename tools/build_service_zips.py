"""Generate static/data/service-zips.json: Ohio ZIPs near Chardon -> miles.

Straight-line distance from the 44024 (Chardon) ZIP centroid, using the
`zipcodes` package (dev-only: pip install -r requirements-dev.txt). The site
uses it to flag quote requests as standard (<=15 mi), extended (15-25 mi) or
outside (>25 mi) — matching the service-area rules on /services.
"""
import json
import math
import os

import zipcodes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "static", "data", "service-zips.json")
MAX_MILES = 40
LAT0, LON0 = 41.5719, -81.2056  # 44024 centroid


def miles(lat, lon):
    r = 3958.8
    p1, p2 = math.radians(LAT0), math.radians(lat)
    dp, dl = p2 - p1, math.radians(lon - LON0)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def main():
    out = {}
    for z in zipcodes.filter_by(state="OH"):
        if not z.get("lat"):
            continue
        d = miles(float(z["lat"]), float(z["long"]))
        if d <= MAX_MILES:
            out[z["zip_code"]] = round(d, 1)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(dict(sorted(out.items())), fh, separators=(",", ":"))
    print(len(out), "ZIPs written")


if __name__ == "__main__":
    main()
