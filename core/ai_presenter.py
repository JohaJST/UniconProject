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

Этап 2:
  4. synthesize_scene_speech(text, lang) — генерация MP3 через edge-tts
     (uz-UZ-MadinaNeural, ru-RU-SvetlanaNeural, en-US-AvaMultilingualNeural)
     с поддержкой опционального переключения на Azure Speech REST API
     или OpenAI TTS через переменные окружения в .env.
  5. get_or_build_presentation(lang) — посегментное кэширование MP3 и
     manifest.json в default_storage (media/ai_presenter/<lang>/<state_hash>/),
     дублирование в django.core.cache.cache, защита Redis-локом при
     перегенерации и автоматическая очистка устаревших файлов предыдущего хэша.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import re
import time
from typing import Any
from xml.sax.saxutils import escape as xml_escape

import requests
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import translation

from core.models import About, Courses, News, Partners, Teachers

VALID_LANGS = ("uz", "ru", "en")
DEFAULT_LANG = "uz"

_AI_TIMEOUT = 45
_TTS_TIMEOUT = 30
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

# Нейронные голоса Microsoft (для edge-tts и Azure Speech REST API)
EDGE_TTS_VOICES = {
    "uz": "uz-UZ-MadinaNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "en": "en-US-AvaMultilingualNeural",
}

_XML_LANG_MAP = {
    "uz": "uz-UZ",
    "ru": "ru-RU",
    "en": "en-US",
}

_MANIFEST_CACHE_TTL = 60 * 60 * 24 * 7  # 7 суток
_LOCK_TIMEOUT = 60                      # 60 секунд на генерацию всех сцен

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


class AIPresenterTTSError(Exception):
    """Внутреннее исключение при синтезе речи."""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Вспомогательные утилиты
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_lang(lang: str | None) -> str:
    if not lang:
        return DEFAULT_LANG
    clean = str(lang).strip().lower()[:2]
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


def _get_voice_for_lang(lang: str) -> str:
    """Возвращает нейронный голос Microsoft для языка (с поддержкой .env переопределения)."""
    lang = _normalize_lang(lang)
    env_key = f"AI_PRESENTER_VOICE_{lang.upper()}"
    return (os.getenv(env_key) or "").strip() or EDGE_TTS_VOICES[lang]


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
                    "Training of cybersecurity specialists",
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
                "Нам доверяют ведущие государственные и профильные организации. "
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
                f"Ta'lim sifatini sohaning yetakchi mutaxassislari va tajribali pedagoglar, "
                f"jumladan {top_teacher_str} kabi ekspertlar ta'minlaydi. Ular tinglovchilarga "
                "real amaliy tajriba va zamonaviy bilimlarni yetkazadilar."
                if top_teacher_str else
                "Darslarimizni sohaning yetakchi mutaxassislari va katta amaliy tajribaga "
                "ega ustozlar jamoasi olib boradi."
            ),
            "news": (
                f"Yangiliklar bo'limida maktabimiz hayotidagi eng muhim voqealar, jumladan "
                f"{latest_news_title} haqida batafsil ma'lumot olishingiz mumkin."
                if latest_news_title else
                "So'nggi yangiliklar bo'limida Kriptologiya maktabi hayotidagi muhim "
                "voqealar, yangi o'quv oqimlari va ilmiy tadbirlar yoritib boriladi."
            ),
            "partners": (
                f"Bizga {partners_count} ta yetakchi tashkilot va kompaniyalar, jumladan "
                f"{top_partners_str} ishonch bildirgan. Kriptologiya maktabi kurslariga "
                "yoziling va kelajak kasbini biz bilan egallang!"
                if top_partners_str else
                "Yetakchi korxona va tashkilotlar bilan hamkorlikda yangi avlod "
                "mutaxassislarini tayyorlaymiz. Kriptologiya maktabiga marhamat!"
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


# ─────────────────────────────────────────────────────────────────────────────
# 5. Синтез речи (TTS): edge-tts + опционально Azure Speech / OpenAI TTS
# ─────────────────────────────────────────────────────────────────────────────

async def _edge_tts_stream_bytes(text: str, voice: str, rate: str = "+0%", pitch: str = "+0Hz") -> bytes:
    """Асинхронная генерация MP3-потока через библиотеку edge-tts."""
    try:
        import edge_tts
    except ImportError as exc:
        raise AIPresenterTTSError("edge_tts_not_installed") from exc

    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    audio_chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio" and chunk.get("data"):
            audio_chunks.append(chunk["data"])

    audio_bytes = b"".join(audio_chunks)
    if not audio_bytes:
        raise AIPresenterTTSError("empty_edge_tts_audio")
    return audio_bytes


def _synthesize_with_edge_tts(text: str, lang: str) -> bytes:
    """
    Синхронная обёртка над асинхронным edge-tts с использованием asyncio.run().
    Если в текущем потоке уже запущен event loop (например, под ASGI),
    выполняет asyncio.run() в отдельном рабочем потоке.
    """
    voice = _get_voice_for_lang(lang)
    rate = (os.getenv("AI_PRESENTER_TTS_RATE") or "+0%").strip()
    pitch = (os.getenv("AI_PRESENTER_TTS_PITCH") or "+0Hz").strip()

    def _runner() -> bytes:
        return asyncio.run(_edge_tts_stream_bytes(text=text, voice=voice, rate=rate, pitch=pitch))

    try:
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop and running_loop.is_running():
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_runner)
                return future.result(timeout=_TTS_TIMEOUT)
        return _runner()
    except Exception as exc:
        if isinstance(exc, AIPresenterTTSError):
            raise
        raise AIPresenterTTSError(f"edge_tts_failed: {exc}") from exc


