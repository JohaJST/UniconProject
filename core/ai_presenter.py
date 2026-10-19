"""
core/ai_presenter.py
────────────────────
Бэкенд-сервис интерактивного голосового гида «AI Presenter» для страницы
«О нас» (templates/about.html) на трёх языках (uz, ru, en).

Этап 1:
  1. collect_about_context(lang) — сбор актуальных данных из моделей
     About, Courses, Teachers, News, Partners с учётом локали и правил
     отображения секций в шаблоне about.html.
  2. compute_state_hash(context_dict, lang) — детерминированный SHA-256
     отпечаток состояния БД и языка (16 hex-символов).
  3. generate_presentation_script(context_dict, lang) — генерация живого
     JSON-сценария экскурсии через DeepSeek API (deepseek-chat) с защитой
     от падений и автоматическим переключением на динамический фолбэк.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

import requests
from django.utils import translation

from core.models import About, Courses, News, Partners, Teachers

VALID_LANGS = ("uz", "ru", "en")
DEFAULT_LANG = "uz"

_AI_TIMEOUT = 45
_DEFAULT_MODEL = "deepseek-chat"

# Снимает ведущий ```/```json и завершающий ``` (как в core/dashboard/ai_translate.py)
_FENCE_RE = re.compile(r"^```(?:json)?\n?|\n?```$")

# Строгий порядок секций на странице templates/about.html
SECTION_ORDER = ("hero", "goals", "courses", "teachers", "news", "partners")

SECTION_SELECTORS = {
    "hero": "#hero",
    "goals": "#goals",
    "courses": "#courses",
    "teachers": "#teachers",
    "news": "#news",
    "partners": "#partners",
}

DEFAULT_TITLES = {
    "uz": {
        "hero": "Kriptologiya maktabi",
        "goals": "Maqsad va vazifalar",
        "courses": "O'quv kurslari",
        "teachers": "O'qituvchilar jamoasi",
        "news": "So'nggi yangiliklar",
        "partners": "Hamkor tashkilotlar",
    },
    "ru": {
        "hero": "Школа криптологии",
        "goals": "Цели и задачи",
        "courses": "Учебные курсы",
        "teachers": "Команда экспертов",
        "news": "Последние новости",
        "partners": "Наши партнёры",
    },
    "en": {
        "hero": "School of Cryptology",
        "goals": "Mission & Goals",
        "courses": "Training Courses",
        "teachers": "Expert Faculty",
        "news": "Latest News",
        "partners": "Trusted Partners",
    },
}

_LANGUAGE_INSTRUCTIONS = {
    "uz": (
        "Язык ответа: УЗБЕКСКИЙ (строго латиница — O'zbek lotin alifbosida). "
        "Используй современный, живой, грамотный литературный узбекский язык. "
        "Избегай машинного калькирования: текст должен звучать естественно "
        "для носителя языка при озвучке диктором."
    ),
    "ru": (
        "Язык ответа: РУССКИЙ. "
        "Используй уверенный, живой, современный деловой стиль без канцеляризмов."
    ),
    "en": (
        "Response language: ENGLISH. "
        "Use a confident, engaging, modern professional tone suitable for a tech academy."
    ),
}

_SYSTEM_PROMPT = (
    "Ты — харизматичный цифровой спикер и голосовой ИИ-гид образовательной "
    "платформы «Kriptologiya maktabi» (Школа криптологии и информационной безопасности).\n\n"
    "Твоя задача — провести увлекательную голосовую экскурсию по веб-странице "
    "платформы на основе переданного JSON-контекста.\n\n"
    "КРИТИЧЕСКИЕ ПРАВИЛА СЦЕНАРИЯ:\n"
    "1. НЕ БУДЬ СКУЧНЫМ ЧТЕЦОМ: Запрещено дословно копировать длинные тексты со "
    "страницы. Посетитель и так видит заголовки глазами — твоя речь должна "
    "дополнять экран, живо объяснять ценность и плавно переводить внимание от "
    "одной секции к другой.\n"
    "2. ТАЙМИНГ И ДЛИНА: Для КАЖДОЙ активной сцены поле 'speech_text' должно "
    "содержать ровно 2–3 предложения (примерно 22–38 слов, что соответствует "
    "8–12 секундам живой речи).\n"
    "3. ГОТОВНОСТЬ К TTS (ОЗВУЧКЕ): В 'speech_text' не используй списки, "
    "кавычки-ёлочки, слэши, звёздочки, эмодзи, сложные аббревиатуры или URL. "
    "Пиши чистым связным текстом, удобным для голосового синтезатора.\n"
    "4. РАБОТА С ДАННЫМИ БД: Обязательно вплетай реальные факты из входного "
    "контекста (назови 1–2 реальных курса, упомяни экспертов, тему свежей "
    "новости или партнёров). Если входные данные в БД заполнены на другом языке, "
    "естественно переведи и адаптируй их на целевой язык презентации.\n"
    "5. СУБТИТРЫ: Поле 'subtitles' может совпадать с 'speech_text' или быть его "
    "слегка ужатой, удобной для чтения с экрана версией (до 240 символов).\n"
    "6. СТРОГИЙ СПИСОК СЦЕН: Генерируй сцены ТОЛЬКО для тех секций, которые "
    "переданы в списке 'active_sections', сохраняя их точный порядок.\n\n"
    "Отвечай ТОЛЬКО валидным JSON без markdown-обёрток и комментариев по схеме:\n"
    "{\n"
    "  \"scenes\": [\n"
    "    {\n"
    "      \"id\": \"hero|goals|courses|teachers|news|partners\",\n"
    "      \"section\": \"#hero|#goals|#courses|#teachers|#news|#partners\",\n"
    "      \"title\": \"Короткое название шага\",\n"
    "      \"speech_text\": \"Текст для голосовой озвучки на 8-12 секунд...\",\n"
    "      \"subtitles\": \"Текст для отображения в блоке субтитров...\"\n"
    "    }\n"
    "  ]\n"
    "}"
)


class AIPresenterError(Exception):
    """Внутреннее исключение при обращении к LLM-провайдеру."""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Вспомогательные утилиты
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_lang(lang: str | None) -> str:
    if not lang:
        return DEFAULT_LANG
    clean = lang.strip().lower()[:2]
    return clean if clean in VALID_LANGS else DEFAULT_LANG


def _clean_text(value: Any, max_len: int = 280) -> str:
    """Очищает строку от лишних переводов строк/пробелов и ограничивает длину."""
    if not value:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rsplit(" ", 1)[0] + "…"


def _get_localized(obj: Any, field: str, lang: str) -> str:
    """
    Безопасно извлекает переводимое поле django-modeltranslation.
    Если перевод на выбранный язык (ru/en) в БД не заполнен, берёт активное
    значение или fallback на основной язык (uz), чтобы LLM-сценарист всегда
    получал осмысленную фактуру.
    """
    if obj is None:
        return ""
    val = (
        getattr(obj, f"{field}_{lang}", None)
        or getattr(obj, field, None)
        or getattr(obj, f"{field}_uz", None)
        or ""
    )
    return _clean_text(val)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Сборщик контекста страницы (collect_about_context)
# ─────────────────────────────────────────────────────────────────────────────

def collect_about_context(lang: str = DEFAULT_LANG) -> dict[str, Any]:
    """
    Собирает актуальные данные из БД для страницы about.html с учётом языка
    и правил видимости секций (см. core/about.py::about и templates/about.html).
    """
    lang = _normalize_lang(lang)

    with translation.override(lang):
        about_obj = About.objects.filter(id=1).first()
        courses_qs = list(Courses.objects.all().order_by("-created")[:6])
        teachers_qs = list(Teachers.objects.all().order_by("-created")[:6])
        news_qs = list(News.objects.all().order_by("-date")[:4])

        partners_enabled = bool(about_obj and about_obj.partners)
        partners_qs = list(Partners.objects.all().order_by("-created")[:10]) if partners_enabled else []

        courses_list = [
            {
                "title": _get_localized(c, "title", lang),
                "name": _get_localized(c, "name", lang),
                "desc": _get_localized(c, "desc", lang),
            }
            for c in courses_qs
        ]

        teachers_list = [
            {
                "fio": _clean_text(t.fio, 120),
                "position": _get_localized(t, "position", lang),
            }
            for t in teachers_qs
        ]

        news_list = [
            {
                "title": _get_localized(n, "title", lang),
                "desc": _get_localized(n, "desc", lang),
                "date": n.date.isoformat() if n.date else "",
            }
            for n in news_qs
        ]

        partners_list = [
            {"name": _clean_text(p.name, 100)}
            for p in partners_qs
            if (p.name or "").strip()
        ]

        # В templates/about.html секция #goals рендерится только {% if about %},
        # а секция #partners — только {% if about.partners and partners %}.
        sections = {
            "hero": {
                "active": True,
                "section": "#hero",
                "org_info": _get_localized(about_obj, "info", lang) or "UNICON.UZ",
                "title": _get_localized(about_obj, "title", lang) or DEFAULT_TITLES[lang]["hero"],
                "desc": _get_localized(about_obj, "desc", lang),
            },
            "goals": {
                "active": bool(about_obj is not None),
                "section": "#goals",
                "goals_info": _get_localized(about_obj, "goals_info", lang),
                "focus_areas": [
                    "Cryptographic protection / Kriptografik himoya",
                    "Scientific research / Ilmiy-tadqiqot",
                    " training of cybersecurity specialists",
                ],
            },
            "courses": {
                "active": True,
                "section": "#courses",
                "courses_info": _get_localized(about_obj, "courses_info", lang),
                "total_count": Courses.objects.count(),
                "items": courses_list,
            },
            "teachers": {
                "active": True,
                "section": "#teachers",
                "teachers_info": _get_localized(about_obj, "teachers_info", lang),
                "total_count": Teachers.objects.count(),
                "items": teachers_list,
            },
            "news": {
                "active": True,
                "section": "#news",
                "news_info": _get_localized(about_obj, "news_info", lang),
                "total_count": News.objects.count(),
                "items": news_list,
            },
            "partners": {
                "active": bool(partners_enabled and len(partners_list) > 0),
                "section": "#partners",
                "partners_info": _get_localized(about_obj, "partners_info", lang),
                "total_count": Partners.objects.count() if partners_enabled else 0,
                "items": partners_list,
            },
        }

    active_sections = [sec_id for sec_id in SECTION_ORDER if sections[sec_id]["active"]]

    return {
        "lang": lang,
        "active_sections": active_sections,
        "sections": sections,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Хэширование состояния (compute_state_hash)
# ─────────────────────────────────────────────────────────────────────────────

def compute_state_hash(context_dict: dict[str, Any], lang: str) -> str:
    """
    Вычисляет детерминированный SHA-256 хэш (16 символов) от канонизированного
    JSON контекста и языка. Любое изменение курса, новости, преподавателя или
    партнёра в дашборде автоматически изменит этот хэш.
    """
    lang = _normalize_lang(lang)
    canonical_payload = {
        "lang": lang,
        "context": context_dict,
    }
    serialized = json.dumps(canonical_payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


# ─────────────────────────────────────────────────────────────────────────────
# 3. Генерация сценария через DeepSeek (generate_presentation_script)
# ─────────────────────────────────────────────────────────────────────────────

def _call_deepseek_presenter(context_dict: dict[str, Any], lang: str) -> dict[str, Any]:
    """Отправляет запрос к DeepSeek API и возвращает распарсенный JSON."""
    api_key = (os.getenv("AI_API_KEY") or "").strip()
    if not api_key:
        raise AIPresenterError("missing_api_key")

    active_ids = context_dict.get("active_sections") or []
    active_data = {
        sec_id: context_dict["sections"][sec_id]
        for sec_id in active_ids
        if sec_id in context_dict.get("sections", {})
    }

    user_prompt_payload = {
        "target_language": lang,
        "language_instruction": _LANGUAGE_INSTRUCTIONS[lang],
        "active_sections": active_ids,
        "default_titles": DEFAULT_TITLES[lang],
        "page_data": active_data,
    }

    payload = {
        "model": _DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_prompt_payload, ensure_ascii=False)},
        ],
        "max_tokens": 2048,
        "temperature": 0.5,
        "response_format": {"type": "json_object"},
        "stream": False,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        resp = requests.post(
            "[https://api.deepseek.com/chat/completions](https://api.deepseek.com/chat/completions)",
            json=payload,
            headers=headers,
            timeout=_AI_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise AIPresenterError("ai_unavailable") from exc

    try:
        raw_text = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, AttributeError, TypeError) as exc:
        raise AIPresenterError("invalid_ai_response") from exc

    cleaned = _FENCE_RE.sub("", raw_text).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AIPresenterError("invalid_ai_response") from exc

    if not isinstance(parsed, dict) or not isinstance(parsed.get("scenes"), list):
        raise AIPresenterError("invalid_ai_response")

    return parsed


def generate_presentation_script(context_dict: dict[str, Any], lang: str = DEFAULT_LANG) -> list[dict[str, str]]:
    """
    Генерирует сценарий презентации для активных секций страницы.
    Если AI_API_KEY отсутствует, API недоступен или вернул неполный ответ —
    безопасно возвращает динамический шаблонный сценарий (fallback).
    """
    lang = _normalize_lang(lang)
    fallback_scenes = build_fallback_script(context_dict, lang)
    fallback_by_id = {scene["id"]: scene for scene in fallback_scenes}
    active_ids = context_dict.get("active_sections") or list(fallback_by_id.keys())

    try:
        ai_data = _call_deepseek_presenter(context_dict, lang)
    except AIPresenterError:
        return fallback_scenes

    ai_scenes_by_id: dict[str, dict[str, str]] = {}
    for raw_scene in ai_data.get("scenes", []):
        if not isinstance(raw_scene, dict):
            continue
        sec_id = str(raw_scene.get("id") or "").strip().lower()
        if sec_id not in SECTION_SELECTORS or sec_id not in active_ids:
            continue

        speech_text = _clean_text(raw_scene.get("speech_text"), max_len=450)
        if not speech_text:
            continue

        subtitles = _clean_text(raw_scene.get("subtitles"), max_len=300) or speech_text
        title = _clean_text(raw_scene.get("title"), max_len=80) or DEFAULT_TITLES[lang][sec_id]

        ai_scenes_by_id[sec_id] = {
            "id": sec_id,
            "section": SECTION_SELECTORS[sec_id],
            "title": title,
            "speech_text": speech_text,
            "subtitles": subtitles,
        }

    # Гарантируем строгий порядок секций и заполняем возможные пропуски из фолбэка
    final_scenes: list[dict[str, str]] = []
    for sec_id in active_ids:
        if sec_id in ai_scenes_by_id:
            final_scenes.append(ai_scenes_by_id[sec_id])
        elif sec_id in fallback_by_id:
            final_scenes.append(fallback_by_id[sec_id])

    return final_scenes if final_scenes else fallback_scenes


# ─────────────────────────────────────────────────────────────────────────────
# 4. Безотказный динамический фолбэк (build_fallback_script)
# ─────────────────────────────────────────────────────────────────────────────

def build_fallback_script(context_dict: dict[str, Any], lang: str = DEFAULT_LANG) -> list[dict[str, str]]:
    """
    Формирует качественный сценарий на нужном языке (uz, ru, en), подставляя
    реальные названия курсов, имена преподавателей, заголовки новостей и
    количество партнёров из context_dict, если LLM API недоступен.
    """
    lang = _normalize_lang(lang)
    sections = context_dict.get("sections", {})
    active_ids = context_dict.get("active_sections") or list(SECTION_ORDER)

    # Извлекаем реальные данные для подстановки в речь
    courses_items = sections.get("courses", {}).get("items", [])
    course_names = [c.get("name") or c.get("title") for c in courses_items if (c.get("name") or c.get("title"))]
    top_courses_str = ", ".join(course_names[:2])

    teachers_items = sections.get("teachers", {}).get("items", [])
    teacher_names = [t.get("fio") for t in teachers_items if t.get("fio")]
    top_teacher_str = teacher_names[0] if teacher_names else ""

    news_items = sections.get("news", {}).get("items", [])
    latest_news_title = news_items[0].get("title") if news_items else ""

    partners_count = sections.get("partners", {}).get("total_count", 0)
    partners_items = sections.get("partners", {}).get("items", [])
    partner_names = [p.get("name") for p in partners_items if p.get("name")]
    top_partners_str = ", ".join(partner_names[:2])

    if lang == "ru":
        templates = {
            "hero": (
                "Добро пожаловать в Школу криптологии! Мы рады приветствовать вас на "
                "образовательной платформе, где формируются передовые компетенции в сфере "
                "криптографической защиты и национальной информационной безопасности."
            ),
            "goals": (
                "Наша ключевая миссия — подготовка высококвалифицированных специалистов "
                "и развитие научных исследований. Мы объединяем фундаментальную теорию "
                "с реальными задачами защиты цифровых систем."
            ),
            "courses": (
                f"Обратите внимание на наши учебные программы, среди которых {top_courses_str}. "
                "Каждый курс разработан так, чтобы дать слушателям максимум прикладных "
                "навыков работы с современными средствами криптозащиты."
                if top_courses_str else
                "В разделе учебных программ представлены специализированные курсы по "
                "современной криптографии и информационной безопасности для специалистов разного уровня."
            ),
            "teachers": (
                f"За качеством обучения стоит команда практикующих экспертов и педагогов, "
                f"включая таких специалистов, как {top_teacher_str}. Они передают слушателям "
                "реальный отраслевой опыт и актуальные методики."
                if top_teacher_str else
                "Занятия проводят ведущие специалисты отрасли и опытные педагоги, которые "
                "делятся практическими знаниями и реальными кейсами из сферы кибербезопасности."
            ),
            "news": (
                f"В блоке новостей вы всегда найдёте свежие события нашей школы, например: "
                f"{latest_news_title}. Мы регулярно проводим семинары, запускаем новые потоки "
                "и делимся достижениями наших выпускников."
                if latest_news_title else
                "Следите за последними событиями нашей школы в разделе новостей. Здесь "
                "публикуются анонсы новых потоков, научных семинаров и важных мероприятий."
            ),
            "partners": (
                f"Нам доверяют {partners_count} ведущих организаций и компаний, включая {top_partners_str}. "
                "Присоединяйтесь к обучению в Школе криптологии и развивайте свои профессиональные навыки вместе с нами!"
                if top_partners_str else
                f"Нам доверяют ведущие государственные и профильные организации. "
                "Присоединяйтесь к Школе криптологии и выходите на новый профессиональный уровень!"
            ),
        }
    elif lang == "en":
        templates = {
            "hero": (
                "Welcome to the School of Cryptology! We are delighted to guide you through "
                "our educational platform dedicated to advanced cryptography and national "
                "information security."
            ),
            "goals": (
                "Our core mission is to train next-generation cybersecurity professionals "
                "and advance scientific research. We bridge deep theoretical knowledge with "
                "practical cryptographic defense."
            ),
            "courses": (
                f"Explore our specialized training programs, including {top_courses_str}. "
                "Each curriculum is designed to provide hands-on expertise in modern "
                "information protection."
                if top_courses_str else
                "Our training catalog offers specialized courses in modern cryptography "
                "and cybersecurity tailored for industry professionals."
            ),
            "teachers": (
                f"Our programs are led by seasoned industry practitioners and educators, "
                f"such as {top_teacher_str}. They bring real-world experience directly into the classroom."
                if top_teacher_str else
                "You will learn from leading industry specialists and experienced educators "
                "who share practical insights and real-world security cases."
            ),
            "news": (
                f"Stay updated with the latest highlights from our academy, including "
                f"{latest_news_title}. We regularly host workshops, launch new cohorts, "
                "and share research milestones."
                if latest_news_title else
                "Keep up with the most important events and announcements of the School "
                "of Cryptology in our latest news section."
            ),
            "partners": (
                f"We are proud to collaborate with {partners_count} leading organizations, "
                f"including {top_partners_str}. Start your learning journey with the School "
                "of Cryptology today!"
                if top_partners_str else
                "We collaborate with leading enterprises and institutions to train the "
                "next generation of experts. Join the School of Cryptology today!"
            ),
        }
    else:  # uz (default)
        templates = {
            "hero": (
                "Kriptologiya maktabiga xush kelibsiz! Sizni zamonaviy kriptografik himoya "
                "va axborot xavfsizligi sohasida yetuk mutaxassislarni tayyorlovchi ta'lim "
                "platformamiz bilan tanishtirishdan mamnunmiz."
            ),
            "goals": (
                "Bizning asosiy maqsadimiz — milliy axborot xavfsizligini ta'minlash uchun "
                "malakali kadrlar tayyorlash hamda ilmiy-tadqiqot ishlarini yangi bosqichga "
                "olib chiqishdir."
            ),
            "courses": (
                f"O'quv dasturlarimiz bo'limida {top_courses_str} kabi zamonaviy kurslar "
                "jamlangan. Har bir yo'nalish tinglovchilarga amaliy ko'nikmalar va "
                "chuqur bilim berishga mo'ljallangan."
                if top_courses_str else
                "O'quv dasturlarimiz bo'limida zamonaviy kriptografiya va axborot "
                "xavfsizligi bo'yicha eng dolzarb kurslar taqdim etilgan."
            ),
            "teachers": (
                f"Ta'lim сифатини соҳанинг етакчи мутахассислари ва тажрибали педагоглар, "
                f"jumladan {top_teacher_str} каби экспертлар таъминлайди. Улар ўзларининг "
                "бой амалий тажрибалари билан ўртоқлашадилар."
                if False else  # чистая узбекская латиница ниже
                (
                    f"Ta'lim sifatini sohaning yetakchi mutaxassislari va tajribali pedagoglar, "
                    f"jumladan {top_teacher_str} kabi ekspertlar ta'minlaydi. Ular tinglovchilarga "
                    "real amaliy tajriba va zamonaviy bilimlarni yetkazadilar."
                    if top_teacher_str else
                    "Darslarimizni sohaning yetakchi mutaxassislari va katta amaliy tajribaga "
                    "ega ustozlar jamoasi olib boradi."
                )
            ),
            "news": (
                f"Yangiliklar bo'limida maktabimiz hayotidagi eng muhim voqealar, jumladan "
                f"{latest_news_title} haqida batafsil ma'lumot olishingiz mumkin."
                if latest_news_title else
                "So'nggi yangiliklar bo'limida Kriptologiya maktabi hayotidagi muhim "
                "voqealar, yangi o'quv oqimlari va ilmiy tadbirlar yoritib boriladi."
            ),
            "partners": (
                f"Bizga {partners_count} ta yetakchi tashkilot va kompaniyalar, жумладан "
                if False else
                (
                    f"Bizga {partners_count} ta yetakchi tashkilot va kompaniyalar, jumladan "
                    f"{top_partners_str} ishonch bildirgan. Kriptologiya maktabi kurslariga "
                    "yoziling va kelajak kasbini biz bilan egallang!"
                    if top_partners_str else
                    "Yetakchi korxona va tashkilotlar bilan hamkorlikda yangi avlod "
                    "mutaxassislarini tayyorlaymiz. Kriptologiya maktabiga marhamat!"
                )
            ),
        }

    scenes: list[dict[str, str]] = []
    for sec_id in active_ids:
        if sec_id not in SECTION_SELECTORS:
            continue
        text = templates.get(sec_id, "")
        scenes.append({
            "id": sec_id,
            "section": SECTION_SELECTORS[sec_id],
            "title": DEFAULT_TITLES[lang][sec_id],
            "speech_text": text,
            "subtitles": text,
        })

    return scenes