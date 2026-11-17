/* Runs matches in Pyodide inside a Web Worker. The main thread owns the watchdog: it terminates this worker if no tick
   arrives for 10 s (covers a bot stuck inside one C call, which the line-count budget cannot interrupt).
   Messages in:  {type:'run', bots:[{name,source}], seed, ticks, base}   Messages out: {type:'ready'|'tick'|'done'|'error', ...} */
'use strict';
var PYODIDE = 'https://cdn.jsdelivr.net/pyodide/v0.27.7/full/';
var py = null, loading = null;

function boot(base, pyodideUrl) {
  if (loading) return loading;
  loading = (async function () {
    importScripts((pyodideUrl || PYODIDE) + 'pyodide.js');
    py = await loadPyodide({indexURL: pyodideUrl || PYODIDE});
    py.FS.mkdirTree('/app/engine');
    var listing = await fetch(base + 'engine_files.json');
    if (!listing.ok) throw new Error('could not load engine_files.json (' + listing.status + '). Run: python tools/build_site.py');
    var info = await listing.json();
    for (var i = 0; i < info.files.length; i++) {
      var r = await fetch(base + info.files[i] + '?v=' + info.hash);
      if (!r.ok) throw new Error('could not load ' + info.files[i] + ' (' + r.status + ')');
      py.FS.writeFile('/app/' + info.files[i], await r.text());
    }
    postMessage({type: 'version', version: info.version, hash: info.hash});
    py.runPython("import sys\nif '/app' not in sys.path: sys.path.insert(0, '/app')");
    postMessage({type: 'ready'});
  })();
  return loading;
}

self.onmessage = async function (e) {
  var m = e.data;
  try {
    if (m.type === 'boot') { await boot(m.base, m.pyodide); return; }
    if (m.type !== 'run') return;
    await boot(m.base, m.pyodide);
    py.globals.set('BOTS_JSON', JSON.stringify(m.bots));
    py.globals.set('SEED', m.seed);
    py.globals.set('TICKS', m.ticks || 400);
    py.globals.set('TICK_CB', function (t) { postMessage({type: 'tick', t: t}); });
    var out = py.runPython([
      'import json',
      'from engine import run_match, BotLoadError',
      'n = [0]',
      'def cb(frame):',
      '    n[0] += 1; TICK_CB(n[0] - 1)',
      'try:',
      '    r = run_match(json.loads(BOTS_JSON), seed=SEED, ticks=TICKS, on_frame=cb)',
      '    OUT = json.dumps(r, separators=(",", ":"), sort_keys=True)',
      'except BotLoadError as ex:',
      '    OUT = json.dumps({"load_error": str(ex)})',
      'OUT'].join('\n'));
    postMessage({type: 'done', replay: out});
  } catch (err) {
    postMessage({type: 'error', message: String(err && err.message || err)});
  }
};
