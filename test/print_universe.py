"""Print all UNIVERSE actions to universe_actions.txt"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from jack.rl.board import UNIVERSE, UNIVERSE_SIZE

out_path = os.path.join(os.path.dirname(__file__), 'universe_actions.txt')

with open(out_path, 'w', encoding='utf-8') as f:
    f.write(f"Total actions: {UNIVERSE_SIZE}\n")
    f.write("=" * 80 + "\n\n")

    objectives = [e for e in UNIVERSE if e['type'] == 'objective']
    stones     = [e for e in UNIVERSE if e['type'] == 'stone']
    roundtable = [e for e in UNIVERSE if e['type'] == 'roundtable']

    f.write(f"OBJECTIVES ({len(objectives)})\n")
    f.write("-" * 80 + "\n")
    for i, e in enumerate(objectives):
        idx  = UNIVERSE.index(e)
        loc  = e['loc']
        name = loc.get('name', '?')
        zone = loc.get('zone', '?')
        lvl  = loc.get('level', 1)
        sq   = ', '.join(sorted(e['sq_names']))
        f.write(f"[{idx:3d}] {name:<45} zone={zone:<18} lvl={lvl}  sq={sq}\n")

    f.write(f"\nSTONE NODES ({len(stones)})\n")
    f.write("-" * 80 + "\n")
    for e in stones:
        idx    = UNIVERSE.index(e)
        loc    = e['loc']
        stype  = 'Somber' if e['stone_somber'] else 'Smithing'
        f.write(f"[{idx:3d}] {stype} Stone [{e['stone_tier']}]  "
                f"@ ({loc.get('x','?'):.2f}, {loc.get('y','?'):.2f})  "
                f"zone={loc.get('zone','?')}\n")

    f.write(f"\nROUNDTABLE ({len(roundtable)})\n")
    f.write("-" * 80 + "\n")
    for e in roundtable:
        idx = UNIVERSE.index(e)
        f.write(f"[{idx:3d}] Roundtable Hold\n")

print(f"Written {UNIVERSE_SIZE} actions to {out_path}")
