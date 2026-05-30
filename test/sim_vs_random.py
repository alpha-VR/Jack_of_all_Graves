"""
Simulate trained model vs random agent with detailed match reporting.

Usage:
    python -m test.sim_vs_random
    python -m test.sim_vs_random --model jack/rl/models/bingo_agent.zip
    python -m test.sim_vs_random --minutes 5
    python -m test.sim_vs_random --games 100
    python -m test.sim_vs_random --verbose          # full play-by-play every game
    python -m test.sim_vs_random --show-losses 5    # detail on N sample losses at end
"""
import argparse
import os
import random
import sys
import time
from collections import Counter, defaultdict

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from jack.rl.env import BingoEnv
from jack.rl.constants import BINGO_LINES


def _load_model(path):
    if path == 'det':
        from jack.solver.det_solver import DeterministicSolver
        print("[+] Loaded model: DeterministicSolver (TSP-based, no ML)")
        return DeterministicSolver()

    from sb3_contrib import MaskablePPO
    from jack.rl.train import BingoExtractor  # noqa: F401

    if not os.path.exists(path) and not os.path.exists(path + '.zip'):
        print(f"[!] Model not found at {path}")
        sys.exit(1)

    env = BingoEnv()
    expected_obs = env.observation_space.shape[0]
    expected_act = env.action_space.n
    try:
        model = MaskablePPO.load(path)
    except Exception as e:
        print(f"[!] Failed to load model: {e}")
        sys.exit(1)

    saved_obs = model.observation_space.shape[0]
    saved_act = model.action_space.n
    if saved_obs != expected_obs or saved_act != expected_act:
        print(f"[!] Checkpoint mismatch: model obs={saved_obs} act={saved_act}, "
              f"current code expects obs={expected_obs} act={expected_act}.")
        print(f"    Start a new training run and wait for the first checkpoint.")
        sys.exit(1)

    print(f"[+] Loaded model: {path}  (obs={saved_obs}, act={saved_act})")
    return model


def _win_reason(winner_id: int, env: BingoEnv, truncated: bool) -> str:
    if truncated:
        return 'truncated'
    marks = env.game.agents[winner_id].marks
    if any(all(marks[i] for i in line) for line in BINGO_LINES):
        return 'bingo'
    if sum(marks) >= 13:
        return 'majority'
    return 'exhausted'


def run_game(model, seed: int) -> dict:
    """Run one game; return detailed result dict."""
    env = BingoEnv(opponent_policy=None, board_seed=seed)
    obs, _ = env.reset(seed=seed)
    board = env.game.board          # list of Square objects, indexed 0-24
    sq_text = [sq.text for sq in board]

    model_events  = []   # (sq_name, time_min) in completion order
    random_events = []

    done = False
    steps = 0
    while not done:
        prev_m = list(env.game.agents[0].marks)
        prev_r = list(env.game.agents[1].marks)

        mask = env.action_masks()
        if hasattr(model, 'act'):
            action = model.act(env.game, 0, mask)
        else:
            action, _ = model.predict(obs, action_masks=mask, deterministic=True)
        obs, _, terminated, truncated, info = env.step(action)
        done = terminated or truncated
        steps += 1

        cur_m = env.game.agents[0].marks
        cur_r = env.game.agents[1].marks
        t_m   = env.game.agents[0].time / 60
        t_r   = env.game.agents[1].time / 60

        for i in range(25):
            if cur_m[i] and not prev_m[i]:
                model_events.append((sq_text[i], t_m))
            if cur_r[i] and not prev_r[i]:
                random_events.append((sq_text[i], t_r))

    # Resolve truncation
    w = info.get('winner')
    truncated_flag = (w is None)
    if w is None:
        m0 = sum(env.game.agents[0].marks)
        m1 = sum(env.game.agents[1].marks)
        if m0 > m1:
            w = 0
        elif m1 > m0:
            w = 1
        else:
            w = 0 if env.game.agents[0].time <= env.game.agents[1].time else 1

    reason = _win_reason(w, env, truncated_flag)

    # Squares neither player completed — note any with unsatisfied prereqs
    incomplete = []
    a0 = env.game.agents[0]
    for sq in board:
        if sq.is_passive:
            continue
        if env.game.agents[0].marks[sq.idx] or env.game.agents[1].marks[sq.idx]:
            continue
        prereq_ok = env.game._prereqs_satisfied(sq, a0)
        incomplete.append({
            'name':      sq.text,
            'prereqs':   sq.prereqs or [],
            'prereq_ok': prereq_ok,
        })

    return {
        'winner':        'model' if w == 0 else 'random',
        'win_reason':    reason,
        'model_marks':   sum(env.game.agents[0].marks),
        'random_marks':  sum(env.game.agents[1].marks),
        'model_time':    env.game.agents[0].time,
        'random_time':   env.game.agents[1].time,
        'truncated':     truncated_flag,
        'steps':         steps,
        'model_events':  model_events,
        'random_events': random_events,
        'incomplete':    incomplete,
        'seed':          seed,
    }


