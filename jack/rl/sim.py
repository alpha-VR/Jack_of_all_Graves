"""Discrete-event game simulation for lockout bingo self-play.

The RL agent picks a location from the universe at each decision point.
The simulation advances that agent's time by (travel + action overhead),
updates inventory and progress, checks bingo win conditions, and returns
the new game state.

Both agents run in their own time streams.  The agent with the lower
current time acts next; the other acts when their time is smaller.
"""
import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .constants import (
    S6_GRACES, BOSS_GRACES, ROUNDTABLE,
    ZONE_TIER, ZONE_PENALTY,
    BOSS_HP, WEAPON_CLASSES, STAVES,
    SMITHING_RUNE_COST, SOMBER_RUNE_COST,
    OVERHEAD_GRACE_SEC, OVERHEAD_BOSS_SEC, OVERHEAD_PICKUP_SEC,
    OVERHEAD_DUNGEON_SEC, OVERHEAD_ROUNDTABLE_SEC, SQUARE_ACTION_SEC,
    compute_kill_time, compute_travel_time, compute_rune_level,
    compute_death_probability, boss_weapon_floor, get_boss_difficulty,
    max_upgrade_level, stones_needed, dungeon_overhead, BINGO_LINES, N_SQUARES,
    PREREQ_LOCS, PREREQ_RESOLUTION, BOSS_MODIFIER_KILL_MULT,
    runes_to_reach_level,
)
from .board import Square, UNIVERSE, UNIVERSE_SIZE, UNIVERSE_KEY_TO_IDX, _loc_key

# ── Observation stream dimensions ──────────────────────────────────────────────
# Self stream:  my_marks(25) + line_mc(12) + agent_state(8) + stones(17) + time(1)
# Opp stream:   opp_marks(25) + per_line(oc+danger=24) + opp_extras(4)
# Board stream: N_SQUARES * 9  (my_mark, opp_mark, available, zone_tier,
#                                coloc, zone_density, prereq_ok,
#                                progress_ratio, unvisited_ratio)
SELF_DIM  = 63
OPP_DIM   = 53
BOARD_DIM = N_SQUARES * 10  # 250

# Prereq resolution — loaded from square_data.json _meta.prereq_resolution.
# Each entry: {'type': 'grace'|'visited'|'optimistic', 'grace_id'|'loc_key': ...}
# Unknown keys → warn once then treat as optimistic.
_PREREQ_TABLE: dict = dict(PREREQ_RESOLUTION)
# Ensure PREREQ_LOCS entries are present (loc_keys computed from coordinates).
for _ploc in PREREQ_LOCS:
    _key = _ploc['prereq_key']
    if _key not in _PREREQ_TABLE:
        _PREREQ_TABLE[_key] = {'type': 'visited', 'loc_key': _loc_key(_ploc)}
_PREREQ_WARNED: set = set()  # tracks unknown keys so we only warn once


# ── Agent state ────────────────────────────────────────────────────────────────
@dataclass
class AgentState:
    agent_id:    int
    pos:         dict               # current location {x, y, level, zone, name}
    warp_pool:   list               # available grace/warp points

    # Weapon
    weapon_class:  str
    weapon_level:  int
    is_somber:     bool
    primary_stat:  str

    # Resources
    rune_level:         int
    total_runes_earned: int
    rune_balance:       int         # runes available to spend

    # Stone inventory {tier: count}  (smithing, somber kept separately)
    smithing_stones: Dict[int, int]
    somber_stones:   Dict[int, int]

    # Flask
    flask_level:   int              # +0 to +14
    flask_charges: int

    # Board progress
    marks:           List[bool]     # 25 squares, True = I marked it
    sq_progress:     Dict[int, Set] # {sq_idx: set of visited loc keys}

    # Time
    time: float                     # game seconds elapsed for this agent

    # State flags
    has_upgraded:    bool           # any weapon upgrade done (+0 squares invalid)
    seal_collected:  bool           # free seal from Roundtable

    # Visited locations (for masking)
    visited_keys:    Set[str]

    def stone_inventory(self, somber: bool) -> Dict[int, int]:
        return self.somber_stones if somber else self.smithing_stones

    def add_stone(self, tier: int, somber: bool, count: int = 1):
        inv = self.somber_stones if somber else self.smithing_stones
        inv[tier] = inv.get(tier, 0) + count

    def can_upgrade_to(self, target_level: int) -> bool:
        """Check if we have stones + runes to upgrade from current level."""
        if self.is_somber:
            max_lv = 9
        else:
            max_lv = 24
        if target_level > max_lv or target_level <= self.weapon_level:
            return False
        needs = stones_needed(self.weapon_level, target_level, self.is_somber)
        for tier, cnt in needs.items():
            inv = self.somber_stones if self.is_somber else self.smithing_stones
            if inv.get(tier, 0) < cnt:
                return False
        rune_cost = sum(
            (SOMBER_RUNE_COST if self.is_somber else SMITHING_RUNE_COST)[lvl]
            for lvl in range(self.weapon_level + 1, target_level + 1)
        )
        return self.rune_balance >= rune_cost

    def best_upgrade_level(self) -> int:
        """Highest level we can currently upgrade to."""
        max_lv = 9 if self.is_somber else 24
        best = self.weapon_level
        for lvl in range(self.weapon_level + 1, max_lv + 1):
            if self.can_upgrade_to(lvl):
                best = lvl
            else:
                break
        return best

    def do_upgrade(self):
        """Perform best available upgrade, deducting stones and runes."""
        target = self.best_upgrade_level()
        if target <= self.weapon_level:
            return
        needs = stones_needed(self.weapon_level, target, self.is_somber)
        inv = self.somber_stones if self.is_somber else self.smithing_stones
        for tier, cnt in needs.items():
            inv[tier] = max(0, inv.get(tier, 0) - cnt)
        rune_cost = sum(
            (SOMBER_RUNE_COST if self.is_somber else SMITHING_RUNE_COST)[lvl]
            for lvl in range(self.weapon_level + 1, target + 1)
        )
        self.rune_balance -= rune_cost
        self.weapon_level = target
        self.has_upgraded = True


