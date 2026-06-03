"""Game constants for Elden Ring S6 bingo RL agents.

All values mirrored from timing.js and router.js to keep the Python sim
in sync with the JavaScript frontend calculations.
"""
import os
import sys
import json
import math

if getattr(sys, 'frozen', False):
    _DATA_DIR = os.path.join(sys._MEIPASS, 'jack', 'data')
else:
    _DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')


def _load_json(name):
    with open(os.path.join(_DATA_DIR, name), encoding='utf-8') as f:
        return json.load(f)


# ── Zone constants ─────────────────────────────────────────────────────────────
ZONE_PENALTY = {
    'limgrave': 0.00, 'weeping_peninsula': 0.05, 'stormveil': 0.05,
    'siofra': 0.15,   'liurnia': 0.15,            'caria_manor': 0.20,
    'caelid': 0.20,   'dragonbarrow': 0.25,        'altus_plateau': 0.30,
    'mt_gelmir': 0.35,'volcano_manor': 0.35,        'leyndell': 0.45,
    'deeproot': 0.45, 'ainsel': 0.40,              'mohgwyn': 0.55,
    'mountaintops': 0.60, 'consecrated': 0.65,     'haligtree': 0.70,
    'farum_azula': 0.75,  'unknown': 0.30,
}

ZONE_SPEED_MULT = {
    'limgrave': 1.0,  'weeping_peninsula': 1.1, 'stormveil': 2.5,
    'siofra': 2.0,    'liurnia': 1.1,            'caria_manor': 2.2,
    'caelid': 1.1,    'dragonbarrow': 1.0,        'altus_plateau': 1.0,
    'mt_gelmir': 1.4, 'volcano_manor': 2.5,       'leyndell': 1.8,
    'deeproot': 2.2,  'ainsel': 2.0,              'mohgwyn': 2.0,
    'mountaintops': 1.1, 'consecrated': 1.1,      'haligtree': 2.8,
    'farum_azula': 2.5,  'unknown': 1.3,
}

ZONE_TIER = {
    'limgrave': 0, 'weeping_peninsula': 1, 'stormveil': 2, 'siofra': 2,
    'liurnia': 3,  'caria_manor': 3,        'caelid': 3,   'dragonbarrow': 4,
    'altus_plateau': 4, 'mt_gelmir': 5,     'volcano_manor': 5,
    'leyndell': 6, 'deeproot': 5,           'ainsel': 5,
    'mohgwyn': 7,  'mountaintops': 6,       'consecrated': 7,
    'haligtree': 8, 'farum_azula': 8,       'unknown': 4,
}

# Minimum weapon level to fight comfortably per zone tier [0..8].
# Standard smithing weapons (max +24) and somber (max +9).
_ZONE_WEAPON_FLOOR_STD    = [0,  3,  6, 12, 15, 18, 20, 22, 24]
_ZONE_WEAPON_FLOOR_SOMBER = [0,  1,  2,  5,  6,  7,  8,  9,  9]

# ── Travel constants ───────────────────────────────────────────────────────────
TRAVEL_SEC_PER_UNIT = 8.3

# Baseline attack uptime for an "average difficulty" boss.
# Divided by BOSS_DIFFICULTY[boss] to get the effective uptime for each fight.
BOSS_UPTIME = 0.60

# Per-boss difficulty rating — captures how many safe attack windows a boss gives.
# 0.7 = nearly stationary (Tibia Mariner), 3.0 = almost no safe windows (Malenia).
# Effective uptime = BOSS_UPTIME / difficulty.
BOSS_DIFFICULTY = {
    # ── Very easy: stationary, scripted, or trivial mechanics ─────────────────
    'soldier of godrick':                        0.6,
    'tibia mariner':                             0.7,
    'guardian golem':                            0.7,
    'spiritcaller snail':                        0.7,
    'erdtree burial watchdog':                   0.8,
    'cemetery shade':                            0.8,
    'stonedigger troll':                         0.8,
    'mad pumpkin head':                          0.8,
    'beastman of farum azula':                   0.8,
    'grafted scion':                             0.9,
    'ancestor spirit':                           0.9,
    'regal ancestor spirit':                     0.9,
    'erdtree avatar':                            0.9,
    'mimic tear':                                0.9,

    # ── Easy: clear attack patterns, generous recovery windows ────────────────
    'rennala, queen of the full moon':           1.0,
    'godrick the grafted':                       1.1,
    'leonine misbegotten':                       1.0,
    'runebear':                                  1.1,
    'omenkiller':                                1.1,
    'royal revenant':                            1.1,
    'wormface':                                  1.1,
    'demi-human queen':                          1.1,
    'sanguine noble':                            1.1,
    'frenzied duelist':                          1.1,
    "bols, carian knight":                       1.1,
    'grave warden duelist':                      1.0,
    'putrid grave warden duelist':               1.1,
    'black knife assassin':                      1.2,
    'cleanrot knight':                           1.2,
    'deathbird':                                 1.2,
    'onyx lord':                                 1.2,
    "commander o'neil":                          1.2,
    'magma wyrm':                                1.2,
    'flying dragon agheel':                      1.2,
    'glintstone dragon smarag':                  1.2,
    'rykard, lord of blasphemy':                 1.2,  # spear gimmick = easy
    'god-devouring serpent':                     1.2,
    'dragonkin soldier':                         1.2,
    'dragonkin soldier of nokstella':            1.2,
    'godefroy the grafted':                      1.2,

    # ── Medium: multi-hit combos, tracking, punishes misreads ─────────────────
    'margit, the fell omen':                     1.5,
    'red wolf of radagon':                       1.3,
    'red wolf of the champion':                  1.4,
    'fallingstar beast':                         1.3,
    "night's cavalry":                           1.3,
    'death rite bird':                           1.4,
    'battlemage hugues':                         1.3,
    'ulcerated tree spirit':                     1.3,
    'putrid avatar':                             1.3,
    'ancient hero of zamor':                     1.3,
    'dragonkin soldier (lake of rot)':           1.3,
    'magma wyrm makar':                          1.3,
    'tree sentinel':                             1.4,
    'full-grown fallingstar beast':              1.5,
    'elemer of the briar':                       1.5,
    'borealis the freezing fog':                 1.5,
    'godskin noble':                             1.5,
    'putrid tree spirit':                        1.5,
    'ancient dragon lansseax':                   1.4,
    'glintstone dragon adula':                   1.4,
    'flying dragon greyll':                      1.3,
    'decaying ekzykes':                          1.3,
    'great wyrm theodorix':                      1.5,
    'lichdragon fortissax':                      1.4,
    'dragonlord placidusax':                     1.4,
    "astel, naturalborn of the void":            1.5,
    "astel, stars of darkness":                  1.6,

    # ── Hard-medium: demanding mechanics, phase pressure ──────────────────────
    'crucible knight':                           1.8,
    'crucible knight and crucible knight ordovis':2.0,
    'crucible knight siluria':                   1.8,
    'bloodhound knight darriwil':                1.7,
    'bloodhound knight':                         1.6,
    'black blade kindred':                       1.8,
    'black blade kindred (forbidden lands)':     1.9,
    "night's cavalry duo":                       1.7,
    'night cavalry (forbidden lands)':           1.6,
    'misbegotten warrior and crucible knight':   1.8,
    'misbegotten crusader':                      1.7,
    'godskin apostle':                           1.6,
    'godskin apostle (caelid)':                  1.6,
    'draconic tree sentinel':                    1.7,
    'royal knight loretta':                      1.5,
    'loretta, knight of the haligtree':          1.8,
    'godfrey, first elden lord':                 1.8,
    'fell twins':                                1.7,
    'bell bearing hunter':                       1.7,
    'roundtable knight vyke':                    1.9,
    'tree sentinel duo':                         1.8,
    'starscourge radahn':                        1.7,
    "fia's champions":                           2.0,
    'fire giant':                                1.8,
    'mohg, the omen':                            1.7,

    # ── Hard: punishing windows, aggressive combos ────────────────────────────
    'morgott, the omen king':                    2.0,
    'godskin duo':                               2.1,
    'commander niall':                           2.0,
    'alecto, black knife ringleader':            2.0,
    'godfrey (ashen capital)':                   2.0,
    'mohg, lord of blood':                       2.1,
    'beast clergyman':                           2.2,
    'maliketh, the black blade':                 2.2,

    # ── Very hard: almost no safe windows ─────────────────────────────────────
    'malenia, blade of miquella':                3.0,  # waterfowl + lifesteal

    # ── NPC fights / special encounters ──────────────────────────────────────
    'elder dragon greyoll':                      1.1,  # 5 small dragons, hit hard, no fire
    'gurranq':                                   2.0,  # huge HP, huge hits, bad arena
    'esgar, priest of blood':                    1.4,  # bleed spells, mobile
    'magnus the beast claw':                     1.5,  # self-heals
    'milicent invader':                          0.9,
    'stray mimic tear':                          0.9,
    'lion guardian stormveil':                   1.4,
    'lion guardian redmane':                     1.4,
    'lion guardian leyndell':                    1.4,
    'lion guardian caelid':                      1.4,
    'lion guardian castle sol':                  1.5,  # harder late-game variant
    'putrid crystalian trio':                    1.8,  # immune to slash/thrust
}