def _print_game_detail(r: dict, game_num: int):
    won   = r['winner'] == 'model'
    label = 'WIN' if won else 'LOSS'
    print(f"\n--- Game {game_num}: {label} ({r['win_reason']}, "
          f"model {r['model_marks']} / random {r['random_marks']}, "
          f"{r['model_time']/60:.1f} min) ---")

    if r['model_events']:
        print(f"  Model squares ({len(r['model_events'])}):")
        for name, t in r['model_events']:
            print(f"    {t:6.1f}m  {name}")
    else:
        print("  Model squares: none")

    if r['random_events']:
        print(f"  Random squares ({len(r['random_events'])}):")
        for name, t in r['random_events']:
            print(f"    {t:6.1f}m  {name}")
    else:
        print("  Random squares: none")

    locked   = [s for s in r['incomplete'] if not s['prereq_ok'] and s['prereqs']]
    unlocked = [s for s in r['incomplete'] if s['prereq_ok'] or not s['prereqs']]
    if unlocked:
        print(f"  Incomplete / contested ({len(unlocked)}):")
        for s in unlocked:
            print(f"    {s['name']}")
    if locked:
        print(f"  Prereqs unmet at game end ({len(locked)}) — could be satisfied if game continued:")
        for s in locked:
            print(f"    {s['name']}  [needs: {', '.join(s['prereqs'])}]")


