"""Deterministic reactive bingo solver.

Decision loop (re-runs every step):
  1. Endgame check — if no bingo line can be completed by either player,
     collapse to cheapest-mark-first greedy.
  2. Score every available board square on three axes:
       offensive  — exponential reward for near-complete lines
       defensive  — steeper exponential for opponent near-complete lines
       majority   — flat mark value (always in scope alongside bingo)
     Value density = (off + def * def_mult + maj) / route_cost_estimate
  3. Race condition — compare my bingo ETA vs opponent bingo ETA.
     If opponent is faster AND a forced block exists → block immediately.
     Otherwise set def_mult to escalate defensive weights.
  4. Select top-N candidate squares by adjusted density, always including
     any forced-block squares.
  5. Expand candidates into TSP nodes:
       - count_needed unvisited objective locations per square
       - prereq stops inserted as constrained predecessors
  6. Brute-force TSP over the node set (≤ self._max_tsp_nodes, ~10):
       - simulate warp pool growth per permutation
       - respect partial-order prereq constraints
       - score by total route time (lower = better)
  7. Return the UNIVERSE index of the first node in the optimal permutation.
"""
import math
from typing import Dict, List, Optional

import numpy as np

from .strategy import Strategy
from ..rl.board import UNIVERSE, UNIVERSE_SIZE, UNIVERSE_KEY_TO_IDX, Square, _loc_key
from ..rl.constants import (
    BINGO_LINES, BOSS_HP, BOSS_GRACES,
    OVERHEAD_BOSS_SEC, OVERHEAD_PICKUP_SEC, OVERHEAD_ROUNDTABLE_SEC,
    SQUARE_ACTION_SEC,
    compute_kill_time, compute_travel_time, dungeon_overhead, stones_needed,
)
from ..rl.sim import BingoGame, AgentState, _PREREQ_TABLE


# Default TSP node cap — 8! = 40k permutations, good quality for UI use
_DEFAULT_TSP_NODES    = 8
_DEFAULT_LOOKAHEAD    = 2