# Flat extra seconds added for scripted phase transitions, cutscenes, and
# repositioning overhead that sits outside normal attack patterns.
BOSS_PHASE_OVERHEAD = {
    'godrick the grafted':               20,
    'rennala, queen of the full moon':   35,
    'starscourge radahn':                15,
    'morgott, the omen king':            10,
    'fire giant':                        20,
    'beast clergyman':                   10,
    'maliketh, the black blade':         10,
    'malenia, blade of miquella':        20,
    'mohg, lord of blood':               35,  # Nihil ritual
    'godskin duo':                       20,
    'dragonlord placidusax':             10,
    "astel, naturalborn of the void":    10,
    "astel, stars of darkness":          10,
}

# Kill-time multipliers for boss_modifier constraint squares.
# Keys match the 'constraint' field in square_data.json.
# Values keyed by primary_stat — modifier difficulty varies by build.
BOSS_MODIFIER_KILL_MULT = {
    'hitless':             {'Strength': 1.5, 'Dexterity': 1.5, 'Int': 1.5, 'Faith': 1.5, 'Quality': 1.5},
    'colossal_only':       {'Strength': 1.0, 'Dexterity': 1.5, 'Int': 2.0, 'Faith': 2.0, 'Quality': 1.2},
    'dagger_claw_fist':    {'Strength': 2.5, 'Dexterity': 2.0, 'Int': 2.5, 'Faith': 2.5, 'Quality': 2.0},
    'bow_only':            {'Strength': 3.0, 'Dexterity': 2.5, 'Int': 3.0, 'Faith': 3.0, 'Quality': 2.8},
    'sorcery_only':        {'Strength': 2.0, 'Dexterity': 2.0, 'Int': 1.0, 'Faith': 2.5, 'Quality': 2.0},
    'incantation_only':    {'Strength': 2.0, 'Dexterity': 2.0, 'Int': 2.5, 'Faith': 1.0, 'Quality': 2.0},
    'remembrance_weapon':  {'Strength': 1.5, 'Dexterity': 1.5, 'Int': 1.5, 'Faith': 1.5, 'Quality': 1.5},
}

OVERHEAD_GRACE_SEC      = 10
OVERHEAD_BOSS_SEC       = 25
OVERHEAD_DUNGEON_SEC    = 40
OVERHEAD_PICKUP_SEC     = 30
OVERHEAD_ROUNDTABLE_SEC = 30   # teleport overhead, fixed regardless of position

# Per square-type action overhead (seconds) for non-boss, non-dungeon squares.
# Overrides the flat OVERHEAD_PICKUP_SEC so the model learns proper time costs
# instead of treating everything as a free 30-second pickup.
SQUARE_ACTION_SEC = {
    'npc_action':        150,  # NPC dialogue / quest trigger (Rya, Hyetta, Thops…)
    'consumable_action': 120,  # Use item on boss: travel-to + fight + use ~2 min
    'restore_rune':      180,  # Divine Tower: boss + climb + activation ~3 min
    'acquire_count':      75,  # Buy/collect multiple items from vendors ~1.25 min
    'acquire_multi':      75,  # Multiple fixed acquisitions ~1.25 min
    'acquire_fixed':      30,  # Single item pickup — keep at base
    'npc_invasion':       90,  # NPC invasion fight ~1.5 min
    'npc_kill':           60,  # Simple NPC kill ~1 min
}

DUNGEON_OVERHEAD = {
    'catacombs': 240, 'cave': 180, 'tunnel': 180,
    'evergaol': 120,  'hero_grave': 360, 'dungeon': 200,
}

