#!/usr/bin/env python3
"""
Jack of All Graves - Local Server
Run this, then open http://localhost:8000
Saves go to ./saves/ (on D drive when project lives there)
"""
import http.server, json, os, re, sys, urllib.parse
from datetime import datetime

if getattr(sys, 'frozen', False):
    # Running as a PyInstaller bundle — static files are in _MEIPASS/jack/
    BASE_DIR = os.path.join(sys._MEIPASS, 'jack')
    # Saves live next to the .exe so they persist across runs
    SAVES = os.path.join(os.path.dirname(sys.executable), 'saves')
else:
    # Running from source
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    SAVES    = os.path.join(BASE_DIR, 'saves')

os.makedirs(SAVES, exist_ok=True)

def _rl_route(payload):
    try:
        from jack.rl.agent import generate_route
        return generate_route(
            raw_names       = payload.get('raw_names', []),
            texts           = payload.get('texts', []),
            marks           = payload.get('marks', [-1]*25),
            player          = payload.get('player', 0),
            build           = payload.get('build'),
            model_path      = payload.get('model_path'),
            max_steps       = payload.get('max_steps', 60),
            solver          = payload.get('solver', 'rl'),
            tsp_depth       = payload.get('tsp_depth', 8),
            lookahead_depth = payload.get('lookahead_depth', 2),
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'error': str(e), 'stops': []}

PORT = 8000

def safe_id(name):
    name = re.sub(r'[^\w\s\-]', '', name).strip()
    name = re.sub(r'\s+', '_', name)
    return (name or 'unnamed')[:64]

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if '/api/' in str(args[0] if args else ''):
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {fmt % args}")

    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path

        if p == '/api/saves/list':
            saves = []
            for f in sorted(os.listdir(SAVES)):
                if not f.endswith('.json'): continue
                try:
                    with open(os.path.join(SAVES, f)) as fh:
                        d = json.load(fh)
                    saves.append({'id': f[:-5], 'name': d.get('name','?'),
                                  'savedAt': d.get('savedAt',''), 'mode': d.get('mode','1v1'),
                                  'p1score': d.get('p1score',0), 'p2score': d.get('p2score',0)})
                except: pass
            return self._json(saves)

        m = re.match(r'^/api/saves/get/(.+)$', p)
        if m:
            sid   = urllib.parse.unquote(m.group(1))
            fpath = os.path.join(SAVES, safe_id(sid) + '.json')
            if os.path.exists(fpath):
                with open(fpath) as fh: return self._json(json.load(fh))
            return self._err(404, 'Not found')

        super().do_GET()

    def do_POST(self):
        p      = urllib.parse.urlparse(self.path).path
        length = int(self.headers.get('Content-Length', 0))
        body   = self.rfile.read(length) if length else b'{}'
        try:    payload = json.loads(body)
        except: return self._err(400, 'Bad JSON')

        if p == '/api/saves/put':
            name  = payload.get('name', 'unnamed')
            fid   = safe_id(name)
            fpath = os.path.join(SAVES, fid + '.json')
            payload['savedAt'] = datetime.now().isoformat()
            payload['id']      = fid
            with open(fpath, 'w') as fh: json.dump(payload, fh, indent=2)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Saved: {fid}.json")
            return self._json({'ok': True, 'id': fid})

        if p == '/api/saves/delete':
            fpath = os.path.join(SAVES, safe_id(payload.get('id','')) + '.json')
            if os.path.exists(fpath): os.remove(fpath)
            return self._json({'ok': True})

        if p == '/api/rl/route':
            return self._json(_rl_route(payload))

        self._err(404, 'Unknown')

    def do_OPTIONS(self):
        self.send_response(200); self._cors(); self.end_headers()

    def _json(self, data):
        b = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length', len(b))
        self._cors(); self.end_headers(); self.wfile.write(b)

    def _err(self, code, msg):
        b = json.dumps({'error': msg}).encode()
        self.send_response(code)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length', len(b))
        self._cors(); self.end_headers(); self.wfile.write(b)

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Access-Control-Allow-Methods','GET,POST,OPTIONS')
        self.send_header('Access-Control-Allow-Headers','Content-Type')

if __name__ == '__main__':
    import threading, time, webbrowser
    os.chdir(BASE_DIR)
    print(f"""
╔══════════════════════════════════════════╗
║    Jack of All Graves — Local Server     ║
╠══════════════════════════════════════════╣
║  http://localhost:{PORT}                   ║
║  Ctrl+C to stop                          ║
╚══════════════════════════════════════════╝
""")
    def _open_browser():
        time.sleep(1.2)
        webbrowser.open(f'http://localhost:{PORT}')
    threading.Thread(target=_open_browser, daemon=True).start()
    http.server.HTTPServer(('localhost', PORT), Handler).serve_forever()
