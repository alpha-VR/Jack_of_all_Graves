// poi.js — Jack of All Graves
// Generates tiered Points of Interest from the current board and computes
// synergies between board squares.
//
// Tier 1 — Board objectives + prerequisite locations.
// Tier 2 — Smithing/Somber stones and golden rune pickups within TIER2_RADIUS
//           map units of any Tier 1 location or S6 starting grace.
//
// Square synergies (per-cell badges on the board):
//   co_location  — two squares share the same visit location (one trip serves both)
//   zone_cluster — 3+ squares concentrated in the same zone
//   prereq_chain — this square provides or depends on a prereq another square needs

const POI = (() => {

  const TIER2_RADIUS = 1;   // map units — calibrated to Haligtree grace → Finlay (~0.97 units)

  // Prereq keys → location data, mirrored from router.js PREREQ_STOPS.
  // Used both for T1 POI insertion and prereq-chain synergy detection.
  const PREREQ_STOPS = {
    nokron_access:                { name:'Starscourge Radahn',              x:-194.36,  y:160.21,  level:1, zone:'caelid'        },
    radahn:                       { name:'Starscourge Radahn',              x:-194.36,  y:160.21,  level:1, zone:'caelid'        },
    capital_access:               { name:'Draconic Tree Sentinel',          x: -96.50,  y:108.00,  level:1, zone:'leyndell'      },
    'Kill Godrick the Grafted':   { name:'Godrick the Grafted',             x:-174.50,  y: 86.20,  level:1, zone:'limgrave'      },
    'Kill Morgott, The Omen King':{ name:'Morgott, the Omen King',          x:-107.64,  y:120.62,  level:1, zone:'leyndell'      },
    'Kill Rykard, Lord of Blasphemy':{ name:'Rykard, Lord of Blasphemy',   x: -87.22,  y: 66.70,  level:1, zone:'volcano_manor' },
    'Kill Starscourge Radahn':    { name:'Starscourge Radahn',              x:-194.36,  y:160.21,  level:1, zone:'caelid'        },
    'Kill Fell Twins':            { name:'Fell Twins',                      x:-104.03,  y:132.13,  level:1, zone:'mountaintops'  },
    kill_loretta:                 { name:'Royal Knight Loretta',            x:-110.58,  y: 50.77,  level:1, zone:'caria_manor'   },
    physick_flask:                { name:'Third Church of Marika',          x:-180.125, y:123.403, level:1, zone:'limgrave'      },
    explosive_tear:               { name:'Erdtree Avatar (Liurnia SW)',     x:-149.594, y: 45.909, level:1, zone:'liurnia'       },
    ranni_quest_p1:               { name:"Ranni's Rise",                   x:-106.42,  y: 50.01,  level:1, zone:'caria_manor'   },
  };

  // Golden rune [9+] pickup clusters — sourced from router.js GOLDEN_RUNE_WAYPOINTS.
  const GOLDEN_RUNE_LOCS = [
    { name:"Golden Rune [10] — Guardian's Garrison",   x: -74.91,  y:160.85, level:1, runes:5000,  zone:'mountaintops' },
    { name:'Golden Rune [12] — Consecrated Snowfield', x: -77.16,  y:148.58, level:1, runes:13000, zone:'consecrated'  },
    { name:'Golden Rune [10] ×3 — Castle Sol',         x: -60.281, y:156.10, level:1, runes:15000, zone:'mountaintops' },
    { name:'Golden Rune [9] — Castle Sol',             x: -60.369, y:158.10, level:1, runes:3800,  zone:'mountaintops' },
    { name:'Golden Rune [9] — Caelid Treasure',        x:-174.56,  y:134.14, level:1, runes:3800,  zone:'caelid'       },
    { name:'Golden Rune [13] — Elphael',               x: -38.209, y:149.35, level:1, runes:22000, zone:'haligtree'    },
    { name:'Golden Rune [10] — Elphael (A)',           x: -36.853, y:149.58, level:1, runes:5000,  zone:'haligtree'    },
    { name:'Golden Rune [12] — Elphael (B)',           x: -39.356, y:149.74, level:1, runes:13000, zone:'haligtree'    },
    { name:'Golden Rune [10] — Elphael (C)',           x: -38.352, y:148.86, level:1, runes:5000,  zone:'haligtree'    },
    { name:'Golden Rune [13] — Mohgwyn Mausoleum',     x:-183.616, y:149.08, level:2, runes:22000, zone:'mohgwyn'      },
    { name:'Golden Rune [10] — Grand Cloister (A)',    x:-139.456, y: 56.23, level:2, runes:5000,  zone:'ainsel'       },
    { name:'Golden Rune [10] — Grand Cloister (B)',    x:-140.35,  y: 56.75, level:2, runes:5000,  zone:'ainsel'       },
  ];

  // S6 starting graces — anchors for Tier 2 proximity check.
  const S6_GRACE_LOCS = [
    { x:-185.78, y:102.10 }, { x: -73.56, y:141.78 }, { x: -37.10, y:149.13 },
    { x: -64.63, y:159.69 }, { x:-178.97, y:143.06 }, { x:-211.27, y:112.20 },
    { x:-156.20, y: 67.88 }, { x:-125.59, y: 73.51 }, { x:-100.79, y: 84.93 },
    { x: -84.37, y: 63.22 },
  ];

  function _dist(a, b) {
    return Math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2);
  }

  function _locKey(loc) {
    return `${Math.round(loc.x * 10)}_${Math.round(loc.y * 10)}_${loc.level || 1}`;
  }

  function _extractLocs(sqName, sqData) {
    if (!sqData) return [];
    const locs = [], seen = new Set();
    const add = arr => {
      if (!arr) return;
      for (const l of arr) {
        if (!l?.x || !l?.y) continue;
        const k = _locKey(l);
        if (!seen.has(k)) { seen.add(k); locs.push(l); }
      }
    };
    add(sqData.locations);
    if (sqData.location?.x) add([sqData.location]);
    add(sqData.vendor_locations);
    add(sqData.all_bosses);
    add(sqData.candidates);
    (sqData.groups  || []).forEach(g => add(g.locations));
    (sqData.bosses  || []).forEach(b => add(b.locations));
    return locs;
  }

  function _kind(sqData) {
    const t = sqData?.type || '';
    if (t.startsWith('boss'))    return 'boss';
    if (t.startsWith('dungeon')) return 'dungeon';
    if (t.startsWith('npc'))     return 'npc';
    return 'pickup';
  }

  // Parse "Smithing Stone (3)" / "Somber Smithing Stone (2)" → {tier, somber}
  // Only matches actual upgrade stones, not gloveworts or ancient dragon stones.
  function _parseStoneMarker(name) {
    if (!/^somber smithing stone|^smithing stone/i.test(name)) return null;
    const somber = /^somber/i.test(name);
    const m = name.match(/[([(\[](\d+)[)\]]/);
    if (!m) return null;
    return { tier: +m[1], somber };
  }

  // ── Tier 1 + Tier 2 generation ─────────────────────────────────────────────
  function generate(board, squareDataObj, allMarkers) {
    const sqDB = squareDataObj?.squares || {};
    // Smithing/Somber stone pickups from the full markers dataset
    const stoneNodes = (allMarkers || [])
      .filter(m => m.category === 'upgrade_materials' && m.x && m.y)
      .map(m => {
        const parsed = _parseStoneMarker(m.name || '');
        if (!parsed) return null;
        return { x: m.x, y: m.y, level: m.level || 1, zone: m.zone || '',
                 tier: parsed.tier, somber: parsed.somber, name: m.name };
      })
      .filter(Boolean);

    // ── Tier 1: all board locations + prereq locations ──────────────────────
    const t1Map = new Map();  // locKey → POI entry

    for (let i = 0; i < board.length; i++) {
      const sq   = board[i];
      const name = sq.raw?.name || '';
      const data = sqDB[name] || sqDB[sq.text] || {};
      const kind = _kind(data);
      const locs = _extractLocs(name, data);

      for (const loc of locs) {
        const k = _locKey(loc);
        if (!t1Map.has(k)) {
          t1Map.set(k, {
            tier: 1, kind,
            name: loc.name || name,
            x: loc.x, y: loc.y, level: loc.level || 1,
            zone: loc.zone || '',
            squareIdxes: [], squareNames: [],
          });
        }
        const entry = t1Map.get(k);
        if (!entry.squareIdxes.includes(i)) {
          entry.squareIdxes.push(i);
          entry.squareNames.push(sq.text || name);
        }
      }

      // Prereq stops required by this square
      for (const prereq of (data.prerequisites || [])) {
        const pl = PREREQ_STOPS[prereq];
        if (!pl) continue;
        const k = _locKey(pl);
        if (!t1Map.has(k)) {
          t1Map.set(k, {
            tier: 1, kind: 'prereq',
            name: pl.name, x: pl.x, y: pl.y,
            level: pl.level || 1, zone: pl.zone || '',
            prereqKey: prereq, squareIdxes: [], squareNames: [],
          });
        }
        // Don't double-add the same square for the same prereq
        const entry = t1Map.get(k);
        if (!entry.squareIdxes.includes(i)) {
          entry.squareIdxes.push(i);
          entry.squareNames.push(sq.text || name);
        }
      }
    }

    const tier1 = [...t1Map.values()];
    const anchors = [...tier1, ...S6_GRACE_LOCS];

    // ── Tier 2: stones + golden runes near anchors ──────────────────────────
    const tier2 = [];
    const seen2 = new Set();

    for (const stone of stoneNodes) {
      if (!stone.x || !stone.y) continue;
      if (!anchors.some(a => _dist(a, stone) <= TIER2_RADIUS)) continue;
      const k = `s_${_locKey(stone)}`;
      if (seen2.has(k)) continue;
      seen2.add(k);
      tier2.push({
        tier: 2, kind: 'stone',
        name: stone.name || `${stone.somber ? 'Somber Smithing' : 'Smithing'} Stone [${stone.tier}]`,
        x: stone.x, y: stone.y, level: stone.level || 1, zone: stone.zone || '',
        stoneTier: stone.tier, isSomber: !!stone.somber,
      });
    }

    for (const rune of GOLDEN_RUNE_LOCS) {
      if (!anchors.some(a => _dist(a, rune) <= TIER2_RADIUS)) continue;
      const k = `r_${_locKey(rune)}`;
      if (seen2.has(k)) continue;
      seen2.add(k);
      tier2.push({
        tier: 2, kind: 'rune',
        name: rune.name, x: rune.x, y: rune.y,
        level: rune.level || 1, zone: rune.zone,
        runes: rune.runes,
      });
    }

    return { tier1, tier2 };
  }

  // ── Square synergies ────────────────────────────────────────────────────────
  // Returns an array[25] where each element is an array of synergy objects
  // for that board position.
  function computeSynergies(board, squareDataObj) {
    const sqDB = squareDataObj?.squares || {};
    const synByIdx = Array.from({ length: 25 }, () => []);

    const locToSquares   = {};   // locKey → [squareIdxes]
    const zoneToSquares  = {};   // zone   → [squareIdxes]
    const squareLocs     = [];   // all extracted locs per board position

    for (let i = 0; i < board.length; i++) {
      const sq   = board[i];
      const name = sq.raw?.name || '';
      const data = sqDB[name] || sqDB[sq.text] || {};
      const locs = _extractLocs(name, data);
      squareLocs.push(locs);

      // Primary zone: whichever zone has the most locations
      const zc = {};
      for (const loc of locs) {
        const z = loc.zone || 'unknown';
        zc[z] = (zc[z] || 0) + 1;
      }
      const primaryZone = Object.entries(zc).sort((a, b) => b[1] - a[1])[0]?.[0] || 'unknown';
      if (!zoneToSquares[primaryZone]) zoneToSquares[primaryZone] = [];
      zoneToSquares[primaryZone].push(i);

      for (const loc of locs) {
        const k = _locKey(loc);
        if (!locToSquares[k]) locToSquares[k] = [];
        if (!locToSquares[k].includes(i)) locToSquares[k].push(i);
      }
    }

    // ── Co-location: 2+ squares share the exact same visit location ──────────
    for (const [, idxes] of Object.entries(locToSquares)) {
      if (idxes.length < 2) continue;
      for (let a = 0; a < idxes.length; a++) {
        for (let b = a + 1; b < idxes.length; b++) {
          synByIdx[idxes[a]].push({ type:'co_location', other:idxes[b], detail:'Same location — one visit for both' });
          synByIdx[idxes[b]].push({ type:'co_location', other:idxes[a], detail:'Same location — one visit for both' });
        }
      }
    }

    // ── Zone cluster: 3+ board squares in same zone ───────────────────────────
    for (const [zone, idxes] of Object.entries(zoneToSquares)) {
      if (idxes.length < 3 || zone === 'unknown') continue;
      const label = zone.replace(/_/g, ' ');
      for (const idx of idxes) {
        synByIdx[idx].push({
          type: 'zone_cluster', zone,
          others: idxes.filter(i => i !== idx),
          detail: `${idxes.length} squares in ${label}`,
        });
      }
    }

    // ── Prereq chain: which squares provide prereqs that other squares need ───
    // Build: locKey → prereq keys satisfied by visiting that location
    const locKeyToPrereqs = {};
    for (const [prereq, pl] of Object.entries(PREREQ_STOPS)) {
      const k = _locKey(pl);
      if (!locKeyToPrereqs[k]) locKeyToPrereqs[k] = [];
      locKeyToPrereqs[k].push(prereq);
    }

    // For each board square, collect which prereq keys its locations satisfy
    const squareProvides = [];   // [i] = Set of prereq keys that square i provides
    for (let i = 0; i < board.length; i++) {
      const provided = new Set();
      for (const loc of squareLocs[i]) {
        const k = _locKey(loc);
        for (const prereq of (locKeyToPrereqs[k] || [])) provided.add(prereq);
        // Also: exact-name match against PREREQ_STOPS (fuzzy proximity)
        for (const [prereq, pl] of Object.entries(PREREQ_STOPS)) {
          if (_dist(loc, pl) < 3) provided.add(prereq);
        }
      }
      squareProvides.push(provided);
    }

    for (let i = 0; i < board.length; i++) {
      const sq   = board[i];
      const name = sq.raw?.name || '';
      const data = sqDB[name] || sqDB[sq.text] || {};
      const prereqs = data.prerequisites || [];

      for (const prereq of prereqs) {
        if (!PREREQ_STOPS[prereq]) continue;  // only known prereqs shown
        // Find board squares that visit the prereq location
        for (let j = 0; j < board.length; j++) {
          if (j === i) continue;
          if (!squareProvides[j].has(prereq)) continue;
          // j provides, i needs
          if (!synByIdx[i].some(s => s.type === 'prereq_needs' && s.prereq === prereq && s.other === j)) {
            synByIdx[i].push({ type:'prereq_needs',    other:j, prereq, detail:`Needs ${prereq.replace(/_/g,' ')} (provided by sq ${j+1})` });
            synByIdx[j].push({ type:'prereq_provides', other:i, prereq, detail:`Unlocks ${prereq.replace(/_/g,' ')} for sq ${i+1}` });
          }
        }
      }
    }

    return synByIdx;
  }

  // ── Auto-run on board generation ────────────────────────────────────────────
  function _run() {
    if (!State.game.board?.length || !State.data.loaded) return;
    const { tier1, tier2 } = generate(State.game.board, State.data.squareData, State.data.markers);
    const synergies        = computeSynergies(State.game.board, State.data.squareData);
    State.emit('board:poisReady', { tier1, tier2, synergies });
  }

  function init() {
    State.on('board:new',    _run);
    State.on('game:loaded',  _run);
    State.on('data:loaded',  () => { if (State.game.board?.length) _run(); });
  }

  return { init, generate, computeSynergies };
})();
