// Элементы
const start_btn = document.querySelector(".start_btn button");
const info_box = document.getElementById("info_box");
const exit_btn = info_box.querySelector(".buttons .quit");
const start_quiz_btn = document.getElementById("start_quiz_btn");
const quiz_box = document.querySelector(".quiz_box");
const result_box = document.querySelector(".result_box");
const option_list = document.querySelector(".option_list");
const next_btn = document.querySelector("footer .next_btn");
const bottom_ques_counter = document.querySelector("footer .total_que");

const retake_btn = document.getElementById("retake_btn");
const final_quit_btn = document.getElementById("final_quit_btn");

// Элементы окна выбора категории (SelfCtg)
const ctg_box = document.getElementById("ctg_box");
const ctg_list = document.getElementById("ctg_list");
const ctg_back_btn = document.getElementById("ctg_back_btn");
let ctgLoading = false; // защита от повторного клика, пока летит fetch

// Данные пользователя
let firstName = "";
let lastName = "";
const fNameInput = document.getElementById("first_name");
const lNameInput = document.getElementById("last_name");

/* ── XSS-защита: имя/фамилия вставляются в innerHTML (subtitleTemplate).
   Пользовательский ввод обязан экранироваться ДО вставки в разметку,
   иначе введённый <img onerror=...> выполнится в браузере. ── */
function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

let que_count = 0;
let que_numb = 1;
let userScore = 0;

// Иконки для ответов
let tickIconTag = '<div class="icon tick"><i class="fas fa-check"></i></div>';
let crossIconTag = '<div class="icon cross"><i class="fas fa-times"></i></div>';

let currentCtgId = "";

// Состояние для крипто-эффектов
const CIPHER_GLYPHS = "0101ABCDEF#ΔΣ§⊕⊗0x7F9A";
let scrambleRafId = null;
let questionStates = [];

// Открытие правил
start_btn.onclick = () => {
    info_box.classList.add("activeInfo");
};

// Выход из правил
exit_btn.onclick = () => {
    info_box.classList.remove("activeInfo");
};

// Подтверждение ФИО -> открытие выбора категории (SelfCtg)
start_quiz_btn.onclick = () => {
    if (fNameInput.value.trim() === "" || lNameInput.value.trim() === "") {
        alert(fioReq);
        return;
    }
    firstName = fNameInput.value.trim();
    lastName = lNameInput.value.trim();

    info_box.classList.remove("activeInfo");
    if (ctg_box) {
        ctg_box.classList.add("activeCtg");
    }
};

// Кнопка "Назад" в окне выбора категории — возврат к вводу ФИО
if (ctg_back_btn) {
    ctg_back_btn.onclick = () => {
        ctg_box.classList.remove("activeCtg");
        info_box.classList.add("activeInfo");
    };
}

// Клик по категории -> подгружаем её вопросы и стартуем тест
if (ctg_list) {
    ctg_list.addEventListener("click", (e) => {
        const item = e.target.closest(".ctg-item");
        if (!item || ctgLoading) return;
        const ctgId = item.getAttribute("data-ctg-id");
        if (ctgId === null || ctgId === "") return;
        currentCtgId = ctgId;
        loadCategoryQuestions(ctgId);
    });
}

function loadCategoryQuestions(ctgId) {
    if (typeof CTG_QUESTIONS_URL_TEMPLATE === "undefined") return;

    ctgLoading = true;
    ctg_list.style.opacity = "0.5";
    ctg_list.style.pointerEvents = "none";

    const url = CTG_QUESTIONS_URL_TEMPLATE.replace("999999", encodeURIComponent(ctgId));

    fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } })
        .then((res) => {
            if (!res.ok) throw new Error("bad_status");
            return res.json();
        })
        .then((data) => {
            if (!data.ok || !Array.isArray(data.questions) || data.questions.length === 0) {
                alert("В этой категории пока нет вопросов");
                return;
            }

            questions = data.questions;

            ctg_box.classList.remove("activeCtg");
            quiz_box.classList.add("activeQuiz");

            que_count = 0;
            que_numb = 1;
            userScore = 0;

            buildCryptoChain(questions.length);
            showQuetions(que_count);
            queCounter(que_numb);
        })
        .catch(() => {
            alert("Не удалось загрузить вопросы. Проверьте соединение и попробуйте ещё раз.");
        })
        .finally(() => {
            ctgLoading = false;
            ctg_list.style.opacity = "";
            ctg_list.style.pointerEvents = "";
        });
}

