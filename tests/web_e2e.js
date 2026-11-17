// Real-browser end-to-end test. Needs: cd tests && npm install   (playwright-core + a local copy of Pyodide)
// Uses an installed Chromium (PLAYWRIGHT_CHROMIUM env var, or the Playwright cache). Run: node tests/web_e2e.js
'use strict';
const http = require('http'), fs = require('fs'), path = require('path'), os = require('os');
const { execFileSync } = require('child_process');
const { chromium } = require('playwright-core');

const ROOT = path.resolve(__dirname, '..');
const SITE = path.join(ROOT, 'site'), SUB = '/critterbots-colonies/';   // served under a sub-path, like GitHub Pages
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.py': 'text/plain',
  '.wasm': 'application/wasm', '.zip': 'application/zip', '.map': 'application/json', '.md': 'text/plain', '.mjs': 'text/javascript' };
const results = [];
function check(name, ok, detail) { results.push([name, !!ok, detail || '']); }

function findChrome() {
  if (process.env.PLAYWRIGHT_CHROMIUM) return process.env.PLAYWRIGHT_CHROMIUM;
  const base = path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), '.cache'), 'ms-playwright');
  const bases = [base, path.join(os.homedir(), '.cache', 'ms-playwright'), path.join(os.homedir(), 'Library', 'Caches', 'ms-playwright')];
  for (const b of bases) {
    if (!fs.existsSync(b)) continue;
    for (const d of fs.readdirSync(b).filter(x => /^chromium-\d+$/.test(x)).sort().reverse()) {
      for (const rel of ['chrome-win64/chrome.exe', 'chrome-win/chrome.exe', 'chrome-linux/chrome', 'chrome-linux64/chrome', 'chrome-mac/Chromium.app/Contents/MacOS/Chromium'])
        if (fs.existsSync(path.join(b, d, rel))) return path.join(b, d, rel);
    }
  }
  throw new Error('no Chromium found; set PLAYWRIGHT_CHROMIUM');
}

