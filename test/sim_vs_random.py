"""
Simulate trained model vs random agent and report win rate.
Runs for ~5 minutes worth of wall-clock time.

Usage:
    python -m test.sim_vs_random
    python -m test.sim_vs_random --model jack/rl/checkpoints/bingo_agent_final.zip
    python -m test.sim_vs_random --minutes 5
"""
import argparse
import os
import random
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from jack.rl.board import generate_board, UNIVERSE_SIZE
from jack.rl.sim   import BingoGame


def _load_model(path):
    from sb3_contrib import MaskablePPO
    from jack.rl.board import generate_board
    from jack.rl.sim   import BingoGame

    if not os.path.exists(path) and not os.path.exists(path + '.zip'):
        print(f"[!] Model not found at {path}")
        sys.exit(1)

    # Check obs size compatibility before loading into sim
    expected = BingoGame(generate_board(seed=0)).obs_size
    try:
        model = MaskablePPO.load(path)
    except Exception as e:
        print(f"[!] Failed to load model: {e}")
        sys.exit(1)

    saved_obs = model.observation_space.shape[0]
    if saved_obs != expected:
        print(f"[!] Obs space mismatch: model has {saved_obs} features, "
              f"current code expects {expected}.")
        print(f"    The saved checkpoint is stale — wait for the new training run to finish.")
        sys.exit(1)

    print(f"[+] Loaded model: {path}  (obs={saved_obs})")
    return model


def _random_action(mask: np.ndarray) -> int:
    valid = np.where(mask)[0]
    return int(np.random.choice(valid))


def run_game(model, seed: int, model_plays_as: int = 0) -> dict:
    """
    Run one complete game. model_plays_as=0 means model is agent 0.
    Returns dict with winner (0=model, 1=random), marks, time.
    """
    board = generate_board(seed=seed)
    game  = BingoGame(board, rng=random.Random(seed + 1))

    for _ in range(500):  # hard cap
        if game.done:
            break

        for agent_id in range(2):
            if game.done:
                break

            obs  = game.get_obs(agent_id)
            mask = game.get_action_mask(agent_id)

            if not mask.any():
                break

            if agent_id == model_plays_as:
                action, _ = model.predict(obs, action_masks=mask, deterministic=True)
                action = int(action)
            else:
                action = _random_action(mask)

            game.step(agent_id, action)

    marks = [sum(a.marks) for a in game.agents]
    winner = game.winner
    # Map winner back to model/random labels
    if winner == model_plays_as:
        result = 'model'
    elif winner == 1 - model_plays_as:
        result = 'random'
    else:
        result = 'draw'

    return {
        'winner':       result,
        'model_marks':  marks[model_plays_as],
        'random_marks': marks[1 - model_plays_as],
        'model_time':   game.agents[model_plays_as].time,
        'random_time':  game.agents[1 - model_plays_as].time,
    }


def simulate(model_path: str, minutes: float = 5.0):
    model    = _load_model(model_path)
    deadline = time.time() + minutes * 60

    results   = []
    game_seed = random.randint(0, 2**31)

    print(f"\nRunning model vs random  (up to {minutes:.0f} min)...\n")
    print(f"{'Game':>5}  {'Result':>6}  {'Model':>5}  {'Random':>6}  {'WinRate':>8}  {'ModelTime':>10}")
    print("-" * 60)

    while time.time() < deadline:
        # Alternate sides each game so model_plays_as doesn't bias results
        model_side = len(results) % 2
        r = run_game(model, seed=game_seed, model_plays_as=model_side)
        results.append(r)
        game_seed += 1

        n      = len(results)
        wins   = sum(1 for x in results if x['winner'] == 'model')
        draws  = sum(1 for x in results if x['winner'] == 'draw')
        wr     = wins / n
        mt     = r['model_time'] / 60

        print(
            f"{n:>5}  {r['winner']:>6}  {r['model_marks']:>5}  "
            f"{r['random_marks']:>6}  {wr:>7.1%}  {mt:>8.1f}m"
        )

    # ── Summary ───────────────────────────────────────────────────────────────
    n      = len(results)
    wins   = sum(1 for x in results if x['winner'] == 'model')
    losses = sum(1 for x in results if x['winner'] == 'random')
    draws  = sum(1 for x in results if x['winner'] == 'draw')

    avg_model_marks  = np.mean([x['model_marks']  for x in results])
    avg_random_marks = np.mean([x['random_marks'] for x in results])
    avg_model_time   = np.mean([x['model_time']   for x in results]) / 60

    print("\n" + "=" * 60)
    print(f"  Games played : {n}")
    print(f"  Model wins   : {wins}  ({wins/n:.1%})")
    print(f"  Random wins  : {losses}  ({losses/n:.1%})")
    print(f"  Draws        : {draws}  ({draws/n:.1%})")
    print(f"  Avg marks    : model {avg_model_marks:.1f}  /  random {avg_random_marks:.1f}")
    print(f"  Avg game time: {avg_model_time:.1f} min  (model side)")
    print("=" * 60)

    return wins / n


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model',   default='jack/rl/checkpoints/bingo_agent_final.zip')
    parser.add_argument('--minutes', type=float, default=5.0)
    args = parser.parse_args()
    simulate(args.model, args.minutes)
