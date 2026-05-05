// ocr.js — Screenshot-to-board via Tesseract.js (offline, runs in browser)
//
// Usage:
//   const cells  = await OCR.extractCells(imageFile, onProgress);  // 25 raw strings
//   const matches = OCR.matchAll(cells, State.data.pool);           // 25 matched squares
//
// Tesseract language data (~10 MB) downloads from CDN on first use
// and is cached in IndexedDB — fully offline after that.

const OCR = (() => {

  let _worker     = null;
  let _workerBusy = false;

  // ── Worker lifecycle ────────────────────────────────────────────────────────
  async function _getWorker(onStatus) {
    if (_worker) return _worker;
    if (onStatus) onStatus('Initialising OCR engine…');
    _worker = await Tesseract.createWorker('eng', 1, {
      logger: m => {
        if (onStatus && m.status === 'loading tesseract core') onStatus('Loading OCR core…');
        if (onStatus && m.status === 'loading language traineddata') onStatus('Downloading language model (first run only)…');
        if (onStatus && m.status === 'initializing api') onStatus('Starting OCR engine…');
      },
    });
    // PSM 6 = single uniform block of text — best for isolated bingo cells
    await _worker.setParameters({ tessedit_pageseg_mode: '6' });
    return _worker;
  }

  // ── Image helpers ───────────────────────────────────────────────────────────
  function _loadImage(src) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload  = () => resolve(img);
      img.onerror = reject;
      img.src = (src instanceof Blob || src instanceof File)
        ? URL.createObjectURL(src)
        : src;
    });
  }

  function _toCanvas(img) {
    const c = document.createElement('canvas');
    c.width  = img.naturalWidth  || img.width;
    c.height = img.naturalHeight || img.height;
    c.getContext('2d').drawImage(img, 0, 0);
    return c;
  }

  // Preprocess a cell canvas for better OCR:
  //   • 2× upscale
  //   • grayscale
  //   • invert if dark background (Tesseract prefers dark text on white)
  function _prepareCell(src, sx, sy, sw, sh) {
    const SCALE = 2;
    const c   = document.createElement('canvas');
    c.width   = Math.round(sw * SCALE);
    c.height  = Math.round(sh * SCALE);
    const ctx = c.getContext('2d');

    ctx.drawImage(src, sx, sy, sw, sh, 0, 0, c.width, c.height);

    const id   = ctx.getImageData(0, 0, c.width, c.height);
    const data = id.data;

    // Convert to greyscale and measure average brightness
    let sum = 0;
    for (let i = 0; i < data.length; i += 4) {
      const grey = 0.299 * data[i] + 0.587 * data[i+1] + 0.114 * data[i+2];
      data[i] = data[i+1] = data[i+2] = grey;
      sum += grey;
    }
    const avg = sum / (data.length / 4);

    // Invert dark-on-light → light-on-dark so Tesseract sees black text on white
    if (avg < 140) {
      for (let i = 0; i < data.length; i += 4) {
        data[i]   = 255 - data[i];
        data[i+1] = 255 - data[i+1];
        data[i+2] = 255 - data[i+2];
      }
    }

    ctx.putImageData(id, 0, 0);
    return c;
  }

  // ── Main extraction ─────────────────────────────────────────────────────────
  async function extractCells(imgSource, onProgress, onStatus) {
    if (_workerBusy) throw new Error('OCR already running');
    _workerBusy = true;
    try {
      const worker = await _getWorker(onStatus);
      const img    = await _loadImage(imgSource);
      const base   = _toCanvas(img);

      const W = base.width, H = base.height;
      // Small inset (2 %) to avoid picking up grid border pixels
      const INSET_X = W * 0.02, INSET_Y = H * 0.02;
      const cellW = (W - 2 * INSET_X) / 5;
      const cellH = (H - 2 * INSET_Y) / 5;

      const texts = [];
      for (let row = 0; row < 5; row++) {
        for (let col = 0; col < 5; col++) {
          const sx = INSET_X + col * cellW;
          const sy = INSET_Y + row * cellH;
          const cell = _prepareCell(base, sx, sy, cellW, cellH);

          const { data: { text } } = await worker.recognize(cell);
          texts.push(text.replace(/\s+/g, ' ').trim());

          if (onProgress) onProgress((row * 5 + col + 1) / 25);
        }
      }
      return texts;
    } finally {
      _workerBusy = false;
    }
  }

  // ── Fuzzy matching ──────────────────────────────────────────────────────────

  // Sørensen–Dice coefficient on character trigrams.
  // Handles OCR typos well (single char substitutions, insertions, deletions).
  function _dice(a, b) {
    if (!a || !b) return 0;
    const tgA = new Set(), tgB = new Set();
    const pa = '  ' + a + '  ', pb = '  ' + b + '  ';
    for (let i = 0; i < pa.length - 2; i++) tgA.add(pa.slice(i, i+3));
    for (let i = 0; i < pb.length - 2; i++) tgB.add(pb.slice(i, i+3));
    let hits = 0;
    for (const g of tgA) if (tgB.has(g)) hits++;
    return (2 * hits) / (tgA.size + tgB.size);
  }

  function _norm(s) {
    return s.toLowerCase().replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ').trim();
  }

  // Build a flat list of { text, entry, rolled } for every rendered variant
  // of every pool entry (handles %num% etc. template substitution).
  function _buildIndex(pool) {
    const index = [];
    for (const entry of pool) {
      const tmplKeys = Object.keys(entry)
        .filter(k => k !== 'name' && k !== 'category' && Array.isArray(entry[k]));

      if (tmplKeys.length === 0) {
        index.push({ text: _norm(entry.name), entry, rolled: {} });
      } else {
        // Cartesian product of all template choices
        const combos = tmplKeys.reduce(
          (acc, k) => acc.flatMap(r => entry[k].map(v => ({ ...r, [k]: v }))),
          [{}]
        );
        for (const rolled of combos) {
          let text = entry.name;
          for (const [k, v] of Object.entries(rolled)) text = text.replace(`%${k}%`, v);
          index.push({ text: _norm(text), entry, rolled });
        }
      }
    }
    return index;
  }

  function _matchOne(rawText, index) {
    const q = _norm(rawText);
    let best = null, bestScore = -1;
    for (const item of index) {
      const score = _dice(q, item.text);
      if (score > bestScore) { bestScore = score; best = item; }
    }
    return best ? { ...best, confidence: bestScore } : { text: rawText, entry: null, rolled: {}, confidence: 0 };
  }

  // Returns array of 25 { entry, rolled, text, confidence, rawOcr }
  function matchAll(cellTexts, pool) {
    const index = _buildIndex(pool);
    return cellTexts.map(raw => {
      const m = _matchOne(raw, index);
      return { ...m, rawOcr: raw };
    });
  }

  // Exposed so the cell picker can reuse the variant index
  function buildVariants(pool) { return _buildIndex(pool); }

  return { extractCells, matchAll, buildVariants };
})();
