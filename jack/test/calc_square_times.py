#!/usr/bin/env python3
"""
calc_square_times.py — Jack of All Graves
Estimates completion time for every bingo square at multiple weapon levels.

Usage:
    python calc_square_times.py
    python calc_square_times.py --weapon-class Katana --stat Dexterity
    python calc_square_times.py --somber
    python calc_square_times.py --csv > times.csv
    python calc_square_times.py --sort wl0

Weapon levels shown (standard):  +0  +5  +10  +15  +20
Weapon levels shown (--somber):   +0  +3   +6   +9

Rune levels are estimated from typical S6 speedrun progression and affect
stat-scaling contributions to AR (not weapon upgrade multipliers).
"""

import json, math, argparse, os, re, sys, io
from contextlib import redirect_stdout

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(SCRIPT_DIR, '..', 'data')

# ── Boss HP / Defense (ported from timing.js BOSS_HP) ─────────────────────────
BOSS_HP = {
    'ancestor spirit':                             {'hp':  4393, 'def': 107},
    'astel, naturalborn of the void':              {'hp': 11170, 'def': 114},
    'astel, stars of darkness':                    {'hp': 18617, 'def': 120},
    'beast clergyman':                             {'hp': 16461, 'def': 120},
    'bell bearing hunter':                         {'hp':  2495, 'def': 103},
    'black blade kindred':                         {'hp': 12297, 'def': 121},
    'bloodhound knight darriwil':                  {'hp':  1450, 'def': 103},
    'bloodhound knight':                           {'hp':  1985, 'def': 107},
    'borealis the freezing fog':                   {'hp': 11268, 'def': 120},
    'cemetery shade':                              {'hp':   781, 'def': 102},
    "commander o'neil":                            {'hp':  9210, 'def': 111},
    'crucible knight':                             {'hp':  2782, 'def': 103},
    'crucible knight and crucible knight ordovis': {'hp':  5460, 'def': 111},
    'death rite bird':                             {'hp':  6577, 'def': 110},
    'deathbird':                                   {'hp':  3442, 'def': 103},
    'draconic tree sentinel':                      {'hp':  8398, 'def': 114},
    'dragonkin soldier':                           {'hp':  5758, 'def': 114},
    'dragonlord placidusax':                       {'hp': 26651, 'def': 121},
    'elemer of the briar':                         {'hp':  4897, 'def': 111},
    'erdtree avatar':                              {'hp':  3163, 'def': 105},
    'fallingstar beast':                           {'hp':  5780, 'def': 111},
    "fia's champions":                             {'hp': 12217, 'def': 130},
    'fire giant':                                  {'hp': 43263, 'def': 118},
    'flying dragon agheel':                        {'hp':  3200, 'def': 106},
    'godfrey, first elden lord':                   {'hp':  7099, 'def': 114},
    'godrick the grafted':                         {'hp':  6080, 'def': 105},
    'godskin apostle':                             {'hp': 10562, 'def': 116},
    'godskin duo':                                 {'hp':  8000, 'def': 118},
    'godskin noble':                               {'hp': 10060, 'def': 114},
    'grafted scion':                               {'hp':  2596, 'def': 107},
    'leonine misbegotten':                         {'hp':  2199, 'def': 103},
    'loretta, knight of the haligtree':            {'hp': 13397, 'def': 122},
    'magma wyrm':                                  {'hp':  7141, 'def': 109},
    'malenia, blade of miquella':                  {'hp': 33251, 'def': 123},
    'margit, the fell omen':                       {'hp':  4174, 'def': 103},
    'mimic tear':                                  {'hp':  1242, 'def':  75},
    'misbegotten crusader':                        {'hp':  9130, 'def': 120},
    'misbegotten warrior and crucible knight':     {'hp':  3569, 'def': 110},
    'mohg, lord of blood':                         {'hp': 18389, 'def': 122},
    'mohg, the omen':                              {'hp': 14000, 'def': 117},
    'morgott, the omen king':                      {'hp': 10399, 'def': 114},
    "night's cavalry":                             {'hp':  1665, 'def': 103},
    "night's cavalry duo":                         {'hp':  7246, 'def': 122},
    'omenkiller':                                  {'hp':  2306, 'def': 110},
    'putrid crystalian trio':                      {'hp':  3358, 'def': 109},
    'red wolf of radagon':                         {'hp':  2204, 'def': 107},
    'regal ancestor spirit':                       {'hp':  6301, 'def': 111},
    'rennala, queen of the full moon':             {'hp':  7590, 'def': 109},
    'roundtable knight vyke':                      {'hp':  5366, 'def': 104},
    'royal knight loretta':                        {'hp':  4214, 'def': 107},
    'soldier of godrick':                          {'hp':   384, 'def': 100},
    'starscourge radahn':                          {'hp':  9572, 'def': 113},
    'tibia mariner':                               {'hp':  3176, 'def': 103},
    'tree sentinel':                               {'hp':  2889, 'def': 103},
    'tree sentinel duo':                           {'hp':  6461, 'def': 113},
    'valiant gargoyle duo':                        {'hp':  5671, 'def': 111},
    'wormface':                                    {'hp':  5876, 'def': 113},
}

