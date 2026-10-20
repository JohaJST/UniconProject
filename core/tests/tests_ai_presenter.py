"""
core/tests/tests_ai_presenter.py
────────────────────────────────
Диагностический набор тестов для выявления точной причины:
  1. Почему не срабатывает DeepSeek AI и включается build_fallback_script().
  2. Почему не генерируется или не раздаётся звук (edge-tts / fallback TTS / URL).
  3. Почему запросы к /about/ возвращают 404.
"""
from __future__ import annotations

import inspect
import os
import shutil
import tempfile

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

import core.ai_presenter as presenter_mod
from core.ai_presenter import (
    AIPresenterError,
    AIPresenterTTSError,
    _call_deepseek_presenter,
    _synthesize_with_edge_tts,
    _synthesize_with_google_tts_fallback,
    build_fallback_script,
    collect_about_context,
    get_or_build_presentation,
    synthesize_scene_speech,
)


class AIPresenterDiagnosticTests(TestCase):
    def setUp(self):
        self.temp_media = tempfile.mkdtemp(prefix="diag_ai_presenter_")
        self.override = override_settings(
            MEDIA_ROOT=self.temp_media,
            MEDIA_URL="/media/",
        )
        self.override.enable()
        cache.clear()
        self.client = Client()

    def tearDown(self):
        cache.clear()
        self.override.disable()
        shutil.rmtree(self.temp_media, ignore_errors=True)

    # ── ДИАГНОСТИКА 1: Проверка кода core/ai_presenter.py на битые URL ───────

    def test_diag_1_check_source_code_urls_not_corrupted_by_markdown(self):
        """
        Проверяет исходный код core/ai_presenter.py на наличие повреждённых
        Markdown-ссылок вида '[https://...](https://...)', которые ломают requests.post/get.
        """
        source = inspect.getsource(presenter_mod)
        corrupted_lines = []
        for lineno, line in enumerate(source.splitlines(), start=1):
            if "](http" in line or "[http" in line:
                corrupted_lines.append(f"Строка {lineno}: {line.strip()}")

        if corrupted_lines:
            self.fail(
                "\n[ПРИЧИНА НАЙДЕНА] В файле core/ai_presenter.py обнаружены испорченные "
                "Markdown-скобки внутри URL-строк (из-за них падают и DeepSeek, и TTS):\n  "
                + "\n  ".join(corrupted_lines)
            )

    # ── ДИАГНОСТИКА 2: Проверка загрузки .env и реального вызова DeepSeek ────

    def test_diag_2_deepseek_direct_call_without_fallback_masking(self):
        """
        Вызывает _call_deepseek_presenter() напрямую (без перехвата ошибки
        фолбэком), чтобы увидеть, почему именно AI не отвечает.
        """
        api_key = (os.getenv("AI_API_KEY") or "").strip()
        self.assertTrue(
            bool(api_key),
            "[ПРИЧИНА НАЙДЕНА] Переменная окружения AI_API_KEY пуста в os.environ! "
            "Проверьте, вызывается ли load_dotenv() в settings.py / manage.py.",
        )

        ctx = collect_about_context("ru")
        try:
            ai_result = _call_deepseek_presenter(ctx, "ru")
        except AIPresenterError as exc:
            cause = exc.__cause__
            self.fail(
                f"\n[ПРИЧИНА НАЙДЕНА] DeepSeek API завершился с кодом '{exc}'.\n"
                f"Исходное исключение: {type(cause).__name__}: {cause}"
            )

        self.assertIn("scenes", ai_result)
        self.assertTrue(len(ai_result["scenes"]) > 0, "DeepSeek вернул пустой список сцен")

    # ── ДИАГНОСТИКА 3: Проверка генерации звука (edge-tts и Google TTS) ──────

    def test_diag_3_tts_engines_direct_check(self):
        """
        Проверяет по отдельности:
          1. Установлен ли пакет edge_tts и отдаёт ли он MP3-байты.
          2. Работает ли резервный HTTP-синтезатор (_synthesize_with_google_tts_fallback).
        """
        test_phrase = "Проверка синтеза речи Школы криптологии."
        errors_report = []

        # 3.1. Проверка edge-tts
        try:
            import edge_tts  # noqa: F401
        except ImportError as exc:
            errors_report.append(
                f"1) Пакет edge-tts НЕ установлен в текущем Python-окружении ({exc}). "
                f"Нужно выполнить: pip install edge-tts"
            )
        else:
            try:
                edge_bytes = _synthesize_with_edge_tts(test_phrase, "ru")
                self.assertTrue(len(edge_bytes) > 100, "edge-tts вернул пустой файл")
            except Exception as exc:
                errors_report.append(
                    f"1) edge-tts установлен, но не смог сгенерировать аудио: "
                    f"{type(exc).__name__}: {exc} (причина: {exc.__cause__})"
                )

        # 3.2. Проверка резервного Google HTTP TTS
        try:
            google_bytes = _synthesize_with_google_tts_fallback(test_phrase, "ru")
            self.assertTrue(len(google_bytes) > 100, "Google TTS вернул пустой файл")
        except Exception as exc:
            errors_report.append(
                f"2) Резервный Google HTTP TTS тоже упал: "
                f"{type(exc).__name__}: {exc} (причина: {exc.__cause__})"
            )

        if errors_report:
            self.fail(
                "\n[ПРИЧИНА ОТСУТСТВИЯ ЗВУКА НА СЕРВЕРЕ]:\n  "
                + "\n  ".join(errors_report)
            )

    # ── ДИАГНОСТИКА 4: Проверка того, что в манифесте реально есть audio_url ─

    def test_diag_4_manifest_contains_non_null_audio_urls(self):
        """
        Вызывает get_or_build_presentation('ru') без моков и проверяет,
        не превратились ли audio_url в None и не взят ли текст из шаблона-фолбэка.
        """
        manifest = get_or_build_presentation("ru")
        scenes = manifest.get("scenes") or []
        self.assertTrue(len(scenes) > 0, "Манифест не содержит сцен")

        first_scene = scenes[0]
        fallback_scenes = build_fallback_script(collect_about_context("ru"), "ru")

        is_using_fallback_text = (
            first_scene.get("speech_text") == fallback_scenes[0].get("speech_text")
        )
        null_audio_scenes = [s["id"] for s in scenes if not s.get("audio_url")]

        diag_messages = []
        if is_using_fallback_text:
            diag_messages.append(
                "Сценарий взят из жёсткого шаблона build_fallback_script(), а НЕ из DeepSeek AI!"
            )
        if null_audio_scenes:
            diag_messages.append(
                f"У сцен {null_audio_scenes} поле audio_url == None (синтез речи упал на сервере)!"
            )

        if diag_messages:
            self.fail("\n[ДИАГНОСТИКА МАНИФЕСТА]:\n  - " + "\n  - ".join(diag_messages))

    # ── ДИАГНОСТИКА 5: Проверка маршрутизации URL (/ vs /about/) и раздачи MP3

    def test_diag_5_routing_and_media_url_accessibility(self):
        """
        Проверяет:
          1. Какой реальный URL у view 'about' в urls.py (почему /about/ дал 404).
          2. Доступен ли сгенерированный MP3 по audio_url (/media/...) и по audio_stream_url.
        """
        real_about_url = reverse("about")
        resp_hardcoded = self.client.get("/about/?ai_presenter=1&lang=ru")
        resp_reversed = self.client.get(f"{real_about_url}?ai_presenter=1&lang=ru")

        self.assertEqual(
            resp_reversed.status_code,
            200,
            f"Даже reverse('about') ({real_about_url}) вернул {resp_reversed.status_code}!",
        )

        if resp_hardcoded.status_code == 404 and real_about_url != "/about/":
            # Проверяем также audio_stream_url, который в core/ai_presenter.py ссылался на /about/
            data = resp_reversed.json()
            stream_url = data["scenes"][0].get("audio_stream_url") or ""
            if stream_url.startswith("/about/"):
                self.fail(
                    f"\n[ПРИЧИНА НАЙДЕНА] View 'about' в urls.py зарегистрирован по адресу "
                    f"'{real_about_url}', а НЕ '/about/' (запрос к /about/ даёт 404)!\n"
                    f"Из-за этого резервная ссылка на звук audio_stream_url='{stream_url}' "
                    f"тоже ведёт на несуществующий '/about/' и возвращает 404!"
                )