def simulate(model_path: str, minutes: float = 5.0, max_games: int = None,
             verbose: bool = False, show_losses: int = 0):
    model    = _load_model(model_path)
    deadline = time.time() + minutes * 60

    results   = []
    loss_samples = []
    game_seed = random.randint(0, 2**31)

    print(f"\nRunning model vs random  (up to {minutes:.0f} min"
          + (f", {max_games} games" if max_games else "") + ")...\n")
    hdr = f"{'#':>5}  {'Result':>6}  {'M':>3}  {'R':>3}  {'Reason':>10}  {'WR':>7}  {'Time':>7}  {'Steps':>5}"
    print(hdr)
    print("-" * len(hdr))

    while time.time() < deadline and (max_games is None or len(results) < max_games):
        r = run_game(model, seed=game_seed)
        results.append(r)
        if r['winner'] == 'random' and len(loss_samples) < max(show_losses, 10):
            loss_samples.append((len(results), r))
        game_seed += 1

        n   = len(results)
        wr  = sum(1 for x in results if x['winner'] == 'model') / n
        mt  = r['model_time'] / 60

        print(f"{n:>5}  {r['winner']:>6}  {r['model_marks']:>3}  {r['random_marks']:>3}  "
              f"{r['win_reason']:>10}  {wr:>6.1%}  {mt:>6.1f}m  {r['steps']:>5}")

        if verbose:
            _print_game_detail(r, n)

    # ── Summary ───────────────────────────────────────────────────────────────
    n      = len(results)
    wins   = sum(1 for x in results if x['winner'] == 'model')
    losses = n - wins

    reason_counts = Counter(r['win_reason'] for r in results)
    win_reasons   = Counter(r['win_reason'] for r in results if r['winner'] == 'model')
    loss_reasons  = Counter(r['win_reason'] for r in results if r['winner'] == 'random')

    avg_model_marks  = np.mean([x['model_marks']  for x in results])
    avg_random_marks = np.mean([x['random_marks'] for x in results])
    avg_model_time   = np.mean([x['model_time']   for x in results]) / 60
    avg_steps        = np.mean([x['steps']        for x in results])
    truncated        = sum(1 for x in results if x['truncated'])

    # Aggregate square stats
    model_sq_wins  = Counter()
    random_sq_wins = Counter()
    locked_counts  = Counter()
    for r in results:
        for name, _ in r['model_events']:
            model_sq_wins[name] += 1
        for name, _ in r['random_events']:
            random_sq_wins[name] += 1
        for s in r['incomplete']:
            if not s['prereq_ok'] and s['prereqs']:
                locked_counts[s['name']] += 1

    print("\n" + "=" * 65)
    print(f"  Games played  : {n}  ({truncated} truncated)")
    print(f"  Model wins    : {wins}  ({wins/n:.1%})")
    print(f"  Random wins   : {losses}  ({losses/n:.1%})")
    print(f"  Avg marks     : model {avg_model_marks:.1f}  /  random {avg_random_marks:.1f}")
    print(f"  Avg game time : {avg_model_time:.1f} min  (model side)")
    print(f"  Avg steps     : {avg_steps:.0f}")

    print(f"\n  Win reasons (model wins):")
    for reason, cnt in sorted(win_reasons.items(), key=lambda x: -x[1]):
        print(f"    {reason:>12}  {cnt:>4}  ({cnt/wins:.0%})" if wins else f"    {reason}  {cnt}")
    print(f"\n  Loss reasons (random wins):")
    for reason, cnt in sorted(loss_reasons.items(), key=lambda x: -x[1]):
        print(f"    {reason:>12}  {cnt:>4}  ({cnt/losses:.0%})" if losses else f"    {reason}  {cnt}")

    if locked_counts:
        print(f"\n  Squares with unmet prereqs at game end (top 8):")
        for name, cnt in locked_counts.most_common(8):
            print(f"    {cnt:>4}x  {name}")

    if losses > 0:
        # Squares random wins most often in loss games
        loss_random = Counter()
        for r in results:
            if r['winner'] == 'random':
                for name, _ in r['random_events']:
                    loss_random[name] += 1
        print(f"\n  Squares random completes most in losses (top 8):")
        for name, cnt in loss_random.most_common(8):
            print(f"    {cnt:>4}x  {name}")

    print("=" * 65)

    # Show sample loss details
    if show_losses > 0 and loss_samples:
        print(f"\n  Sample losses (up to {show_losses}):")
        for game_num, r in loss_samples[:show_losses]:
            _print_game_detail(r, game_num)

    return wins / n


def _latest_checkpoint(ckpt_dir: str = 'jack/rl/checkpoints') -> str:
    """Return the most recently written checkpoint in ckpt_dir."""
    import glob
    files = glob.glob(os.path.join(ckpt_dir, 'ckpt_*.zip'))
    if not files:
        return os.path.join(ckpt_dir, 'ckpt_002000000')
    return max(files, key=os.path.getmtime).replace('.zip', '')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model',       default=None,
                        help='Path to checkpoint (default: latest in jack/rl/checkpoints)')
    parser.add_argument('--minutes',     type=float, default=5.0)
    parser.add_argument('--games',       type=int,   default=None,
                        help='Run exactly N games instead of time-based')
    parser.add_argument('--verbose',     action='store_true',
                        help='Print full play-by-play after every game')
    parser.add_argument('--show-losses', type=int,   default=3,
                        help='Print detailed breakdown for N sample losses at end')
    args = parser.parse_args()
    model_path = args.model or _latest_checkpoint()
    print(f"[*] Using checkpoint: {model_path}")
    simulate(model_path, args.minutes, args.games, args.verbose, args.show_losses)
