/* Replay viewer for Critterbots: Colonies. Classic script. Usage: const v = CBViewer(rootElement); v.load(replayObject);
   Frame format is documented in BOT_GUIDE.md ("Replay format"). Everything is drawn from the replay; no engine code here. */
(function () {
  'use strict';
  var COLORS = ['#4dabf7', '#ff6b6b', '#ffd43b', '#69db7c'];
  var DIM = ['#1b6fb0', '#b03a3a', '#a88a14', '#2f9a4a'];
  var TYPES = ['worker', 'scout', 'brute'];
  var VISION = [4, 7, 3], DEN_VISION = 3, RIPEN = 40;
  var TERR = {'.': '#2b3a2e', 's': '#5b4630', 'g': '#2f5a34', 'm': '#4a3f33', '#': '#0f1217'};
  var ACTS = ['wait', 'move', 'dash', 'pickup', 'harvest', 'bank', 'plant', 'build', 'break', 'snatch', 'bonk', 'shove'];
  var EVT = {bank: 'banked', snatch: 'snatched', bonk: 'bonked', shove: 'shoved', harvest: 'harvested', trample: 'trampled',
    fence: 'built a fence', 'break': 'broke a fence', hatch: 'hatched', starve: 'starved'};

  function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
  function esc(s) { return String(s).replace(/[&<>]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;'}[c]; }); }

  window.CBViewer = function (root) {
    var S = {replay: null, t: 0, playing: false, speed: 1, persp: -1, sel: null, acc: 0, last: 0, shake: 0, fx: [], seenT: -1};
    root.innerHTML = '';
    root.classList.add('cbv');
    var cv = el('canvas'); cv.width = cv.height = 720; cv.setAttribute('aria-label', 'Match board');
    var banner = el('div', 'cbv-banner'), controls = el('div', 'cbv-controls'), side = el('div', 'cbv-side');
    var left = el('div', 'cbv-left'); left.appendChild(cv); left.appendChild(banner); left.appendChild(controls);
    root.appendChild(left); root.appendChild(side);
    controls.innerHTML = '<button data-a="play" title="Space">Play</button><button data-a="step" title="Right arrow">Step</button>' +
      '<button data-a="restart" title="R">Restart</button><span class="spd"></span><input type="range" min="0" max="400" value="0" aria-label="Tick">' +
      '<span class="tickno"></span><select aria-label="Perspective"></select>';
    var scrub = controls.querySelector('input'), tickno = controls.querySelector('.tickno'), sel = controls.querySelector('select');
    [0.5, 1, 2, 4, 8].forEach(function (s) { var b = el('button', s === 1 ? 'on' : '', s + 'x'); b.dataset.s = s; b.dataset.a = 'speed'; controls.querySelector('.spd').appendChild(b); });
    side.innerHTML = '<div class="card"><table class="score"></table></div><div class="card"><b>Stores</b><canvas class="chart" width="360" height="110"></canvas></div>' +
      '<div class="card inspect"><b>Inspector</b><div class="ibody">Click a critter or cell.</div></div>' +
      '<div class="card"><div class="tabs"></div><div class="log" aria-live="off"></div></div>';
    var chart = side.querySelector('.chart'), ibody = side.querySelector('.ibody'), logBox = side.querySelector('.log'), tabs = side.querySelector('.tabs'), score = side.querySelector('.score');
    var ctx = cv.getContext('2d'), logTab = 'events';

    function R() { return S.replay; }
    function F(t) { return R().frames[t === undefined ? S.t : t]; }
    function N() { return R().size; }
    function cell() { return cv.width / N(); }

    // ---------- fog (mirrors engine/fog.py) ----------
    function visibleSet(f, ci) {
      var n = N(), vis = {}, i;
      function add(cx, cy, r) {
        for (var y = Math.max(0, cy - r); y <= Math.min(n - 1, cy + r); y++) {
          var rem = r - Math.abs(y - cy);
          for (var x = Math.max(0, cx - rem); x <= Math.min(n - 1, cx + rem); x++) vis[y * n + x] = 1;
        }
      }
      f.u.forEach(function (u) { if (u[0] === ci) add(u[3], u[4], VISION[u[2]]); });
      R().dens[ci].forEach(function (d) { add(d[0], d[1], DEN_VISION); });
      return vis;
    }
    function hiddenUnit(f, u, ci, vis) {
      var n = N();
      if (u[0] === ci) return false;
      if (!vis[u[4] * n + u[3]]) return true;
      if (R().terrain[u[4]][u[3]] !== 'g') return false;
      return !f.u.some(function (o) { return o[0] === ci && Math.abs(o[3] - u[3]) + Math.abs(o[4] - u[4]) === 1; });
    }

    // ---------- drawing ----------
    function draw() {
      if (!R()) return;
      var f = F(), n = N(), c = cell(), ci = S.persp, vis = ci >= 0 ? visibleSet(f, ci) : null, x, y;
      ctx.save();
      if (S.shake > 0) ctx.translate((Math.random() - 0.5) * S.shake, (Math.random() - 0.5) * S.shake);
      ctx.clearRect(-10, -10, cv.width + 20, cv.height + 20);
      for (y = 0; y < n; y++) for (x = 0; x < n; x++) {
        var ch = R().terrain[y][x];
        ctx.fillStyle = TERR[ch] || TERR['.']; ctx.fillRect(x * c, y * c, c, c);
        if (ch === 'g') { ctx.fillStyle = '#3f7a45'; ctx.fillRect(x * c + c * 0.2, y * c + c * 0.55, c * 0.12, c * 0.3); ctx.fillRect(x * c + c * 0.6, y * c + c * 0.4, c * 0.12, c * 0.4); }
        if (ch === 'm') { ctx.fillStyle = '#5d4e3d'; ctx.beginPath(); ctx.arc(x * c + c * 0.5, y * c + c * 0.55, c * 0.28, 0, 7); ctx.fill(); }
        if (ch === 's') { ctx.strokeStyle = '#7a5c3a'; ctx.lineWidth = 1; for (var k = 1; k < 4; k++) { ctx.beginPath(); ctx.moveTo(x * c + 3, y * c + k * c / 4); ctx.lineTo(x * c + c - 3, y * c + k * c / 4); ctx.stroke(); } }
        if (ch === '#') { ctx.fillStyle = '#1c212b'; ctx.fillRect(x * c + 2, y * c + 2, c - 4, c - 4); }
      }
      R().dens.forEach(function (d, i) {
        d.forEach(function (p) { ctx.fillStyle = DIM[i]; ctx.fillRect(p[0] * c, p[1] * c, c, c); ctx.strokeStyle = COLORS[i]; ctx.lineWidth = 2; ctx.strokeRect(p[0] * c + 1, p[1] * c + 1, c - 2, c - 2); });
      });
      f.s.forEach(function (s) {
        if (vis && !vis[s[1] * n + s[0]]) return;
        ctx.fillStyle = s[2] === 3 ? '#ffd43b' : '#e9e2c8'; ctx.beginPath(); ctx.arc(s[0] * c + c / 2, s[1] * c + c / 2, c * (s[2] === 3 ? 0.2 : 0.13), 0, 7); ctx.fill();
        if (s[2] === 3) { ctx.strokeStyle = '#fff6'; ctx.stroke(); }
      });
      f.p.forEach(function (p) {
        if (vis && p[2] !== ci && !vis[p[1] * n + p[0]]) return;
        var age = f.t - p[3], ripe = age >= RIPEN, st = ripe ? 3 : Math.floor(age * 3 / RIPEN), px = p[0] * c + c / 2, py = p[1] * c + c / 2;
        ctx.fillStyle = ripe ? '#ffa94d' : '#74c365'; ctx.fillRect(px - 1.5, py - c * (0.12 + st * 0.1), 3, c * (0.12 + st * 0.1));
        ctx.beginPath(); ctx.arc(px, py - c * (0.14 + st * 0.1), c * (0.1 + st * 0.04), 0, 7); ctx.fill();
        ctx.strokeStyle = COLORS[p[2]]; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(px, py + c * 0.28, 2, 0, 7); ctx.stroke();
      });
      f.f.forEach(function (fe) {
        if (vis && fe[2] !== ci && !vis[fe[1] * n + fe[0]]) return;
        ctx.strokeStyle = COLORS[fe[2]]; ctx.lineWidth = 3; ctx.beginPath();
        ctx.moveTo(fe[0] * c + 3, fe[1] * c + c * 0.35); ctx.lineTo(fe[0] * c + c - 3, fe[1] * c + c * 0.35);
        ctx.moveTo(fe[0] * c + 3, fe[1] * c + c * 0.7); ctx.lineTo(fe[0] * c + c - 3, fe[1] * c + c * 0.7); ctx.stroke();
      });
      f.u.forEach(function (u) {
        if (vis && hiddenUnit(f, u, ci, vis)) return;
        var ux = u[3] * c + c / 2, uy = u[4] * c + c / 2, r = c * 0.32;
        ctx.fillStyle = u[6] > 0 ? '#adb5bd' : COLORS[u[0]]; ctx.strokeStyle = '#0008'; ctx.lineWidth = 2;
        ctx.beginPath();
        if (u[2] === 0) ctx.arc(ux, uy, r, 0, 7);
        else if (u[2] === 1) { ctx.moveTo(ux, uy - r * 1.15); ctx.lineTo(ux + r * 1.05, uy + r * 0.8); ctx.lineTo(ux - r * 1.05, uy + r * 0.8); ctx.closePath(); }
        else ctx.rect(ux - r, uy - r, r * 2, r * 2);
        ctx.fill(); ctx.stroke();
        if (S.sel === u[1]) { ctx.strokeStyle = '#fff'; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.arc(ux, uy, r * 1.55, 0, 7); ctx.stroke(); }
        if (u[7]) { ctx.fillStyle = '#6b5339'; ctx.fillRect(ux - r, uy + r * 0.85, r * 2, 3); }
        for (var i = 0; i < u[5]; i++) { ctx.fillStyle = '#ffe066'; ctx.fillRect(ux - r + i * (r * 2 / 5), uy - r * 1.55, r * 2 / 5 - 1, 4); }
        if (u[6] > 0) { ctx.fillStyle = '#212529'; ctx.font = 'bold ' + Math.round(c * 0.4) + 'px system-ui'; ctx.textAlign = 'center'; ctx.fillText('z', ux, uy + c * 0.14); }
      });
      if (vis) {
        ctx.fillStyle = 'rgba(8,10,16,0.62)';
        for (y = 0; y < n; y++) for (x = 0; x < n; x++) if (!vis[y * n + x]) ctx.fillRect(x * c, y * c, c, c);
      }
      S.fx = S.fx.filter(function (e) { return performance.now() - e.t0 < 600; });
      S.fx.forEach(function (e) {
        var a = (performance.now() - e.t0) / 600;
        ctx.globalAlpha = 1 - a; ctx.strokeStyle = e.col; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(e.x * c + c / 2, e.y * c + c / 2, c * (0.3 + a * 0.9), 0, 7); ctx.stroke();
        if (e.txt) { ctx.fillStyle = e.col; ctx.font = 'bold ' + Math.round(c * 0.45) + 'px system-ui'; ctx.textAlign = 'center'; ctx.fillText(e.txt, e.x * c + c / 2, e.y * c - a * c * 0.6); }
        ctx.globalAlpha = 1;
      });
      ctx.restore();
    }

    function spawnFx(t) {
      var f = F(t), now = performance.now();
      f.e.forEach(function (e) {
        var col = e[0] === 'bonk' || e[0] === 'shove' || e[0] === 'snatch' ? '#ff8787' : e[0] === 'bank' ? '#ffd43b' : e[0] === 'trample' ? '#ffa94d' : '#a5d8ff';
        S.fx.push({x: e[3], y: e[4], t0: now, col: col, txt: e[0] === 'bank' ? '+' + e[5] : e[0] === 'bonk' ? 'BONK' : e[0] === 'snatch' ? 'SNATCH' : ''});
        if (e[0] === 'bonk') S.shake = 6;
      });
    }

    // ---------- panels ----------
    function panels() {
      var f = F(), r = R(), res = r.result.scores, h = '<tr><th></th><th>Bot</th><th>Stores</th><th>Crit.</th></tr>';
      r.bots.forEach(function (b, i) {
        var cnt = f.u.filter(function (u) { return u[0] === i; }).length;
        h += '<tr><td><span class="sw" style="background:' + COLORS[i] + '"></span></td><td>' + esc(b) + (f.h[i] ? ' <small>(hatching ' + f.h[i][0] + ')</small>' : '') + '</td><td class="n">' + f.st[i] + '</td><td class="n">' + cnt + '</td></tr>';
      });
      score.innerHTML = h;
      tickno.textContent = 'tick ' + S.t + ' / ' + r.ticks;
      scrub.value = S.t;
      drawChart();
      drawLog();
      drawInspector();
      var end = S.t >= r.ticks;
      banner.className = 'cbv-banner' + (end ? ' show' : '');
      if (end) {
        var w = r.result.winners.map(function (i) { return r.bots[i]; }).join(' & ');
        banner.innerHTML = '<b>' + (r.result.winners.length > 1 ? 'DRAW: ' : '') + esc(w) + (r.result.winners.length > 1 ? '' : ' WINS') + '</b>' +
          '<span>' + r.result.scores.map(function (s) { return esc(r.bots[s.colony]) + ' ' + s.stores; }).join(' · ') + '</span>';
      } else banner.innerHTML = '';
    }
    function drawChart() {
      var g = chart.getContext('2d'), r = R(), w = chart.width, h = chart.height, mx = 10;
      g.clearRect(0, 0, w, h);
      r.frames.forEach(function (f) { f.st.forEach(function (v) { if (v > mx) mx = v; }); });
      g.strokeStyle = '#323a4e'; g.beginPath(); g.moveTo(0, h - 0.5); g.lineTo(w, h - 0.5); g.stroke();
      r.bots.forEach(function (b, i) {
        g.strokeStyle = COLORS[i]; g.lineWidth = 2; g.beginPath();
        r.frames.forEach(function (f, t) { var px = t / r.ticks * w, py = h - 4 - f.st[i] / mx * (h - 10); if (t) g.lineTo(px, py); else g.moveTo(px, py); });
        g.stroke();
      });
      g.strokeStyle = '#fff'; g.lineWidth = 1; g.beginPath(); g.moveTo(S.t / r.ticks * w, 0); g.lineTo(S.t / r.ticks * w, h); g.stroke();
      g.fillStyle = '#d3d9e4'; g.font = '11px system-ui'; g.fillText('max ' + mx, 3, 11);
      // event markers
      r.frames.forEach(function (f, t) { f.e.forEach(function (e) { if (e[0] === 'bonk' || e[0] === 'snatch' || e[0] === 'trample' || e[0] === 'starve') { g.fillStyle = '#ff8787'; g.fillRect(t / r.ticks * w, h - 6, 2, 6); } }); });
    }
    function drawLog() {
      var r = R(), html = '';
      if (logTab === 'events') {
        var shown = 0;
        for (var t = S.t; t >= 0 && shown < 60; t--) F(t).e.forEach(function (e) {
          if (shown >= 60) return; shown++;
          html += '<div class="t" data-t="' + t + '">t' + t + ' <b style="color:' + COLORS[e[1]] + '">' + esc(r.bots[e[1]]) + '</b> ' + (EVT[e[0]] || e[0]) + (e[2] !== null && e[2] !== e[1] ? ' <b style="color:' + COLORS[e[2]] + '">' + esc(r.bots[e[2]]) + '</b>' : '') + '</div>';
        });
        r.errors.forEach(function (er) { if (er[0] <= S.t && shown < 60) html += '<div class="e" data-t="' + er[0] + '">t' + er[0] + ' ' + esc(r.bots[er[1]]) + ': ' + esc(er[2]) + '</div>'; });
      } else {
        var i = +logTab;
        (r.logs[i] || []).forEach(function (l) { if (l[0] <= S.t) html += '<div class="p" data-t="' + l[0] + '">t' + l[0] + ' ' + esc(l[1]) + '</div>'; });
        r.errors.forEach(function (er) { if (er[1] === i && er[0] <= S.t) html += '<div class="e" data-t="' + er[0] + '">t' + er[0] + ' ' + esc(er[2]) + '</div>'; });
      }
      logBox.innerHTML = html || '<div class="t">Nothing yet.</div>';
    }
    function drawTabs() {
      var r = R(), h = '<button data-tab="events"' + (logTab === 'events' ? ' class="on"' : '') + '>Events</button>';
      r.bots.forEach(function (b, i) { h += '<button data-tab="' + i + '"' + (logTab === String(i) ? ' class="on"' : '') + '><span class="sw" style="background:' + COLORS[i] + '"></span>' + esc(b) + '</button>'; });
      tabs.innerHTML = h;
    }
    function drawInspector() {
      var f = F(), r = R();
      if (S.sel === null) return;
      var u = f.u.filter(function (q) { return q[1] === S.sel; })[0];
      if (!u) { ibody.innerHTML = 'Critter #' + S.sel + ' is gone.'; return; }
      var last = u[8] >> 1 ? '' : '', act = ACTS[u[8] >> 1] + (u[8] & 1 ? '' : ' (failed)');
      var tr = R().terrain[u[4]][u[3]];
      ibody.innerHTML = '<span class="sw" style="background:' + COLORS[u[0]] + '"></span><b>' + esc(r.bots[u[0]]) + ' ' + TYPES[u[2]] + ' #' + u[1] + '</b><br>' +
        'at (' + u[3] + ', ' + u[4] + ') on ' + ({'.': 'open', s: 'soil', g: 'grass', m: 'mud', '#': 'wall'}[tr]) + '<br>load ' + u[5] + (u[6] ? ' · stunned ' + u[6] : '') + (u[7] ? ' · stuck in mud' : '') + '<br>last action: ' + act;
    }

    // ---------- control ----------
    function setT(t, fx) {
      t = Math.max(0, Math.min(R().ticks, t));
      if (fx && t === S.t + 1) spawnFx(t);
      S.t = t; panels();
    }
    function play(on) { S.playing = on === undefined ? !S.playing : on; controls.querySelector('[data-a=play]').textContent = S.playing ? 'Pause' : 'Play'; if (S.playing && S.t >= R().ticks) setT(0); S.last = performance.now(); }
    controls.addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b || !R()) return;
      if (b.dataset.a === 'play') play();
      else if (b.dataset.a === 'step') { play(false); setT(S.t + 1, true); }
      else if (b.dataset.a === 'restart') { setT(0); play(true); }
      else if (b.dataset.a === 'speed') { S.speed = +b.dataset.s; [].forEach.call(controls.querySelectorAll('[data-a=speed]'), function (x) { x.classList.toggle('on', x === b); }); }
    });
    scrub.addEventListener('input', function () { play(false); setT(+scrub.value); });
    sel.addEventListener('change', function () { S.persp = +sel.value; draw(); });
    tabs.addEventListener('click', function (e) { var b = e.target.closest('button'); if (b) { logTab = b.dataset.tab; drawTabs(); drawLog(); } });
    logBox.addEventListener('click', function (e) { var d = e.target.closest('[data-t]'); if (d) { play(false); setT(+d.dataset.t); } });
    cv.addEventListener('click', function (e) {
      if (!R()) return;
      var rc = cv.getBoundingClientRect(), c = cell(), x = Math.floor((e.clientX - rc.left) / rc.width * N()), y = Math.floor((e.clientY - rc.top) / rc.height * N());
      var u = F().u.filter(function (q) { return q[3] === x && q[4] === y; })[0];
      if (u) { S.sel = u[1]; drawInspector(); draw(); return; }
      S.sel = null;
      var f = F(), plant = f.p.filter(function (p) { return p[0] === x && p[1] === y; })[0], seed = f.s.filter(function (p) { return p[0] === x && p[1] === y; })[0];
      var tr = R().terrain[y][x];
      ibody.innerHTML = 'Cell (' + x + ', ' + y + '): ' + ({'.': 'open', s: 'soil', g: 'grass (hides critters)', m: 'mud (costs an action)', '#': 'wall'}[tr]) +
        (seed ? '<br>seed worth ' + seed[2] : '') + (plant ? '<br>' + esc(R().bots[plant[2]]) + '\'s crop, ' + (f.t - plant[3] >= RIPEN ? 'ripe' : 'ripe in ' + (RIPEN - (f.t - plant[3]))) : '');
      draw();
    });
    document.addEventListener('keydown', function (e) {
      if (!R() || /INPUT|TEXTAREA|SELECT/.test(e.target.tagName) || e.target.closest && e.target.closest('.cm-editor')) return;
      if (e.key === ' ') { e.preventDefault(); play(); }
      else if (e.key === 'ArrowRight') { play(false); setT(S.t + 1, true); }
      else if (e.key === 'ArrowLeft') { play(false); setT(S.t - 1); }
      else if (e.key === 'r' || e.key === 'R') { setT(0); play(true); }
      else if (e.key >= '1' && e.key <= '5') { var s = [0.5, 1, 2, 4, 8][+e.key - 1]; var b = controls.querySelector('[data-a=speed][data-s="' + s + '"]'); if (b) b.click(); }
    });
    function frame(now) {
      if (R()) {
        if (S.playing) {
          S.acc += (now - S.last) * S.speed / 110; S.last = now;
          while (S.acc >= 1 && S.t < R().ticks) { S.acc -= 1; setT(S.t + 1, true); }
          if (S.t >= R().ticks) play(false);
        }
        if (S.shake > 0) S.shake = Math.max(0, S.shake - 0.6);
        draw();
      }
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);

    var api = {
      load: function (replay, opts) {
        S.replay = replay; S.t = 0; S.sel = null; S.persp = -1; S.fx = [];
        scrub.max = replay.ticks;
        sel.innerHTML = '<option value="-1">God view</option>' + replay.bots.map(function (b, i) { return '<option value="' + i + '">' + esc(b) + ' (fog)</option>'; }).join('');
        drawTabs(); panels(); draw();
        if (!opts || opts.autoplay !== false) play(true);
      },
      get state() { return S; }, setTick: function (t) { play(false); setT(t); }, play: play,
      perspective: function (i) { S.persp = i; sel.value = i; draw(); }
    };
    return api;
  };
})();
