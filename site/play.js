/* Play page: editor, worker, watchdog, viewer. Classic script. */
(function () {
  'use strict';
  var $ = function (id) { return document.getElementById(id); };
  var BASE = new URL('./', location.href).href;                      // the site folder (engine/, bots/ are copied in by tools/build_site.py)
  var params = new URLSearchParams(location.search);
  var worker = null, wd = null, running = false, manifest = [], viewer = CBViewer($('viewer')), getCode, setCode;
  var WATCHDOG_MS = +params.get('watchdog') || 10000;
  var PYODIDE = params.get('pyodide') || undefined;                  // tests point this at a local copy
  var STORE = 'cbcol.code.v1';

  function status(msg, bad) { $('status').textContent = msg; $('status').className = bad ? 'err' : ''; }
  function problems(text) { $('problems').textContent = text || ''; }
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }

  // ---------- share links: JSON -> deflate-raw -> base64url, in the URL fragment ----------
  function b64(buf) { var s = '', b = new Uint8Array(buf); for (var i = 0; i < b.length; i++) s += String.fromCharCode(b[i]); return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''); }
  function unb64(t) { t = t.replace(/-/g, '+').replace(/_/g, '/'); while (t.length % 4) t += '='; var s = atob(t), b = new Uint8Array(s.length); for (var i = 0; i < s.length; i++) b[i] = s.charCodeAt(i); return b; }
  async function pipe(bytes, stream) { var w = stream.writable.getWriter(); w.write(bytes); w.close(); return new Response(stream.readable).arrayBuffer(); }
  async function pack(obj) { return b64(await pipe(new TextEncoder().encode(JSON.stringify(obj)), new CompressionStream('deflate-raw'))); }
  async function unpack(t) { return JSON.parse(new TextDecoder().decode(await pipe(unb64(t), new DecompressionStream('deflate-raw')))); }
  window.CBShare = {pack: pack, unpack: unpack};

  var chals = [], chal = null;
  function done(key) { try { var d = JSON.parse(localStorage.getItem('cbcol.done') || '{}'); if (key) { d[key] = 1; localStorage.setItem('cbcol.done', JSON.stringify(d)); } return d; } catch (e) { return {}; } }
  function judge(c, r) {
    var me = r.result.scores[0], g = c.goal, why = [], win = r.result.winners.length === 1 && r.result.winners[0] === 0;
    if (g.win && !win) why.push('you did not win (' + me.stores + ' vs ' + r.result.scores[1].stores + ')');
    if (g.errors !== undefined && me.errors > g.errors) why.push(me.errors + ' error(s) in your bot');
    if (g.stat && g.gte !== undefined && me.stats[g.stat] < g.gte) why.push(g.stat + ' is ' + me.stats[g.stat] + ', need ' + g.gte);
    if (g.stat && g.lte !== undefined && me.stats[g.stat] > g.lte) why.push(g.stat + ' is ' + me.stats[g.stat] + ', must be at most ' + g.lte);
    if (g.stores_gte !== undefined && me.stores < g.stores_gte) why.push('stores ' + me.stores + ', need ' + g.stores_gte);
    return why;
  }
  function chalUi() {
    var d = done();
    $('chal').innerHTML = '<option value="">Free play</option>' + chals.map(function (c) { return '<option value="' + c.id + '">' + (d[c.id] ? '\u2713 ' : '') + c.title + '</option>'; }).join('');
    $('chal').value = chal ? chal.id : '';
    $('chalinfo').textContent = chal ? chal.blurb : '';
  }
  function pickChallenge(id) {
    chal = chals.filter(function (c) { return c.id === id; })[0] || null;
    if (chal) { $('opp').value = chal.opp; $('seed').value = chal.seed; }
    chalUi();
  }

  async function text(path) { var r = await fetch(BASE + path); if (!r.ok) throw new Error(path + ': ' + r.status); return r.text(); }

  function newWorker() {
    if (worker) worker.terminate();
    worker = new Worker('worker.js');
    worker.onmessage = onMsg;
    worker.onerror = function (e) { finish(); status('Worker crashed: ' + (e.message || 'unknown'), true); };
    worker.postMessage({type: 'boot', base: BASE, pyodide: PYODIDE});
  }
  function arm(label) {
    clearTimeout(wd);
    wd = setTimeout(function () {
      worker.terminate(); worker = null; finish();
      status('Match stopped: your bot made no progress for ' + (WATCHDOG_MS / 1000) + ' seconds (' + label + '). Look for an endless loop that the step counter cannot see.', true);
      newWorker();
    }, WATCHDOG_MS);
  }
  function finish() { clearTimeout(wd); running = false; $('run').disabled = false; }
  function onMsg(e) {
    var m = e.data;
    if (m.type === 'ready') { $('run').disabled = false; status('Python engine ready.'); }
    else if (m.type === 'tick') { arm('tick ' + m.t); status('Running… tick ' + m.t + ' / 400'); }
    else if (m.type === 'done') {
      finish();
      var r = JSON.parse(m.replay);
      if (r.load_error) { status('Could not start: ' + r.load_error, true); problems(r.load_error); return; }
      window.__replayJson = m.replay;
      problems(r.errors.filter(function (x) { return x[1] === 0; }).slice(0, 8).map(function (x) { return 'tick ' + x[0] + ': ' + x[2]; }).join('\n'));
      status('Done: ' + r.bots.map(function (b, i) { return b + ' ' + r.result.scores[i].stores; }).join(' · '));
      viewer.load(r);
      if (chal) {
        var why = judge(chal, r);
        if (!why.length) { done(chal.id); chalUi(); $('chalinfo').textContent = 'Challenge complete: ' + chal.title + '!'; }
        else $('chalinfo').textContent = 'Not yet: ' + why.join('; ') + '.';
      }
    } else if (m.type === 'error') { finish(); status('Error: ' + m.message, true); problems(m.message); }
  }

  async function run() {
    if (running) return;
    var oppName = $('opp').value, seed = parseInt($('seed').value, 10) || 1;
    running = true; $('run').disabled = true; problems('');
    status('Loading Python (first run downloads about 10 MB)…');
    try {
      var opp = await text('bots/' + oppName);
      var mine = getCode();
      if ($('ro').hidden) store(STORE, mine);
      arm('loading Python');
      worker.postMessage({type: 'run', base: BASE, pyodide: PYODIDE, seed: seed, ticks: 400, bots: [{name: 'you', source: mine}, {name: oppName.replace(/\.py$/, ''), source: opp}]});
    } catch (err) { finish(); status('Error: ' + err.message, true); }
  }

  var shared = null;
  async function editor() {
    var holder = $('editor'), start = store(STORE) || await text('bots/forager.py');
    if (shared) start = shared.code;
    var ta = document.createElement('textarea'); ta.value = start; ta.spellcheck = false; ta.setAttribute('aria-label', 'Bot code');
    ta.addEventListener('keydown', function (e) { if (e.key === 'Tab' && !e.shiftKey) { e.preventDefault(); var s = ta.selectionStart; ta.setRangeText('    ', s, ta.selectionEnd, 'end'); } });
    holder.appendChild(ta); getCode = function () { return ta.value; }; setCode = function (s) { ta.value = s; };
    if (shared) { ta.readOnly = true; $('ro').hidden = false; return; }          // shared code is read-only and never loads CodeMirror
    if (params.has('nocm')) return;
    try {                                                              // upgrade to CodeMirror 6 when the CDN is reachable
      var cm = await Promise.race([import('https://esm.sh/codemirror@6.0.1'), new Promise(function (_, rej) { setTimeout(rej, 6000); })]);
      var py = await import('https://esm.sh/@codemirror/lang-python@6.1.6');
      var view = new cm.EditorView({doc: ta.value, extensions: [cm.basicSetup, py.python(), cm.EditorView.theme({'&': {backgroundColor: '#10131a', color: '#e6edf7'}, '.cm-gutters': {backgroundColor: '#10131a', color: '#8d98ab'}}, {dark: true})], parent: holder});
      ta.remove(); getCode = function () { return view.state.doc.toString(); };
      setCode = function (s) { view.dispatch({changes: {from: 0, to: view.state.doc.length, insert: s}}); };
    } catch (e) { /* keep the textarea */ }
  }

  async function init() {
    $('run').disabled = true;
    if (/^#r=/.test(location.hash)) { try { shared = await unpack(location.hash.slice(3)); } catch (e) { status('That share link is damaged and could not be read.', true); } }
    try { manifest = JSON.parse(await text('bots/manifest.json')); } catch (e) { status('Could not load bots/manifest.json. Run python tools/build_site.py, then serve site/ over http (see README).', true); }
    $('opp').innerHTML = manifest.map(function (b) { return '<option value="' + b.file + '">' + b.name + ' · ' + b.blurb + '</option>'; }).join('');
    await editor();
    if (shared) { if (shared.opp) $('opp').value = shared.opp; if (shared.seed) $('seed').value = shared.seed; }
    $('run').addEventListener('click', run);
    $('reset').addEventListener('click', async function () { setCode(await text('bots/forager.py')); });
    try { chals = JSON.parse(await (await fetch('challenges.json')).text()); } catch (e) { chals = []; }
    chalUi();
    $('chal').addEventListener('change', function () { pickChallenge($('chal').value); });
    $('share').addEventListener('click', async function () {
      var url = location.href.split('#')[0] + '#r=' + await pack({v: 1, code: getCode(), opp: $('opp').value, seed: parseInt($('seed').value, 10) || 1});
      $('shbar').hidden = false; $('shareurl').value = url; $('shareurl').select();
      try { await navigator.clipboard.writeText(url); status('Share link copied (' + url.length + ' characters).'); } catch (e) { status('Copy the link from the box below.'); }
      if (url.length > 8000) status('That link is long (' + url.length + ' characters); some apps may cut it. Shorter code makes shorter links.', true);
    });
    $('fork').addEventListener('click', function () { var ta = document.querySelector('#editor textarea'); if (ta) ta.readOnly = false; $('ro').hidden = true; history.replaceState(null, '', location.pathname + location.search); });
    var seedFromUrl = params.get('seed'); if (seedFromUrl && !shared) $('seed').value = seedFromUrl;     // a share link's seed wins over ?seed=
    newWorker();
    window.__game = {viewer: viewer, run: run, get code() { return getCode(); }, set code(s) { setCode(s); }, get running() { return running; }};
    if (params.has('autorun')) { var wait = setInterval(function () { if (!$('run').disabled) { clearInterval(wait); run(); } }, 100); }
  }
  init();
})();