def _synthesize_with_azure_rest(text: str, lang: str) -> bytes:
    """
    Опциональный синтез через официальный Azure Cognitive Services Speech REST API,
    если в .env заданы AZURE_SPEECH_KEY и AZURE_SPEECH_REGION.
    """
    speech_key = (os.getenv("AZURE_SPEECH_KEY") or "").strip()
    speech_region = (os.getenv("AZURE_SPEECH_REGION") or "").strip()
    if not speech_key or not speech_region:
        raise AIPresenterTTSError("missing_azure_credentials")

    voice = _get_voice_for_lang(lang)
    xml_lang = _XML_LANG_MAP.get(lang, "uz-UZ")
    escaped_text = xml_escape(text)

    ssml = (
        f"<speak version='1.0' xml:lang='{xml_lang}'>"
        f"<voice xml:lang='{xml_lang}' name='{voice}'>{escaped_text}</voice>"
        f"</speak>"
    )

    endpoint = (
        (os.getenv("AZURE_SPEECH_ENDPOINT") or "").strip()
        or f"https://{speech_region}[.tts.speech.microsoft.com/cognitiveservices/v1](https://.tts.speech.microsoft.com/cognitiveservices/v1)"
    )
    headers = {
        "Ocp-Apim-Subscription-Key": speech_key,
        "Content-Type": "application/ssml+xml; charset=utf-8",
        "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3",
        "User-Agent": "UniconAIPresenter/1.0",
    }

    try:
        resp = requests.post(
            endpoint,
            data=ssml.encode("utf-8"),
            headers=headers,
            timeout=_TTS_TIMEOUT,
        )
        resp.raise_for_status()
        if not resp.content:
            raise AIPresenterTTSError("empty_azure_audio")
        return resp.content
    except requests.RequestException as exc:
        raise AIPresenterTTSError("azure_tts_unavailable") from exc