# ── Weapon DPS factors (MV/100 × hits/sec, from timing.js) ────────────────────
WEAPON_DPS_FACTOR = {
    'Dagger':                2.23, 'Throwing Blade':        1.42,
    'Straight Sword':        1.83, 'Light Greatsword':      1.52,
    'Greatsword':            1.24, 'Colossal Sword':        0.78,
    'Thrusting Sword':       2.03, 'Heavy Thrusting Sword': 1.62,
    'Curved Sword':          1.93, 'Curved Greatsword':     1.36,
    'Backhand Blade':        2.13, 'Katana':                1.83,
    'Great Katana':          1.24, 'Twinblade':             2.03,
    'Axe':                   1.62, 'Greataxe':              1.03,
    'Hammer':                1.53, 'Flail':                 1.55,
    'Great Hammer':          0.93, 'Colossal Weapon':       0.72,
    'Spear':                 1.80, 'Great Spear':           1.24,
    'Halberd':               1.34, 'Reaper':                1.24,
    'Whip':                  1.64, 'Fist':                  2.44,
    'Hand-to-Hand':          1.42, 'Claw':                  2.23,
    'Beast Claw':            2.30, 'Glintstone Staff':      1.01,
    'Sacred Seal':           1.01,
}

# ── Base AR per weapon class at +0 (from timing.js BASE_AR) ───────────────────
BASE_AR = {
    'Dagger':                110, 'Straight Sword':       130,
    'Light Greatsword':      140, 'Greatsword':           145,
    'Colossal Sword':        180, 'Thrusting Sword':      125,
    'Heavy Thrusting Sword': 145, 'Curved Sword':         120,
    'Curved Greatsword':     148, 'Backhand Blade':       115,
    'Katana':                130, 'Great Katana':         155,
    'Twinblade':             128, 'Axe':                  130,
    'Greataxe':              155, 'Hammer':               130,
    'Flail':                 128, 'Great Hammer':         162,
    'Colossal Weapon':       175, 'Spear':                120,
    'Great Spear':           155, 'Halberd':              148,
    'Reaper':                152, 'Whip':                 112,
    'Fist':                   95, 'Claw':                  97,
    'Sacred Seal':            75, 'Glintstone Staff':      80,
}

# ── Upgrade multipliers (from timing.js) ──────────────────────────────────────
SMITHING_MULT = [
    1.000, 1.058, 1.116, 1.174, 1.232, 1.290,
    1.348, 1.406, 1.464, 1.522, 1.580,
    1.620, 1.660, 1.700, 1.740, 1.780,
    1.820, 1.860, 1.900, 1.940, 1.980,
    2.020, 2.060, 2.100, 2.140,
]
SOMBER_MULT = [
    1.000, 1.125, 1.250, 1.375, 1.500,
    1.625, 1.750, 1.875, 2.000, 2.125,
]

# ── Stat scaling bonus as fraction of base AR (from timing.js) ────────────────
STAT_SCALING = {
    'Strength':  {'early': 0.25, 'mid': 0.50, 'late': 0.80},
    'Dexterity': {'early': 0.20, 'mid': 0.45, 'late': 0.70},
    'Faith':     {'early': 0.15, 'mid': 0.35, 'late': 0.60},
    'Int':       {'early': 0.15, 'mid': 0.35, 'late': 0.60},
    'Quality':   {'early': 0.22, 'mid': 0.47, 'late': 0.70},
}

# ── Travel speed (from timing.js) ─────────────────────────────────────────────
TRAVEL_SEC_PER_UNIT = 8.3
ZONE_SPEED_MULT = {
    'limgrave': 1.0,   'weeping_peninsula': 1.1,  'stormveil':    2.5,
    'siofra':   2.0,   'liurnia':           1.1,  'caria_manor':  2.2,
    'caelid':   1.1,   'dragonbarrow':      1.0,  'altus_plateau':1.0,
    'mt_gelmir':1.4,   'volcano_manor':     2.5,  'leyndell':     1.8,
    'deeproot': 2.2,   'ainsel':            2.0,  'mohgwyn':      2.0,
    'mountaintops': 1.1, 'consecrated':     1.1,  'haligtree':    2.8,
    'farum_azula': 2.5, 'unknown':          1.3,
}
# Zone routing penalty (from router.js) — reflects accessibility/progression tier,
# distinct from ZONE_SPEED_MULT which is raw movement speed.
ZONE_PENALTY = {
    'limgrave': 0.00, 'weeping_peninsula': 0.05, 'stormveil':   0.05,
    'siofra':   0.15, 'liurnia':           0.15, 'caria_manor': 0.20,
    'caelid':   0.20, 'dragonbarrow':      0.25, 'altus_plateau':0.30,
    'mt_gelmir':0.35, 'volcano_manor':     0.35, 'leyndell':    0.45,
    'deeproot': 0.45, 'ainsel':            0.40, 'mohgwyn':     0.55,
    'mountaintops': 0.60, 'consecrated':   0.65, 'haligtree':   0.70,
    'farum_azula': 0.75, 'unknown':         0.30,
}