# Surface entry points for underground zones (from router.js)
SURF_ENTRIES = {
    'siofra':   {'x': -187.55, 'y': 122.18},
    'nokron':   {'x': -187.55, 'y': 122.18},
    'deeproot': {'x': -187.55, 'y': 122.18},
    'ainsel':   {'x': -130.11, 'y':  78.35},
    'mohgwyn':  {'x':  -70.68, 'y': 129.59},
}

# ── S6 starting graces ─────────────────────────────────────────────────────────
S6_GRACES = [
    {'id': 'sg_gatefront',   'name': 'Gatefront Ruins',             'x': -185.78, 'y': 102.10, 'level': 1, 'zone': 'limgrave'},
    {'id': 'sg_consecrated', 'name': 'Inner Consecrated Snowfield', 'x':  -73.56, 'y': 141.78, 'level': 1, 'zone': 'consecrated'},
    {'id': 'sg_haligtree',   'name': 'Haligtree Roots',             'x':  -37.10, 'y': 149.13, 'level': 1, 'zone': 'haligtree'},
    {'id': 'sg_snow_valley', 'name': 'Snow Valley Ruins Overlook',  'x':  -64.63, 'y': 159.69, 'level': 1, 'zone': 'mountaintops'},
    {'id': 'sg_aeonia',      'name': 'Inner Aeonia',                 'x': -178.97, 'y': 143.06, 'level': 1, 'zone': 'caelid'},
    {'id': 'sg_ailing',      'name': 'Ailing Village Outskirts',     'x': -211.27, 'y': 112.20, 'level': 1, 'zone': 'limgrave'},
    {'id': 'sg_scenic',      'name': 'Scenic Isle',                  'x': -156.20, 'y':  67.88, 'level': 1, 'zone': 'liurnia'},
    {'id': 'sg_labyrinth',   'name': 'Ruined Labyrinth',             'x': -125.59, 'y':  73.51, 'level': 1, 'zone': 'liurnia'},
    {'id': 'sg_altus_hwy',   'name': 'Altus Highway Junction',       'x': -100.79, 'y':  84.93, 'level': 1, 'zone': 'altus_plateau'},
    {'id': 'sg_iniquity',    'name': 'Road of Iniquity',              'x':  -84.37, 'y':  63.22, 'level': 1, 'zone': 'mt_gelmir'},
    {'id': 'sg_lake_rot',    'name': 'Lake of Rot Shoreside',         'x': -128.46, 'y':  60.20, 'level': 2, 'zone': 'ainsel'},
    {'id': 'sg_siofra',      'name': 'Siofra River Bank',             'x': -184.90, 'y': 130.58, 'level': 2, 'zone': 'siofra'},
    {'id': 'sg_roundtable',  'name': 'Roundtable Hold',               'x': -160.00, 'y':  90.00, 'level': 1, 'zone': 'liurnia',  'is_roundtable': True},
]

# Boss arena graces unlocked after killing the corresponding boss
BOSS_GRACES = {
    'margit, the fell omen':           {'id': 'bg_margit',      'x': -183.33, 'y':  93.85, 'level': 1, 'zone': 'limgrave',    'name': 'Castleward Tunnel'},
    'godrick the grafted':             {'id': 'bg_godrick',     'x': -174.50, 'y':  86.20, 'level': 1, 'zone': 'limgrave',    'name': 'Godrick the Grafted'},
    'rennala, queen of the full moon': {'id': 'bg_rennala',     'x': -135.42, 'y':  56.11, 'level': 1, 'zone': 'liurnia',     'name': 'Raya Lucaria Grand Library'},
    'starscourge radahn':              {'id': 'bg_radahn',      'x': -194.36, 'y': 160.21, 'level': 1, 'zone': 'caelid',      'name': 'Starscourge Radahn'},
    'morgott, the omen king':          {'id': 'bg_morgott',     'x': -107.64, 'y': 120.62, 'level': 1, 'zone': 'leyndell',    'name': 'Morgott, the Omen King'},
    'rykard, lord of blasphemy':       {'id': 'bg_rykard',      'x':  -87.22, 'y':  66.70, 'level': 1, 'zone': 'mt_gelmir',   'name': 'Rykard, Lord of Blasphemy'},
    'malenia, blade of miquella':      {'id': 'bg_malenia',     'x':  -38.12, 'y': 146.39, 'level': 1, 'zone': 'haligtree',   'name': 'Malenia, Goddess of Rot'},
    'fire giant':                      {'id': 'bg_fire_giant',  'x':  -92.34, 'y': 163.88, 'level': 1, 'zone': 'mountaintops','name': 'Fire Giant'},
    'mohg, lord of blood':             {'id': 'bg_mohg',        'x': -182.32, 'y': 146.50, 'level': 2, 'zone': 'mohgwyn',     'name': 'Mohg, Lord of Blood'},
    'maliketh, the black blade':       {'id': 'bg_maliketh',    'x': -125.10, 'y': 221.00, 'level': 1, 'zone': 'farum_azula', 'name': 'Maliketh, the Black Blade'},
    'borealis the freezing fog':        {'id': 'bg_borealis',    'x':  -61.49, 'y': 164.59, 'level': 1, 'zone': 'mountaintops','name': 'Freezing Lake'},
    'mimic tear':                      {'id': 'bg_mimic',       'x': -184.91, 'y': 128.39, 'level': 2, 'zone': 'siofra',      'name': 'Nokron, Eternal City'},
    "commander o'neil":                {'id': 'bg_oneil',       'x': -180.50, 'y': 144.00, 'level': 1, 'zone': 'caelid',      'name': "Commander O'Neil"},
}

