"""
check_coordinates.py
Compares x/y coordinates in square_data.json against markers.json (source of truth).

For locations with a numeric id: looks up that id directly in markers.json.
For locations with id=null: tries exact then fuzzy name matching, picking the
nearest marker (by coordinate distance) among name-matches above a similarity
threshold.

Run:  python jack/test/check_coordinates.py
      python jack/test/check_coordinates.py --threshold 2.0   (change tolerance)
"""

import json, sys, math
from difflib import SequenceMatcher
from pathlib import Path

# ── config ────────────────────────────────────────────────────────────────────
COORD_THRESHOLD = float(sys.argv[sys.argv.index("--threshold") + 1]
                        if "--threshold" in sys.argv else 2.0)
FUZZY_SIM_MIN   = 0.72   # minimum name similarity to attempt a match

DATA_DIR = Path(__file__).resolve().parents[2] / "jack" / "data"
MARKERS_PATH    = DATA_DIR / "markers.json"
SQUARE_DATA_PATH = DATA_DIR / "square_data.json"
# ──────────────────────────────────────────────────────────────────────────────


def load():
    with open(MARKERS_PATH, encoding="utf-8") as f:
        markers = json.load(f)
    with open(SQUARE_DATA_PATH, encoding="utf-8") as f:
        sq_data = json.load(f)
    return markers, sq_data["squares"]


def dist(ax, ay, bx, by):
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