ZONE_LABEL = {
    'limgrave': 'Limgrave',           'weeping_peninsula': 'Weeping Pen.',
    'stormveil': 'Stormveil',         'liurnia': 'Liurnia',
    'caria_manor': 'Caria Manor',     'caelid': 'Caelid',
    'dragonbarrow': 'Dragonbarrow',   'altus_plateau': 'Altus Plateau',
    'mt_gelmir': 'Mt. Gelmir',        'volcano_manor': 'Volcano Manor',
    'leyndell': 'Leyndell',           'deeproot': 'Deeproot',
    'siofra': 'Siofra/Nokron',        'ainsel': 'Ainsel/LoR',
    'mohgwyn': 'Mohgwyn',             'mountaintops': 'Mountaintops',
    'consecrated': 'Consecrated',     'haligtree': 'Haligtree',
    'farum_azula': 'Farum Azula',     'unknown': '?',
}

# ── Dungeon traversal overhead in seconds (from timing.js) ────────────────────
DUNGEON_OVERHEAD_SEC = {
    'catacombs': 240, 'cave': 180, 'tunnel': 180,
    'evergaol': 120,  'hero_grave': 360, 'dungeon': 200,
}
OVERHEAD_GRACE_SEC   = 10
OVERHEAD_BOSS_SEC    = 25
OVERHEAD_DUNGEON_SEC = 40
BOSS_UPTIME          = 0.60

# ── S6 starting graces (warp pool) ────────────────────────────────────────────
S6_GRACES = [
    {'id': 'sg_gatefront',   'x': -185.78, 'y': 102.10, 'level': 1},
    {'id': 'sg_consecrated', 'x':  -73.56, 'y': 141.78, 'level': 1},
    {'id': 'sg_haligtree',   'x':  -37.10, 'y': 149.13, 'level': 1},
    {'id': 'sg_snow_valley', 'x':  -64.63, 'y': 159.69, 'level': 1},
    {'id': 'sg_aeonia',      'x': -178.97, 'y': 143.06, 'level': 1},
    {'id': 'sg_ailing',      'x': -211.27, 'y': 112.20, 'level': 1},
    {'id': 'sg_scenic',      'x': -156.20, 'y':  67.88, 'level': 1},
    {'id': 'sg_labyrinth',   'x': -125.59, 'y':  73.51, 'level': 1},
    {'id': 'sg_altus_hwy',   'x': -100.79, 'y':  84.93, 'level': 1},
    {'id': 'sg_iniquity',    'x':  -84.37, 'y':  63.22, 'level': 1},
    {'id': 'sg_lake_rot',    'x': -128.46, 'y':  60.20, 'level': 2},
    {'id': 'sg_siofra',      'x': -184.90, 'y': 130.58, 'level': 2},
]

PASSIVE_TYPES = {'passive_runes', 'passive_stat', 'boss_modifier'}

# Map grace ID → short label for route display
GRACE_LABEL = {
    'sg_gatefront':   'Gatefront',
    'sg_consecrated': 'Consecrated',
    'sg_haligtree':   'Haligtree',
    'sg_snow_valley': 'Snow Valley',
    'sg_aeonia':      'Aeonia Swamp',
    'sg_ailing':      'Ailing Village',
    'sg_scenic':      'Scenic Isle',
    'sg_labyrinth':   'Labyrinth',
    'sg_altus_hwy':   'Altus Hwy',
    'sg_iniquity':    'Bridge of Iniquity',
    'sg_lake_rot':    'Lake of Rot',
    'sg_siofra':      'Siofra River',
}


class _Tee(io.TextIOBase):
    """Write to multiple streams simultaneously."""
    def __init__(self, *streams):
        self._streams = streams
    def write(self, data):
        for s in self._streams:
            s.write(data)
        return len(data)
    def flush(self):
        for s in self._streams:
            s.flush()

# ── Math helpers ───────────────────────────────────────────────────────────────

def _dist(a, b):
    return math.sqrt((a['x'] - b['x'])**2 + (a['y'] - b['y'])**2)


def _closest_grace(loc):
    is_ug = loc.get('level', 1) == 2
    pool  = [g for g in S6_GRACES if (g['level'] == 2) == is_ug] or S6_GRACES
    best  = min(pool, key=lambda g: _dist(g, loc))
    return best, _dist(best, loc)


