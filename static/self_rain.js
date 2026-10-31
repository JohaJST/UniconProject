/**
 * self_rain.js — «Neural Knowledge Matrix» для Self Study.
 * - Потоки символов только в боковых кулисах (центральный лист не засоряется).
 * - 2 слоя глубины: дальний (мелкий, тусклый) и ближний (крупный, со свечением).
 * - Нейро-линии между близкими головными символами.
 * - Скорость реагирует на скролл.
 * Vanilla JS, один canvas, пауза на скрытой вкладке.
 */
(function () {
    'use strict';

    var GLYPHS = '0123456789ABCDEF∑Δπλ Ω⊕0x'.replace(/ /g, '').split('');
    // сапфир, кобальт, бирюза, золото
    var PALETTE = [
        { h: '#1e3a8a', t: '30,58,138'  },
        { h: '#2563eb', t: '37,99,235'  },
        { h: '#0891b2', t: '8,145,178'  },
        { h: '#d97706', t: '217,119,6'  }
    ];

    function rnd(a, b) { return a + Math.random() * (b - a); }
    function pick(arr) { return arr[(Math.random() * arr.length) | 0]; }

    function start(opts) {
        opts = opts || {};
        var canvas = document.getElementById(opts.canvasId || 'svRain');
        if (!canvas) return;
        var ctx = canvas.getContext('2d');
        var contentMax = opts.contentMax || 900;
        var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;

        var W = 0, H = 0, dpr = 1, streams = [], raf = 0;
        var boost = 0, lastY = window.pageYOffset;
        var LINK = 115;

        function build() {
            streams = [];
            var narrow = W < contentMax + 160;                 // кулис почти нет
            var sheetW = Math.min(contentMax, W - 32);
            var left = (W - sheetW) / 2 - 14, right = (W + sheetW) / 2 + 14;
            var step = W < 700 ? 26 : 22;

            for (var x = step / 2; x < W; x += step) {
                var inside = x > left && x < right;
                if (inside && !narrow) continue;               // центр чистый
                var near = Math.random() > 0.55;
                var c = pick(PALETTE);
                var len = near ? (8 + (Math.random() * 10 | 0)) : (6 + (Math.random() * 8 | 0));
                var chars = [];
                for (var k = 0; k < len; k++) chars.push(pick(GLYPHS));
                streams.push({
                    x: x, y: rnd(-H, H),
                    fs: near ? (17 + (Math.random() * 5 | 0)) : (11 + (Math.random() * 3 | 0)),
                    speed: near ? rnd(1.1, 2.2) : rnd(0.6, 1.2),
                    near: near, color: c, chars: chars, len: len,
                    tick: (Math.random() * 20) | 0,
                    // на узких экранах — приглушаем, чтобы не мешать чтению
                    a: narrow ? 0.28 : (near ? 0.85 : 0.55)
                });
            }
        }

        function resize() {
            dpr = Math.min(window.devicePixelRatio || 1, 2);
            W = window.innerWidth; H = window.innerHeight;
            canvas.width = Math.round(W * dpr);
            canvas.height = Math.round(H * dpr);
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            build();
            if (reduce) draw(0);
        }

        function draw(dt) {
            ctx.clearRect(0, 0, W, H);
            var heads = [];
            ctx.textAlign = 'center';

            for (var i = 0; i < streams.length; i++) {
                var s = streams[i];
                s.y += s.speed * (1 + boost) * dt;
                s.tick++;
                if (s.tick % 12 === 0) s.chars[0] = pick(GLYPHS);
                if (s.tick % 7 === 0) s.chars[1 + ((Math.random() * (s.len - 1)) | 0)] = pick(GLYPHS);
                if (s.y - s.len * s.fs * 1.15 > H) {
                    s.y = -s.fs * 2;
                    s.speed *= rnd(0.9, 1.1);
                    s.speed = Math.max(0.5, Math.min(2.4, s.speed));
                }

                ctx.font = '700 ' + s.fs + 'px "JetBrains Mono", Consolas, monospace';
                for (var j = 0; j < s.len; j++) {
                    var cy = s.y - j * s.fs * 1.15;
                    if (cy < -20 || cy > H + 20) continue;
                    if (j === 0) {
                        ctx.globalAlpha = s.a;
                        ctx.fillStyle = s.color.h;
                        if (s.near) { ctx.shadowColor = s.color.h; ctx.shadowBlur = 10; }
                        ctx.fillText(s.chars[0], s.x, cy);
                        ctx.shadowBlur = 0;
                        heads.push({ x: s.x, y: cy, c: s.color.t, near: s.near });
                    } else {
                        ctx.globalAlpha = Math.max(0.03, (1 - j / s.len) * 0.6 * s.a);
                        ctx.fillStyle = 'rgb(' + s.color.t + ')';
                        ctx.fillText(s.chars[j], s.x, cy);
                    }
                }
            }

            // Созвездия: тонкие линии между близкими головами
            ctx.lineWidth = 0.8;
            for (var a = 0; a < heads.length; a++) {
                for (var b = a + 1; b < heads.length; b++) {
                    var dx = heads[a].x - heads[b].x;
                    if (dx > LINK || dx < -LINK) continue;
                    var dy = heads[a].y - heads[b].y;
                    if (dy > LINK || dy < -LINK) continue;
                    var d = Math.sqrt(dx * dx + dy * dy);
                    if (d < LINK) {
                        ctx.globalAlpha = (1 - d / LINK) * 0.35;
                        ctx.strokeStyle = 'rgb(' + heads[a].c + ')';
                        ctx.beginPath();
                        ctx.moveTo(heads[a].x, heads[a].y);
                        ctx.lineTo(heads[b].x, heads[b].y);
                        ctx.stroke();
                    }
                }
            }
            // Узлы на головах
            for (var n = 0; n < heads.length; n++) {
                if (!heads[n].near) continue;
                ctx.globalAlpha = 0.55;
                ctx.fillStyle = 'rgb(' + heads[n].c + ')';
                ctx.beginPath();
                ctx.arc(heads[n].x, heads[n].y - 6, 1.8, 0, 6.2832);
                ctx.fill();
            }
            ctx.globalAlpha = 1;
        }

        var last = 0;
        function loop(ts) {
            raf = requestAnimationFrame(loop);
            var dt = last ? Math.min(2.5, (ts - last) / 16.67) : 1;
            last = ts;
            boost *= Math.pow(0.93, dt);                       // затухание реакции на скролл
            draw(dt);
        }
        function run()  { if (!reduce && !raf) { last = 0; raf = requestAnimationFrame(loop); } }
        function stop() { if (raf) { cancelAnimationFrame(raf); raf = 0; } }

        window.addEventListener('scroll', function () {
            var y = window.pageYOffset;
            boost = Math.min(4, boost + Math.abs(y - lastY) * 0.02);
            lastY = y;
        }, { passive: true });

        var rt;
        window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(resize, 150); });
        document.addEventListener('visibilitychange', function () { document.hidden ? stop() : run(); });

        resize();
        run();
    }

    window.initSelfStudyRain = start;
})();