"""
Pit two trained checkpoints against each other.

Usage:
    python -m test.sim_vs_model --model-a jack/rl/checkpoints/ckpt_001000000.zip \
                                --model-b jack/rl/checkpoints/ckpt_004100008.zip
    python -m test.sim_vs_model --model-a ... --model-b ... --minutes 5
    python -m test.sim_vs_model --model-a ... --model-b ... --games 200
    python -m test.sim_vs_model --model-a ... --model-b ... --show-losses 3

Games alternate sides each round to remove positional bias.
"""
import argparse
import os
import random
import sys
import time
from collections import Counter

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from jack.rl.env import BingoEnv
from jack.rl.constants import BINGO_LINES

DET_SENTINEL = 'det'


def _load_model(path, label):
    """Load an RL checkpoint or return a DeterministicSolver for path=='det'."""
    if path == DET_SENTINEL:
        from jack.solver.det_solver import DeterministicSolver
        solver = DeterministicSolver()
        print(f"[+] {label}: DeterministicSolver (TSP-based, no ML)")
        return solver

    from sb3_contrib import MaskablePPO
    from jack.rl.train import BingoExtractor  # noqa: F401

    if not os.path.exists(path) and not os.path.exists(path + '.zip'):
        print(f"[!] {label}: model not found at {path}")
        sys.exit(1)

    env = BingoEnv()
    expected_obs = env.observation_space.shape[0]
    expected_act = env.action_space.n
    try:
        model = MaskablePPO.load(path)
    except Exception as e:
        print(f"[!] {label}: failed to load — {e}")
        sys.exit(1)

    saved_obs = model.observation_space.shape[0]
    saved_act = model.action_space.n
    if saved_obs != expected_obs or saved_act != expected_act:
        print(f"[!] {label}: checkpoint mismatch "
              f"(model obs={saved_obs} act={saved_act}, "
              f"expected obs={expected_obs} act={expected_act})")
        sys.exit(1)

    print(f"[+] {label}: {path}  (obs={saved_obs}, act={saved_act})")
    return model


def _act(model, env: BingoEnv, obs) -> int:
    """Call model regardless of whether it's an RL model or DeterministicSolver."""
    if hasattr(model, 'act'):
        mask = env.action_masks()
        return int(model.act(env.game, 0, mask))
    mask = env.action_masks()
    action, _ = model.predict(obs, action_masks=mask, deterministic=True)
    return int(action)


def _win_reason(winner_id: int, env: BingoEnv, truncated: bool) -> str:
    if truncated:
        return 'truncated'
    marks = env.game.agents[winner_id].marks
    if any(all(marks[i] for i in line) for line in BINGO_LINES):
        return 'bingo'
    if sum(marks) >= 13:
        return 'majority'
    return 'exhausted'


