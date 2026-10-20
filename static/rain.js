/* static/rain.js — зелёный "digital rain" на белом фоне (канвас прозрачный) */
(function () {
    'use strict';

    var CHARS = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'.split('');
    var DEFAULTS = {
        color: '22,163,74',   // RGB зелёного (tailwind green-600)
        fontSize: 16,         // размер символа, px
        frameMs: 60,          // период кадра (больше = медленнее)
        fade: 0.07,           // скорость затухания хвоста (меньше = длиннее хвост)
        density: 0.55,        // доля активных колонок 0..1
        opacity: 0.45         // общая прозрачность слоя 0..1
    };

    function injectStyle() {
        if (document.getElementById('rain-style')) return;
        var st = document.createElement('style');
        st.id = 'rain-style';
        st.textContent =
            '.rain-host{isolation:isolate;}' +
            '.rain-canvas{position:absolute;top:0;left:0;width:100%;height:100%;' +
            'z-index:-1;pointer-events:none;}';
        document.head.appendChild(st);
    }

    function merge(o) {
        var r = {}, k;
        for (k in DEFAULTS) r[k] = DEFAULTS[k];
        for (k in (o || {})) r[k] = o[k];
        return r;
    }

    function Rain(host, o) {
        if (host.__rain) return;
        host.__rain = true;
        if (getComputedStyle(host).position === 'static') host.style.position = 'relative';
        host.classList.add('rain-host');

        var canvas = document.createElement('canvas');
        canvas.className = 'rain-canvas';
        canvas.setAttribute('aria-hidden', 'true');
        canvas.style.opacity = o.opacity;
        host.insertBefore(canvas, host.firstChild);

        var ctx = canvas.getContext('2d');
        var fs = o.fontSize, w = 0, h = 0, cols = 0;
        var drops = [], speeds = [], active = [];
        var raf = 0, last = 0, visible = false;

        function resize() {
            w = host.clientWidth; h = host.clientHeight;
            if (!w || !h) return;
            var dpr = Math.min(window.devicePixelRatio || 1, 2);
            canvas.width = w * dpr; canvas.height = h * dpr;
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            ctx.font = 'bold ' + fs + 'px "Courier New", monospace';
            ctx.textBaseline = 'top';
            var n = Math.ceil(w / fs);
            if (n !== cols) {
                cols = n; drops = []; speeds = []; active = [];
                for (var i = 0; i < cols; i++) {
                    drops.push(Math.floor(Math.random() * -(h / fs)));
                    speeds.push(0.4 + Math.random() * 0.6);
                    active.push(Math.random() < o.density);
                }
            }
        }

        function frame(t) {
            raf = requestAnimationFrame(frame);
            if (t - last < o.frameMs || !cols) return;
            last = t;

            // плавно "стираем" прошлые кадры (канвас прозрачный -> destination-out)
            ctx.globalCompositeOperation = 'destination-out';
            ctx.fillStyle = 'rgba(0,0,0,' + o.fade + ')';
            ctx.fillRect(0, 0, w, h);
            ctx.globalCompositeOperation = 'source-over';
            ctx.fillStyle = 'rgba(' + o.color + ',0.95)';

            for (var i = 0; i < cols; i++) {
                if (!active[i] || Math.random() > speeds[i]) continue;
                var y = drops[i] * fs;
                if (y >= 0 && y < h) {
                    ctx.fillText(CHARS[(Math.random() * CHARS.length) | 0], i * fs, y);
                }
                drops[i]++;
                if (y > h && Math.random() > 0.975) drops[i] = Math.floor(Math.random() * -20);
            }
        }

        function start() { if (!raf) raf = requestAnimationFrame(frame); }
        function stop() { if (raf) { cancelAnimationFrame(raf); raf = 0; } }

        resize();

        if ('ResizeObserver' in window) new ResizeObserver(resize).observe(host);
        else window.addEventListener('resize', resize);

        // анимация идёт только пока блок на экране
        if ('IntersectionObserver' in window) {
            new IntersectionObserver(function (e) {
                visible = e[0].isIntersecting;
                visible ? start() : stop();
            }, { threshold: 0 }).observe(host);
        } else start();
    }

    var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;

    /** targets: CSS-селектор | NodeList | массив элементов */
    window.initDigitalRain = function (targets, opts) {
        if (reduce) return;
        injectStyle();
        var o = merge(opts);
        var els = typeof targets === 'string' ? document.querySelectorAll(targets) : targets;
        Array.prototype.forEach.call(els, function (el) { Rain(el, o); });
    };

    /* ── авто-поиск БЕЛЫХ блоков внутри root (для контента из БД) ── */
    function bg(el) {
        var cs = getComputedStyle(el);
        var m = cs.backgroundColor.match(/rgba?\(([^)]+)\)/);
        if (!m) return { a: 0 };
        var p = m[1].split(/[,\s\/]+/).filter(Boolean).map(parseFloat);
        return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
    }
    function collect(parent, depth, out) {
        Array.prototype.forEach.call(parent.children, function (el) {
            if (/^(SCRIPT|STYLE|LINK|META|TEMPLATE|CANVAS)$/.test(el.tagName)) return;
            var b = bg(el);
            if (b.a > 0.5) {
                // непрозрачный фон: белый -> хост; цветной (синий hero и т.п.) -> пропускаем целиком
                if (b.r >= 225 && b.g >= 225 && b.b >= 225 && el.offsetHeight >= 80) out.push(el);
                return;
            }
            if (depth < 3 && el.children.length) collect(el, depth + 1, out);
        });
    }
    window.initDigitalRainInBlocks = function (root, opts) {
        if (!root) return;
        var hosts = [];
        collect(root, 0, hosts);
        // ручная разметка в HTML из БД: class="rain-bg" или data-rain
        Array.prototype.forEach.call(root.querySelectorAll('.rain-bg,[data-rain]'), function (el) {
            if (hosts.indexOf(el) === -1) hosts.push(el);
        });
        window.initDigitalRain(hosts, opts);
    };
})();