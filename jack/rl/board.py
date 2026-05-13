"""Board generation for Elden Ring S6 lockout bingo.

Generates a 5×5 board from s6_base_bingo.json templates with S6 randomization:
  - %num% / %numofbosses% variants resolved randomly
  - Weapon class retained, specific weapon randomized
  - Staves not randomized (always world pickups)
  - Vendor pool randomized but count is fixed per vendor

Also builds the global action universe: the fixed set of all locations the RL
agent can ever choose from, consistent across all episode boards.
"""
import os
import sys
import json
import random
import re
import math
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from .constants import (
    ZONE_PENALTY, ZONE_SPEED_MULT, ZONE_TIER,
    BOSS_HP, compute_kill_time, compute_travel_time,
    WEAPON_CLASSES, S6_GRACES, STONE_NODES, ROUNDTABLE, PREREQ_LOCS,
    TACTICAL_GRACES,
    OVERHEAD_GRACE_SEC, OVERHEAD_BOSS_SEC, OVERHEAD_PICKUP_SEC,
    OVERHEAD_DUNGEON_SEC, dungeon_overhead, BINGO_LINES, N_SQUARES,
)

if getattr(sys, 'frozen', False):
    _DATA_DIR = os.path.join(sys._MEIPASS, 'jack', 'data')
else:
    _DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')


def _load_json(name):
    with open(os.path.join(_DATA_DIR, name), encoding='utf-8') as f:
        return json.load(f)


_TEMPLATES  = _load_json('s6_base_bingo.json')
_SQUARE_DB  = _load_json('square_data.json')['squares']

# Base-category templates only
_BASE_TEMPLATES = [t for t in _TEMPLATES if t.get('category') == 'Base']


# ── Passive square types — no locations to visit ──────────────────────────────
_PASSIVE_TYPES = {'passive_runes', 'passive_stat'}

# ── Square types that require +0 weapon (invalidated on first upgrade) ─────────
_ZERO_WEAPON_PATTERNS = re.compile(r'\+0\s+weapon', re.IGNORECASE)


@dataclass
class Square:
    idx:          int           # 0-24 position on board
    text:         str           # resolved display text
    raw_name:     str           # template name (used as square_data.json key)
    sq_type:      str           # from square_data.json
    data:         Dict          # full square_data.json entry
    locations:    List[Dict]    # candidate locations for this square
    count_needed: int           # how many locations must be visited to complete
    is_passive:   bool          # no active visits needed
    requires_zero_weapon: bool  # invalidated if player has upgraded weapon
    prereqs:      List[str]     # prerequisite keys (nokron_access, capital_access…)
    runes_on_complete: int      # rune reward for completing this square

    def loc_keys(self):
        return {_loc_key(l) for l in self.locations}


def _loc_key(l):
    return f"{round(l['x']*10)}_{round(l['y']*10)}_{l.get('level',1)}"


def _infer_zone(loc):
    x, y, lv = loc.get('x', 0), loc.get('y', 0), loc.get('level', 1)
    if lv == 2:
        if x < -160 and y >= 128:                       return 'siofra'
        if -145 < x < -115 and 55 < y < 85:             return 'ainsel'
        if -110 < x < -85  and y > 105:                 return 'deeproot'
        if x < -175 and y > 144:                        return 'mohgwyn'
        return 'unknown'
    if  -55 < x < -25  and 130 < y < 165:               return 'haligtree'
    if  -90 < x < -55  and 125 < y < 165:               return 'consecrated'
    if -105 < x < -55  and  95 < y < 175:               return 'mountaintops'
    if -140 < x < -55  and 195 < y < 230:               return 'farum_azula'
    if -200 < x < -140 and 120 < y < 170:               return 'caelid'
    if -115 < x < -75  and  95 < y < 145:               return 'leyndell'
    if -100 < x < -75  and  55 < y <  75:               return 'mt_gelmir'
    if -115 < x < -75  and  55 < y <  95:               return 'altus_plateau'
    if -175 < x < -115 and  45 < y <  95:               return 'liurnia'
    if -115 < x < -100 and  45 < y <  60:               return 'caria_manor'
    if -215 < x < -170 and  75 < y <  95:               return 'stormveil'
    if -215 < x < -170 and  80 < y < 130:               return 'limgrave'
    if -240 < x < -195 and  90 < y < 135:               return 'weeping_peninsula'
    if -215 < x < -160 and 125 < y < 170:               return 'caelid'
    return 'unknown'


