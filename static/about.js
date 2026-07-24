/**
 * about.js — Premium Interactive Engine «Kriptologiya maktabi»
 *
 * 1. Cyber Canvas — перспективная кибер-сетка с glowing nodes (hero)
 * 2. 3D Mouse Tracking — карточки курсов следят за мышью
 * 3. Bidirectional IntersectionObserver — двусторонняя анимация скролла
 * 4. Infinite Carousel — Clone Buffer Pattern (бесшовный цикл)
 * 5. Hero Parallax — лёгкий параллакс aurora-пятен
 * 6. Smooth Scroll — якорные ссылки
 *
 * Vanilla JS, без зависимостей.
 */

(function () {
    "use strict";

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }

    function boot() {
        initCyberCanvas();
        init3DCards();
        initBidirectionalObserver();
        initInfiniteCarousels();
        initHeroParallax();
        initSmoothScroll();
    }

    // ================================================================
    // 1. CYBER CANVAS — перспективная сетка + glowing nodes (hero bg)
    // ================================================================
    function initCyberCanvas() {
        var canvas = document.getElementById("hero-canvas");
        if (!canvas) return;

        var ctx = canvas.getContext("2d");
        var W, H;
        var nodes = [];
        var animId = null;

        function resize() {
            W = canvas.width  = canvas.offsetWidth;
            H = canvas.height = canvas.offsetHeight;
            buildNodes();
        }

        /**
         * Строим перспективную сетку узлов.
         * Чем ниже строка — тем больше узлов, крупнее и ярче.
         */
        function buildNodes() {
            nodes = [];
            var cols = 14;
            var rows = 8;

            for (var r = 0; r < rows; r++) {
                var t  = r / (rows - 1);               // 0 (верх) … 1 (низ)
                var py = Math.pow(t, 0.55);             // перспективное сжатие
                var y  = py * H * 0.82 + H * 0.1;

                var colsInRow = Math.floor(cols * (0.3 + t * 0.7));
                var rowW = W * (0.25 + t * 0.75);
                var startX  = (W - rowW) / 2;

                for (var c = 0; c < colsInRow; c++) {
                    var x = startX + (c / (colsInRow - 1 || 1)) * rowW;
                    nodes.push({
                        bx: x,                                // базовая X
                        by: y,                                // базовая Y
                        x:  x, y: y,                          // текущие (дрейфуют)
                        r:  1 + t * 2.2,                      // радиус
                        a:  0.08 + t * 0.55,                  // прозрачность
                        ph: Math.random() * Math.PI * 2,      // фаза синуса
                        sp: 0.002 + Math.random() * 0.008     // скорость
                    });
                }
            }
        }

        function frame(ts) {
            ctx.clearRect(0, 0, W, H);

            // Дрейф узлов (синусоидальное «дыхание»)
            for (var i = 0; i < nodes.length; i++) {
                var n = nodes[i];
                n.x = n.bx + Math.sin(ts * n.sp + n.ph) * 0.7;
                n.y = n.by + Math.cos(ts * n.sp * 1.4 + n.ph) * 0.4;
            }

            // Соединительные линии между близкими узлами
            var maxD = 140;
            for (var i = 0; i < nodes.length; i++) {
                for (var j = i + 1; j < nodes.length; j++) {
                    var dx = nodes[i].x - nodes[j].x;
                    var dy = nodes[i].y - nodes[j].y;
                    var d  = Math.sqrt(dx * dx + dy * dy);
                    if (d < maxD) {
                        var la = 0.05 * (1 - d / maxD);
                        ctx.beginPath();
                        ctx.moveTo(nodes[i].x, nodes[i].y);
                        ctx.lineTo(nodes[j].x, nodes[j].y);
                        ctx.strokeStyle = "rgba(59,130,246," + la + ")";
                        ctx.lineWidth = 0.45;
                        ctx.stroke();
                    }
                }
            }

            // Отрисовка узлов с радиальным свечением
            for (var k = 0; k < nodes.length; k++) {
                var n  = nodes[k];
                var ga = n.a * (0.55 + 0.45 * Math.sin(ts * 0.0018 + n.ph));

                // Внешний glow
                var grad = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, n.r * 5);
                grad.addColorStop(0,    "rgba(96,165,250,"  + ga + ")");
                grad.addColorStop(0.35, "rgba(59,130,246,"  + ga * 0.35 + ")");
                grad.addColorStop(1,    "rgba(59,130,246,0)");
                ctx.beginPath();
                ctx.arc(n.x, n.y, n.r * 5, 0, Math.PI * 2);
                ctx.fillStyle = grad;
                ctx.fill();

                // Ядро
                ctx.beginPath();
                ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
                ctx.fillStyle = "rgba(147,197,253," + Math.min(1, ga * 1.4) + ")";
                ctx.fill();
            }

            animId = requestAnimationFrame(frame);
        }

        resize();
        window.addEventListener("resize", resize);
        animId = requestAnimationFrame(frame);
    }


    // ================================================================
    // 2. 3D MOUSE TRACKING — карточки курсов
    // ================================================================
    function init3DCards() {
        var cards = document.querySelectorAll("[data-3d]");
        if (!cards.length) return;
        if ("ontouchstart" in window) return; // не нужно на тач-устройствах

        for (var i = 0; i < cards.length; i++) {
            (function (card) {
                card.addEventListener("mousemove", function (e) {
                    var r = card.getBoundingClientRect();
                    var rx = ((e.clientX - r.left) / r.width  - 0.5) * 2;
                    var ry = ((e.clientY - r.top)  / r.height - 0.5) * 2;
                    card.style.transform =
                        "perspective(800px) rotateX(" + (-ry * 7) + "deg) rotateY(" + (rx * 9) + "deg) translateY(-4px)";
                    card.style.transition = "transform 0.1s ease-out";
                });
                card.addEventListener("mouseleave", function () {
                    card.style.transform =
                        "perspective(800px) rotateX(0deg) rotateY(0deg) translateY(0px)";
                    card.style.transition = "transform 0.6s cubic-bezier(0.34,1.56,0.64,1)";
                });
            })(cards[i]);
        }
    }


    // ================================================================
    // 3. BIDIRECTIONAL INTERSECTION OBSERVER
    //    КЛЮЧ: не вызываем unobserve() — элементы отслеживаются постоянно.
    //    Скролл вниз  → .aos-show добавляется (плавное появление)
    //    Скролл вверх → .aos-show убирается  (элемент «упаковывается»)
    // ================================================================
    function initBidirectionalObserver() {
        var els = document.querySelectorAll("[data-aos]");
        if (!els.length) return;

        if (!("IntersectionObserver" in window)) {
            for (var f = 0; f < els.length; f++) els[f].classList.add("aos-show");
            return;
        }

        var obs = new IntersectionObserver(function (entries) {
            for (var i = 0; i < entries.length; i++) {
                var e = entries[i];
                if (e.isIntersecting) {
                    e.target.classList.add("aos-show");
                } else {
                    e.target.classList.remove("aos-show");
                }
            }
        }, { threshold: 0.06, rootMargin: "0px 0px -35px 0px" });

        for (var j = 0; j < els.length; j++) obs.observe(els[j]);
    }


    // ================================================================
    // 4. INFINITE CAROUSEL — Clone Buffer Pattern
    //
    //   Алгоритм:
    //     Трек после клонирования:
    //       [8c,9c,10c,11c, 0,1,...,11, 0c,1c,2c,3c]
    //        ↑ prepend 4       originals    ↑ append 4
    //
    //     Стартовый индекс = visibleCount (4)
    //
    //     ВПЕРЁД: анимация до индекса 15, затем до 16 (чистые клоны).
    //             На transitionend → мгновенный сброс на индекс 4.
    //             Визуально незаметно: клоны выглядят как оригиналы.
    //
    //     НАЗАД:  анимация до индекса 0 (prepend-клоны).
    //             Затем prev → мгновенный прыжок на последнюю
    //             страницу оригиналов (индекс startIdx + totalOrig - vis).
    // ================================================================
    function initInfiniteCarousels() {
        var wrappers = document.querySelectorAll("[data-carousel]");
        for (var w = 0; w < wrappers.length; w++) {
            buildInfiniteCarousel(wrappers[w]);
        }
    }

    function buildInfiniteCarousel(wrapper) {
        var track   = wrapper.querySelector(".carousel__track");
        var btnPrev = wrapper.querySelector(".carousel__arr--prev");
        var btnNext = wrapper.querySelector(".carousel__arr--next");
        var vp      = wrapper.querySelector(".carousel__vp");
        if (!track || !btnPrev || !btnNext) return;

        var origCards = Array.prototype.slice.call(track.children);
        var totalOrig = origCards.length;
        if (totalOrig === 0) return;

        // Определяем количество видимых карточек
        function getVisible() {
            if (!origCards[0]) return 4;
            var style = window.getComputedStyle(origCards[0]);
            var fb = style.flexBasis;
            var m = fb.match(/\/\s*(\d+)/);
            if (m) return parseInt(m[1], 10);
            var vw = vp ? vp.offsetWidth : wrapper.offsetWidth;
            var cw = origCards[0].offsetWidth;
            if (cw > 0) return Math.max(1, Math.floor(vw / cw));
            var ww = window.innerWidth;
            if (ww <= 480) return 1;
            if (ww <= 768) return 1;
            if (ww <= 1024) return 2;
            return 4;
        }

        var vis = getVisible();
        if (vis >= totalOrig) {
            btnPrev.style.display = "none";
            btnNext.style.display = "none";
            return;
        }

        // ── Клонируем буферы ──
        // prepend: последние vis карточек
        var prependClones = [];
        for (var p = totalOrig - vis; p < totalOrig; p++) {
            prependClones.push(origCards[p].cloneNode(true));
        }
        // append: первые vis карточек
        var appendClones = [];
        for (var a = 0; a < vis; a++) {
            appendClones.push(origCards[a].cloneNode(true));
        }

        // Вставляем prepend в начало (обратный порядок!)
        for (var pi = prependClones.length - 1; pi >= 0; pi--) {
            track.insertBefore(prependClones[pi], track.firstChild);
        }
        // Вставляем append в конец
        for (var ai = 0; ai < appendClones.length; ai++) {
            track.appendChild(appendClones[ai]);
        }

        // ── Состояние ──
        var allCards   = track.children;
        var totalAll   = allCards.length;            // = totalOrig + 2*vis
        var startIdx   = vis;                        // индекс первого оригинала
        var currentIdx = startIdx;
        var animating  = false;

        function getStep() {
            if (!allCards[0]) return 0;
            var cw  = allCards[0].offsetWidth;
            var gap = parseFloat(window.getComputedStyle(track).gap) || 18;
            return cw + gap;
        }

        function go(idx, animate) {
            track.style.transition = animate
                ? "transform 0.5s cubic-bezier(0.16, 1, 0.3, 1)"
                : "none";
            track.style.transform = "translateX(" + (-idx * getStep()) + "px)";
            currentIdx = idx;
        }

        function onEnd(fn) {
            track.addEventListener("transitionend", function h() {
                track.removeEventListener("transitionend", h);
                animating = false;
                fn();
            });
        }

        // ── NEXT (всегда анимация вперёд) ──
        function next() {
            if (animating) return;
            animating = true;
            var nxt = currentIdx + 1;

            // Зашли в зону чистых клонов?
            if (nxt > startIdx + totalOrig - 1) {
                go(nxt, true);
                onEnd(function () {
                    // Сброс на оригиналы (мгновенно, незаметно)
                    go(startIdx + ((nxt - startIdx) % totalOrig), false);
                });
            } else {
                go(nxt, true);
                onEnd(function () {});
            }
        }

        // ── PREV ──
        function prev() {
            if (animating) return;
            animating = true;
            var prv = currentIdx - 1;

            if (prv < 0) {
                // Мгновенный прыжок на последнюю страницу оригиналов
                go(startIdx + totalOrig - vis, false);
                animating = false;
            } else {
                go(prv, true);
                onEnd(function () {});
            }
        }

        btnNext.addEventListener("click", next);
        btnPrev.addEventListener("click", prev);

        // ── Touch / Swipe ──
        var tsX = 0, tsY = 0;
        track.addEventListener("touchstart", function (e) {
            tsX = e.changedTouches[0].screenX;
            tsY = e.changedTouches[0].screenY;
        }, { passive: true });

        track.addEventListener("touchend", function (e) {
            var teX = e.changedTouches[0].screenX;
            var teY = e.changedTouches[0].screenY;
            var dX = tsX - teX;
            var dY = tsY - teY;
            if (Math.abs(dY) > Math.abs(dX)) return;
            if (Math.abs(dX) < 35) return;
            if (dX > 0) next(); else prev();
        });

        // ── Ресайз ──
        var rt;
        window.addEventListener("resize", function () {
            clearTimeout(rt);
            rt = setTimeout(function () {
                vis = getVisible();
                go(currentIdx, false);
            }, 250);
        });
    }


    // ================================================================
    // 5. HERO PARALLAX — aurora-пятна двигаются при скролле
    // ================================================================
    function initHeroParallax() {
        var hero = document.querySelector(".hero");
        var aurL = document.querySelector(".hero-aurora--L");
        var aurR = document.querySelector(".hero-aurora--R");
        var cnt  = document.querySelector(".hero-content");
        if (!hero) return;

        var ticking = false;
        window.addEventListener("scroll", function () {
            if (!ticking) {
                requestAnimationFrame(function () {
                    var sy = window.pageYOffset;
                    var hh = hero.offsetHeight;
                    if (sy < hh) {
                        var f = sy / hh;
                        if (aurL) aurL.style.transform = "translateY(" + (f * 50) + "px)";
                        if (aurR) aurR.style.transform = "translateY(" + (-f * 40) + "px)";
                        if (cnt)  { cnt.style.transform = "translateY(" + (f * 20) + "px)"; cnt.style.opacity = 1 - f * 0.5; }
                    }
                    ticking = false;
                });
                ticking = true;
            }
        }, { passive: true });
    }


    // ================================================================
    // 6. SMOOTH SCROLL
    // ================================================================
    function initSmoothScroll() {
        document.addEventListener("click", function (e) {
            var link = e.target.closest('a[href^="#"]');
            if (!link) return;
            var href = link.getAttribute("href");
            if (!href || href === "#") return;
            var target = document.querySelector(href);
            if (!target) return;
            e.preventDefault();
            var top = target.getBoundingClientRect().top + window.pageYOffset - 65;
            window.scrollTo({ top: top, behavior: "smooth" });
        });
    }

})();
