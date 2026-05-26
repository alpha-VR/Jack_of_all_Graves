"""Route generation using a trained RL agent.

Given a current board state (squares, marks, build config), runs the agent
deterministically and returns a detailed stop-by-stop route.
"""
import os
import sys
from typing import List, Dict, Optional

from .board import generate_board, UNIVERSE, UNIVERSE_SIZE, _SQUARE_DB, _extract_locations, _extract_count, Square, _loc_key, _ZERO_WEAPON_PATTERNS
from .sim   import BingoGame, AgentState
from .constants import (
    S6_GRACES, ROUNDTABLE, compute_travel_time, compute_kill_time,
    OVERHEAD_BOSS_SEC, OVERHEAD_PICKUP_SEC, OVERHEAD_ROUNDTABLE_SEC,
    OVERHEAD_GRACE_SEC, BINGO_LINES, WEAPON_CLASSES,
)

if getattr(sys, 'frozen', False):
    _DEFAULT_MODEL = os.path.join(sys._MEIPASS, 'jack', 'rl', 'models', 'bingo_agent.zip')
else:
    _DEFAULT_MODEL = os.path.join(os.path.dirname(__file__), 'models', 'bingo_agent.zip')


def _load_model(model_path: Optional[str] = None):
    from sb3_contrib import MaskablePPO
    from .train import BingoExtractor  # noqa: F401 — registers custom policy class for load
    path = model_path or _DEFAULT_MODEL
    exists = os.path.exists(path)
    print(f"[RL] model path: {path}")
    print(f"[RL] file exists: {exists}")
    if not exists and not os.path.exists(path + '.zip'):
        print("[RL] model not found — falling back to random")
        return None
    try:
        model = MaskablePPO.load(path)
        print("[RL] model loaded OK")
        return model
    except Exception as e:
        import traceback
        print(f"[RL] model load FAILED: {e}")
        traceback.print_exc()
        return None


def _squares_from_raw_names(raw_names: List[str]) -> List[Square]:
    """Build Square objects from a list of raw template names (from the JS board)."""
    squares = []
    for i, raw_name in enumerate(raw_names):
        sq_data = _SQUARE_DB.get(raw_name, {})
        sq_type = sq_data.get('type', 'unknown')
        locs    = _extract_locations(raw_name, sq_data) if sq_data else []
        count   = _extract_count(raw_name, sq_data) if sq_data else 1
        is_passive = sq_type in ('passive_runes', 'passive_stat') or not locs

        squares.append(Square(
            idx=i,
            text=raw_name,
            raw_name=raw_name,
            sq_type=sq_type,
            data=sq_data,
            locations=locs,
            count_needed=count,
            is_passive=is_passive,
            requires_zero_weapon=bool(_ZERO_WEAPON_PATTERNS.search(raw_name)),
            prereqs=sq_data.get('prerequisites', []) if sq_data else [],
            runes_on_complete=sq_data.get('runes', 0) if sq_data else 0,
        ))
    return squares


