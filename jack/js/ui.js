// ui.js — Jack of All Graves
// Score bar, route panel, modals, toasts, player toggle.

const UI = (() => {

  let _activePlayer = 0;  // 0=P1, 1=P2
  let _doneStops = new Set();  // stable stop keys (rawName|x_y) marked done

  // ── DOM refs (set in init) ────────────────────────────────────────────────
  let $scoreBar, $p1score, $p2score, $p1name, $p2name, $threatMsg;
  let $playerToggle;
  let $routePanel, $routeList, $routeWarnings, $routeToggle;
  let $boardOverlay, $boardGrid, $btnBoard;
  let $genBtn, $routeBtn, $saveBtn, $savesBtn;
  let $modal, $modalContent;
  let $toast;
  let $markerDetail;

  function init() {
    // Score bar
    $scoreBar    = document.getElementById('score-bar');
    $p1score     = document.getElementById('p1-score');
    $p2score     = document.getElementById('p2-score');
    $p1name      = document.getElementById('p1-name');
    $p2name      = document.getElementById('p2-name');
    $threatMsg   = document.getElementById('threat-msg');
    $playerToggle= document.getElementById('player-toggle');

    // Route panel
    $routePanel  = document.getElementById('route-panel');
    $routeList   = document.getElementById('route-list');
    $routeWarnings=document.getElementById('route-warnings');
    $routeToggle = document.getElementById('route-toggle');

    // Board overlay
    $boardOverlay = document.getElementById('board-overlay');
    $boardGrid    = document.getElementById('board-grid');
    $btnBoard     = document.getElementById('btn-board');

    // Buttons
    $genBtn      = document.getElementById('btn-generate');
    $routeBtn    = document.getElementById('btn-route');
    $saveBtn     = document.getElementById('btn-save');
    $savesBtn    = document.getElementById('btn-saves');

    // Modal + toast
    $modal       = document.getElementById('modal');
    $modalContent= document.getElementById('modal-content');
    $toast       = document.getElementById('toast');
    $markerDetail= document.getElementById('marker-detail');

    _bindEvents();
    _bindStateEvents();
    _updatePlayerToggle();
    _initBuildPanel();
  }

  // Shared RL route fetch — called from button and on mark changes
  async function _computeRlRoute({ silent = false } = {}) {
    try {
      const isDet = State.build.solver === 'det';
      const res = await fetch('/api/rl/route', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          raw_names:       State.game.board.map(sq => sq.raw.name),
          texts:           State.game.board.map(sq => sq.text),
          marks:           [...State.game.marks],
          player:          0,
          build:           State.build,
          solver:          State.build.solver ?? 'det',
          tsp_depth:       State.build.tspDepth ?? 8,
          lookahead_depth: State.build.lookaheadDepth ?? 2,
        }),
      });
      const rl = await res.json();
      if (rl.error) throw new Error(rl.error);
      const adapted = _adaptRlRoute(rl);
      const routeLabel = isDet ? 'Det Route' : 'AI Route';
      State.route.computed       = true;
      State.route.isRlRoute      = true;
      State.route.stops          = adapted.stops;
      State.route.passive        = [];
      State.route.warnings       = rl.model_found ? [] : ['Model not ready — showing random play'];
      State.route.summary        = {};
      State.route.targetLine     = null;
      State.route.targetLineName = routeLabel;
      State.route.lineSummary    = [];
      State.route.activeStop     = 0;
      State.emit('route:ready', State.route);
      if (!silent) toast(`${routeLabel} ready — ${adapted.stops.length} stops`, 'ok');
      return true;
    } catch(e) {
      return false;
    }
  }

  function _bindEvents() {
    // Route collapse toggle
    $routeToggle.addEventListener('click', () => {
      const collapsed = $routePanel.classList.toggle('collapsed');
      $routeToggle.textContent = collapsed ? '▶' : '▼';
    });

    // Board overlay toggle button
    $btnBoard.addEventListener('click', () => _toggleBoard());

    // Close board — ✕ button
    document.getElementById('btn-close-board').addEventListener('click', () => _closeBoard());

    // Close board — click backdrop (outside panel)
    $boardOverlay.addEventListener('click', e => {
      if (e.target === $boardOverlay) _closeBoard();
    });

    // Player toggle
    $playerToggle.addEventListener('click', () => {
      _activePlayer = 1 - _activePlayer;
      _updatePlayerToggle();
    });

    // Generate board
    $genBtn.addEventListener('click', () => {
      if (State.game.board.length > 0) {
        if (!confirm('Generate a new board? Current game will be lost unless saved.')) return;
      }
      try {
        State.generateBoard();
        toast('New board generated!', 'ok');
        $routeBtn.disabled = false;
        $btnBoard.disabled = false;
        _openBoard();
      } catch(e) {
        toast('Error generating board: ' + e.message, 'err');
      }
    });

    // Compute route — tries RL model first, falls back to JS router
    $routeBtn.addEventListener('click', async () => {
      if (!State.game.board.length) return toast('Generate a board first', 'warn');
      $routeBtn.disabled = true;
      $routeBtn.textContent = 'Computing...';
      try {
        const ok = await _computeRlRoute();
        if (!ok) {
          const result = Router.computeBestLine(State.game.board, State.data.squareData);
          State.route.isRlRoute = false;
          State.setRoute(result);
          toast(`Route ready — ${result.route.length} stops`, 'ok');
        }
      } catch(e) {
        toast('Route error: ' + e.message, 'err');
        console.error(e);
      } finally {
        $routeBtn.disabled = false;
        $routeBtn.textContent = '⚔ Compute Route';
      }
    });

    // Save
    $saveBtn.addEventListener('click', _showSaveDialog);

    // Saves list
    $savesBtn.addEventListener('click', _showSavesDialog);

    // Close modal on backdrop click
    $modal.addEventListener('click', e => { if (e.target === $modal) closeModal(); });

    // Edit player names
    [$p1name, $p2name].forEach((el, i) => {
      el.addEventListener('dblclick', () => {
        const name = prompt(`Player ${i+1} name:`, State.game.players[i]);
        if (name !== null) {
          State.game.players[i] = name.trim() || `P${i+1}`;
          el.textContent = State.game.players[i];
        }
      });
    });

    // Map marker click → show detail
    State.on('map:markerClicked', d => _showMarkerDetail(d));

    // Keyboard shortcuts
    document.addEventListener('keydown', e => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      if (e.key === 'Escape') { if ($boardOverlay.classList.contains('open')) _closeBoard(); else closeModal(); }
      if (e.key === 'b' || e.key === 'B') _toggleBoard();
      if (e.key === 'n' || e.key === 'N') State.advanceStop();
      if (e.key === 'Tab') { e.preventDefault(); $playerToggle.click(); }
    });
  }

  function _stopKey(stop) {
    const loc = stop.location;
    return stop.rawName + (loc ? `|${Math.round(loc.x*10)}_${Math.round(loc.y*10)}` : '');
  }

  function _bindStateEvents() {
    // Clear done stops only when a brand-new board is generated
    State.on('board:new', () => { _doneStops.clear(); });

    State.on('scores:updated', ({ scores, bingoLines, threats, noBingo }) => {
      $p1score.textContent = scores[0];
      $p2score.textContent = scores[1];
      _updateThreatBar(threats, bingoLines, noBingo, scores);
    });

    State.on('route:ready', _renderRoute);
    State.on('route:recomputed', route => {
      toast(`Route updated → ${route.targetLineName}`, 'ok');
    });
    State.on('route:stepChanged', ({ idx }) => _highlightRouteStop(idx));

    // Recompute route whenever a square is marked/unmarked
    State.on('square:marked', () => {
      if (!State.route.computed) return;
      if (State.route.isRlRoute) {
        setTimeout(() => _computeRlRoute({ silent: true }), 0);
      } else {
        setTimeout(() => State.recomputeRoute(), 0);
      }
    });

    State.on('game:saved', ({ name }) => toast(`Saved: ${name}`, 'ok'));
    State.on('game:loaded', () => {
      toast(`Game loaded: ${State.game.name}`, 'ok');
      $routeBtn.disabled = false;
      $btnBoard.disabled = false;
      _openBoard();
    });

    State.on('poi:requested', ({ sq, squareData }) => {
      if (!squareData) return toast('No location data for this square', 'warn');
    });
  }

  // ── Board overlay ─────────────────────────────────────────────────────────
  function _openBoard()   { $boardOverlay.classList.add('open'); }
  function _closeBoard()  { $boardOverlay.classList.remove('open'); }
  function _toggleBoard() { if (!State.game.board.length) return; $boardOverlay.classList.toggle('open'); }

  // ── Score bar ─────────────────────────────────────────────────────────────
  function _updatePlayerToggle() {
    const label = _activePlayer === 0
      ? `Marking as <span class="p1-tag">${State.game.players[0]}</span>`
      : `Marking as <span class="p2-tag">${State.game.players[1]}</span>`;
    $playerToggle.innerHTML = label + ' (Tab to switch)';
    $playerToggle.className = `player-toggle player-toggle--p${_activePlayer+1}`;
  }

  function _updateThreatBar(threats, bingoLines, noBingo, scores) {
    const LINE_NAMES = ['Row 1','Row 2','Row 3','Row 4','Row 5',
                        'Col 1','Col 2','Col 3','Col 4','Col 5','Diag ↘','Diag ↗'];

    let state = '';
    if (bingoLines[0].length > 0) {
      state = 'bingo-p1';
      $threatMsg.textContent = `🏆 ${State.game.players[0]} BINGO!`;
    } else if (bingoLines[1].length > 0) {
      state = 'bingo-p2';
      $threatMsg.textContent = `🏆 ${State.game.players[1]} BINGO!`;
    } else if (noBingo) {
      const [s0, s1] = scores || [0, 0];
      if (s0 > s1) {
        state = 'bingo-p1';
        $threatMsg.textContent = `🏆 ${State.game.players[0]} wins by majority (${s0}–${s1})`;
      } else if (s1 > s0) {
        state = 'bingo-p2';
        $threatMsg.textContent = `🏆 ${State.game.players[1]} wins by majority (${s1}–${s0})`;
      } else {
        state = 'warn';
        $threatMsg.textContent = `No bingo possible — tied at ${s0}, keep marking`;
      }
    } else {
      const danger = threats.filter(t => t.danger);
      if (danger.length > 0) {
        state = 'danger';
        const lineStr = danger.map(t => `${LINE_NAMES[t.lineIdx]} (${t.oppCount}/5)`).join(', ');
        $threatMsg.textContent = `⚠ Opponent threatening: ${lineStr}`;
      } else if (threats.length > 0) {
        state = 'warn';
        $threatMsg.textContent = `Opponent has ${threats[0].oppCount}/5 on ${LINE_NAMES[threats[0].lineIdx]}`;
      } else {
        $threatMsg.textContent = '';
      }
    }

    $scoreBar.className = state ? `score-bar ${state}` : 'score-bar';
    // Sync overlay backdrop tint without disturbing the open/closed state
    $boardOverlay.classList.remove('overlay-danger','overlay-bingo-p1','overlay-bingo-p2','overlay-warn');
    if (state && state !== 'warn') $boardOverlay.classList.add(`overlay-${state}`);
  }

  // ── RL route adapter ──────────────────────────────────────────────────────
  const _ZONE_DISPLAY = {
    limgrave:'Limgrave', weeping_peninsula:'Weeping Peninsula',
    stormveil:'Stormveil Castle', siofra:'Siofra River',
    liurnia:'Liurnia of the Lakes', caria_manor:'Caria Manor',
    caelid:'Caelid', dragonbarrow:'Dragonbarrow',
    altus_plateau:'Altus Plateau', mt_gelmir:'Mt. Gelmir',
    volcano_manor:'Volcano Manor', leyndell:'Leyndell, Royal Capital',
    deeproot:'Deeproot Depths', ainsel:'Ainsel River',
    mohgwyn:'Mohgwyn Palace', mountaintops:'Mountaintops of the Giants',
    consecrated:'Consecrated Snowfield', haligtree:'Haligtree',
    farum_azula:'Crumbling Farum Azula',
  };

  function _adaptRlRoute(rl) {
    const fmt = s => typeof Timing !== 'undefined'
      ? Timing.formatTime(s)
      : (s < 60 ? `${s}s` : `~${Math.floor(s/60)}m ${s%60>0?s%60+'s':''}`.trim());

    // Build raw-name → resolved text map so %num% etc. get substituted
    const rawToText = {};
    if (State.game?.board) {
      State.game.board.forEach(sq => { rawToText[sq.raw.name] = sq.text; });
    }

    // Pre-pass: count stops per square (used only when sq_count_needed is unavailable).
    const sqTotals   = {};   // rawName → total stop count (fallback denominator)
    const sqCounters = {};   // rawName → running visit index
    rl.stops.forEach(stop => {
      (stop.sq_names || []).forEach(rn => {
        sqTotals[rn] = (sqTotals[rn] || 0) + 1;
      });
    });
    // Preferred denominator: count_needed from RL response (actual locations required).
    const sqCountNeeded = rl.sq_count_needed || {};

    let runeAcc = 0;
    const stops = rl.stops.map((stop, i) => {
      const isSton  = stop.type === 'stone';
      const isRT    = stop.type === 'roundtable';
      const isGrace = stop.type === 'grace';
      let squareName;

      if (isRT) {
        squareName = 'Roundtable Hold — Upgrade Weapon';
      } else if (isSton) {
        squareName = `Stone [${stop.stone_tier}]${stop.stone_somber ? ' Somber' : ''}`;
      } else if (isGrace) {
        squareName = `Grace: ${stop.name}`;
      } else {
        // Prefer the first board square this stop contributes to (raw name available);
        // fall back to the completing-square text or bare location name.
        const primaryRaw = (stop.sq_names || []).find(rn => rawToText[rn]) || null;
        if (primaryRaw) {
          sqCounters[primaryRaw] = (sqCounters[primaryRaw] || 0) + 1;
          const needed = sqCountNeeded[primaryRaw] || sqTotals[primaryRaw] || 1;
          const countStr = needed > 1 ? ` (${sqCounters[primaryRaw]}/${needed})` : '';
          squareName = (rawToText[primaryRaw] || primaryRaw) + countStr;
        } else {
          squareName = stop.completes?.length
            ? (rawToText[stop.completes[0]] || stop.completes[0])
            : stop.name;
        }
      }

      const travel = stop.travel_sec  || 0;
      const action = stop.action_sec  || 0;
      const cum    = stop.cumulative_sec || 0;

      // Pull notes + prerequisites from squareData for the primary completed square
      const primarySquare = stop.completes?.[0];
      const sqData = primarySquare && State.data.squareData
        ? State.data.squareData[primarySquare] : null;
      const sqNotes = sqData?.notes || '';
      const sqPrereqs = sqData?.prerequisites || [];

      // Flags: additional completed squares + prerequisites from square data
      const extraCompletes = stop.completes?.length > 1
        ? stop.completes.slice(1).map(c => `✓ Completes: ${c}`) : [];
      const prereqFlags = sqPrereqs.map(p => `⚠ ${p}`);

      // Boss modifier constraint flags
      const _modifierLabels = {
        'hitless':            'Hitless run',
        'colossal_only':      'Colossal armaments only',
        'dagger_claw_fist':   'Daggers / claws / fists only',
        'bow_only':           'Bow only',
        'sorcery_only':       'Sorceries only',
        'incantation_only':   'Incantations only',
        'remembrance_weapon': 'Remembrance weapon only',
      };
      const modifierFlags = (stop.modifier_info || []).map(m => {
        const label = _modifierLabels[m.constraint] || m.constraint;
        const prep  = m.overhead_sec > 0 ? ` (+${fmt(m.overhead_sec)} prep)` : '';
        return `🔒 ${label}${prep}`;
      });

      const allFlags = [...extraCompletes, ...prereqFlags, ...modifierFlags];

      return {
        num:           i + 1,
        squareName,
        rawName:       stop.name,
        type:          isRT ? 'start' : (isSton ? 'acquire_fixed' : (isGrace ? 'grace' : 'boss_specific')),
        zone:          _ZONE_DISPLAY[stop.zone] || stop.zone || '',
        zoneId:        stop.zone,
        location:      stop.x != null ? { x: stop.x, y: stop.y, zone: stop.zone,
                         level: ['siofra','ainsel','deeproot','mohgwyn'].includes(stop.zone) ? 2 : 1 } : null,
        warpFrom:      null,
        backendTravelSec: stop.travel_sec || 0,
        flags:         allFlags,
        notes:         sqNotes,
        runes:         stop.runes || 0,
        runeTotal:     (runeAcc += (stop.runes || 0)),
        isRemembrance: false,
        isPrereq:      false,
        timing: {
          killSec:      action,
          travelSec:    travel,
          overheadSec:  0,
          totalSec:     travel + action,
          label:        fmt(travel + action),
          runningTotal: cum,
          runningLabel: fmt(cum),
          weaponLevel:  stop.weapon_level || 0,
          runeLevel:    stop.rune_level   || 1,
        },
      };
    });
    return { stops };
  }

  // ── Route panel ───────────────────────────────────────────────────────────
  function _renderRoute(route) {
    $routeList.innerHTML = '';
    $routeWarnings.innerHTML = '';

    // Target line banner
    if (route.targetLineName) {
      const banner = document.createElement('div');
      banner.className = 'target-line-banner';
      banner.innerHTML = `
        <span class="target-line-label">Targeting</span>
        <span class="target-line-name">${route.targetLineName}</span>
        <button class="line-scores-btn" id="btn-line-scores">All Lines ▾</button>
      `;
      $routeList.appendChild(banner);

      document.getElementById('btn-line-scores')?.addEventListener('click', () => {
        _showLineScores(route.lineSummary);
      });
    }

    if (route.warnings?.length) {
      route.warnings.forEach(w => {
        const el = document.createElement('div');
        el.className = 'route-warning';
        el.textContent = w;
        $routeWarnings.appendChild(el);
      });
    }

    route.stops.forEach((stop, i) => {
      const card = document.createElement('div');
      const stopKey = _stopKey(stop);
      const isDone = _doneStops.has(stopKey);
      card.dataset.idx = i;

      const isStart  = stop.rawName === '_start';
      const isBonus  = stop.type === 'bonus_pickup';
      const typeIcon = isStart ? '🐴' : isBonus ? '💰' : stop.isPrereq ? '⚡' : (stop.isRemembrance ? '💀' : _typeIcon(stop.type));
      card.className = `stop-card${i === route.activeStop ? ' active' : ''}${stop.isPrereq ? ' is-prereq' : ''}${isBonus ? ' is-bonus' : ''}${isDone ? ' stop-done' : ''}`;

      card.innerHTML = `
        <div class="stop-header">
          <span class="stop-num">${isBonus ? '★' : stop.num}</span>
          <span class="stop-icon">${typeIcon}</span>
          <span class="stop-name">${stop.squareName}</span>
        </div>
        <div class="stop-meta">
          <span class="stop-zone">${stop.zone || ''}</span>
          ${stop.warpFrom ? `<span class="stop-warp">⟳ ${stop.warpFrom.name}</span>` : ''}
          ${stop.runes    ? `<span class="stop-runes">✦ ${stop.runes.toLocaleString()} runes</span>` : ''}
          ${stop.timing?.label ? `<span class="stop-time" title="Travel: ${Timing.formatTime(stop.timing.travelSec)} | Kill: ${Timing.formatTime(stop.timing.killSec)}">⏱ ${stop.timing.label}</span>` : ''}
          ${stop.timing?.runningLabel ? `<span class="stop-running">${stop.timing.runningLabel}</span>` : ''}
        </div>
        ${stop.flags?.length ? `<div class="stop-flags">${stop.flags.map(f=>`<div class="stop-flag">${f}</div>`).join('')}</div>` : ''}
        ${stop.timing?.killSec > 0 ? `<div class="stop-timing-detail">🗡 ${Timing.formatTime(stop.timing.killSec)} fight · 🏃 ${Timing.formatTime(stop.timing.travelSec)} travel</div>` : ''}
        ${stop.notes ? `<div class="stop-notes">${stop.notes}</div>` : ''}
        <div class="stop-actions">
          ${stop.location?.x ? `<button class="stop-btn map-btn" data-idx="${i}">📍 Map</button>` : ''}
          ${!isStart ? `<button class="stop-btn done-btn" data-idx="${i}">${isBonus ? '💰 Grab' : '✓ Done'}</button>` : ''}
        </div>
      `;

      card.querySelector('.map-btn')?.addEventListener('click', e => {
        e.stopPropagation();
        State.focusStop(stop);
        State.setActiveStop(i);
      });
      card.querySelector('.done-btn')?.addEventListener('click', e => {
        e.stopPropagation();
        // Mark this stop as visually done (persists across recomputes)
        _doneStops.add(stopKey);
        card.classList.add('stop-done');
        card.querySelector('.done-btn').textContent = '✓';
        card.querySelector('.done-btn').disabled = true;
        // If it's a prereq stop, tell the router it's satisfied
        if (stop.rawName?.startsWith('_prereq_')) {
          const prereqKey = stop.rawName.slice('_prereq_'.length);
          State.addCompletedPrereq(prereqKey);
        }
        // Advance to next undone stop
        let next = i + 1;
        while (next < route.stops.length && _doneStops.has(_stopKey(route.stops[next]))) next++;
        if (next < route.stops.length) State.setActiveStop(next);
        _scrollToActive();
      });
      card.addEventListener('click', () => {
        State.setActiveStop(i);
        State.focusStop(stop);
      });

      $routeList.appendChild(card);
    });

    // Passive squares
    if (route.passive?.length) {
      const heading = document.createElement('div');
      heading.className = 'passive-heading';
      heading.textContent = `Passive / No Location (${route.passive.length})`;
      $routeList.appendChild(heading);

      route.passive.forEach(sq => {
        const el = document.createElement('div');
        el.className = 'passive-card';
        el.innerHTML = `<span class="passive-name">${sq.squareName}</span>
          ${sq.data?.notes ? `<div class="passive-notes">${sq.data.notes}</div>` : ''}`;
        $routeList.appendChild(el);
      });
    }
  }

  function _typeIcon(type) {
    const icons = {
      boss_specific:'⚔', boss_any:'⚔', boss_count:'⚔', boss_tag:'⚔',
      boss_region:'⚔', boss_modifier:'🎯', boss_multi_type:'⚔', boss_multi_specific:'⚔',
      dungeon_count:'🏛', dungeon_specific:'🏛',
      acquire_multi:'📦', acquire_count:'📦', acquire_fixed:'📦',
      restore_rune:'✦', npc_action:'💬', npc_invasion:'🩸', npc_kill:'🗡',
      consumable_action:'🧪', passive_runes:'📊', passive_stat:'📊',
      bonus_pickup:'💰', start:'🐴', grace:'✨',
    };
    return icons[type] || '●';
  }

  function _highlightRouteStop(idx) {
    $routeList.querySelectorAll('.stop-card').forEach(c => {
      c.classList.toggle('active', +c.dataset.idx === idx);
    });
    _scrollToActive();
  }

  function _scrollToActive() {
    const active = $routeList.querySelector('.stop-card.active');
    active?.scrollIntoView({ behavior:'smooth', block:'nearest' });
  }

  // ── Marker detail panel ───────────────────────────────────────────────────
  function _showMarkerDetail(d) {
    $markerDetail.innerHTML = `
      <div class="detail-cat">${d.category?.replace(/_/g,' ')}</div>
      <div class="detail-name">${d.name}</div>
      ${d.description ? `<div class="detail-desc">${d.description}</div>` : ''}
      <div class="detail-coords">x: ${d.x?.toFixed(2)}, y: ${d.y?.toFixed(2)}</div>
    `;
    $markerDetail.classList.add('visible');
  }

  // ── Save dialog ───────────────────────────────────────────────────────────
  function _showSaveDialog() {
    const defaultName = `S6-${new Date().toLocaleDateString('en-GB',{day:'2-digit',month:'short'})}`;
    showModal(`
      <h2>Save Game</h2>
      <input id="save-name-input" class="modal-input" placeholder="Game name" value="${State.game.name === 'New Game' ? defaultName : State.game.name}">
      <div class="modal-btns">
        <button id="modal-save-confirm" class="modal-btn primary">Save</button>
        <button class="modal-btn" onclick="UI.closeModal()">Cancel</button>
      </div>
    `);
    const input = document.getElementById('save-name-input');
    input.focus(); input.select();
    document.getElementById('modal-save-confirm').addEventListener('click', async () => {
      const name = input.value.trim() || defaultName;
      closeModal();
      await State.saveGame(name);
    });
  }

  // ── Saves list dialog ─────────────────────────────────────────────────────
  async function _showSavesDialog() {
    showModal('<h2>Saved Games</h2><div id="saves-list-loading">Loading...</div>');
    const saves = await State.listSaves();
    const container = document.getElementById('saves-list-loading');
    if (!container) return;

    if (!saves.length) {
      container.innerHTML = '<div class="saves-empty">No saved games yet.</div>';
      return;
    }

    container.id = 'saves-list';
    container.innerHTML = saves.map(s => `
      <div class="save-row" data-id="${s.id}">
        <div class="save-info">
          <div class="save-name">${s.name}</div>
          <div class="save-meta">${s.mode} · P1: ${s.p1score} · P2: ${s.p2score} · ${s.savedAt ? new Date(s.savedAt).toLocaleString() : ''}</div>
        </div>
        <div class="save-row-btns">
          <button class="save-load-btn modal-btn primary" data-id="${s.id}">Load</button>
          <button class="save-del-btn modal-btn danger" data-id="${s.id}">Del</button>
        </div>
      </div>
    `).join('');

    container.querySelectorAll('.save-load-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        closeModal();
        try { await State.loadGame(btn.dataset.id); }
        catch(e) { toast('Load failed: ' + e.message, 'err'); }
      });
    });

    container.querySelectorAll('.save-del-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (!confirm('Delete this save?')) return;
        await State.deleteSave(btn.dataset.id);
        btn.closest('.save-row').remove();
      });
    });
  }

  // ── Modal ─────────────────────────────────────────────────────────────────
  function showModal(html) {
    $modalContent.innerHTML = html;
    $modal.classList.add('open');
  }

  function closeModal() {
    $modal.classList.remove('open');
    $modalContent.innerHTML = '';
  }

  // ── Toast ─────────────────────────────────────────────────────────────────
  let _toastTimer = null;
  function toast(msg, type='ok') {
    $toast.textContent = msg;
    $toast.className = `toast toast-${type} show`;
    clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => $toast.classList.remove('show'), 3000);
  }

  // ── Build panel ──────────────────────────────────────────────────────────
  function _initBuildPanel() {
    const panel = document.getElementById('build-panel');
    if (!panel || typeof Timing === 'undefined') return;

    const weaponClasses = [
      'Dagger','Straight Sword','Light Greatsword','Greatsword','Colossal Sword',
      'Thrusting Sword','Curved Sword','Curved Greatsword','Katana','Twinblade',
      'Axe','Greataxe','Hammer','Great Hammer','Colossal Weapon',
      'Spear','Great Spear','Halberd','Reaper','Fist','Claw',
      'Sacred Seal','Glintstone Staff',
    ];

    panel.innerHTML = `
      <div class="build-row">
        <label class="build-label">Weapon class</label>
        <select id="build-wc" class="build-select">
          ${weaponClasses.map(wc =>
            `<option value="${wc}" ${wc===State.build.weaponClass?'selected':''}>${wc}</option>`
          ).join('')}
        </select>
      </div>
      <div class="build-row">
        <label class="build-label">Primary stat</label>
        <select id="build-stat" class="build-select">
          ${['Strength','Dexterity','Quality','Faith','Int'].map(s =>
            `<option value="${s}" ${s===State.build.primaryStat?'selected':''}>${s}</option>`
          ).join('')}
        </select>
      </div>
      <div class="build-row">
        <label class="build-label">Somber weapon?</label>
        <input type="checkbox" id="build-somber" ${State.build.isSomber?'checked':''}>
      </div>
      <div class="build-row">
        <label class="build-label">Solver</label>
        <div class="solver-toggle" id="solver-toggle">
          <button class="solver-btn ${State.build.solver!=='det'?'active':''}" data-solver="rl">AI Agent</button>
          <button class="solver-btn ${State.build.solver==='det'?'active':''}" data-solver="det">Deterministic</button>
        </div>
      </div>
      <div class="build-row" id="det-options" style="display:${State.build.solver==='det'?'flex':'none'}">
        <label class="build-label">Route depth</label>
        <select id="build-tsp-depth">
          ${[4,6,8,10,12].map(d => `<option value="${d}" ${(State.build.tspDepth??8)===d?'selected':''}>${d} squares</option>`).join('')}
        </select>
      </div>
      <div class="build-row" id="det-lookahead" style="display:${State.build.solver==='det'?'flex':'none'}">
        <label class="build-label">Opp. lookahead</label>
        <select id="build-lookahead">
          ${[{v:0,l:'Off'},{v:1,l:'1 move'},{v:2,l:'2 moves'},{v:3,l:'3 moves'}].map(({v,l}) =>
            `<option value="${v}" ${(State.build.lookaheadDepth??2)===v?'selected':''}>${l}</option>`).join('')}
        </select>
      </div>
    `;

    panel.querySelector('#build-wc')?.addEventListener('change', e =>
      State.setBuild({ weaponClass: e.target.value }));
    panel.querySelector('#build-stat')?.addEventListener('change', e =>
      State.setBuild({ primaryStat: e.target.value }));
    panel.querySelector('#build-somber')?.addEventListener('change', e =>
      State.setBuild({ isSomber: e.target.checked }));
    panel.querySelector('#solver-toggle')?.addEventListener('click', e => {
      const btn = e.target.closest('.solver-btn');
      if (!btn) return;
      State.setBuild({ solver: btn.dataset.solver });
      panel.querySelectorAll('.solver-btn').forEach(b =>
        b.classList.toggle('active', b === btn));
      const isDet = btn.dataset.solver === 'det';
      panel.querySelector('#det-options').style.display  = isDet ? 'flex' : 'none';
      panel.querySelector('#det-lookahead').style.display = isDet ? 'flex' : 'none';
    });
    panel.querySelector('#build-tsp-depth')?.addEventListener('change', e =>
      State.setBuild({ tspDepth: parseInt(e.target.value) }));
    panel.querySelector('#build-lookahead')?.addEventListener('change', e =>
      State.setBuild({ lookaheadDepth: parseInt(e.target.value) }));
  }

  // ── Line scores modal ────────────────────────────────────────────────────
  function _showLineScores(lineSummary) {
    if (!lineSummary?.length) return;

    const feasible = lineSummary.filter(x => x.feasible);
    const minAdj   = feasible.length ? Math.min(...feasible.map(x => x.adjustedCost ?? x.cost)) : Infinity;

    const rows = lineSummary.map(ls => {
      const isBest  = ls.feasible && (ls.adjustedCost ?? ls.cost) === minAdj;
      const icon    = ls.blocked ? '🚫' : (!ls.feasible ? '✗' : (isBest ? '⭐' : '✓'));
      const adjCost = ls.adjustedCost ?? ls.cost;
      const costStr = ls.feasible && adjCost !== Infinity ? adjCost.toFixed(0) : '—';
      const blockTag= ls.blocksOpp ? ' <span class="ls-block-tag">🛡 blocks opp</span>' : '';
      const cls = ls.blocked ? 'ls-blocked' : (!ls.feasible ? 'ls-nofeasible' : (isBest ? 'ls-best' : ''));
      return `<div class="ls-row ${cls}">
        <span class="ls-icon">${icon}</span>
        <span class="ls-name">${ls.name}${blockTag}</span>
        <span class="ls-cost">${costStr}</span>
      </div>`;
    }).join('');

    showModal(`
      <h2>Line Scores</h2>
      <div class="ls-legend">Lower score = cheaper · 🛡 = also blocks opponent threat</div>
      <div class="ls-table">${rows}</div>
      <div class="modal-btns" style="margin-top:14px">
        <button class="modal-btn primary" onclick="UI.closeModal()">Close</button>
      </div>
    `);
  }

  return {
    init,
    getActivePlayer: () => _activePlayer,
    showModal, closeModal, toast,
  };
})();