# Pre-fight tactical graces — agent explicitly visits these to shorten corpse runs.
# Added to warp_pool only when the agent chooses to visit them (unlike BOSS_GRACES
# which are added automatically after a kill).
TACTICAL_GRACES = [
    {'id': 'tg_margit',       'name': 'Castleward Tunnel',          'x': -180.70, 'y':  92.40, 'level': 1, 'zone': 'stormveil'},
    {'id': 'tg_godrick',      'name': 'Secluded Cell',              'x': -173.90, 'y':  84.60, 'level': 1, 'zone': 'stormveil'},
    {'id': 'tg_rennala',      'name': 'Schoolhouse Classroom',      'x': -136.50, 'y':  57.20, 'level': 1, 'zone': 'liurnia'},
    {'id': 'tg_loretta',      'name': 'Caria Manor Lower Level',    'x': -104.00, 'y':  57.50, 'level': 1, 'zone': 'caria_manor'},
    {'id': 'tg_radahn',       'name': 'Impassable Greatbridge',     'x': -198.00, 'y': 158.50, 'level': 1, 'zone': 'caelid'},
    {'id': 'tg_capital_gate', 'name': 'Capital Outskirts',          'x':  -96.50, 'y': 116.00, 'level': 1, 'zone': 'leyndell'},
    {'id': 'tg_leyndell_hub', 'name': 'Erdtree Sanctuary',          'x': -108.50, 'y': 117.00, 'level': 1, 'zone': 'leyndell'},
    {'id': 'tg_avenue',       'name': 'Avenue Balcony',             'x': -107.00, 'y': 116.00, 'level': 1, 'zone': 'leyndell'},
    {'id': 'tg_rykard',       'name': 'Prison Town Church',         'x':  -89.20, 'y':  65.00, 'level': 1, 'zone': 'volcano_manor'},
    {'id': 'tg_fire_giant',   'name': 'Foot of the Forge',          'x':  -90.50, 'y': 158.00, 'level': 1, 'zone': 'mountaintops'},
    {'id': 'tg_mohg',         'name': 'Dynasty Mausoleum Entrance', 'x': -183.00, 'y': 144.00, 'level': 2, 'zone': 'mohgwyn'},
    {'id': 'tg_malenia',      'name': 'Haligtree Town',             'x':  -45.00, 'y': 147.00, 'level': 1, 'zone': 'haligtree'},
]

# Roundtable Hold — teleport from any grace
ROUNDTABLE = {
    'id':   'roundtable',
    'name': 'Roundtable Hold',
    'x':    -160.0,
    'y':     90.0,
    'level': 1,
    'zone':  'liurnia',
    'is_roundtable': True,
}

# Prerequisite stops (used by router.js for route planning)
PREREQ_STOPS = {
    'nokron_access': {'name': 'Starscourge Radahn', 'x': -194.36, 'y': 160.21, 'level': 1, 'zone': 'caelid', 'runes': 70000},
    'radahn':        {'name': 'Starscourge Radahn', 'x': -194.36, 'y': 160.21, 'level': 1, 'zone': 'caelid', 'runes': 70000},
    'capital_access':{'name': 'Draconic Tree Sentinel', 'x': -93.609375, 'y': 120.199825, 'level': 1, 'zone': 'leyndell', 'runes': 50000},
}

# Prerequisite-only locations — must be visited but belong to no square's locations list.
# These become 'prereq' type entries in the UNIVERSE so the RL agent can route to them.
PREREQ_LOCS = [
    {'name': 'Third Church of Marika',                  'x': -180.125,    'y': 123.403,
     'level': 1, 'zone': 'limgrave',      'prereq_key': 'physick_flask'},
    {'name': "Ranni's Rise",                            'x': -106.42,     'y':  50.01,
     'level': 1, 'zone': 'caria_manor',   'prereq_key': 'ranni_quest_p1'},
    {'name': 'Commander Niall',                         'x':  -57.0,      'y': 157.5,
     'level': 1, 'zone': 'mountaintops',  'prereq_key': 'kill_commander_niall'},
    {'name': 'Commander Niall',                         'x':  -57.0,      'y': 157.5,
     'level': 1, 'zone': 'mountaintops',  'prereq_key': 'Kill Commander Niall for left half'},
    {'name': 'Waygate to Mohgwyn Palace',               'x':  -70.68,     'y': 129.59,
     'level': 1, 'zone': 'consecrated',  'prereq_key': 'mohgwyn_access'},
    # capital_access: Draconic Tree Sentinel blocks entry to Leyndell
    {'name': 'Draconic Tree Sentinel',                  'x':  -93.609375, 'y': 120.199825,
     'level': 1, 'zone': 'leyndell',      'prereq_key': 'capital_access'},
    {'name': 'Godfrey, First Elden Lord (Golden Shade)', 'x': -107.117,   'y': 116.465,
     'level': 1, 'zone': 'leyndell',      'prereq_key': 'kill_godfrey_gold_spirit'},
    {'name': 'Fell Twins',                              'x': -104.0,      'y': 132.1,
     'level': 1, 'zone': 'leyndell',      'prereq_key': 'Kill Fell Twins'},
    {'name': 'Royal Knight Loretta',                    'x': -104.635938, 'y':  56.783965,
     'level': 1, 'zone': 'caria_manor',   'prereq_key': 'kill_loretta'},
    {'name': 'Red Wolf of Radagon',                     'x': -138.0,      'y':  57.0,
     'level': 1, 'zone': 'liurnia',       'prereq_key': 'kill_red_wolf_of_radagon'},
    {'name': 'Onyx Lord (Sealed Tunnel)',               'x': -111.5,      'y': 105.77997,
     'level': 1, 'zone': 'leyndell',      'prereq_key': 'kill_onyx_lord_sealed_tunnel'},
    {'name': 'Astel, Naturalborn of the Void',          'x': -165.7,      'y':  47.6,
     'level': 2, 'zone': 'ainsel',        'prereq_key': 'kill_astel_lake_of_rot'},
    {'name': 'Blackguard Big Boggart',                  'x': -151.88,     'y':  67.387,
     'level': 1, 'zone': 'liurnia',       'prereq_key': 'boggart_necklace_bought'},
    # Academy Glintstone Keys — Key (A) is outside near Smarag (used to enter Academy),
    # Key (B) is the spare on the chandelier inside Church of the Cuckoo (given to Thops).
    # Key (A) listed first so it sets the PREREQ_TABLE entry; Key (B) still enters UNIVERSE.
    {'name': 'Academy Glintstone Key (A)',              'x': -137.05,     'y':  50.22,
     'level': 1, 'zone': 'liurnia',       'prereq_key': 'academy_glintstone_key'},
    {'name': 'Academy Glintstone Key (B)',              'x': -135.929687, 'y':  54.10881,
     'level': 1, 'zone': 'liurnia',       'prereq_key': 'academy_glintstone_key'},
    # Boss kill prereqs — agent routes here to kill boss and unlock grace even when
    # the standalone kill square isn't on the board.
    {'name': 'Margit, the Fell Omen',                  'x': -182.695312, 'y':  90.972955,
     'level': 1, 'zone': 'limgrave',      'prereq_key': 'kill_margit'},
    {'name': 'Godrick the Grafted',                    'x': -173.665626, 'y':  86.058335,
     'level': 1, 'zone': 'limgrave',      'prereq_key': 'Kill Godrick the Grafted'},
    {'name': 'Starscourge Radahn',                     'x': -194.5625,   'y': 159.103951,
     'level': 1, 'zone': 'caelid',        'prereq_key': 'nokron_access'},
    {'name': 'Starscourge Radahn',                     'x': -194.5625,   'y': 159.103951,
     'level': 1, 'zone': 'caelid',        'prereq_key': 'Kill Starscourge Radahn'},
    {'name': 'Rykard, Lord of Blasphemy',              'x':  -87.59375,  'y':  66.862074,
     'level': 1, 'zone': 'volcano_manor', 'prereq_key': 'Kill Rykard, Lord of Blasphemy'},
    {'name': 'Morgott, The Omen King',                 'x': -107.320312, 'y': 120.965331,
     'level': 1, 'zone': 'leyndell',      'prereq_key': 'Kill Morgott, The Omen King'},
]