function serve() {
  const pyodideDir = path.join(__dirname, 'node_modules', 'pyodide');
  const srv = http.createServer((req, res) => {
    let p = decodeURIComponent(req.url.split('?')[0]);
    let file = null;
    if (p.startsWith('/pyodide/')) file = path.join(pyodideDir, p.slice(9));
    else if (p.startsWith(SUB)) file = path.join(SITE, p.slice(SUB.length));
    if (!file || !(file.startsWith(SITE) || file.startsWith(pyodideDir)) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); res.end('not found'); return; }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream', 'Access-Control-Allow-Origin': '*' });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise(r => srv.listen(0, '127.0.0.1', () => r(srv)));
}

const REF = `
import sys, json, hashlib
sys.path.insert(0, sys.argv[1])
from engine import run_match
def canon(r):
    r = dict((k, v) for k, v in r.items() if k != "diag")
    return hashlib.sha256(json.dumps(r, separators=(",", ":"), sort_keys=True).encode()).hexdigest()
web = json.load(open(sys.argv[2]))
bots = [{"name": "you", "source": open(sys.argv[1] + "/bots/forager.py", encoding="utf-8").read()},
        {"name": "farmer", "source": open(sys.argv[1] + "/bots/farmer.py", encoding="utf-8").read()}]
mine = run_match(bots, seed=7, ticks=400)
print(canon(web) + " " + canon(mine))
`;

(async () => {
  execFileSync(process.env.PYTHON || 'python', [path.join(ROOT, 'tools', 'build_site.py')], { stdio: 'inherit' });
  const srv = await serve(), port = srv.address().port, origin = 'http://127.0.0.1:' + port;
  const browser = await chromium.launch({ executablePath: findChrome(), headless: true });
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  const errors = [], requests = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('request', r => { if (!r.url().startsWith(origin)) requests.push(r.url()); });
  const url = (q) => `${origin}${SUB}play.html?nocm&pyodide=${encodeURIComponent(origin + '/pyodide/')}&${q}`;
  const t0 = Date.now();
  try {
    // 1. full match in a real browser, then compare with CPython byte for byte
    await page.goto(url('seed=7'));
    await page.selectOption('#opp', 'farmer.py');
    await page.waitForFunction(() => !document.getElementById('run').disabled, null, { timeout: 120000 });
    await page.click('#run');
    await page.waitForFunction(() => window.__replayJson, null, { timeout: 240000 });
    const replay = await page.evaluate(() => window.__replayJson);
    const tmp = path.join(os.tmpdir(), 'cb_web_replay.json');
    fs.writeFileSync(tmp, replay);
    const py = process.env.PYTHON || 'python';
    const out = execFileSync(py, ['-I', '-c', REF, ROOT, tmp], { encoding: 'utf8', timeout: 120000 }).trim().split(' ');
    check('browser (Pyodide) replay is byte-identical to CPython (400 ticks, seed 7)', out[0] === out[1], out.map(s => s.slice(0, 12)).join(' vs '));
    check('no console errors on the play page', errors.length === 0, errors.join(' | ').slice(0, 300));
    check('no requests left the local server (Pyodide served locally here)', requests.length === 0, requests.slice(0, 3).join(' '));

    // 2. viewer: banner at the end, fog view, scrubbing, inspector
    await page.evaluate(() => window.__game.viewer.setTick(400));
    const banner = await page.textContent('.cbv-banner');
    check('viewer shows a result banner at tick 400', /WINS|DRAW/.test(banner), banner.slice(0, 80));
    await page.evaluate(() => window.__game.viewer.setTick(200));
    const t = await page.evaluate(() => window.__game.viewer.state.t);
    check('scrub to tick 200 works', t === 200, 't=' + t);
    await page.selectOption('.cbv-controls select', '0');
    const persp = await page.evaluate(() => window.__game.viewer.state.persp);
    check('fog perspective switch works', persp === 0, 'persp=' + persp);
    const shot = path.join(os.tmpdir(), 'cb_play.png');
    await page.screenshot({ path: shot });
    check('screenshot taken', fs.statSync(shot).size > 20000, shot);

    // 3. watchdog: a bot stuck inside one C call (time.sleep) must be stopped
    await page.goto(url('seed=1&watchdog=3000'));
    await page.waitForFunction(() => !document.getElementById('run').disabled, null, { timeout: 120000 });
    await page.evaluate(() => { window.__game.code = 'import time\ndef act(view):\n    time.sleep(60)\n'; });
    await page.click('#run');
    await page.waitForFunction(() => /no progress/.test(document.getElementById('status').textContent), null, { timeout: 30000 });
    check('watchdog terminates a worker stuck in time.sleep and the page recovers', true);
    await page.waitForFunction(() => !document.getElementById('run').disabled, null, { timeout: 120000 });
    check('Run button usable again after the watchdog', true);

    // 4. blocked import shows a clear message
    await page.evaluate(() => { window.__game.code = 'import js\ndef act(view):\n    return {}\n'; });
    await page.click('#run');
    await page.waitForFunction(() => /not allowed/.test(document.getElementById('problems').textContent), null, { timeout: 120000 });
    check("'import js' in a bot is refused with a readable message", true);

    // 5. runtime error shows the line number
    await page.evaluate(() => { window.__game.code = 'def act(view):\n    x = 1\n    return {"units": 1 / 0}\n'; });
    await page.click('#run');
    await page.waitForFunction(() => /line 3: ZeroDivisionError/.test(document.getElementById('problems').textContent), null, { timeout: 120000 });
    check('runtime error is shown with its line number', true);

    // 6. share link round trip: packed in the fragment, opens read-only, same code and settings
    await page.goto(url('seed=1&watchdog=3000'));
    await page.waitForFunction(() => !document.getElementById('run').disabled, null, { timeout: 120000 });
    const myCode = ['import random', 'def act(view):', '    return {"units": {u["id"]: {"do": "move", "dir": random.choice("NESW")} for u in view["units"]}}  # café ñ', ''].join('\n');
    await page.evaluate((c) => { window.__game.code = c; }, myCode);
    await page.selectOption('#opp', 'forager.py');
    await page.fill('#seed', '5');
    await page.click('#share');
    await page.waitForFunction(() => document.getElementById('shareurl').value.length > 0, null, { timeout: 10000 });
    const link = await page.inputValue('#shareurl');
    check('share link is in the URL fragment and reasonably short', /#r=[A-Za-z0-9_-]+$/.test(link) && link.length < 1500, link.length + ' chars');
    const page2 = await browser.newPage({ viewport: { width: 1400, height: 900 } });
    page2.on('pageerror', e => errors.push('page2 error: ' + e.message));
    await page2.goto(link);
    await page2.waitForFunction(() => !document.getElementById('run').disabled, null, { timeout: 120000 });
    const shown = await page2.evaluate(() => ({ code: window.__game.code, ro: document.querySelector('#editor textarea').readOnly, banner: !document.getElementById('ro').hidden,
      opp: document.getElementById('opp').value, seed: document.getElementById('seed').value }));
    check('shared link restores code (with accents), opponent and seed', shown.code === myCode && shown.opp === 'forager.py' && shown.seed === '5', JSON.stringify(shown).slice(0, 120));
    check('shared code is read-only with a banner', shown.ro && shown.banner);
    await page2.click('#fork');
    check('"Edit a copy" makes the code editable', await page2.evaluate(() => !document.querySelector('#editor textarea').readOnly));
    const bad = await browser.newPage();
    await bad.goto(`${origin}${SUB}play.html?nocm&pyodide=${encodeURIComponent(origin + '/pyodide/')}#r=!!!not-valid`);
    await bad.waitForFunction(() => /damaged/.test(document.getElementById('status').textContent), null, { timeout: 30000 });
    check('a damaged share link shows a clear message', true);
    await page2.close(); await bad.close();

    // 7. challenge: the forager template beats the sleepwalker on the "beat the sleepwalker" challenge
    await page.goto(url('seed=1'));
    await page.waitForFunction(() => !document.getElementById('run').disabled && document.querySelectorAll('#chal option').length > 3, null, { timeout: 120000 });
    await page.evaluate(() => localStorage.clear());
    await page.selectOption('#chal', 'beat-sleep');
    const picked = await page.evaluate(() => ({ opp: document.getElementById('opp').value, seed: document.getElementById('seed').value }));
    check('picking a challenge sets its opponent and seed', picked.opp === 'sleepwalker.py' && picked.seed === '2', JSON.stringify(picked));
    await page.evaluate(async () => { window.__game.code = await (await fetch('bots/forager.py')).text(); });
    await page.click('#run');
    await page.waitForFunction(() => /Challenge complete|Not yet/.test(document.getElementById('chalinfo').textContent), null, { timeout: 240000 });
    const ci = await page.textContent('#chalinfo');
    check('challenge is judged and marked complete (forager beats sleepwalker)', /Challenge complete/.test(ci), ci.slice(0, 100));
    check('completed challenge shows a check mark in the list', /✓ Beat the sleepwalker/.test(await page.textContent('#chal')));
  } catch (e) {
    check('test run completed without a thrown error', false, String(e && e.message || e).slice(0, 400));
  }
  await browser.close(); srv.close();
  let bad = 0;
  for (const [n, ok, d] of results) { console.log((ok ? 'PASS  ' : 'FAIL  ') + n + (d ? '  [' + d + ']' : '')); if (!ok) bad++; }
  console.log(`\n${results.length - bad}/${results.length} web checks passed in ${Math.round((Date.now() - t0) / 1000)} s`);
  process.exit(bad ? 1 : 0);
})();
