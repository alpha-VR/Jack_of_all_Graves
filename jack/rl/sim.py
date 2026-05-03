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
    compute_death_probability, get_boss_difficulty,
    max_upgrade_level, stones_needed, dungeon_overhead, BINGO_LINES, N_SQUARES,
    PREREQ_LOCS,
)
from .board import Square, UNIVERSE, UNIVERSE_SIZE, UNIVERSE_KEY_TO_IDX, _loc_key


# Prereq keys → the universe locKey that satisfies them when visited.
# Keys matching 'nokron_access'/'radahn'/boss kills use warp_pool (boss grace added
# on kill); these keys use visited_keys instead.
_PREREQ_VISITED: dict = {
    'capital_access':  '-936_1202_1',   # Draconic Tree Sentinel, leyndell entrance
    'Kill Fell Twins': '-1040_1321_1',  # Fell Twins, mountaintops
    'kill_loretta':    '-1046_568_1',   # Royal Knight Loretta, Caria Manor
    **{ploc['prereq_key']: _loc_key(ploc) for ploc in PREREQ_LOCS},
}


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
            rune_level=1,
            total_runes_earned=0,
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
        runes_gained = 0
        sq_completed = []
        stone_reward   = 0.0
        upgrade_reward = 0.0
        death_penalty  = 0.0

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
            # Reward useful stone pickups; tier closest to current need scores highest
            cur_tier = (agent.weapon_level + 1) if somber else (agent.weapon_level // 3 + 1)
            usefulness = max(0.0, 1.0 - abs(tier - cur_tier) * 0.25)
            proximity_bonus = 0.015 if self._stone_near_obj[action_idx] else 0.0
            stone_reward = 0.04 * max(usefulness, 0.1) + proximity_bonus

        elif entry['type'] == 'objective':
            # Determine which board squares this location contributes to
            relevant_squares = [
                sq for sq in self.board
                if sq.raw_name in entry['sq_names']
                and not agent.marks[sq.idx]
                and not self._is_blocked_by_opp(sq.idx, agent_id)
                and not (sq.requires_zero_weapon and agent.has_upgraded)
                and self._prereqs_satisfied(sq, agent)
            ]
            if not relevant_squares:
                # Location visited but no benefit — still costs travel time
                pass
            else:
                for sq in relevant_squares:
                    progress = agent.sq_progress.setdefault(sq.idx, set())
                    progress.add(key)
                    needed = self._count_needed(sq, agent)
                    if len(progress) >= needed:
                        # Square complete!
                        agent.marks[sq.idx] = True
                        sq_completed.append(sq.idx)
                        runes_gained += sq.runes_on_complete

            # Boss kill: compute time + runes + unlock grace
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
                    kill_sec      = kill_result['kill_sec']
                    runes_gained += kill_result['runes']
                    overhead      = OVERHEAD_BOSS_SEC + kill_sec
                    # Stochastic variance (±15%)
                    overhead = int(overhead * self.rng.uniform(0.85, 1.15))
                else:
                    overhead += OVERHEAD_BOSS_SEC
                # Unlock boss grace
                bg = BOSS_GRACES.get(boss_name)
                if bg and not any(g.get('id') == bg['id'] for g in agent.warp_pool):
                    agent.warp_pool.append(dict(bg))
                # Death probability: underleveled agents lose runes and spend recovery time.
                # Death overhead scales with boss difficulty — hard boss = longer corpse run.
                p_death = compute_death_probability(
                    loc.get('zone', 'unknown'), agent.weapon_level, agent.is_somber
                )
                if p_death > 0:
                    difficulty   = get_boss_difficulty(loc.get('name', ''))
                    death_time   = int(120 + 60 * math.sqrt(difficulty))
                    if self.rng.random() < p_death:
                        agent.rune_balance = 0
                        agent.time += death_time
                        death_penalty = 0.20
                    else:
                        death_penalty = p_death * 0.05
            else:
                # Pickup / NPC / dungeon overhead — use per-type cost where available
                sq_type = (relevant_squares[0].sq_type if relevant_squares else '')
                if 'dungeon' in sq_type:
                    overhead += OVERHEAD_DUNGEON_SEC + dungeon_overhead(
                        relevant_squares[0].text if relevant_squares else ''
                    )
                else:
                    overhead += SQUARE_ACTION_SEC.get(sq_type, OVERHEAD_PICKUP_SEC)

            agent.visited_keys.add(key)
            agent.pos = dict(loc)
            # Unlock this location as a warp point if it's a named grace
            if loc.get('name') and not any(
                abs(g.get('x',0)-loc['x'])<0.5 for g in agent.warp_pool
            ):
                agent.warp_pool.append(dict(loc))

        elif entry['type'] == 'prereq':
            # Prerequisite-only stop: pay travel + pickup overhead, no square credit
            overhead = OVERHEAD_PICKUP_SEC
            agent.visited_keys.add(key)
            agent.pos = dict(loc)
            if loc.get('name') and not any(
                abs(g.get('x', 0) - loc['x']) < 0.5 for g in agent.warp_pool
            ):
                agent.warp_pool.append(dict(loc))

        agent.time += overhead

        # ── Update rune economy ──────────────────────────────────────────────────
        if runes_gained:
            agent.total_runes_earned += runes_gained
            agent.rune_balance       += runes_gained
            agent.rune_level = compute_rune_level(agent.total_runes_earned)

        # ── Reward shaping ───────────────────────────────────────────────────────
        reward = 0.0
        reward += 0.1  * len(sq_completed)   # per-square bonus
        reward -= travel_sec * 0.0001         # time penalty
        reward += stone_reward               # incentivise useful stone pickups
        reward += upgrade_reward             # reward weapon level gains at Roundtable
        reward -= death_penalty              # penalise fighting underleveled

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

    def _prereqs_satisfied(self, sq: 'Square', agent: AgentState) -> bool:
        """Return True if all prerequisites for this square are met by the agent."""
        for p in (sq.prereqs or []):
            if p in ('nokron_access', 'radahn', 'Kill Starscourge Radahn'):
                if not any(g.get('id') == 'bg_radahn' for g in agent.warp_pool):
                    return False
            elif p == 'mohgwyn_access':
                if not any(g.get('id') == 'bg_mohg' for g in agent.warp_pool):
                    return False
            elif p == 'Kill Godrick the Grafted':
                if not any(g.get('id') == 'bg_godrick' for g in agent.warp_pool):
                    return False
            elif p == 'Kill Morgott, The Omen King':
                if not any(g.get('id') == 'bg_morgott' for g in agent.warp_pool):
                    return False
            elif p == 'Kill Rykard, Lord of Blasphemy':
                if not any(g.get('id') == 'bg_rykard' for g in agent.warp_pool):
                    return False
            elif p in _PREREQ_VISITED:
                if _PREREQ_VISITED[p] not in agent.visited_keys:
                    return False
            # Truly unknown prereqs: optimistically allow
        return True

    def _count_needed(self, sq: Square, agent: AgentState) -> int:
        """For upgrade squares (smithing/somber), count is 1 (just visit Roundtable)."""
        if sq.sq_type in ('upgrade_weapon',):
            return 1
        return sq.count_needed

    def _has_bingo(self, marks: List[bool]) -> bool:
        return any(all(marks[i] for i in line) for line in BINGO_LINES)

    def _no_markable_squares_remain(self) -> bool:
        """True when every board square is either marked by one agent or has no
        reachable locations left for either agent."""
        for sq in self.board:
            if sq.is_passive:
                continue
            if any(a.marks[sq.idx] for a in self.agents):
                continue
            # Square still available — check if any agent could still mark it
            for a in self.agents:
                if self._is_blocked_by_opp(sq.idx, a.agent_id):
                    continue
                if sq.requires_zero_weapon and a.has_upgraded:
                    continue
                visited = a.visited_keys
                unvisited = [l for l in sq.locations
                             if _loc_key(l) not in visited]
                if unvisited:
                    return False   # at least one agent can still work on this
        return True

    def _check_majority(self) -> Optional[int]:
        """Returns winning agent_id if majority achieved, else None."""
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
                # Valid if it contributes to at least one non-blocked, non-marked square
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
                    mask[i] = True
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
        """Returns flat float32 numpy array of game state for agent_id."""
        import numpy as np
        agent = self.agents[agent_id]
        opp   = self.agents[1 - agent_id]

        # Board marks: 25 mine + 25 opp
        obs = list(agent.marks) + list(opp.marks)

        # Line progress: for each of 12 lines, (my_count/5, opp_count/5,
        #                                        opp_danger 0/1)
        for line in BINGO_LINES:
            mc = sum(agent.marks[i] for i in line)
            oc = sum(opp.marks[i]   for i in line)
            obs += [mc / 5.0, oc / 5.0, float(oc >= 3 and mc == 0)]

        # Agent state (normalised)
        obs += [
            (agent.pos.get('x', -150) + 250) / 300.0,
            (agent.pos.get('y',  100) - 50)  / 200.0,
            float(agent.pos.get('level', 1) == 2),
            agent.weapon_level / 24.0,
            agent.rune_level / 150.0,
            float(agent.is_somber),
            agent.flask_level / 14.0,
            float(agent.has_upgraded),
        ]

        # Stone inventory (smithing tiers 1-8, somber tiers 1-9)
        for tier in range(1, 9):
            obs.append(min(agent.smithing_stones.get(tier, 0), 5) / 5.0)
        for tier in range(1, 10):
            obs.append(min(agent.somber_stones.get(tier, 0), 3) / 3.0)

        # Time (normalised to 3600s)
        obs.append(min(agent.time / 3600.0, 2.0))

        # Square-level features (25 squares × 7 features)
        for sq in self.board:
            available = not agent.marks[sq.idx] and not opp.marks[sq.idx]
            # Co-location: other open squares sharing a visit location with this one
            coloc = sum(
                1 for idx in self._coloc_partners[sq.idx]
                if not agent.marks[idx] and not opp.marks[idx]
            )
            # Zone density: other open squares in same primary zone
            zone = self._sq_zone[sq.idx]
            zone_density = sum(
                1 for idx in self._zone_sq.get(zone, [])
                if idx != sq.idx and not agent.marks[idx] and not opp.marks[idx]
            )
            prereq_ok = float(self._prereqs_satisfied(sq, agent))
            obs += [
                float(agent.marks[sq.idx]),
                float(opp.marks[sq.idx]),
                float(available),
                ZONE_TIER.get(sq.locations[0].get('zone', 'unknown') if sq.locations else 'unknown', 5) / 10.0,
                min(coloc, 4) / 4.0,          # co-location synergy (capped at 4)
                min(zone_density, 8) / 8.0,   # zone cluster density (capped at 8)
                prereq_ok,                    # prereq gate: 1.0 = reachable now
            ]

        return np.array(obs, dtype=np.float32)

    @property
    def obs_size(self) -> int:
        # 50 (marks) + 36 (line × 3) + 8 (state) + 17 (stones) + 1 (time) + 175 (squares × 7)
        return 50 + 12 * 3 + 8 + 17 + 1 + N_SQUARES * 7

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