def compute_ar(weapon_class, weapon_level, is_somber, primary_stat, rune_level):
    base = BASE_AR.get(weapon_class, 130)
    mult = (SOMBER_MULT[min(weapon_level, 9)]
            if is_somber else SMITHING_MULT[min(weapon_level, 24)])
    stat_tier   = 'early' if rune_level < 30 else ('mid' if rune_level < 60 else 'late')
    scaling     = STAT_SCALING.get(primary_stat, STAT_SCALING['Strength'])[stat_tier]
    return round(base * mult + base * scaling)


def compute_kill_sec(boss_name, weapon_class, weapon_level, is_somber, primary_stat, rune_level):
    """Returns kill time in seconds, or None if boss not in database."""
    key  = boss_name.lower()
    data = BOSS_HP.get(key)
    if not data:
        stripped = key.split('(')[0].strip()
        for k, v in BOSS_HP.items():
            if k in key or stripped in k or key in k:
                data = v
                break
    if not data:
        return None
    ar         = compute_ar(weapon_class, weapon_level, is_somber, primary_stat, rune_level)
    dps_factor = WEAPON_DPS_FACTOR.get(weapon_class, 1.4)
    hps        = dps_factor / 1.032
    dmg_hit    = (ar * ar) / (ar + data['def'])
    eff_dps    = dmg_hit * hps * BOSS_UPTIME
    return math.ceil(data['hp'] / eff_dps)


def _travel_sec(dist_units, zone_id):
    return math.ceil(dist_units * TRAVEL_SEC_PER_UNIT * ZONE_SPEED_MULT.get(zone_id, 1.3))


def _dungeon_overhead(dungeon_type_str):
    if not dungeon_type_str:
        return 0
    t = dungeon_type_str.lower()
    if 'catacomb' in t:                return DUNGEON_OVERHEAD_SEC['catacombs']
    if 'cave' in t or 'grotto' in t:   return DUNGEON_OVERHEAD_SEC['cave']
    if 'tunnel' in t or 'precipice' in t: return DUNGEON_OVERHEAD_SEC['tunnel']
    if 'evergaol' in t:                return DUNGEON_OVERHEAD_SEC['evergaol']
    if "hero" in t:                    return DUNGEON_OVERHEAD_SEC['hero_grave']
    return DUNGEON_OVERHEAD_SEC['dungeon']


def _fallback_kill_sec(zone_id):
    tier = {'limgrave':0,'weeping_peninsula':0,'stormveil':1,'liurnia':1,
            'caelid':2,'altus_plateau':2,'leyndell':3,'mountaintops':3,
            'haligtree':4,'farum_azula':4}.get(zone_id, 2)
    return [30, 60, 120, 180, 240][tier]


# ── Location helpers ───────────────────────────────────────────────────────────

def _extract_locs(sq_data):
    """Return all candidate locations from a square_data entry as a flat list."""
    locs = []
    def add(arr):
        for l in (arr or []):
            if isinstance(l, dict) and l.get('x') and l.get('y'):
                locs.append(l)

    t = sq_data.get('type', '')
    if t in ('boss_specific','dungeon_specific','npc_action','npc_invasion',
             'consumable_action','acquire_fixed'):
        add(sq_data.get('locations'))
        loc = sq_data.get('location')
        if isinstance(loc, dict) and loc.get('x'):
            locs.append(loc)
    elif t in ('boss_any','boss_count','dungeon_count','acquire_multi',
               'npc_kill','restore_rune'):
        add(sq_data.get('locations'))
    elif t == 'acquire_count':
        add(sq_data.get('locations'))
        add(sq_data.get('vendor_locations'))  # Sellen, Corhyn, Miriel etc.
    elif t == 'boss_region':
        add(sq_data.get('all_bosses'))
    elif t == 'boss_tag':
        add(sq_data.get('candidates'))
    elif t == 'boss_multi_type':
        for g in sq_data.get('groups', []):
            add(g.get('locations'))
    elif t == 'boss_multi_specific':
        for b in sq_data.get('bosses', []):
            add(b.get('locations'))
    else:
        add(sq_data.get('locations'))
        loc = sq_data.get('location')
        if isinstance(loc, dict) and loc.get('x'):
            locs.append(loc)

    # Deduplicate by rounded coordinates + level
    seen, unique = set(), []
    for l in locs:
        k = (round(l['x']*10), round(l['y']*10), l.get('level', 1))
        if k not in seen:
            seen.add(k)
            unique.append(l)
    return unique


def _adj_grace_cost(loc):
    """Zone-penalty-adjusted distance from nearest S6 grace — used for clustering."""
    _, d = _closest_grace(loc)
    zone = loc.get('zone', 'unknown')
    return d * (1 + ZONE_PENALTY.get(zone, 0.30))


def _subset_route_cost(locs_subset):
    """
    Approximate total route cost for visiting a set of locations.
    Greedy: always warp to the cheapest next stop (zone-penalty-adjusted).
    Mirrors router.js lineTravelCost logic for clustering decisions.
    """
    remaining = list(locs_subset)
    total = 0.0
    while remaining:
        costs = [_adj_grace_cost(l) for l in remaining]
        idx   = costs.index(min(costs))
        total += costs[idx]
        remaining.pop(idx)
    return total


