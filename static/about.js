/**
 * about.js — Premium Interactive Engine «Kriptologiya maktabi»
 *
 * 1. Cyber Canvas — перспективная кибер-сетка с glowing nodes (hero)
 * 2. 3D Mouse Tracking — карточки курсов следят за мышью
 * 3. Bidirectional IntersectionObserver — двусторонняя анимация скролла
 * 4. Infinite Carousel — Clone Buffer Pattern (бесшовный цикл)
 * 5. Hero Parallax — лёгкий параллакс aurora-пятен
 * 6. Smooth Scroll — якорные ссылки
 * 7. AI Presenter — голосовой ИИ-гид с синхронной хореографией интерфейса
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
        initAIPresenter();
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
        var prependClones = [];
        for (var p = totalOrig - vis; p < totalOrig; p++) {
            prependClones.push(origCards[p].cloneNode(true));
        }
        var appendClones = [];
        for (var a = 0; a < vis; a++) {
            appendClones.push(origCards[a].cloneNode(true));
        }

        for (var pi = prependClones.length - 1; pi >= 0; pi--) {
            track.insertBefore(prependClones[pi], track.firstChild);
        }
        for (var ai = 0; ai < appendClones.length; ai++) {
            track.appendChild(appendClones[ai]);
        }

        // ── Состояние ──
        var allCards   = track.children;
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

            if (nxt > startIdx + totalOrig - 1) {
                go(nxt, true);
                onEnd(function () {
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


    // ================================================================
        // 7. AI PRESENTER — Интерактивный голосовой гид + хореография DOM
        // ================================================================
        function initAIPresenter() {
            var root         = document.getElementById("aiPresenterRoot");
            var fab          = document.getElementById("aiPresenterFab");
            var dock         = document.getElementById("aiPresenterDock");
            if (!root || !fab || !dock) return;
    
            var eq           = document.getElementById("aiPresenterEq");
            var stepEl       = document.getElementById("aiPresenterStep");
            var secTitleEl   = document.getElementById("aiPresenterSecTitle");
            var subsTextEl   = document.getElementById("aiPresenterSubsText");
            var progressBar  = document.getElementById("aiDockProgressBar");
    
            var btnPrev      = document.getElementById("aiBtnPrev");
            var btnPlayPause = document.getElementById("aiBtnPlayPause");
            var btnNext      = document.getElementById("aiBtnNext");
            var btnRefocus   = document.getElementById("aiBtnRefocus");
            var btnClose     = document.getElementById("aiBtnClose");
    
            var NAVBAR_OFFSET = 65; // Высота sticky .navbar (60px) + буфер 5px
    
            // Состояние презентатора
            var scenes             = [];
            var loadedLang         = "";
            var preloadedAudios    = {};
            var currentIndex       = -1;
            var isTourActive       = false;
            var isPlaying          = false;
            var isLoadingManifest  = false;
            var userScrolled       = false;
            var carouselStepFired  = false;
            var triedStreamUrl     = false;
            var audioUnlocked      = false;
            var fallbackTimer      = null;
            var fallbackElapsed    = 0;
            var FALLBACK_DURATION  = 9.5;
    
            var audio = new Audio();
            audio.preload = "auto";
            audio.volume = 1.0;
    
            // ── Определение текущего активного языка (URL -> <html lang> -> data-lang) ──
            function detectCurrentLang() {
                var pathMatch = window.location.pathname.match(/^\/(uz|ru|en)(\/|$)/i);
                if (pathMatch) return pathMatch[1].toLowerCase();
    
                var htmlLang = (document.documentElement.getAttribute("lang") || "").trim().toLowerCase().slice(0, 2);
                if (htmlLang === "uz" || htmlLang === "ru" || htmlLang === "en") return htmlLang;
    
                var dataLang = (root.getAttribute("data-lang") || "").trim().toLowerCase().slice(0, 2);
                if (dataLang === "uz" || dataLang === "ru" || dataLang === "en") return dataLang;
    
                return "uz";
            }
    
            // ── Разблокировка HTML5 Audio в момент клика пользователя (Autoplay Policy Fix) ──
            function unlockAudioOnUserGesture() {
                if (audioUnlocked) return;
                try {
                    audio.muted = true;
                    audio.src = "data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA";
                    var p = audio.play();
                    if (p && typeof p.then === "function") {
                        p.then(function () {
                            audio.pause();
                            audio.muted = false;
                            audio.currentTime = 0;
                            audioUnlocked = true;
                        }).catch(function () {
                            audio.muted = false;
                        });
                    } else {
                        audio.pause();
                        audio.muted = false;
                        audioUnlocked = true;
                    }
                } catch (e) {
                    audio.muted = false;
                }
            }
    
            // ── Браузерный Web Speech API (резервный голос, если MP3 недоступен) ──
            function speakWithBrowserTTS(text, lang) {
                if (!("speechSynthesis" in window) || !text) return;
                try {
                    window.speechSynthesis.cancel();
                    var utter = new SpeechSynthesisUtterance(text);
                    utter.lang = (lang === "ru") ? "ru-RU" : (lang === "en" ? "en-US" : "uz-UZ");
                    utter.rate = 1.0;
                    window.speechSynthesis.speak(utter);
                } catch (e) {}
            }
    
            function stopBrowserTTS() {
                if ("speechSynthesis" in window) {
                    try { window.speechSynthesis.cancel(); } catch (e) {}
                }
            }
    
            function pad2(num) {
                return num < 10 ? "0" + num : String(num);
            }
    
            function clearAllChoreographyClasses() {
                var highlighted = document.querySelectorAll(
                    ".ai-highlight, .ai-card-open, .ai-partner-focus, .ai-focus"
                );
                for (var i = 0; i < highlighted.length; i++) {
                    highlighted[i].classList.remove(
                        "ai-highlight", "ai-card-open", "ai-partner-focus", "ai-focus"
                    );
                }
            }
    
            function clearActiveSections() {
                var secs = document.querySelectorAll("section.ai-sec-active");
                for (var i = 0; i < secs.length; i++) {
                    secs[i].classList.remove("ai-sec-active");
                }
            }
    
            function forceShowAosInSection(secEl) {
                if (!secEl) return;
                var aosEls = secEl.querySelectorAll("[data-aos]");
                for (var i = 0; i < aosEls.length; i++) {
                    aosEls[i].classList.add("aos-show");
                }
            }
    
            function setPlayingUI(playing) {
                isPlaying = playing;
                if (playing) {
                    dock.classList.add("ai-dock--playing");
                    if (eq) eq.classList.add("ai-eq--playing");
                } else {
                    dock.classList.remove("ai-dock--playing");
                    if (eq) eq.classList.remove("ai-eq--playing");
                }
            }
    
            function updateSubtitles(text) {
                if (!subsTextEl) return;
                subsTextEl.classList.add("ai-subs-fade");
                setTimeout(function () {
                    subsTextEl.textContent = text || "";
                    subsTextEl.classList.remove("ai-subs-fade");
                }, 160);
            }
    
            function scrollToSection(secEl) {
                if (!secEl) return;
                var top = secEl.getBoundingClientRect().top + window.pageYOffset - NAVBAR_OFFSET;
                window.scrollTo({
                    top: Math.max(0, top),
                    behavior: "smooth"
                });
            }
    
            function stopFallbackTimer() {
                if (fallbackTimer) {
                    clearInterval(fallbackTimer);
                    fallbackTimer = null;
                }
            }
    
            // ── Предзагрузка аудиофайлов следующих сцен ──
            function preloadRemainingScenes(startIdx) {
                for (var i = startIdx; i < scenes.length; i++) {
                    var url = scenes[i] && (scenes[i].audio_url || scenes[i].audio_stream_url);
                    if (url && !preloadedAudios[url]) {
                        var a = new Audio();
                        a.preload = "auto";
                        a.src = url;
                        preloadedAudios[url] = a;
                    }
                }
            }
    
            function getVisibleCarouselCards(carouselAttr, cardSelector) {
                var wrap = document.querySelector('[data-carousel="' + carouselAttr + '"]');
                if (!wrap) return [];
                var vp = wrap.querySelector(".carousel__vp") || wrap;
                var vpRect = vp.getBoundingClientRect();
                var allCards = wrap.querySelectorAll(cardSelector);
                var visible = [];
    
                for (var i = 0; i < allCards.length; i++) {
                    var r = allCards[i].getBoundingClientRect();
                    var center = r.left + r.width / 2;
                    if (center >= vpRect.left && center <= vpRect.right) {
                        visible.push(allCards[i]);
                    }
                }
                if (visible.length === 0 && allCards.length > 0) {
                    for (var j = 0; j < Math.min(4, allCards.length); j++) {
                        visible.push(allCards[j]);
                    }
                }
                return visible;
            }
    
            function triggerCarouselNext(carouselAttr) {
                var wrap = document.querySelector('[data-carousel="' + carouselAttr + '"]');
                if (!wrap) return;
                var nextBtn = wrap.querySelector(".carousel__arr--next");
                if (nextBtn && nextBtn.style.display !== "none") {
                    nextBtn.click();
                }
            }
    
            // ── Хореография внутри активной секции по прогрессу (0..1) ──
            function applySceneChoreography(scene, progress) {
                if (!scene) return;
                var secEl = document.querySelector(scene.section || scene.section_selector);
                if (!secEl) return;
    
                forceShowAosInSection(secEl);
                clearAllChoreographyClasses();
    
                var p = Math.max(0, Math.min(0.999, progress || 0));
                var sceneId = scene.id || scene.scene_id;
    
                if (sceneId === "hero") {
                    var heroTargets = [
                        secEl.querySelector(".hero-chip"),
                        secEl.querySelector(".hero-heading"),
                        secEl.querySelector(".hero-btns")
                    ];
                    var hIdx = Math.min(2, Math.floor(p * 3));
                    if (heroTargets[hIdx]) {
                        heroTargets[hIdx].classList.add("ai-highlight");
                    }
                } else if (sceneId === "goals") {
                    var panels = secEl.querySelectorAll(".goal-panel");
                    if (p < 0.5) {
                        if (panels[0]) panels[0].classList.add("ai-highlight");
                    } else {
                        if (panels[1]) panels[1].classList.add("ai-highlight");
                        var tasks = secEl.querySelectorAll(".task-row");
                        if (tasks.length > 0) {
                            var subP = (p - 0.5) / 0.5;
                            var tIdx = Math.min(tasks.length - 1, Math.floor(subP * tasks.length));
                            if (tasks[tIdx]) tasks[tIdx].classList.add("ai-highlight");
                        }
                    }
                } else if (sceneId === "courses") {
                    var grid = document.getElementById("coursesGrid") || secEl.querySelector(".courses-grid") || secEl;
                    var courseCards = grid.querySelectorAll(".c-card");
                    var count = Math.min(3, courseCards.length);
                    if (count > 0) {
                        var cIdx = Math.min(count - 1, Math.floor(p * count));
                        courseCards[cIdx].classList.add("ai-card-open", "ai-focus", "ai-highlight");
                    }
                } else if (sceneId === "teachers") {
                    if (p >= 0.5 && !carouselStepFired) {
                        carouselStepFired = true;
                        triggerCarouselNext("teachers");
                    }
                    var tCards = getVisibleCarouselCards("teachers", ".t-card");
                    if (tCards.length > 0) {
                        var localT = (p < 0.5) ? (p / 0.5) : ((p - 0.5) / 0.5);
                        var tcIdx = Math.min(tCards.length - 1, Math.floor(localT * tCards.length));
                        if (tCards[tcIdx]) tCards[tcIdx].classList.add("ai-highlight");
                    }
                } else if (sceneId === "news") {
                    if (p >= 0.5 && !carouselStepFired) {
                        carouselStepFired = true;
                        triggerCarouselNext("news");
                    }
                    var nCards = getVisibleCarouselCards("news", ".n-card");
                    if (nCards.length > 0) {
                        var localN = (p < 0.5) ? (p / 0.5) : ((p - 0.5) / 0.5);
                        var ncIdx = Math.min(nCards.length - 1, Math.floor(localN * nCards.length));
                        if (nCards[ncIdx]) nCards[ncIdx].classList.add("ai-highlight");
                    }
                } else if (sceneId === "partners") {
                    var firstGroup = secEl.querySelector(".marquee-group");
                    var partnerItems = firstGroup
                        ? firstGroup.querySelectorAll(".marquee-item")
                        : secEl.querySelectorAll(".marquee-item");
                    if (partnerItems.length > 0) {
                        var pIdx = Math.min(partnerItems.length - 1, Math.floor(p * partnerItems.length));
                        if (partnerItems[pIdx]) {
                            partnerItems[pIdx].classList.add("ai-partner-focus", "ai-focus");
                        }
                    }
                }
            }
    
            function updateProgressUI(sceneProgress) {
                if (!progressBar || scenes.length === 0) return;
                var totalProgress = ((currentIndex + Math.max(0, Math.min(1, sceneProgress))) / scenes.length) * 100;
                progressBar.style.width = totalProgress.toFixed(1) + "%";
            }
    
            // ── Попытка запуска аудио с автоматическим переключением на резервный stream URL ──
            function tryPlayAudioUrl(url, scene, isRetry) {
                audio.muted = false;
                audio.volume = 1.0;
                audio.src = url;
                audio.currentTime = 0;
    
                var playPromise = audio.play();
                if (playPromise && typeof playPromise.then === "function") {
                    playPromise.then(function () {
                        setPlayingUI(true);
                    }).catch(function () {
                        if (!isRetry && scene.audio_stream_url && scene.audio_stream_url !== url) {
                            triedStreamUrl = true;
                            tryPlayAudioUrl(scene.audio_stream_url, scene, true);
                        } else {
                            startFallbackPlayback(scene);
                        }
                    });
                } else {
                    setPlayingUI(true);
                }
            }
    
            // ── Переход к конкретной сцене ──
            function playScene(index) {
                if (index < 0 || index >= scenes.length) {
                    stopAndCloseTour();
                    return;
                }
    
                stopFallbackTimer();
                stopBrowserTTS();
                audio.pause();
                clearAllChoreographyClasses();
    
                currentIndex = index;
                carouselStepFired = false;
                triedStreamUrl = false;
    
                var scene = scenes[currentIndex];
                var secEl = document.querySelector(scene.section || scene.section_selector);
    
                document.body.classList.add("ai-tour-active");
                clearActiveSections();
                if (secEl) {
                    secEl.classList.add("ai-sec-active");
                    forceShowAosInSection(secEl);
                    if (!userScrolled) {
                        scrollToSection(secEl);
                    }
                }
    
                if (stepEl) {
                    stepEl.textContent = pad2(currentIndex + 1) + " / " + pad2(scenes.length);
                }
                if (secTitleEl) {
                    secTitleEl.textContent = scene.title || "";
                }
                updateSubtitles(scene.subtitles || scene.subtitle_text || scene.speech_text || "");
                updateProgressUI(0);
    
                if (btnPrev) btnPrev.disabled = (currentIndex <= 0);
                if (btnNext) btnNext.disabled = (currentIndex >= scenes.length - 1);
    
                applySceneChoreography(scene, 0);
                preloadRemainingScenes(currentIndex + 1);
    
                var primaryUrl = scene.audio_url || scene.audio_stream_url;
                if (primaryUrl) {
                    tryPlayAudioUrl(primaryUrl, scene, false);
                } else {
                    startFallbackPlayback(scene);
                }
            }
    
            function startFallbackPlayback(scene) {
                stopFallbackTimer();
                fallbackElapsed = 0;
                setPlayingUI(true);
    
                // Озвучиваем текст встроенным синтезатором браузера, если MP3 недоступен
                speakWithBrowserTTS(scene.speech_text || scene.subtitles, loadedLang || detectCurrentLang());
    
                fallbackTimer = setInterval(function () {
                    if (!isPlaying) return;
                    fallbackElapsed += 0.1;
                    var progress = Math.min(1, fallbackElapsed / FALLBACK_DURATION);
                    updateProgressUI(progress);
                    applySceneChoreography(scene, progress);
    
                    if (fallbackElapsed >= FALLBACK_DURATION) {
                        stopFallbackTimer();
                        handleSceneEnded();
                    }
                }, 100);
            }
    
            function handleSceneEnded() {
                if (!isTourActive) return;
                if (currentIndex + 1 < scenes.length) {
                    playScene(currentIndex + 1);
                } else {
                    stopAndCloseTour();
                }
            }
    
            // ── События HTML5 Audio ──
            audio.addEventListener("timeupdate", function () {
                if (!isTourActive || currentIndex < 0 || currentIndex >= scenes.length) return;
                var dur = (audio.duration && isFinite(audio.duration) && audio.duration > 0)
                    ? audio.duration
                    : FALLBACK_DURATION;
                var progress = Math.min(1, audio.currentTime / dur);
                updateProgressUI(progress);
                applySceneChoreography(scenes[currentIndex], progress);
            });
    
            audio.addEventListener("ended", function () {
                handleSceneEnded();
            });
    
            audio.addEventListener("error", function () {
                if (!isTourActive || currentIndex < 0) return;
                var scene = scenes[currentIndex];
                if (!triedStreamUrl && scene && scene.audio_stream_url) {
                    triedStreamUrl = true;
                    tryPlayAudioUrl(scene.audio_stream_url, scene, true);
                    return;
                }
                startFallbackPlayback(scene);
            });
    
            // ── Пауза / Возобновление / Закрытие ──
            function pausePresentation() {
                if (!isTourActive) return;
                if (!audio.paused) {
                    audio.pause();
                }
                if ("speechSynthesis" in window) {
                    try { window.speechSynthesis.pause(); } catch (e) {}
                }
                setPlayingUI(false);
            }
    
            function resumePresentation() {
                if (!isTourActive) return;
                var scene = scenes[currentIndex];
                if (!scene) return;
    
                if ((scene.audio_url || scene.audio_stream_url) && audio.src && !fallbackTimer) {
                    var p = audio.play();
                    if (p && typeof p.then === "function") {
                        p.then(function () {
                            setPlayingUI(true);
                        }).catch(function () {
                            startFallbackPlayback(scene);
                        });
                    } else {
                        setPlayingUI(true);
                    }
                } else {
                    if ("speechSynthesis" in window) {
                        try { window.speechSynthesis.resume(); } catch (e) {}
                    }
                    setPlayingUI(true);
                    if (!fallbackTimer) {
                        startFallbackPlayback(scene);
                    }
                }
            }
    
            function togglePlayPause() {
                if (!isTourActive) return;
                if (isPlaying) {
                    pausePresentation();
                } else {
                    resumePresentation();
                }
            }
    
            function stopAndCloseTour() {
                isTourActive = false;
                setPlayingUI(false);
                stopFallbackTimer();
                stopBrowserTTS();
    
                try {
                    audio.pause();
                    audio.removeAttribute("src");
                    audio.load();
                } catch (e) {}
    
                userScrolled = false;
                if (btnRefocus) btnRefocus.hidden = true;
    
                document.body.classList.remove("ai-tour-active");
                clearActiveSections();
                clearAllChoreographyClasses();
    
                dock.hidden = true;
                dock.setAttribute("aria-hidden", "true");
                fab.hidden = false;
                fab.classList.remove("ai-fab--loading");
                fab.setAttribute("aria-expanded", "false");
                currentIndex = -1;
            }
    
            // ── Запуск презентации по клику на .ai-fab ──
            function startTour() {
                if (isLoadingManifest || isTourActive) return;
    
                // КРИТИЧНО: разблокируем Audio синхронно в момент клика пользователя
                unlockAudioOnUserGesture();
    
                var currentLang = detectCurrentLang();
                if (scenes.length > 0 && loadedLang === currentLang) {
                    openDockAndPlay();
                    return;
                }
    
                isLoadingManifest = true;
                fab.classList.add("ai-fab--loading");
    
                var endpoint = (
                    window.location.pathname
                    + "?ai_presenter=1&lang="
                    + encodeURIComponent(currentLang)
                );
    
                fetch(endpoint, {
                    method: "GET",
                    headers: { "Accept": "application/json" },
                    credentials: "same-origin"
                })
                    .then(function (resp) {
                        if (!resp.ok) throw new Error("HTTP " + resp.status);
                        return resp.json();
                    })
                    .then(function (data) {
                        isLoadingManifest = false;
                        fab.classList.remove("ai-fab--loading");
    
                        if (!data || !data.ok || !Array.isArray(data.scenes) || data.scenes.length === 0) {
                            return;
                        }
                        scenes = data.scenes;
                        loadedLang = data.lang || currentLang;
                        openDockAndPlay();
                    })
                    .catch(function () {
                        isLoadingManifest = false;
                        fab.classList.remove("ai-fab--loading");
                    });
            }
    
            function openDockAndPlay() {
                isTourActive = true;
                userScrolled = false;
                if (btnRefocus) btnRefocus.hidden = true;
    
                fab.hidden = true;
                fab.setAttribute("aria-expanded", "true");
                dock.hidden = false;
                dock.setAttribute("aria-hidden", "false");
    
                playScene(0);
            }
    
            // ── UX Guardrails: перехват ручного скролла и сворачивания вкладки ──
            function onUserManualScroll(e) {
                if (!isTourActive) return;
                if (e && e.target && dock.contains(e.target)) return;
    
                if (!userScrolled) {
                    userScrolled = true;
                    if (btnRefocus) btnRefocus.hidden = false;
                }
            }
    
            window.addEventListener("wheel", onUserManualScroll, { passive: true });
            window.addEventListener("touchmove", onUserManualScroll, { passive: true });
    
            document.addEventListener("visibilitychange", function () {
                if (document.hidden && isTourActive && isPlaying) {
                    pausePresentation();
                }
            });
    
            // ── Обработчики кнопок управления ──
            fab.addEventListener("click", startTour);
    
            if (btnPlayPause) {
                btnPlayPause.addEventListener("click", togglePlayPause);
            }
    
            if (btnPrev) {
                btnPrev.addEventListener("click", function () {
                    if (!isTourActive || currentIndex <= 0) return;
                    playScene(currentIndex - 1);
                });
            }
    
            if (btnNext) {
                btnNext.addEventListener("click", function () {
                    if (!isTourActive) return;
                    if (currentIndex + 1 < scenes.length) {
                        playScene(currentIndex + 1);
                    } else {
                        stopAndCloseTour();
                    }
                });
            }
    
            if (btnRefocus) {
                btnRefocus.addEventListener("click", function () {
                    if (!isTourActive) return;
                    userScrolled = false;
                    btnRefocus.hidden = true;
                    var scene = scenes[currentIndex];
                    if (scene) {
                        var secEl = document.querySelector(scene.section || scene.section_selector);
                        if (secEl) scrollToSection(secEl);
                    }
                });
            }
    
            if (btnClose) {
                btnClose.addEventListener("click", stopAndCloseTour);
            }
  }
  })();       