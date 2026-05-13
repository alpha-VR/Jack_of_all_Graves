// router.js — Jack of All Graves  (Phase 2)
// Key upgrades over Phase 1:
//   1. Evaluates all 12 bingo lines, routes the cheapest completable one
//   2. Count-square clustering — picks N geographically closest candidates
//   3. Prerequisite chain insertion — Radahn/capital stops added automatically
//   4. Recompute on mark — adapts to completed/blocked squares
//   5. Available-now list — squares reachable with current warp pool

const Router = (() => {

  // ── Zone data ──────────────────────────────────────────────────────────────
  const ZONE_TIER = {
    limgrave:0, weeping_peninsula:1, stormveil:1, siofra:2,
    liurnia:3, caria_manor:4, caelid:4, dragonbarrow:5,
    altus_plateau:5, mt_gelmir:6, volcano_manor:6,
    leyndell:7, deeproot:7, ainsel:7,
    mohgwyn:8, mountaintops:8, consecrated:9,
    haligtree:10, farum_azula:10, unknown:5,
  };

  const ZONE_PENALTY = {
    limgrave:0, weeping_peninsula:0.05, stormveil:0.05, siofra:0.15,
    liurnia:0.15, caria_manor:0.2, caelid:0.2, dragonbarrow:0.25,
    altus_plateau:0.3, mt_gelmir:0.35, volcano_manor:0.35,
    leyndell:0.45, deeproot:0.45, ainsel:0.4,
    mohgwyn:0.55, mountaintops:0.6, consecrated:0.65,
    haligtree:0.7, farum_azula:0.75, unknown:0.3,
  };

  const ZONE_LABEL = {
    limgrave:'Limgrave', weeping_peninsula:'Weeping Peninsula',
    stormveil:'Stormveil Castle', liurnia:'Liurnia of the Lakes',
    caria_manor:'Caria Manor', caelid:'Caelid', dragonbarrow:'Dragonbarrow',
    altus_plateau:'Altus Plateau', mt_gelmir:'Mt. Gelmir',
    volcano_manor:'Volcano Manor', leyndell:'Leyndell, Royal Capital',
    deeproot:'Deeproot Depths', siofra:'Siofra River / Nokron',
    ainsel:'Ainsel River / Lake of Rot', mohgwyn:'Mohgwyn Palace',
    mountaintops:'Mountaintops of the Giants', consecrated:'Consecrated Snowfield',
    haligtree:'Haligtree', farum_azula:'Crumbling Farum Azula', unknown:'Unknown',
  };

  const LINE_NAMES = [
    'Row 1','Row 2','Row 3','Row 4','Row 5',
    'Col 1','Col 2','Col 3','Col 4','Col 5',
    'Diag ↘','Diag ↗',
  ];

  // ── S6 starting graces ─────────────────────────────────────────────────────
  const S6_GRACES = [
    { id:'sg_gatefront',   name:'Gatefront Ruins',             x:-185.78, y:102.10, level:1 },
    { id:'sg_consecrated', name:'Inner Consecrated Snowfield', x: -73.56, y:141.78, level:1 },
    { id:'sg_haligtree',   name:'Haligtree Roots',             x: -37.10, y:149.13, level:1 },
    { id:'sg_snow_valley', name:'Snow Valley Ruins Overlook',  x: -64.63, y:159.69, level:1 },
    { id:'sg_aeonia',      name:'Inner Aeonia',                x:-178.97, y:143.06, level:1 },
    { id:'sg_ailing',      name:'Ailing Village Outskirts',    x:-211.27, y:112.20, level:1 },
    { id:'sg_scenic',      name:'Scenic Isle',                 x:-156.20, y: 67.88, level:1 },
    { id:'sg_labyrinth',   name:'Ruined Labyrinth',            x:-125.59, y: 73.51, level:1 },
    { id:'sg_altus_hwy',   name:'Altus Highway Junction',      x:-100.79, y: 84.93, level:1 },
    { id:'sg_iniquity',    name:'Road of Iniquity',            x: -84.37, y: 63.22, level:1 },
    { id:'sg_lake_rot',    name:'Lake of Rot Shoreside',       x:-128.46, y: 60.20, level:2 },
    { id:'sg_siofra',      name:'Siofra River Bank',           x:-184.90, y:130.58, level:2 },
    { id:'sg_roundtable',  name:'Roundtable Hold',             x:-160.00, y: 90.00, level:1, is_roundtable:true },
  ];

  // Boss arena graces — unlocked after killing the boss
  const BOSS_GRACES = {
    'margit, the fell omen':           { id:'bg_margit',      x:-183.33, y: 93.85, level:1, name:'Castleward Tunnel' },
    'godrick the grafted':             { id:'bg_godrick',     x:-174.50, y: 86.20, level:1, name:'Godrick the Grafted' },
    'rennala, queen of the full moon': { id:'bg_rennala',     x:-135.42, y: 56.11, level:1, name:'Raya Lucaria Grand Library' },
    'starscourge radahn':              { id:'bg_radahn',      x:-194.36, y:160.21, level:1, name:'Starscourge Radahn' },
    'morgott, the omen king':          { id:'bg_morgott',     x:-107.64, y:120.62, level:1, name:'Morgott, the Omen King' },
    'rykard, lord of blasphemy':       { id:'bg_rykard',      x: -87.22, y: 66.70, level:1, name:'Rykard, Lord of Blasphemy' },
    'malenia, blade of miquella':      { id:'bg_malenia',     x: -38.12, y:146.39, level:1, name:'Malenia, Goddess of Rot' },
    'fire giant':                      { id:'bg_fire_giant',  x: -92.34, y:163.88, level:1, name:'Fire Giant' },
    'mohg, lord of blood':             { id:'bg_mohg',        x:-182.32, y:146.50, level:2, name:'Mohg, Lord of Blood' },
    'maliketh, the black blade':       { id:'bg_maliketh',    x:-125.10, y:221.00, level:1, name:'Maliketh, the Black Blade' },
    'borealis the freezing fog':       { id:'bg_borealis',    x: -61.49, y:164.59, level:1, name:'Freezing Lake' },
    'mimic tear':                      { id:'bg_mimic',       x:-184.91, y:128.39, level:2, name:'Nokron, Eternal City' },
    "commander o'neil":                { id:'bg_oneil',       x:-180.50, y:144.00, level:1, name:"Commander O'Neil" },
  };

  // Surface entry points for underground zones
  const SURF_ENTRIES = {
    siofra:   {x:-187.55, y:122.18}, nokron:   {x:-187.55, y:122.18},
    deeproot: {x:-187.55, y:122.18}, ainsel:   {x:-130.11, y: 78.35},
    mohgwyn:  {x: -70.68, y:129.59},
  };

  // Prerequisite stop data — when a prereq is needed, insert this stop
  const PREREQ_STOPS = {
    nokron_access: {
      name:'Starscourge Radahn', x:-194.36, y:160.21, level:1,
      zone:'caelid', label:'Kill Radahn (unlocks Nokron meteor)',
      runes: 70000,
    },
    radahn: {
      name:'Starscourge Radahn', x:-194.36, y:160.21, level:1,
      zone:'caelid', label:'Kill Radahn',
      runes: 70000,
    },
    capital_access: {
      name:'Draconic Tree Sentinel', x: -96.50, y:108.00, level:1,
      zone:'leyndell', label:'Kill Draconic Tree Sentinel (Leyndell gate)',
      runes: 80000,
    },
    // Free-text boss-kill prerequisites (from square_data.json prerequisites field)
    'Kill Godrick the Grafted': {
      name:'Godrick the Grafted', x:-174.50, y:86.20, level:1,
      zone:'limgrave', label:'Kill Godrick the Grafted',
      runes: 15000,
    },
    'Kill Morgott, The Omen King': {
      name:'Morgott, the Omen King', x:-107.64, y:120.62, level:1,
      zone:'leyndell', label:'Kill Morgott, The Omen King',
      runes: 120000,
    },
    'Kill Rykard, Lord of Blasphemy': {
      name:'Rykard, Lord of Blasphemy', x:-87.22, y:66.70, level:1,
      zone:'volcano_manor', label:'Kill Rykard, Lord of Blasphemy',
      runes: 130000,
    },
    'Kill Starscourge Radahn': {
      name:'Starscourge Radahn', x:-194.36, y:160.21, level:1,
      zone:'caelid', label:'Kill Starscourge Radahn',
      runes: 70000,
    },
    kill_loretta: {
      name:'Royal Knight Loretta', x:-110.58, y:50.77, level:1,
      zone:'caria_manor', label:'Kill Royal Knight Loretta (unlocks Three Sisters / Ranni\'s Rise)',
      runes: 10000,
    },
    physick_flask: {
      name:'Third Church of Marika', x:-180.125, y:123.403, level:1,
      zone:'limgrave', label:'Collect Flask of Wondrous Physick (Third Church of Marika)',
      runes: 0,
    },
    explosive_tear: {
      name:'Erdtree Avatar (Liurnia Southwest)', x:-149.594, y:45.909, level:1,
      zone:'liurnia', label:'Kill Erdtree Avatar — Liurnia SW (drops Ruptured Crystal Tear)',
      runes: 12000,
    },
    ranni_quest_p1: {
      name:"Ranni's Rise", x:-106.42, y:50.01, level:1,
      zone:'caria_manor', label:"Talk to Ranni at Ranni's Rise (start quest)",
      runes: 0,
    },
    'Kill Fell Twins': {
      name:'Fell Twins', x:-104.03, y:132.13, level:1,
      zone:'leyndell', label:'Kill Fell Twins (unlock lift to Divine Tower of East Altus)',
      runes: 30000,
    },
  };

  const REMEMBRANCE_BOSSES = new Set([
    'godrick the grafted','rennala, queen of the full moon','starscourge radahn',
    'morgott, the omen king','rykard, lord of blasphemy','fire giant',
    'mohg, lord of blood','malenia, blade of miquella','maliketh, the black blade',
    'astel, naturalborn of the void','dragonlord placidusax','elden beast',
    'lichdragon fortissax','regal ancestor spirit',
  ]);

  // ── Golden Rune [9]+ waypoints — high-value consumable pickups ──────────────
  // Any of these within GOLDEN_RUNE_PROXIMITY map units of a planned stop gets
  // inserted as an optional bonus waypoint in buildRouteForLine.
  const GOLDEN_RUNE_PROXIMITY = 10;

  const GOLDEN_RUNE_WAYPOINTS = [
    { name:"Golden Rune [10] — Guardian's Garrison",   x:-74.91,   y:160.85, level:1, runes:5000,  zone:'mountaintops' },
    { name:'Golden Rune [12] — Consecrated Snowfield', x:-77.16,   y:148.58, level:1, runes:13000, zone:'consecrated'  },
    { name:'Golden Rune [10] ×3 — Castle Sol',         x:-60.281,  y:156.10, level:1, runes:15000, zone:'mountaintops' },
    { name:'Golden Rune [9] — Castle Sol',             x:-60.369,  y:158.10, level:1, runes:3800,  zone:'mountaintops' },
    { name:'Golden Rune [9] — Caelid Treasure',        x:-174.56,  y:134.14, level:1, runes:3800,  zone:'caelid'       },
    { name:'Golden Rune [13] — Elphael',               x:-38.209,  y:149.35, level:1, runes:22000, zone:'haligtree'    },
    { name:'Golden Rune [10] — Elphael (A)',           x:-36.853,  y:149.58, level:1, runes:5000,  zone:'haligtree'    },
    { name:'Golden Rune [12] — Elphael (B)',           x:-39.356,  y:149.74, level:1, runes:13000, zone:'haligtree'    },
    { name:'Golden Rune [10] — Elphael (C)',           x:-38.352,  y:148.86, level:1, runes:5000,  zone:'haligtree'    },
    { name:'Golden Rune [13] — Mohgwyn Mausoleum',     x:-183.616, y:149.08, level:2, runes:22000, zone:'mohgwyn'      },
    { name:'Golden Rune [10] — Grand Cloister (A)',    x:-139.456, y:56.23,  level:2, runes:5000,  zone:'ainsel'       },
    { name:'Golden Rune [10] — Grand Cloister (B)',    x:-140.35,  y:56.75,  level:2, runes:5000,  zone:'ainsel'       },
  ];

  // Full set of remembrance boss fight locations — used when a boss_modifier square
  // is on the board (e.g. "Kill a Remembrance boss hitless").  The modifier square
  // can be completed at any of these locations, so they are treated as its candidates.
  const REMEMBRANCE_BOSS_LOCS = [
    { name:'Godrick the Grafted',             x:-174.50, y: 86.20, level:1, zone:'stormveil'    },
    { name:'Rennala, Queen of the Full Moon', x:-135.42, y: 56.11, level:1, zone:'liurnia'      },
    { name:'Starscourge Radahn',              x:-194.36, y:160.21, level:1, zone:'caelid'       },
    { name:'Morgott, the Omen King',          x:-107.64, y:120.62, level:1, zone:'leyndell'     },
    { name:'Rykard, Lord of Blasphemy',       x: -87.22, y: 66.70, level:1, zone:'volcano_manor'},
    { name:'Fire Giant',                      x: -92.34, y:163.88, level:1, zone:'mountaintops' },
    { name:'Mohg, Lord of Blood',             x:-182.32, y:146.50, level:2, zone:'mohgwyn'      },
    { name:'Malenia, Blade of Miquella',      x: -38.12, y:146.39, level:1, zone:'haligtree'   },
    { name:'Maliketh, the Black Blade',       x:-125.10, y:221.00, level:1, zone:'farum_azula'  },
    { name:'Astel, Naturalborn of the Void',  x:-165.67, y: 47.65, level:2, zone:'ainsel'      },
    { name:'Dragonlord Placidusax',           x:-138.50, y:218.00, level:1, zone:'farum_azula'  },
    { name:'Lichdragon Fortissax',            x:-103.50, y:124.00, level:1, zone:'deeproot'     },
    { name:'Regal Ancestor Spirit',           x:-178.20, y:131.50, level:2, zone:'siofra'       },
  ];

  const PREREQ_LABELS = {
    nokron_access:  'Kill Radahn first (unlocks Nokron)',
    radahn:         'Kill Radahn first',
    kill_loretta:   'Kill Royal Knight Loretta first (unlocks Three Sisters)',
    physick_flask:  'Collect Flask of Wondrous Physick (Third Church of Marika)',
    explosive_tear: 'Kill Erdtree Avatar — Liurnia SW for Ruptured Crystal Tear',
    ranni_quest_p1: "Talk to Ranni at Ranni's Rise (start quest)",
    ranni_quest_p2: 'Progress Ranni quest (Fingerslayer Blade)',
    fia_quest:      'Progress Fia quest',
    mohgwyn_access: 'Varre quest or Haligtree left medallion half',
    capital_access: '2 Great Runes + Draconic Tree Sentinel',
    'Kill Fell Twins': 'Kill Fell Twins (unlocks lift to Divine Tower of East Altus)',
  };

  // ── Math helpers ───────────────────────────────────────────────────────────
  function dist(a, b) { return Math.sqrt((a.x-b.x)**2 + (a.y-b.y)**2); }
  function locKey(l)  { return `${Math.round(l.x*10)}_${Math.round(l.y*10)}_${l.level||1}`; }
  function isUG(l)    { return l.level === 2; }

  function travelCost(target, pool) {
    if (isUG(target)) {
      let bestUG = null, dUG = Infinity;
      for (const g of pool) { if (!isUG(g)) continue; const d = dist(g,target); if (d<dUG){dUG=d;bestUG=g;} }
      const entry = SURF_ENTRIES[target.zone] || SURF_ENTRIES.siofra;
      let bestS = null, dS = Infinity;
      for (const g of pool) { if (isUG(g)) continue; const d = dist(g,entry); if (d<dS){dS=d;bestS=g;} }
      const surfTotal = dS + dist(entry, target);
      if (bestUG && dUG <= surfTotal) return { grace: bestUG, distance: dUG };
      if (bestS)  return { grace: bestS, distance: surfTotal };
      return { grace: pool[0], distance: Infinity };
    }
    let best = null, bd = Infinity;
    for (const g of pool) {
      if (isUG(g)) continue;
      const d = dist(g, target);
      if (d < bd) { bd = d; best = g; }
    }
    return { grace: best || pool[0], distance: bd };
  }

  // Total travel cost to visit a set of locations in cheapest order from a pool
  // Used to score a bingo line
  function lineTravelCost(locs, pool) {
    if (!locs.length) return 0;
    let total = 0;
    const currentPool = pool.map(g => ({...g}));
    const remaining   = [...locs];
    let iter = 0;
    while (remaining.length && iter++ < 200) {
      let bestIdx = -1, bestCost = Infinity;
      for (let i = 0; i < remaining.length; i++) {
        const { distance } = travelCost(remaining[i], currentPool);
        const zone    = remaining[i].zone || inferZone(remaining[i]);
        const penalty = ZONE_PENALTY[zone] ?? 0.3;
        const cost    = distance * (1 + penalty);
        if (cost < bestCost) { bestCost = cost; bestIdx = i; }
      }
      if (bestIdx === -1) break;
      const loc = remaining.splice(bestIdx, 1)[0];
      total += bestCost;
      // Unlock boss grace if applicable
      const n = (loc.name||'').toLowerCase();
      const bg = BOSS_GRACES[n];
      if (bg && !currentPool.find(g => g.id === bg.id)) currentPool.push({...bg});
    }
    return total;
  }

  function inferZone(loc) {
    const {x, y, level} = loc;
    if (!x || !y) return 'unknown';
    if (level === 2) {
      if (x < -160 && y >= 128)                          return 'siofra';
      if (x > -145 && x < -115 && y > 55 && y < 85)     return 'ainsel';
      if (x > -110 && x < -85  && y > 105)               return 'deeproot';
      if (x < -175 && y > 144)                           return 'mohgwyn';
      return 'unknown';
    }
    if (x >  -55 && x <  -25 && y > 130 && y < 165)    return 'haligtree';
    if (x >  -90 && x <  -55 && y > 125 && y < 165)    return 'consecrated';
    if (x > -105 && x <  -55 && y >  95 && y < 175)    return 'mountaintops';
    if (x > -140 && x <  -55 && y > 195 && y < 230)    return 'farum_azula';
    if (x > -200 && x < -140 && y > 120 && y < 170)    return 'caelid';
    if (x > -115 && x <  -75 && y >  95 && y < 145)    return 'leyndell';
    if (x > -100 && x <  -75 && y >  55 && y <  75)    return 'mt_gelmir';
    if (x > -115 && x <  -75 && y >  55 && y <  95)    return 'altus_plateau';
    if (x > -175 && x < -115 && y >  45 && y <  95)    return 'liurnia';
    if (x > -115 && x < -100 && y >  45 && y <  60)    return 'caria_manor';
    if (x > -215 && x < -170 && y >  75 && y <  95)    return 'stormveil';
    if (x > -215 && x < -170 && y >  80 && y < 130)    return 'limgrave';
    if (x > -240 && x < -195 && y >  90 && y < 135)    return 'weeping_peninsula';
    return 'unknown';
  }

  // ── Location resolving ─────────────────────────────────────────────────────
  function resolveLocs(rawName, sqData) {
    if (!sqData) return [];
    const locs = [];
    const add  = arr => { if (!arr) return; arr.forEach(l => { if (l?.x && l?.y) locs.push({...l, zone: l.zone||inferZone(l)}); }); };
    switch (sqData.type) {
      case 'boss_specific': case 'dungeon_specific': case 'npc_action':
      case 'npc_invasion':  case 'consumable_action': case 'acquire_fixed':
        add(sqData.locations);
        if (sqData.location) locs.push({...sqData.location, zone: sqData.location.zone||inferZone(sqData.location)});
        break;
      case 'boss_any': case 'boss_count': case 'dungeon_count':
      case 'acquire_multi': case 'npc_kill':
        add(sqData.locations); break;
      case 'acquire_count':
        add(sqData.locations);
        add(sqData.vendor_locations); // vendor stops (Sellen, Corhyn, Miriel…) are valid route targets
        break;
      case 'boss_region':       add(sqData.all_bosses);  break;
      case 'boss_tag':          add(sqData.candidates);  break;
      case 'boss_multi_type':   (sqData.groups||[]).forEach(g => add(g.locations)); break;
      case 'boss_multi_specific':(sqData.bosses||[]).forEach(b => add(b.locations)); break;
      default:
        add(sqData.locations);
        if (sqData.location) locs.push({...sqData.location, zone: sqData.location.zone||inferZone(sqData.location)});
    }
    const seen = new Set();
    return locs.filter(l => { const k = locKey(l); if (seen.has(k)) return false; seen.add(k); return true; });
  }

  function extractCount(text, sqData) {
    if (sqData?.count_needed != null) return sqData.count_needed;
    if (sqData?.type === 'boss_multi_type') return (sqData.groups||[]).reduce((s,g) => s+(g.count||1), 0);
    // acquire_multi: every item must be collected; boss_multi_specific: every boss must die
    if (sqData?.type === 'acquire_multi')      return (sqData.locations||[]).length || 1;
    if (sqData?.type === 'boss_multi_specific') return (sqData.bosses||[]).length   || 1;
    if (['boss_specific','consumable_action','npc_action','restore_rune',
         'acquire_fixed','dungeon_specific','npc_invasion'].includes(sqData?.type)) return 1;
    const m = text.match(/^(?:Kill|Complete|Collect|Acquire|Learn|Give|Return|Invade|Buy|Dupe|Use)\s+(\d+)/i);
    return m ? parseInt(m[1]) : 1;
  }

  // ── Count-square clustering ────────────────────────────────────────────────
  // For squares that need N kills from M candidates, pick the N closest
  // candidates to each other (minimise total inter-location travel).
  // Returns the N best locations sorted by travel order.
  function clusterLocs(locs, count, warpPool) {
    if (locs.length <= count) return locs;

    // Score each possible subset using full lineTravelCost (applies zone penalties).
    // Brute-force for small N; greedy with zone-penalty weighting for larger N.
    if (count <= 6 && locs.length <= 20) {
      let bestSubset = null, bestCost = Infinity;
      for (const subset of combinations(locs, count)) {
        const cost = lineTravelCost(subset, warpPool);
        if (cost < bestCost) { bestCost = cost; bestSubset = subset; }
      }
      return bestSubset || locs.slice(0, count);
    }

    // Greedy: anchor = location with lowest zone-penalty-adjusted grace distance
    function adjCost(l) {
      const { distance } = travelCost(l, warpPool);
      const zone = l.zone || inferZone(l);
      return distance * (1 + (ZONE_PENALTY[zone] ?? 0.3));
    }
    let anchor = locs.reduce((best, l) => adjCost(l) < adjCost(best) ? l : best, locs[0]);

    const chosen    = [anchor];
    const remaining = locs.filter(l => locKey(l) !== locKey(anchor));
    while (chosen.length < count && remaining.length) {
      let bestLoc = null, bestD = Infinity;
      for (const candidate of remaining) {
        const zone    = candidate.zone || inferZone(candidate);
        const penalty = 1 + (ZONE_PENALTY[zone] ?? 0.3);
        // Prefer candidates close to already-chosen locations AND in low-penalty zones
        const d = Math.min(...chosen.map(c => dist(c, candidate))) * penalty;
        if (d < bestD) { bestD = d; bestLoc = candidate; }
      }
      if (!bestLoc) break;
      chosen.push(bestLoc);
      remaining.splice(remaining.indexOf(bestLoc), 1);
    }
    return chosen;
  }

  // Standard combinations(array, k) generator
  function* combinations(arr, k) {
    if (k === 0) { yield []; return; }
    for (let i = 0; i <= arr.length - k; i++) {
      for (const rest of combinations(arr.slice(i+1), k-1)) {
        yield [arr[i], ...rest];
      }
    }
  }

  // ── Prerequisite resolution ────────────────────────────────────────────────
  // Returns list of prereq keys that aren't satisfied yet by completed stops
  function unsatisfiedPrereqs(prereqs, completedNames) {
    return (prereqs||[]).filter(p => {
      if (p === 'nokron_access' || p === 'radahn')
        return !completedNames.has('starscourge radahn');
      if (p === 'capital_access')
        return !completedNames.has('_capital_access');
      if (p === 'kill_loretta')
        return !completedNames.has('royal knight loretta');
      if (p === 'physick_flask')
        return !completedNames.has('third church of marika');
      if (p === 'explosive_tear')
        return !completedNames.has('erdtree avatar (liurnia southwest)');
      if (p === 'ranni_quest_p1')
        // Ranni's Rise requires Loretta first — if Loretta not done, Ranni isn't either
        return !completedNames.has("ranni's rise") || !completedNames.has('royal knight loretta');
      // Free-text boss-kill prereqs: check if we've already visited that boss
      if (PREREQ_STOPS[p])
        return !completedNames.has((PREREQ_STOPS[p].name || '').toLowerCase());
      return false; // truly unknown prereqs — optimistically allow
    });
  }

  // ── Build objectives from board squares ────────────────────────────────────
  function buildObjectives(boardSquares, squareDataMap, doneMask, blockedMask) {
    const squares    = squareDataMap?.squares || squareDataMap || {};
    const objectives = [];
    const passive    = [];
    const warnings   = [];
    const modifiers  = []; // boss_modifier squares — resolved in second pass

    boardSquares.forEach((sq, boardIdx) => {
      const sqData = squares[sq.raw.name];
      if (!sqData) { warnings.push(`No data: "${sq.text}"`); return; }

      if (['passive_runes','passive_stat'].includes(sqData.type)) {
        passive.push({ squareName:sq.text, rawName:sq.raw.name, data:sqData, boardIdx }); return;
      }

      // boss_modifier (hitless, bow-only, etc.) — defer to second pass
      if (sqData.type === 'boss_modifier') {
        modifiers.push({ sq, boardIdx, sqData }); return;
      }

      const locs = resolveLocs(sq.raw.name, sqData);
      if (!locs.length) {
        passive.push({ squareName:sq.text, rawName:sq.raw.name, data:sqData, boardIdx }); return;
      }

      const count = extractCount(sq.text, sqData);
      objectives.push({
        boardIdx, rawName:sq.raw.name, squareName:sq.text, data:sqData,
        allLocs:locs, countNeeded:count, prereqs:sqData.prerequisites||[],
        isDone:    doneMask    ? doneMask[boardIdx]    : false,
        isBlocked: blockedMask ? blockedMask[boardIdx] : false,
      });
    });

    // Second pass: give boss_modifier squares the remembrance boss locations
    // already present in this board's objectives (so visiting, say, Radahn for
    // another square automatically credits "Kill a Remembrance boss hitless" too).
    if (modifiers.length) {
      const boardRemLocs = [];
      objectives.forEach(obj => {
        obj.allLocs.forEach(loc => {
          if (REMEMBRANCE_BOSSES.has((loc.name||'').toLowerCase()))
            boardRemLocs.push({...loc});
        });
      });
      // Fall back to the full constant list if no remembrance bosses are on the board
      const remLocs = boardRemLocs.length ? boardRemLocs : REMEMBRANCE_BOSS_LOCS;

      modifiers.forEach(({ sq, boardIdx, sqData }) => {
        objectives.push({
          boardIdx, rawName:sq.raw.name, squareName:sq.text, data:sqData,
          allLocs:    remLocs,
          countNeeded:1,
          prereqs:    sqData.prerequisites||[],
          isDone:     doneMask    ? doneMask[boardIdx]    : false,
          isBlocked:  blockedMask ? blockedMask[boardIdx] : false,
          isBossModifier: true,
        });
      });
    }

    return { objectives, passive, warnings };
  }

  // ── Compute opponent threat score for each line ───────────────────────────
  // Returns array of threat info per line index
  function computeOpponentThreats(BINGO_LINES, objectives) {
    return BINGO_LINES.map((indices, li) => {
      const lineObjs = indices.map(i => objectives.find(o => o.boardIdx === i)).filter(Boolean);
      const oppCount = lineObjs.filter(o => o.isBlocked).length;
      const myCount  = lineObjs.filter(o => o.isDone).length;
      const isBlockedByMe = myCount > 0;
      return {
        li, oppCount, myCount,
        isBlockedByMe,
        isThreat: oppCount >= 3 && !isBlockedByMe,
        isDanger: oppCount >= 4 && !isBlockedByMe,
      };
    });
  }

  // ── Score a single bingo line ──────────────────────────────────────────────
  // Returns { cost, feasible, needsPrereqs[], objsForLine[] }
  function scoreLine(lineIndices, objectives, warpPool, completedNames) {
    const lineObjs = lineIndices.map(i => objectives.find(o => o.boardIdx === i)).filter(Boolean);

    // If any square in this line is passive (not in objectives), the line can't be completed
    if (lineObjs.length < lineIndices.length) return { cost: Infinity, feasible: false, blocked: false };

    // Check if line is already blocked (opponent marked a square on it)
    const blockedObjs = lineObjs.filter(o => o.isBlocked);
    if (blockedObjs.length > 0) return { cost: Infinity, feasible: false, blocked: true };

    // Squares already done don't cost anything
    const todoObjs = lineObjs.filter(o => !o.isDone);

    // Collect all prereqs needed
    const neededPrereqs = new Set();
    todoObjs.forEach(o => {
      unsatisfiedPrereqs(o.prereqs, completedNames).forEach(p => neededPrereqs.add(p));
    });

    // Build the flat list of locations to visit for this line
    // For count squares: cluster to N closest candidates
    const allLocsForLine = [];
    for (const obj of todoObjs) {
      if (obj.countNeeded <= 1) {
        // Single location — pick cheapest candidate
        allLocsForLine.push(...obj.allLocs);
      } else {
        // Multi-count — cluster to N closest
        const clustered = clusterLocs(obj.allLocs, obj.countNeeded, warpPool);
        allLocsForLine.push(...clustered);
      }
    }

    // Add prereq stop locations
    neededPrereqs.forEach(p => {
      const ps = PREREQ_STOPS[p];
      if (ps) allLocsForLine.unshift({...ps}); // prereqs go first
    });

    // Deduplicate by locKey — shared locations (synergies) only pay travel cost once.
    // e.g. "Kill Radahn" + "Kill Remembrance boss hitless" + "Restore Great Rune"
    // all share the same arena; visiting once should suffice for scoring.
    const _seenLocs = new Set();
    const dedupedLocs = allLocsForLine.filter(loc => {
      const k = locKey(loc);
      if (_seenLocs.has(k)) return false;
      _seenLocs.add(k);
      return true;
    });

    // Score total travel cost for this line
    const cost = lineTravelCost(dedupedLocs, warpPool);

    return {
      cost,
      feasible:    true,
      blocked:     false,
      todoObjs,
      lineObjs,
      neededPrereqs: [...neededPrereqs],
      allLocsForLine,
    };
  }

  // ── Core route builder for a given line ───────────────────────────────────
  function buildRouteForLine(lineIndices, objectives, passive, warnings, warpPool, completedNames) {
    const stops      = [];
    const visited    = new Set();
    let   runeTotal  = 0;
    let   stopNum    = 1;
    const unlockedIds= new Set(warpPool.map(g => g.id));
    const currentPool= warpPool.map(g => ({...g}));

    function unlockBossGrace(nameL) {
      const g = BOSS_GRACES[nameL];
      if (!g || unlockedIds.has(g.id)) return null;
      unlockedIds.add(g.id); currentPool.push({...g}); return g;
    }

    // Stop 0: Gatefront start
    stops.push({
      num:0, squareName:'Grab Torrent', rawName:'_start',
      type:'start', zone:'Limgrave', zoneId:'limgrave',
      location: S6_GRACES[0], warpFrom: null,
      flags:['Pick up Torrent from Melina'], notes:'',
      allLocations:[], runes:0, runeTotal:0, isRemembrance:false,
    });

    // Get todo objectives for this line (not done, not blocked)
    const lineObjs = lineIndices
      .map(i => objectives.find(o => o.boardIdx === i))
      .filter(o => o && !o.isDone && !o.isBlocked);

    // Collect prereq stops needed
    const insertedPrereqs = new Set();
    lineObjs.forEach(obj => {
      unsatisfiedPrereqs(obj.prereqs, completedNames).forEach(p => {
        if (!insertedPrereqs.has(p) && PREREQ_STOPS[p]) {
          insertedPrereqs.add(p);
        }
      });
    });

    // Build cross-credit map across ALL objectives (not just this line)
    // So visiting a location credits other objectives too
    const creditMap = new Map();
    objectives.forEach(obj => {
      obj.allLocs.forEach(loc => {
        const k = locKey(loc);
        if (!creditMap.has(k)) creditMap.set(k, []);
        creditMap.get(k).push(obj.rawName);
      });
    });

    // Build flat work queue: prereq stops first, then line objectives
    // For each multi-count square, expand to N clustered locations
    const workQueue = [];

    // Insert prereq stops
    insertedPrereqs.forEach(p => {
      const ps = PREREQ_STOPS[p];
      if (!ps) return;
      workQueue.push({
        isPrereq:    true,
        prereqKey:   p,
        squareName:  ps.label,
        rawName:     `_prereq_${p}`,
        loc:         {...ps, zone: ps.zone},
        runes:       ps.runes || 0,
        countNeeded: 1, remaining: 1,
      });
    });

    // Gap 1 — locKey→prereqKey map.  When an objective stop happens to land at
    // the same coordinate as a prereq, the pending prereq work item is removed
    // and the prereq is satisfied for free (one stop, double purpose).
    const prereqByLoc = new Map();
    insertedPrereqs.forEach(p => {
      const ps = PREREQ_STOPS[p];
      if (ps) prereqByLoc.set(locKey({x:ps.x, y:ps.y, level:ps.level||1}), p);
    });

    // Gap 2 — collect already-queued locations (prereq stops) as synergy anchors.
    // Objective candidate selection will prefer candidates near these planned stops,
    // modelling "we're already going there — pick a boss on the way."
    const plannedLocs = workQueue.filter(w => w.loc).map(w => ({...w.loc}));

    // Line objectives → expand count squares into individual location tasks
    lineObjs.forEach(obj => {
      let locs;
      if (obj.countNeeded <= 1) {
        // Route-aware candidate selection (Gap 2):
        // For each candidate, effective cost = min(standalone_travel, detour_from_nearest_planned_stop).
        // This means "if we're already routing through Liurnia for the Erdtree Avatar prereq,
        // a Liurnia boss candidate for the physick square costs only the short detour, not the
        // full trip from Gatefront."
        let bestLoc = obj.allLocs[0], bestScore = Infinity;
        obj.allLocs.forEach(loc => {
          const { distance } = travelCost(loc, currentPool);
          const zone    = loc.zone || inferZone(loc);
          const penalty = ZONE_PENALTY[zone] ?? 0.3;
          let score = distance * (1 + penalty);
          if (plannedLocs.length > 0) {
            const minD = Math.min(...plannedLocs.map(p => dist(loc, p)));
            if (minD < 20) {
              // Detour model: if near a planned stop, cost ≈ short detour, not full trip
              const detourCost = minD * (1 + penalty) + 2; // +2 = fixed stop overhead
              score = Math.min(score, detourCost);
            }
          }
          if (score < bestScore) { bestScore = score; bestLoc = loc; }
        });
        locs = [bestLoc];
      } else {
        locs = clusterLocs(obj.allLocs, obj.countNeeded, currentPool);
      }

      locs.forEach((loc, i) => {
        workQueue.push({
          isPrereq:    false,
          obj,
          loc,
          squareName:  obj.squareName,
          rawName:     obj.rawName,
          countNeeded: obj.countNeeded,
          locIndex:    i,
          totalLocs:   Math.min(obj.countNeeded, locs.length),
        });
      });
      // Let subsequent objectives see this one's chosen location as a synergy anchor
      if (locs.length > 0) plannedLocs.push({...locs[0]});
    });

    // Greedy ordering of work queue
    let iter = 0;
    while (workQueue.length && iter++ < 300) {
      // Prereqs always go first if not yet done
      const prereqItems = workQueue.filter(w => w.isPrereq);
      if (prereqItems.length > 0) {
        const item = prereqItems[0];
        workQueue.splice(workQueue.indexOf(item), 1);
        _emitStop(item, stops, currentPool, creditMap, visited, runeTotal, stopNum++, unlockBossGrace);
        runeTotal += item.runes || 0;
        // Mark prereq as satisfied
        if (item.prereqKey === 'nokron_access' || item.prereqKey === 'radahn') {
          completedNames.add('starscourge radahn');
        }
        if (item.prereqKey === 'capital_access') {
          completedNames.add('_capital_access');
        }
        if (item.prereqKey === 'ranni_quest_p1') {
          completedNames.add("ranni's rise");
        }
        // Free-text boss-kill prereqs
        if (PREREQ_STOPS[item.prereqKey]) {
          completedNames.add((PREREQ_STOPS[item.prereqKey].name || '').toLowerCase());
        }
        continue;
      }

      // Pick cheapest remaining work item
      let bestIdx = -1, bestCost = Infinity;
      workQueue.forEach((item, i) => {
        if (visited.has(locKey(item.loc))) { bestIdx = i; bestCost = -1; return; } // already visited
        const { distance } = travelCost(item.loc, currentPool);
        const zone    = item.loc.zone || inferZone(item.loc);
        const penalty = ZONE_PENALTY[zone] ?? 0.3;
        const cost    = distance * (1 + penalty);
        if (cost < bestCost) { bestCost = cost; bestIdx = i; }
      });

      if (bestIdx === -1) break;
      const item = workQueue.splice(bestIdx, 1)[0];

      if (visited.has(locKey(item.loc))) {
        // Already visited via cross-credit — still credit it but no stop
        if (item.obj) {
          const credited = creditMap.get(locKey(item.loc)) || [];
          credited.forEach(rn => {
            const o = objectives.find(x => x.rawName === rn);
            if (o) o._creditsGiven = (o._creditsGiven||0) + 1;
          });
        }
        continue;
      }

      runeTotal += _emitStop(item, stops, currentPool, creditMap, visited, runeTotal, stopNum++, unlockBossGrace);

      // Gap 1: if this objective stop's location coincides with a pending prereq,
      // remove the duplicate prereq work item and satisfy the prereq in-place.
      if (!item.isPrereq && prereqByLoc.size > 0) {
        const emKey = locKey(item.loc);
        const mergedPrereq = prereqByLoc.get(emKey);
        if (mergedPrereq) {
          const pendingIdx = workQueue.findIndex(w => w.isPrereq && w.prereqKey === mergedPrereq);
          if (pendingIdx !== -1) {
            workQueue.splice(pendingIdx, 1);
            stops[stops.length-1].flags.push(`⚡ Also: ${PREREQ_LABELS[mergedPrereq] || mergedPrereq}`);
          }
          _satisfyPrereq(mergedPrereq, completedNames);
        }
      }
    }

    // ── Insert nearby golden rune [9]+ bonus waypoints ───────────────────────
    // Group runes by the closest route stop (within GOLDEN_RUNE_PROXIMITY units,
    // same surface/underground level).
    const runeGroups = new Map(); // stopIdx → [rune, ...]
    GOLDEN_RUNE_WAYPOINTS.forEach(rune => {
      let nearestIdx = -1, nearestDist = Infinity;
      stops.forEach((s, idx) => {
        if (!s.location || s.type === 'start') return;
        if ((s.location.level || 1) !== (rune.level || 1)) return;
        const d = dist(s.location, rune);
        if (d < nearestDist) { nearestDist = d; nearestIdx = idx; }
      });
      if (nearestIdx !== -1 && nearestDist <= GOLDEN_RUNE_PROXIMITY) {
        if (!runeGroups.has(nearestIdx)) runeGroups.set(nearestIdx, []);
        runeGroups.get(nearestIdx).push(rune);
      }
    });

    // Insert one bonus stop per group; process in descending index order so
    // earlier splice calls don't shift later indices.
    [...runeGroups.keys()].sort((a, b) => b - a).forEach(stopIdx => {
      const group      = runeGroups.get(stopIdx);
      const totalRunes = group.reduce((s, r) => s + r.runes, 0);
      const loc        = group[0];
      const zone       = loc.zone || inferZone(loc);
      const label      = group.length > 1
        ? `Nearby Golden Runes (×${group.length}) — ${ZONE_LABEL[zone]||zone}`
        : loc.name;
      stops.splice(stopIdx + 1, 0, {
        num:          0,
        squareName:   label,
        rawName:      `_golden_runes_near_${stopIdx}`,
        type:         'bonus_pickup',
        zone:         ZONE_LABEL[zone] || zone,
        zoneId:       zone,
        location:     loc,
        allLocations: group,
        warpFrom:     stops[stopIdx]?.location || null,
        flags:        [`💰 +${totalRunes.toLocaleString()} runes — ${group.map(r => r.name).join(', ')}`],
        notes:        'Optional bonus pickup — on the way',
        runes:        totalRunes,
        runeTotal:    0,
        isBonus:      true,
        isRemembrance:false,
        isPrereq:     false,
      });
    });

    // Renumber stops and recompute runeTotal; mark rune-level-60 milestone
    const RUNES_60 = 1_200_000;
    let runeAcc = 0, marked60 = false;
    stops.forEach((s, i) => {
      s.num = i;
      s.flags = (s.flags || []).filter(f => !f.includes('~Rune Level 60'));
      s._lvl60 = false;
      runeAcc += s.runes || 0;
      s.runeTotal = runeAcc;
      if (!marked60 && runeAcc >= RUNES_60) {
        s.flags.push('📊 ~Rune Level 60 reachable here');
        s._lvl60 = true;
        marked60 = true;
      }
    });

    return stops;
  }

  // Helper: emit a single route stop and return runes gained
  function _emitStop(item, stops, pool, creditMap, visited, runeTotal, stopNum, unlockBossGrace) {
    const loc     = item.loc;
    const locName = (loc.name||'').toLowerCase();
    visited.add(locKey(loc));

    const { grace: warpFrom } = travelCost(loc, pool);
    const zone   = loc.zone || inferZone(loc);
    const flags  = [];
    const runes  = item.runes || item.obj?.data?.runes || item.obj?.data?.runes_each || 0;

    // Cross-credit
    const credited = (creditMap.get(locKey(loc))||[]);
    const crossCredit = credited
      .filter(rn => rn !== item.rawName)
      .map(rn => item.obj ? rn : null).filter(Boolean);
    // We'll just show location name credits for clarity

    // Prereq flags from the objective
    (item.obj?.prereqs||[]).forEach(p => { if (PREREQ_LABELS[p]) flags.push(PREREQ_LABELS[p]); });

    // Boss grace unlock
    const newGrace = unlockBossGrace(locName);
    if (newGrace) flags.push(`✓ Unlocks warp: ${newGrace.name}`);

    // Count label
    const totalLocs = item.totalLocs || 1;
    const locIdx    = item.locIndex  ?? 0;
    const showCount = totalLocs > 1;
    const countStr  = showCount ? ` (${locIdx+1}/${totalLocs})` : '';

    stops.push({
      num:          stopNum,
      squareName:   item.squareName + countStr,
      rawName:      item.rawName,
      type:         item.obj?.data?.type || 'prereq',
      zone:         ZONE_LABEL[zone] || zone,
      zoneId:       zone,
      location:     loc,
      allLocations: item.obj?.allLocs || [loc],
      warpFrom,
      flags,
      notes:        item.obj?.data?.notes || '',
      prereqs:      (item.obj?.prereqs||[]).map(p => PREREQ_LABELS[p]||p),
      runes,
      runeTotal:    runeTotal + runes,
      isRemembrance:REMEMBRANCE_BOSSES.has(locName),
      isPrereq:     item.isPrereq || false,
    });

    return runes;
  }

  // ── Majority route: pick cheapest uncompleted objectives to reach 13 ────────
  function buildMajorityRoute(objectives, passive, warnings, warpPool, completedNames) {
    const done    = objectives.filter(o => o.isDone).length;
    const needed  = Math.max(1, 13 - done);
    const avail   = objectives.filter(o => !o.isDone && !o.isBlocked);

    // Score each available objective by its cheapest-single-location travel cost
    const scored = avail.map(obj => {
      let best = Infinity;
      obj.allLocs.forEach(loc => {
        const { distance } = travelCost(loc, warpPool);
        const zone = loc.zone || inferZone(loc);
        const cost = distance * (1 + (ZONE_PENALTY[zone] ?? 0.3));
        if (cost < best) best = cost;
      });
      return { obj, cost: best };
    }).sort((a, b) => a.cost - b.cost);

    const targetIndices = scored.slice(0, Math.min(needed, scored.length))
                                .map(s => s.obj.boardIdx);
    return buildRouteForLine(targetIndices, objectives, passive, warnings, warpPool, completedNames);
  }

  // ── Main: evaluate all 12 lines, pick best, build route ───────────────────
  function _satisfyPrereq(key, completedNames) {
    if (key === 'nokron_access' || key === 'radahn') completedNames.add('starscourge radahn');
    else if (key === 'capital_access')               completedNames.add('_capital_access');
    else if (key === 'kill_loretta')                 completedNames.add('royal knight loretta');
    else if (key === 'physick_flask')                completedNames.add('third church of marika');
    else if (key === 'explosive_tear')               completedNames.add('erdtree avatar (liurnia southwest)');
    else if (key === 'ranni_quest_p1')               { completedNames.add("ranni's rise"); completedNames.add('royal knight loretta'); }
    else if (PREREQ_STOPS[key])                      completedNames.add((PREREQ_STOPS[key].name || '').toLowerCase());
  }

  function computeBestLine(boardSquares, squareDataMap, options = {}) {
    const { doneMask = null, blockedMask = null, satisfiedPrereqs = [] } = options;
    const squares   = squareDataMap?.squares || squareDataMap || {};
    const warpPool  = S6_GRACES.map(g => ({...g}));
    const completedNames = new Set();

    // Pre-populate completedNames from already-done board squares
    if (doneMask) {
      boardSquares.forEach((sq, i) => {
        if (!doneMask[i]) return;
        const locs = resolveLocs(sq.raw.name, squares[sq.raw.name] || {});
        locs.forEach(l => completedNames.add((l.name||'').toLowerCase()));
      });
    }

    // Pre-populate from prereq stops the player already completed in the UI
    satisfiedPrereqs.forEach(key => _satisfyPrereq(key, completedNames));

    const { objectives, passive, warnings } = buildObjectives(
      boardSquares, squareDataMap, doneMask, blockedMask
    );

    // Score all 12 lines
    const BINGO_LINES = [
      [0,1,2,3,4],[5,6,7,8,9],[10,11,12,13,14],[15,16,17,18,19],[20,21,22,23,24], // rows
      [0,5,10,15,20],[1,6,11,16,21],[2,7,12,17,22],[3,8,13,18,23],[4,9,14,19,24], // cols
      [0,6,12,18,24],[4,8,12,16,20],                                               // diagonals
    ];

    const lineScores = BINGO_LINES.map((indices, li) => {
      const score = scoreLine(indices, objectives, warpPool, completedNames);
      return { li, indices, ...score };
    });

    // ── Opponent threat analysis ──────────────────────────────────────────────
    // Determine which of the opponent's lines are most dangerous.
    // A "block square" is any unclaimed square on a threatening opponent line
    // that we could claim to stop them.
    const threats = computeOpponentThreats(BINGO_LINES, objectives);
    const dangerLines = threats.filter(t => t.isDanger);   // opp has 4/5
    const threatLines = threats.filter(t => t.isThreat);   // opp has 3/5

    // For each threat line, find the cheapest unclaimed square on it
    // that isn't already on our planned line — that's a "blocking candidate"
    function findBlockSquares(threatLineIndices) {
      return threatLineIndices.flatMap(t =>
        BINGO_LINES[t.li]
          .map(i => objectives.find(o => o.boardIdx === i))
          .filter(o => o && !o.isDone && !o.isBlocked)
      );
    }

    const blockCandidates = findBlockSquares(dangerLines.length ? dangerLines : threatLines);

    // ── Scoring with opponent awareness ──────────────────────────────────────
    // Pure cost scoring ignores the opponent. We blend:
    //   finalScore = ownCost - blockBonus
    // blockBonus = big number if a stop on this line happens to be on a danger line
    const feasibleLines = lineScores.filter(ls => ls.feasible);

    feasibleLines.forEach(ls => {
      // Does this line include any squares that would block a danger/threat line?
      const mySquareIndices = new Set(ls.indices);
      const blocksOpp = blockCandidates.some(o => mySquareIndices.has(o.boardIdx));

      // bonus: reduces effective cost, making blocker lines more attractive
      const dangerBonus = dangerLines.length > 0 && blocksOpp ? ls.cost * 0.40 : 0;
      const threatBonus = threatLines.length > 0 && blocksOpp ? ls.cost * 0.20 : 0;
      ls.blockBonus   = dangerBonus || threatBonus;
      ls.adjustedCost = ls.cost - ls.blockBonus;
      ls.blocksOpp    = blocksOpp;
    });

    // Sort: feasible first, then by adjusted cost (opponent-aware)
    lineScores.sort((a, b) => {
      if (a.feasible !== b.feasible) return a.feasible ? -1 : 1;
      const ac = a.adjustedCost ?? a.cost;
      const bc = b.adjustedCost ?? b.cost;
      return ac - bc;
    });

    const best = lineScores[0];
    const targetLineIdx  = best?.feasible ? best.li : null;

    // Emit warnings about opponent threats
    if (dangerLines.length > 0) {
      warnings.push(`⚠ Opponent is ONE square from bingo on: ${dangerLines.map(t => LINE_NAMES[t.li]).join(', ')}`);
    } else if (threatLines.length > 0) {
      warnings.push(`Opponent threatening: ${threatLines.map(t => LINE_NAMES[t.li]).join(', ')} (${threatLines[0].oppCount}/5)`);
    }

    if (best?.blocksOpp) {
      warnings.push(`✓ Chosen line also blocks opponent threat`);
    }

    // When no bingo line is feasible, fall back to majority routing
    if (!best?.feasible) {
      const myDone = objectives.filter(o => o.isDone).length;
      warnings.push(`No bingo line available — routing for majority (${myDone}/13 squares).`);
      const majorityRoute = buildMajorityRoute(
        objectives, passive, warnings, warpPool, new Set(completedNames)
      );
      const targetLineName = `Majority (${myDone}/13)`;
      const lineSummary2 = lineScores.map(ls => ({
        name: LINE_NAMES[ls.li], lineIdx:ls.li, cost:ls.cost,
        adjustedCost:ls.adjustedCost??ls.cost, feasible:ls.feasible,
        blocked:ls.blocked||false, blocksOpp:ls.blocksOpp||false,
      }));
      return {
        route: majorityRoute, passive, warnings,
        targetLine: null, targetLineName,
        lineSummary: lineSummary2,
        threats: { dangerLines, threatLines },
        summary: {
          totalStops: majorityRoute.length, passiveCount: passive.length,
          estimatedRunes: majorityRoute.reduce((s,r) => s+(r.runes||0), 0),
          zonesVisited: [...new Set(majorityRoute.map(s => s.zone).filter(Boolean))],
          targetLine: targetLineName, warnings,
        },
      };
    }

    const targetLineName = LINE_NAMES[targetLineIdx];

    // Build route for the best bingo line
    const route = buildRouteForLine(best.indices, objectives, passive, warnings, warpPool, new Set(completedNames));

    // Compute line scores summary for display
    const lineSummary = lineScores.map(ls => ({
      name:       LINE_NAMES[ls.li],
      lineIdx:    ls.li,
      cost:       ls.cost,
      adjustedCost: ls.adjustedCost ?? ls.cost,
      feasible:   ls.feasible,
      blocked:    ls.blocked || false,
      blocksOpp:  ls.blocksOpp || false,
    }));

    return {
      route, passive, warnings,
      targetLine:  targetLineIdx,
      targetLineName,
      lineSummary,
      threats: { dangerLines, threatLines },
      summary: {
        totalStops:     route.length,
        passiveCount:   passive.length,
        estimatedRunes: route.reduce((s, r) => s + (r.runes||0), 0),
        zonesVisited:   [...new Set(route.map(s => s.zone).filter(Boolean))],
        targetLine:     targetLineName,
        warnings,
      },
    };
  }

  // ── Recompute after a mark event ───────────────────────────────────────────
  // doneMask[i]=true  → P1 completed square i
  // blockedMask[i]=true → opponent (P2) claimed square i
  // satisfiedPrereqs → prereq keys the player manually marked done in the UI
  function recompute(boardSquares, squareDataMap, marks, satisfiedPrereqs = []) {
    const doneMask    = marks.map(m => m === 0);
    const blockedMask = marks.map(m => m === 1);
    return computeBestLine(boardSquares, squareDataMap, { doneMask, blockedMask, satisfiedPrereqs });
  }

  // ── Available now: squares reachable with current warp pool ────────────────
  // Returns top N cheapest objectives sorted by travel cost
  function getAvailableNow(boardSquares, squareDataMap, marks, topN = 8) {
    const squares  = squareDataMap?.squares || squareDataMap || {};
    const warpPool = S6_GRACES.map(g => ({...g}));
    const results  = [];

    boardSquares.forEach((sq, i) => {
      if (marks && marks[i] !== -1) return; // already marked
      const sqData = squares[sq.raw.name];
      if (!sqData || ['passive_runes','passive_stat','boss_modifier'].includes(sqData.type)) return;
      const locs = resolveLocs(sq.raw.name, sqData);
      if (!locs.length) return;

      // Cheapest single location for this square
      let minCost = Infinity, bestLoc = null;
      locs.forEach(loc => {
        const { distance } = travelCost(loc, warpPool);
        const zone    = loc.zone || inferZone(loc);
        const penalty = ZONE_PENALTY[zone] ?? 0.3;
        const cost    = distance * (1 + penalty);
        if (cost < minCost) { minCost = cost; bestLoc = loc; }
      });

      if (bestLoc) {
        results.push({
          boardIdx: i, squareName: sq.text, rawName: sq.raw.name,
          cost: minCost, location: bestLoc,
          zone: ZONE_LABEL[bestLoc.zone || inferZone(bestLoc)] || 'Unknown',
        });
      }
    });

    return results.sort((a, b) => a.cost - b.cost).slice(0, topN);
  }

  return {
    computeBestLine,
    recompute,
    getAvailableNow,
    inferZone,
    ZONE_LABEL,
    LINE_NAMES,
  };
})();