# ── Weapon combat model (from timing.js) ──────────────────────────────────────
BOSS_HP = {
    'ancestor spirit':                          {'hp': 4393,  'def': 107, 'runes': 13000},
    'astel, naturalborn of the void':           {'hp': 11170, 'def': 114, 'runes': 80000},
    'astel, stars of darkness':                 {'hp': 18617, 'def': 120, 'runes': 120000},
    'beast clergyman':                          {'hp': 16461, 'def': 120, 'runes': 220000},
    'maliketh, the black blade':               {'hp': 16461, 'def': 120, 'runes': 220000},
    'bell bearing hunter':                      {'hp': 2495,  'def': 103, 'runes': 2700},
    'black blade kindred':                      {'hp': 12297, 'def': 121, 'runes': 88000},
    'bloodhound knight darriwil':               {'hp': 1450,  'def': 103, 'runes': 1900},
    'bloodhound knight':                        {'hp': 1985,  'def': 107, 'runes': 3600},
    'borealis the freezing fog':                 {'hp': 11268, 'def': 120, 'runes': 100000},
    'cemetery shade':                           {'hp': 781,   'def': 102, 'runes': 2200},
    "commander o'neil":                         {'hp': 9210,  'def': 111, 'runes': 12000},
    'crucible knight':                          {'hp': 2782,  'def': 103, 'runes': 2100},
    'crucible knight and crucible knight ordovis': {'hp': 5460, 'def': 111, 'runes': 28000},
    'death rite bird':                          {'hp': 6577,  'def': 110, 'runes': 7800},
    'deathbird':                                {'hp': 3442,  'def': 103, 'runes': 2800},
    'draconic tree sentinel':                   {'hp': 8398,  'def': 114, 'runes': 50000},
    'dragonkin soldier':                        {'hp': 5758,  'def': 114, 'runes': 16000},
    'dragonlord placidusax':                    {'hp': 26651, 'def': 121, 'runes': 280000},
    'elemer of the briar':                      {'hp': 4897,  'def': 111, 'runes': 24000},
    'erdtree avatar':                           {'hp': 3163,  'def': 105, 'runes': 3600},
    'fallingstar beast':                        {'hp': 5780,  'def': 111, 'runes': 9300},
    "fia's champions":                          {'hp': 12217, 'def': 130, 'runes': 40000},
    'fire giant':                               {'hp': 43263, 'def': 118, 'runes': 180000},
    'flying dragon agheel':                     {'hp': 3200,  'def': 106, 'runes': 5000},
    'godfrey, first elden lord':                {'hp': 7099,  'def': 114, 'runes': 80000},
    'godrick the grafted':                      {'hp': 6080,  'def': 105, 'runes': 20000},
    'godskin apostle':                          {'hp': 10562, 'def': 116, 'runes': 54000},
    'godskin duo':                              {'hp': 8000,  'def': 118, 'runes': 170000},
    'godskin noble':                            {'hp': 10060, 'def': 114, 'runes': 50000},
    'grafted scion':                            {'hp': 2596,  'def': 107, 'runes': 3200},
    'leonine misbegotten':                      {'hp': 2199,  'def': 103, 'runes': 3800},
    'loretta, knight of the haligtree':         {'hp': 13397, 'def': 122, 'runes': 200000},
    'magma wyrm':                               {'hp': 7141,  'def': 109, 'runes': 15000},
    'malenia, blade of miquella':               {'hp': 33251, 'def': 123, 'runes': 480000},
    'margit, the fell omen':                    {'hp': 4174,  'def': 103, 'runes': 12000},
    'mimic tear':                               {'hp': 1242,  'def': 75,  'runes': 10000},
    'misbegotten crusader':                     {'hp': 9130,  'def': 120, 'runes': 93000},
    'misbegotten warrior and crucible knight':  {'hp': 3569,  'def': 110, 'runes': 16000},
    'mohg, lord of blood':                      {'hp': 18389, 'def': 122, 'runes': 420000},
    'mohg, the omen':                           {'hp': 14000, 'def': 117, 'runes': 100000},
    'morgott, the omen king':                   {'hp': 10399, 'def': 114, 'runes': 120000},
    "night's cavalry":                          {'hp': 1665,  'def': 103, 'runes': 2400},
    "night's cavalry duo":                      {'hp': 7246,  'def': 122, 'runes': 84000},
    'omenkiller':                               {'hp': 2306,  'def': 110, 'runes': 4900},
    'putrid crystalian trio':                   {'hp': 10074, 'def': 109, 'runes': 7100},
    'red wolf of radagon':                      {'hp': 2204,  'def': 107, 'runes': 14000},
    'regal ancestor spirit':                    {'hp': 6301,  'def': 111, 'runes': 24000},
    'rennala, queen of the full moon':          {'hp': 7590,  'def': 109, 'runes': 40000},
    'roundtable knight vyke':                   {'hp': 5366,  'def': 104, 'runes': 75000},
    'royal knight loretta':                     {'hp': 4214,  'def': 107, 'runes': 10000},
    'soldier of godrick':                       {'hp': 384,   'def': 100, 'runes': 400},
    'starscourge radahn':                       {'hp': 9572,  'def': 113, 'runes': 70000},
    'tibia mariner':                            {'hp': 3176,  'def': 103, 'runes': 2400},
    'tree sentinel':                            {'hp': 2889,  'def': 103, 'runes': 3200},
    'tree sentinel duo':                        {'hp': 6461,  'def': 113, 'runes': 20000},
    'valiant gargoyles':                        {'hp': 5671,  'def': 111, 'runes': 30000},
    'wormface':                                 {'hp': 5876,  'def': 113, 'runes': 10000},

    # ── Dragons ────────────────────────────────────────────────────────────────
    'ancient dragon lansseax':               {'hp': 9087,  'def': 115, 'runes': 60000},
    'glintstone dragon smarag':              {'hp': 6069,  'def': 113, 'runes': 14000},
    'glintstone dragon adula':               {'hp': 11550, 'def': 121, 'runes': 120000},
    'flying dragon greyll':                  {'hp': 11550, 'def': 121, 'runes': 80000},
    'decaying ekzykes':                      {'hp': 23731, 'def': 114, 'runes': 38000},
    'great wyrm theodorix':                  {'hp': 25649, 'def': 122, 'runes': 180000},
    'lichdragon fortissax':                  {'hp': 12903, 'def': 114, 'runes': 90000},
    'dragonkin soldier of nokstella':        {'hp': 4372,  'def': 106, 'runes': 12000},
    'dragonkin soldier (lake of rot)':       {'hp': 7655,  'def': 117, 'runes': 58000},

    # ── Named field / evergaol bosses ─────────────────────────────────────────
    'god-devouring serpent':                 {'hp': 59174, 'def': 115, 'runes': 130000},
    'rykard, lord of blasphemy':             {'hp': 59174, 'def': 115, 'runes': 130000},
    'alecto, black knife ringleader':        {'hp': 17482, 'def': 120, 'runes': 80000},
    'commander niall':                       {'hp': 15541, 'def': 117, 'runes': 90000},
    'fell twins':                            {'hp': 14410, 'def': 115, 'runes': 29000},
    'full-grown fallingstar beast':          {'hp': 13010, 'def': 114, 'runes': 21000},
    'godefroy the grafted':                  {'hp': 12419, 'def': 113, 'runes': 26000},
    'magma wyrm makar':                      {'hp': 7141,  'def': 109, 'runes': 24000},
    'crucible knight siluria':               {'hp': 4606,  'def': 117, 'runes': 25000},
    "bols, carian knight":                   {'hp': 5109,  'def': 110, 'runes': 4600},
    'godskin apostle (caelid)':              {'hp': 13596, 'def': 120, 'runes': 94000},
    'roundtable knight vyke':                {'hp': 5366,  'def': 104, 'runes': 75000},
    'black blade kindred (forbidden lands)': {'hp': 8452,  'def': 115, 'runes': 60000},
    'night cavalry (forbidden lands)':       {'hp': 6602,  'def': 118, 'runes': 36000},

    # ── Tree spirits ──────────────────────────────────────────────────────────
    'ulcerated tree spirit':                 {'hp': 6147,  'def': 107, 'runes': 15000},
    'putrid tree spirit':                    {'hp': 18144, 'def': 120, 'runes': 64000},

    # ── Dungeon / catacomb bosses ─────────────────────────────────────────────
    'black knife assassin':                  {'hp': 2500,  'def': 107, 'runes': 5000},
    'grave warden duelist':                  {'hp': 3200,  'def': 106, 'runes': 2000},
    'putrid grave warden duelist':           {'hp': 8800,  'def': 120, 'runes': 78000},
    'erdtree burial watchdog':               {'hp': 2000,  'def': 104, 'runes': 2200},
    'ancient hero of zamor':                 {'hp': 3800,  'def': 108, 'runes': 25000},
    'runebear':                              {'hp': 3311,  'def': 102, 'runes': 2600},
    'frenzied duelist':                      {'hp': 3079,  'def': 109, 'runes': 6700},
    'onyx lord':                             {'hp': 4500,  'def': 111, 'runes': 10000},
    'putrid avatar':                         {'hp': 10000, 'def': 117, 'runes': 90000},
    'stonedigger troll':                     {'hp': 2100,  'def': 104, 'runes': 4000},
    'mad pumpkin head':                      {'hp': 1328,  'def': 101, 'runes': 1100},
    'guardian golem':                        {'hp': 5974,  'def': 101, 'runes': 1700},
    'royal revenant':                        {'hp': 3077,  'def': 107, 'runes': 3100},
    'cleanrot knight':                       {'hp': 2050,  'def': 108, 'runes': 5000},
    'demi-human queen':                      {'hp': 4000,  'def': 110, 'runes': 9000},
    'spiritcaller snail':                    {'hp': 1722,  'def': 107, 'runes': 3000},
    'sanguine noble':                        {'hp': 3128,  'def': 110, 'runes': 8800},
    'beastman of farum azula':               {'hp': 1417,  'def': 101, 'runes': 1000},
    'miranda the blighted bloom':            {'hp': 2360,  'def': 103, 'runes': 1800},
    'kindred of rot':                        {'hp': 2100,  'def': 104, 'runes': 1700},
    'anastasia, tarnished-eater':            {'hp': 2800,  'def': 104, 'runes': 1200},
    'rileigh the idle':                      {'hp': 2200,  'def': 104, 'runes': 1500},
    'battlemage hugues':                     {'hp': 4095,  'def': 111, 'runes': 7800},
    'red wolf of the champion':              {'hp': 3162,  'def': 111, 'runes': 21000},
    'godfrey (ashen capital)':               {'hp': 21903, 'def': 120, 'runes': 300000},

    # ── NPC fights / special encounters ──────────────────────────────────────
    'elder dragon greyoll':                  {'hp': 17350, 'def': 110, 'runes': 50000},  # 5x small dragons (3470 each)
    'gurranq':                               {'hp': 10620, 'def': 116, 'runes': 10000},
    'esgar, priest of blood':                {'hp': 3511,  'def': 94,  'runes': 30000},
    'magnus the beast claw':                 {'hp': 4345,  'def': 110, 'runes': 1754},
    'milicent invader':                      {'hp': 1000,  'def': 95,  'runes': 316},
    'stray mimic tear':                      {'hp': 1242,  'def': 75,  'runes': 50000},

    # ── Lion Guardians (zone-specific HP) ────────────────────────────────────
    'lion guardian stormveil':               {'hp': 2119,  'def': 103, 'runes': 1500},
    'lion guardian redmane':                 {'hp': 3440,  'def': 110, 'runes': 5000},
    'lion guardian leyndell':                {'hp': 4739,  'def': 113, 'runes': 8000},
    'lion guardian caelid':                  {'hp': 3079,  'def': 109, 'runes': 6000},
    'lion guardian castle sol':              {'hp': 7019,  'def': 117, 'runes': 15000},
}

