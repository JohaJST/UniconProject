# -*- coding: utf-8 -*-
"""Выводит msgid -> msgstr (ru) для TextID-ключей из моей задачи."""
import re

MY_IDS = {
    "homePageTitle", "heroChipOrgName", "heroHeadingMain", "heroHeadingGlow",
    "heroDescText", "heroBtnViewCourses", "heroBtnMoreInfo", "heroScrollHint",
    "goalMainTitle", "goalMainText", "goalMainHighlight", "tasksTitle",
    "task1Title", "task1Text", "task2Title", "task2Text", "task3Title",
    "task3Text", "footerBrandName", "footerBrandDesc", "footerContactHeading",
    "footerAddress", "footerWorkingHours", "footerSocialHeading",
    "footerCopyrightText", "footerDesignedByText",
    "loginPageTitle", "logoAlt",
    "reqPBPageTitle", "logoAltReq", "reqPBHeading", "reqPBHintText",
    "positionLabel", "positionPlaceholder", "companyLabel", "companyPlaceholder",
    "goHomeBtn",
    "ctgSelectTitle", "questionsCountSuffix", "noCategoriesYet", "ctgBack",
    "testsPageTitle", "availableTestsHeading", "chooseTestPrompt",
    "completedBadge", "newBadge", "questionsAbbrev", "viewResultsBtn",
    "startTestBtn", "noTestsAvailable", "contactTeacherPrompt",
    "inProgressBadge", "continueTestBtn",
    "exitConfirmMessage", "questionImageAlt", "noQuestionsInTest",
    "finishTestBtn", "submittingResultsText", "confirmSubmitAnswers",
    "submitErrorFallback", "connectionErrorPrefix",
    "profilePageTitle", "potokLabel", "positionLabelColon", "companyLabelColon",
    "langLabel", "testsCompletedLabel", "avgPercentLabel", "testHistoryHeading",
    "noTestsCompletedYet",
    "resultsPageTitleSuffix", "resultHeadingPrefix", "resultHeadingSuffix",
    "percentLabel", "correctLabel", "totalLabel", "backToHomeBtn",
}

data = open("locale/ru/LC_MESSAGES/django.po", encoding="utf-8").read()
entries = dict(
    (m.strip().replace('"', ""), t.strip().replace('"', ""))
    for m, t in re.findall(r"^msgid (.*?)\nmsgstr (.*?)(?=\n(?:#|\nmsgid|\Z))", data, re.S | re.M)
)
for mid in sorted(MY_IDS):
    print(f"{mid!r:32s} -> {entries.get(mid, '<НЕТ В СЛОВАРЕ>')!r}")
