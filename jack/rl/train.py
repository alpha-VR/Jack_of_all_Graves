"""Self-play PPO training for Elden Ring S6 lockout bingo agents.

Usage:
    python -m jack.rl.train [--timesteps 1_000_000] [--save-dir checkpoints]

The agent plays as both players via self-play:
  - A frozen snapshot of the policy acts as opponent.
  - The snapshot is updated every `opponent_update_interval` timesteps.
  - Win-rate is tracked and printed periodically.

Routing is fully learned: the agent picks which location to visit at each
step.  No pre-computed routes are injected.
"""
import argparse
import io
import os
import random
import sys
import time
from collections import deque
from typing import Optional


class _Tee:
    """Writes to both stdout and a log file simultaneously."""
    def __init__(self, path):
        self._file = open(path, 'a', buffering=1, encoding='utf-8')
        self._stdout = sys.stdout
    def write(self, data):
        self._stdout.write(data)
        self._file.write(data)
    def flush(self):
        self._stdout.flush()
        self._file.flush()
    def __enter__(self):
        sys.stdout = self
        return self
    def __exit__(self, *_):
        sys.stdout = self._stdout
        self._file.close()

import numpy as np
from sb3_contrib import MaskablePPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.env_util   import make_vec_env
from stable_baselines3.common.vec_env    import VecEnv

from .env import BingoEnv

DEFAULT_SAVE_DIR = os.path.join(os.path.dirname(__file__), 'checkpoints')


# ── Self-play callback ─────────────────────────────────────────────────────────
class SelfPlayCallback(BaseCallback):
    """Updates opponent with frozen copy of the current policy periodically."""

    def __init__(
        self,
        env: BingoEnv,
        save_dir: str,
        update_interval: int = 50_000,
        eval_episodes:   int = 100,
        verbose:         int = 1,
    ):
        super().__init__(verbose)
        self._env              = env
        self._save_dir         = save_dir
        self._update_interval  = update_interval
        self._eval_episodes    = eval_episodes
        self._last_update      = 0
        self._win_history      = deque(maxlen=200)
        self._snapshot: Optional[MaskablePPO] = None

    def _on_step(self) -> bool:
        if self.num_timesteps - self._last_update >= self._update_interval:
            self._update_opponent()
            self._last_update = self.num_timesteps
        return True

    def _update_opponent(self):
        """Freeze current policy as new opponent and save checkpoint."""
        buf = io.BytesIO()
        self.model.save(buf)
        buf.seek(0)
        self._snapshot = MaskablePPO.load(buf)
        self._env.set_opponent(self._snapshot)

        # Save checkpoint to disk
        ckpt_path = os.path.join(self._save_dir, f'ckpt_{self.num_timesteps:09d}')
        self.model.save(ckpt_path)

        if self.verbose:
            wr = self._quick_win_rate()
            print(f"[{self.num_timesteps:>9,}] Saved {ckpt_path}.zip  |  win-rate vs old: {wr:.1%}")

    def _quick_win_rate(self) -> float:
        """Play `_eval_episodes` games vs frozen snapshot, return win rate."""
        if self._snapshot is None:
            return 0.5
        wins = 0
        eval_env = BingoEnv(opponent_policy=self._snapshot)
        for _ in range(self._eval_episodes):
            obs, info = eval_env.reset()
            done = False
            while not done:
                mask = eval_env.action_masks()
                action, _ = self.model.predict(obs, action_masks=mask, deterministic=False)
                obs, _, terminated, truncated, info = eval_env.step(action)
                done = terminated or truncated
            if info.get('winner') == 0:
                wins += 1
        return wins / self._eval_episodes


# ── Training entry point ───────────────────────────────────────────────────────
def train(
    total_timesteps:          int   = 1_000_000,
    save_dir:                 str   = DEFAULT_SAVE_DIR,
    opponent_update_interval: int   = 100_000,
    n_envs:                   int   = 4,
    learning_rate:            float = 1e-4,
    batch_size:               int   = 512,
    n_epochs:                 int   = 10,
    gamma:                    float = 0.99,
    ent_coef:                 float = 0.05,
    resume_from:              str   = None,
):
    os.makedirs(save_dir, exist_ok=True)

    # Single env for self-play callback evaluation
    eval_env = BingoEnv()

    # Vectorised training envs (opponents start as random)
    def _make():
        return BingoEnv()

    vec_env = make_vec_env(_make, n_envs=n_envs)

    if resume_from and os.path.exists(resume_from):
        print(f"Resuming from {resume_from}")
        model = MaskablePPO.load(resume_from, env=vec_env)
    else:
        model = MaskablePPO(
            policy="MlpPolicy",
            env=vec_env,
            learning_rate=learning_rate,
            n_steps=2048,
            batch_size=batch_size,
            n_epochs=n_epochs,
            gamma=gamma,
            ent_coef=ent_coef,
            verbose=1,
            policy_kwargs=dict(net_arch=[256, 256]),
        )

    callback = SelfPlayCallback(
        env=eval_env,
        save_dir=save_dir,
        update_interval=opponent_update_interval,
        verbose=1,
    )

    print(f"Training for {total_timesteps:,} timesteps  |  {n_envs} parallel envs")
    t0 = time.time()
    model.learn(
        total_timesteps=total_timesteps,
        callback=callback,
        reset_num_timesteps=resume_from is None,
    )
    elapsed = time.time() - t0
    print(f"Training complete in {elapsed/60:.1f} min")

    save_path = os.path.join(save_dir, 'bingo_agent_final')
    model.save(save_path)
    print(f"Model saved to {save_path}")
    return model


# ── Quick evaluation helper ────────────────────────────────────────────────────
def evaluate(model_path: str, n_episodes: int = 200, verbose: bool = True):
    """Evaluate a trained model in self-play and print stats."""
    model   = MaskablePPO.load(model_path)
    env     = BingoEnv(opponent_policy=model)
    wins, total_time = 0, []

    for ep in range(n_episodes):
        obs, info = env.reset()
        done = False
        while not done:
            mask   = env.action_masks()
            action, _ = model.predict(obs, action_masks=mask, deterministic=True)
            obs, _, terminated, truncated, info = env.step(action)
            done = terminated or truncated
        if info.get('winner') == 0:
            wins += 1
        total_time.append(env.game.agents[0].time)

    wr = wins / n_episodes
    avg_time = np.mean(total_time) / 60
    if verbose:
        print(f"Win rate: {wr:.1%}  |  Avg game time: {avg_time:.1f} min  ({n_episodes} episodes)")
    return wr, avg_time


# ── CLI ────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Train bingo RL agent')
    parser.add_argument('--timesteps',  type=int,   default=1_000_000)
    parser.add_argument('--save-dir',   type=str,   default=DEFAULT_SAVE_DIR)
    parser.add_argument('--n-envs',     type=int,   default=4)
    parser.add_argument('--lr',         type=float, default=3e-4)
    parser.add_argument('--resume',     type=str,   default=None)
    parser.add_argument('--log',        type=str,   default=None,
                        help='Path to log file (appends; also prints to terminal)')
    parser.add_argument('--eval',       type=str,   default=None,
                        help='Path to saved model to evaluate instead of training')
    args = parser.parse_args()

    def _run():
        if args.eval:
            evaluate(args.eval)
        else:
            train(
                total_timesteps=args.timesteps,
                save_dir=args.save_dir,
                n_envs=args.n_envs,
                learning_rate=args.lr,
                resume_from=args.resume,
            )

    if args.log:
        os.makedirs(os.path.dirname(os.path.abspath(args.log)), exist_ok=True)
        with _Tee(args.log):
            _run()
    else:
        _run()
