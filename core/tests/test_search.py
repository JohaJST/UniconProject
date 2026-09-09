"""
core/tests/test_search.py — Unit-тесты для core/dashboard/list.py::apply_search

Покрытие:
  1. Пустой запрос ("" и None) -> queryset не меняется.
  2. Неизвестный tip -> queryset не меняется, без падений.
  3. Текстовый поиск (icontains), без учёта регистра.
  4. Защита от ValueError при поиске текста по tip с числовыми полями
     (result: foyiz/time/result) — сервер не должен падать с 500.
  5. Числовой поиск — точное совпадение (exact).
  6. Числовой поиск с запятой вместо точки ("75,5" -> 75.5).
  7. .distinct() убирает дубли строк, возникающие из-за JOIN по
     реверсивной связи (Subject -> Test, related_name="tests").

Все тесты используют реальную тестовую БД (django.test.TestCase),
без моков — apply_search работает напрямую с ORM.

ПРИМЕЧАНИЕ (SQLite): case-insensitive проверка (test_text_search_case_insensitive)
намеренно использует ASCII-поле (username), а не кириллицу. SQLite-бэкенд
Django (settings.py: DEBUG=True -> sqlite3) реализует icontains через LIKE,
чей встроенный case-folding в SQLite работает только для ASCII-символов
(без расширения ICU) — "иВан" никогда не совпадёт с "Иван" на этом бэкенде,
и это ограничение БД, а не баг apply_search. Тесты на точное совпадение
регистра (test_text_query_on_numeric_fields_does_not_crash и т.п.)
кириллицу использовать не мешает — там регистр запроса и данных совпадает.
"""
from django.test import TestCase

from core.dashboard.list import apply_search
from core.models import Result, Subject, Test, User
from core.models.auth import Role