def _resolve_loc(l):
    """Ensure location has zone field."""
    loc = dict(l)
    if not loc.get('zone'):
        loc['zone'] = _infer_zone(loc)
    return loc


def _extract_locations(sq_name, sq_data):
    """Extract all candidate visit locations for a square."""
    locs = []
    seen = set()

    def add(lst):
        if not lst:
            return
        for l in lst:
            if not isinstance(l, dict) or not l.get('x') or not l.get('y'):
                continue
            loc = _resolve_loc(l)
            k = _loc_key(loc)
            if k not in seen:
                seen.add(k)
                locs.append(loc)

    t = sq_data.get('type', '')
    add(sq_data.get('locations'))
    if t == 'acquire_count':
        add(sq_data.get('vendor_locations'))
    add(sq_data.get('all_bosses'))
    add(sq_data.get('candidates'))
    for g in sq_data.get('groups', []):
        add(g.get('locations'))
    for b in sq_data.get('bosses', []):
        add(b.get('locations'))
    loc_single = sq_data.get('location')
    if isinstance(loc_single, dict):
        add([loc_single])
    return locs


def _extract_count(text, sq_data):
    if sq_data.get('count_needed') is not None:
        return sq_data['count_needed']
    t = sq_data.get('type', '')
    if t == 'boss_multi_type':
        return sum(g.get('count', 1) for g in sq_data.get('groups', []))
    # acquire_multi: every item must be collected; boss_multi_specific: every boss must die
    if t == 'acquire_multi':
        return len(sq_data.get('locations', [])) or 1
    if t == 'boss_multi_specific':
        return len(sq_data.get('bosses', [])) or 1
    if t in ('boss_specific', 'consumable_action', 'npc_action', 'restore_rune',
             'acquire_fixed', 'dungeon_specific', 'npc_invasion'):
        return 1
    m = re.search(r'(?:Kill|Complete|Collect|Acquire|Learn|Give|Return|Invade|Buy|Dupe|Use)\s+(\d+)', text, re.I)
    if m:
        return int(m.group(1))
    m2 = re.search(r'(?<!\w)(\d+)(?!\w)', text)
    return int(m2.group(1)) if m2 else 1


def _estimate_runes(sq_data):
    """Quick rune estimate for a square (used for ordering heuristics)."""
    total = sq_data.get('runes', 0)
    for loc in sq_data.get('locations', []):
        if isinstance(loc, dict):
            total += loc.get('runes', 0)
    return total


def _resolve_template(template, rng):
    """Fill %num% / %numofbosses% variants, return (resolved_text, raw_name)."""
    name = template['name']
    raw  = name  # key into square_data.json
    for var_key in ('num', 'numofbosses'):
        if var_key in template:
            chosen = rng.choice(template[var_key])
            name = name.replace(f'%{var_key}%', chosen)
    return name, raw