def _synthesize_with_openai_tts(text: str, lang: str) -> bytes:
    """
    Опциональный синтез через OpenAI Audio Speech API, если в .env
    включён провайдер openai и задан OPENAI_API_KEY (или OPENAI_TTS_API_KEY).
    """
    api_key = (os.getenv("OPENAI_TTS_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise AIPresenterTTSError("missing_openai_tts_key")

    endpoint = (
        (os.getenv("OPENAI_TTS_URL") or "").strip()
        or "[https://api.openai.com/v1/audio/speech](https://api.openai.com/v1/audio/speech)"
    )
    model = (os.getenv("OPENAI_TTS_MODEL") or "tts-1").strip()
    voice = (os.getenv("OPENAI_TTS_VOICE") or "nova").strip()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "input": text,
        "voice": voice,
        "response_format": "mp3",
    }

    try:
        resp = requests.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=_TTS_TIMEOUT,
        )
        resp.raise_for_status()
        if not resp.content:
            raise AIPresenterTTSError("empty_openai_audio")
        return resp.content
    except requests.RequestException as exc:
        raise AIPresenterTTSError("openai_tts_unavailable") from exc


def synthesize_scene_speech(text: str, lang: str = DEFAULT_LANG) -> bytes:
    """
    Единая точка синтеза речи (MP3) для одной сцены.
    Выбирает провайдера по AI_PRESENTER_TTS_PROVIDER (edge | azure | openai)
    или автоматически использует Azure/OpenAI при наличии их ключей в .env,
    с безотказным откатом на edge-tts в случае ошибки внешнего API.
    """
    lang = _normalize_lang(lang)
    clean_speech = _clean_text(text, max_len=600)
    if not clean_speech:
        raise AIPresenterTTSError("empty_text")

    provider = (os.getenv("AI_PRESENTER_TTS_PROVIDER") or "").strip().lower()

    if provider == "azure" or (not provider and os.getenv("AZURE_SPEECH_KEY") and os.getenv("AZURE_SPEECH_REGION")):
        try:
            return _synthesize_with_azure_rest(clean_speech, lang)
        except AIPresenterTTSError:
            return _synthesize_with_edge_tts(clean_speech, lang)

    if provider == "openai":
        try:
            return _synthesize_with_openai_tts(clean_speech, lang)
        except AIPresenterTTSError:
            return _synthesize_with_edge_tts(clean_speech, lang)

    return _synthesize_with_edge_tts(clean_speech, lang)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Кэширование по state_hash, сохранение в media/ и очистка старых файлов
# ─────────────────────────────────────────────────────────────────────────────

def _manifest_cache_key(lang: str, state_hash: str) -> str:
    return f"ai_presenter:manifest:{lang}:{state_hash}"


def _latest_hash_cache_key(lang: str) -> str:
    return f"ai_presenter:latest_hash:{lang}"


def _lock_cache_key(lang: str) -> str:
    return f"ai_presenter_lock:{lang}"


def _manifest_storage_path(lang: str, state_hash: str) -> str:
    return f"ai_presenter/{lang}/{state_hash}/manifest.json"


def _scene_audio_storage_path(lang: str, state_hash: str, idx: int, scene_id: str) -> str:
    safe_id = re.sub(r"[^a-z0-9_-]", "", str(scene_id).lower()) or f"s{idx}"
    return f"ai_presenter/{lang}/{state_hash}/scene_{idx}_{safe_id}.mp3"


def _save_to_storage_exact(rel_path: str, content_bytes: bytes) -> str:
    """
    Сохраняет файл в default_storage строго по указанному пути
    (удаляя прежний файл при совпадении имени, чтобы Django не добавлял суффикс).
    """
    if default_storage.exists(rel_path):
        default_storage.delete(rel_path)
    return default_storage.save(rel_path, ContentFile(content_bytes))


def _manifest_is_valid_and_files_exist(manifest: Any, lang: str, state_hash: str) -> bool:
    """
    Проверяет, что структура манифеста валидна, его хэш совпадает с текущим,
    а сам manifest.json и все сгенерированные MP3-файлы сцен физически существуют
    в default_storage.
    """
    if not isinstance(manifest, dict):
        return False
    if manifest.get("lang") != lang or manifest.get("hash") != state_hash:
        return False

    scenes = manifest.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        return False

    manifest_path = _manifest_storage_path(lang, state_hash)
    if not default_storage.exists(manifest_path):
        return False

    for idx, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            return False
        scene_id = scene.get("id") or f"s{idx}"
        expected_audio_path = _scene_audio_storage_path(lang, state_hash, idx, scene_id)
        # Если для сцены был сохранён audio_url, сам MP3 обязан лежать в storage
        if not scene.get("audio_url") or not default_storage.exists(expected_audio_path):
            return False

    return True


