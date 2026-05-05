// state.js — Jack of All Graves
// Single source of truth. All modules read from here, talk via events.
// No module imports another module directly.

const State = (() => {

  // ── Event bus ──────────────────────────────────────────────────────────────
  const _listeners = {};
  function on(evt, fn)  { (_listeners[evt] = _listeners[evt] || []).push(fn); }
  function off(evt, fn) { if (_listeners[evt]) _listeners[evt] = _listeners[evt].filter(f => f !== fn); }
  function emit(evt, data) {
    (_listeners[evt] || []).forEach(fn => { try { fn(data); } catch(e) { console.error(`[State:${evt}]`, e); } });
  }

  // ── All 12 bingo lines on a 5x5 board ─────────────────────────────────────
  const BINGO_LINES = (() => {
    const lines = [];
    for (let r = 0; r < 5; r++) lines.push([0,1,2,3,4].map(c => r*5+c)); // rows
    for (let c = 0; c < 5; c++) lines.push([0,1,2,3,4].map(r => r*5+c)); // cols
    lines.push([0,6,12,18,24]); // diagonal TL-BR
    lines.push([4,8,12,16,20]); // diagonal TR-BL
    return lines;
  })();

  // ── Game state ─────────────────────────────────────────────────────────────
  const game = {
    id:        null,
    name:      'New Game',
    mode:      '1v1',
    season:    's6',
    players:   ['P1', 'P2'],
    board:     [],          // [{raw, text, rolled}] x25
    marks:     new Array(25).fill(-1),  // -1=none, 0=P1, 1=P2
    scores:    [0, 0],
    bingoLines:[[], []],    // line indices complete per player
    createdAt: null,
    savedAt:   null,
  };

  // ── Route state ────────────────────────────────────────────────────────────
  const route = {
    computed:         false,
    stops:            [],
    passive:          [],
    warnings:         [],
    summary:          {},
    activeStop:       0,
    targetLine:       null,
    targetLineName:   '',
    lineSummary:      [],
    completedPrereqs: new Set(), // prereq keys the player has manually marked done
  };

  // ── Build state (player's weapon/class setup) ────────────────────────────
  const build = {
    weaponClass: 'Greatsword',
    isSomber:    false,
    primaryStat: 'Strength',
    // weaponLevel and runeLevel are computed from route progress
  };

  // ── Map state ──────────────────────────────────────────────────────────────
  const mapState = {
    layer:   'surface',
    filters: new Set(['site_of_grace', 'bosses', 'locations']),
    search:  '',
    poiSquareIdx: null,   // which square's POIs are currently shown
  };

  // ── Loaded data cache ──────────────────────────────────────────────────────
  const data = {
    markers:    null,
    squareData: null,
    pool:       null,
    loaded:     false,
  };

  // ── Helpers ────────────────────────────────────────────────────────────────
  function _recomputeScores() {
    const scores = [0, 0];
    const bingos = [[], []];
    for (let p = 0; p < 2; p++) {
      for (let i = 0; i < 25; i++) if (game.marks[i] === p) scores[p]++;
      BINGO_LINES.forEach((line, li) => {
        if (line.every(idx => game.marks[idx] === p)) bingos[p].push(li);
      });
    }
    game.scores     = scores;
    game.bingoLines = bingos;
  }

  // Returns threats to playerIdx from opponent
  // [{lineIdx, oppCount, danger(bool), blocked(bool)}] sorted by oppCount desc
  function opponentThreats(playerIdx) {
    const opp = 1 - playerIdx;
    return BINGO_LINES.map((line, li) => {
      const oppCount = line.filter(i => game.marks[i] === opp).length;
      const blocked  = line.some(i => game.marks[i] === playerIdx);
      return { lineIdx: li, oppCount, blocked, danger: oppCount >= 4 && !blocked };
    })
    .filter(t => t.oppCount > 0 && !t.blocked)
    .sort((a, b) => b.oppCount - a.oppCount);
  }

  // True when every line has ≥1 mark from each player → neither can bingo
  function noBingoPossible() {
    return BINGO_LINES.every(line => {
      const hasP0 = line.some(i => game.marks[i] === 0);
      const hasP1 = line.some(i => game.marks[i] === 1);
      return hasP0 && hasP1;
    });
  }

  // ── Public API ─────────────────────────────────────────────────────────────
  return {
    on, off, emit,
    BINGO_LINES,
    game, route, mapState, data, build,

    // ── Load all JSON data ──
    async loadData() {
      if (data.loaded) return;
      const [markers, squareData, pool] = await Promise.all([
        fetch('/data/markers.json').then(r => r.json()),
        fetch('/data/square_data.json').then(r => r.json()),
        fetch('/data/s6_base_bingo.json').then(r => r.json()),
      ]);
      data.markers    = markers;
      data.squareData = squareData;
      data.pool       = pool;
      data.loaded     = true;
      emit('data:loaded');
    },

    // ── Generate a new board ──
    generateBoard() {
      if (!data.loaded) throw new Error('Data not loaded yet');
      const pool = [...data.pool];
      // Fisher-Yates shuffle
      for (let i = pool.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [pool[i], pool[j]] = [pool[j], pool[i]];
      }
      game.board = pool.slice(0, 25).map(raw => {
        let text = raw.name;
        const rolled = {};
        for (const [k, v] of Object.entries(raw)) {
          if (k === 'name' || k === 'category' || !Array.isArray(v)) continue;
          const chosen = v[Math.floor(Math.random() * v.length)];
          rolled[k] = chosen;
          text = text.replace(`%${k}%`, chosen);
        }
        return { raw, text, rolled };
      });
      game.marks      = new Array(25).fill(-1);
      game.scores     = [0, 0];
      game.bingoLines = [[], []];
      game.createdAt  = new Date().toISOString();
      game.id         = null;
      route.computed  = false;
      route.stops     = [];
      route.completedPrereqs = new Set();
      emit('board:new', game.board);
      emit('scores:updated', { scores: game.scores, bingoLines: game.bingoLines, threats: [], noBingo: noBingoPossible() });
    },

    // ── Import a board from OCR matches ──
    // squares: array of 25 { entry, rolled } from OCR.matchAll()
    importBoard(squares) {
      if (!data.loaded) throw new Error('Data not loaded yet');
      if (squares.length !== 25) throw new Error('Need exactly 25 squares');
      game.board = squares.map(({ entry, rolled }) => {
        let text = entry.name;
        for (const [k, v] of Object.entries(rolled)) text = text.replace(`%${k}%`, v);
        return { raw: entry, text, rolled };
      });
      game.marks      = new Array(25).fill(-1);
      game.scores     = [0, 0];
      game.bingoLines = [[], []];
      game.createdAt  = new Date().toISOString();
      game.id         = null;
      route.computed  = false;
      route.stops     = [];
      route.completedPrereqs = new Set();
      emit('board:new', game.board);
      emit('scores:updated', { scores: game.scores, bingoLines: game.bingoLines, threats: [], noBingo: false });
    },

    // ── Mark a square ──
    markSquare(idx, player) {
      if (idx < 0 || idx > 24) return;
      // Toggle off if same player taps again
      game.marks[idx] = (game.marks[idx] === player) ? -1 : player;
      _recomputeScores();
      const threats = opponentThreats(0);
      emit('square:marked', { idx, mark: game.marks[idx], marks: [...game.marks] });
      emit('scores:updated', { scores: [...game.scores], bingoLines: game.bingoLines, threats, noBingo: noBingoPossible() });
    },

    opponentThreats,

    // ── Route ──
    setRoute(result) {
      route.computed       = true;
      route.passive        = result.passive        || [];
      route.warnings       = result.warnings       || [];
      route.summary        = result.summary        || {};
      route.targetLine     = result.targetLine     ?? null;
      route.targetLineName = result.targetLineName || '';
      route.lineSummary    = result.lineSummary    || [];
      route.activeStop     = 0;
      // Annotate stops with timing
      const rawStops = result.route || [];
      if (typeof Timing !== 'undefined') {
        const timed = Timing.processRoute(rawStops, build);
        route.stops       = timed.stops;
        route.totalTime   = timed.totalLabel;
        route.totalSec    = timed.totalSec;
      } else {
        route.stops = rawStops;
      }
      emit('route:ready', route);
    },

    // Update build config and re-annotate route with new timing
    setBuild(updates) {
      Object.assign(build, updates);
      if (route.computed && route.stops.length) {
        // Re-annotate existing stops with new build
        if (typeof Timing !== 'undefined') {
          const rawStops = route.stops.map(s => ({ ...s, timing: undefined }));
          const timed = Timing.processRoute(rawStops, build);
          route.stops     = timed.stops;
          route.totalTime = timed.totalLabel;
          route.totalSec  = timed.totalSec;
        }
        emit('build:updated', build);
        emit('route:ready', route);
      } else {
        emit('build:updated', build);
      }
    },

    // Called by UI when a prereq stop is marked done — persists across recomputes
    addCompletedPrereq(key) {
      route.completedPrereqs.add(key);
      this.recomputeRoute();
    },

    // Recompute route based on current marks (after square marked/unmarked)
    recomputeRoute() {
      if (!route.computed || !game.board.length || !data.loaded) return;
      try {
        const result = Router.recompute(game.board, data.squareData, game.marks, [...route.completedPrereqs]);
        route.computed       = true;
        const rawStops2 = result.route || [];
        const timed2 = (typeof Timing !== 'undefined') ? Timing.processRoute(rawStops2, build) : { stops: rawStops2, totalLabel: '', totalSec: 0 };
        route.stops          = timed2.stops;
        route.passive        = result.passive        || [];
        route.warnings       = result.warnings       || [];
        route.summary        = result.summary        || {};
        route.targetLine     = result.targetLine     ?? null;
        route.targetLineName = result.targetLineName || '';
        route.lineSummary    = result.lineSummary    || [];
        route.activeStop     = 0;
        emit('route:ready', route);
        emit('route:recomputed', route);
      } catch(e) {
        console.error('[State] recomputeRoute error:', e);
      }
    },

    setActiveStop(idx) {
      route.activeStop = Math.max(0, Math.min(idx, route.stops.length - 1));
      emit('route:stepChanged', { idx: route.activeStop, stop: route.stops[route.activeStop] });
    },

    advanceStop() { this.setActiveStop(route.activeStop + 1); },

    // ── Map ──
    setPoiFocus(squareIdx) {
      mapState.poiSquareIdx = squareIdx;
      emit('map:poiFocus', squareIdx);
    },

    focusStop(stop) {
      emit('map:focusStop', stop);
    },

    // ── Save / Load ──
    async saveGame(name) {
      game.name   = name || game.name;
      game.savedAt= new Date().toISOString();
      const payload = {
        name: game.name, mode: game.mode, season: game.season,
        players: game.players, board: game.board, marks: game.marks,
        p1score: game.scores[0], p2score: game.scores[1],
        route: route.computed
          ? { stops: route.stops, passive: route.passive, warnings: route.warnings, summary: route.summary }
          : null,
        savedAt: game.savedAt,
      };
      const res  = await fetch('/api/saves/put', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
      const json = await res.json();
      if (json.ok) { game.id = json.id; emit('game:saved', { id: json.id, name: game.name }); }
      return json;
    },

    async loadGame(id) {
      const res = await fetch(`/api/saves/get/${encodeURIComponent(id)}`);
      const d   = await res.json();
      if (d.error) throw new Error(d.error);
      game.id        = d.id;
      game.name      = d.name      || 'Untitled';
      game.mode      = d.mode      || '1v1';
      game.season    = d.season    || 's6';
      game.players   = d.players   || ['P1','P2'];
      game.board     = d.board     || [];
      game.marks     = d.marks     || new Array(25).fill(-1);
      game.savedAt   = d.savedAt;
      _recomputeScores();
      if (d.route) {
        route.computed  = true;
        route.stops     = d.route.stops    || [];
        route.passive   = d.route.passive  || [];
        route.warnings  = d.route.warnings || [];
        route.summary   = d.route.summary  || {};
        route.activeStop= 0;
      } else {
        route.computed = false; route.stops = [];
      }
      emit('board:new', game.board);
      emit('scores:updated', { scores: [...game.scores], bingoLines: game.bingoLines, threats: opponentThreats(0), noBingo: noBingoPossible() });
      if (route.computed) emit('route:ready', route);
      emit('game:loaded', game);
    },

    async listSaves() {
      return fetch('/api/saves/list').then(r => r.json());
    },

    async deleteSave(id) {
      return fetch('/api/saves/delete', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({id}) }).then(r => r.json());
    },
  };
})();
