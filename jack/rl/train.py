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
import torch
import torch.nn as nn
from sb3_contrib import MaskablePPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.env_util   import make_vec_env
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
from stable_baselines3.common.vec_env    import VecEnv, VecNormalize

from .env import BingoEnv
from .sim import SELF_DIM, OPP_DIM, BOARD_DIM


# ── Three-stream feature extractor ─────────────────────────────────────────────
class BingoExtractor(BaseFeaturesExtractor):
    """Separate encoder streams for self-state, opponent, and board synergy.

    Processes each perspective independently before merging, so the network
    can specialize: self_net learns routing efficiency, opp_net learns
    opponent threat assessment, board_net learns square synergy.
    """

    def __init__(self, observation_space, features_dim: int = 256):
        super().__init__(observation_space, features_dim)
        self.self_net = nn.Sequential(
            nn.Linear(SELF_DIM, 128), nn.ReLU(),
            nn.Linear(128, 128),      nn.ReLU(),
        )
        self.opp_net = nn.Sequential(
            nn.Linear(OPP_DIM, 64),  nn.ReLU(),
            nn.Linear(64, 64),        nn.ReLU(),
        )
        self.board_net = nn.Sequential(
            nn.Linear(BOARD_DIM, 128), nn.ReLU(),
            nn.Linear(128, 128),       nn.ReLU(),
        )
        self.merge = nn.Sequential(
            nn.Linear(128 + 64 + 128, features_dim), nn.ReLU(),
        )

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        s = self.self_net(obs[:, :SELF_DIM])
        o = self.opp_net(obs[:, SELF_DIM:SELF_DIM + OPP_DIM])
        b = self.board_net(obs[:, SELF_DIM + OPP_DIM:])
        return self.merge(torch.cat([s, o, b], dim=1))

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
        solver=None,
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
        self._opponent_pool: list = []          # past frozen snapshots (max 20)
        self._solver           = solver         # DeterministicSolver for eval (optional)

    def _on_step(self) -> bool:
        if self.num_timesteps - self._last_update >= self._update_interval:
            self._update_opponent()
            self._last_update = self.num_timesteps
        return True

    def _update_opponent(self):
        """Freeze current policy as new opponent and save checkpoint."""
        # Measure improvement vs previous snapshot BEFORE freezing the new one
        wr = self._quick_win_rate()

        buf = io.BytesIO()
        self.model.save(buf)
        buf.seek(0)
        # Explicitly load to same device as training model to avoid CPU fallback
        device = next(self.model.policy.parameters()).device
        self._snapshot = MaskablePPO.load(buf, device=device)
        self._opponent_pool.append({'policy': self._snapshot, 'win_rate': wr})
        if len(self._opponent_pool) > 20:
            self._opponent_pool.pop(0)
        self._env.set_opponent(self._snapshot, win_rate=wr)

        # Push new snapshot to all training envs
        if isinstance(self.training_env, VecEnv):
            self.training_env.env_method('set_opponent', self._snapshot, wr)

        # Save checkpoint to disk
        ckpt_path = os.path.join(self._save_dir, f'ckpt_{self.num_timesteps:09d}')
        self.model.save(ckpt_path)

        # Optionally eval vs solver
        solver_wr_str = ""
        if self._solver is not None:
            swr = self._solver_win_rate()
            solver_wr_str = f"  |  vs solver: {swr:.1%}"

        if self.verbose:
            print(f"[{self.num_timesteps:>9,}] Saved {ckpt_path}.zip  |  win-rate vs prev: {wr:.1%}{solver_wr_str}")

    def _quick_win_rate(self) -> float:
        """Play `_eval_episodes` games vs uniformly-sampled past snapshots.

        Uniform (not recency-weighted) sampling across the full pool avoids the
        rock-paper-scissors problem: A beats B, B beats C, C beats A.  Win rate
        here means "I beat X% of all past selves on average," which is robust to
        non-transitive cycles.  Falls back to the latest snapshot when the pool
        is still empty.
        """
        if self._snapshot is None:
            return 0.5
        wins = 0
        eval_env = BingoEnv()
        rng = random.Random()
        pool_policies = [e['policy'] for e in self._opponent_pool] if self._opponent_pool else [self._snapshot]
        for _ in range(self._eval_episodes):
            obs, info = eval_env.reset()
            eval_env._current_opponent = rng.choice(pool_policies)  # uniform across all past selves
            done = False
            while not done:
                mask = eval_env.action_masks()
                action, _ = self.model.predict(obs, action_masks=mask, deterministic=False)
                obs, _, terminated, truncated, info = eval_env.step(action)
                done = terminated or truncated
            w = info.get('winner')
            if w == 0:
                wins += 1
            elif w is None:
                # Truncated: decide by mark count, tiebreak by time
                a0 = eval_env.game.agents[0]
                a1 = eval_env.game.agents[1]
                m0, m1 = sum(a0.marks), sum(a1.marks)
                if m0 > m1:
                    wins += 1
                elif m0 == m1:
                    wins += 0.5
        return wins / self._eval_episodes

    def _solver_win_rate(self) -> float:
        """Play eval_episodes/2 games vs the deterministic solver."""
        wins = 0
        n    = self._eval_episodes // 2
        eval_env = BingoEnv()
        eval_env._current_opponent = self._solver
        rng = random.Random()
        for _ in range(n):
            obs, _ = eval_env.reset()
            eval_env._current_opponent = self._solver
            done = False
            while not done:
                mask = eval_env.action_masks()
                action, _ = self.model.predict(obs, action_masks=mask, deterministic=False)
                obs, _, terminated, truncated, info = eval_env.step(action)
                done = terminated or truncated
            w = info.get('winner')
            if w == 0:
                wins += 1
            elif w is None:
                a0, a1 = eval_env.game.agents[0], eval_env.game.agents[1]
                m0, m1 = sum(a0.marks), sum(a1.marks)
                if m0 > m1:   wins += 1
                elif m0 == m1: wins += 0.5
        return wins / n