class ApplySearchTests(TestCase):
    """Общая база: пара Subject/User/Test/Result для всех сценариев поиска."""

    @classmethod
    def setUpTestData(cls):
        cls.subject_math = Subject.objects.create(
            name_uz="Математика", name_ru="Математика", name_en="Math"
        )
        cls.subject_physics = Subject.objects.create(
            name_uz="Физика", name_ru="Физика", name_en="Physics"
        )

        cls.user_ivan = User.objects.create_user(
            username="ivan_search_test",
            password="pass12345",
            name="Иван",
            last_name="Петров",
            role=Role.STUDENT,
        )
        cls.user_maria = User.objects.create_user(
            username="maria_search_test",
            password="pass12345",
            name="Мария",
            last_name="Сидорова",
            role=Role.STUDENT,
        )

        cls.test_math = Test.objects.create(subject=cls.subject_math)

        cls.result_75 = Result.objects.create(
            user=cls.user_ivan, test=cls.test_math,
            result=7, foyiz=75, totalQuestions=10, time=120,
        )
        cls.result_50 = Result.objects.create(
            user=cls.user_maria, test=cls.test_math,
            result=5, foyiz=50, totalQuestions=10, time=90,
        )

    # ── 1. Пустой запрос ────────────────────────────────────────────────

    def test_empty_query_returns_all(self):
        """query="" — queryset должен вернуться без изменений."""
        qs = Subject.objects.all()
        result = apply_search(qs, "subject", "")
        self.assertEqual(list(result), list(qs))

    def test_none_query_returns_all(self):
        """query=None — тот же контракт, что и для пустой строки."""
        qs = Subject.objects.all()
        result = apply_search(qs, "subject", None)
        self.assertEqual(list(result), list(qs))

    # ── 2. Неизвестный tip ───────────────────────────────────────────────

    def test_unknown_tip_returns_unchanged(self):
        """
        tip, которого нет в SEARCH_FIELDS, не должен ронять функцию —
        даже с непустым query queryset возвращается как есть.
        """
        qs = Subject.objects.all()
        result = apply_search(qs, "unknown_model", "Математика")
        self.assertEqual(list(result), list(qs))

    # ── 3. Текстовый поиск, регистронезависимый ──────────────────────────

    def test_text_search_case_insensitive(self):
        """
        Поиск без учёта регистра должен работать независимо от регистра
        запроса. Используем ASCII-поле (username) — SQLite гарантированно
        поддерживает case-folding только для ASCII (см. примечание в шапке
        файла про кириллицу и LIKE).
        """
        result = apply_search(User.objects.all(), "user", "IVAN_SEARCH")
        self.assertIn(self.user_ivan, result)
        self.assertNotIn(self.user_maria, result)

    def test_text_search_matches_exact_case_cyrillic(self):
        """Дополнительная проверка на кириллице — регистр запроса совпадает
        с регистром данных, поэтому SQLite-ограничение здесь не мешает."""
        result = apply_search(User.objects.all(), "user", "Иван")
        self.assertIn(self.user_ivan, result)
        self.assertNotIn(self.user_maria, result)

    # ── 4. Защита типов БД: текст по tip с числовыми полями ──────────────

    def test_text_query_on_numeric_fields_does_not_crash(self):
        """
        tip="result" имеет числовые поля (time/foyiz/result). Поиск текста
        "Иван" не должен ронять apply_search ValueError-ом при попытке
        float("Иван") — он должен быть тихо пойман, а поиск — отработать
        по текстовым полям (user__name) как ни в чём не бывало.
        """
        result = apply_search(Result.objects.all(), "result", "Иван")
        self.assertIn(self.result_75, result)
        self.assertNotIn(self.result_50, result)

    # ── 5. Числовой поиск — точное совпадение ────────────────────────────

    def test_numeric_search_exact_match(self):
        """"75" должен найти Result с foyiz=75 через точное совпадение."""
        result = apply_search(Result.objects.all(), "result", "75")
        self.assertIn(self.result_75, result)
        self.assertNotIn(self.result_50, result)

    # ── 6. Числовой поиск с запятой вместо точки ─────────────────────────

    def test_numeric_search_with_comma_decimal(self):
        """
        "75,5" должен быть преобразован в "75.5" -> float(75.5) без
        ValueError. Поле foyiz — PositiveSmallIntegerField, поэтому Django
        обрежет 75.5 до 75 на уровне get_prep_value() при построении
        лукапа exact — итоговый SQL ищет foyiz=75, и запись с foyiz=75
        должна быть найдена. Главное здесь — что запятая корректно
        заменяется на точку и код не падает на float("75,5").
        """
        result = apply_search(Result.objects.all(), "result", "75,5")
        self.assertIn(self.result_75, result)
        self.assertNotIn(self.result_50, result)

    def test_non_numeric_text_does_not_trigger_number_filters(self):
        """
        Слово, которое не встречается ни в одном текстовом поле и не
        конвертируется в float, должно просто дать пустой результат —
        без исключений на этапе построения числового Q().
        """
        result = apply_search(Result.objects.all(), "result", "совершенно-случайный-текст")
        self.assertEqual(list(result), [])

    # ── 7. .distinct() против дублей от JOIN по реверсивной связи ────────

    def test_distinct_prevents_duplicate_rows_from_joins(self):
        """
        Test.subject имеет related_name="tests" — реверсивная связь
        Subject -> Test (one-to-many). Если у Subject несколько Test,
        JOIN по этой связи размножает строки Subject (по одной на каждый
        связанный Test) — ЭТО и есть классический сценарий, ради которого
        apply_search обязан звать .distinct() в конце.

        Мы явно строим "раздутый" queryset и убеждаемся, что до
        apply_search там реально дубли (СТРОГО по pk нашего Subject —
        setUpTestData уже создал subject_math с одним test_math, так что
        нефильтрованный join размножил бы и его тоже, давая ложный счёт).
        """
        subject = Subject.objects.create(
            name_uz="УникальноеНазваниеДляДублей", name_ru="Ru", name_en="En"
        )
        Test.objects.create(subject=subject)
        Test.objects.create(subject=subject)
        Test.objects.create(subject=subject)

        # JOIN по реверсивной связи "tests", ограниченный ИМЕННО этим
        # subject.pk — иначе subject_math (у которого есть свой test_math
        # из setUpTestData) тоже попал бы в join и испортил бы счёт.
        duplicated_qs = Subject.objects.filter(pk=subject.pk, tests__id__gte=0)
        self.assertEqual(
            duplicated_qs.count(), 3,
            "сетап теста не воспроизводит дубли — сам тест некорректен",
        )

        result = apply_search(duplicated_qs, "subject", "УникальноеНазваниеДляДублей")
        self.assertEqual(result.count(), 1)