WEAPON_DPS_FACTOR = {
    'Dagger': 2.23,            'Throwing Blade': 1.42,     'Straight Sword': 1.83,
    'Light Greatsword': 1.52,  'Greatsword': 1.24,         'Colossal Sword': 0.78,
    'Thrusting Sword': 2.03,   'Heavy Thrusting Sword': 1.62, 'Curved Sword': 1.93,
    'Curved Greatsword': 1.36, 'Backhand Blade': 2.13,     'Katana': 1.83,
    'Great Katana': 1.24,      'Twinblade': 2.03,          'Axe': 1.62,
    'Greataxe': 1.03,          'Hammer': 1.53,             'Flail': 1.55,
    'Great Hammer': 0.93,      'Colossal Weapon': 0.72,    'Spear': 1.80,
    'Great Spear': 1.24,       'Halberd': 1.34,            'Reaper': 1.24,
    'Whip': 1.64,              'Fist': 2.44,               'Hand-to-Hand': 1.42,
    'Claw': 2.23,              'Beast Claw': 2.30,         'Glintstone Staff': 1.01,
    'Sacred Seal': 1.01,
}

WEAPON_CLASSES = list(WEAPON_DPS_FACTOR.keys())

# Staves are NOT randomized in S6
STAVES = [
    'Astrologer\'s Staff', 'Demi-Human Queen\'s Staff', 'Digger\'s Staff',
    'Gelmir Glintstone Staff', 'Glintstone Staff', 'Lusat\'s Glintstone Staff',
    'Meteorite Staff', 'Prince of Death\'s Staff', 'Rotten Glintstone Staff',
    'Staff of Loss', 'Staff of the Avatar',
]