// ── 1. Эффект «Живой дешифровки» (Cipher Text Scramble) за 350ms ──
function scrambleQuestionText(titleEl, originalHtml, duration = 350) {
    if (!titleEl) return;
    if (scrambleRafId) {
        cancelAnimationFrame(scrambleRafId);
        scrambleRafId = null;
    }

    titleEl.innerHTML = originalHtml;
    const finalText = titleEl.textContent || "";
    const len = finalText.length;
    if (!len) return;

    const startTime = performance.now();

    function step(now) {
        const elapsed = now - startTime;
        const progress = Math.min(1, elapsed / duration);
        const revealCount = Math.floor(progress * len);
        let scrambled = "";

        for (let i = 0; i < len; i++) {
            const ch = finalText[i];
            if (ch === " " || ch === "\n" || ch === "\t") {
                scrambled += ch;
            } else if (i < revealCount) {
                scrambled += ch;
            } else {
                scrambled += CIPHER_GLYPHS[Math.floor(Math.random() * CIPHER_GLYPHS.length)];
            }
        }

        titleEl.textContent = scrambled;

        if (progress < 1) {
            scrambleRafId = requestAnimationFrame(step);
        } else {
            titleEl.innerHTML = originalHtml;
            scrambleRafId = null;
        }
    }

    scrambleRafId = requestAnimationFrame(step);
}

// ── 2. Цепочка крипто-блоков (Blockchain Nodes Progress) ──
function buildCryptoChain(total) {
    const chainEl = document.getElementById("crypto_chain");
    if (!chainEl) return;
    chainEl.innerHTML = "";
    questionStates = new Array(total).fill("pending");

    for (let i = 0; i < total; i++) {
        const node = document.createElement("span");
        node.className = "crypto-node";
        node.setAttribute("data-idx", i + 1);
        node.title = "BLOCK #" + String(i + 1).padStart(2, "0");
        chainEl.appendChild(node);
    }
    updateCryptoChain(0);
}

function updateCryptoChain(activeIndex) {
    const chainEl = document.getElementById("crypto_chain");
    if (!chainEl) return;
    const nodes = chainEl.children;

    for (let i = 0; i < nodes.length; i++) {
        nodes[i].className = "crypto-node";
        if (i < activeIndex) {
            nodes[i].classList.add("is-passed");
            if (questionStates[i] === "correct") nodes[i].classList.add("is-verified");
            if (questionStates[i] === "incorrect") nodes[i].classList.add("is-breach");
        } else if (i === activeIndex) {
            nodes[i].classList.add("is-active");
            if (questionStates[i] === "correct") nodes[i].classList.add("is-verified");
            if (questionStates[i] === "incorrect") nodes[i].classList.add("is-breach");
        }
    }
}

// Кнопка "Следующий вопрос"
next_btn.onclick = () => {
    if (que_count < questions.length - 1) {
        que_count++;
        que_numb++;
        showQuetions(que_count);
        queCounter(que_numb);
        next_btn.classList.remove("show");
    } else {
        showResult();
    }
};

