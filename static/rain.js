/* static/rain.js — Cipher Rain: фоновый "цифровой дождь".
   ОДИН fixed-canvas за контентом, атлас спрайтов, 3 слоя глубины,
   слова-шифры и реакция на курсор. */
(function () {
    'use strict';

    var CHARSET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-<>/\\|#$%&*+=:.';
    var RANDSRC = '0123456789ABCDEF0123456789ABCDEF<>/|#$%&*+=:';
    var WORDS = ['AES-256', 'RSA-4096', 'SHA-3', 'ECC', 'HMAC', 'TLS', 'PKI',
                 'XOR', '0XFF', 'KEY', 'SALT', 'HASH', 'CRYPTO', 'UNICON.UZ'];
    var RAND = [];
    for (var i = 0; i < RANDSRC.length; i++) RAND.push(CHARSET.indexOf(RANDSRC.charAt(i)));

    var PALETTE = {
        // светлый фон: тёмно-зелёный хвост + насыщенная светящаяся "голова"
        light: { body: 'rgb(20,83,45)',    head: 'rgb(22,163,74)',   glow: 'rgba(34,197,94,0.95)' },
        // тёмный фон: яркий зелёный хвост + почти белая "голова"
        dark:  { body: 'rgb(34,197,94)',   head: 'rgb(220,252,231)', glow: 'rgba(74,222,128,0.95)' }
    };

    // speed — строк за кадр (при 30 fps), len — длина хвоста, alpha — прозрачность слоя
    var LAYERS = [
        { fs: 12, speed: 0.10, len: [8, 14],  alpha: 0.55, density: 0.32 },
        { fs: 17, speed: 0.17, len: [10, 18], alpha: 0.80, density: 0.38 },
        { fs: 24, speed: 0.26, len: [12, 22], alpha: 1.00, density: 0.24 }
    ];

    var DEFAULTS = {
        theme: 'auto',   // 'auto' | 'light' | 'dark'
        edgeMin: 0.45,   // яркость в центре экрана (0..1), у краёв всегда 1
        maxFps: 30,
        intensity: 1,    // множитель плотности колонок
        zIndex: -1,
        pointer: true,   // реакция на курсор
        radius: 170,     // радиус "зоны дешифровки", px
        words: true
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
            var c = parseRGB(getComputedStyle(els[i]).backgroundColor);
            if (c && c.a > 0.05) {
                var lum = (0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b) / 255;
                return lum > 0.5 ? 'light' : 'dark';
            }
        }
        return 'light';
    }

    function start(opts) {
        var o = merge(opts);
        var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
        var theme = o.theme === 'auto' ? detectTheme() : o.theme;
        var pal = PALETTE[theme] || PALETTE.light;
        var frameMs = 1000 / o.maxFps;
        var R = o.radius, R2 = R * R;

        var canvas = document.createElement('canvas');
        canvas.id = 'rain-bg';
        canvas.setAttribute('aria-hidden', 'true');
        canvas.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;' +
            'pointer-events:none;z-index:' + o.zIndex + ';';
        document.body.insertBefore(canvas, document.body.firstChild);
        var ctx = canvas.getContext('2d');

        var W = 0, H = 0, dpr = 1, layers = [], atlasKey = '';
        var px = -9999, py = -9999;
        var raf = 0, last = 0, wordTimer = 0;

        /* ── Атлас: все символы одного слоя, строка 0 = хвост, строка 1 = светящаяся голова ── */
        function buildAtlas(L) {
            var n = CHARSET.length;
            L.cwp = Math.round(L.cw * dpr);
            L.chp = Math.round(L.ch * dpr);
            var cv = document.createElement('canvas');
            cv.width = L.cwp * n;
            cv.height = L.chp * 2;
            var g = cv.getContext('2d');
            g.scale(L.cwp / L.cw, L.chp / L.ch);
            g.font = 'bold ' + L.fs + 'px "Courier New", ui-monospace, Menlo, Consolas, monospace';
            g.textAlign = 'center';
            g.textBaseline = 'middle';
            for (var row = 0; row < 2; row++) {
                g.shadowBlur = row ? L.fs * 0.7 : 0;
                g.shadowColor = pal.glow;
                g.fillStyle = row ? pal.head : pal.body;
                for (var i = 0; i < n; i++) {
                    g.fillText(CHARSET.charAt(i),
                        i * L.cw + L.pad + L.colW / 2,
                        row * L.ch + L.pad + L.rowH / 2);
                }
            }
            L.atlas = cv;
        }

        function spawn(L, c, initial) {
            c.head = initial ? Math.random() * L.rows * 1.2 - L.rows * 0.2
                             : -(Math.random() * L.rows * 0.5 + 2);
            c.speed = L.speed * (0.7 + Math.random() * 0.6);
            c.len = (L.len[0] + Math.random() * (L.len[1] - L.len[0])) | 0;
            c.active = Math.random() < L.density * o.intensity;
            c.b = 0;
            c.mark.fill(0);
            for (var r = 0; r < c.chars.length; r++) c.chars[r] = RAND[(Math.random() * RAND.length) | 0];
        }

        function buildLayers() {
            var mobile = W < 700;
            layers = [];
            LAYERS.forEach(function (cfg, idx) {
                if (mobile && idx === 0) return;              // на мобильных без дальнего слоя
                var L = {
                    fs: cfg.fs, speed: cfg.speed, len: cfg.len, alpha: cfg.alpha,
                    density: cfg.density * (mobile ? 0.7 : 1)
                };
                L.colW = Math.round(L.fs * 0.62);
                L.rowH = Math.round(L.fs * 1.12);
                L.pad = Math.ceil(L.fs * 0.45);
                L.cw = L.colW + 2 * L.pad;
                L.ch = L.rowH + 2 * L.pad;
                L.rows = Math.ceil(H / L.rowH) + 2;
                var ncols = Math.ceil(W / L.colW);
                L.cols = [];
                for (var i = 0; i < ncols; i++) {
                    var c = {
                        x: i * L.colW,
                        chars: new Uint8Array(L.rows + 1),
                        mark: new Uint8Array(L.rows + 1)
                    };
                    var nx = (c.x + L.colW / 2) / W;
                    c.edge = o.edgeMin + (1 - o.edgeMin) * Math.pow(Math.abs(nx * 2 - 1), 1.1);
                    spawn(L, c, true);
                    L.cols.push(c);
                }
                buildAtlas(L);
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
            buildLayers();
            if (reduce) { draw(); }
        }

        /* ── Слово-шифр "проявляется" в падающей колонке крупного слоя ── */
        function injectWord() {
            var L = layers[layers.length - 1];
            if (!L || document.hidden) return;
            var w = WORDS[(Math.random() * WORDS.length) | 0];
            var c = L.cols[(Math.random() * L.cols.length) | 0];
            var r0 = Math.floor(L.rows * (0.2 + Math.random() * 0.4));
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

        function step() {
            for (var li = 0; li < layers.length; li++) {
                var L = layers[li];
                for (var ci = 0; ci < L.cols.length; ci++) {
                    var c = L.cols[ci], b = 0;
                    if (c.active && px > -9000) {
                        var dx = c.x + L.colW * 0.5 - px, dy = c.head * L.rowH - py;
                        var d2 = dx * dx + dy * dy;
                        if (d2 < R2) b = 1 - Math.sqrt(d2) / R;
                    }
                    c.b = b;
                    c.head += c.speed * (1 + b * 1.1);
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
            for (var li = 0; li < layers.length; li++) {
                var L = layers[li];
                var at = L.atlas, cw = L.cw, ch = L.ch, cwp = L.cwp, chp = L.chp;
                var pad = L.pad, rowH = L.rowH, rows = L.rows;
                for (var ci = 0; ci < L.cols.length; ci++) {
                    var c = L.cols[ci];
                    if (!c.active) continue;
                    var h = Math.floor(c.head), len = c.len;
                    var base = L.alpha * c.edge * (1 + 0.6 * c.b);
                    var x = c.x - pad;
                    for (var k = 0; k <= len; k++) {
                        var r = h - k;
                        if (r < 0) break;
                        if (r >= rows) continue;
                        var t = 1 - k / (len + 1);
                        var a = t * t, row = 0, gi = c.chars[r];
                        if (k === 0) {                                   // мерцающая светящаяся голова
                            row = 1; a = 1;
                            gi = RAND[(Math.random() * RAND.length) | 0];
                        } else if (c.mark[r]) {                          // буквы слова-шифра
                            row = 1;
                            a = Math.max(a, 0.7 * Math.min(1, (len - k + 1) / 4));
                        }
                        a *= base;
                        if (a > 1) a = 1;
                        if (a < 0.03) continue;
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
            if (o.words && !wordTimer) wordTimer = setInterval(injectWord, 3800);
        }
        function stop() {
            if (raf) { cancelAnimationFrame(raf); raf = 0; }
            if (wordTimer) { clearInterval(wordTimer); wordTimer = 0; }
        }

        if (o.pointer && !reduce) {
            window.addEventListener('pointermove', function (e) { px = e.clientX; py = e.clientY; }, { passive: true });
            document.addEventListener('pointerleave', function () { px = py = -9999; });
        }
        var rt;
        window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(resize, 200); });
        document.addEventListener('visibilitychange', function () { document.hidden ? stop() : run(); });

        resize();
        run();
        return { stop: stop, run: run, canvas: canvas };
    }

    var instance = null;
    function boot(opts) {
        if (instance) return instance;
        if (!document.body) {
            document.addEventListener('DOMContentLoaded', function () { boot(opts); });
            return null;
        }
        instance = start(opts);
        return instance;
    }

    window.initDigitalRainBackground = boot;
    // обратная совместимость: старые вызовы (about.js, self.html) теперь тоже запускают фон
    window.initDigitalRain = function (_targets, opts) { return boot(opts); };
    window.initDigitalRainInBlocks = function (_root, opts) { return boot(opts); };
})();