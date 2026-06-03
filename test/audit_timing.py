"""
Audit every square's timing engine inputs and outputs.

Usage:
    python -m test.audit_timing > test\timing_audit.txt
"""
import sys, os, json, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.stdout.reconfigure(encoding='utf-8')

from jack.rl.constants import (
    BOSS_HP, BOSS_DIFFICULTY, compute_kill_time, compute_death_probability,
    boss_weapon_floor, ZONE_TIER, BOSS_MODIFIER_KILL_MULT,
)

with open('jack/data/square_data.json', encoding='utf-8') as f:
    data = json.load(f)

BOSS_TYPES = {
    'boss_specific', 'boss_any', 'boss_modifier', 'boss_tag',
    'boss_count', 'boss_region', 'boss_multi_type', 'boss_multi_specific',
    'npc_kill', 'npc_invasion',
}

NON_BOSS_TYPES = {
    'acquire_multi', 'acquire_count', 'acquire_fixed',
    'consumable_action', 'passive_stat', 'passive_runes',
    'restore_rune', 'npc_action', 'dungeon_count', 'dungeon_specific',
}

WEAPON_CLASS = 'standard'
PRIMARY_STAT = 'str'
RUNE_LEVEL   = 60
IS_SOMBER    = True

def boss_hp_lookup(loc):
    boss_name = (loc.get('boss_name') or loc.get('name', '')).lower()
    bd = BOSS_HP.get(boss_name)
    matched_key = boss_name if bd else None
    if not bd:
        for k2, v in BOSS_HP.items():
            if boss_name in k2 or k2 in boss_name:
                bd = v
                matched_key = k2
                break
    return bd, matched_key

def fmt_kill(wl, loc, boss_data_key):
    if boss_data_key is None:
        return '  --'
    r = compute_kill_time(boss_data_key, WEAPON_CLASS, wl, IS_SOMBER, PRIMARY_STAT, RUNE_LEVEL)
    if r is None:
        return '  --'
    return f'{r["kill_sec"]:4d}s'

squares = data['squares']

print('=' * 110)
print('TIMING ENGINE AUDIT — all squares')
print(f'Weapon class: {WEAPON_CLASS}  |  stat: {PRIMARY_STAT}  |  somber  |  rune level: {RUNE_LEVEL}')
print('=' * 110)

for sq_name in sorted(squares, key=lambda n: squares[n].get('type', '')):
    sq = squares[sq_name]
    sq_type = sq.get('type', '?')
    locs = sq.get('locations', [])
    prereqs = sq.get('prerequisites', [])

    print(f'\n{"-"*110}')
    print(f'[{sq_type}]  {sq_name}')
    if prereqs:
        print(f'  prereqs: {prereqs}')

    if sq_type in NON_BOSS_TYPES:
        overhead = sq.get('overhead_sec', '?')
        print(f'  type: non-boss  |  overhead_sec={overhead}')
        for loc in locs:
            zone = loc.get('zone', '?')
            print(f'    loc: {loc.get("name","?")}  zone={zone}')
        continue

    if sq_type not in BOSS_TYPES:
        print(f'  (unhandled type)')
        continue

    for loc in locs:
        loc_name  = loc.get('name', '?')
        zone      = loc.get('zone', '?')
        wl_floor  = boss_weapon_floor(zone, IS_SOMBER)
        tier      = ZONE_TIER.get(zone, '?')
        boss_data, matched_key = boss_hp_lookup(loc)

        print(f'  loc: {loc_name}')
        print(f'       zone={zone}  tier={tier}  weapon_floor(somber)=+{wl_floor}')

        if loc.get('boss_name'):
            print(f'       boss_name override: {loc["boss_name"]!r}')

        if boss_data:
            diff = BOSS_DIFFICULTY.get(matched_key, 1.3)
            hp   = boss_data['hp']
            dfns = boss_data['def']
            print(f'       BOSS_HP match: {matched_key!r}  hp={hp}  def={dfns}  difficulty={diff}')
            # Kill times at key weapon levels
            kills = []
            for wl in [0, 3, 6, 9]:
                r = compute_kill_time(matched_key, WEAPON_CLASS, wl, IS_SOMBER, PRIMARY_STAT, RUNE_LEVEL)
                kills.append(f'+{wl}={r["kill_sec"]}s' if r else f'+{wl}=N/A')
            print(f'       kill_sec (somber): {" | ".join(kills)}')
        else:
            print(f'       BOSS_HP match: NONE  ← no kill time, no death penalty')

        # Death probability
        print(f'       death prob: ', end='')
        probs = []
        for wl in [0, 2, 4, 6]:
            p = compute_death_probability(zone, wl, IS_SOMBER)
            probs.append(f'+{wl}={p:.0%}')
        if boss_data:
            print(' | '.join(probs))
        else:
            print('(skipped — no BOSS_HP entry)')

        # Modifier overhead if applicable
        if sq_type == 'boss_modifier':
            constraint = sq.get('data', {}).get('constraint', '') or sq.get('constraint', '')
            mults = BOSS_MODIFIER_KILL_MULT.get(constraint, {})
            oh = sq.get('overhead_sec', 0)
            print(f'       modifier constraint={constraint!r}  kill_mult={mults}  overhead_sec={oh}')

print(f'\n{"=" * 110}')
print('SUMMARY')
print('=' * 110)

boss_sq_count = sum(1 for sq in squares.values() if sq.get('type') in BOSS_TYPES)
no_hp_locs = []
for sq_name, sq in squares.items():
    if sq.get('type') not in BOSS_TYPES:
        continue
    for loc in sq.get('locations', []):
        bd, _ = boss_hp_lookup(loc)
        if not bd:
            no_hp_locs.append((sq_name, loc.get('name','?'), loc.get('zone','?')))

print(f'Boss-type squares: {boss_sq_count}')
print(f'Locations with no BOSS_HP match: {len(no_hp_locs)}')
print()
print(f'{"Zone":20s}  {"Location":45s}  Square')
print('-' * 110)
for sq_name, loc_name, zone in sorted(no_hp_locs, key=lambda x: x[2]):
    print(f'{zone:20s}  {loc_name:45s}  {sq_name}')
