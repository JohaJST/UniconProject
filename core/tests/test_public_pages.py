"""
core/tests/test_public_pages.py — публичные страницы about и self берут данные из БД.
Клиент без авторизации: страницы публичные.
"""
from django.test import TestCase

from core.models import About, SelfStudy


class AboutPageTests(TestCase):
    def test_no_about_record_renders_with_trans_fallback(self):
        r = self.client.get("/ru/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Смотреть курсы")
        self.assertContains(r, "Современный научно-образовательный центр")

    def test_empty_about_record_uses_trans_fallback(self):
        About.objects.create(id=1)
        r = self.client.get("/ru/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Современный научно-образовательный центр")
        self.assertContains(r, "Разработка и совершенствование национальных")
        self.assertContains(r, "Школа криптологии")

    def test_about_desc_shown_and_html_escaped(self):
        About.objects.create(
            id=1,
            desc_uz="uz text",
            desc_ru='Мой текст <script>alert(1)</script> "q"\nвторая строка',
            desc_en="en text",
        )
        r = self.client.get("/ru/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Мой текст")
        self.assertNotContains(r, "<script>alert(1)</script>")
        self.assertContains(r, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertContains(r, "<br>")  # linebreaksbr
        self.assertNotContains(r, "Современный научно-образовательный центр")

    def test_languages_show_different_values(self):
        About.objects.create(
            id=1,
            desc_uz="Uzbek description value",
            desc_ru="Русское значение описания",
            desc_en="English description value",
        )
        ru = self.client.get("/ru/")
        en = self.client.get("/en/")
        self.assertContains(ru, "Русское значение описания")
        self.assertNotContains(ru, "English description value")
        self.assertContains(en, "English description value")
        self.assertNotContains(en, "Русское значение описания")


class SelfPageTests(TestCase):
    def test_without_selfstudy_static_fallback(self):
        r = self.client.get("/ru/self/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Основы Кибербезопасности")
        self.assertNotContains(r, "<iframe")
        self.assertContains(r, "self/check/")

    def test_with_html_text_renders_sandboxed_iframe(self):
        SelfStudy.objects.create(
            id=1,
            html_text_uz="<p>uz</p>",
            html_text_ru='<div class="x">Привет</div><script>1</script>',
            html_text_en="<p>en</p>",
        )
        r = self.client.get("/ru/self/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "<iframe")
        self.assertContains(r, 'sandbox="allow-scripts"')
        self.assertNotContains(r, "allow-same-origin")
        self.assertContains(r, "class=&quot;x&quot;")      # кавычки в srcdoc экранированы
        self.assertNotContains(r, '<div class="x">')        # сырой HTML на странице отсутствует
        self.assertNotContains(r, "Основы Кибербезопасности")
        self.assertContains(r, "self/check/")               # кнопка сохранена