def sim(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def collect_locations(sq_data):
    """Yield (square_name, loc_dict) for every location in every square."""
    for sq_name, sq in sq_data.items():
        for loc in sq.get("locations", []):
            yield sq_name, loc
        for boss in sq.get("bosses", []):
            for loc in boss.get("locations", []):
                yield sq_name, loc
        for group in sq.get("groups", []):
            for loc in group.get("locations", []):
                yield sq_name, loc


def find_fuzzy(lname, lx, ly, markers):
    """
    Return (best_marker, method_note) where method_note explains which kind
    of match was used.  Returns (None, reason) if no useful match found.
    """
    candidates = []
    for m in markers:
        s = sim(lname, m["name"])
        if s >= FUZZY_SIM_MIN:
            d = dist(lx, ly, m["x"], m["y"])
            candidates.append((s, d, m))

    if not candidates:
        return None, "no name match above threshold"

    # Among candidates, prefer the one whose coordinates are closest.
    # If multiple markers have the same name, this naturally picks the right one.
    candidates.sort(key=lambda t: (t[1], -t[0]))  # sort by coord-dist asc, sim desc
    s, d, best = candidates[0]
    note = f"name-sim={s:.2f}, coord-dist={d:.2f}"

    # Also find the closest candidate purely by coordinate (sanity check)
    closest_by_coord = min(candidates, key=lambda t: t[1])
    if closest_by_coord[2]["id"] != best["id"]:
        note += f" (closest-by-coord: id={closest_by_coord[2]['id']!r} '{closest_by_coord[2]['name']}' dist={closest_by_coord[1]:.2f})"

    return best, note


def run():
    markers, sq_data = load()
    marker_by_id = {m["id"]: m for m in markers}

    results = {
        "id_match":      [],   # had numeric id, exact marker lookup
        "name_match":    [],   # null id, fuzzy name + coord match
        "no_match":      [],   # null id, couldn't find a marker
        "null_coords":   [],   # location has no x/y to compare
    }

    total = 0
    for sq_name, loc in collect_locations(sq_data):
        total += 1
        lid  = loc.get("id")
        lx   = loc.get("x")
        ly   = loc.get("y")
        lname = loc.get("name", "?")

        if lx is None or ly is None:
            results["null_coords"].append({"square": sq_name, "loc": lname, "id": lid})
            continue

        if lid is not None:
            # ── ID-based match ─────────────────────────────────────────────
            m = marker_by_id.get(lid)
            if m is None:
                results["no_match"].append({
                    "square": sq_name, "loc": lname, "id": lid,
                    "note": "id not found in markers.json"
                })
                continue
            dx = abs(m["x"] - lx)
            dy = abs(m["y"] - ly)
            if dx > COORD_THRESHOLD or dy > COORD_THRESHOLD:
                results["id_match"].append({
                    "square": sq_name, "loc": lname, "id": lid,
                    "sq_x": lx,  "sq_y": ly,
                    "mk_x": m["x"], "mk_y": m["y"],
                    "mk_name": m["name"],
                    "dx": dx, "dy": dy,
                })
        else:
            # ── Name-based fuzzy match ─────────────────────────────────────
            m, note = find_fuzzy(lname, lx, ly, markers)
            if m is None:
                results["no_match"].append({
                    "square": sq_name, "loc": lname, "id": None, "note": note
                })
                continue
            dx = abs(m["x"] - lx)
            dy = abs(m["y"] - ly)
            if dx > COORD_THRESHOLD or dy > COORD_THRESHOLD:
                results["name_match"].append({
                    "square": sq_name, "loc": lname, "id": None,
                    "sq_x": lx,  "sq_y": ly,
                    "mk_x": m["x"], "mk_y": m["y"],
                    "mk_name": m["name"], "mk_id": m["id"],
                    "dx": dx, "dy": dy,
                    "note": note,
                })

    # ── Print report ──────────────────────────────────────────────────────────
    sep = "=" * 72

    print(sep)
    print(f"COORDINATE CHECK — square_data.json vs markers.json")
    print(f"Threshold: {COORD_THRESHOLD} units  |  Total locations checked: {total}")
    print(sep)

    # ID-based mismatches (most reliable — always real errors)
    id_issues = sorted(results["id_match"], key=lambda r: max(r["dx"], r["dy"]), reverse=True)
    print(f"\n[A] ID-MATCHED MISMATCHES  ({len(id_issues)} found)")
    print("    These have a numeric id in square_data.json that resolves to a marker")
    print("    with different coordinates — almost certainly a data error.\n")
    if not id_issues:
        print("    None — all id-matched locations have correct coordinates.\n")
    for r in id_issues:
        print(f"  Square : {r['square']!r}")
        print(f"  Loc    : {r['loc']!r}  (id={r['id']}  marker='{r['mk_name']}')")
        print(f"  In data: x={r['sq_x']},  y={r['sq_y']}")
        print(f"  Marker : x={r['mk_x']},  y={r['mk_y']}")
        print(f"  Diff   : dx={r['dx']:.3f},  dy={r['dy']:.3f}\n")

    # Name-matched mismatches (may have false positives if name is ambiguous)
    nm_issues = sorted(results["name_match"], key=lambda r: max(r["dx"], r["dy"]), reverse=True)
    print(f"[B] NAME-MATCHED MISMATCHES  ({len(nm_issues)} found)")
    print("    Null-id locations matched by fuzzy name.  Large diffs = probable error;")
    print("    small diffs = likely just a different reference point (entrance vs boss).\n")
    if not nm_issues:
        print("    None.\n")
    for r in nm_issues:
        print(f"  Square : {r['square']!r}")
        print(f"  Loc    : {r['loc']!r}")
        print(f"  Match  : id={r['mk_id']!r}  '{r['mk_name']}'  ({r['note']})")
        print(f"  In data: x={r['sq_x']},  y={r['sq_y']}")
        print(f"  Marker : x={r['mk_x']},  y={r['mk_y']}")
        print(f"  Diff   : dx={r['dx']:.3f},  dy={r['dy']:.3f}\n")

    # No match at all
    print(f"[C] NO MARKER MATCH  ({len(results['no_match'])} locations)")
    print("    Null-id locations where no similar marker name was found.")
    print("    These may be fine (custom locations not in markers.json).\n")
    for r in results["no_match"]:
        print(f"  [{r['square']!r}] '{r['loc']}'  id={r['id']}  — {r['note']}")

    print(f"\n[D] NULL COORDINATES  ({len(results['null_coords'])} locations)")
    print("    Locations with no x/y — map display will be broken.\n")
    for r in results["null_coords"]:
        print(f"  [{r['square']!r}] '{r['loc']}'")

    print(f"\n{sep}")
    total_issues = len(id_issues) + len(nm_issues)
    print(f"SUMMARY: {total_issues} coordinate mismatches  |  "
          f"{len(results['no_match'])} unmatchable  |  "
          f"{len(results['null_coords'])} null-coord locations")
    print(sep)


if __name__ == "__main__":
    run()
