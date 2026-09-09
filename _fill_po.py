# -*- coding: utf-8 -*-
"""
Заполняет django.po (ru/uz/en) переводами из таблицы TRANSLATIONS:
  - пустые msgstr заполняются;
  - fuzzy-записи (msgmerge-подсказки) перезаписываются и теряют флаг fuzzy;
  - существующие корректные переводы НЕ трогаются.
"""
import re

# ─── Таблица переводов: msgid -> {"ru": ..., "uz": ..., "en": ...} ──────────
TRANSLATIONS = {
    # ── about.html (hero/goals/footer) ─────────────────────────────────────
    "homePageTitle": {"ru": "Главная страница", "uz": "Bosh sahifa", "en": "Home page"},
    "heroChipOrgName": {
        "ru": "«UNICON.UZ — Центр научно-технических и маркетинговых исследований» ООО",
        "uz": "\"UNICON.UZ - Fan-texnika va marketing tadqiqotlari markazi\" MChJ",
        "en": "\"UNICON.UZ - Science, Technology and Marketing Research Center\" LLC",
    },
    "heroHeadingMain": {"ru": "Криптология", "uz": "Kriptologiya", "en": "Cryptology"},
    "heroHeadingGlow": {"ru": "школа", "uz": "maktabi", "en": "School"},
    "heroDescText": {
        "ru": "Современный научно-образовательный центр, готовящий криптографов будущего. В сфере информационной безопасности начинается новая эра.",
        "uz": "Kelajak kriptograflarini tayyorlovchi zamonaviy ilmiy-ta'lim markazi. Axborot xavfsizligi sohasida yangi davr boshlanmoqda.",
        "en": "A modern scientific and educational center training the cryptographers of the future. A new era begins in the field of information security.",
    },
    "heroBtnViewCourses": {"ru": "Смотреть курсы", "uz": "Kurslarni ko'rish", "en": "View courses"},
    "heroBtnMoreInfo": {"ru": "Подробнее", "uz": "Batafsil", "en": "Details"},
    "heroScrollHint": {"ru": "Листайте вниз", "uz": "Pastga suring", "en": "Scroll down"},
    "goalMainTitle": {"ru": "Основная цель", "uz": "Asosiy maqsad", "en": "Main goal"},
    "goalMainText": {
        "ru": "Разработка и совершенствование национальных средств криптографической защиты информации, развитие научно-исследовательских и практических работ в области криптологии с целью",
        "uz": "Axborotni kriptografik himoyalash, milliy vositalarini ishlab chiqish va ularni takomillashtirish, kriptologiya sohasida olib borilayotgan ilmiy-tadqiqot va amaliy ishlarni rivojlantirish maqsadida",
        "en": "To develop and improve national cryptographic information protection tools and to advance research and practical work in the field of cryptology in order to",
    },
    "goalMainHighlight": {
        "ru": "подготовки криптографов нового поколения",
        "uz": "yangi avlod kriptograflarini tayyorlash",
        "en": "train a new generation of cryptographers",
    },
    "tasksTitle": {"ru": "Основные задачи", "uz": "Asosiy vazifalar", "en": "Main tasks"},
    "task1Title": {"ru": "Научно-исследовательская работа", "uz": "Ilmiy-tadqiqot ishlari", "en": "Research work"},
    "task1Text": {
        "ru": "Развитие новых направлений криптологии и проведение научно-исследовательских работ.",
        "uz": "Kriptologiyaning yangi yo'nalishlarini rivojlantirish va ilmiy-tadqiqot ishlari olib borish.",
        "en": "Developing new areas of cryptology and conducting research.",
    },
    "task2Title": {"ru": "Образовательная деятельность", "uz": "Ta'lim faoliyati", "en": "Educational activities"},
    "task2Text": {
        "ru": "Лекции по криптологии, курсы повышения квалификации, научные семинары и тренинги.",
        "uz": "Kriptologiya bo'yicha o'qishlar, malaka oshirish kurslari, ilmiy seminar va treninglar.",
        "en": "Cryptology lectures, professional development courses, scientific seminars and trainings.",
    },
    "task3Title": {"ru": "Повышение грамотности", "uz": "Savodxonlikni oshirish", "en": "Improving literacy"},
    "task3Text": {
        "ru": "Организация учебных курсов по криптологической грамотности.",
        "uz": "Kriptologiya savodxonligi bo'yicha o'quv kurslarini tashkil etish.",
        "en": "Organizing training courses on cryptology literacy.",
    },
    "footerBrandName": {"ru": "Школа криптологии", "uz": "Kriptologiya maktabi", "en": "School of Cryptology"},
    "footerBrandDesc": {
        "ru": "Современный образовательный центр в сфере информационной безопасности. Вместе мы построим безопасное будущее.",
        "uz": "Axborot xavfsizligi sohasida zamonaviy ta'lim markazi. Biz bilan kelajak xavfsizligini birga quramiz.",
        "en": "A modern educational center in information security. Together we will build a secure future.",
    },
    "footerContactHeading": {"ru": "Свяжитесь с нами", "uz": "Biz bilan bog'laning", "en": "Contact us"},
    "footerAddress": {"ru": "г. Ташкент, ул. Амира Темура, 108", "uz": "Toshkent sh., Amir Temur ko'chasi, 108", "en": "Tashkent, Amir Temur Street, 108"},
    "footerWorkingHours": {"ru": "Пн-Пт: 9:00 — 18:00", "uz": "Dush-Juma: 9:00 — 18:00", "en": "Mon-Fri: 9:00 — 18:00"},
    "footerSocialHeading": {"ru": "Социальные сети", "uz": "Ijtimoiy tarmoqlar", "en": "Social media"},
    "footerCopyrightText": {"ru": "Все права защищены.", "uz": "Barcha huquqlar himoyalangan.", "en": "All rights reserved."},
    "footerDesignedByText": {"ru": "Разработано", "uz": "Designed by", "en": "Designed by"},

    # ── about.html: legacy-msgid секций (источник — uz) ────────────────────
    "Missiya": {"ru": "Миссия", "uz": "Missiya", "en": "Mission"},
    "Maqsad va vazifalar": {"ru": "Цели и задачи", "uz": "Maqsad va vazifalar", "en": "Goals and objectives"},
    "Kriptologiya sohasida milliy xavfsizlikni ta'minlashga qaratilgan strategik yo'nalishlar": {
        "ru": "Стратегические направления обеспечения национальной безопасности в сфере криптологии",
        "uz": "Kriptologiya sohasida milliy xavfsizlikni ta'minlashga qaratilgan strategik yo'nalishlar",
        "en": "Strategic directions for ensuring national security in the field of cryptology",
    },
    "Kriptografik himoya": {"ru": "Криптографическая защита", "uz": "Kriptografik himoya", "en": "Cryptographic protection"},
    "Ilmiy-tadqiqot": {"ru": "Научные исследования", "uz": "Ilmiy-tadqiqot", "en": "Research"},
    "O'quv dasturlari": {"ru": "Учебные программы", "uz": "O'quv dasturlari", "en": "Study programs"},
    "Kurslar": {"ru": "Курсы", "uz": "Kurslar", "en": "Courses"},
    "Zamonaviy kriptografiya va axborot xavfsizligi bo'yicha yo'nalishlar": {
        "ru": "Направления современной криптографии и информационной безопасности",
        "uz": "Zamonaviy kriptografiya va axborot xavfsizligi bo'yicha yo'nalishlar",
        "en": "Areas of modern cryptography and information security",
    },
    "Kurs": {"ru": "Курс", "uz": "Kurs", "en": "Course"},
    "Kurslar hali qo'shilmagan": {"ru": "Курсы пока не добавлены", "uz": "Kurslar hali qo'shilmagan", "en": "No courses added yet"},
    "Jamoa": {"ru": "Команда", "uz": "Jamoa", "en": "Team"},
    "O'qituvchilar": {"ru": "Преподаватели", "uz": "O'qituvchilar", "en": "Teachers"},
    "Sohaning yetakchi mutaxassislari va tajribali pedagoglar jamoasi": {
        "ru": "Команда ведущих специалистов отрасли и опытных педагогов",
        "uz": "Sohaning yetakchi mutaxassislari va tajribali pedagoglar jamoasi",
        "en": "A team of leading industry experts and experienced educators",
    },
    "Oldingi": {"ru": "Назад", "uz": "Oldingi", "en": "Previous"},
    "O'qituvchilar hali qo'shilmagan": {"ru": "Преподаватели пока не добавлены", "uz": "O'qituvchilar hali qo'shilmagan", "en": "No teachers added yet"},
    "Keyingi": {"ru": "Далее", "uz": "Keyingi", "en": "Next"},
    "Yangiliklar": {"ru": "Новости", "uz": "Yangiliklar", "en": "News"},
    "So'nggi yangiliklar": {"ru": "Последние новости", "uz": "So'nggi yangiliklar", "en": "Latest news"},
    "Kriptologiya maktabi hayotidagi eng muhim voqealar": {
        "ru": "Важнейшие события из жизни Школы криптологии",
        "uz": "Kriptologiya maktabi hayotidagi eng muhim voqealar",
        "en": "The most important events in the life of the School of Cryptology",
    },
    "Yangiliklar hali qo'shilmagan": {"ru": "Новости пока не добавлены", "uz": "Yangiliklar hali qo'shilmagan", "en": "No news added yet"},
    "Hamkorlik": {"ru": "Сотрудничество", "uz": "Hamkorlik", "en": "Partnership"},
    "Hamkorlar": {"ru": "Партнёры", "uz": "Hamkorlar", "en": "Partners"},
    "Biz bilan hamkorlik qilayotgan yetakchi tashkilot va kompaniyalar": {
        "ru": "Ведущие организации и компании, сотрудничающие с нами",
        "uz": "Biz bilan hamkorlik qilayotgan yetakchi tashkilot va kompaniyalar",
        "en": "Leading organizations and companies partnering with us",
    },

    # ── module 3 test ──────────────────────────────────────────────────────
    "ctgSelectTitle": {"ru": "Выберите категорию", "uz": "Kategoriyani tanlang", "en": "Select a category"},
    "questionsCountSuffix": {"ru": "вопросов", "uz": "savol", "en": "questions"},
    "noCategoriesYet": {"ru": "Категории пока не добавлены", "uz": "Kategoriyalar hali qo'shilmagan", "en": "No categories added yet"},
    "ctgBack": {"ru": "Назад", "uz": "Orqaga", "en": "Back"},
    "resultText": {
        "ru": "Уважаемый(ая) <b>{last_name} {first_name}</b>, вы набрали <b>{score}</b> из <b>{total}</b>",
        "uz": "Hurmatli <b>{last_name} {first_name}</b>, siz <b>{total}</b> savoldan <b>{score}</b> tasiga to'g'ri javob berdingiz",
        "en": "Dear <b>{last_name} {first_name}</b>, you scored <b>{score}</b> out of <b>{total}</b>",
    },

    # ── login ──────────────────────────────────────────────────────────────
    "loginPageTitle": {"ru": "Check Your Brain — Вход", "uz": "Check Your Brain — Kirish", "en": "Check Your Brain — Sign in"},
    "logoAlt": {"ru": "Логотип", "uz": "Logotip", "en": "Logo"},
    "Поток": {"ru": "Поток", "uz": "Oqim", "en": "Group"},
    "Выберите поток": {"ru": "Выберите поток", "uz": "Oqimni tanlang", "en": "Select a group"},
    "Сначала выберите поток": {"ru": "Сначала выберите поток", "uz": "Avval oqimni tanlang", "en": "First select a group"},

    # ── reqPB ──────────────────────────────────────────────────────────────
    "reqPBPageTitle": {"ru": "Укажите должность и компанию", "uz": "Lavozim va kompaniyani kiriting", "en": "Request Position and Company"},
    "logoAltReq": {"ru": "Логотип", "uz": "Logotip", "en": "Logo"},
    "reqPBHeading": {"ru": "Обязательно", "uz": "Majburiy", "en": "Required"},
    "reqPBHintText": {
        "ru": "Укажите реальные актуальные данные. Это необходимо для получения результатов теста",
        "uz": "Haqiqiy va dolzarb ma'lumotlarni kiriting. Bu test natijalarini olish uchun zarur",
        "en": "Enter your actual details. This is required to receive your test results",
    },
    "positionLabel": {"ru": "Должность", "uz": "Lavozim", "en": "Position"},
    "positionPlaceholder": {"ru": "Ваша должность", "uz": "Sizning lavozimingiz", "en": "Your position"},
    "companyLabel": {"ru": "Компания", "uz": "Kompaniya", "en": "Company"},
    "companyPlaceholder": {"ru": "Название компании", "uz": "Kompaniya nomi", "en": "Company name"},
    "goHomeBtn": {"ru": "На главную", "uz": "Bosh sahifaga", "en": "Go Home"},

    # ── index.html ─────────────────────────────────────────────────────────
    "testsPageTitle": {"ru": "Тесты", "uz": "Testlar", "en": "Tests"},
    "availableTestsHeading": {"ru": "Доступные тесты", "uz": "Mavjud testlar", "en": "Available tests"},
    "chooseTestPrompt": {"ru": ", выберите тест для прохождения", "uz": ", o'tish uchun testni tanlang", "en": ", choose a test to take"},
    "completedBadge": {"ru": "✓ Пройден", "uz": "✓ O'tilgan", "en": "✓ Completed"},
    "newBadge": {"ru": "Новый", "uz": "Yangi", "en": "New"},
    "questionsAbbrev": {"ru": "вопр.", "uz": "savol", "en": "q."},
    "viewResultsBtn": {"ru": "Посмотреть результаты", "uz": "Natijalarni ko'rish", "en": "View results"},
    "startTestBtn": {"ru": "Начать тест →", "uz": "Testni boshlash →", "en": "Start test →"},
    "noTestsAvailable": {"ru": "Нет доступных тестов", "uz": "Mavjud testlar yo'q", "en": "No available tests"},
    "contactTeacherPrompt": {"ru": "Обратитесь к преподавателю", "uz": "O'qituvchingizga murojaat qiling", "en": "Contact your teacher"},
    "inProgressBadge": {"ru": "↻ В процессе", "uz": "↻ Jarayonda", "en": "↻ In progress"},
    "continueTestBtn": {"ru": "Продолжить →", "uz": "Davom ettirish →", "en": "Continue →"},

    # ── new_test_page.html ─────────────────────────────────────────────────
    "exitConfirmMessage": {"ru": "Выйти? Прогресс будет потерян.", "uz": "Chiqasizmi? Jarayon yo'qoladi.", "en": "Exit? Your progress will be lost."},
    "questionImageAlt": {"ru": "Изображение вопроса", "uz": "Savol rasmi", "en": "Question image"},
    "noQuestionsInTest": {"ru": "В этом тесте пока нет вопросов.", "uz": "Bu testda hozircha savollar yo'q.", "en": "This test has no questions yet."},
    "finishTestBtn": {"ru": "ЗАВЕРШИТЬ ТЕСТ", "uz": "TESTNI YAKUNLASH", "en": "FINISH TEST"},
    "submittingResultsText": {"ru": "Отправка результатов...", "uz": "Natijalar yuborilmoqda...", "en": "Submitting results..."},
    "confirmSubmitAnswers": {"ru": "Отправить ответы?", "uz": "Javoblar yuborilsinmi?", "en": "Submit answers?"},
    "submitErrorFallback": {"ru": "Ошибка отправки", "uz": "Yuborishda xatolik", "en": "Submission error"},
    "connectionErrorPrefix": {"ru": "Ошибка соединения: ", "uz": "Ulanish xatosi: ", "en": "Connection error: "},

    # ── profile.html ───────────────────────────────────────────────────────
    "profilePageTitle": {"ru": "Профиль", "uz": "Profil", "en": "Profile"},
    "potokLabel": {"ru": "Поток: ", "uz": "Oqim: ", "en": "Group: "},
    "positionLabelColon": {"ru": "Должность: ", "uz": "Lavozim: ", "en": "Position: "},
    "companyLabelColon": {"ru": "Компания: ", "uz": "Kompaniya: ", "en": "Company: "},
    "langLabel": {"ru": "Язык: ", "uz": "Til: ", "en": "Language: "},
    "testsCompletedLabel": {"ru": "Тестов пройдено", "uz": "O'tilgan testlar", "en": "Tests completed"},
    "avgPercentLabel": {"ru": "Средний процент", "uz": "O'rtacha foiz", "en": "Average percentage"},
    "testHistoryHeading": {"ru": "История тестов", "uz": "Testlar tarixi", "en": "Test history"},
    "noTestsCompletedYet": {"ru": "Вы ещё не прошли ни одного теста", "uz": "Siz hali birorta ham test o'tmagansiz", "en": "You haven't taken any tests yet"},

    # ── test_result.html ───────────────────────────────────────────────────
    "resultsPageTitleSuffix": {"ru": "— Результаты", "uz": "— Natijalar", "en": "— Results"},
    "resultHeadingPrefix": {"ru": "Курс «", "uz": "Kriptologiya maktabining", "en": "The Cryptology School "},
    "resultHeadingSuffix": {"ru": "» школы криптологии", "uz": "kursi", "en": " course"},
    "percentLabel": {"ru": "Процент", "uz": "Foiz", "en": "Percentage"},
    "correctLabel": {"ru": "Верных", "uz": "To'g'ri", "en": "Correct"},
    "totalLabel": {"ru": "Всего", "uz": "Jami", "en": "Total"},
    "backToHomeBtn": {"ru": "На главную", "uz": "Bosh sahifaga", "en": "Home"},
}