def generate_board(seed=None, num_squares=N_SQUARES):
    """Sample and return a list of `num_squares` Square objects."""
    rng = random.Random(seed)
    selected = rng.sample(_BASE_TEMPLATES, num_squares)

    squares = []
    for i, tmpl in enumerate(selected):
        text, raw_name = _resolve_template(tmpl, rng)
        sq_data = _SQUARE_DB.get(raw_name) or _SQUARE_DB.get(text) or {}
        sq_type = sq_data.get('type', 'unknown')

        locs = _extract_locations(raw_name, sq_data) if sq_data else []
        count = _extract_count(text, sq_data) if sq_data else 1
        is_passive = (sq_type in _PASSIVE_TYPES) or (not locs and sq_type != 'unknown')

        squares.append(Square(
            idx=i,
            text=text,
            raw_name=raw_name,
            sq_type=sq_type,
            data=sq_data,
            locations=locs,
            count_needed=count,
            is_passive=is_passive,
            requires_zero_weapon=bool(_ZERO_WEAPON_PATTERNS.search(text)),
            prereqs=sq_data.get('prerequisites', []) if sq_data else [],
            runes_on_complete=_estimate_runes(sq_data),
        ))
    return squares


# ── Global action universe ─────────────────────────────────────────────────────
# Pre-built from ALL 117 possible squares so the action space is consistent
# across episodes.  Each entry is a dict with keys:
#   type: 'objective' | 'stone' | 'roundtable'
#   loc:  location dict {x, y, level, zone, name, ...}
#   sq_names: set of square raw_names this location belongs to (objective only)
#   stone_tier, stone_somber: for 'stone' type

_BOSS_NAMES_LOWER = set(BOSS_HP.keys())


def _is_boss_loc(loc: dict) -> bool:
    """True if this location hosts a boss fight (name is in BOSS_HP)."""
    name = loc.get('name', '').lower().strip()
    if not name:
        return False
    if name in _BOSS_NAMES_LOWER:
        return True
    for k in _BOSS_NAMES_LOWER:
        if name in k or k in name.split('(')[0].strip():
            return True
    return False


def _build_global_universe():
    # Collect all objective locations
    obj_locs = {}   # loc_key → {loc, sq_names}
    for raw_name, sq_data in _SQUARE_DB.items():
        if sq_data.get('type') in _PASSIVE_TYPES:
            continue
        locs = _extract_locations(raw_name, sq_data)
        for loc in locs:
            k = _loc_key(loc)
            if k not in obj_locs:
                obj_locs[k] = {'loc': loc, 'sq_names': set()}
            obj_locs[k]['sq_names'].add(raw_name)

    universe = []
    # Objective locations
    for k, entry in obj_locs.items():
        loc = entry['loc']
        universe.append({
            'type':           'objective',
            'loc':             loc,
            'sq_names':        frozenset(entry['sq_names']),
            'key':             k,
            'loc_prereqs':     loc.get('prerequisites', []),
            'is_boss_loc':     _is_boss_loc(loc),
            'min_weapon_level': loc.get('min_weapon_level'),  # None = use zone floor
        })
    # Stone nodes (direct access = guaranteed world pickups)
    for node in STONE_NODES:
        universe.append({
            'type':       'stone',
            'loc':         _resolve_loc(node),
            'stone_tier':  node['tier'],
            'stone_somber': node.get('somber', False),
            'stone_count': 1,
            'key':         _loc_key(node),
        })
    # Roundtable Hold
    universe.append({
        'type': 'roundtable',
        'loc':   ROUNDTABLE,
        'key':   'roundtable',
    })
    # Prerequisite-only locations (not in any square's locations list)
    for ploc in PREREQ_LOCS:
        loc = _resolve_loc(ploc)
        universe.append({
            'type':       'prereq',
            'loc':         loc,
            'prereq_key':  ploc['prereq_key'],
            'key':         _loc_key(loc),
        })
    # Tactical graces — pre-fight graces agent visits to shorten corpse runs
    for tg in TACTICAL_GRACES:
        loc = _resolve_loc(tg)
        universe.append({
            'type':     'grace',
            'loc':       loc,
            'grace_id':  tg['id'],
            'key':       _loc_key(loc),
        })
    return universe


UNIVERSE = _build_global_universe()
UNIVERSE_SIZE = len(UNIVERSE)

# Index lookup: key → universe index
UNIVERSE_KEY_TO_IDX = {entry['key']: i for i, entry in enumerate(UNIVERSE)}
