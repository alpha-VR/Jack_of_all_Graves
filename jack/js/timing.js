// timing.js — Jack of All Graves (Phase 3)
// Pure functions only. No DOM, no globals, no side effects.
// Computes time estimates for each route stop.
//
// Key assumptions (S6-specific):
//   - Weapon class is randomized but maintained through pickups
//   - Starting class is fully random — no guaranteed stats
//   - Strength builds are the default assumption (most comfortable)
//   - Smithing stone cost = 1 per upgrade (S6 mod)
//   - Travel is on Torrent for open world, walking for dungeons
//   - ~60% uptime in boss fights (dodge rolling, repositioning)

const Timing = (() => {

  // ── Boss HP database (from Elden Ring NPC Data Sheet 1.05) ─────────────────
  const BOSS_HP = {
    'ancestor spirit':                          { hp:4393,  def:107, runes:13000  },
    'astel, naturalborn of the void':           { hp:11170, def:114, runes:80000  },
    'astel, stars of darkness':                 { hp:18617, def:120, runes:120000 },
    'beast clergyman':                          { hp:16461, def:120, runes:220000 },
    'maliketh, the black blade':               { hp:16461, def:120, runes:220000 },
    'bell bearing hunter':                      { hp:2495,  def:103, runes:2700   },
    'black blade kindred':                      { hp:12297, def:121, runes:88000  },
    'bloodhound knight darriwil':               { hp:1450,  def:103, runes:1900   },
    'bloodhound knight':                        { hp:1985,  def:107, runes:3600   },
    'borealis the freezing fog':                { hp:11268, def:120, runes:100000 },
    'cemetery shade':                           { hp:781,   def:102, runes:2200   },
    "commander o'neil":                         { hp:9210,  def:111, runes:12000  },
    'crucible knight':                          { hp:2782,  def:103, runes:2100   },
    'crucible knight and crucible knight ordovis':{ hp:5460, def:111, runes:28000 },
    'death rite bird':                          { hp:6577,  def:110, runes:7800   },
    'deathbird':                                { hp:3442,  def:103, runes:2800   },
    'draconic tree sentinel':                   { hp:8398,  def:114, runes:50000  },
    'dragonkin soldier':                        { hp:5758,  def:114, runes:16000  },
    'dragonlord placidusax':                    { hp:26651, def:121, runes:280000 },
    'elemer of the briar':                      { hp:4897,  def:111, runes:24000  },
    'erdtree avatar':                           { hp:3163,  def:105, runes:3600   },
    'fallingstar beast':                        { hp:5780,  def:111, runes:9300   }, // avg of locations
    "fia's champions":                          { hp:12217, def:130, runes:40000  },
    'fire giant':                               { hp:43263, def:118, runes:180000 },
    'flying dragon agheel':                     { hp:3200,  def:106, runes:5000   },
    'godfrey, first elden lord':                { hp:7099,  def:114, runes:80000  },
    'godrick the grafted':                      { hp:6080,  def:105, runes:20000  },
    'godskin apostle':                          { hp:10562, def:116, runes:54000  }, // avg
    'godskin duo':                              { hp:8000,  def:118, runes:170000 },
    'godskin noble':                            { hp:10060, def:114, runes:50000  },
    'grafted scion':                            { hp:2596,  def:107, runes:3200   },
    'leonine misbegotten':                      { hp:2199,  def:103, runes:3800   },
    'loretta, knight of the haligtree':         { hp:13397, def:122, runes:200000 },
    'magma wyrm':                               { hp:7141,  def:109, runes:15000  },
    'malenia, blade of miquella':               { hp:33251, def:123, runes:480000 },
    'margit, the fell omen':                    { hp:4174,  def:103, runes:12000  },
    'mimic tear':                               { hp:1242,  def:75,  runes:10000  },
    'misbegotten crusader':                     { hp:9130,  def:120, runes:93000  },
    'misbegotten warrior and crucible knight':  { hp:3569,  def:110, runes:16000  },
    'mohg, lord of blood':                      { hp:18389, def:122, runes:420000 },
    'mohg, the omen':                           { hp:14000, def:117, runes:100000 },
    'morgott, the omen king':                   { hp:10399, def:114, runes:120000 },
    "night's cavalry":                          { hp:1665,  def:103, runes:2400   },
    "night's cavalry duo":                      { hp:7246,  def:122, runes:84000  },
    'omenkiller':                               { hp:2306,  def:110, runes:4900   },
    'putrid crystalian trio':                   { hp:3358,  def:109, runes:7100   },
    'red wolf of radagon':                      { hp:2204,  def:107, runes:14000  },
    'regal ancestor spirit':                    { hp:6301,  def:111, runes:24000  },
    'rennala, queen of the full moon':          { hp:7590,  def:109, runes:40000  },
    'roundtable knight vyke':                   { hp:5366,  def:104, runes:75000  },
    'royal knight loretta':                     { hp:4214,  def:107, runes:10000  },
    'soldier of godrick':                       { hp:384,   def:100, runes:400    },
    'starscourge radahn':                       { hp:9572,  def:113, runes:70000  },
    'tibia mariner':                            { hp:3176,  def:103, runes:2400   },
    'tree sentinel':                            { hp:2889,  def:103, runes:3200   },
    'tree sentinel duo':                        { hp:6461,  def:113, runes:20000  },
    'valiant gargoyle duo':                     { hp:5671,  def:111, runes:30000  },
    'wormface':                                 { hp:5876,  def:113, runes:10000  },
  };

  // ── Weapon class DPS factors (MV/100 × hits_per_sec) ──────────────────────
  // Computed from Motion Values CSV + community frame data
  const WEAPON_DPS_FACTOR = {
    'Dagger':               2.23,
    'Throwing Blade':       1.42,
    'Straight Sword':       1.83,
    'Light Greatsword':     1.52,
    'Greatsword':           1.24,
    'Colossal Sword':       0.78,
    'Thrusting Sword':      2.03,
    'Heavy Thrusting Sword':1.62,
    'Curved Sword':         1.93,
    'Curved Greatsword':    1.36,
    'Backhand Blade':       2.13,
    'Katana':               1.83,
    'Great Katana':         1.24,
    'Twinblade':            2.03,
    'Axe':                  1.62,
    'Greataxe':             1.03,
    'Hammer':               1.53,
    'Flail':                1.55,
    'Great Hammer':         0.93,
    'Colossal Weapon':      0.72,
    'Spear':                1.80,
    'Great Spear':          1.24,
    'Halberd':              1.34,
    'Reaper':               1.24,
    'Whip':                 1.64,
    'Fist':                 2.44,
    'Hand-to-Hand':         1.42,
    'Claw':                 2.23,
    'Beast Claw':           2.30,
    'Glintstone Staff':     1.01,
    'Sacred Seal':          1.01,
  };

  // ── Weapon AR model ────────────────────────────────────────────────────────
  // Base AR for "average" weapons of each class at +0
  // These represent typical open-world pickup weapons
  const BASE_AR = {
    'Dagger':               110,
    'Straight Sword':       130,
    'Light Greatsword':     140,
    'Greatsword':           145,
    'Colossal Sword':       180,
    'Thrusting Sword':      125,
    'Heavy Thrusting Sword':145,
    'Curved Sword':         120,
    'Curved Greatsword':    148,
    'Backhand Blade':       115,
    'Katana':               130,
    'Great Katana':         155,
    'Twinblade':            128,
    'Axe':                  130,
    'Greataxe':             155,
    'Hammer':               130,
    'Flail':                128,
    'Great Hammer':         162,
    'Colossal Weapon':      175,
    'Spear':                120,
    'Great Spear':          155,
    'Halberd':              148,
    'Reaper':               152,
    'Whip':                 112,
    'Fist':                 95,
    'Claw':                 97,
    'Sacred Seal':          75,
    'Glintstone Staff':     80,
  };

  // Smithing upgrade AR multiplier at each level (0-24)
  // Approximated from Elden Ring upgrade curves (varies by weapon, this is a generic avg)
  const SMITHING_MULT = [
    1.000, 1.058, 1.116, 1.174, 1.232, 1.290,  // +0 to +5
    1.348, 1.406, 1.464, 1.522, 1.580,          // +6 to +10
    1.620, 1.660, 1.700, 1.740, 1.780,          // +11 to +15
    1.820, 1.860, 1.900, 1.940, 1.980,          // +16 to +20
    2.020, 2.060, 2.100, 2.140,                  // +21 to +24
  ];

  // Somber upgrade AR multiplier at each level (0-9)
  const SOMBER_MULT = [
    1.000, 1.125, 1.250, 1.375, 1.500,
    1.625, 1.750, 1.875, 2.000, 2.125,
  ];

  // Stat scaling bonus as fraction of base AR
  // Assumes "comfortable strength build" — ~30 Str by mid-game
  // stat_level: 'early'(1-30), 'mid'(31-60), 'late'(61+)
  const STAT_SCALING = {
    Strength: { early: 0.25, mid: 0.50, late: 0.80 },
    Dexterity:{ early: 0.20, mid: 0.45, late: 0.70 },
    Faith:    { early: 0.15, mid: 0.35, late: 0.60 },
    Int:      { early: 0.15, mid: 0.35, late: 0.60 },
    Quality:  { early: 0.22, mid: 0.47, late: 0.70 },
  };

  // ── Travel speed calibration ───────────────────────────────────────────────
  // Based on: Gatefront → Margit fog gate ≈ 75s on Torrent (well-known benchmark)
  // Coord distance Gatefront→Margit ≈ 9 units → 1 unit ≈ 8.3s on Torrent
  // Zone multipliers account for terrain (open field vs winding paths vs dungeons)
  const TRAVEL_SEC_PER_UNIT = 8.3;
  const ZONE_SPEED_MULT = {
    limgrave:          1.0,
    weeping_peninsula: 1.1,
    stormveil:         2.5,  // castle interior, walking
    siofra:            2.0,  // underground, no Torrent
    liurnia:           1.1,
    caria_manor:       2.2,
    caelid:            1.1,
    dragonbarrow:      1.0,
    altus_plateau:     1.0,
    mt_gelmir:         1.4,
    volcano_manor:     2.5,
    leyndell:          1.8,
    deeproot:          2.2,
    ainsel:            2.0,
    mohgwyn:           2.0,
    mountaintops:      1.1,
    consecrated:       1.1,
    haligtree:         2.8,
    farum_azula:       2.5,
    unknown:           1.3,
  };

  // ── Dungeon traversal overhead (seconds) ──────────────────────────────────
  const DUNGEON_OVERHEAD = {
    catacombs:   240,  // ~4 min
    cave:        180,  // ~3 min
    tunnel:      180,  // ~3 min
    evergaol:    120,  // ~2 min
    hero_grave:  360,  // ~6 min
    dungeon:     200,  // generic fallback
  };

  // ── Fixed overhead per stop ────────────────────────────────────────────────
  const OVERHEAD_GRACE_SEC   = 10;   // opening map, resting, loading
  const OVERHEAD_BOSS_SEC    = 25;   // fog gate load + boss death animation
  const OVERHEAD_DUNGEON_SEC = 40;   // dungeon load in + load out

  // Baseline attack uptime for an average-difficulty boss.
  // Divided by BOSS_DIFFICULTY to get per-boss effective uptime.
  const BOSS_UPTIME = 0.60;

  // Per-boss difficulty: how many safe attack windows the boss gives.
  // effective_uptime = BOSS_UPTIME / difficulty
  const BOSS_DIFFICULTY = {
    // Very easy
    'soldier of godrick':                          0.6,
    'tibia mariner':                               0.7,
    'guardian golem':                              0.7,
    'spiritcaller snail':                          0.7,
    'erdtree burial watchdog':                     0.8,
    'cemetery shade':                              0.8,
    'stonedigger troll':                           0.8,
    'mad pumpkin head':                            0.8,
    'beastman of farum azula':                     0.8,
    'grafted scion':                               0.9,
    'ancestor spirit':                             0.9,
    'regal ancestor spirit':                       0.9,
    'erdtree avatar':                              0.9,
    'mimic tear':                                  0.9,
    // Easy
    'rennala, queen of the full moon':             1.0,
    'godrick the grafted':                         1.1,
    'leonine misbegotten':                         1.0,
    'runebear':                                    1.1,
    'omenkiller':                                  1.1,
    'royal revenant':                              1.1,
    'wormface':                                    1.1,
    'demi-human queen':                            1.1,
    'sanguine noble':                              1.1,
    'frenzied duelist':                            1.1,
    "bols, carian knight":                         1.1,
    'grave warden duelist':                        1.0,
    'putrid grave warden duelist':                 1.1,
    'black knife assassin':                        1.2,
    'cleanrot knight':                             1.2,
    'deathbird':                                   1.2,
    'onyx lord':                                   1.2,
    "commander o'neil":                            1.2,
    'magma wyrm':                                  1.2,
    'flying dragon agheel':                        1.2,
    'glintstone dragon smarag':                    1.2,
    'rykard, lord of blasphemy':                   1.2,
    'god-devouring serpent':                       1.2,
    'dragonkin soldier':                           1.2,
    'dragonkin soldier of nokstella':              1.2,
    'godefroy the grafted':                        1.2,
    // Medium
    'margit, the fell omen':                       1.5,
    'red wolf of radagon':                         1.3,
    'red wolf of the champion':                    1.4,
    'fallingstar beast':                           1.3,
    "night's cavalry":                             1.3,
    'death rite bird':                             1.4,
    'battlemage hugues':                           1.3,
    'ulcerated tree spirit':                       1.3,
    'putrid avatar':                               1.3,
    'ancient hero of zamor':                       1.3,
    'dragonkin soldier (lake of rot)':             1.3,
    'magma wyrm makar':                            1.3,
    'tree sentinel':                               1.4,
    'full-grown fallingstar beast':                1.5,
    'elemer of the briar':                         1.5,
    'borealis the freezing fog':                   1.5,
    'godskin noble':                               1.5,
    'putrid tree spirit':                          1.5,
    'ancient dragon lansseax':                     1.4,
    'glintstone dragon adula':                     1.4,
    'flying dragon greyll':                        1.3,
    'decaying ekzykes':                            1.3,
    'great wyrm theodorix':                        1.5,
    'lichdragon fortissax':                        1.4,
    'dragonlord placidusax':                       1.4,
    'astel, naturalborn of the void':              1.5,
    'astel, stars of darkness':                    1.6,
    // Hard-medium
    'crucible knight':                             1.8,
    'crucible knight and crucible knight ordovis': 2.0,
    'crucible knight siluria':                     1.8,
    'bloodhound knight darriwil':                  1.7,
    'bloodhound knight':                           1.6,
    'black blade kindred':                         1.8,
    'black blade kindred (forbidden lands)':       1.9,
    "night's cavalry duo":                         1.7,
    'night cavalry (forbidden lands)':             1.6,
    'misbegotten warrior and crucible knight':     1.8,
    'misbegotten crusader':                        1.7,
    'godskin apostle':                             1.6,
    'draconic tree sentinel':                      1.7,
    'royal knight loretta':                        1.5,
    'loretta, knight of the haligtree':            1.8,
    'godfrey, first elden lord':                   1.8,
    'fell twins':                                  1.7,
    'bell bearing hunter':                         1.7,
    'roundtable knight vyke':                      1.9,
    'tree sentinel duo':                           1.8,
    'starscourge radahn':                          1.7,
    "fia's champions":                             2.0,
    'fire giant':                                  1.8,
    'mohg, the omen':                              1.7,
    // Hard
    'morgott, the omen king':                      2.0,
    'godskin duo':                                 2.1,
    'commander niall':                             2.0,
    'alecto, black knife ringleader':              2.0,
    'godfrey (ashen capital)':                     2.0,
    'mohg, lord of blood':                         2.1,
    'beast clergyman':                             2.2,
    'maliketh, the black blade':                   2.2,
    // Very hard
    'malenia, blade of miquella':                  3.0,
  };

  // Flat extra seconds for phase transitions, cutscenes, and repositioning.
  const BOSS_PHASE_OVERHEAD = {
    'godrick the grafted':               20,
    'rennala, queen of the full moon':   35,
    'starscourge radahn':                15,
    'morgott, the omen king':            10,
    'fire giant':                        20,
    'beast clergyman':                   10,
    'maliketh, the black blade':         10,
    'malenia, blade of miquella':        20,
    'mohg, lord of blood':               35,
    'godskin duo':                       20,
    'dragonlord placidusax':             10,
    'astel, naturalborn of the void':    10,
    'astel, stars of darkness':          10,
  };

  // ── Rune level formula ─────────────────────────────────────────────────────
  function runesForLevel(level) {
    if (level < 12)  return Math.floor(673 * Math.pow(1.04, level));
    if (level < 92)  return Math.floor(0.02 * Math.pow(level, 3) + 3.06 * Math.pow(level, 2) + 105.6 * level - 895);
    return Math.floor(0.1 * Math.pow(level, 3) - 16 * Math.pow(level, 2) + 2010 * level - 60000);
  }

  function totalRunesForLevel(target, start = 1) {
    let total = 0;
    for (let l = start; l < target; l++) total += runesForLevel(l);
    return total;
  }

  // ── Smithing rune costs ────────────────────────────────────────────────────
  const SMITHING_RUNE_COST = [
    0, 200, 400, 600, 900, 1200, 1500, 2000, 2500, 3000,
    3500, 4000, 5000, 6000, 7000, 8000, 9000, 10000, 11000, 12000,
    13000, 14000, 15000, 16000, 17000,
  ];
  const SOMBER_RUNE_COST = [
    0, 200, 400, 700, 1000, 1400, 1800, 2300, 2800, 3500,
  ];

  // ── Core: compute weapon AR at a given level and build ────────────────────
  function computeAR(weaponClass, weaponLevel, isSomber, primaryStat, runeLevel) {
    const base    = BASE_AR[weaponClass] || 130;
    const mult    = isSomber
      ? (SOMBER_MULT[Math.min(weaponLevel, 9)] || 1)
      : (SMITHING_MULT[Math.min(weaponLevel, 24)] || 1);
    const baseUpgraded = base * mult;

    // Stat scaling — estimate based on rune level
    const statTier = runeLevel < 30 ? 'early' : runeLevel < 60 ? 'mid' : 'late';
    const scaling  = (STAT_SCALING[primaryStat] || STAT_SCALING.Strength)[statTier];
    const statBonus= base * scaling; // scaling applies to base, not upgraded

    return Math.round(baseUpgraded + statBonus);
  }

  // ── Core: compute boss kill time ──────────────────────────────────────────
  // Three factors beyond raw DPS:
  //   1. Boss difficulty  — harder bosses give fewer safe attack windows
  //   2. Phase overhead   — cutscenes / repositioning between phases
  //   3. +0 struggle      — low weapon = cautious play; ~2× longer at +0
  function computeKillTime(bossName, weaponClass, weaponLevel, isSomber, primaryStat, runeLevel) {
    let key = bossName.toLowerCase().trim();
    let bossData = BOSS_HP[key];
    if (!bossData) {
      for (const [k, v] of Object.entries(BOSS_HP)) {
        if (key.includes(k) || k.includes(key.split('(')[0].trim())) {
          bossData = v; key = k; break;
        }
      }
    }
    if (!bossData) return null;

    const ar        = computeAR(weaponClass, weaponLevel, isSomber, primaryStat, runeLevel);
    const dpsFactor = WEAPON_DPS_FACTOR[weaponClass] || 1.4;
    const hps       = dpsFactor / 1.032;
    const dmgPerHit = (ar * ar) / (ar + bossData.def);

    const difficulty      = BOSS_DIFFICULTY[key] ?? 1.3;
    const effectiveUptime = BOSS_UPTIME / difficulty;
    const effectiveDPS    = dmgPerHit * hps * effectiveUptime;

    const baseKillSec   = Math.ceil(bossData.hp / effectiveDPS);
    const phaseOverhead = BOSS_PHASE_OVERHEAD[key] ?? 0;

    // Underleveled struggle: quadratic penalty, 2× longer at +0, 1× at max level
    const maxLv       = isSomber ? 9 : 24;
    const progress    = weaponLevel / maxLv;
    const struggleMult = 1.0 + 1.0 * Math.pow(1.0 - progress, 2);

    const killSec = Math.ceil((baseKillSec + phaseOverhead) * struggleMult);
    return { killSec, hp: bossData.hp, ar, effectiveDPS: Math.round(effectiveDPS), difficulty };
  }

  // ── Core: compute travel time ─────────────────────────────────────────────
  function computeTravelTime(travelDistance, zoneId) {
    const speedMult = ZONE_SPEED_MULT[zoneId] || 1.3;
    return Math.ceil(travelDistance * TRAVEL_SEC_PER_UNIT * speedMult);
  }

  // ── Dungeon overhead ──────────────────────────────────────────────────────
  function getDungeonOverhead(stopType) {
    if (!stopType) return 0;
    const t = stopType.toLowerCase();
    if (t.includes('catacomb'))       return DUNGEON_OVERHEAD.catacombs;
    if (t.includes('cave') || t.includes('grotto')) return DUNGEON_OVERHEAD.cave;
    if (t.includes('tunnel') || t.includes('precipice')) return DUNGEON_OVERHEAD.tunnel;
    if (t.includes('evergaol'))       return DUNGEON_OVERHEAD.evergaol;
    if (t.includes('hero'))           return DUNGEON_OVERHEAD.hero_grave;
    if (t.includes('dungeon'))        return DUNGEON_OVERHEAD.dungeon;
    return 0;
  }

  // ── Main: estimate time for a single stop ─────────────────────────────────
  // Returns { killSec, travelSec, overheadSec, totalSec, label, confidence }
  function estimateStop(stop, build) {
    const { weaponClass, weaponLevel, isSomber, primaryStat, runeLevel } = build;
    const isBoss    = ['boss_specific','boss_any','boss_count','boss_tag',
                       'boss_region','boss_modifier','boss_multi_type',
                       'boss_multi_specific','prereq'].includes(stop.type);
    const isDungeon = ['dungeon_count','dungeon_specific'].includes(stop.type);
    const isPickup  = ['acquire_multi','acquire_count','acquire_fixed',
                       'npc_action','npc_invasion','restore_rune'].includes(stop.type);
    const isStart   = stop.rawName === '_start';

    if (isStart) return { killSec:0, travelSec:0, overheadSec:0, totalSec:0, label:'Start' };

    // Travel time
    const travelDist = stop.warpFrom && stop.location
      ? Math.sqrt((stop.warpFrom.x - stop.location.x)**2 + (stop.warpFrom.y - stop.location.y)**2)
      : 0;
    const travelSec = computeTravelTime(travelDist, stop.zoneId);

    // Kill time
    let killSec = 0;
    let killData = null;
    if (isBoss && stop.location?.name) {
      killData = computeKillTime(
        stop.location.name, weaponClass, weaponLevel,
        isSomber, primaryStat, runeLevel
      );
      killSec = killData?.killSec || estimateFallbackKillTime(stop);
    }

    // Overhead
    let overheadSec = OVERHEAD_GRACE_SEC;
    if (isBoss)    overheadSec += OVERHEAD_BOSS_SEC;
    if (isDungeon) overheadSec += OVERHEAD_DUNGEON_SEC + getDungeonOverhead(stop.squareName);
    if (isPickup)  overheadSec += 30; // walk to item, pick up

    const totalSec = travelSec + killSec + overheadSec;

    // Confidence: lower if we couldn't find boss data
    const confidence = killData ? 'medium' : (isBoss ? 'low' : 'high');

    return {
      killSec, travelSec, overheadSec, totalSec,
      ar: killData?.ar,
      effectiveDPS: killData?.effectiveDPS,
      confidence,
      label: formatTime(totalSec),
    };
  }

  // Fallback kill time when boss not in DB — based on zone tier
  function estimateFallbackKillTime(stop) {
    const tier = {
      limgrave:0, weeping_peninsula:0, stormveil:1, liurnia:1,
      caelid:2, altus_plateau:2, leyndell:3, mountaintops:3,
      haligtree:4, farum_azula:4,
    }[stop.zoneId] ?? 2;
    return [30, 60, 120, 180, 240][tier] || 90;
  }

  // ── Weapon upgrade tracker ────────────────────────────────────────────────
  // Given rune income up to this point and weapon level,
  // returns the weapon level the player would realistically have
  function computeWeaponLevelFromRunes(runeBalance, isSomber) {
    const costs = isSomber ? SOMBER_RUNE_COST : SMITHING_RUNE_COST;
    const maxLevel = isSomber ? 9 : 24;
    let level = 0;
    let spent = 0;
    while (level < maxLevel) {
      const cost = costs[level + 1] || Infinity;
      if (spent + cost > runeBalance) break;
      spent += cost;
      level++;
    }
    return level;
  }

  // ── Rune level tracker ────────────────────────────────────────────────────
  // Given total runes earned, what rune level are you approximately?
  function computeRuneLevel(totalRunes, startLevel = 1) {
    let level = startLevel;
    let remaining = totalRunes;
    while (remaining > 0 && level < 150) {
      const cost = runesForLevel(level);
      if (remaining < cost) break;
      remaining -= cost;
      level++;
    }
    return level;
  }

  // ── Process full route ────────────────────────────────────────────────────
  // Annotates each stop with timing data.
  // Tracks weapon level progression through the route.
  // Returns annotated stops + summary.
  function processRoute(stops, buildConfig) {
    const build = {
      weaponClass:  buildConfig.weaponClass  || 'Greatsword',
      weaponLevel:  buildConfig.weaponLevel  ?? 0,
      isSomber:     buildConfig.isSomber     ?? false,
      primaryStat:  buildConfig.primaryStat  || 'Strength',
      runeLevel:    buildConfig.runeLevel    ?? 1,
      // Track dynamically through route
      currentWeaponLevel: buildConfig.weaponLevel ?? 0,
      currentRuneLevel:   buildConfig.runeLevel ?? 1,
      currentRuneBalance: 0,
    };

    let runningTotal = 0;
    const annotated  = [];

    for (const stop of stops) {
      // Update rune balance from this stop
      const runesGained = stop.runes || 0;
      build.currentRuneBalance += runesGained;

      // Update rune level
      const totalRunesEarned = stops
        .slice(0, stops.indexOf(stop) + 1)
        .reduce((s, st) => s + (st.runes || 0), 0);
      build.currentRuneLevel = computeRuneLevel(totalRunesEarned, 1);

      // Update weapon level based on rune income
      // (Player upgrades opportunistically — whenever they have runes)
      const estimatedWL = computeWeaponLevelFromRunes(
        build.currentRuneBalance, build.isSomber
      );
      build.currentWeaponLevel = Math.max(build.currentWeaponLevel, estimatedWL);

      // Compute timing with current build state
      const timing = estimateStop(stop, {
        weaponClass:  build.weaponClass,
        weaponLevel:  build.currentWeaponLevel,
        isSomber:     build.isSomber,
        primaryStat:  build.primaryStat,
        runeLevel:    build.currentRuneLevel,
      });

      runningTotal += timing.totalSec;

      annotated.push({
        ...stop,
        timing: {
          ...timing,
          runningTotal,
          runningLabel:   formatTime(runningTotal),
          weaponLevel:    build.currentWeaponLevel,
          runeLevel:      build.currentRuneLevel,
        },
      });
    }

    const totalMin = Math.round(runningTotal / 60);
    return {
      stops: annotated,
      totalSec: runningTotal,
      totalLabel: formatTime(runningTotal),
      totalMin,
    };
  }

  // ── Format helpers ────────────────────────────────────────────────────────
  function formatTime(sec) {
    if (!sec || sec <= 0) return '';
    const m = Math.floor(sec / 60);
    const s = Math.round(sec % 60);
    if (m === 0) return `~${s}s`;
    if (s === 0) return `~${m}m`;
    return `~${m}m ${s}s`;
  }

  function formatRunning(sec) {
    const m = Math.floor(sec / 60);
    const s = Math.round(sec % 60);
    return `${m}:${String(s).padStart(2,'0')} in`;
  }

  // ── Default build (no weapon found yet) ───────────────────────────────────
  const DEFAULT_BUILD = {
    weaponClass: 'Greatsword',
    weaponLevel: 0,
    isSomber:    false,
    primaryStat: 'Strength',
    runeLevel:   1,
  };

  // ── Public API ────────────────────────────────────────────────────────────
  return {
    processRoute,
    estimateStop,
    computeKillTime,
    computeAR,
    computeWeaponLevelFromRunes,
    computeRuneLevel,
    formatTime,
    formatRunning,
    DEFAULT_BUILD,
    WEAPON_DPS_FACTOR,
    BASE_AR,
    BOSS_HP,
  };
})();