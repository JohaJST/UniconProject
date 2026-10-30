/**
 * news.js — галерея новости: сцена + миниатюры + полноэкранный Lightbox.
 * Vanilla JS. Данные кадров — из <script id="news-slides" type="application/json">.
 */
(function () {
    "use strict";

    var dataEl = document.getElementById("news-slides");
    if (!dataEl) return;

    var slidesData;
    try { slidesData = JSON.parse(dataEl.textContent); } catch (e) { return; }
    var total = slidesData.length;
    if (!total) return;

    var stage   = document.getElementById("stage");
    var slides  = stage ? stage.querySelectorAll(".stage__slide") : [];
    var thumbsC = document.getElementById("thumbs");
    var thumbs  = thumbsC ? thumbsC.querySelectorAll(".thumb") : [];
    var counter = document.getElementById("stageCounter");

    var lb      = document.getElementById("lightbox");
    var lbImg   = document.getElementById("lbImg");
    var lbCount = document.getElementById("lbCounter");

    var idx = 0;
    var lastFocus = null;

    function pad(n) { return n < 10 ? "0" + n : String(n); }
    function label() { return pad(idx + 1) + " / " + pad(total); }

    function centerThumb(btn) {
        if (!thumbsC || !btn) return;
        thumbsC.scrollTo({
            left: btn.offsetLeft - (thumbsC.clientWidth - btn.clientWidth) / 2,
            behavior: "smooth"
        });
    }

    function lbShow(animate) {
        if (!lb || !lb.classList.contains("is-open")) return;
        var url = slidesData[idx].url;
        if (animate) {
            lbImg.classList.add("is-swap");
            setTimeout(function () { lbImg.src = url; lbImg.classList.remove("is-swap"); }, 160);
        } else {
            lbImg.src = url;
        }
        if (lbCount) lbCount.textContent = label();
    }

    function go(i) {
        idx = ((i % total) + total) % total;
        for (var s = 0; s < slides.length; s++) slides[s].classList.toggle("is-active", s === idx);
        for (var t = 0; t < thumbs.length; t++) thumbs[t].classList.toggle("is-active", t === idx);
        if (counter) counter.textContent = label();
        centerThumb(thumbs[idx]);
        lbShow(true);
    }

    function next() { go(idx + 1); }
    function prev() { go(idx - 1); }

    // ── Сцена ──
    if (stage) {
        stage.addEventListener("click", function (e) {
            if (e.target.closest(".stage__btn")) return;
            openLb();
        });
        var prevBtn = document.getElementById("stagePrev");
        var nextBtn = document.getElementById("stageNext");
        if (prevBtn) prevBtn.addEventListener("click", function (e) { e.stopPropagation(); prev(); });
        if (nextBtn) nextBtn.addEventListener("click", function (e) { e.stopPropagation(); next(); });

        stage.addEventListener("keydown", function (e) {
            if (e.key === "ArrowLeft") { e.preventDefault(); prev(); }
            else if (e.key === "ArrowRight") { e.preventDefault(); next(); }
            else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openLb(); }
        });
    }

    for (var k = 0; k < thumbs.length; k++) {
        (function (btn) {
            btn.addEventListener("click", function () {
                go(parseInt(btn.getAttribute("data-index"), 10) || 0);
            });
        })(thumbs[k]);
    }

    // ── Swipe (сцена и lightbox) ──
    function bindSwipe(el) {
        if (!el || total < 2) return;
        var x0 = 0, y0 = 0;
        el.addEventListener("touchstart", function (e) {
            x0 = e.changedTouches[0].clientX; y0 = e.changedTouches[0].clientY;
        }, { passive: true });
        el.addEventListener("touchend", function (e) {
            var dx = x0 - e.changedTouches[0].clientX;
            var dy = y0 - e.changedTouches[0].clientY;
            if (Math.abs(dx) < 40 || Math.abs(dy) > Math.abs(dx)) return;
            if (dx > 0) next(); else prev();
        }, { passive: true });
    }
    bindSwipe(stage);
    bindSwipe(lbImg);

    // ── Lightbox ──
    function openLb() {
        if (!lb) return;
        lastFocus = document.activeElement;
        lb.classList.add("is-open");
        lb.setAttribute("aria-hidden", "false");
        document.body.style.overflow = "hidden";
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
    }

    if (lb) {
        document.getElementById("lbClose").addEventListener("click", closeLb);
        var lp = document.getElementById("lbPrev");
        var ln = document.getElementById("lbNext");
        if (lp) lp.addEventListener("click", function (e) { e.stopPropagation(); prev(); });
        if (ln) ln.addEventListener("click", function (e) { e.stopPropagation(); next(); });

        // клик по тёмному фону (не по фото и не по кнопкам) закрывает
        lb.addEventListener("click", function (e) {
            if (e.target === lb) closeLb();
        });

        document.addEventListener("keydown", function (e) {
            if (!lb.classList.contains("is-open")) return;
            if (e.key === "Escape") closeLb();
            else if (e.key === "ArrowLeft") prev();
            else if (e.key === "ArrowRight") next();
        });
    }

    go(0);
})();