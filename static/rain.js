/* static/rain.js — Cipher Rain & Quantum Vault Engine ("Kriptologiya maktabi").
   Поддерживает режимы:
   - theme: 'quantum' (Main Test: Сапфировый фон + Гексагональные соты + Неоновый дождь кобальт/циан/золото + Купол тишины 85% + Импульс при клике)
   - theme: 'light'   (Светлые страницы: Контрастный сапфирово-бирюзовый и золотой поток)
   - theme: 'dark'    (Классический тёмный кибер-режим) */
(function () {
    'use strict';

    var CHARSET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-<>/\\|#$%&*+=:.';
    var RANDSRC = '0123456789ABCDEF0123456789ABCDEF<>/|#$%&*+=:';
    var WORDS = ['AES-256', 'RSA-4096', 'SHA-3', 'ECC', 'HMAC', 'TLS', 'PKI',
                 'XOR', '0XFF', 'KEY', 'SALT', 'HASH', 'CRYPTO', 'UNICON.UZ'];
    var RAND = [];
    for (var i = 0; i < RANDSRC.length; i++) RAND.push(CHARSET.indexOf(RANDSRC.charAt(i)));

    var PALETTE = {
        // Светлый фон: контрастные сапфировые, бирюзовые и золотые струи
        light: [
            { body: 'rgb(30, 64, 175)',  head: 'rgb(29, 78, 216)',   glow: 'rgba(37, 99, 235, 0.85)' },
            { body: 'rgb(14, 116, 144)', head: 'rgb(8, 145, 178)',   glow: 'rgba(6, 182, 212, 0.85)' },
            { body: 'rgb(180, 83, 9)',   head: 'rgb(217, 119, 6)',   glow: 'rgba(234, 179, 8, 0.90)' }
        ],
        // Тёмный классический фон
        dark: [
            { body: 'rgb(34, 197, 94)',  head: 'rgb(220, 252, 231)', glow: 'rgba(74, 222, 128, 0.95)' },
            { body: 'rgb(6, 182, 212)',  head: 'rgb(207, 250, 254)', glow: 'rgba(34, 211, 238, 0.95)' }
        ],
        // Quantum Vault: Кобальт (#3b82f6), Неоновый Циан (#06b6d4) и Сияющее Золото (#facc15)
        quantum: [
            { body: 'rgb(59, 130, 246)', head: 'rgb(224, 242, 254)', glow: 'rgba(56, 189, 248, 0.98)' },
            { body: 'rgb(6, 182, 212)',  head: 'rgb(207, 250, 254)', glow: 'rgba(34, 211, 238, 0.98)' },
            { body: 'rgb(234, 179, 8)',  head: 'rgb(254, 249, 195)', glow: 'rgba(250, 204, 21, 0.98)' }
        ]
    };

    // 3 слоя глубины: дальний, средний, ближний
    var LAYERS = [
        { fs: 12, speed: 0.11, len: [8, 14],  alpha: 0.58, density: 0.34 },
        { fs: 16, speed: 0.18, len: [10, 18], alpha: 0.84, density: 0.40 },
        { fs: 22, speed: 0.26, len: [12, 22], alpha: 1.00, density: 0.26 }
    ];

    var DEFAULTS = {
        theme: 'auto',   // 'auto' | 'light' | 'dark' | 'quantum'
        edgeMin: 0.15,   // в центре экрана 15% яркости ("Купол тишины" 85%), по бокам 100%
        maxFps: 32,
        intensity: 1,
        zIndex: 0,
        pointer: true,
        radius: 185,
        words: true,
        hexGrid: true
    };

    function merge(o) {
        var r = {}, k;
        for (k in DEFAULTS) r[k] = DEFAULTS[k];
        for (k in (o || {})) r[k] = o[k];
        return r;
    }

    function parseRGB(str) {
        var m = /rgba?\(([^)]+)\)/.exec(str || '');
        if (!m) return null;
        var p = m[1].split(/[,\s\/]+/).filter(Boolean).map(parseFloat);
        return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
    }

    function detectTheme() {
        var els = [document.body, document.documentElement];
        for (var i = 0; i < els.length; i++) {
            if (!els[i]) continue;
            var c = parseRGB(getComputedStyle(els[i]).backgroundColor);
            if (c && c.a > 0.05) {
                var lum = (0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b) / 255;
                return lum > 0.5 ? 'light' : 'quantum';
            }
        }
        return 'quantum';
    }

    function start(opts) {
        var o = merge(opts);
        var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
        var theme = o.theme === 'auto' ? detectTheme() : o.theme;
        var palList = PALETTE[theme] || PALETTE.quantum;
        var isQuantumOrDark = (theme === 'quantum' || theme === 'dark');
        var frameMs = 1000 / o.maxFps;
        var R = o.radius, R2 = R * R;

        var old = document.getElementById('rain-bg');
        if (old && old.parentNode) old.parentNode.removeChild(old);

        var canvas = document.createElement('canvas');
        canvas.id = 'rain-bg';
        canvas.setAttribute('aria-hidden', 'true');
        canvas.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;' +
            'pointer-events:none;z-index:' + o.zIndex + ';';
        document.body.insertBefore(canvas, document.body.firstChild);
        var ctx = canvas.getContext('2d');

        var W = 0, H = 0, dpr = 1, layers = [];
        var hexCells = [];
        var waves = [];
        var px = -9999, py = -9999;
        var raf = 0, last = 0, wordTimer = 0;

        // "Купол тишины": в центральной зоне (под карточкой вопроса) приглушаем дождь до edgeMin (15%)
        function calcEdgeFactor(nx) {
            var dist = Math.abs(nx * 2 - 1); // 0 в центре, 1 у левого/правого края
            if (dist < 0.46) {
                return o.edgeMin + (0.28 - o.edgeMin) * Math.pow(dist / 0.46, 2);
            }
            var flank = (dist - 0.46) / 0.54;
            return Math.min(1, 0.35 + Math.pow(flank, 1.05) * 0.75);
        }

        /* ── Слой 1: Гексагональная крипто-сетка (Соты) ── */
        function buildHexGrid() {
            hexCells = [];
            if (!isQuantumOrDark || !o.hexGrid) return;

            var rad = W < 768 ? 34 : 42;
            var dx = rad * Math.sqrt(3);
            var dy = rad * 1.5;
            var cols = Math.ceil(W / dx) + 2;
            var rows = Math.ceil(H / dy) + 2;

            for (var r = 0; r < rows; r++) {
                for (var c = 0; c < cols; c++) {
                    var hx = c * dx + (r % 2 ? dx * 0.5 : 0);
                    var hy = r * dy;
                    var nx = hx / (W || 1);
                    var edge = calcEdgeFactor(nx);
                    hexCells.push({
                        x: hx,
                        y: hy,
                        r: rad - 1.5,
                        edge: edge,
                        baseAlpha: edge > 0.32 ? 0.055 : 0.014,
                        energy: 0,
                        rgb: (r + c) % 6 === 0 ? '250, 204, 21' : ((r + c) % 2 === 0 ? '34, 211, 238' : '59, 130, 246')
                    });
                }
            }
        }

        function traceHex(cx, cy, r) {
            ctx.beginPath();
            for (var i = 0; i < 6; i++) {
                var a = (Math.PI / 3) * i - Math.PI / 6;
                var x = cx + r * Math.cos(a);
                var y = cy + r * Math.sin(a);
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }
            ctx.closePath();
        }

        /* ── Атлас спрайтов: 3 цветовые вариации (Кобальт, Циан, Золото) в одном атласе ── */
        function buildAtlas(L) {
            var n = CHARSET.length;
            var pCount = palList.length;
            L.cwp = Math.round(L.cw * dpr);
            L.chp = Math.round(L.ch * dpr);
            var cv = document.createElement('canvas');
            cv.width = L.cwp * n;
            cv.height = L.chp * 2 * pCount;
            var g = cv.getContext('2d');
            g.scale(L.cwp / L.cw, L.chp / L.ch);
            g.font = 'bold ' + L.fs + 'px "JetBrains Mono", "Courier New", ui-monospace, Consolas, monospace';
            g.textAlign = 'center';
            g.textBaseline = 'middle';

            for (var pIdx = 0; pIdx < pCount; pIdx++) {
                var pal = palList[pIdx];
                for (var row = 0; row < 2; row++) {
                    var atlasRow = pIdx * 2 + row;
                    g.shadowBlur = row ? L.fs * 0.78 : L.fs * 0.15;
                    g.shadowColor = pal.glow;
                    g.fillStyle = row ? pal.head : pal.body;
                    for (var i = 0; i < n; i++) {
                        g.fillText(
                            CHARSET.charAt(i),
                            i * L.cw + L.pad + L.colW / 2,
                            atlasRow * L.ch + L.pad + L.rowH / 2
                        );
                    }
                }
            }
            L.atlas = cv;
            L.pCount = pCount;
        }

        function spawn(L, c, initial) {
            c.head = initial ? Math.random() * L.rows * 1.2 - L.rows * 0.2
                             : -(Math.random() * L.rows * 0.5 + 2);
            c.speed = L.speed * (0.75 + Math.random() * 0.6);
            c.len = (L.len[0] + Math.random() * (L.len[1] - L.len[0])) | 0;
            c.active = Math.random() < L.density * o.intensity;
            c.b = 0;
            c.boost = 0;
            // Каждая 5-я активная струя — золотая, остальные чередуют кобальт и бирюзовый циан
            c.palIdx = (Math.random() < 0.22 && L.pCount >= 3) ? 2 : ((Math.random() * Math.min(2, L.pCount)) | 0);
            c.mark.fill(0);
            for (var r = 0; r < c.chars.length; r++) {
                c.chars[r] = RAND[(Math.random() * RAND.length) | 0];
            }
        }

        function buildLayers() {
            var mobile = W < 700;
            layers = [];
            LAYERS.forEach(function (cfg, idx) {
                if (mobile && idx === 0) return;
                var L = {
                    fs: cfg.fs, speed: cfg.speed, len: cfg.len, alpha: cfg.alpha,
                    density: cfg.density * (mobile ? 0.75 : 1)
                };
                L.colW = Math.round(L.fs * 0.64);
                L.rowH = Math.round(L.fs * 1.14);
                L.pad = Math.ceil(L.fs * 0.45);
                L.cw = L.colW + 2 * L.pad;
                L.ch = L.rowH + 2 * L.pad;
                L.rows = Math.ceil(H / L.rowH) + 2;
                var ncols = Math.ceil(W / L.colW);
                L.cols = [];
                buildAtlas(L);

                for (var i = 0; i < ncols; i++) {
                    var c = {
                        x: i * L.colW,
                        chars: new Uint8Array(L.rows + 1),
                        mark: new Uint8Array(L.rows + 1),
                        palIdx: 0,
                        boost: 0
                    };
                    var nx = (c.x + L.colW / 2) / (W || 1);
                    c.edge = calcEdgeFactor(nx);
                    spawn(L, c, true);
                    L.cols.push(c);
                }
                layers.push(L);
            });
        }

        function resize() {
            W = window.innerWidth;
            H = window.innerHeight;
            dpr = Math.min(window.devicePixelRatio || 1, 2);
            canvas.width = Math.round(W * dpr);
            canvas.height = Math.round(H * dpr);
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            buildHexGrid();
            buildLayers();
            if (reduce) { draw(); }
        }

        /* ── Слово-шифр в падающей колонке крупного слоя ── */
        function injectWord() {
            var L = layers[layers.length - 1];
            if (!L || document.hidden) return;
            var w = WORDS[(Math.random() * WORDS.length) | 0];
            // Выбираем колонку преимущественно на боковых кулисах, где она ярко видна
            var sideCols = L.cols.filter(function (col) { return col.edge > 0.45; });
            var pool = sideCols.length ? sideCols : L.cols;
            var c = pool[(Math.random() * pool.length) | 0];
            var r0 = Math.floor(L.rows * (0.18 + Math.random() * 0.42));
            if (r0 + w.length >= L.rows) return;
            spawn(L, c, false);
            c.active = true;
            c.head = -2;
            c.len = Math.max(c.len, w.length + 8);
            for (var j = 0; j < w.length; j++) {
                c.chars[r0 + j] = CHARSET.indexOf(w.charAt(j));
                c.mark[r0 + j] = 1;
            }
        }

        /* ── Слой 3: Интерактивный импульс при клике на ответ или кнопку ── */
        function triggerWave(cx, cy) {
            var x = typeof cx === 'number' ? cx : W * 0.5;
            var y = typeof cy === 'number' ? cy : H * 0.5;
            waves.push({
                x: x,
                y: y,
                r: 24,
                maxR: Math.max(W, H) * 0.9,
                alpha: 0.72
            });
            for (var li = 0; li < layers.length; li++) {
                var cols = layers[li].cols;
                for (var ci = 0; ci < cols.length; ci++) {
                    if (cols[ci].edge > 0.3) {
                        cols[ci].boost = 0.22;
                    }
                }
            }
        }

        function step() {
            // Обновление световых волн
            for (var wi = waves.length - 1; wi >= 0; wi--) {
                var wv = waves[wi];
                wv.r += 22;
                wv.alpha *= 0.94;
                if (wv.r > wv.maxR || wv.alpha < 0.02) {
                    waves.splice(wi, 1);
                }
            }

            for (var li = 0; li < layers.length; li++) {
                var L = layers[li];
                for (var ci = 0; ci < L.cols.length; ci++) {
                    var c = L.cols[ci], b = 0;
                    if (c.boost > 0.005) c.boost *= 0.92;
                    else c.boost = 0;

                    if (c.active && px > -9000) {
                        var dx = c.x + L.colW * 0.5 - px, dy = c.head * L.rowH - py;
                        var d2 = dx * dx + dy * dy;
                        if (d2 < R2) b = 1 - Math.sqrt(d2) / R;
                    }
                    c.b = b;
                    c.head += c.speed * (1 + b * 1.15) + c.boost;

                    // Подсветка гексагональных сот при пролёте головы струи в боковых зонах
                    if (isQuantumOrDark && li === layers.length - 1 && c.active && c.edge > 0.35) {
                        var headY = c.head * L.rowH;
                        for (var hi = 0; hi < hexCells.length; hi++) {
                            var hc = hexCells[hi];
                            if (Math.abs(hc.x - c.x) < 34 && Math.abs(hc.y - headY) < 34) {
                                hc.energy = Math.max(hc.energy, 0.55 * c.edge);
                                break;
                            }
                        }
                    }

                    if (c.head - c.len > L.rows) {
                        spawn(L, c, false);
                    } else if (c.active && Math.random() < 0.22) {
                        var r = Math.floor(c.head - Math.random() * c.len);
                        if (r >= 0 && r < L.rows && !c.mark[r]) {
                            c.chars[r] = RAND[(Math.random() * RAND.length) | 0];
                        }
                    }
                }
            }
        }

        function draw() {
            ctx.clearRect(0, 0, W, H);

            // 1. Отрисовка гексагональной крипто-сетки (Слой 1)
            if (isQuantumOrDark && hexCells.length) {
                ctx.lineWidth = 0.85;
                for (var hi = 0; hi < hexCells.length; hi++) {
                    var cell = hexCells[hi];
                    if (cell.energy > 0.005) cell.energy *= 0.93;
                    else cell.energy = 0;

                    for (var wi = 0; wi < waves.length; wi++) {
                        var distW = Math.hypot(cell.x - waves[wi].x, cell.y - waves[wi].y);
                        if (Math.abs(distW - waves[wi].r) < 48) {
                            cell.energy = Math.max(cell.energy, waves[wi].alpha * 0.65);
                        }
                    }

                    var aHex = cell.baseAlpha + cell.energy * 0.34;
                    if (aHex <= 0.01) continue;

                    traceHex(cell.x, cell.y, cell.r);
                    ctx.strokeStyle = 'rgba(' + cell.rgb + ',' + aHex.toFixed(3) + ')';
                    ctx.stroke();

                    if (cell.energy > 0.14) {
                        ctx.fillStyle = 'rgba(' + cell.rgb + ',' + (cell.energy * 0.08).toFixed(3) + ')';
                        ctx.fill();
                    }
                }
            }

            // 2. Отрисовка расходящихся световых колец импульса (Слой 3)
            for (var wj = 0; wj < waves.length; wj++) {
                var wv = waves[wj];
                ctx.beginPath();
                ctx.arc(wv.x, wv.y, wv.r, 0, Math.PI * 2);
                ctx.strokeStyle = 'rgba(34, 211, 238, ' + (wv.alpha * 0.32).toFixed(3) + ')';
                ctx.lineWidth = 1.8;
                ctx.stroke();
            }

            // 3. Отрисовка многослойного цифрового дождя (Слой 2)
            for (var li = 0; li < layers.length; li++) {
                var L = layers[li];
                var at = L.atlas, cw = L.cw, ch = L.ch, cwp = L.cwp, chp = L.chp;
                var pad = L.pad, rowH = L.rowH, rows = L.rows;
                for (var ci = 0; ci < L.cols.length; ci++) {
                    var c = L.cols[ci];
                    if (!c.active) continue;
                    var h = Math.floor(c.head), len = c.len;
                    var base = L.alpha * c.edge * (1 + 0.65 * c.b + c.boost * 1.5);
                    var x = c.x - pad;
                    var pOffset = (c.palIdx || 0) * 2;

                    for (var k = 0; k <= len; k++) {
                        var r = h - k;
                        if (r < 0) break;
                        if (r >= rows) continue;
                        var t = 1 - k / (len + 1);
                        var a = t * t, row = pOffset, gi = c.chars[r];
                        if (k === 0) {
                            row = pOffset + 1;
                            a = 1;
                            gi = RAND[(Math.random() * RAND.length) | 0];
                        } else if (c.mark[r]) {
                            row = pOffset + 1;
                            a = Math.max(a, 0.78 * Math.min(1, (len - k + 1) / 4));
                        }
                        a *= base;
                        if (a > 1) a = 1;
                        if (a < 0.025) continue;
                        ctx.globalAlpha = a;
                        ctx.drawImage(at, gi * cwp, row * chp, cwp, chp, x, r * rowH - pad, cw, ch);
                    }
                }
            }
            ctx.globalAlpha = 1;
        }

        function loop(ts) {
            raf = requestAnimationFrame(loop);
            if (ts - last < frameMs - 2) return;
            last = ts;
            step();
            draw();
        }

        function run() {
            if (reduce || raf) return;
            raf = requestAnimationFrame(loop);
            if (o.words && !wordTimer) wordTimer = setInterval(injectWord, 3400);
        }
        function stop() {
            if (raf) { cancelAnimationFrame(raf); raf = 0; }
            if (wordTimer) { clearInterval(wordTimer); wordTimer = 0; }
        }

        if (o.pointer && !reduce) {
            window.addEventListener('pointermove', function (e) { px = e.clientX; py = e.clientY; }, { passive: true });
            document.addEventListener('pointerleave', function () { px = py = -9999; });
            document.addEventListener('click', function (e) {
                var hit = e.target.closest('label, button, input[type="radio"], .qv-option, .water-btn');
                if (hit) triggerWave(e.clientX, e.clientY);
            }, { passive: true });
        }
        var rt;
        window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(resize, 200); });
        document.addEventListener('visibilitychange', function () { document.hidden ? stop() : run(); });

        resize();
        run();
        return { stop: stop, run: run, canvas: canvas, triggerWave: triggerWave };
    }

    var instance = null;
    function boot(opts) {
        if (instance && instance.stop) {
            instance.stop();
            instance = null;
        }
        if (!document.body) {
            document.addEventListener('DOMContentLoaded', function () { boot(opts); });
            return null;
        }
        instance = start(opts);
        return instance;
    }

    window.initDigitalRainBackground = boot;
    window.initDigitalRain = function (_targets, opts) { return boot(opts); };
    window.initDigitalRainInBlocks = function (_root, opts) { return boot(opts); };
})();