def generate_route(
    raw_names:   List[str],         # 25 raw template names from JS board
    marks:       List[int],          # -1=none, 0=P1, 1=P2  (JS format)
    player:      int        = 0,     # which player is requesting the route (0 or 1)
    build:       Dict       = None,  # {weaponClass, isSomber, primaryStat, weaponLevel}
    model_path:  str        = None,
    max_steps:   int        = 60,
) -> Dict:
    """
    Run the trained agent on the current board state and return a detailed route.

    Returns:
        {
          stops: [{step, type, name, x, y, zone, sq_names, travel_sec, action_sec,
                   cumulative_sec, weapon_level, rune_level, completes}],
          total_sec: int,
          model_used: str,
        }
    """
    import random, numpy as np

    model = _load_model(model_path)
    model_label = os.path.basename(model_path or _DEFAULT_MODEL)

    squares    = _squares_from_raw_names(raw_names)
    sq_by_name = {sq.raw_name: sq for sq in squares}
    game       = BingoGame(squares, rng=random.Random(42))

    # Pre-apply existing marks
    my_player  = player
    opp_player = 1 - player
    for sq_idx, mark in enumerate(marks):
        if mark == my_player:
            game.agents[0].marks[sq_idx] = True
        elif mark == opp_player:
            game.agents[1].marks[sq_idx] = True

    # Apply build config
    if build:
        a = game.agents[0]
        a.weapon_class  = build.get('weaponClass', a.weapon_class)
        a.is_somber     = build.get('isSomber',    a.is_somber)
        a.primary_stat  = build.get('primaryStat', a.primary_stat)
        a.weapon_level  = build.get('weaponLevel', a.weapon_level)
        if a.weapon_level > 0:
            a.has_upgraded = True

    # Run agent deterministically
    stops     = []
    cum_sec   = 0.0
    agent     = game.agents[0]
    prev_time = agent.time

    for step in range(max_steps):
        if game.done:
            break

        obs  = game.get_obs(0)
        mask = game.get_action_mask(0)

        if not mask.any():
            break

        # Pick action: model if available, else random valid
        if model is not None:
            try:
                action, _ = model.predict(obs, action_masks=mask, deterministic=True)
                action = int(action)
            except Exception:
                # Model action space doesn't match current universe (stale checkpoint)
                valid  = np.where(mask)[0]
                action = int(np.random.choice(valid))
                model  = None  # stop trying for remaining steps
        else:
            valid  = np.where(mask)[0]
            action = int(np.random.choice(valid))

        entry     = UNIVERSE[action]
        loc       = entry['loc']
        prev_wl   = agent.weapon_level
        prev_rl   = agent.rune_level
        prev_pos  = dict(agent.pos)
        prev_warp = list(agent.warp_pool)

        reward, done, info = game.step(0, action)

        travel_sec = compute_travel_time(prev_pos, loc, prev_warp)
        action_sec = max(0, agent.time - prev_time - travel_sec)
        cum_sec    = agent.time
        prev_time  = agent.time

        stop = {
            'step':         step + 1,
            'type':         entry['type'],
            'name':         loc.get('name', entry['key']),
            'x':            loc.get('x'),
            'y':            loc.get('y'),
            'zone':         loc.get('zone', 'unknown'),
            'travel_sec':   int(travel_sec),
            'action_sec':   int(action_sec),
            'cumulative_sec': int(cum_sec),
            'weapon_level': agent.weapon_level,
            'rune_level':   agent.rune_level,
            'completes':    [squares[i].text for i in info.get('sq_completed', [])],
        }

        if entry['type'] == 'stone':
            stop['stone_tier']  = entry['stone_tier']
            stop['stone_somber']= entry['stone_somber']
        if entry['type'] == 'objective':
            sq_names = [n for n in entry['sq_names']
                        if n in sq_by_name and not agent.marks[sq_by_name[n].idx]]
            stop['sq_names'] = sq_names
            progress = {n: len(agent.sq_progress.get(sq_by_name[n].idx, set()))
                        for n in sq_names if sq_by_name[n].count_needed > 1}
            if progress:
                stop['sq_progress'] = progress
        if entry['type'] == 'prereq':
            prereq_key = entry.get('prereq_key', '')
            stop['prereq_key'] = prereq_key
            stop['unlocks'] = [sq.text for sq in squares
                               if not agent.marks[sq.idx]
                               and any(prereq_key in (loc.get('prerequisites') or [])
                                       for loc in sq.locations)]
            stop['sq_names'] = []
        if entry['type'] == 'grace':
            stop['grace_id'] = entry.get('grace_id')

        # Annotate boss stops that complete a modifier constraint
        modifier_info = []
        for sq_idx in info.get('sq_completed', []):
            sq = squares[sq_idx]
            if sq.data.get('type') == 'boss_modifier':
                modifier_info.append({
                    'constraint':   sq.data.get('constraint', ''),
                    'overhead_sec': sq.data.get('overhead_sec', 0),
                    'sq_text':      sq.text,
                })
        if modifier_info:
            stop['modifier_info'] = modifier_info

        stops.append(stop)

        if done:
            break

    return {
        'stops':       stops,
        'total_sec':   int(agent.time),
        'model_used':  model_label,
        'model_found': model is not None,
        'squares_marked': sum(agent.marks),
        'sq_count_needed': {sq.raw_name: sq.count_needed for sq in squares},
    }
