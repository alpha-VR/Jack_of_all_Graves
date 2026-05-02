// map.js — Jack of All Graves
// Leaflet map: surface + underground layers, markers, route overlay, POI.

const MapView = (() => {

  const _UG_ZONE_IDS = new Set(['siofra', 'ainsel', 'deeproot', 'mohgwyn']);
  // level field may be absent on older saves — fall back to zone name
  const _isUG = loc => loc.level === 2 || _UG_ZONE_IDS.has(loc.zone);

  // ── Calibrated bounds (verified from original app) ─────────────────────────
  const SURFACE_BOUNDS    = [[-235.7096, 33.4688], [-23.0207, 237.1583]];

  // Underground sub-zones — each has its own image overlay + bounds
  // Coordinates match the data.json x/y values for level:2 markers
  const UG_ZONES = {
    siofra: {
      name:   'Siofra River / Nokron',
      image:  '/data/underground_siofra.jpg',
      bounds: [[-192.3659, 118.2217], [-162.2844, 160.8600]],
    },
    ainsel: {
      name:   'Ainsel River / Lake of Rot',
      image:  '/data/underground_ainsel.jpg',
      bounds: [[-174.9268, 42.7769], [-109.1348, 80.8894]],
    },
    deeproot: {
      name:   'Deeproot Depths / Mohgwyn',
      image:  '/data/underground_deeproot.jpg',
      bounds: [[-114.0965, 103.4648], [-85.2376, 130.7871]],
    },
  };

  function coords(marker) { return [marker.x, marker.y]; }

  // ── Category config ────────────────────────────────────────────────────────
  const CAT_CONFIG = {
    site_of_grace:     { label:'Graces',       color:'#c8a96e', radius:6  },
    bosses:            { label:'Bosses',        color:'#e05a2a', radius:7  },
    npc:               { label:'NPCs',          color:'#6acea0', radius:5  },
    npc_invader:       { label:'Invaders',      color:'#f06060', radius:6  },
    weapons:           { label:'Weapons',       color:'#aaaacc', radius:5  },
    armor:             { label:'Armor',         color:'#88aacc', radius:4  },
    talismans:         { label:'Talismans',     color:'#ccaa44', radius:5  },
    spirit_ashes:      { label:'Spirits',       color:'#aa88cc', radius:5  },
    sorceries:         { label:'Sorceries',     color:'#66aaff', radius:5  },
    incantations:      { label:'Incantations',  color:'#ffaa66', radius:5  },
    ashes_of_war:      { label:'AoW',           color:'#88ccaa', radius:4  },
    key:               { label:'Key Items',     color:'#ffdd44', radius:5  },
    locations:         { label:'Locations',     color:'#777777', radius:4  },
    consumables:       { label:'Consumables',   color:'#99bbaa', radius:3  },
    upgrade_materials: { label:'Upgr. Mats',    color:'#bb9977', radius:3  },
    flask_upgrades:    { label:'Flask Items',   color:'#cc8844', radius:4  },
    waygates:          { label:'Waygates',      color:'#44ccdd', radius:5  },
    maps:              { label:'Map Fragments', color:'#ddcc44', radius:4  },
    materials:         { label:'Materials',     color:'#aabb99', radius:3  },
    shields:           { label:'Shields',       color:'#99aabb', radius:4  },
  };

  // Default: only the S6 starting graces shown — everything else off
  // The S6 graces are added as a dedicated layer, not through the filter system
  const DEFAULT_VISIBLE = new Set(); // nothing from regular filter system by default

  // S6 starting graces — shown always on surface layer regardless of filters
  const S6_STARTING_GRACES = [
    { id:'sg_gatefront',   name:'Gatefront Ruins',             x:-185.78, y:102.10 },
    { id:'sg_consecrated', name:'Inner Consecrated Snowfield', x: -73.56, y:141.78 },
    { id:'sg_haligtree',   name:'Haligtree Roots',             x: -37.10, y:149.13 },
    { id:'sg_snow_valley', name:'Snow Valley Ruins Overlook',  x: -64.63, y:159.69 },
    { id:'sg_aeonia',      name:'Inner Aeonia',                x:-178.97, y:143.06 },
    { id:'sg_ailing',      name:'Ailing Village Outskirts',    x:-211.27, y:112.20 },
    { id:'sg_scenic',      name:'Scenic Isle',                 x:-156.20, y: 67.88 },
    { id:'sg_labyrinth',   name:'Ruined Labyrinth',            x:-125.59, y: 73.51 },
    { id:'sg_altus_hwy',   name:'Altus Highway Junction',      x:-100.79, y: 84.93 },
    { id:'sg_iniquity',    name:'Road of Iniquity',            x: -84.37, y: 63.22 },
    { id:'sg_lake_rot',    name:'Lake of Rot Shoreside',       x:-128.46, y: 60.20, level:2 },
    { id:'sg_siofra',      name:'Siofra River Bank',           x:-184.90, y:130.58, level:2 },
  ];

  // ── State ──────────────────────────────────────────────────────────────────
  let _map          = null;
  let _layer        = 'surface';   // 'surface' | 'underground'
  let _surfaceImg   = null;        // surface image overlay
  let _ugOverlays   = {};          // zone → L.imageOverlay
  let _markers      = [];          // all data markers (both layers)
  let _s6Layer      = null;        // LayerGroup for S6 starting graces
  let _routeLayer   = null;
  let _poiLayer     = null;        // single-square POI focus (📍 button)
  let _t1PoiLayer   = null;        // board Tier 1 POIs (objectives + prereqs)
  let _t2PoiLayer   = null;        // board Tier 2 POIs (stones + runes)
  let _t1Visible    = false;
  let _t2Visible    = false;
  let _lastPOIs     = null;        // {tier1, tier2} cache for re-draws on layer switch
  let _filters      = new Set(DEFAULT_VISIBLE);
  let _searchTerm   = '';
  let _allData      = [];
  let _routeVisible = true;

  // ── Init ───────────────────────────────────────────────────────────────────
  function init(mapEl) {
    _map = L.map(mapEl, {
      crs:               L.CRS.Simple,
      minZoom:           -2,
      maxZoom:           9,
      zoomSnap:          0.25,
      zoomDelta:         0.5,
      attributionControl:false,
      preferCanvas:      true,
    });

    // Surface image
    _surfaceImg = L.imageOverlay('/data/map.jpg', SURFACE_BOUNDS).addTo(_map);

    // Underground image overlays (hidden by default)
    Object.entries(UG_ZONES).forEach(([key, zone]) => {
      _ugOverlays[key] = L.imageOverlay(zone.image, zone.bounds);
    });

    // fitBounds lets Leaflet auto-calculate zoom to fill the panel
    _map.fitBounds(SURFACE_BOUNDS, { padding: [10, 10] });

    // Layer groups (order = draw order, last = on top)
    _s6Layer    = L.layerGroup().addTo(_map);
    _t2PoiLayer = L.layerGroup().addTo(_map);  // T2 below T1 and route
    _t1PoiLayer = L.layerGroup().addTo(_map);
    _routeLayer = L.layerGroup().addTo(_map);
    _poiLayer   = L.layerGroup().addTo(_map);

    // Draw S6 graces immediately (before data loads)
    _drawS6Graces();

    // State events
    State.on('data:loaded',        _onDataLoaded);
    State.on('route:ready',        _onRouteReady);
    State.on('route:stepChanged',  _onStepChanged);
    State.on('map:focusStop',      _onFocusStop);
    State.on('map:poiFocus',       _onPoiFocus);
    State.on('board:poisReady',    _onBoardPOIsReady);
  }

  // ── S6 Starting Graces (always visible, prominent) ─────────────────────────
  function _drawS6Graces() {
    _s6Layer.clearLayers();
    const surfaceGraces = S6_STARTING_GRACES.filter(g => !g.level || g.level === 1);
    const ugGraces      = S6_STARTING_GRACES.filter(g => g.level === 2);
    const gracesToShow  = _layer === 'surface' ? surfaceGraces : ugGraces;

    gracesToShow.forEach(g => {
      // Outer ring
      const ring = L.circleMarker([g.x, g.y], {
        radius:10, fillColor:'#c8a96e', color:'#e8c88a',
        weight:2, fillOpacity:0.25,
      });
      // Inner dot
      const dot = L.circleMarker([g.x, g.y], {
        radius:5, fillColor:'#e8c88a', color:'#000',
        weight:1, fillOpacity:1,
      });
      dot.bindTooltip(`S6: ${g.name}`, { direction:'top', className:'map-tip s6-tip' });
      ring.bindTooltip(`S6: ${g.name}`, { direction:'top', className:'map-tip s6-tip' });
      _s6Layer.addLayer(ring);
      _s6Layer.addLayer(dot);
    });
  }

  // ── Data loaded ────────────────────────────────────────────────────────────
  function _onDataLoaded() {
    _allData = State.data.markers || [];
    _buildMarkers();
    // Apply current layer visibility
    _applyLayerVisibility();
  }

  // ── Build all markers (both layers) ───────────────────────────────────────
  function _buildMarkers() {
    _markers.forEach(m => { try { _map.removeLayer(m); } catch(e) {} });
    _markers = [];

    _allData.forEach(d => {
      const cfg    = CAT_CONFIG[d.category] || { color:'#666', radius:4 };
      const isUG   = d.level === 2;
      const isL3   = d.level === 3;

      const marker = L.circleMarker(coords(d), {
        radius:      cfg.radius,
        fillColor:   cfg.color,
        color:       'rgba(0,0,0,0.6)',
        weight:      1,
        fillOpacity: 0.85,
      });

      marker._data  = d;
      marker._isUG  = isUG;
      marker._isL3  = isL3;

      marker.bindTooltip(d.name, { permanent:false, direction:'top', className:'map-tip' });
      marker.on('click', () => State.emit('map:markerClicked', d));

      _markers.push(marker);
      // Don't add to map yet — _applyLayerVisibility will do it
    });
  }

  // ── Layer visibility: show only markers for current layer + active filters ─
  function _applyLayerVisibility() {
    const isUGLayer = _layer === 'underground';

    _markers.forEach(m => {
      const d       = m._data;
      const layerOk = isUGLayer ? (d.level === 2) : (d.level === 1 || !d.level);
      const filterOk= _filters.has(d.category);
      const searchOk= _matchesSearch(d);
      const show    = layerOk && filterOk && searchOk;

      if (show  && !_map.hasLayer(m)) m.addTo(_map);
      if (!show &&  _map.hasLayer(m)) _map.removeLayer(m);
    });
  }

  function _matchesSearch(d) {
    if (!_searchTerm) return true;
    const s = _searchTerm.toLowerCase();
    return (d.name||'').toLowerCase().includes(s) ||
           (d.description||'').toLowerCase().includes(s);
  }

  // ── Layer switch (surface ↔ underground) ──────────────────────────────────
  function setLayer(layer) {
    _layer = layer;
    const goingUG = layer === 'underground';

    // Toggle surface image
    if (goingUG) {
      _map.removeLayer(_surfaceImg);
      Object.values(_ugOverlays).forEach(o => o.addTo(_map));
      // Fit to Siofra as default underground view
      _map.fitBounds(UG_ZONES.siofra.bounds, { padding: [10, 10] });
    } else {
      Object.values(_ugOverlays).forEach(o => { try { _map.removeLayer(o); } catch(e){} });
      _surfaceImg.addTo(_map);
      _map.fitBounds(SURFACE_BOUNDS, { padding: [10, 10] });
    }

    // Redraw S6 graces for this layer
    _drawS6Graces();

    // Reapply marker visibility
    _applyLayerVisibility();

    // Re-render route + board POIs for the new layer
    if (State.route?.computed) _onRouteReady(State.route);
    if (_lastPOIs) _drawBoardPOIs(_lastPOIs.tier1, _lastPOIs.tier2);
  }

  // ── Route overlay ──────────────────────────────────────────────────────────
  function _onRouteReady(route) {
    _routeLayer.clearLayers();
    if (!_routeVisible) return;
    const stops = route.stops || [];
    const isUGLayer = _layer === 'underground';

    // Filter to only stops visible on this layer (skip _start and no-location stops)
    const visibleStops = stops.filter(s =>
      s.location?.x && (_isUG(s.location) === isUGLayer)
    );

    // Draw sequential path lines: prev stop → next stop
    for (let i = 1; i < visibleStops.length; i++) {
      const prev = visibleStops[i - 1];
      const cur  = visibleStops[i];

      // Check if there's a warp (big distance jump) vs natural travel
      const d = Math.sqrt(
        (prev.location.x - cur.location.x)**2 +
        (prev.location.y - cur.location.y)**2
      );
      const isWarp = cur.warpFrom && d > 15; // warp if far and has a grace source

      if (isWarp) {
        // Warp: dashed gold line (teleport)
        _routeLayer.addLayer(L.polyline(
          [coords(prev.location), coords(cur.location)],
          { color:'#c8a96e', weight:1.5, opacity:0.5, dashArray:'6,8' }
        ));
      } else {
        // Travel: solid path line
        _routeLayer.addLayer(L.polyline(
          [coords(prev.location), coords(cur.location)],
          { color:'#6acea0', weight:2, opacity:0.55 }
        ));
      }
    }

    // Draw stop markers on top of lines
    visibleStops.forEach((stop, visIdx) => {
      const globalIdx = stops.indexOf(stop);
      const isActive  = globalIdx === route.activeStop;
      const isStart   = stop.rawName === '_start';
      const isPrereq  = stop.isPrereq;
      const isRem     = stop.isRemembrance;

      const fillColor = isActive  ? '#e8c88a'
                      : isStart   ? '#c8a96e'
                      : isPrereq  ? '#f0c040'
                      : isRem     ? '#e05a2a'
                      : '#6acea0';

      // Outer pulse ring for active stop
      if (isActive) {
        _routeLayer.addLayer(L.circleMarker(coords(stop.location), {
          radius: 16, fillColor:'#e8c88a', color:'#e8c88a',
          weight:1, fillOpacity:0.12, interactive:false,
        }));
      }

      const circle = L.circleMarker(coords(stop.location), {
        radius:      isActive ? 10 : (isStart ? 8 : 7),
        fillColor,
        color:       isActive ? '#fff' : '#1a1610',
        weight:      isActive ? 2 : 1.5,
        fillOpacity: isActive ? 1 : 0.88,
      });

      // Number label
      const icon = L.divIcon({
        html: `<div class="route-num-label" style="color:${fillColor};font-size:${isActive?'11px':'9px'};font-weight:${isActive?'700':'600'}">${stop.num}</div>`,
        iconSize:[22,22], iconAnchor:[11,11], className:'',
      });
      _routeLayer.addLayer(L.marker(coords(stop.location), { icon, interactive:false }));

      circle.bindTooltip(`${stop.num}. ${stop.squareName}`, { direction:'top', className:'map-tip' });
      circle.on('click', () => State.setActiveStop(globalIdx));
      _routeLayer.addLayer(circle);
    });
  }

  function _onStepChanged({ idx, stop }) {
    if (!stop?.location?.x) return;
    // Auto-switch layer if the stop is on a different layer
    const stopIsUG = _isUG(stop.location);
    if (stopIsUG && _layer !== 'underground') {
      State.emit('map:requestLayerSwitch', 'underground');
    } else if (!stopIsUG && _layer !== 'surface') {
      State.emit('map:requestLayerSwitch', 'surface');
    }
    // Re-render route AFTER potential layer switch, then fly
    _onRouteReady(State.route);
    _map.panTo(coords(stop.location), { animate:true, duration:0.4 });
  }

  function _onFocusStop(stop) {
    if (!stop?.location?.x) return;
    _map.panTo(coords(stop.location), { animate:true, duration:0.4 });
  }

  // ── POI highlighting ───────────────────────────────────────────────────────
  function _onPoiFocus(squareIdx) {
    _poiLayer.clearLayers();
    if (squareIdx === null) return;

    const sq     = State.game.board[squareIdx];
    if (!sq) return;
    const sqData = State.data.squareData?.squares?.[sq.raw.name];
    if (!sqData) return;

    const locs = _getLocsFromSquareData(sqData);
    if (!locs.length) return;

    locs.forEach(loc => {
      if (!loc.x) return;
      const isUG = _isUG(loc);

      // Switch to the right layer if needed
      if (isUG && _layer !== 'underground') State.emit('map:requestLayerSwitch', 'underground');
      if (!isUG && _layer !== 'surface')    State.emit('map:requestLayerSwitch', 'surface');

      const ring = L.circleMarker(coords(loc), {
        radius:13, fillColor:'#fff', color:'#c8a96e',
        weight:2.5, fillOpacity:0.15,
      });
      const dot = L.circleMarker(coords(loc), {
        radius:7, fillColor:'#c8a96e', color:'none',
        weight:0, fillOpacity:0.9,
      });
      ring.bindTooltip(loc.name || sq.text, { permanent:false, direction:'top', className:'map-tip poi-tip' });
      _poiLayer.addLayer(ring);
      _poiLayer.addLayer(dot);
    });

    const first = locs.find(l => l.x);
    if (first) _map.panTo(coords(first), { animate:true, duration:0.5 });
  }

  function _getLocsFromSquareData(sqData) {
    if (!sqData) return [];
    const locs = [];
    const add  = arr => { if (arr) arr.forEach(l => { if (l?.x) locs.push(l); }); };
    switch (sqData.type) {
      case 'boss_specific': case 'dungeon_specific': case 'npc_action':
      case 'npc_invasion':  case 'consumable_action': case 'acquire_fixed':
        add(sqData.locations);
        if (sqData.location) locs.push(sqData.location);
        break;
      case 'boss_any': case 'boss_count': case 'dungeon_count':
      case 'acquire_count': case 'acquire_multi': case 'npc_kill':
        add(sqData.locations); break;
      case 'boss_region':        add(sqData.all_bosses);  break;
      case 'boss_tag':           add(sqData.candidates);  break;
      case 'boss_multi_type':    (sqData.groups||[]).forEach(g => add(g.locations)); break;
      case 'boss_multi_specific':(sqData.bosses||[]).forEach(b => add(b.locations)); break;
      default:
        add(sqData.locations);
        if (sqData.location) locs.push(sqData.location);
    }
    return locs;
  }

  // ── Board POI layers (Tier 1 / Tier 2) ────────────────────────────────────
  const _T1_KIND_COLOR = {
    boss:    '#e05a2a',
    dungeon: '#aa88cc',
    npc:     '#6acea0',
    pickup:  '#aaaacc',
    prereq:  '#f0c040',
  };

  function _onBoardPOIsReady({ tier1, tier2 }) {
    _lastPOIs = { tier1, tier2 };
    _drawBoardPOIs(tier1, tier2);
  }

  function _drawBoardPOIs(tier1, tier2) {
    _t1PoiLayer.clearLayers();
    _t2PoiLayer.clearLayers();
    const isUGLayer = _layer === 'underground';

    if (_t1Visible) {
      tier1
        .filter(p => _isUG(p) === isUGLayer)
        .forEach(p => {
          const color    = _T1_KIND_COLOR[p.kind] || '#c8a96e';
          const multi    = p.squareIdxes?.length > 1;
          const ringR    = multi ? 15 : 10;
          const dotR     = multi ? 8  : 5;

          const ring = L.circleMarker([p.x, p.y], {
            radius: ringR, fillColor: color, color: '#fff',
            weight: multi ? 2.5 : 1.5, fillOpacity: multi ? 0.40 : 0.25,
          });
          const dot = L.circleMarker([p.x, p.y], {
            radius: dotR, fillColor: color, color: '#000',
            weight: 1, fillOpacity: 0.9, interactive: false,
          });

          const tipLines = [p.name];
          if (p.squareNames?.length) tipLines.push(...p.squareNames.map(n => `· ${n}`));
          if (multi) tipLines[0] = `★ ${tipLines[0]}`;
          if (p.kind === 'prereq') tipLines.push(`(prereq: ${p.prereqKey})`);
          const tip = tipLines.join('\n');

          ring.bindTooltip(tip, { permanent: false, direction: 'top', className: 'map-tip poi-tip' });
          _t1PoiLayer.addLayer(ring);
          _t1PoiLayer.addLayer(dot);
        });
    }

    if (_t2Visible) {
      tier2
        .filter(p => _isUG(p) === isUGLayer)
        .forEach(p => {
          const color = p.kind === 'stone' ? '#bb9977' : '#ddcc44';
          const dot = L.circleMarker([p.x, p.y], {
            radius: 4, fillColor: color, color: '#000',
            weight: 0.5, fillOpacity: 0.80,
          });
          dot.bindTooltip(p.name, { permanent: false, direction: 'top', className: 'map-tip' });
          _t2PoiLayer.addLayer(dot);
        });
    }
  }

  function toggleBoardPoiTier(tier, on) {
    if (tier === 1) {
      _t1Visible = on;
      if (!on) _t1PoiLayer.clearLayers();
      else if (_lastPOIs) _drawBoardPOIs(_lastPOIs.tier1, _lastPOIs.tier2);
    } else if (tier === 2) {
      _t2Visible = on;
      if (!on) _t2PoiLayer.clearLayers();
      else if (_lastPOIs) _drawBoardPOIs(_lastPOIs.tier1, _lastPOIs.tier2);
    }
  }

  // ── Public API ─────────────────────────────────────────────────────────────
  function setFilter(cat, on) {
    if (on) _filters.add(cat); else _filters.delete(cat);
    _applyLayerVisibility();
  }

  function toggleFilter(cat) {
    setFilter(cat, !_filters.has(cat));
    return _filters.has(cat);
  }

  function setSearch(term) {
    _searchTerm = term.trim();
    _applyLayerVisibility();
  }

  function clearPoi() {
    _poiLayer.clearLayers();
  }

  function getLayer() { return _layer; }

  // ── AI route helpers ───────────────────────────────────────────────────────
  function panTo(x, y) {
    _map.panTo([x, y], { animate: true, duration: 0.4 });
  }

  function drawPolyline(xys, opts) {
    const line = L.polyline(xys.map(([x, y]) => [x, y]), opts).addTo(_map);
    return line;
  }

  function drawCircleMarker(x, y, opts) {
    const m = L.circleMarker([x, y], opts).addTo(_map);
    if (opts.tooltip) m.bindTooltip(opts.tooltip, { permanent: false });
    return m;
  }

  function removeLayer(layer) {
    if (layer) _map.removeLayer(layer);
  }

  function setRouteVisible(on) {
    _routeVisible = on;
    if (!on) {
      _routeLayer.clearLayers();
    } else if (State.route?.computed) {
      _onRouteReady(State.route);
    }
  }

  function getRouteVisible() { return _routeVisible; }

  return {
    init, setLayer, getLayer,
    setFilter, toggleFilter, setSearch, clearPoi,
    setRouteVisible, getRouteVisible,
    toggleBoardPoiTier,
    panTo, drawPolyline, drawCircleMarker, removeLayer,
    CAT_CONFIG, DEFAULT_VISIBLE,
  };
})();