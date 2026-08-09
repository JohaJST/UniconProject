// Элементы
const start_btn = document.querySelector(".start_btn button");
const info_box = document.querySelector(".info_box");
const exit_btn = info_box.querySelector(".buttons .quit");
const start_quiz_btn = document.getElementById("start_quiz_btn"); // Кнопка "Далее"
const quiz_box = document.querySelector(".quiz_box");
const result_box = document.querySelector(".result_box");
const option_list = document.querySelector(".option_list");
const next_btn = document.querySelector("footer .next_btn");
const bottom_ques_counter = document.querySelector("footer .total_que");

const retake_btn = document.getElementById("retake_btn");
const final_quit_btn = document.getElementById("final_quit_btn");

// Переменные для пользователя
let firstName = "";
let lastName = "";
const fNameInput = document.getElementById("first_name");
const lNameInput = document.getElementById("last_name");

let que_count = 0;
let que_numb = 1;
let userScore = 0;

start_btn.onclick = ()=>{
    info_box.classList.add("activeInfo");
}

exit_btn.onclick = ()=>{
    info_box.classList.remove("activeInfo");
}

// Проверка имени и старт теста
start_quiz_btn.onclick = ()=>{
    if(fNameInput.value.trim() === "" || lNameInput.value.trim() === ""){
        alert(fioReq);
        return;
    }
    firstName = fNameInput.value.trim();
    lastName = lNameInput.value.trim();

    info_box.classList.remove("activeInfo");
    quiz_box.classList.add("activeQuiz");
    showQuetions(0);
    queCounter(1);
}

// Кнопка Следующий вопрос
next_btn.onclick = ()=>{
    if(que_count < questions.length - 1){
        que_count++;
        que_numb++;
        showQuetions(que_count);
        queCounter(que_numb);
        next_btn.classList.remove("show");
    }else{
        showResult();
    }
}

let tickIconTag = '<div class="icon tick"><i class="fas fa-check"></i></div>';
let crossIconTag = '<div class="icon cross"><i class="fas fa-times"></i></div>';

function optionSelected(answer){
    let userAns = answer.textContent;
    let correcAns = questions[que_count].answer;
    const allOptions = option_list.children.length;
    answer.classList.add("select");
    
    if(userAns == correcAns){
        userScore += 1;
        answer.classList.add("correct");
        answer.insertAdjacentHTML("beforeend", tickIconTag);
    }else{
        answer.classList.add("incorrect");
        answer.insertAdjacentHTML("beforeend", crossIconTag);
    }
    
    for(let i=0; i < allOptions; i++){
        option_list.children[i].classList.add("disabled");
    }
    next_btn.classList.add("show");
}

function showResult(){
    info_box.classList.remove("activeInfo");
    quiz_box.classList.remove("activeQuiz");
    result_box.classList.add("activeResult");
    
    const statusText = document.getElementById("status_text");
    const subtitleText = document.getElementById("subtitle_text");
    const resultIcon = document.getElementById("result_icon");

    // Высчитываем процент
    let percentage = (userScore / questions.length) * 100;
    
    if (percentage >= 80) {
        statusText.innerHTML = statusNice;
        resultIcon.innerHTML = '<i class="fas fa-crown" style="color: gold;"></i>';
        fireConfetti(); // Запуск салюта
    } else if (percentage >= 50) {
        statusText.innerHTML = statusNorm;
        resultIcon.innerHTML = '<i class="fas fa-thumbs-up" style="color: #007bff;"></i>';
    } else {
        statusText.innerHTML = statusBad;
        resultIcon.innerHTML = '<i class="fas fa-dumbbell" style="color: #dc3545;"></i>';
    }

    // Подставляем данные в Subtitle
    subtitleText.innerHTML = `<span>Уважаемый(ая) <b>${lastName} ${firstName}</b>, вы набрали <p>${userScore}</p> из <p>${questions.length}</p></span>`;

    // Отправляем на бэкенд
    sendResultToBackend();
}

function queCounter(index){
    let totalQueCounTag = '<span><p>'+ index +'</p> вопрос из <p>'+ questions.length + '</p></span>';
    bottom_ques_counter.innerHTML = totalQueCounTag;
}

// Кнопка рестарта
retake_btn.onclick = ()=>{
    quiz_box.classList.add("activeQuiz");
    result_box.classList.remove("activeResult");
    que_count = 0;
    que_numb = 1;
    userScore = 0;
    showQuetions(que_count);
    queCounter(que_numb);
    next_btn.classList.remove("show");
}

// Выход из результатов
final_quit_btn.onclick = ()=>{
    window.location.href = homelink; // укажите ваш URL для главной страницы
}

// --- ФУНКЦИИ КРЕАТИВА И ОТПРАВКИ ---

// Функция эффекта салюта
function fireConfetti() {
    let duration = 3 * 1000;
    let animationEnd = Date.now() + duration;
    let defaults = { startVelocity: 30, spread: 360, ticks: 60, zIndex: 10 };

    function randomInRange(min, max) { return Math.random() * (max - min) + min; }

    let interval = setInterval(function() {
        let timeLeft = animationEnd - Date.now();
        if (timeLeft <= 0) return clearInterval(interval);
        
        let particleCount = 50 * (timeLeft / duration);
        confetti(Object.assign({}, defaults, { particleCount, origin: { x: randomInRange(0.1, 0.3), y: Math.random() - 0.2 } }));
        confetti(Object.assign({}, defaults, { particleCount, origin: { x: randomInRange(0.7, 0.9), y: Math.random() - 0.2 } }));
    }, 250);
}

// Функция отправки на бэкенд без перезагрузки (AJAX)
function sendResultToBackend() {
    const form = document.getElementById("results-id");
    const csrfToken = form.querySelector('[name=csrfmiddlewaretoken]').value;
    
    let formData = new FormData();
    formData.append('first_name', firstName);
    formData.append('last_name', lastName);
    formData.append('score', userScore);
    formData.append('total', questions.length);
    formData.append('percentage', (userScore / questions.length) * 100);

    // Отправляем POST запрос на текущий URL (или укажите ваш API endpoint)
    fetch(window.location.href, {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrfToken,
            'X-Requested-With': 'XMLHttpRequest' // Помечаем как AJAX запрос для Django
        },
        body: formData
    })
    .then(response => {
        console.log("Результат успешно отправлен!");
    })
    .catch(error => {
        console.error("Ошибка отправки на сервер: ", error);
    });
}