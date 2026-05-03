"""Gymnasium environment wrapping the BingoGame simulation.

Exposes a MaskablePPO-compatible single-agent interface where:
  - The "player" is always agent 0.
  - The "opponent" (agent 1) uses a frozen snapshot of a past policy, updated
    periodically during training (self-play).

Observation space : Box(float32, shape=(obs_size,))
Action space      : Discrete(UNIVERSE_SIZE)  — valid set enforced via masking
"""
import random
import numpy as np
import gymnasium as gym
from gymnasium import spaces

from .board import generate_board, UNIVERSE_SIZE
from .sim   import BingoGame


class BingoEnv(gym.Env):
    metadata = {'render_modes': []}

    def __init__(self, opponent_policy=None, board_seed=None, noise_scale=0.05,
                 max_steps=300):
        super().__init__()
        self._opponent_latest  = opponent_policy
        self._opponent_pool    = []          # past snapshots (max 10)
        self._current_opponent = None        # sampled once per episode
        self._board_seed       = board_seed
        self._noise_scale      = noise_scale
        self._max_steps        = max_steps
        self._steps            = 0

        # Temporary game to get obs size
        _tmp_board = generate_board(seed=0)
        _tmp_game  = BingoGame(_tmp_board)
        _obs_size  = _tmp_game.obs_size

        self.observation_space = spaces.Box(
            low=-2.0, high=2.0, shape=(_obs_size,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(UNIVERSE_SIZE)

        self.game: BingoGame = None
        self._ep_rng = random.Random()

    # ── Gymnasium API ──────────────────────────────────────────────────────────
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if seed is not None:
            self._ep_rng = random.Random(seed)

        board_seed = self._board_seed if self._board_seed is not None else self._ep_rng.randint(0, 2**31)
        board      = generate_board(seed=board_seed)
        self.game  = BingoGame(board, rng=random.Random(board_seed + 1))

        self._steps            = 0
        self._current_opponent = self._sample_opponent()
        obs  = self.game.get_obs(0)
        info = {'action_mask': self.game.get_action_mask(0)}
        return obs, info

    def step(self, action: int):
        assert self.game is not None, "call reset() first"

        self._steps += 1

        # Player 0 acts
        reward, done, info = self.game.step(0, int(action))

        # Opponent acts (runs until its time catches up to player 0, or until done)
        if not done:
            done = self._run_opponent()

        # Episode timeout (truncation, not true game end)
        truncated_flag = False
        if not done and self._steps >= self._max_steps:
            done = True
            truncated_flag = True
            # Assign result based on who has more marks
            my_c  = sum(self.game.agents[0].marks)
            opp_c = sum(self.game.agents[1].marks)
            if my_c > opp_c:
                reward += 0.5
            elif opp_c > my_c:
                reward -= 0.5
            else:
                # Time tiebreak — lower game time wins
                t0 = self.game.agents[0].time
                t1 = self.game.agents[1].time
                reward += 0.3 if t0 <= t1 else -0.3

        obs = self.game.get_obs(0)
        if done:
            # Terminal reward from winner
            if self.game.winner == 0:
                reward = max(reward, 1.0)
            elif self.game.winner == 1:
                reward = min(reward, -1.0)

        mask = self.game.get_action_mask(0) if not done else np.ones(UNIVERSE_SIZE, dtype=bool)
        info['action_mask'] = mask
        info['winner']      = self.game.winner

        return obs, float(reward), done, truncated_flag, info

    def action_masks(self):
        """SB3-contrib MaskablePPO hook."""
        if self.game is None:
            return np.ones(UNIVERSE_SIZE, dtype=bool)
        return self.game.get_action_mask(0)

    def set_opponent(self, policy):
        """Add policy to pool and set as latest opponent."""
        self._opponent_latest = policy
        self._opponent_pool.append(policy)
        if len(self._opponent_pool) > 10:
            self._opponent_pool.pop(0)

    def _sample_opponent(self):
        """Sample an opponent policy for the current episode (70/20/10 mix)."""
        r = self._ep_rng.random()
        if r < 0.70 and self._opponent_latest is not None:
            return self._opponent_latest
        if r < 0.90 and self._opponent_pool:
            return self._ep_rng.choice(self._opponent_pool)
        return None  # pure random

    # ── Opponent loop ─────────────────────────────────────────────────────────
    def _run_opponent(self) -> bool:
        """Let opponent (agent 1) act until its time >= player 0's time."""
        p0_time = self.game.agents[0].time
        for _ in range(50):  # safety limit per step
            if self.game.done:
                return True
            p1_time = self.game.agents[1].time
            if p1_time >= p0_time:
                break
            # Pick opponent action
            opp_obs  = self.game.get_obs(1)
            opp_mask = self.game.get_action_mask(1)
            action   = self._opponent_action(opp_obs, opp_mask)
            _, done, _ = self.game.step(1, action)
            if done:
                return True
        return self.game.done

    def _opponent_action(self, obs, mask):
        if self._current_opponent is not None:
            try:
                action, _ = self._current_opponent.predict(obs, action_masks=mask, deterministic=False)
                return int(action)
            except Exception:
                pass
        # Fallback: random valid action
        valid = np.where(mask)[0]
        return int(np.random.choice(valid)) if len(valid) > 0 else 0