// Функция отображения вопросов и картинок
function showQuetions(index) {
    const que_text = document.querySelector(".que_text");

    let que_tag = '<span class="que_title"></span>';
    if (questions[index].img && questions[index].img !== "null" && questions[index].img !== "None") {
        que_tag += '<div class="que_image_box"><img src="' + questions[index].img + '" class="que_img" alt="Question"></div>';
    }
    que_text.innerHTML = que_tag;

    const titleEl = que_text.querySelector(".que_title");
    scrambleQuestionText(titleEl, questions[index].question, 350);

    updateCryptoChain(index);

    option_list.innerHTML = "";
    let option_tag = "";

    for (let i = 0; i < questions[index].options.length; i++) {
        let opt = questions[index].options[i];
        let hexBadge = '[0x' + String(i + 1).padStart(2, '0') + ']';
        let content =
            '<div class="opt_head">' +
                '<span class="opt_hex">' + hexBadge + '</span>' +
                '<span class="opt_text">' + opt.text + '</span>' +
            '</div>';
        if (opt.img && opt.img !== "null" && opt.img !== "None") {
            content += '<img src="' + opt.img + '" class="opt_img" alt="Option">';
        }
        option_tag += '<div class="option" onclick="optionSelected(this)">' + content + '</div>';
    }

    option_list.innerHTML = option_tag;

    const allOptions = option_list.children.length;
    for (let i = 0; i < allOptions; i++) {
        option_list.children[i].classList.remove("disabled");
    }
}

// Функция проверки выбранного ответа
function optionSelected(answer) {
    let userAns = answer.querySelector(".opt_text").textContent;
    let correcAns = questions[que_count].answer;

    const allOptions = option_list.children.length;
    answer.classList.add("select");

    if (userAns == correcAns) {
        userScore += 1;
        questionStates[que_count] = "correct";
        answer.classList.add("correct");
        answer.insertAdjacentHTML("beforeend", tickIconTag);
        answer.insertAdjacentHTML(
            "beforeend",
            '<span class="cyber-verdict cyber-verdict--ok">VERIFIED // ACCESS GRANTED</span>'
        );
    } else {
        questionStates[que_count] = "incorrect";
        answer.classList.add("incorrect");
        answer.insertAdjacentHTML("beforeend", crossIconTag);
        answer.insertAdjacentHTML(
            "beforeend",
            '<span class="cyber-verdict cyber-verdict--err">ANOMALY DETECTED</span>'
        );
    }

    updateCryptoChain(que_count);

    for (let i = 0; i < allOptions; i++) {
        option_list.children[i].classList.add("disabled");
    }
    next_btn.classList.add("show");
}

// Показ результатов в стиле крипто-отчёта с круговой диаграммой и цифровым штампом
function showResult() {
    info_box.classList.remove("activeInfo");
    quiz_box.classList.remove("activeQuiz");
    result_box.classList.add("activeResult");

    const statusText = document.getElementById("status_text");
    const subtitleText = document.getElementById("subtitle_text");
    const resultIcon = document.getElementById("result_icon");

    let percentage = (userScore / questions.length) * 100;
    let roundedPct = Math.round(percentage);

    let tierColor = "#10b981";
    let tierSecondary = "#22d3ee";
    let tierIconHtml = '<i class="fas fa-crown" style="color: #facc15;"></i>';
    let stampLabel = "CLEARANCE GRANTED // AES-VERIFIED";
    let stampClass = "cyber-stamp--high";

    if (percentage >= 75) {
        statusText.innerHTML = statusNice;
        tierColor = "#10b981";
        tierSecondary = "#facc15";
        tierIconHtml = '<i class="fas fa-crown" style="color: #facc15;"></i>';
        stampLabel = "CLEARANCE GRANTED // AES-VERIFIED";
        stampClass = "cyber-stamp--high";
        fireConfetti();
    } else if (percentage >= 50) {
        statusText.innerHTML = statusNorm;
        tierColor = "#3b82f6";
        tierSecondary = "#22d3ee";
        tierIconHtml = '<i class="fas fa-thumbs-up" style="color: #38bdf8;"></i>';
        stampLabel = "STANDARD CLEARANCE // LEVEL 02";
        stampClass = "cyber-stamp--mid";
    } else {
        statusText.innerHTML = statusBad;
        tierColor = "#ef4444";
        tierSecondary = "#f59e0b";
        tierIconHtml = '<i class="fas fa-book-open" style="color: #f87171;"></i>';
        stampLabel = "SECURITY ALERT // RETRAINING REQ";
        stampClass = "cyber-stamp--low";
    }

    const circumference = 2 * Math.PI * 58; // r = 58 -> ~364.42
    const dashOffset = circumference * (1 - Math.max(0, Math.min(100, percentage)) / 100);

    resultIcon.innerHTML = `
        <div class="cyber-report-visual">
            <div class="cyber-gauge-wrap">
                <svg class="cyber-gauge-svg" viewBox="0 0 140 140">
                    <defs>
                        <linearGradient id="selfResultGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" stop-color="${tierSecondary}" />
                            <stop offset="100%" stop-color="${tierColor}" />
                        </linearGradient>
                    </defs>
                    <circle class="cyber-gauge-ring-spin" cx="70" cy="70" r="65" fill="none" stroke="${tierColor}" stroke-opacity="0.28" stroke-width="1.2" stroke-dasharray="8 6 2 6" />
                    <circle cx="70" cy="70" r="58" fill="none" stroke="rgba(148, 163, 184, 0.16)" stroke-width="6" />
                    <circle class="cyber-gauge-arc" id="selfGaugeArc"
                            cx="70" cy="70" r="58"
                            fill="none"
                            stroke="url(#selfResultGrad)"
                            stroke-width="6"
                            stroke-linecap="round"
                            stroke-dasharray="${circumference.toFixed(2)}"
                            stroke-dashoffset="${circumference.toFixed(2)}"
                            transform="rotate(-90 70 70)" />
                </svg>
                <div class="cyber-gauge-center">
                    <div class="cyber-gauge-ico">${tierIconHtml}</div>
                    <div class="cyber-gauge-pct">${roundedPct}%</div>
                </div>
            </div>
            <div class="cyber-stamp ${stampClass}">${stampLabel}</div>
        </div>
    `;

    requestAnimationFrame(() => {
        setTimeout(() => {
            const arcEl = document.getElementById("selfGaugeArc");
            if (arcEl) arcEl.style.strokeDashoffset = dashOffset.toFixed(2);
        }, 60);
    });

    let finalSubtitle = subtitleTemplate
        .replace('{last_name}', escapeHtml(lastName))
        .replace('{first_name}', escapeHtml(firstName))
        .replace('{score}', userScore)
        .replace('{total}', questions.length);

    subtitleText.innerHTML = `<span>${finalSubtitle}</span>`;

    sendResultToBackend();
}