def run_game(model_main, model_opp, seed: int) -> dict:
    """
    Run one game with model_main as player 0, model_opp as player 1.
    model_opp is passed as opponent_policy so BingoEnv drives it internally.
    Both models predict deterministically.
    """
    # Wrap model_opp so the env drives it correctly regardless of type.
    # DeterministicSolver exposes .act(game, agent_id, mask); RL models use .predict().
    # The env checks for .act() first, so we just pass the solver through directly.
    # For RL models we force deterministic=True.
    class _DetOpp:
        def __init__(self, m): self._m = m
        def act(self, game, agent_id, mask):
            return self._m.act(game, agent_id, mask)
        def predict(self, obs, action_masks=None, deterministic=False):
            return self._m.predict(obs, action_masks=action_masks, deterministic=True)

    # If the opponent is a DeterministicSolver, pass it directly (env handles .act())
    opp_wrapper = model_opp if hasattr(model_opp, 'act') else _DetOpp(model_opp)

    env = BingoEnv(opponent_policy=opp_wrapper, board_seed=seed)
    obs, _ = env.reset(seed=seed)

    sq_text = [sq.text for sq in env.game.board]
    main_events = []
    opp_events  = []

    done  = False
    steps = 0
    while not done:
        prev_m = list(env.game.agents[0].marks)
        prev_o = list(env.game.agents[1].marks)

        action = _act(model_main, env, obs)
        obs, _, terminated, truncated, info = env.step(action)
        done  = terminated or truncated
        steps += 1

        cur_m = env.game.agents[0].marks
        cur_o = env.game.agents[1].marks
        t_m   = env.game.agents[0].time / 60
        t_o   = env.game.agents[1].time / 60

        for i in range(25):
            if cur_m[i] and not prev_m[i]:
                main_events.append((sq_text[i], t_m))
            if cur_o[i] and not prev_o[i]:
                opp_events.append((sq_text[i], t_o))

    w = info.get('winner')
    truncated_flag = (w is None)
    if w is None:
        m0 = sum(env.game.agents[0].marks)
        m1 = sum(env.game.agents[1].marks)
        if m0 > m1:   w = 0
        elif m1 > m0: w = 1
        else:
            w = 0 if env.game.agents[0].time <= env.game.agents[1].time else 1

    reason = _win_reason(w, env, truncated_flag)

    return {
        'main_won':   w == 0,
        'win_reason': reason,
        'main_marks': sum(env.game.agents[0].marks),
        'opp_marks':  sum(env.game.agents[1].marks),
        'main_time':  env.game.agents[0].time,
        'opp_time':   env.game.agents[1].time,
        'truncated':  truncated_flag,
        'steps':      steps,
        'main_events': main_events,
        'opp_events':  opp_events,
        'seed':        seed,
    }


def _print_game_detail(r: dict, game_num: int, label_a: str, label_b: str,
                       a_is_main: bool):
    a_won  = r['main_won'] if a_is_main else not r['main_won']
    print(f"\n--- Game {game_num}: {label_a} {'WIN' if a_won else 'LOSS'} "
          f"({r['win_reason']}, "
          f"{label_a} {r['main_marks'] if a_is_main else r['opp_marks']} / "
          f"{label_b} {r['opp_marks'] if a_is_main else r['main_marks']}, "
          f"{r['main_time']/60:.1f} min) ---")

    a_evts = r['main_events'] if a_is_main else r['opp_events']
    b_evts = r['opp_events']  if a_is_main else r['main_events']

    if a_evts:
        print(f"  {label_a} squares ({len(a_evts)}):")
        for name, t in a_evts:
            print(f"    {t:6.1f}m  {name}")
    if b_evts:
        print(f"  {label_b} squares ({len(b_evts)}):")
        for name, t in b_evts:
            print(f"    {t:6.1f}m  {name}")