class DeterministicSolver(Strategy):
    # ── Scoring constants ──────────────────────────────────────────────────────
    OFF_BASE         = 3.0    # exponential base: offensive line progress
    DEF_BASE         = 4.0    # steeper base: defensive urgency
    MAJ_FLAT         = 0.5    # flat bonus per mark for majority path
    BINGO_WIN_BONUS  = 200.0  # completing MY line (4 → 5)
    BLOCK_BONUS      = 150.0  # blocking OPP 4-in-line
    DEF_MULT_URGENT  = 2.0    # defensive weight when opponent ETA < mine
    RACE_THRESHOLD   = 0.85   # opp_eta / my_eta below this → forced block if available
    CONTENTION_MULT  = 0.6    # fraction of opponent's score added as contention bonus

    # ── Pre-indexed UNIVERSE lookups (built once, reused every step) ───────────
    _IDX_OBJECTIVE  : List[int] = []   # indices where type == 'objective'
    _IDX_PREREQ     : List[int] = []   # indices where type == 'prereq'
    _IDX_ROUNDTABLE : List[int] = []   # indices where type == 'roundtable'
    # stones[(somber, tier)] → list of universe indices
    _IDX_STONES     : dict = {}
    _INDEXED        : bool = False

    @classmethod
    def _build_index(cls):
        if cls._INDEXED:
            return
        for i, entry in enumerate(UNIVERSE):
            t = entry['type']
            if t == 'objective':
                cls._IDX_OBJECTIVE.append(i)
            elif t == 'prereq':
                cls._IDX_PREREQ.append(i)
            elif t == 'roundtable':
                cls._IDX_ROUNDTABLE.append(i)
            elif t == 'stone':
                key = (entry.get('stone_somber', False), entry.get('stone_tier', 0))
                cls._IDX_STONES.setdefault(key, []).append(i)
        cls._INDEXED = True

    def __init__(self, max_tsp_nodes: int = _DEFAULT_TSP_NODES,
                 lookahead_depth: int = _DEFAULT_LOOKAHEAD):
        self._max_tsp_nodes   = max_tsp_nodes
        self._lookahead_depth = lookahead_depth
        self._build_index()

    def act(self, game: BingoGame, agent_id: int, mask: np.ndarray) -> int:
        agent = game.agents[agent_id]

        # ── Endgame: bingo impossible for both → greedy cheapest mark ──────────
        if game._no_bingo_possible():
            return self._greedy_cheapest(game, agent_id, mask)

        # ── Score all available squares ────────────────────────────────────────
        sq_scores = self._score_all_squares(game, agent_id)

        # ── Forced blocks (opponent at exactly 4-in-line) ──────────────────────
        forced = self._forced_blocks(game, agent_id, mask)

        # ── Race condition ─────────────────────────────────────────────────────
        my_eta  = self._bingo_eta(game, agent_id, own=True)
        opp_eta = self._bingo_eta(game, agent_id, own=False)
        ratio   = opp_eta / max(my_eta, 1.0)

        if ratio < self.RACE_THRESHOLD and forced:
            act = forced[0]
            return act if mask[act] else self._fallback(mask)

        def_mult = self.DEF_MULT_URGENT if ratio < 1.0 else 1.0

        # ── Candidate square selection ─────────────────────────────────────────
        candidates = self._select_candidates(game, agent_id, sq_scores, forced, def_mult, mask)

        # ── TSP route planning ─────────────────────────────────────────────────
        planned = self._plan_route(game, agent_id, candidates, mask)

        # ── Upgrade path: stones then roundtable ───────────────────────────────
        # Skip if opponent is very close to bingo, or zero-weapon squares still pending.
        if ratio >= self.RACE_THRESHOLD and not self._zero_weapon_pending(game, agent_id):
            rt = self._maybe_roundtable(agent, mask, planned)
            if rt is not None:
                return rt
            stone = self._maybe_pick_stone(agent, mask, planned)
            if stone is not None:
                return stone

        return planned

    # ── Square scoring ─────────────────────────────────────────────────────────

    def _score_all_squares(self, game: BingoGame, agent_id: int) -> Dict[int, float]:
        agent = game.agents[agent_id]
        opp   = game.agents[1 - agent_id]
        scores: Dict[int, float] = {}

        for sq in game.board:
            if agent.marks[sq.idx] or opp.marks[sq.idx]:
                continue
            if sq.requires_zero_weapon and agent.has_upgraded:
                continue
            if not game._prereqs_ever_satisfiable(sq, agent):
                continue

            off = self._offensive_score(sq.idx, agent)
            dfn = self._defensive_score(sq.idx, opp)
            est = self._square_time_est(sq, agent)
            scores[sq.idx] = (off + dfn + self.MAJ_FLAT) / max(est, 30.0)

        # ── Opponent prediction: contention bonus ──────────────────────────────
        if self._lookahead_depth > 0:
            predictions = self._predict_opponent_moves(game, agent_id)
            for pred in predictions:
                sq_idx = pred['sq_idx']
                if sq_idx not in scores:
                    continue
                # Only add bonus if we can reach it before the opponent
                if pred['my_eta'] < pred['opp_eta']:
                    scores[sq_idx] += pred['opp_score'] * self.CONTENTION_MULT

        return scores

    def _predict_opponent_moves(self, game: BingoGame, agent_id: int) -> list:
        """Score the board from the opponent's perspective, return their top N squares
        with both players' ETAs for contention analysis."""
        opp_id = 1 - agent_id
        agent  = game.agents[agent_id]
        opp    = game.agents[opp_id]

        opp_scores: Dict[int, float] = {}
        for sq in game.board:
            if opp.marks[sq.idx] or agent.marks[sq.idx]:
                continue
            if sq.requires_zero_weapon and opp.has_upgraded:
                continue
            if not game._prereqs_ever_satisfiable(sq, opp):
                continue
            off = self._offensive_score(sq.idx, opp)
            dfn = self._defensive_score(sq.idx, agent)
            est = self._square_time_est(sq, opp)
            opp_scores[sq.idx] = (off + dfn + self.MAJ_FLAT) / max(est, 30.0)

        top = sorted(opp_scores, key=opp_scores.get, reverse=True)[:self._lookahead_depth]
        result = []
        for sq_idx in top:
            sq = game.sq_by_idx.get(sq_idx)
            if sq is None:
                continue
            result.append({
                'sq_idx':    sq_idx,
                'opp_eta':   self._square_time_est(sq, opp),
                'my_eta':    self._square_time_est(sq, agent),
                'opp_score': opp_scores[sq_idx],
            })
        return result

    def _offensive_score(self, sq_idx: int, agent: AgentState) -> float:
        score = 0.0
        for line in BINGO_LINES:
            if sq_idx not in line:
                continue
            mc = sum(agent.marks[i] for i in line)
            score += self.BINGO_WIN_BONUS if mc == 4 else self.OFF_BASE ** mc
        return score

    def _defensive_score(self, sq_idx: int, opp: AgentState) -> float:
        score = 0.0
        for line in BINGO_LINES:
            if sq_idx not in line:
                continue
            oc = sum(opp.marks[i] for i in line)
            score += self.BLOCK_BONUS if oc == 4 else self.DEF_BASE ** oc
        return score

    def _square_time_est(self, sq: Square, agent: AgentState) -> float:
        if sq.is_passive or not sq.locations:
            return 60.0
        nearest = min(
            compute_travel_time(agent.pos, loc, agent.warp_pool)
            for loc in sq.locations
        )
        return nearest + self._sq_overhead_est(sq, agent) * sq.count_needed

    def _sq_overhead_est(self, sq: Square, agent: AgentState) -> float:
        t = sq.sq_type
        if 'dungeon' in t:
            return OVERHEAD_BOSS_SEC + dungeon_overhead(sq.text)
        if sq.locations:
            loc = sq.locations[0]
            boss_name = (loc.get('boss_name') or loc.get('name', '')).lower()
            if boss_name in BOSS_HP:
                kt = compute_kill_time(
                    loc.get('name', ''), agent.weapon_class, agent.weapon_level,
                    agent.is_somber, agent.primary_stat, agent.rune_level,
                    loc.get('zone', 'unknown'),
                )
                return (kt['kill_sec'] + OVERHEAD_BOSS_SEC) if kt else OVERHEAD_BOSS_SEC
        return SQUARE_ACTION_SEC.get(t, OVERHEAD_PICKUP_SEC)

    # ── Forced blocks ─────────────────────────────────────────────────────────

    def _forced_blocks(self, game: BingoGame, agent_id: int, mask: np.ndarray) -> List[int]:
        opp   = game.agents[1 - agent_id]
        agent = game.agents[agent_id]
        out: List[int] = []
        for line in BINGO_LINES:
            oc = sum(opp.marks[i] for i in line)
            if oc < 4:
                continue
            for sq_idx in line:
                if opp.marks[sq_idx] or agent.marks[sq_idx]:
                    continue
                sq = game.sq_by_idx.get(sq_idx)
                if sq is None:
                    continue
                for uni_i in self._IDX_OBJECTIVE:
                    if not mask[uni_i]:
                        continue
                    if sq.raw_name in UNIVERSE[uni_i]['sq_names']:
                        out.append(uni_i)
                        break
        return out

    # ── ETA estimates ─────────────────────────────────────────────────────────

    def _bingo_eta(self, game: BingoGame, agent_id: int, own: bool) -> float:
        a_id  = agent_id if own else 1 - agent_id
        other = 1 - a_id
        agent = game.agents[a_id]
        opp   = game.agents[other]
        best  = float('inf')
        for line in BINGO_LINES:
            if any(opp.marks[i] for i in line):
                continue
            remaining = [i for i in line if not agent.marks[i]]
            if not remaining:
                return 0.0
            total = sum(
                self._square_time_est(game.sq_by_idx[i], agent)
                for i in remaining
                if game.sq_by_idx.get(i)
            )
            best = min(best, total)
        return best

    # ── Candidate selection ───────────────────────────────────────────────────

    def _select_candidates(self, game: BingoGame, agent_id: int,
                           sq_scores: Dict[int, float], forced: List[int],
                           def_mult: float, mask: np.ndarray) -> List[int]:
        agent = game.agents[agent_id]
        opp   = game.agents[1 - agent_id]

        adjusted: Dict[int, float] = {}
        for sq_idx, _ in sq_scores.items():
            sq = game.sq_by_idx.get(sq_idx)
            if sq is None:
                continue
            off = self._offensive_score(sq_idx, agent)
            dfn = self._defensive_score(sq_idx, opp) * def_mult
            est = self._square_time_est(sq, agent)
            adjusted[sq_idx] = (off + dfn + self.MAJ_FLAT) / max(est, 30.0)

        sorted_sq = sorted(adjusted, key=adjusted.get, reverse=True)[:self._max_tsp_nodes]

        # Always include forced-block squares
        for uni_i in forced:
            for rn in UNIVERSE[uni_i].get('sq_names', frozenset()):
                sq = game.sq_by_name.get(rn)
                if sq and sq.idx not in sorted_sq:
                    sorted_sq.append(sq.idx)

        return sorted_sq

    # ── TSP route planning ────────────────────────────────────────────────────

    def _plan_route(self, game: BingoGame, agent_id: int,
                    candidate_sq_idxs: List[int], mask: np.ndarray) -> int:
        agent = game.agents[agent_id]

        nodes: List[dict] = []
        prereq_node_map: Dict[str, int] = {}

        for sq_idx in candidate_sq_idxs:
            sq = game.sq_by_idx.get(sq_idx)
            if sq is None:
                continue

            already_visited = len(agent.sq_progress.get(sq_idx, set()))
            still_needed    = max(0, sq.count_needed - already_visited)
            if still_needed == 0:
                continue

            # ── Insert prereq nodes ────────────────────────────────────────────
            prereq_node_indices_for_sq: List[int] = []
            for pk in (sq.prereqs or []):
                if self._prereq_met_by_state(pk, agent):
                    continue

                # Check if an already-queued node satisfies this prereq
                existing = next(
                    (j for j, nd in enumerate(nodes)
                     if self._node_satisfies_prereq(UNIVERSE[nd['uni_idx']], pk)),
                    None,
                )
                if existing is not None:
                    prereq_node_indices_for_sq.append(existing)
                    continue

                if pk in prereq_node_map:
                    prereq_node_indices_for_sq.append(prereq_node_map[pk])
                    continue

                # Find and add a PREREQ_LOC entry
                for uni_i in self._IDX_PREREQ:
                    if not mask[uni_i]:
                        continue
                    if UNIVERSE[uni_i].get('prereq_key') == pk:
                        idx = len(nodes)
                        nodes.append({'uni_idx': uni_i, 'sq_idx': None, 'needs_before': set()})
                        prereq_node_map[pk] = idx
                        prereq_node_indices_for_sq.append(idx)
                        break

            # ── Add objective nodes for this square ────────────────────────────
            added = 0
            for uni_i in self._IDX_OBJECTIVE:
                if added >= still_needed:
                    break
                if not mask[uni_i]:
                    continue
                entry = UNIVERSE[uni_i]
                if sq.raw_name not in entry.get('sq_names', frozenset()):
                    continue
                if entry['key'] in agent.visited_keys:
                    continue
                nodes.append({
                    'uni_idx':    uni_i,
                    'sq_idx':     sq_idx,
                    'needs_before': set(prereq_node_indices_for_sq),
                })
                added += 1

        # Trim to hard cap
        if len(nodes) > self._max_tsp_nodes:
            nodes = nodes[:self._max_tsp_nodes]

        if not nodes:
            return self._fallback(mask)

        # ── Pre-compute distance matrix (avoids repeated travel calc in TSP loop) ─
        n     = len(nodes)
        locs  = [UNIVERSE[nd['uni_idx']]['loc'] for nd in nodes]
        warp0 = agent.warp_pool

        # dist_from_start[j]: travel from current position to node j
        d0 = [compute_travel_time(agent.pos, locs[j], warp0) for j in range(n)]
        # dist_matrix[i][j]: travel from node i's location to node j's location.
        # Uses the initial warp pool as a consistent baseline — the solver
        # re-evaluates every step so the small error from ignoring mid-route
        # grace unlocks doesn't accumulate.
        dm = [
            [compute_travel_time(locs[i], locs[j], warp0) for j in range(n)]
            for i in range(n)
        ]
        oh = [
            self._entry_overhead(
                UNIVERSE[nodes[j]['uni_idx']],
                game.sq_by_idx.get(nodes[j]['sq_idx']) if nodes[j]['sq_idx'] is not None else None,
                agent,
            )
            for j in range(n)
        ]

        # ── Branch-and-bound TSP with pruning ─────────────────────────────────
        # Sort nodes in greedy nearest-neighbour order so the first DFS path
        # explored is near-optimal — maximising early pruning of worse branches.
        order = []
        remaining_set = set(range(n))
        cur = -1
        while remaining_set:
            nxt = min(remaining_set,
                      key=lambda j: (d0[j] if cur < 0 else dm[cur][j]) + oh[j])
            order.append(nxt)
            remaining_set.remove(nxt)
            cur = nxt
        # Remap nodes/d0/dm/oh to greedy order so DFS walks cheapest-first
        nodes = [nodes[i] for i in order]
        d0    = [d0[i]    for i in order]
        oh    = [oh[i]    for i in order]
        dm    = [[dm[order[i]][order[j]] for j in range(n)] for i in range(n)]
        # Remap needs_before indices to new ordering
        old_to_new = {old: new for new, old in enumerate(order)}
        for nd in nodes:
            nd['needs_before'] = {old_to_new[x] for x in nd['needs_before']}

        state     = [float('inf'), nodes[0]['uni_idx']]
        remaining = list(range(n))

        def _search(path: List[int], seen_mask: int,
                    partial: float, last: int) -> None:
            if not remaining:
                if partial < state[0]:
                    state[0] = partial
                    state[1] = nodes[path[0]]['uni_idx']
                return
            for pos, idx in enumerate(remaining):
                nb = nodes[idx]['needs_before']
                if nb and not all(seen_mask >> x & 1 for x in nb):
                    continue
                step = (d0[idx] if last < 0 else dm[last][idx]) + oh[idx]
                cost = partial + step
                if cost >= state[0]:
                    continue
                remaining.pop(pos)
                path.append(idx)
                _search(path, seen_mask | (1 << idx), cost, idx)
                remaining.insert(pos, idx)
                path.pop()

        _search([], 0, 0.0, -1)
        best_first = state[1]
        return best_first if mask[best_first] else self._fallback(mask)

    # ── Per-node overhead estimate (mirrors sim.py logic, no state mutation) ──

    def _entry_overhead(self, entry: dict, sq: Optional[Square],
                        agent: AgentState) -> float:
        t = entry['type']
        if t in ('grace', 'prereq'):
            return float(OVERHEAD_PICKUP_SEC)
        if t == 'stone':
            return float(OVERHEAD_PICKUP_SEC)
        if t == 'roundtable':
            return float(OVERHEAD_ROUNDTABLE_SEC)
        loc       = entry['loc']
        boss_name = (loc.get('boss_name') or loc.get('name', '')).lower()
        if boss_name in BOSS_HP:
            kt = compute_kill_time(
                loc.get('name', ''), agent.weapon_class, agent.weapon_level,
                agent.is_somber, agent.primary_stat, agent.rune_level,
                loc.get('zone', 'unknown'),
            )
            return float((kt['kill_sec'] + OVERHEAD_BOSS_SEC) if kt else OVERHEAD_BOSS_SEC)
        if sq:
            if 'dungeon' in sq.sq_type:
                return float(OVERHEAD_BOSS_SEC + dungeon_overhead(sq.text))
            return float(SQUARE_ACTION_SEC.get(sq.sq_type, OVERHEAD_PICKUP_SEC))
        return float(OVERHEAD_PICKUP_SEC)

    # ── Prereq helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _prereq_met_by_state(prereq_key: str, agent: AgentState) -> bool:
        res = _PREREQ_TABLE.get(prereq_key)
        if res is None:
            return True  # optimistic
        if res['type'] == 'grace':
            return any(g.get('id') == res['grace_id'] for g in agent.warp_pool)
        if res['type'] == 'any_grace':
            return any(g.get('id') in res.get('grace_ids', set()) for g in agent.warp_pool)
        if res['type'] == 'min_graces':
            count = sum(1 for g in agent.warp_pool if g.get('id') in res.get('grace_ids', set()))
            return count >= res.get('min', 1)
        if res['type'] == 'visited':
            return res['loc_key'] in agent.visited_keys
        return True  # optimistic

    @staticmethod
    def _node_satisfies_prereq(entry: dict, prereq_key: str) -> bool:
        res = _PREREQ_TABLE.get(prereq_key)
        if res is None:
            return False
        loc       = entry['loc']
        boss_name = (loc.get('boss_name') or loc.get('name', '')).lower()
        bg        = BOSS_GRACES.get(boss_name)
        if res['type'] == 'grace' and bg:
            return bg['id'] == res['grace_id']
        if res['type'] == 'visited':
            return entry.get('key') == res['loc_key']
        return False

    # ── Stone and upgrade logic ───────────────────────────────────────────────

    # Max extra seconds willing to detour for a stone or roundtable visit.
    STONE_DETOUR_SEC     = 60
    ROUNDTABLE_DETOUR_SEC = 90

    def _zero_weapon_pending(self, game: BingoGame, agent_id: int) -> bool:
        """True if any unmarked square requires a +0 weapon."""
        agent = game.agents[agent_id]
        opp   = game.agents[1 - agent_id]
        return any(
            sq.requires_zero_weapon
            and not agent.marks[sq.idx]
            and not opp.marks[sq.idx]
            for sq in game.board
        )

    def _needed_stone_tier(self, agent: AgentState) -> Optional[int]:
        """Tier of stone needed for the agent's next upgrade level, or None."""
        max_lv = 9 if agent.is_somber else 24
        if agent.weapon_level >= max_lv:
            return None
        inv   = agent.somber_stones if agent.is_somber else agent.smithing_stones
        needs = stones_needed(agent.weapon_level, agent.weapon_level + 1, agent.is_somber)
        for tier, count in needs.items():
            if inv.get(tier, 0) < count:
                return tier
        return None  # have enough stones already — just need roundtable

    def _detour_cost(self, agent: AgentState, candidate_loc: dict, planned_loc: dict) -> float:
        """Extra seconds to visit candidate_loc before planned_loc vs going direct."""
        pool = agent.warp_pool
        d_direct    = compute_travel_time(agent.pos, planned_loc, pool)
        d_to_cand   = compute_travel_time(agent.pos, candidate_loc, pool)
        d_cand_plan = compute_travel_time(candidate_loc, planned_loc, pool)
        return max(0, d_to_cand + OVERHEAD_PICKUP_SEC + d_cand_plan - d_direct)

    def _maybe_pick_stone(self, agent: AgentState, mask: np.ndarray,
                          planned: int) -> Optional[int]:
        """Return a stone action if picking it up is a cheap enough detour."""
        tier = self._needed_stone_tier(agent)
        if tier is None:
            return None
        planned_loc = UNIVERSE[planned]['loc']
        best_cost   = self.STONE_DETOUR_SEC
        best_uni    = None
        for uni_i in self._IDX_STONES.get((agent.is_somber, tier), []):
            if not mask[uni_i]:
                continue
            cost = self._detour_cost(agent, UNIVERSE[uni_i]['loc'], planned_loc)
            if cost < best_cost:
                best_cost = cost
                best_uni  = uni_i
        return best_uni

    def _maybe_roundtable(self, agent: AgentState, mask: np.ndarray,
                          planned: int) -> Optional[int]:
        """Return roundtable action if an upgrade is available and affordable."""
        if not agent.can_upgrade_to(agent.weapon_level + 1):
            return None
        planned_loc = UNIVERSE[planned]['loc']
        for uni_i in self._IDX_ROUNDTABLE:
            if not mask[uni_i]:
                continue
            cost = self._detour_cost(agent, UNIVERSE[uni_i]['loc'], planned_loc)
            if cost <= self.ROUNDTABLE_DETOUR_SEC:
                return uni_i
        return None

    # ── Endgame greedy ────────────────────────────────────────────────────────

    def _greedy_cheapest(self, game: BingoGame, agent_id: int,
                         mask: np.ndarray) -> int:
        agent    = game.agents[agent_id]
        best_idx: Optional[int] = None
        best_t   = float('inf')
        for i, entry in enumerate(UNIVERSE):
            if not mask[i] or entry['type'] != 'objective':
                continue
            t = compute_travel_time(agent.pos, entry['loc'], agent.warp_pool)
            if t < best_t:
                best_t   = t
                best_idx = i
        return best_idx if best_idx is not None else self._fallback(mask)

    # ── Fallback ──────────────────────────────────────────────────────────────

    @staticmethod
    def _fallback(mask: np.ndarray) -> int:
        valid = np.where(mask)[0]
        return int(valid[0]) if len(valid) else 0