// Счетчик в футере
function queCounter(index) {
    let totalQueCounTag = '<span class="hud-counter-tag"><p>' + index + '</p>' + quesOf + '<p>' + questions.length + '</p></span>';
    bottom_ques_counter.innerHTML = totalQueCounTag;
}

// Кнопка рестарта
retake_btn.onclick = () => {
    window.location.reload();
};

// Кнопка финального выхода
final_quit_btn.onclick = () => {
    window.location.href = homelink;
};

function fireConfetti() {
    let duration = 3 * 1000;
    let animationEnd = Date.now() + duration;
    let defaults = { startVelocity: 30, spread: 360, ticks: 60, zIndex: 10 };

    function randomInRange(min, max) { return Math.random() * (max - min) + min; }

    let interval = setInterval(function () {
        let timeLeft = animationEnd - Date.now();
        if (timeLeft <= 0) return clearInterval(interval);

        let particleCount = 50 * (timeLeft / duration);
        confetti(Object.assign({}, defaults, { particleCount, origin: { x: randomInRange(0.1, 0.3), y: Math.random() - 0.2 } }));
        confetti(Object.assign({}, defaults, { particleCount, origin: { x: randomInRange(0.7, 0.9), y: Math.random() - 0.2 } }));
    }, 250);
}

function sendResultToBackend() {
    const form = document.getElementById("results-id");
    const csrfToken = form.querySelector('[name=csrfmiddlewaretoken]').value;

    let formData = new FormData();
    formData.append('first_name', firstName);
    formData.append('last_name', lastName);
    formData.append('ctg', currentCtgId);
    formData.append('score', userScore);
    formData.append('total', questions.length);
    formData.append('percentage', (userScore / questions.length) * 100);

    fetch(window.location.href, {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrfToken,
            'X-Requested-With': 'XMLHttpRequest'
        },
        body: formData
    })
        .then(response => console.log("Результат отправлен на бэкенд"))
        .catch(error => console.error("Ошибка:", error));
}