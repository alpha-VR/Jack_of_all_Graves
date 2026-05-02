// board.js — Jack of All Graves
// Renders 5x5 board, handles marking, emits POI requests.

const Board = (() => {
  let _el = null;  // board grid container

  function init(containerEl) {
    _el = containerEl;
    State.on('board:new',       _render);
    State.on('square:marked',   ({ marks }) => _applyMarks(marks));
    State.on('scores:updated',  ({ bingoLines }) => _highlightLines(bingoLines));
    State.on('board:poisReady', ({ synergies }) => _applySynergies(synergies));
    State.on('game:loaded',     () => {
      _render(State.game.board);
      _applyMarks(State.game.marks);
      _highlightLines(State.game.bingoLines);
    });
  }

  function _render(board) {
    if (!_el || !board?.length) return;
    _el.innerHTML = '';
    board.forEach((sq, idx) => {
      const cell = document.createElement('div');
      cell.className = 'cell';
      cell.dataset.idx = idx;

      const label = document.createElement('div');
      label.className = 'cell-text';
      label.textContent = sq.text;

      const poi = document.createElement('button');
      poi.className = 'cell-poi';
      poi.textContent = '📍';
      poi.title = 'Show locations on map';
      poi.addEventListener('click', e => {
        e.stopPropagation();
        const squareData = State.data.squareData?.squares?.[sq.raw.name];
        State.emit('poi:requested', { idx, sq, squareData });
        State.setPoiFocus(idx);
      });

      cell.appendChild(label);
      cell.appendChild(poi);
      cell.addEventListener('click', () => {
        const player = UI.getActivePlayer();
        State.markSquare(idx, player);
      });

      _el.appendChild(cell);
    });
  }

  function _applyMarks(marks) {
    if (!_el) return;
    _el.querySelectorAll('.cell').forEach(cell => {
      const idx  = +cell.dataset.idx;
      const mark = marks[idx];
      cell.classList.remove('mark-p1', 'mark-p2');
      cell.classList.toggle('mark-p1', mark === 0);
      cell.classList.toggle('mark-p2', mark === 1);
    });
  }

  function _highlightLines(bingoLines) {
    if (!_el) return;
    _el.querySelectorAll('.cell').forEach(c => c.classList.remove('bingo-p1','bingo-p2'));
    bingoLines[0].forEach(li =>
      State.BINGO_LINES[li].forEach(idx => _el.querySelector(`[data-idx="${idx}"]`)?.classList.add('bingo-p1'))
    );
    bingoLines[1].forEach(li =>
      State.BINGO_LINES[li].forEach(idx => _el.querySelector(`[data-idx="${idx}"]`)?.classList.add('bingo-p2'))
    );
  }

  // ── Synergy badges ──────────────────────────────────────────────────────────
  function _applySynergies(synergies) {
    if (!_el || !synergies) return;
    // Remove any existing badges (safe re-apply)
    _el.querySelectorAll('.cell-syn').forEach(el => el.remove());

    synergies.forEach((sqSyns, idx) => {
      if (!sqSyns.length) return;
      const cell = _el.querySelector(`[data-idx="${idx}"]`);
      if (!cell) return;

      const synEl = document.createElement('div');
      synEl.className = 'cell-syn';

      const types = new Set(sqSyns.map(s => s.type));

      if (types.has('co_location')) {
        const co = sqSyns.filter(s => s.type === 'co_location');
        const b  = document.createElement('span');
        b.className = 'syn-badge syn-coloc';
        b.textContent = '🔗';
        b.title = co.map(s => s.detail).join('\n');
        synEl.appendChild(b);
      }
      if (types.has('zone_cluster')) {
        const zc = sqSyns.find(s => s.type === 'zone_cluster');
        const b  = document.createElement('span');
        b.className = 'syn-badge syn-zone';
        b.textContent = '🗺';
        b.title = zc.detail;
        synEl.appendChild(b);
      }
      if (types.has('prereq_needs') || types.has('prereq_provides')) {
        const pr = sqSyns.find(s => s.type === 'prereq_needs' || s.type === 'prereq_provides');
        const b  = document.createElement('span');
        b.className  = 'syn-badge syn-prereq';
        b.textContent = types.has('prereq_provides') ? '🔑' : '⛓';
        b.title = pr.detail;
        synEl.appendChild(b);
      }

      if (synEl.children.length) cell.appendChild(synEl);
    });
  }

  return { init };
})();