BASE_AR = {
    'Dagger': 110,          'Straight Sword': 130,   'Light Greatsword': 140,
    'Greatsword': 145,      'Colossal Sword': 180,   'Thrusting Sword': 125,
    'Heavy Thrusting Sword': 145, 'Curved Sword': 120, 'Curved Greatsword': 148,
    'Backhand Blade': 115,  'Katana': 130,           'Great Katana': 155,
    'Twinblade': 128,       'Axe': 130,              'Greataxe': 155,
    'Hammer': 130,          'Flail': 128,            'Great Hammer': 162,
    'Colossal Weapon': 175, 'Spear': 120,            'Great Spear': 155,
    'Halberd': 148,         'Reaper': 152,           'Whip': 112,
    'Fist': 95,             'Claw': 97,              'Sacred Seal': 75,
    'Glintstone Staff': 80,
}

SMITHING_MULT = [
    1.000, 1.058, 1.116, 1.174, 1.232, 1.290,
    1.348, 1.406, 1.464, 1.522, 1.580,
    1.620, 1.660, 1.700, 1.740, 1.780,
    1.820, 1.860, 1.900, 1.940, 1.980,
    2.020, 2.060, 2.100, 2.140,
]

SOMBER_MULT = [1.000, 1.125, 1.250, 1.375, 1.500, 1.625, 1.750, 1.875, 2.000, 2.125]

STAT_SCALING = {
    'Strength':  {'early': 0.25, 'mid': 0.50, 'late': 0.80},
    'Dexterity': {'early': 0.20, 'mid': 0.45, 'late': 0.70},
    'Faith':     {'early': 0.15, 'mid': 0.35, 'late': 0.60},
    'Int':       {'early': 0.15, 'mid': 0.35, 'late': 0.60},
    'Quality':   {'early': 0.22, 'mid': 0.47, 'late': 0.70},
}

SMITHING_RUNE_COST = [
    0, 200, 400, 600, 900, 1200, 1500, 2000, 2500, 3000,
    3500, 4000, 5000, 6000, 7000, 8000, 9000, 10000, 11000, 12000,
    13000, 14000, 15000, 16000, 17000,
]
SOMBER_RUNE_COST = [0, 200, 400, 700, 1000, 1400, 1800, 2300, 2800, 3500]

# ── Bingo board geometry ───────────────────────────────────────────────────────
BOARD_SIZE  = 5
N_SQUARES   = 25
BINGO_LINES = (
    # Rows
    [0,1,2,3,4], [5,6,7,8,9], [10,11,12,13,14], [15,16,17,18,19], [20,21,22,23,24],
    # Cols
    [0,5,10,15,20], [1,6,11,16,21], [2,7,12,17,22], [3,8,13,18,23], [4,9,14,19,24],
    # Diagonals
    [0,6,12,18,24], [4,8,12,16,20],
)
N_LINES = len(BINGO_LINES)

# ── Combat helpers ─────────────────────────────────────────────────────────────
def compute_ar(weapon_class, weapon_level, is_somber, primary_stat, rune_level):
    base = BASE_AR.get(weapon_class, 130)
    mult = (SOMBER_MULT[min(weapon_level, 9)] if is_somber
            else SMITHING_MULT[min(weapon_level, 24)])
    base_upgraded = base * mult
    stat_tier = 'early' if rune_level < 30 else ('mid' if rune_level < 60 else 'late')
    scaling = (STAT_SCALING.get(primary_stat) or STAT_SCALING['Strength'])[stat_tier]
    return round(base_upgraded + base * scaling)


def get_boss_difficulty(boss_name: str) -> float:
    """Returns the difficulty rating for a boss (1.0 = easy, 3.0 = Malenia)."""
    key = boss_name.lower().strip().replace('-', ' ')
    if key in BOSS_DIFFICULTY:
        return BOSS_DIFFICULTY[key]
    for k in BOSS_DIFFICULTY:
        if key in k or k in key.split('(')[0].strip():
            return BOSS_DIFFICULTY[k]
    return 1.3


