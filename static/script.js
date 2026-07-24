// creating an array and passing the number, questions, options, and answers

//selecting all required elements
const start_btn = document.querySelector(".start_btn button");
const info_box = document.querySelector(".info_box");
const exit_btn = info_box.querySelector(".buttons .quit");
const restart_quiz = info_box.querySelector(".buttons .restart");
const quiz_box = document.querySelector(".quiz_box");
const result_box = document.querySelector(".result_box");
const option_list = document.querySelector(".option_list");
const time_line = document.querySelector("header .time_line");
const timeText = document.querySelector(".timer .time_left_txt");
const timeCount = document.querySelector(".timer .timer_sec");
const result = document.querySelector(".result_for_backend");

// if startQuiz button clicked
start_btn.onclick = ()=>{
    info_box.classList.add("activeInfo"); //show info box
}

// if exitQuiz button clicked
exit_btn.onclick = ()=>{
    info_box.classList.remove("activeInfo"); //hide info box
}

// if continueQuiz button clicked
restart_quiz.onclick = ()=>{
    info_box.classList.remove("activeInfo"); //hide info box
    quiz_box.classList.add("activeQuiz"); //show quiz box
    showQuetions(0); //calling showQestions function
    queCounter(1); //passing 1 parameter to queCounter
}

let timeValue =  15;
let que_count = 0;
let que_numb = 1;
let userScore = 0;
let counter;
let counterLine;
let widthValue = 0;

// const restart_quiz = result_box.querySelector(".buttons .restart");
const quit_quiz = result_box.querySelector(".buttons .quit");

// if restartQuiz button clicked
restart_quiz.onclick = ()=>{
    quiz_box.classList.add("activeQuiz"); //show quiz box
    result_box.classList.remove("activeResult"); //hide result box
    timeValue = 15; 
    que_count = 0;
    que_numb = 1;
    userScore = 0;
    widthValue = 0;
    showQuetions(que_count); //calling showQestions function
    queCounter(que_numb); //passing que_numb value to queCounter
    clearInterval(counter); //clear counter
    clearInterval(counterLine); //clear counterLine
    startTimer(timeValue); //calling startTimer function
    startTimerLine(widthValue); //calling startTimerLine function
    timeText.textContent = "Time Left"; //change the text of timeText to Time Left
    next_btn.classList.remove("show"); //hide the next button
}

// if quitQuiz button clicked
// quit_quiz.onclick = ()=>{
//     window.location.reload(); //reload the current window
// }

const next_btn = document.querySelector("footer .next_btn");
const bottom_ques_counter = document.querySelector("footer .total_que");

// if Next Que button clicked
next_btn.onclick = ()=>{
    // console.log("Btn Click")
    if(que_count < questions.length - 1){ //if question count is less than total question length
        // console.log("True")
        que_count++; //increment the que_count value
        que_numb++; //increment the que_numb value
        showQuetions(que_count); //calling showQestions function
        queCounter(que_numb); //passing que_numb value to queCounter
        clearInterval(counter); //clear counter
        clearInterval(counterLine); //clear counterLine
        // startTimer(timeValue); //calling startTimer function
        // startTimerLine(widthValue); //calling startTimerLine function
        // timeText.textContent = "Time Left"; //change the timeText to Time Left
        next_btn.classList.remove("show"); //hide the next button
        const allOptions = option_list.children.length;
        for(i=0; i < allOptions; i++){
            option_list.children[i].classList.remove("select"); //once user select an option then disabled all options
        }
    }else{
        // console.log("False (else)")
        clearInterval(counter); //clear counter
        clearInterval(counterLine); //clear counterLine
        showResult(); //calling showResult function
    }
}

// getting questions and options from array

// creating the new div tags which for icons
let tickIconTag = '<div class="icon tick"><i class="fas fa-check"></i></div>';
let crossIconTag = '<div class="icon cross"><i class="fas fa-times"></i></div>';

//if user clicked on option
function optionSelected(answer){
    // clearInterval(counter); //clear counter
    // clearInterval(counterLine); //clear counterLine
    let userAns = answer.textContent; //getting user selected option
    let correcAns = questions[que_count].answer; //getting correct answer from array
    const allOptions = option_list.children.length; //getting all option items
    answer.classList.add("select");
    // answer.classList.add("correct");
    if(userAns == correcAns){ //if user selected option is equal to array's correct answer
        userScore += 1; //upgrading score value with 1
        // answer.classList.add("correct"); //adding green color to correct selected option
        // answer.insertAdjacentHTML("beforeend", tickIconTag); //adding tick icon to correct selected option
        console.log("Correct Answer");
        console.log("Your correct answers = " + userScore);
    }else{
        // answer.classList.add("incorrect"); //adding red color to correct selected option
        // answer.insertAdjacentHTML("beforeend", crossIconTag); //adding cross icon to correct selected option
        console.log("Wrong Answer");

        // for(i=0; i < allOptions; i++){
        //     if(option_list.children[i].textContent == correcAns){ //if there is an option which is matched to an array answer
        //         option_list.children[i].setAttribute("class", "option correct"); //adding green color to matched option
        //         option_list.children[i].insertAdjacentHTML("beforeend", tickIconTag); //adding tick icon to matched option
        //         console.log("Auto selected correct answer.");
        //     }
        // }
    }
    for(i=0; i < allOptions; i++){
        option_list.children[i].classList.add("disabled"); //once user select an option then disabled all options
    }
    next_btn.classList.add("show"); //show the next button if user selected any option
}

function showResult(){
    info_box.classList.remove("activeInfo"); //hide info box
    quiz_box.classList.remove("activeQuiz"); //hide quiz box
    result_box.classList.add("activeResult"); //show result box
    const scoreText = result_box.querySelector(".score_text");
    let resultText = '<input name="result" type="hidden" value="' + userScore + '">'
    result.innerHTML = resultText
    // var form = document.getElementById("results-id");
    // form.submit();
     // if user scored more than 3
        //creating a new span tag and passing the user score number and total question number
    let foyiz = userScore * 100 / questions.length
    console.log(foyiz);
    if (foyiz > 80) {
        let scoreTag = '<center><h3>Здорово</h3><span>Вы набрали <p>'+ userScore +'</p> из <p>'+ questions.length +'</p></span></center>';
            scoreText.innerHTML = scoreTag;  //adding new span tag inside score_Text
    }
    else if (80 > foyiz && foyiz >= 50) {
        let scoreTag = '<center><h3>Нормально</h3><span>Вы набрали <p>'+ userScore +'</p> из <p>'+ questions.length +'</p></span></center>';
            scoreText.innerHTML = scoreTag;  //adding new span tag inside score_Text
    }
    else{
        let scoreTag = '<center><h3>Нужно по тренироваться</h3><span>Вы набрали <p>'+ userScore +'</p> из <p>'+ questions.length +'</p></span></center>';
        scoreText.innerHTML = scoreTag;  //adding new span tag inside score_Text
    }
}

function queCounter(index){
    //creating a new span tag and passing the question number and total question
    let totalQueCounTag = '<span><p>'+ index +'</p> вопрос из <p>'+ questions.length;
    bottom_ques_counter.innerHTML = totalQueCounTag;  //adding new span tag inside bottom_ques_counter
}