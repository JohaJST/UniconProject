/**
 * news.js — страница новости:
 *   1) поиск по списку новостей слева;
 *   2) 3D Coverflow-галерея (стрелки, точки, миниатюры, свайп, клавиатура, автопрокрутка);
 *   3) полноэкранный Lightbox.
 * Vanilla JS. Данные кадров — из <script id="news-slides" type="application/json">.
 */
(function () {
    "use strict";

    /* ═══════════ 1. Левый список ═══════════ */
    var side = document.getElementById("newsSide");
    if (side) {
        var list = document.getElementById("sideList");
        var search = document.getElementById("sideSearch");
        var empty = document.getElementById("sideEmpty");
        var current = list ? list.querySelector(".is-current") : null;

        // Прокручиваем ТОЛЬКО список (без скачка всей страницы), чтобы текущая новость была в центре.
        if (current && list) {
            var isRow = list.scrollWidth > list.clientWidth + 4;
            var li = current.parentNode;
            if (isRow) {
                list.scrollLeft = li.offsetLeft - (list.clientWidth - li.offsetWidth) / 2;
            } else {
                list.scrollTop = li.offsetTop - (list.clientHeight - li.offsetHeight) / 2;
            }
        }

        if (search && list) {
            search.addEventListener("input", function () {
                var q = search.value.trim().toLowerCase();
                var shown = 0;
                var items = list.children;
                for (var i = 0; i < items.length; i++) {
                    var a = items[i].querySelector(".side-item");
                    var hit = !q || (a && a.getAttribute("data-q").indexOf(q) !== -1);
                    items[i].hidden = !hit;
                    if (hit) shown++;
                }
                if (empty) empty.hidden = shown !== 0;
            });
        }
    }

    /* ═══════════ 2. Галерея ═══════════ */
    var dataEl = document.getElementById("news-slides");
    if (!dataEl) return;

    var slidesData;
    try { slidesData = JSON.parse(dataEl.textContent); } catch (e) { return; }
    var total = slidesData.length;
    if (!total) return;

    var stage    = document.getElementById("stage");
    var slides   = stage ? stage.querySelectorAll(".s3d") : [];
    var thumbsC  = document.getElementById("thumbs");
    var thumbs   = thumbsC ? thumbsC.querySelectorAll(".thumb") : [];
    var dotsC    = document.getElementById("dots");
    var dots     = dotsC ? dotsC.querySelectorAll(".dot") : [];
    var counter  = document.getElementById("stageCounter");
    var playBtn  = document.getElementById("stagePlay");
    var progress = document.getElementById("stageProgress");

    var lb      = document.getElementById("lightbox");
    var lbImg   = document.getElementById("lbImg");
    var lbCount = document.getElementById("lbCounter");

    var AUTOPLAY_MS = 5500;
    var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

    var idx = 0;
    var lastFocus = null;
    var timer = null;
    var playing = total > 1 && !reduce;
    var hovering = false;

    function pad(n) { return n < 10 ? "0" + n : String(n); }
    function label() { return pad(idx + 1) + " / " + pad(total); }
    function lbOpen() { return !!(lb && lb.classList.contains("is-open")); }

    /* ── Позиционирование слайдов в 3D ── */
    function layout() {
        for (var i = 0; i < slides.length; i++) {
            var d = ((i - idx) % total + total) % total;
            if (d > total / 2) d -= total;
            var ad = Math.abs(d);
            var el = slides[i];
            el.style.setProperty("--o", d);
            el.style.setProperty("--ao", ad);
            el.style.zIndex = String(10 - ad);
            el.classList.toggle("is-active", d === 0);
            el.classList.toggle("is-hidden", ad > 2);
            el.setAttribute("aria-hidden", d === 0 ? "false" : "true");
            if (d !== 0) {
                el.style.setProperty("--tx", 0);
                el.style.setProperty("--ty", 0);
            }
        }
    }

    function centerThumb(btn) {
        if (!thumbsC || !btn || thumbsC.offsetParent === null) return;
        thumbsC.scrollTo({
            left: btn.offsetLeft - (thumbsC.clientWidth - btn.clientWidth) / 2,
            behavior: "smooth"
        });
    }

    /* ── Автопрокрутка + полоса прогресса ── */
    function resetProgress() {
        if (!progress) return;
        progress.style.transition = "none";
        progress.style.width = "0";
    }
    function startProgress() {
        if (!progress) return;
        void progress.offsetWidth; // reflow, чтобы анимация стартовала заново
        progress.style.transition = "width " + AUTOPLAY_MS + "ms linear";
        progress.style.width = "100%";
    }
    function schedule() {
        clearTimeout(timer);
        resetProgress();
        if (!playing || hovering || lbOpen() || document.hidden) return;
        startProgress();
        timer = setTimeout(function () { go(idx + 1, true); }, AUTOPLAY_MS);
    }

    function lbShow(animate) {
        if (!lbOpen()) return;
        var url = slidesData[idx].url;
        if (animate) {
            lbImg.classList.add("is-swap");
            setTimeout(function () { lbImg.src = url; lbImg.classList.remove("is-swap"); }, 160);
        } else {
            lbImg.src = url;
        }
        if (lbCount) lbCount.textContent = label();
        // Предзагрузка соседей
        [1, -1].forEach(function (step) {
            var n = new Image();
            n.src = slidesData[((idx + step) % total + total) % total].url;
        });
    }

    function go(i, fromAuto) {
        idx = ((i % total) + total) % total;
        layout();
        for (var t = 0; t < thumbs.length; t++) thumbs[t].classList.toggle("is-active", t === idx);
        for (var d = 0; d < dots.length; d++) dots[d].classList.toggle("is-active", d === idx);
        if (counter) counter.textContent = label();
        centerThumb(thumbs[idx]);
        lbShow(true);
        schedule();
    }
    function next() { go(idx + 1); }
    function prev() { go(idx - 1); }

    /* ── Lightbox ── */
    function openLb() {
        if (!lb) return;
        lastFocus = document.activeElement;
        lb.classList.add("is-open");
        lb.setAttribute("aria-hidden", "false");
        document.body.style.overflow = "hidden";
        clearTimeout(timer);
        resetProgress();
        lbShow(false);
        var close = document.getElementById("lbClose");
        if (close) close.focus({ preventScroll: true });
    }
    function closeLb() {
        if (!lb) return;
        lb.classList.remove("is-open");
        lb.setAttribute("aria-hidden", "true");
        document.body.style.overflow = "";
        if (lastFocus && lastFocus.focus) lastFocus.focus({ preventScroll: true });
        schedule();
    }

    /* ── Сцена: клики, стрелки, drag/swipe, tilt ── */
    if (stage) {
        var sx = 0, dragging = false, moved = false;

        stage.addEventListener("pointerdown", function (e) {
            if (e.target.closest("button")) return;
            sx = e.clientX; dragging = true; moved = false;
        });
        stage.addEventListener("pointermove", function (e) {
            if (dragging && Math.abs(e.clientX - sx) > 8) moved = true;
            // лёгкий 3D-наклон центрального кадра за курсором (только мышь)
            if (e.pointerType === "mouse" && !dragging) {
                var act = stage.querySelector(".s3d.is-active");
                if (!act) return;
                var r = stage.getBoundingClientRect();
                var px = (e.clientX - r.left) / r.width - 0.5;
                var py = (e.clientY - r.top) / r.height - 0.5;
                act.style.setProperty("--tx", (px * 8).toFixed(2));
                act.style.setProperty("--ty", (-py * 6).toFixed(2));
            }
        });
        stage.addEventListener("pointerleave", function () {
            var act = stage.querySelector(".s3d.is-active");
            if (act) { act.style.setProperty("--tx", 0); act.style.setProperty("--ty", 0); }
        });
        window.addEventListener("pointerup", function (e) {
            if (!dragging) return;
            dragging = false;
            var dx = e.clientX - sx;
            if (total > 1 && Math.abs(dx) > 50) { dx < 0 ? next() : prev(); }
        });
        window.addEventListener("pointercancel", function () { dragging = false; });

        stage.addEventListener("click", function (e) {
            if (e.target.closest("button")) return;
            if (moved) { moved = false; return; }
            var s = e.target.closest(".s3d");
            if (!s) return;
            var i = parseInt(s.getAttribute("data-index"), 10) || 0;
            if (i === idx) openLb(); else go(i);
        });

        var prevBtn = document.getElementById("stagePrev");
        var nextBtn = document.getElementById("stageNext");
        if (prevBtn) prevBtn.addEventListener("click", function (e) { e.stopPropagation(); prev(); });
        if (nextBtn) nextBtn.addEventListener("click", function (e) { e.stopPropagation(); next(); });

        stage.addEventListener("keydown", function (e) {
            if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openLb(); }
        });

        // пауза автопрокрутки при наведении/фокусе
        stage.addEventListener("mouseenter", function () { hovering = true; schedule(); });
        stage.addEventListener("mouseleave", function () { hovering = false; schedule(); });
        stage.addEventListener("focusin", function () { hovering = true; schedule(); });
        stage.addEventListener("focusout", function () { hovering = false; schedule(); });
    }

    if (playBtn) {
        playBtn.classList.toggle("is-paused", !playing);
        playBtn.setAttribute("aria-pressed", playing ? "true" : "false");
        playBtn.addEventListener("click", function (e) {
            e.stopPropagation();
            playing = !playing;
            playBtn.classList.toggle("is-paused", !playing);
            playBtn.setAttribute("aria-pressed", playing ? "true" : "false");
            schedule();
        });
    }

    function bindIndexButtons(nodes) {
        for (var k = 0; k < nodes.length; k++) {
            (function (btn) {
                btn.addEventListener("click", function () {
                    go(parseInt(btn.getAttribute("data-index"), 10) || 0);
                });
            })(nodes[k]);
        }
    }
    bindIndexButtons(thumbs);
    bindIndexButtons(dots);

    /* ── Swipe в lightbox ── */
    if (lbImg && total > 1) {
        var x0 = 0, y0 = 0;
        lbImg.addEventListener("touchstart", function (e) {
            x0 = e.changedTouches[0].clientX; y0 = e.changedTouches[0].clientY;
        }, { passive: true });
        lbImg.addEventListener("touchend", function (e) {
            var dx = x0 - e.changedTouches[0].clientX;
            var dy = y0 - e.changedTouches[0].clientY;
            if (Math.abs(dx) < 40 || Math.abs(dy) > Math.abs(dx)) return;
            dx > 0 ? next() : prev();
        }, { passive: true });
    }

    if (lb) {
        document.getElementById("lbClose").addEventListener("click", closeLb);
        var lp = document.getElementById("lbPrev");
        var ln = document.getElementById("lbNext");
        if (lp) lp.addEventListener("click", function (e) { e.stopPropagation(); prev(); });
        if (ln) ln.addEventListener("click", function (e) { e.stopPropagation(); next(); });
        lb.addEventListener("click", function (e) { if (e.target === lb) closeLb(); });
    }

    /* ── Клавиатура (глобально) ── */
    document.addEventListener("keydown", function (e) {
        var tag = (e.target && e.target.tagName) || "";
        if (tag === "INPUT" || tag === "TEXTAREA") return;
        if (lbOpen() && e.key === "Escape") { closeLb(); return; }
        if (total < 2) return;
        if (e.key === "ArrowLeft") { e.preventDefault(); prev(); }
        else if (e.key === "ArrowRight") { e.preventDefault(); next(); }
    });

    document.addEventListener("visibilitychange", schedule);

    go(0);
})();