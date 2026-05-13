#!/usr/bin/env python3
"""
board_synergy.py — Jack of All Graves
Computes synergy metrics for a generated bingo board.

Synergy = how much squares share locations or cluster geographically,
reducing total travel needed to complete the board.

Usage:
    python board_synergy.py
    python board_synergy.py --seed 42
    python board_synergy.py --seed 42 --lines
    python board_synergy.py --samples 1000   # score distribution across random boards
"""

import sys, os, argparse, math, random
from collections import defaultdict

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, '..', '..'))

from jack.rl.board import generate_board, _loc_key
from jack.rl.constants import ZONE_PENALTY, ZONE_TIER, BINGO_LINES


# ── Zone helpers ───────────────────────────────────────────────────────────────

LINE_NAMES = [
    'Row 1','Row 2','Row 3','Row 4','Row 5',
    'Col 1','Col 2','Col 3','Col 4','Col 5',
    'Diag \\','Diag /',
]

def _primary_zone(sq):
    """Most common zone among the square's locations, or 'passive'."""
    if sq.is_passive or not sq.locations:
        return 'passive'
    counts = defaultdict(int)
    for loc in sq.locations:
        counts[loc.get('zone', 'unknown')] += 1
    return max(counts, key=counts.get)

def _all_zones(sq):
    """Set of all zones this square's locations touch."""
    if sq.is_passive or not sq.locations:
        return set()
    return {loc.get('zone', 'unknown') for loc in sq.locations}


# ── Core metrics ───────────────────────────────────────────────────────────────

def coloc_pairs(squares):
    """
    Returns list of (sq_a, sq_b) pairs that share at least one visit location.
    Completing either square will visit a location that contributes to the other.
    """
    pairs = []
    for i, a in enumerate(squares):
        if a.is_passive:
            continue
        keys_a = a.loc_keys()
        for b in squares[i+1:]:
            if b.is_passive:
                continue
            if keys_a & b.loc_keys():
                pairs.append((a, b))
    return pairs


def zone_distribution(squares):
    """zone → list of squares whose primary zone is that zone."""
    dist = defaultdict(list)
    for sq in squares:
        dist[_primary_zone(sq)].append(sq)
    return dict(dist)


def line_metrics(squares):
    """
    Per bingo line: {
        name, indices,
        coloc_pairs: int,       # co-located pairs within this line
        unique_zones: set,      # zones touched by any square in line
        avg_zone_penalty: float,
        passives: int,          # passive squares (no locations)
    }
    """
    results = []
    for line_idx, indices in enumerate(BINGO_LINES):
        line_sqs = [squares[i] for i in indices]
        active   = [s for s in line_sqs if not s.is_passive]

        # Co-location within this line
        pairs = 0
        for i, a in enumerate(active):
            for b in active[i+1:]:
                if a.loc_keys() & b.loc_keys():
                    pairs += 1

        # Zone spread
        zones = set()
        for s in active:
            zones |= _all_zones(s)

        avg_pen = (sum(ZONE_PENALTY.get(z, 0.3) for z in zones) / len(zones)) if zones else 0.0

        results.append({
            'name':              LINE_NAMES[line_idx],
            'indices':           indices,
            'coloc_pairs':       pairs,
            'unique_zones':      zones,
            'avg_zone_penalty':  avg_pen,
            'passives':          sum(1 for s in line_sqs if s.is_passive),
        })
    return results


def board_score(squares):
    """
    Composite synergy score 0–100. Higher = more efficient board.

    Components:
      Co-location  (0–40): bonus for square pairs sharing a location
      Zone ease    (0–40): bonus for squares in lower-penalty zones
      Line tight   (0–20): bonus for bingo lines that stay within few zones
    """
    active = [s for s in squares if not s.is_passive]
    if not active:
        return 0.0

    # Co-location: each pair is a "free ride"; cap contribution at 8 pairs
    pairs  = len(coloc_pairs(squares))
    coloc  = min(pairs / 8.0, 1.0) * 40.0

    # Zone ease: average ZONE_PENALTY across all unique zones needed
    all_zones = set()
    for s in active:
        all_zones |= _all_zones(s)
    avg_penalty = (sum(ZONE_PENALTY.get(z, 0.3) for z in all_zones) / len(all_zones)) if all_zones else 0.0
    zone_ease   = max(0.0, 1.0 - avg_penalty / 0.75) * 40.0

    # Line tightness: for each line, penalise high zone spread
    lm = line_metrics(squares)
    active_lines = [l for l in lm if l['passives'] < 5]
    if active_lines:
        avg_spread = sum(len(l['unique_zones']) for l in active_lines) / len(active_lines)
        line_tight = max(0.0, 1.0 - (avg_spread - 1) / 8.0) * 20.0
    else:
        line_tight = 10.0

    return round(coloc + zone_ease + line_tight, 1)


# ── Formatting ─────────────────────────────────────────────────────────────────

def _bar(val, max_val, width=20, char='█'):
    filled = round(val / max_val * width) if max_val else 0
    return char * filled + '░' * (width - filled)

ZONE_ORDER = [
    'limgrave','weeping_peninsula','stormveil','siofra','liurnia',
    'caria_manor','caelid','dragonbarrow','altus_plateau','mt_gelmir',
    'volcano_manor','leyndell','deeproot','ainsel','mohgwyn',
    'mountaintops','consecrated','haligtree','farum_azula','unknown','passive',
]

def _zone_label(z):
    return z.replace('_', ' ').title()