def compute_kill_time(boss_name, weapon_class, weapon_level, is_somber,
                      primary_stat, rune_level, zone='unknown'):
    """Returns {'kill_sec': int, 'runes': int, 'difficulty': float} or None.

    Models three factors the flat DPS formula misses:
      1. Boss difficulty   — harder bosses give fewer safe attack windows
                             (effective_uptime = BOSS_UPTIME / difficulty)
      2. Phase overhead    — flat seconds for cutscenes / phase transitions
      3. +0 struggle       — low weapon = cautious play + more flask usage;
                             ~2× longer at +0, decays quadratically to 1× at max
    """
    key = boss_name.lower().strip().replace('-', ' ')
    boss_data = BOSS_HP.get(key)
    if not boss_data:
        for k, v in BOSS_HP.items():
            if key in k or k in key.split('(')[0].strip():
                boss_data = v
                key = k   # update so difficulty lookup uses matched key
                break
    if not boss_data:
        return None

    ar           = compute_ar(weapon_class, weapon_level, is_somber, primary_stat, rune_level)
    dps_factor   = WEAPON_DPS_FACTOR.get(weapon_class, 1.4)
    hps          = dps_factor / 1.032
    dmg_per_hit  = (ar * ar) / (ar + boss_data['def'])

    difficulty       = BOSS_DIFFICULTY.get(key, 1.3)
    effective_uptime = BOSS_UPTIME / difficulty
    effective_dps    = dmg_per_hit * hps * effective_uptime

    base_kill_sec  = math.ceil(boss_data['hp'] / effective_dps)
    phase_overhead = BOSS_PHASE_OVERHEAD.get(key, 0)

    # At +0: fights take ~2× longer (tickling bosses → more healing, more careful).
    # Penalty fades quadratically: (1 - progress)² so it's steep at low levels.
    max_lv        = 9 if is_somber else 24
    progress      = weapon_level / max_lv
    struggle_mult = 1.0 + 1.0 * (1.0 - progress) ** 2

    kill_sec = math.ceil((base_kill_sec + phase_overhead) * struggle_mult)
    return {'kill_sec': kill_sec, 'runes': boss_data['runes'], 'difficulty': difficulty}


def compute_travel_time(from_loc, to_loc, warp_pool=None):
    """Travel time in seconds from from_loc to to_loc using nearest grace warp."""
    if to_loc.get('is_roundtable'):
        return OVERHEAD_ROUNDTABLE_SEC

    def _dist(a, b):
        return math.sqrt((a['x'] - b['x'])**2 + (a['y'] - b['y'])**2)

    to_level = to_loc.get('level', 1)
    pool = warp_pool or [from_loc]

    if to_level == 2:
        entry = SURF_ENTRIES.get(to_loc.get('zone', ''), SURF_ENTRIES['siofra'])
        ug_graces  = [g for g in pool if g.get('level', 1) == 2]
        surf_graces = [g for g in pool if g.get('level', 1) != 2]
        ug_dist   = min((_dist(g, to_loc) for g in ug_graces),   default=float('inf'))
        surf_dist = min((_dist(g, entry) + _dist(entry, to_loc) for g in surf_graces), default=float('inf'))
        dist = min(ug_dist, surf_dist)
    else:
        surf_graces = [g for g in pool if g.get('level', 1) != 2]
        dist = min((_dist(g, to_loc) for g in surf_graces), default=_dist(from_loc, to_loc))

    zone  = to_loc.get('zone', 'unknown')
    speed = ZONE_SPEED_MULT.get(zone, 1.3)
    return math.ceil(dist * TRAVEL_SEC_PER_UNIT * speed)


def stones_needed(from_level, to_level, is_somber):
    """Returns {tier: count} of stones to upgrade from from_level to to_level."""
    needs = {}
    for lvl in range(from_level + 1, to_level + 1):
        tier = lvl if is_somber else ((lvl - 1) // 3 + 1)
        needs[tier] = needs.get(tier, 0) + 1
    return needs


def level_up_cost(level: int) -> int:
    """Rune cost for a single level-up from `level` to `level+1`."""
    if level < 12:
        return int(673 * (1.04 ** level))
    elif level < 92:
        return int(0.02 * level**3 + 3.06 * level**2 + 105.6 * level - 895)
    else:
        return int(0.1 * level**3 - 16 * level**2 + 2010 * level - 60000)


def runes_to_reach_level(target: int, start: int = 1) -> int:
    """Total runes spent going from `start` to `target` rune level."""
    return sum(level_up_cost(lvl) for lvl in range(start, target))


def compute_rune_level(total_runes, start=1):
    level, remaining = start, total_runes
    while remaining > 0 and level < 150:
        if level < 12:
            cost = int(673 * (1.04 ** level))
        elif level < 92:
            cost = int(0.02 * level**3 + 3.06 * level**2 + 105.6 * level - 895)
        else:
            cost = int(0.1 * level**3 - 16 * level**2 + 2010 * level - 60000)
        if remaining < cost:
            break
        remaining -= cost
        level += 1
    return level


def max_upgrade_level(rune_balance, is_somber):
    """Max weapon level achievable with given rune balance."""
    costs = SOMBER_RUNE_COST if is_somber else SMITHING_RUNE_COST
    max_lv = 9 if is_somber else 24
    level, spent = 0, 0
    while level < max_lv:
        cost = costs[level + 1] if level + 1 < len(costs) else float('inf')
        if spent + cost > rune_balance:
            break
        spent += cost
        level += 1
    return level


def dungeon_overhead(square_name):
    name = square_name.lower()
    if 'catacomb' in name:     return DUNGEON_OVERHEAD['catacombs']
    if 'cave' in name or 'grotto' in name: return DUNGEON_OVERHEAD['cave']
    if 'tunnel' in name or 'precipice' in name: return DUNGEON_OVERHEAD['tunnel']
    if 'evergaol' in name:     return DUNGEON_OVERHEAD['evergaol']
    if 'hero' in name:         return DUNGEON_OVERHEAD['hero_grave']
    return DUNGEON_OVERHEAD['dungeon']


def boss_weapon_floor(zone: str, is_somber: bool) -> int:
    """Minimum weapon level to fight comfortably in this zone."""
    tier = ZONE_TIER.get(zone, 4)
    arr  = _ZONE_WEAPON_FLOOR_SOMBER if is_somber else _ZONE_WEAPON_FLOOR_STD
    return arr[min(tier, len(arr) - 1)]


def compute_death_probability(zone: str, weapon_level: int, is_somber: bool) -> float:
    """P(dying on first attempt) against a boss in this zone at current weapon_level.

    0.18 per level of deficit vs zone floor, capped at 0.90.
    Deficit = 0 means no penalty (at or above expected level).
    """
    floor  = boss_weapon_floor(zone, is_somber)
    deficit = max(0, floor - weapon_level)
    return min(0.90, deficit * 0.18)


# ── Stone node data (loaded from square_data.json at import) ──────────────────
_raw = _load_json('square_data.json')

# Only "direct" access stones are guaranteed world pickups (not random enemy drops)
STONE_NODES = [
    s for s in _raw['_meta']['poi_stones']
    if s.get('access_tier') == 'direct' and s.get('tier', 99) <= 9
]

# Prereq resolution table — maps every prereq key to how the sim enforces it.
# Loaded from square_data.json so adding a new prereq only requires a JSON edit.
PREREQ_RESOLUTION: dict = _raw['_meta'].get('prereq_resolution', {})