def _pick_n_clustered(locs, n):
    """
    Pick n geographically accessible locations to minimise total route cost.
    Brute-force (C(M,N) subsets) for small N/M; zone-penalty-weighted greedy otherwise.
    Mirrors router.js clusterLocs.
    """
    from itertools import combinations as _combos
    if not locs:
        return []
    n = min(n, len(locs))
    if n == len(locs):
        return locs

    # Brute-force path: try all subsets, pick the one with lowest route cost
    if n <= 6 and len(locs) <= 20:
        best, best_cost = None, float('inf')
        for subset in _combos(locs, n):
            c = _subset_route_cost(subset)
            if c < best_cost:
                best_cost = c
                best = list(subset)
        return best

    # Greedy path: zone-penalty-adjusted anchor, then nearest zone-weighted neighbour
    anchor    = min(locs, key=_adj_grace_cost)
    chosen    = [anchor]
    remaining = [l for l in locs if l is not anchor]
    while len(chosen) < n and remaining:
        def _neighbor_cost(c):
            zone    = c.get('zone', 'unknown')
            penalty = 1 + ZONE_PENALTY.get(zone, 0.30)
            return min(_dist(c, ch) for ch in chosen) * penalty
        best = min(remaining, key=_neighbor_cost)
        chosen.append(best)
        remaining.remove(best)
    return chosen


# ── Per-location time estimate ─────────────────────────────────────────────────

def _time_loc(loc, stop_type, build):
    """
    Return (seconds, zone_id) for one visit to `loc`.
    Includes travel from nearest S6 grace + kill time (if boss) + overhead.
    """
    _, travel_dist = _closest_grace(loc)
    zone_id  = loc.get('zone', 'unknown')
    travel   = _travel_sec(travel_dist, zone_id)

    is_boss    = stop_type in ('boss_specific','boss_any','boss_count','boss_tag',
                               'boss_region','boss_multi_type','boss_multi_specific','prereq')
    is_dungeon = stop_type in ('dungeon_count','dungeon_specific')
    is_pickup  = stop_type in ('acquire_multi','acquire_count','acquire_fixed',
                               'npc_action','npc_invasion','npc_kill','restore_rune',
                               'consumable_action')

    kill = 0
    if is_boss:
        kill = compute_kill_sec(
            loc.get('name',''), build['weapon_class'], build['weapon_level'],
            build['is_somber'], build['primary_stat'], build['rune_level'],
        ) or _fallback_kill_sec(zone_id)

    overhead = OVERHEAD_GRACE_SEC
    if is_boss:    overhead += OVERHEAD_BOSS_SEC
    if is_dungeon: overhead += OVERHEAD_DUNGEON_SEC + _dungeon_overhead(loc.get('name',''))
    if is_pickup:  overhead += 30

    return travel + kill + overhead, zone_id


# ── Square-level time estimate ─────────────────────────────────────────────────

def estimate_square(sq_data, count, build):
    """
    Return (total_seconds, primary_zone_id).
    Returns (None, 'passive') for passive/modifier squares.
    """
    sq_type = sq_data.get('type', '')
    if sq_type in PASSIVE_TYPES:
        return None, 'passive'

    # boss_multi_specific: kill all bosses in each group's location list
    if sq_type == 'boss_multi_specific':
        total, zones = 0, []
        for b_group in sq_data.get('bosses', []):
            b_locs = [l for l in b_group.get('locations', []) if l.get('x')]
            if b_locs:
                t, z = _time_loc(b_locs[0], sq_type, build)
                total += t
                zones.append(z)
        return (total or OVERHEAD_GRACE_SEC + 30), (zones[0] if zones else 'unknown')

    # boss_multi_type: each group requires its own count
    if sq_type == 'boss_multi_type':
        total, zones = 0, []
        for g in sq_data.get('groups', []):
            g_locs  = [l for l in g.get('locations', []) if l.get('x')]
            g_count = g.get('count', 1)
            for loc in _pick_n_clustered(g_locs, g_count):
                t, z = _time_loc(loc, 'boss_count', build)
                total += t
                zones.append(z)
        return (total or OVERHEAD_GRACE_SEC + 30), (zones[0] if zones else 'unknown')

    locs = _extract_locs(sq_data)
    if not locs:
        return OVERHEAD_GRACE_SEC + 30, 'unknown'

    chosen = _pick_n_clustered(locs, count)
    total, zones = 0, []
    for loc in chosen:
        t, z = _time_loc(loc, sq_type, build)
        total += t
        zones.append(z)
    return total, (zones[0] if zones else 'unknown')


# ── Route builder ─────────────────────────────────────────────────────────────

