"""
Analyze per-square completion time distributions across many games.

Runs the DeterministicSolver (or a model checkpoint) against a random opponent
and records, for each square, when it was completed (in minutes).

Usage:
    python -m test.analyze_square_times                          # solver, 500 games
    python -m test.analyze_square_times --games 1000
    python -m test.analyze_square_times --model jack/rl/models/bingo_agent.zip
    python -m test.analyze_square_times --out square_times.json  # save raw data
"""
import argparse
import json
import os
import sys
import statistics
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from jack.rl.board import generate_board, UNIVERSE_SIZE
from jack.rl.sim import BingoGame
from jack.rl.constants import N_SQUARES


def _load_agent(path):
    if path is None or path == 'det':
        from jack.solver.det_solver import DeterministicSolver
        return DeterministicSolver(), 'DeterministicSolver'
    from sb3_contrib import MaskablePPO
    from jack.rl.train import BingoExtractor  # noqa: F401
    model = MaskablePPO.load(path)
    return model, os.path.basename(path)


def _act(agent, game, agent_id, mask, deterministic=True):
    if hasattr(agent, 'act'):
        return agent.act(game, agent_id, mask)
    obs = game.get_obs(agent_id)
    import numpy as np
    action, _ = agent.predict(obs, action_masks=mask, deterministic=deterministic)
    return int(action)


def run_games(agent, n_games=500, verbose=True):
    """Returns dict: sq_name -> list of completion times (seconds)."""
    times_by_sq = defaultdict(list)   # sq_name -> [seconds, ...]
    pick_counts  = defaultdict(int)    # sq_name -> how many games it appeared

    for game_idx in range(n_games):
        board = generate_board(seed=game_idx)
        game  = BingoGame(board)

        # Track which squares are on this board
        sq_names = [sq.text for sq in board]
        for name in set(sq_names):
            pick_counts[name] += 1

        done = False
        step = 0
        while not done and step < 300:
            mask = game.get_action_mask(0)
            action = _act(agent, game, 0, mask)
            _, done, info = game.step(0, action)

            completed_time = game.agents[0].time
            for sq_idx in info.get('sq_completed', []):
                name = sq_names[sq_idx]
                times_by_sq[name].append(completed_time)

            if not done:
                # Random opponent
                mask1 = game.get_action_mask(1)
                valid  = [i for i, m in enumerate(mask1) if m]
                if valid:
                    import random
                    game.step(1, random.choice(valid))

            step += 1

        if verbose and (game_idx + 1) % 100 == 0:
            print(f"  {game_idx + 1}/{n_games} games done", flush=True)

    return times_by_sq, pick_counts


def _stats(values):
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mean = sum(s) / n
    median = s[n // 2]
    sd = statistics.stdev(s) if n > 1 else 0.0
    p10 = s[max(0, int(n * 0.10))]
    p90 = s[min(n - 1, int(n * 0.90))]
    return dict(n=n, mean=mean, median=median, sd=sd, p10=p10, p90=p90,
                min=s[0], max=s[-1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', default=None,
                    help='Checkpoint path or "det" for DeterministicSolver (default)')
    ap.add_argument('--games', type=int, default=500)
    ap.add_argument('--out', default=None, help='Save raw JSON to this file')
    ap.add_argument('--sort', default='mean',
                    choices=['mean', 'median', 'sd', 'pick_rate'],
                    help='Sort output by this stat')
    ap.add_argument('--min-picks', type=int, default=20,
                    help='Only show squares picked in at least N games')
    args = ap.parse_args()

    agent, label = _load_agent(args.model)
    print(f"Agent: {label}")
    print(f"Running {args.games} games...\n")

    times_by_sq, pick_counts = run_games(agent, n_games=args.games)

    # Build stats table
    rows = []
    for name, times in times_by_sq.items():
        st = _stats(times)
        if st is None:
            continue
        st['name'] = name
        st['pick_rate'] = st['n'] / pick_counts[name]  # completion rate when on board
        rows.append(st)

    # Filter & sort
    rows = [r for r in rows if r['n'] >= args.min_picks]
    rows.sort(key=lambda r: r[args.sort])

    # Print table
    print(f"{'Square':<52}  {'n':>5}  {'pick%':>5}  {'mean':>6}  {'med':>6}  "
          f"{'sd':>5}  {'p10':>6}  {'p90':>6}")
    print('-' * 100)
    for r in rows:
        print(f"{r['name'][:52]:<52}  {r['n']:>5}  {r['pick_rate']*100:>4.0f}%  "
              f"{r['mean']/60:>5.1f}m  {r['median']/60:>5.1f}m  "
              f"{r['sd']/60:>4.1f}m  {r['p10']/60:>5.1f}m  {r['p90']/60:>5.1f}m")

    # Highlight high-SD squares (potentially skewed)
    print(f"\n--- High variance squares (SD > 30 min) ---")
    high_sd = sorted([r for r in rows if r['sd'] > 1800], key=lambda r: -r['sd'])
    for r in high_sd:
        print(f"  {r['name'][:60]:<60}  mean={r['mean']/60:.1f}m  sd={r['sd']/60:.1f}m  "
              f"p10={r['p10']/60:.1f}m  p90={r['p90']/60:.1f}m")

    # Highlight squares that are almost never completed (low pick rate)
    print(f"\n--- Rarely completed (pick rate < 40%) ---")
    rare = sorted([r for r in rows if r['pick_rate'] < 0.40], key=lambda r: r['pick_rate'])
    for r in rare:
        print(f"  {r['name'][:60]:<60}  {r['pick_rate']*100:.0f}% completed  "
              f"mean={r['mean']/60:.1f}m")

    if args.out:
        with open(args.out, 'w') as f:
            json.dump({'stats': rows, 'pick_counts': pick_counts}, f, indent=2)
        print(f"\nRaw data saved to {args.out}")


if __name__ == '__main__':
    main()