# ── Entropy schedule callback ──────────────────────────────────────────────────
class EntropyScheduleCallback(BaseCallback):
    """Linearly decays model.ent_coef from initial_ent → final_ent over training."""

    def __init__(self, initial_ent: float = 0.15, final_ent: float = 0.02,
                 total_steps: int = 1_000_000):
        super().__init__()
        self._initial    = initial_ent
        self._final      = final_ent
        self._total      = total_steps

    def _on_step(self) -> bool:
        frac = min(self.num_timesteps / self._total, 1.0)
        self.model.ent_coef = self._final + (1.0 - frac) * (self._initial - self._final)
        return True


# ── Training entry point ───────────────────────────────────────────────────────
def train(
    total_timesteps:          int   = 1_000_000,
    save_dir:                 str   = DEFAULT_SAVE_DIR,
    opponent_update_interval: int   = 100_000,
    n_envs:                   int   = 8,
    learning_rate:            float = 3e-4,
    batch_size:               int   = 256,
    n_epochs:                 int   = 4,
    gamma:                    float = 0.995,
    ent_coef:                 float = 0.10,
    resume_from:              str   = None,
    solver_opp:               float = 0.0,   # fraction of episodes vs solver
):
    os.makedirs(save_dir, exist_ok=True)

    # Load solver if requested
    solver = None
    if solver_opp > 0:
        from jack.solver.det_solver import DeterministicSolver
        solver = DeterministicSolver()
        print(f"[solver] DeterministicSolver enabled as {solver_opp:.0%} of training opponents")

    # Single env for self-play callback evaluation (no normalization needed)
    eval_env = BingoEnv(solver=solver, solver_prob=solver_opp)

    # Vectorised training envs wrapped with reward normalization.
    # norm_obs=False because we manually normalize all obs features in get_obs().
    def _make():
        return BingoEnv(solver=solver, solver_prob=solver_opp)

    vec_env = VecNormalize(
        make_vec_env(_make, n_envs=n_envs),
        norm_obs=False,
        norm_reward=True,
        clip_reward=10.0,
    )

    if resume_from and os.path.exists(resume_from):
        print(f"Resuming from {resume_from}")
        model = MaskablePPO.load(resume_from, env=vec_env)
    else:
        model = MaskablePPO(
            policy="MlpPolicy",
            env=vec_env,
            learning_rate=learning_rate,
            n_steps=1024,
            batch_size=batch_size,
            n_epochs=n_epochs,
            gamma=gamma,
            ent_coef=ent_coef,
            verbose=1,
            policy_kwargs=dict(
                features_extractor_class=BingoExtractor,
                features_extractor_kwargs=dict(features_dim=256),
                net_arch=dict(pi=[256], vf=[256]),
            ),
        )

    callbacks = [
        SelfPlayCallback(
            env=eval_env,
            save_dir=save_dir,
            update_interval=opponent_update_interval,
            solver=solver,
            verbose=1,
        ),
        EntropyScheduleCallback(
            initial_ent=0.15 if not resume_from else 0.05,
            final_ent=0.02,
            total_steps=total_timesteps,
        ),
    ]

    print(f"Training for {total_timesteps:,} timesteps  |  {n_envs} parallel envs")
    t0 = time.time()
    model.learn(
        total_timesteps=total_timesteps,
        callback=callbacks,
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
    parser.add_argument('--timesteps',   type=int,   default=1_000_000)
    parser.add_argument('--save-dir',    type=str,   default=DEFAULT_SAVE_DIR)
    parser.add_argument('--n-envs',      type=int,   default=8)
    parser.add_argument('--lr',          type=float, default=3e-4)
    parser.add_argument('--resume',      type=str,   default=None)
    parser.add_argument('--solver-opp',  type=float, default=0.0,
                        help='Fraction of training episodes to face the deterministic solver (e.g. 0.2)')
    parser.add_argument('--log',         type=str,   default=None,
                        help='Path to log file (appends; also prints to terminal)')
    parser.add_argument('--eval',        type=str,   default=None,
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
                solver_opp=args.solver_opp,
            )

    if args.log:
        os.makedirs(os.path.dirname(os.path.abspath(args.log)), exist_ok=True)
        with _Tee(args.log):
            _run()
    else:
        _run()