def _load_manifest_from_storage(lang: str, state_hash: str) -> dict[str, Any] | None:
    """Читает manifest.json из default_storage, если он существует и валиден."""
    manifest_path = _manifest_storage_path(lang, state_hash)
    if not default_storage.exists(manifest_path):
        return None
    try:
        with default_storage.open(manifest_path, "rb") as f:
            raw = f.read().decode("utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _cleanup_hash_directory(lang: str, old_hash: str) -> None:
    """
    Удаляет все файлы устаревшего хэша из default_storage
    по пути ai_presenter/<lang>/<old_hash>/ и инвалидирует его кэш.
    """
    if not old_hash:
        return

    cache.delete(_manifest_cache_key(lang, old_hash))
    prefix_dir = f"ai_presenter/{lang}/{old_hash}"

    try:
        if not default_storage.exists(prefix_dir):
            # Даже если сама директория не определяется через exists(),
            # пробуем listdir() на случай S3/кастомного стораджа
            pass
        _, files = default_storage.listdir(prefix_dir)
        for filename in files:
            file_rel_path = f"{prefix_dir}/{filename}"
            try:
                default_storage.delete(file_rel_path)
            except Exception:
                pass
    except Exception:
        # Фолбэк: пробуем удалить стандартные пути напрямую
        for idx, sec_id in enumerate(SECTION_ORDER):
            candidate = _scene_audio_storage_path(lang, old_hash, idx, sec_id)
            if default_storage.exists(candidate):
                default_storage.delete(candidate)
        manifest_candidate = _manifest_storage_path(lang, old_hash)
        if default_storage.exists(manifest_candidate):
            default_storage.delete(manifest_candidate)


def _cleanup_stale_lang_dirs(lang: str, keep_hash: str, previous_hash: str | None = None) -> None:
    """
    Удаляет файлы предыдущего хэша (из Redis-ключа ai_presenter:latest_hash:<lang>),
    а также подчищает любые другие осиротевшие папки старых хэшей внутри
    ai_presenter/<lang>/.
    """
    if previous_hash and previous_hash != keep_hash:
        _cleanup_hash_directory(lang, previous_hash)

    base_dir = f"ai_presenter/{lang}"
    try:
        dirs, _ = default_storage.listdir(base_dir)
        for dir_name in dirs:
            if dir_name and dir_name != keep_hash:
                _cleanup_hash_directory(lang, dir_name)
    except Exception:
        pass


def get_or_build_presentation(lang: str = DEFAULT_LANG) -> dict[str, Any]:
    """
    Главная точка входа для получения JSON-манифеста презентации:
      1. Вычисляет актуальный state_hash по данным БД и языку.
      2. Если state_hash не менялся и файлы сцен существуют в default_storage —
         мгновенно возвращает готовый манифест без вызова DeepSeek и TTS.
      3. Если данные изменились — ставит Redis-лок, генерирует новый сценарий
         и MP3-файлы каждой сцены, сохраняет manifest.json в media/ и кэш,
         обновляет ai_presenter:latest_hash:<lang> и удаляет старые файлы.
    """
    lang = _normalize_lang(lang)
    context_dict = collect_about_context(lang)
    state_hash = compute_state_hash(context_dict, lang)

    manifest_key = _manifest_cache_key(lang, state_hash)
    latest_hash_key = _latest_hash_cache_key(lang)

    # ── 1. Быстрый путь: манифест уже в кэше и все файлы на месте ────────
    cached_manifest = cache.get(manifest_key)
    if _manifest_is_valid_and_files_exist(cached_manifest, lang, state_hash):
        cache.set(latest_hash_key, state_hash, timeout=_MANIFEST_CACHE_TTL)
        return cached_manifest

    # ── 2. Быстрый путь: манифест есть на диске (например, после рестарта Redis) ──
    disk_manifest = _load_manifest_from_storage(lang, state_hash)
    if _manifest_is_valid_and_files_exist(disk_manifest, lang, state_hash):
        cache.set(manifest_key, disk_manifest, timeout=_MANIFEST_CACHE_TTL)
        cache.set(latest_hash_key, state_hash, timeout=_MANIFEST_CACHE_TTL)
        return disk_manifest

    # ── 3. Перегенерация под защитой Redis-лока ──────────────────────────
    lock_key = _lock_cache_key(lang)
    lock_acquired = cache.add(lock_key, "1", timeout=_LOCK_TIMEOUT)

    if not lock_acquired:
        # Параллельный запрос уже генерирует презентацию для этого языка —
        # ждём завершения (до ~12 секунд) и проверяем кэш/диск.
        for _ in range(24):
            time.sleep(0.5)
            ready = cache.get(manifest_key) or _load_manifest_from_storage(lang, state_hash)
            if _manifest_is_valid_and_files_exist(ready, lang, state_hash):
                cache.set(manifest_key, ready, timeout=_MANIFEST_CACHE_TTL)
                return ready

        # Если параллельный воркер ещё не успел закончить — отдаём
        # предыдущий валидный манифест (если есть) или быстрый фолбэк без ожидания
        prev_hash = cache.get(latest_hash_key)
        if prev_hash:
            prev_manifest = cache.get(_manifest_cache_key(lang, prev_hash)) or _load_manifest_from_storage(lang, prev_hash)
            if prev_manifest and isinstance(prev_manifest.get("scenes"), list):
                return prev_manifest

        fallback_scenes = [
            {**scene, "audio_url": None}
            for scene in build_fallback_script(context_dict, lang)
        ]
        return {
            "ok": True,
            "lang": lang,
            "hash": state_hash,
            "scenes": fallback_scenes,
        }

    try:
        previous_hash = cache.get(latest_hash_key)

        raw_scenes = generate_presentation_script(context_dict, lang)
        scenes_with_audio: list[dict[str, Any]] = []
        all_audio_ok = True

        for idx, scene in enumerate(raw_scenes):
            scene_id = scene.get("id") or f"s{idx}"
            speech_text = scene.get("speech_text") or ""
            audio_url: str | None = None

            try:
                mp3_bytes = synthesize_scene_speech(speech_text, lang=lang)
                rel_audio_path = _scene_audio_storage_path(lang, state_hash, idx, scene_id)
                saved_audio_path = _save_to_storage_exact(rel_audio_path, mp3_bytes)
                audio_url = default_storage.url(saved_audio_path)
            except Exception:
                all_audio_ok = False
                audio_url = None

            scenes_with_audio.append({
                "id": scene_id,
                "section": scene.get("section") or SECTION_SELECTORS.get(scene_id, f"#{scene_id}"),
                "title": scene.get("title") or DEFAULT_TITLES[lang].get(scene_id, ""),
                "speech_text": speech_text,
                "subtitles": scene.get("subtitles") or speech_text,
                "audio_url": audio_url,
            })

        manifest_data: dict[str, Any] = {
            "ok": True,
            "lang": lang,
            "hash": state_hash,
            "scenes": scenes_with_audio,
        }

        # Сохраняем manifest.json и обновляем latest_hash, если аудио успешно сгенерировано
        if all_audio_ok and scenes_with_audio:
            manifest_rel_path = _manifest_storage_path(lang, state_hash)
            manifest_bytes = json.dumps(manifest_data, ensure_ascii=False, indent=2).encode("utf-8")
            _save_to_storage_exact(manifest_rel_path, manifest_bytes)

            cache.set(manifest_key, manifest_data, timeout=_MANIFEST_CACHE_TTL)
            cache.set(latest_hash_key, state_hash, timeout=_MANIFEST_CACHE_TTL)

            # Очищаем устаревшие файлы предыдущего state_hash
            _cleanup_stale_lang_dirs(lang, keep_hash=state_hash, previous_hash=previous_hash)

        return manifest_data
    finally:
        cache.delete(lock_key)