def report(squares, show_lines=False):
    score = board_score(squares)
    pairs = coloc_pairs(squares)
    zdist = zone_distribution(squares)
    lm    = line_metrics(squares)
    active = [s for s in squares if not s.is_passive]

    # ── Header ─────────────────────────────────────────────────────────────────
    print()
    print('╔══════════════════════════════════════════════════════════════╗')
    print(f'║  Board Synergy Score: {score:>5.1f} / 100                           ║')
    print('╚══════════════════════════════════════════════════════════════╝')
    print()

    # ── Board grid (5×5 zone overview) ────────────────────────────────────────
    print('Board (primary zone per square):')
    for row in range(5):
        cells = []
        for col in range(5):
            sq = squares[row * 5 + col]
            z  = _primary_zone(sq)
            label = _zone_label(z)[:14].center(14)
            cells.append(label)
        print('  ' + ' │ '.join(cells))
        if row < 4:
            print('  ' + '─' * 14 + ('─┼─' + '─' * 14) * 4)
    print()

    # ── Co-location pairs ──────────────────────────────────────────────────────
    print(f'Co-location pairs: {len(pairs)}  (squares sharing ≥1 visit location)')
    if pairs:
        for a, b in pairs:
            shared = sorted(a.loc_keys() & b.loc_keys())
            print(f'  [{a.idx:2d}] {a.text[:36]:<36}  ↔  [{b.idx:2d}] {b.text[:36]}')
    print()

    # ── Zone distribution ──────────────────────────────────────────────────────
    max_count = max((len(v) for v in zdist.values()), default=1)
    print('Zone distribution  (# squares with primary location in zone):')
    for z in ZONE_ORDER:
        sqs = zdist.get(z, [])
        if not sqs:
            continue
        pen   = ZONE_PENALTY.get(z, 0.0)
        bar   = _bar(len(sqs), max_count, width=12)
        label = _zone_label(z)
        print(f'  {label:<20}  {bar}  {len(sqs):2d}   penalty={pen:.2f}')
    print()

    # ── Per-line summary ───────────────────────────────────────────────────────
    if show_lines:
        print('Bingo line synergy:')
        header = f'  {"Line":<10}  {"Zones":>5}  {"Avg Pen":>7}  {"Colocs":>6}  {"Passives":>8}'
        print(header)
        print('  ' + '─' * (len(header) - 2))
        for l in lm:
            nz  = len(l['unique_zones'])
            pen = l['avg_zone_penalty']
            print(f'  {l["name"]:<10}  {nz:>5}  {pen:>7.2f}  {l["coloc_pairs"]:>6}  {l["passives"]:>8}')
        print()

    # ── Component breakdown ────────────────────────────────────────────────────
    all_zones = set()
    for s in active:
        all_zones |= _all_zones(s)
    avg_pen   = (sum(ZONE_PENALTY.get(z, 0.3) for z in all_zones) / len(all_zones)) if all_zones else 0.0
    lm_active = [l for l in lm if l['passives'] < 5]
    avg_spread= (sum(len(l['unique_zones']) for l in lm_active) / len(lm_active)) if lm_active else 1.0

    coloc_pts = min(len(pairs) / 8.0, 1.0) * 40.0
    ease_pts  = max(0.0, 1.0 - avg_pen / 0.75) * 40.0
    tight_pts = max(0.0, 1.0 - (avg_spread - 1) / 8.0) * 20.0

    print('Score breakdown:')
    print(f'  Co-location  {coloc_pts:>5.1f}/40  ({len(pairs)} pairs)')
    print(f'  Zone ease    {ease_pts:>5.1f}/40  (avg penalty {avg_pen:.2f}  across {len(all_zones)} zones)')
    print(f'  Line tight   {tight_pts:>5.1f}/20  (avg {avg_spread:.1f} zones per line)')
    print(f'  ─────────────────')
    print(f'  Total        {score:>5.1f}/100')
    print()


def distribution_report(n_samples):
    """Sample n boards and show score distribution."""
    scores = []
    for _ in range(n_samples):
        squares = generate_board()
        scores.append(board_score(squares))

    scores.sort()
    lo, hi = scores[0], scores[-1]
    mean   = sum(scores) / len(scores)
    median = scores[len(scores) // 2]
    p25    = scores[len(scores) // 4]
    p75    = scores[3 * len(scores) // 4]

    print()
    print(f'Score distribution across {n_samples} random boards:')
    print(f'  Min    {lo:.1f}')
    print(f'  P25    {p25:.1f}')
    print(f'  Median {median:.1f}')
    print(f'  Mean   {mean:.1f}')
    print(f'  P75    {p75:.1f}')
    print(f'  Max    {hi:.1f}')

    # ASCII histogram
    bucket_size = 5
    buckets = defaultdict(int)
    for s in scores:
        buckets[int(s // bucket_size) * bucket_size] += 1
    print()
    print('Histogram (bucket size = 5):')
    max_b = max(buckets.values())
    for b in sorted(buckets):
        bar = _bar(buckets[b], max_b, width=30)
        print(f'  {b:3d}–{b+4:3d}  {bar}  {buckets[b]}')
    print()


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Board synergy analyser')
    parser.add_argument('--seed',    type=int, default=None, help='RNG seed for reproducible board')
    parser.add_argument('--lines',   action='store_true',    help='Show per-line breakdown')
    parser.add_argument('--samples', type=int, default=None, help='Sample N boards and show distribution')
    args = parser.parse_args()

    if args.samples:
        distribution_report(args.samples)
        return

    squares = generate_board(seed=args.seed)
    if args.seed is not None:
        print(f'Seed: {args.seed}')
    report(squares, show_lines=args.lines)


if __name__ == '__main__':
    main()