def _stop_detail(loc, stop_type, build):
    """Return dict with travel/kill/overhead breakdown for one location visit."""
    grace, travel_dist = _closest_grace(loc)
    zone_id  = loc.get('zone', 'unknown')
    travel   = _travel_sec(travel_dist, zone_id)

    is_boss    = stop_type in ('boss_specific','boss_any','boss_count','boss_tag',
                               'boss_region','boss_multi_type','boss_multi_specific','prereq')
    is_dungeon = stop_type in ('dungeon_count','dungeon_specific')
    is_pickup  = stop_type in ('acquire_multi','acquire_count','acquire_fixed',
                               'npc_action','npc_invasion','npc_kill','restore_rune',
                               'consumable_action')
    kill = 0
    if is_boss:
        kill = compute_kill_sec(
            loc.get('name',''), build['weapon_class'], build['weapon_level'],
            build['is_somber'], build['primary_stat'], build['rune_level'],
        ) or _fallback_kill_sec(zone_id)

    overhead = OVERHEAD_GRACE_SEC
    if is_boss:    overhead += OVERHEAD_BOSS_SEC
    if is_dungeon: overhead += OVERHEAD_DUNGEON_SEC + _dungeon_overhead(loc.get('name',''))
    if is_pickup:  overhead += 30

    return {
        'loc':      loc,
        'grace_id': grace['id'],
        'zone':     zone_id,
        'travel':   travel,
        'kill':     kill,
        'overhead': overhead,
        'total':    travel + kill + overhead,
    }


def build_route(sq_data, count, build):
    """
    Return ordered list of stop-detail dicts for a square.
    Each dict has keys: loc, grace_id, zone, travel, kill, overhead, total.
    """
    sq_type = sq_data.get('type', '')
    if sq_type in PASSIVE_TYPES:
        return []

    stops = []

    if sq_type == 'boss_multi_specific':
        for b_group in sq_data.get('bosses', []):
            b_locs = [l for l in b_group.get('locations', []) if l.get('x')]
            if b_locs:
                stops.append(_stop_detail(b_locs[0], sq_type, build))

    elif sq_type == 'boss_multi_type':
        for g in sq_data.get('groups', []):
            g_locs  = [l for l in g.get('locations', []) if l.get('x')]
            g_count = g.get('count', 1)
            for loc in _pick_n_clustered(g_locs, g_count):
                stops.append(_stop_detail(loc, 'boss_count', build))

    else:
        locs = _extract_locs(sq_data)
        if locs:
            for loc in _pick_n_clustered(locs, count):
                stops.append(_stop_detail(loc, sq_type, build))

    return stops


# ── Pool count extraction ──────────────────────────────────────────────────────

def _pool_variants(pool_item):
    """
    Return list of (rolled_display_name, count_int) for all dice combinations.
    Fixed squares → one entry.  Variable squares → one entry per rolled value.
    """
    name   = pool_item['name']
    ph_keys = [k for k, v in pool_item.items()
               if k not in ('name','category') and isinstance(v, list)]

    # Build all rolled combinations (usually just one placeholder)
    combos = [{}]
    for k in ph_keys:
        combos = [{**c, k: v} for c in combos for v in pool_item[k]]

    results = []
    for roll in combos:
        rolled = name
        for k, v in roll.items():
            rolled = rolled.replace(f'%{k}%', v)
        m = re.match(
            r'^(?:Kill|Complete|Collect|Acquire|Learn|Give|Return|Invade|Buy|Dupe|Use|Restore)\s+(\d+)',
            rolled, re.IGNORECASE,
        )
        if m:
            count = int(m.group(1))
        else:
            # Non-verb names: "10 Sacred Flask charges", "Spirit Ash +4 summon", etc.
            m2 = re.search(r'(?<!\w)(\d+)(?!\w)', rolled)
            count = int(m2.group(1)) if m2 else 1
        results.append((rolled, count))
    return results


# ── Output helpers ─────────────────────────────────────────────────────────────

def fmt_time(sec):
    if sec is None:
        return 'passive'
    sec = int(sec)
    if sec <= 0:
        return '-'
    m, s = divmod(sec, 60)
    if m == 0: return f'{s}s'
    if s == 0: return f'{m}m'
    return f'{m}m {s:02d}s'


