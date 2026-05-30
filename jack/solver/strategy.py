"""Common strategy interface for both RL and deterministic solvers.

Both solvers receive the full BingoGame object so they can read structured
state.  The RL solver also calls get_obs() internally; the deterministic
solver reads AgentState / board directly.
"""
from abc import ABC, abstractmethod
import numpy as np


class Strategy(ABC):
    @abstractmethod
    def act(self, game, agent_id: int, mask: np.ndarray) -> int:
        """Return a UNIVERSE index to act on."""


class RLStrategy(Strategy):
    """Wraps a stable-baselines3 MaskablePPO model behind the Strategy interface."""

    def __init__(self, model):
        self._model = model

    def act(self, game, agent_id: int, mask: np.ndarray) -> int:
        obs = game.get_obs(agent_id)
        action, _ = self._model.predict(obs, action_masks=mask, deterministic=False)
        return int(action)

    # SB3 callers that use .predict() directly still work (e.g. env self-play pool).
    def predict(self, obs, action_masks=None, deterministic=False):
        return self._model.predict(obs, action_masks=action_masks, deterministic=deterministic)