def simulate(path_a: str, path_b: str, label_a: str, label_b: str,
             minutes: float = 5.0, max_games: int = None,
             show_losses: int = 0):
    model_a = _load_model(path_a, label_a)
    model_b = _load_model(path_b, label_b)
    deadline = time.time() + minutes * 60

    # Track from A's perspective
    a_wins = 0
    b_wins = 0
    truncated_total = 0
    win_reasons = Counter()
    loss_reasons = Counter()
    all_results  = []   # (game_num, r, a_is_main)
    loss_samples = []
    game_seed = random.randint(0, 2**31)
    game_num  = 0

    print(f"\n{label_a}  vs  {label_b}")
    print(f"Running up to {minutes:.0f} min"
          + (f", {max_games} games" if max_games else "") + " (sides alternate each game)\n")

    hdr = (f"{'#':>5}  {'Winner':>{max(len(label_a), len(label_b))+1}}  "
           f"{'A':>3}  {'B':>3}  {'Reason':>10}  {'A WR':>7}  {'Time':>7}  {'Steps':>5}")
    print(hdr)
    print("-" * len(hdr))

    while time.time() < deadline and (max_games is None or game_num < max_games):
        # Alternate who plays as main (p0)
        a_is_main = (game_num % 2 == 0)
        main_model, opp_model = (model_a, model_b) if a_is_main else (model_b, model_a)

        r = run_game(main_model, opp_model, seed=game_seed)
        game_num  += 1
        game_seed += 1

        a_won = r['main_won'] if a_is_main else not r['main_won']
        if a_won:
            a_wins += 1
            win_reasons[r['win_reason']] += 1
        else:
            b_wins += 1
            loss_reasons[r['win_reason']] += 1

        if r['truncated']:
            truncated_total += 1

        all_results.append((game_num, r, a_is_main))
        if not a_won and len(loss_samples) < max(show_losses, 5):
            loss_samples.append((game_num, r, a_is_main))

        n      = a_wins + b_wins
        wr     = a_wins / n
        a_marks = r['main_marks'] if a_is_main else r['opp_marks']
        b_marks = r['opp_marks']  if a_is_main else r['main_marks']
        winner_label = label_a if a_won else label_b
        w = max(len(label_a), len(label_b)) + 1

        print(f"{game_num:>5}  {winner_label:>{w}}  {a_marks:>3}  {b_marks:>3}  "
              f"{r['win_reason']:>10}  {wr:>6.1%}  {r['main_time']/60:>6.1f}m  {r['steps']:>5}")

    # ── Summary ───────────────────────────────────────────────────────────────
    n = a_wins + b_wins
    print("\n" + "=" * 65)
    print(f"  Games played  : {n}  ({truncated_total} truncated)")
    print(f"  {label_a} wins : {a_wins}  ({a_wins/n:.1%})")
    print(f"  {label_b} wins : {b_wins}  ({b_wins/n:.1%})")

    avg_marks_a = np.mean([
        r['main_marks'] if a_is_main else r['opp_marks']
        for _, r, a_is_main in all_results
    ])
    avg_marks_b = np.mean([
        r['opp_marks'] if a_is_main else r['main_marks']
        for _, r, a_is_main in all_results
    ])
    avg_steps = np.mean([r['steps'] for _, r, _ in all_results])
    print(f"  Avg marks     : {label_a} {avg_marks_a:.1f}  /  {label_b} {avg_marks_b:.1f}")
    print(f"  Avg steps     : {avg_steps:.0f}")

    if win_reasons:
        print(f"\n  {label_a} win reasons:")
        for reason, cnt in sorted(win_reasons.items(), key=lambda x: -x[1]):
            print(f"    {reason:>12}  {cnt:>4}  ({cnt/a_wins:.0%})")
    if loss_reasons:
        print(f"\n  {label_b} win reasons:")
        for reason, cnt in sorted(loss_reasons.items(), key=lambda x: -x[1]):
            print(f"    {reason:>12}  {cnt:>4}  ({cnt/b_wins:.0%})" if b_wins else f"    {reason}  {cnt}")

    print("=" * 65)

    if show_losses > 0 and loss_samples:
        print(f"\n  Sample {label_a} losses (up to {show_losses}):")
        for game_num, r, a_is_main in loss_samples[:show_losses]:
            _print_game_detail(r, game_num, label_a, label_b, a_is_main)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Pit two checkpoints against each other')
    parser.add_argument('--model-a',    required=True, help='Path to first checkpoint')
    parser.add_argument('--model-b',    required=True, help='Path to second checkpoint')
    parser.add_argument('--label-a',    default=None,  help='Display name for model A')
    parser.add_argument('--label-b',    default=None,  help='Display name for model B')
    parser.add_argument('--minutes',    type=float, default=5.0)
    parser.add_argument('--games',      type=int,   default=None)
    parser.add_argument('--show-losses',type=int,   default=3)
    args = parser.parse_args()

    label_a = args.label_a or os.path.basename(args.model_a).replace('.zip', '')
    label_b = args.label_b or os.path.basename(args.model_b).replace('.zip', '')

    simulate(args.model_a, args.model_b, label_a, label_b,
             args.minutes, args.games, args.show_losses)