def fmt_range(t_min, t_max):
    if t_min is None:
        return 'passive'
    if t_min == t_max:
        return fmt_time(t_min)
    return f'{fmt_time(t_min)}-{fmt_time(t_max)}'


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Estimate bingo square completion times at multiple weapon levels.')
    parser.add_argument('--weapon-class', default='Greatsword',
                        choices=sorted(WEAPON_DPS_FACTOR.keys()),
                        metavar='CLASS',
                        help=f'Weapon class (default: Greatsword). Choices: {", ".join(sorted(WEAPON_DPS_FACTOR.keys()))}')
    parser.add_argument('--stat', default='Strength',
                        choices=list(STAT_SCALING.keys()),
                        help='Primary stat (default: Strength)')
    parser.add_argument('--somber', action='store_true',
                        help='Use somber upgrade track (+0 to +9)')
    parser.add_argument('--csv', action='store_true',
                        help='Output CSV to stdout')
    parser.add_argument('--sort', default='type',
                        choices=['name','type','wl0','wl_mid','wl_max'],
                        help='Sort column (default: type)')
    parser.add_argument('--output', default=None, metavar='FILE',
                        help='Save output to FILE (default: square_times.txt or square_times.csv)')
    parser.add_argument('--routes', action='store_true',
                        help='Print ordered stop-by-stop route for each square (appended after table)')
    args = parser.parse_args()

    default_ext = '.csv' if args.csv else '.txt'
    out_path = args.output or os.path.join(SCRIPT_DIR, f'square_times{default_ext}')

    # ── Load data ──────────────────────────────────────────────────────────────
    with open(os.path.join(DATA_DIR, 's6_base_bingo.json'), encoding='utf-8') as f:
        pool = json.load(f)
    with open(os.path.join(DATA_DIR, 'square_data.json'), encoding='utf-8') as f:
        squares = json.load(f)['squares']

    # ── Build scenarios ────────────────────────────────────────────────────────
    # Rune levels paired with each weapon level reflect typical S6 speedrun pacing.
    if args.somber:
        scenarios = [
            {'label': 'WL+0', 'weapon_level': 0, 'rune_level':  1},
            {'label': 'WL+3', 'weapon_level': 3, 'rune_level': 20},
            {'label': 'WL+6', 'weapon_level': 6, 'rune_level': 40},
            {'label': 'WL+9', 'weapon_level': 9, 'rune_level': 65},
        ]
    else:
        scenarios = [
            {'label': 'WL+0',  'weapon_level':  0, 'rune_level':  1},
            {'label': 'WL+5',  'weapon_level':  5, 'rune_level': 20},
            {'label': 'WL+10', 'weapon_level': 10, 'rune_level': 35},
            {'label': 'WL+15', 'weapon_level': 15, 'rune_level': 55},
            {'label': 'WL+20', 'weapon_level': 20, 'rune_level': 75},
        ]

    # ── Process pool entries ───────────────────────────────────────────────────
    rows = []
    seen_templates = set()

    for pool_item in pool:
        template = pool_item['name']
        if template in seen_templates:
            continue
        seen_templates.add(template)

        sq_data = squares.get(template)
        if not sq_data:
            continue  # no square_data entry

        sq_type  = sq_data.get('type', '?')
        variants = _pool_variants(pool_item)

        # Separate min/max count for variable-count squares
        counts       = [c for _, c in variants]
        min_count    = min(counts)
        max_count    = max(counts)
        is_variable  = min_count != max_count
        display_name = variants[0][0] if not is_variable else re.sub(
            r'(?<= )\d+(?= )', 'N', variants[0][0], count=1
        )

        # Compute time for min and max count at each scenario
        scenario_times = []  # list of (t_min, t_max, zone)
        for sc in scenarios:
            build = {
                'weapon_class': args.weapon_class,
                'weapon_level': sc['weapon_level'],
                'is_somber':    args.somber,
                'primary_stat': args.stat,
                'rune_level':   sc['rune_level'],
            }
            t_min, zone = estimate_square(sq_data, min_count, build)
            t_max, _    = estimate_square(sq_data, max_count, build) if is_variable else (t_min, zone)
            scenario_times.append((t_min, t_max, zone))

        count_str = f'{min_count}-{max_count}' if is_variable else (str(min_count) if min_count > 1 else '')

        rows.append({
            'name':      display_name,
            'type':      sq_type,
            'count':     count_str,
            'zone':      scenario_times[0][2] if scenario_times else 'unknown',
            'times':     scenario_times,
            '_template': template,
            '_min_count': min_count,
            '_max_count': max_count,
            '_sort_wl0':     scenario_times[0][0] if scenario_times else None,
            '_sort_wl_mid':  scenario_times[len(scenarios)//2][0] if scenario_times else None,
            '_sort_wl_max':  scenario_times[-1][0] if scenario_times else None,
        })

    # ── Sort ───────────────────────────────────────────────────────────────────
    INF = float('inf')
    if args.sort == 'name':
        rows.sort(key=lambda r: r['name'].lower())
    elif args.sort == 'type':
        rows.sort(key=lambda r: (r['type'], r['name'].lower()))
    elif args.sort == 'wl0':
        rows.sort(key=lambda r: r['_sort_wl0'] if r['_sort_wl0'] is not None else INF)
    elif args.sort == 'wl_mid':
        rows.sort(key=lambda r: r['_sort_wl_mid'] if r['_sort_wl_mid'] is not None else INF)
    elif args.sort == 'wl_max':
        rows.sort(key=lambda r: r['_sort_wl_max'] if r['_sort_wl_max'] is not None else INF)

    sc_labels = [sc['label'] for sc in scenarios]

    # ── CSV output ─────────────────────────────────────────────────────────────
    with open(out_path, 'w', encoding='utf-8') as f_out:
        with redirect_stdout(_Tee(sys.stdout, f_out)):
            if args.csv:
                import csv
                w = csv.writer(sys.stdout)
                w.writerow(['Square', 'Type', 'Count', 'Zone'] +
                           [f'{lbl}_min' for lbl in sc_labels] +
                           [f'{lbl}_max' for lbl in sc_labels])
                for r in rows:
                    t_mins = [fmt_time(t[0]) for t in r['times']]
                    t_maxs = [fmt_time(t[1]) for t in r['times']]
                    w.writerow([r['name'], r['type'], r['count'],
                                ZONE_LABEL.get(r['zone'], r['zone'])] + t_mins + t_maxs)
            else:
                # ── Pretty table ───────────────────────────────────────────────
                NW, TW, CW, ZW, VW = 48, 22, 5, 16, 12
                total_w = NW + TW + CW + ZW + VW * len(sc_labels) + 5 + (len(sc_labels) + 3) * 3

                def rule():
                    print('-' * total_w)

                def header_row():
                    h = (f'{"Square":<{NW}} | {"Type":<{TW}} | {"N":<{CW}} | {"Zone":<{ZW}}'
                         + ''.join(f' | {lbl:>{VW}}' for lbl in sc_labels))
                    print(h)

                print()
                print(f'  Weapon class : {args.weapon_class}')
                print(f'  Primary stat : {args.stat}')
                print(f'  Upgrade track: {"Somber (+0~+9)" if args.somber else "Standard (+0~+24)"}')
                print(f'  Rune levels  : {" / ".join(str(sc["rune_level"]) for sc in scenarios)} (RL per scenario)')
                print(f'  Sort         : {args.sort}')
                print()

                rule()
                header_row()
                rule()

                prev_type = None
                for r in rows:
                    if args.sort == 'type' and r['type'] != prev_type and prev_type is not None:
                        rule()
                    prev_type = r['type']

                    if r['type'] in PASSIVE_TYPES:
                        time_cells = ['passive'] * len(sc_labels)
                    else:
                        time_cells = [fmt_range(t[0], t[1]) for t in r['times']]

                    zone_str = ZONE_LABEL.get(r['zone'], r['zone']) or ''
                    print(
                        f'{(r["name"] or "")[:NW]:<{NW}} | '
                        f'{r["type"]:<{TW}} | '
                        f'{r["count"]:<{CW}} | '
                        f'{zone_str:<{ZW}}'
                        + ''.join(f' | {c:>{VW}}' for c in time_cells)
                    )

                rule()
                print(f'  {len(rows)} squares  |  Times = travel + kill + overhead from nearest S6 grace')
                print(f'  Variable-count squares show min-max range across rolled values.')
                print()

            # ── Routes section (--routes flag) ────────────────────────────────
            if args.routes and not args.csv:
                # Show routes at the highest weapon-level scenario
                route_sc   = scenarios[-1]
                route_build = {
                    'weapon_class': args.weapon_class,
                    'weapon_level': route_sc['weapon_level'],
                    'is_somber':    args.somber,
                    'primary_stat': args.stat,
                    'rune_level':   route_sc['rune_level'],
                }
                label = route_sc['label']
                print()
                print(f'  ROUTES @ {label} ({args.weapon_class}, {args.stat})')
                print()

                for r in rows:
                    if r['type'] in PASSIVE_TYPES:
                        continue
                    matched_sq = squares.get(r['_template'])
                    if not matched_sq:
                        continue

                    use_count  = r['_max_count']
                    stops      = build_route(matched_sq, use_count, route_build)
                    if not stops:
                        continue

                    count_note = f' (x{use_count})' if use_count > 1 else ''
                    total_sec  = sum(s['total'] for s in stops)
                    print(f'  [{r["type"]}] {r["name"]}{count_note}  -->  {fmt_time(total_sec)}')

                    for i, s in enumerate(stops, 1):
                        loc_name  = s['loc'].get('name', '?')
                        zone_lbl  = ZONE_LABEL.get(s['zone'], s['zone'])
                        grace_lbl = GRACE_LABEL.get(s['grace_id'], s['grace_id'])
                        parts = [f'travel {fmt_time(s["travel"])}']
                        if s['kill']:     parts.append(f'kill {fmt_time(s["kill"])}')
                        if s['overhead']: parts.append(f'overhead {fmt_time(s["overhead"])}')
                        print(f'    {i}. {loc_name:<40} [{zone_lbl:<16}] warp: {grace_lbl:<22} {fmt_time(s["total"])}  ({" + ".join(parts)})')
                    print()

    sys.stderr.write(f'Saved to {out_path}\n')


if __name__ == '__main__':
    main()