def po_escape(text: str) -> str:
    """Экранирование строки для msgstr (одна строка)."""
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def clean_msgid(raw: str) -> str:
    """Склеивает многострочный msgid в одну строку без кавычек."""
    return "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', raw, re.S))


def fill_po(path: str, lang: str):
    with open(path, encoding="utf-8") as f:
        content = f.read()

    blocks = re.split(r"\n\n", content)
    out_blocks = []
    changed = 0
    for block in blocks:
        mid = re.search(r"^msgid (.*?)(?=\nmsgstr)", block, re.S | re.M)
        if not mid:
            out_blocks.append(block)
            continue
        msgid = clean_msgid(mid.group(1))
        entry = TRANSLATIONS.get(msgid)
        if entry is None or lang not in entry:
            out_blocks.append(block)
            continue

        new_text = entry[lang]
        new_block_lines = []
        for line in block.split("\n"):
            if line.startswith("#, fuzzy"):
                continue  # снимаем fuzzy-флаг — перевод теперь валиден
            if line.startswith("#| msgid"):
                continue  # убираем устаревшие подсказки msgmerge
            new_block_lines.append(line)
        new_block = "\n".join(new_block_lines)
        new_block = re.sub(
            r'^msgstr .*$',
            f'msgstr "{po_escape(new_text)}"',
            new_block,
            count=1,
            flags=re.M,
        )
        out_blocks.append(new_block)
        changed += 1

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(out_blocks))
    print(f"{lang}: обновлено записей — {changed}")


for lang in ("ru", "uz", "en"):
    fill_po(f"locale/{lang}/LC_MESSAGES/django.po", lang)
print("DONE")