# ── Game state ─────────────────────────────────────────────────────────────────
class BingoGame:
    """
    Two-agent lockout bingo simulation.

    Each agent makes stop-level decisions (which of the UNIVERSE locations to
    visit next).  The simulation computes exact travel + action time and
    advances that agent's clock.  Both agents run concurrently in separate
    time streams.
    """

    def __init__(self, board: List[Square], rng=None):
        self.board = board          # 25 Square objects
        self.rng   = rng or random.Random()

        # Build per-game universe mask: which UNIVERSE entries are relevant
        # to this specific board.  Stone nodes and roundtable are always relevant.
        board_raw_names = {sq.raw_name for sq in board}
        board_prereqs   = {p for sq in board for p in (sq.prereqs or [])}
        self.relevant_mask = []
        for entry in UNIVERSE:
            t = entry['type']
            if t == 'objective':
                self.relevant_mask.append(bool(entry['sq_names'] & board_raw_names))
            elif t == 'prereq':
                self.relevant_mask.append(entry['prereq_key'] in board_prereqs)
            else:
                self.relevant_mask.append(True)

        # Map square raw_name → board square
        self.sq_by_name  = {sq.raw_name: sq for sq in board}
        self.sq_by_idx   = {sq.idx: sq for sq in board}

        # ── POI-derived synergy maps (precomputed once per episode) ────────────
        # Co-location: sq_idx → set of other sq_idx sharing at least one loc key
        loc_to_sq: Dict[str, Set[int]] = {}
        for sq in board:
            for loc in sq.locations:
                k = _loc_key(loc)
                loc_to_sq.setdefault(k, set()).add(sq.idx)
        self._coloc_partners: List[Set[int]] = []
        for sq in board:
            partners: Set[int] = set()
            for loc in sq.locations:
                for other in loc_to_sq.get(_loc_key(loc), set()):
                    if other != sq.idx:
                        partners.add(other)
            self._coloc_partners.append(partners)

        # Primary zone per square (mode of location zones)
        self._sq_zone: List[str] = []
        for sq in board:
            zc: Dict[str, int] = {}
            for loc in sq.locations:
                z = loc.get('zone') or 'unknown'
                zc[z] = zc.get(z, 0) + 1
            self._sq_zone.append(max(zc, key=zc.get) if zc else 'unknown')

        # Zone → list of sq_idx on this board
        self._zone_sq: Dict[str, List[int]] = {}
        for sq in board:
            self._zone_sq.setdefault(self._sq_zone[sq.idx], []).append(sq.idx)

        # Stone proximity: stone universe entry index → T1 objective loc keys nearby.
        # Used for reward shaping when agent picks up a stone near an open objective.
        _T2_RADIUS_SQ = 1.0 ** 2  # squared distance threshold (mirrors JS TIER2_RADIUS=1)
        self._stone_near_obj: List[bool] = []  # parallel to UNIVERSE, True = near T1 loc
        obj_locs = [
            entry['loc'] for entry in UNIVERSE
            if entry['type'] == 'objective' and entry['loc'].get('x')
        ]
        for entry in UNIVERSE:
            if entry['type'] != 'stone':
                self._stone_near_obj.append(False)
                continue
            lx, ly = entry['loc'].get('x', 0), entry['loc'].get('y', 0)
            near = any(
                (lx - o['x']) ** 2 + (ly - o['y']) ** 2 <= _T2_RADIUS_SQ
                for o in obj_locs if o.get('x')
            )
            self._stone_near_obj.append(near)

        # Initialise both agents
        self.agents = [self._init_agent(i) for i in range(2)]

        # Opponent board marks visible to each agent (only marks, not position)
        # agents[i].marks = my marks;  _opp_marks[i] = what agent i sees of opp
        self.done   = False
        self.winner = None  # 0, 1, or -1 (draw)

    # ── Initialisation ──────────────────────────────────────────────────────────
    def _init_agent(self, agent_id: int) -> AgentState:
        # Randomise starting grace (physical start position)
        grace = self.rng.choice(S6_GRACES)
        # Randomise weapon class (S6: class retained, specific weapon random)
        weapon_class = self.rng.choice(WEAPON_CLASSES)
        # Seal is always available at Roundtable (Sacred Seal, fixed)
        is_somber = weapon_class in ('Glintstone Staff', 'Sacred Seal')

        return AgentState(
            agent_id=agent_id,
            pos=dict(grace),
            # All 13 S6 starting graces are pre-lit and warpable from turn 1
            # (Torrent is picked up at the first grace rest — all are accessible)
            warp_pool=[dict(g) for g in S6_GRACES],
            weapon_class=weapon_class,
            weapon_level=0,
            is_somber=is_somber,
            primary_stat=self._default_stat(weapon_class),
            rune_level=10,
            total_runes_earned=runes_to_reach_level(10),
            rune_balance=0,
            smithing_stones={},
            somber_stones={},
            flask_level=0,
            flask_charges=4,   # starting flasks in ER
            marks=[False] * N_SQUARES,
            sq_progress={},
            time=0.0,
            has_upgraded=False,
            seal_collected=False,
            visited_keys=set(),
        )

    @staticmethod
    def _default_stat(weapon_class):
        if weapon_class in ('Glintstone Staff',):         return 'Int'
        if weapon_class in ('Sacred Seal',):              return 'Faith'
        if weapon_class in ('Dagger', 'Katana', 'Claw', 'Thrusting Sword',
                            'Twinblade', 'Curved Sword'): return 'Dexterity'
        return 'Strength'

    # ── Core step ───────────────────────────────────────────────────────────────
    def step(self, agent_id: int, action_idx: int) -> Tuple[float, bool, dict]:
        """
        Execute the chosen action for `agent_id`.

        Returns (reward, done, info).
        The caller should read game.get_obs(agent_id) for the next observation.
        """
        if self.done:
            return 0.0, True, {}

        agent  = self.agents[agent_id]
        entry  = UNIVERSE[action_idx]
        loc    = entry['loc']
        key    = entry['key']

        # ── Travel time ──────────────────────────────────────────────────────────
        travel_sec = compute_travel_time(agent.pos, loc, agent.warp_pool)
        agent.time += travel_sec

        # ── Action time + effects ────────────────────────────────────────────────
        overhead = OVERHEAD_GRACE_SEC
        runes_gained    = 0
        sq_completed    = []
        stone_reward    = 0.0
        upgrade_reward  = 0.0
        death_penalty   = 0.0
        partial_reward  = 0.0
        blocking_reward = 0.0

        if entry['type'] == 'roundtable':
            overhead = OVERHEAD_ROUNDTABLE_SEC
            if not agent.seal_collected:
                agent.seal_collected = True
            old_wl = agent.weapon_level
            agent.do_upgrade()
            upgrade_reward = 0.06 * (agent.weapon_level - old_wl)
            agent.visited_keys.add(key)
            # Unlock Roundtable grace for warping
            if not any(g.get('id') == 'roundtable' for g in agent.warp_pool):
                agent.warp_pool.append(dict(ROUNDTABLE))

        elif entry['type'] == 'stone':
            overhead = OVERHEAD_PICKUP_SEC
            tier   = entry['stone_tier']
            somber = entry['stone_somber']
            count  = entry.get('stone_count', 1)
            agent.add_stone(tier, somber, count)
            agent.visited_keys.add(key)
            cur_tier = (agent.weapon_level + 1) if somber else (agent.weapon_level // 3 + 1)
            usefulness = max(0.0, 1.0 - abs(tier - cur_tier) * 0.25)
            proximity_bonus = 0.012 if self._stone_near_obj[action_idx] else 0.0
            stone_reward = 0.06 * max(usefulness, 0.15) + proximity_bonus
            # Upgrade-enable bonus: first stone of the exact needed tier unlocks next upgrade
            inv = agent.somber_stones if somber else agent.smithing_stones
            if tier == cur_tier and inv.get(tier, 0) == count:
                stone_reward += 0.04

        elif entry['type'] == 'objective':
            # Determine which board squares this location contributes to.
            # Location-level prereqs gate the entire visit (e.g. medallion chest
            # requires Niall dead); square-level prereqs gate per-square credit.
            loc_prereqs_ok = self._check_prereqs(entry.get('loc_prereqs', []), agent)
            relevant_squares = [
                sq for sq in self.board
                if sq.raw_name in entry['sq_names']
                and not agent.marks[sq.idx]
                and not self._is_blocked_by_opp(sq.idx, agent_id)
                and not (sq.requires_zero_weapon and agent.has_upgraded)
                and self._prereqs_satisfied(sq, agent)
            ] if loc_prereqs_ok else []

            # Mutual exclusivity: at most one boss_modifier can complete per boss kill.
            # Keep the easiest constraint for this build (lowest kill multiplier).
            modifier_sqs = [sq for sq in relevant_squares if sq.sq_type == 'boss_modifier']
            if len(modifier_sqs) > 1:
                modifier_sqs.sort(key=lambda sq: BOSS_MODIFIER_KILL_MULT.get(
                    sq.data.get('constraint', ''), {}).get(agent.primary_stat, 1.5))
                for sq in modifier_sqs[1:]:
                    relevant_squares.remove(sq)

            if not relevant_squares:
                # Location visited but no benefit — still costs travel time
                pass
            else:
                # Snapshot progress before this visit for partial reward calculation
                prog_before = {
                    sq.idx: len(agent.sq_progress.get(sq.idx, set()))
                    for sq in relevant_squares
                }
                for sq in relevant_squares:
                    progress = agent.sq_progress.setdefault(sq.idx, set())
                    progress.add(key)
                    needed = self._count_needed(sq, agent)
                    if len(progress) >= needed:
                        # Square complete!
                        agent.marks[sq.idx] = True
                        sq_completed.append(sq.idx)
                        runes_gained += sq.runes_on_complete

                # Partial progress: small reward for each new step toward a square
                opp_agent = self.agents[1 - agent_id]
                for sq in relevant_squares:
                    if not agent.marks[sq.idx]:
                        needed = self._count_needed(sq, agent)
                        after  = len(agent.sq_progress.get(sq.idx, set()))
                        if after > prog_before[sq.idx]:
                            partial_reward += 0.04 / max(needed, 1)

                # Blocking: reward for marking a square that broke an opponent danger line
                for sq_idx in sq_completed:
                    best = 0
                    for line in BINGO_LINES:
                        if sq_idx in line:
                            oc = sum(opp_agent.marks[i] for i in line)
                            if oc >= 2:
                                best = max(best, oc)
                    if best >= 2:
                        blocking_reward += 0.08 * best

                # Line proximity: bonus for reaching 3-in-a-line or 4-in-a-line
                for sq_idx in sq_completed:
                    for line in BINGO_LINES:
                        if sq_idx in line:
                            mc = sum(agent.marks[i] for i in line)
                            if mc == 3:
                                partial_reward += 0.10
                            elif mc == 4:
                                partial_reward += 0.25
                            break

            # Boss kill: compute time + runes + unlock grace
            # boss_name field overrides location name for items dropped by bosses
            boss_name = (loc.get('boss_name') or loc.get('name', '')).lower().replace('-', ' ')
            boss_data = BOSS_HP.get(boss_name)
            if not boss_data:
                for k2, v in BOSS_HP.items():
                    if boss_name in k2 or k2 in boss_name:
                        boss_data = v; break

            if boss_data:
                kill_result = compute_kill_time(
                    loc.get('name', ''), agent.weapon_class, agent.weapon_level,
                    agent.is_somber, agent.primary_stat, agent.rune_level,
                    loc.get('zone', 'unknown'),
                )
                if kill_result:
                    kill_sec      = kill_result['kill_sec']
                    runes_gained += kill_result['runes']
                    # Apply boss_modifier constraint multiplier if any board square requires it
                    modifier_mult    = 1.0
                    modifier_overhead = 0
                    for sq in relevant_squares:
                        if sq.sq_type == 'boss_modifier':
                            constraint = sq.data.get('constraint', '')
                            mult = BOSS_MODIFIER_KILL_MULT.get(constraint, {}).get(
                                agent.primary_stat, 1.5)
                            if mult > modifier_mult:
                                modifier_mult = mult
                            mod_oh = sq.data.get('overhead_sec', 0)
                            if mod_oh > modifier_overhead:
                                modifier_overhead = mod_oh
                    kill_sec = math.ceil(kill_sec * modifier_mult)
                    overhead      = OVERHEAD_BOSS_SEC + kill_sec + modifier_overhead
                    # Stochastic variance (±15%)
                    overhead = int(overhead * self.rng.uniform(0.85, 1.15))
                else:
                    overhead += OVERHEAD_BOSS_SEC
                # Unlock boss grace
                bg = BOSS_GRACES.get(boss_name)
                if bg and not any(g.get('id') == bg['id'] for g in agent.warp_pool):
                    agent.warp_pool.append(dict(bg))
                # Death probability: underleveled agents lose runes and spend recovery time.
                # Recovery time uses nearest warp-point distance — a tactical grace near
                # the boss dramatically shortens the corpse run vs. a distant S6 grace.
                p_death = compute_death_probability(
                    loc.get('zone', 'unknown'), agent.weapon_level, agent.is_somber
                )
                if p_death > 0:
                    difficulty        = get_boss_difficulty(loc.get('name', ''))
                    recovery_travel   = compute_travel_time(agent.pos, loc, agent.warp_pool)
                    death_time        = int(recovery_travel + 30 * math.sqrt(difficulty))
                    if self.rng.random() < p_death:
                        agent.rune_balance = 0
                        agent.time += death_time
                        death_penalty = 0.10
                    else:
                        death_penalty = p_death * 0.025
            else:
                # Pickup / NPC / dungeon overhead — per-square override, then per-type
                sq = relevant_squares[0] if relevant_squares else None
                sq_type = sq.sq_type if sq else ''
                sq_overhead = sq.data.get('overhead_sec') if sq else None
                if sq_overhead:
                    overhead += sq_overhead
                elif 'dungeon' in sq_type:
                    overhead += OVERHEAD_DUNGEON_SEC + dungeon_overhead(sq.text if sq else '')
                else:
                    overhead += SQUARE_ACTION_SEC.get(sq_type, OVERHEAD_PICKUP_SEC)

            agent.visited_keys.add(key)
            agent.pos = dict(loc)
            # Unlock this location as a warp point if it's a named grace
            if loc.get('name') and not any(
                abs(g.get('x',0)-loc['x'])<0.5 for g in agent.warp_pool
            ):
                agent.warp_pool.append(dict(loc))

        elif entry['type'] == 'grace':
            # Tactical grace: register as warp point and move position.
            # No square credit, but shortens corpse-run recovery when nearby bosses are fought.
            overhead = OVERHEAD_GRACE_SEC
            agent.visited_keys.add(key)
            agent.pos = dict(loc)
            grace_id = entry.get('grace_id')
            if grace_id and not any(g.get('id') == grace_id for g in agent.warp_pool):
                agent.warp_pool.append(dict(loc) | {'id': grace_id})

        elif entry['type'] == 'prereq':
            # Prerequisite-only stop: pay travel overhead, no square credit.
            # Boss kills still happen and add their grace so grace-type prereqs are satisfied.
            overhead = OVERHEAD_PICKUP_SEC
            agent.visited_keys.add(key)
            agent.pos = dict(loc)
            if loc.get('name') and not any(
                abs(g.get('x', 0) - loc['x']) < 0.5 for g in agent.warp_pool
            ):
                agent.warp_pool.append(dict(loc))
            # Boss kill: add kill time and unlock boss grace
            boss_name = loc.get('name', '').lower()
            boss_data = BOSS_HP.get(boss_name)
            if not boss_data:
                for k2, v in BOSS_HP.items():
                    if boss_name in k2 or k2 in boss_name:
                        boss_data = v; break
            if boss_data:
                kill_result = compute_kill_time(
                    loc.get('name', ''), agent.weapon_class, agent.weapon_level,
                    agent.is_somber, agent.primary_stat, agent.rune_level,
                    loc.get('zone', 'unknown'),
                )
                if kill_result:
                    overhead += kill_result['kill_sec']
                    runes_gained += kill_result['runes']
                else:
                    overhead += OVERHEAD_BOSS_SEC
                bg = BOSS_GRACES.get(boss_name)
                if bg and not any(g.get('id') == bg['id'] for g in agent.warp_pool):
                    agent.warp_pool.append(dict(bg))

        agent.time += overhead

        # ── Update rune economy ──────────────────────────────────────────────────
        if runes_gained:
            agent.total_runes_earned += runes_gained
            agent.rune_balance       += runes_gained
            agent.rune_level = compute_rune_level(agent.total_runes_earned)

        # ── Auto-mark passive squares (rune threshold) ───────────────────────────
        # passive_runes:  mark "Rune Level 60" when total rune level reaches 60
        # passive_stat:   mark "30 Faith/Int/Arcane" when rune level reaches 30
        # consumable_action with runes_threshold: mark when rune_balance hits threshold,
        #   then drain rune_balance (simulates spending runes on the consumable use)
        for sq in self.board:
            if agent.marks[sq.idx] or self._is_blocked_by_opp(sq.idx, agent_id):
                continue
            if sq.sq_type == 'passive_runes' and agent.rune_level >= 60:
                agent.marks[sq.idx] = True
                sq_completed.append(sq.idx)
            elif sq.sq_type == 'passive_stat' and agent.rune_level >= 30:
                agent.marks[sq.idx] = True
                sq_completed.append(sq.idx)
            elif sq.sq_type == 'consumable_action':
                threshold = sq.data.get('runes_threshold', 0)
                if threshold and agent.rune_balance >= threshold:
                    agent.marks[sq.idx] = True
                    sq_completed.append(sq.idx)
                    agent.rune_balance = 0

        # ── Reward shaping ───────────────────────────────────────────────────────
        reward = 0.0
        reward += 0.15 * len(sq_completed)   # per-square bonus (increased)
        reward += partial_reward             # dense: fractional credit toward squares
        reward += blocking_reward            # strategic: breaking opponent danger lines
        reward -= travel_sec * 0.00005      # time penalty (halved — win must dominate)
        reward += stone_reward
        reward += upgrade_reward
        reward -= death_penalty

        # ── Win condition check ──────────────────────────────────────────────────
        done   = False
        my_marks  = agent.marks
        opp_marks = self.agents[1 - agent_id].marks

        # Did I win (bingo line OR majority)?
        if self._has_bingo(my_marks) or self._check_majority() == agent_id:
            self.done   = True
            self.winner = agent_id
            reward += 1.0
            done   = True
        # Did opponent win?
        elif self._has_bingo(opp_marks) or self._check_majority() == 1 - agent_id:
            self.done   = True
            self.winner = 1 - agent_id
            reward -= 1.0
            done   = True
        # All markable squares taken → majority wins
        elif self._no_markable_squares_remain():
            my_count  = sum(my_marks)
            opp_count = sum(opp_marks)
            self.done = True
            if my_count > opp_count:
                self.winner = agent_id
                reward += 1.0
            elif opp_count > my_count:
                self.winner = 1 - agent_id
                reward -= 1.0
            else:
                # Tie-break by game time — lower time = more efficient routing wins
                t0 = self.agents[0].time
                t1 = self.agents[1].time
                winner_id = 0 if t0 <= t1 else 1
                self.winner = winner_id
                if winner_id == agent_id:
                    reward += 0.5
                else:
                    reward -= 0.5
            done = True

        return reward, done, {
            'sq_completed': sq_completed,
            'runes_gained': runes_gained,
            'agent_time':   agent.time,
        }

    # ── Helpers ──────────────────────────────────────────────────────────────────
    def _is_blocked_by_opp(self, sq_idx: int, agent_id: int) -> bool:
        return self.agents[1 - agent_id].marks[sq_idx]

    def _check_prereqs(self, prereqs: list, agent: AgentState) -> bool:
        """Return True if every prereq in the list is satisfied by the agent."""
        for p in prereqs:
            res = _PREREQ_TABLE.get(p)
            if res is None:
                if p not in _PREREQ_WARNED:
                    _PREREQ_WARNED.add(p)
                    print(f'[prereq] unknown key {p!r} — treating as optimistic; '
                          f'add to square_data.json _meta.prereq_resolution')
                continue  # optimistic
            if res['type'] == 'grace':
                if not any(g.get('id') == res['grace_id'] for g in agent.warp_pool):
                    return False
            elif res['type'] == 'any_grace':
                if not any(g.get('id') in res['grace_ids'] for g in agent.warp_pool):
                    return False
            elif res['type'] == 'min_graces':
                grace_ids = set(res.get('grace_ids', []))
                count = sum(1 for g in agent.warp_pool if g.get('id') in grace_ids)
                if count < res.get('min', 1):
                    return False
            elif res['type'] == 'visited':
                if res['loc_key'] not in agent.visited_keys:
                    return False
            # 'optimistic' → always pass
        return True

    def _prereqs_satisfied(self, sq: 'Square', agent: AgentState) -> bool:
        return self._check_prereqs(sq.prereqs or [], agent)

    def _count_needed(self, sq: Square, agent: AgentState) -> int:
        """For upgrade squares (smithing/somber), count is 1 (just visit Roundtable)."""
        if sq.sq_type in ('upgrade_weapon',):
            return 1
        return sq.count_needed

    def _has_bingo(self, marks: List[bool]) -> bool:
        return any(all(marks[i] for i in line) for line in BINGO_LINES)

    def _no_bingo_possible(self) -> bool:
        """True when every bingo line has at least one mark from each player,
        making it impossible for either player to complete any line."""
        p0, p1 = self.agents[0].marks, self.agents[1].marks
        return all(
            any(p0[i] for i in line) and any(p1[i] for i in line)
            for line in BINGO_LINES
        )

    def _prereqs_ever_satisfiable(self, sq: 'Square', agent: AgentState) -> bool:
        """True if every prereq for sq can still be satisfied given current game state.

        A grace-type prereq is satisfiable if an unvisited, board-relevant entry
        exists (objective OR prereq type) that would grant that grace on visit.
        A visited-type prereq is satisfiable only if its loc_key is reachable in UNIVERSE.
        """
        for p in (sq.prereqs or []):
            res = _PREREQ_TABLE.get(p)
            if res is None:
                continue  # unknown → optimistic
            t = res.get('type', 'optimistic')
            if t == 'optimistic':
                continue
            if t == 'grace':
                grace_id = res['grace_id']
                if any(g.get('id') == grace_id for g in agent.warp_pool):
                    continue  # already obtained
                can_get = any(
                    self.relevant_mask[i]
                    and UNIVERSE[i]['type'] in ('objective', 'prereq')
                    and UNIVERSE[i]['key'] not in agent.visited_keys
                    and BOSS_GRACES.get(
                        UNIVERSE[i]['loc'].get('name', '').lower(), {}
                    ).get('id') == grace_id
                    for i in range(UNIVERSE_SIZE)
                )
                if not can_get:
                    return False
            elif t == 'any_grace':
                grace_ids = set(res.get('grace_ids', []))
                if any(g.get('id') in grace_ids for g in agent.warp_pool):
                    continue
                can_get = any(
                    self.relevant_mask[i]
                    and UNIVERSE[i]['type'] in ('objective', 'prereq')
                    and UNIVERSE[i]['key'] not in agent.visited_keys
                    and BOSS_GRACES.get(
                        UNIVERSE[i]['loc'].get('name', '').lower(), {}
                    ).get('id') in grace_ids
                    for i in range(UNIVERSE_SIZE)
                )
                if not can_get:
                    return False
            elif t == 'min_graces':
                grace_ids = set(res.get('grace_ids', []))
                needed = res.get('min', 1)
                already = sum(1 for g in agent.warp_pool if g.get('id') in grace_ids)
                if already >= needed:
                    continue
                remaining_needed = needed - already
                can_get = sum(
                    1 for i in range(UNIVERSE_SIZE)
                    if self.relevant_mask[i]
                    and UNIVERSE[i]['type'] in ('objective', 'prereq')
                    and UNIVERSE[i]['key'] not in agent.visited_keys
                    and BOSS_GRACES.get(
                        UNIVERSE[i]['loc'].get('name', '').lower(), {}
                    ).get('id') in grace_ids
                )
                if can_get < remaining_needed:
                    return False
            elif t == 'visited':
                loc_key_needed = res['loc_key']
                if loc_key_needed in agent.visited_keys:
                    continue
                if loc_key_needed not in UNIVERSE_KEY_TO_IDX:
                    return False  # prereq location not in universe → permanent lock
        return True

    def _no_markable_squares_remain(self) -> bool:
        """True when every board square is either marked by one agent or has no
        reachable locations left for either agent (accounting for permanently
        unsatisfiable prerequisites)."""
        for sq in self.board:
            if sq.is_passive:
                continue
            if any(a.marks[sq.idx] for a in self.agents):
                continue
            for a in self.agents:
                if self._is_blocked_by_opp(sq.idx, a.agent_id):
                    continue
                if sq.requires_zero_weapon and a.has_upgraded:
                    continue
                if not self._prereqs_ever_satisfiable(sq, a):
                    continue  # prereqs can never be met → treat as permanently unavailable
                visited = a.visited_keys
                unvisited = [l for l in sq.locations
                             if _loc_key(l) not in visited]
                if unvisited:
                    return False
        return True

    def _check_majority(self) -> Optional[int]:
        """Returns winning agent_id if they have 13+ marks AND no bingo is possible, else None."""
        if not self._no_bingo_possible():
            return None
        counts = [sum(a.marks) for a in self.agents]
        for i, c in enumerate(counts):
            if c >= 13:
                return i
        return None

    # ── Action mask ───────────────────────────────────────────────────────────────
    def get_action_mask(self, agent_id: int):
        """Returns boolean array of length UNIVERSE_SIZE, True = valid action."""
        import numpy as np
        agent = self.agents[agent_id]
        mask  = [False] * UNIVERSE_SIZE

        for i, entry in enumerate(UNIVERSE):
            if not self.relevant_mask[i]:
                continue
            key = entry['key']
            if key in agent.visited_keys:
                continue

            if entry['type'] == 'roundtable':
                # Valid if we have any stones to spend, or haven't collected seal
                has_stones = any(
                    v > 0 for inv in (agent.smithing_stones, agent.somber_stones)
                    for v in inv.values()
                )
                if has_stones or not agent.seal_collected:
                    mask[i] = True

            elif entry['type'] == 'stone':
                tier   = entry['stone_tier']
                somber = entry['stone_somber']
                # Only offer stones matching the agent's upgrade path
                if somber != agent.is_somber:
                    continue
                max_lv = 9 if agent.is_somber else 24
                if agent.weapon_level >= max_lv:
                    continue
                # Current and next 3 upgrade tiers (lookahead window)
                cur_tier = agent.weapon_level + 1 if somber else (agent.weapon_level // 3 + 1)
                if not (cur_tier <= tier <= cur_tier + 2):
                    continue
                # Skip if we already have 3+ of this tier (enough)
                inv = agent.somber_stones if somber else agent.smithing_stones
                if inv.get(tier, 0) >= 3:
                    continue
                mask[i] = True

            elif entry['type'] == 'objective':
                # Skip if this location's own prereqs aren't met yet (physical access gate)
                if not self._check_prereqs(entry.get('loc_prereqs', []), agent):
                    continue
                # Valid if it contributes to at least one non-marked, non-opponent-blocked square
                # whose prerequisites are satisfied (prevents wasted no-credit visits)
                for raw in entry['sq_names']:
                    sq = self.sq_by_name.get(raw)
                    if sq is None:
                        continue
                    if agent.marks[sq.idx]:
                        continue
                    if self._is_blocked_by_opp(sq.idx, agent_id):
                        continue
                    if sq.requires_zero_weapon and agent.has_upgraded:
                        continue
                    if not self._prereqs_satisfied(sq, agent):
                        continue
                    mask[i] = True
                    break

            elif entry['type'] == 'grace':
                # Offer if not already in warp_pool AND there's an unfinished boss
                # objective within 15 map units (same level) that could benefit from
                # a shorter corpse run.
                grace_id = entry.get('grace_id')
                if any(g.get('id') == grace_id for g in agent.warp_pool):
                    continue
                gx = entry['loc']['x']
                gy = entry['loc']['y']
                glv = entry['loc'].get('level', 1)
                for j, ue in enumerate(UNIVERSE):
                    if not self.relevant_mask[j]:
                        continue
                    if ue['type'] != 'objective' or not ue.get('is_boss_loc'):
                        continue
                    if ue['loc'].get('level', 1) != glv:
                        continue
                    if (ue['loc']['x'] - gx) ** 2 + (ue['loc']['y'] - gy) ** 2 > 15 ** 2:
                        continue
                    for raw in ue['sq_names']:
                        sq = self.sq_by_name.get(raw)
                        if sq and not agent.marks[sq.idx] and not self._is_blocked_by_opp(sq.idx, agent_id):
                            mask[i] = True
                            break
                    if mask[i]:
                        break

            elif entry['type'] == 'prereq':
                # Valid if any board square still needs this prereq and isn't yet done
                prereq_key = entry['prereq_key']
                for sq in self.board:
                    if prereq_key not in (sq.prereqs or []):
                        continue
                    if agent.marks[sq.idx]:
                        continue
                    if self._is_blocked_by_opp(sq.idx, agent_id):
                        continue
                    mask[i] = True
                    break

        mask_arr = np.array(mask, dtype=bool)
        # Safety: always have at least one valid action (Roundtable is last)
        if not mask_arr.any():
            mask_arr[-1] = True
        return mask_arr

    # ── Observation ───────────────────────────────────────────────────────────────
    def get_obs(self, agent_id: int):
        """Returns flat float32 numpy array of game state for agent_id.

        Layout: [self_stream (SELF_DIM)] + [opp_stream (OPP_DIM)] + [board_stream (BOARD_DIM)]
        Separable streams let the encoder give each perspective its own weights.
        """
        import numpy as np
        agent = self.agents[agent_id]
        opp   = self.agents[1 - agent_id]
        obs   = []

        # ── Self stream (63) ─────────────────────────────────────────────────────
        obs.extend(float(m) for m in agent.marks)           # 25: my marks
        for line in BINGO_LINES:                             # 12: my count per line
            obs.append(sum(agent.marks[i] for i in line) / 5.0)
        obs += [                                             # 8: agent state
            (agent.pos.get('x', -150) + 250) / 300.0,
            (agent.pos.get('y',  100) - 50)  / 200.0,
            float(agent.pos.get('level', 1) == 2),
            agent.weapon_level / 24.0,
            agent.rune_level / 150.0,
            float(agent.is_somber),
            agent.flask_level / 14.0,
            float(agent.has_upgraded),
        ]
        for tier in range(1, 9):                            # 8: smithing stones
            obs.append(min(agent.smithing_stones.get(tier, 0), 5) / 5.0)
        for tier in range(1, 10):                           # 9: somber stones
            obs.append(min(agent.somber_stones.get(tier, 0), 3) / 3.0)
        obs.append(min(agent.time / 3600.0, 2.0))           # 1: time

        # ── Opponent stream (53) ─────────────────────────────────────────────────
        obs.extend(float(m) for m in opp.marks)             # 25: opp marks
        for line in BINGO_LINES:                             # 24: opp count + danger
            mc = sum(agent.marks[i] for i in line)
            oc = sum(opp.marks[i]   for i in line)
            obs.append(oc / 5.0)
            obs.append(float(oc >= 3 and mc == 0))
        obs += [                                             # 4: opp extras
            (opp.pos.get('x', -150) + 250) / 300.0,
            (opp.pos.get('y',  100) - 50)  / 200.0,
            opp.weapon_level / 24.0,
            min(opp.time / 3600.0, 2.0),
        ]

        # ── Board stream (250 = 25 × 10) ─────────────────────────────────────────
        ax = agent.pos.get('x', -150)
        ay = agent.pos.get('y',  100)
        for sq in self.board:
            available    = not agent.marks[sq.idx] and not opp.marks[sq.idx]
            coloc        = sum(
                1 for idx in self._coloc_partners[sq.idx]
                if not agent.marks[idx] and not opp.marks[idx]
            )
            zone         = self._sq_zone[sq.idx]
            zone_density = sum(
                1 for idx in self._zone_sq.get(zone, [])
                if idx != sq.idx and not agent.marks[idx] and not opp.marks[idx]
            )
            prereq_ok = float(self._prereqs_satisfied(sq, agent))

            if sq.is_passive:
                # Passive squares need no visits — signal as already complete
                progress_ratio  = 1.0
                unvisited_ratio = 0.0
                nearest_dt      = 0.0
            else:
                n_locs         = len(sq.locations)
                progress       = len(agent.sq_progress.get(sq.idx, set()))
                needed         = self._count_needed(sq, agent)
                unvisited_locs = [
                    loc for loc in sq.locations
                    if _loc_key(loc) not in agent.visited_keys
                ]
                progress_ratio  = progress / max(needed, 1)
                unvisited_ratio = len(unvisited_locs) / max(n_locs, 1)
                # Euclidean distance to nearest unvisited PoI, normalized to ~400 unit world
                if available and unvisited_locs:
                    nearest_dt = min(
                        math.sqrt((ax - loc.get('x', ax)) ** 2 + (ay - loc.get('y', ay)) ** 2)
                        for loc in unvisited_locs
                    ) / 400.0
                    nearest_dt = min(nearest_dt, 2.0)
                else:
                    nearest_dt = 0.0  # marked or blocked — irrelevant

            obs += [
                float(agent.marks[sq.idx]),
                float(opp.marks[sq.idx]),
                float(available),
                ZONE_TIER.get(
                    sq.locations[0].get('zone', 'unknown') if sq.locations else 'unknown', 5
                ) / 10.0,
                min(coloc, 4) / 4.0,
                min(zone_density, 8) / 8.0,
                prereq_ok,
                progress_ratio,
                unvisited_ratio,
                nearest_dt,                         # distance to nearest unvisited PoI
            ]

        return np.array(obs, dtype=np.float32)

    @property
    def obs_size(self) -> int:
        return SELF_DIM + OPP_DIM + BOARD_DIM

    # ── Route export (for map visualisation) ─────────────────────────────────────
    def export_route(self, agent_id: int) -> list:
        """Export visited stops in order for map display."""
        agent = self.agents[agent_id]
        stops = []
        for key in agent.visited_keys:
            idx = UNIVERSE_KEY_TO_IDX.get(key)
            if idx is None:
                continue
            entry = UNIVERSE[idx]
            stops.append({
                'type': entry['type'],
                'name': entry['loc'].get('name', key),
                'x':    entry['loc'].get('x'),
                'y':    entry['loc'].get('y'),
                'zone': entry['loc'].get('zone'),
            })
        return stops
