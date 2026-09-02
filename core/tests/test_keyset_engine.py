"""
core/tests/test_keyset_engine.py — Unit-тесты для
core/dashboard/pagination/keyset_engine.py

Используется core.models.Question (per промпт: "Question или User — что
удобнее") + вспомогательный core.models.Test (обязательный FK у Question,
subject/potok у Test nullable — минимальная фикстура).

created у Question — auto_now_add=True, поэтому явные значения
проставляются НЕ через .save(), а через queryset.update() — этот путь
не проходит через Model.save() и не переписывается auto_now_add обратно.

Тесты гоняются через django.test.TestCase — реальная тестовая БД (в этом
проекте, при DEBUG=True, это SQLite), транзакция откатывается после
каждого теста. HttpRequest строится через django.test.RequestFactory —
paginate_keyset() вызывается напрямую, без похода через реальный view.
"""
from datetime import datetime, timedelta

from django.test import RequestFactory, TestCase

from core.dashboard.pagination.keyset_engine import paginate_keyset
from core.dashboard.pagination.registry import ListSpec
from core.dashboard.pagination.tokens import encode_cursor
from core.models import Question, Test


def _spec(sort_field="created", sort_direction="desc", page_size=2) -> ListSpec:
    return ListSpec(
        queryset_factory=lambda: Question.objects.all(),
        engine="keyset",
        sort_field=sort_field,
        sort_direction=sort_direction,
        page_size=page_size,
    )


class KeysetEngineTestCase(TestCase):
    """Общая база: создаёт Test + N Question с управляемыми created/id."""

    def setUp(self):
        self.factory = RequestFactory()
        self.test_obj = Test.objects.create()

    def _make_questions(self, count: int) -> list[Question]:
        """
        Создаёт count вопросов подряд: id растёт по порядку создания,
        created — тоже растёт (база + i дней), т.е. id и created
        согласованы (более новый вопрос = больший id = больший created).
        """
        base = datetime(2026, 1, 1)
        questions = []
        for i in range(count):
            q = Question.objects.create(test=self.test_obj, text=f"q{i}")
            Question.objects.filter(pk=q.pk).update(created=base + timedelta(days=i))
            q.refresh_from_db()
            questions.append(q)
        return questions

    def _get(self, **params):
        return self.factory.get("/dashboard/list/question/", data=params)


class StartNextPrevLastTests(KeysetEngineTestCase):
    """Базовая навигация: start -> next -> last -> prev, sort_field="created"."""

    def setUp(self):
        super().setUp()
        # По убыванию created (новые сверху): q4, q3, q2, q1, q0
        self.questions = self._make_questions(5)
        self.spec = _spec(sort_field="created", sort_direction="desc", page_size=2)

    def test_start_page(self):
        request = self._get()
        page = paginate_keyset(Question.objects.all(), self.spec, request)

        self.assertEqual([q.id for q in page.items], [self.questions[4].id, self.questions[3].id])
        self.assertFalse(page.has_prev)
        self.assertTrue(page.has_next)
        self.assertIsNone(page.urls["start"])
        self.assertIsNone(page.urls["prev"])
        self.assertIsNotNone(page.urls["next"])
        self.assertIsNotNone(page.urls["last"])

    def test_next_page(self):
        start_request = self._get()
        start_page = paginate_keyset(Question.objects.all(), self.spec, start_request)

        # Достаём cursor/dir из сгенерированного URL "next" и повторно
        # прогоняем через фасад запроса.
        next_request = self.factory.get("/dashboard/list/question/", data={
            "cursor": _extract_query_param(start_page.urls["next"], "cursor"),
            "dir": "next",
        })
        page2 = paginate_keyset(Question.objects.all(), self.spec, next_request)

        self.assertEqual([q.id for q in page2.items], [self.questions[2].id, self.questions[1].id])
        self.assertTrue(page2.has_prev)
        self.assertTrue(page2.has_next)  # q0 остаётся

    def test_last_page(self):
        request = self._get(dir="last")
        page = paginate_keyset(Question.objects.all(), self.spec, request)

        self.assertEqual([q.id for q in page.items], [self.questions[0].id])
        self.assertFalse(page.has_next)
        self.assertTrue(page.has_prev)  # 5 записей, page_size=2 — до последней есть страницы

    def test_prev_reconstructs_previous_page(self):
        start_page = paginate_keyset(Question.objects.all(), self.spec, self._get())
        next_request = self.factory.get("/dashboard/list/question/", data={
            "cursor": _extract_query_param(start_page.urls["next"], "cursor"),
            "dir": "next",
        })
        page2 = paginate_keyset(Question.objects.all(), self.spec, next_request)

        prev_request = self.factory.get("/dashboard/list/question/", data={
            "cursor": _extract_query_param(page2.urls["prev"], "cursor"),
            "dir": "prev",
        })
        page1_again = paginate_keyset(Question.objects.all(), self.spec, prev_request)

        self.assertEqual(
            [q.id for q in page1_again.items],
            [q.id for q in start_page.items],
        )


class TieBreakTests(KeysetEngineTestCase):
    """
    Составной Q(sort_field=X, id__op=Y) — корректность при совпадающих
    значениях sort_field (created), различие только по id.
    """

    def setUp(self):
        super().setUp()
        self.questions = self._make_questions(5)  # q0..q4, created растёт с id
        # q5 получает created ТОЧНО КАК у q4, но id у q5 БОЛЬШЕ (создан позже).
        q5 = Question.objects.create(test=self.test_obj, text="q5")
        Question.objects.filter(pk=q5.pk).update(created=self.questions[4].created)
        q5.refresh_from_db()
        self.q5 = q5
        self.spec = _spec(sort_field="created", sort_direction="desc", page_size=2)

    def test_tie_break_orders_by_id_desc_among_equal_created(self):
        # desc-порядок: при равном created — больший id раньше.
        page1 = paginate_keyset(Question.objects.all(), self.spec, self._get())
        self.assertEqual([q.id for q in page1.items], [self.q5.id, self.questions[4].id])

    def test_tie_break_does_not_duplicate_or_skip_across_pages(self):
        page1 = paginate_keyset(Question.objects.all(), self.spec, self._get())
        next_request = self.factory.get("/dashboard/list/question/", data={
            "cursor": _extract_query_param(page1.urls["next"], "cursor"),
            "dir": "next",
        })
        page2 = paginate_keyset(Question.objects.all(), self.spec, next_request)

        # q4 был последним на странице 1 (created совпадает с q5, но id
        # меньше) — на странице 2 не должно быть ни q5, ни q4 повторно.
        page2_ids = [q.id for q in page2.items]
        self.assertNotIn(self.q5.id, page2_ids)
        self.assertNotIn(self.questions[4].id, page2_ids)
        self.assertEqual(page2_ids, [self.questions[3].id, self.questions[2].id])


class SimpleIdComparisonTests(KeysetEngineTestCase):
    """sort_field="id" — без составного Q, простое id__lt/id__gt."""

    def setUp(self):
        super().setUp()
        self.questions = self._make_questions(5)
        self.spec = _spec(sort_field="id", sort_direction="asc", page_size=2)

    def test_full_traversal_matches_plain_order_by_id(self):
        expected_ids = [q.id for q in Question.objects.order_by("id")]

        collected = []
        request = self._get()
        page = paginate_keyset(Question.objects.all(), self.spec, request)
        collected.extend(q.id for q in page.items)

        while page.has_next:
            next_request = self.factory.get("/dashboard/list/question/", data={
                "cursor": _extract_query_param(page.urls["next"], "cursor"),
                "dir": "next",
            })
            page = paginate_keyset(Question.objects.all(), self.spec, next_request)
            collected.extend(q.id for q in page.items)

        self.assertEqual(collected, expected_ids)


class FallbackSafetyTests(KeysetEngineTestCase):
    """Невалидный курсор / расхождение фингерпринта / пустая выборка."""

    def setUp(self):
        super().setUp()
        self.questions = self._make_questions(5)
        self.spec = _spec(sort_field="created", sort_direction="desc", page_size=2)

    def test_garbage_cursor_falls_back_to_start_page(self):
        request = self._get(cursor="not-a-real-token", dir="next")
        page = paginate_keyset(Question.objects.all(), self.spec, request)

        start_page = paginate_keyset(Question.objects.all(), self.spec, self._get())
        self.assertEqual([q.id for q in page.items], [q.id for q in start_page.items])

    def test_fingerprint_mismatch_falls_back_to_start_page(self):
        # Курсор подписан валидно, но с ЗАВЕДОМО чужим fingerprint фильтров —
        # при текущих (пустых) фильтрах он не совпадёт.
        bogus_cursor = encode_cursor(
            sort_value=str(self.questions[3].created),
            id_value=self.questions[3].id,
            direction="next",
            filters_fingerprint="deadbeef-not-the-real-fingerprint",
        )
        request = self._get(cursor=bogus_cursor, dir="next")
        page = paginate_keyset(Question.objects.all(), self.spec, request)

        start_page = paginate_keyset(Question.objects.all(), self.spec, self._get())
        self.assertEqual([q.id for q in page.items], [q.id for q in start_page.items])

    def test_invalid_dir_falls_back_to_start(self):
        request = self._get(dir="something-weird")
        page = paginate_keyset(Question.objects.all(), self.spec, request)
        self.assertFalse(page.has_prev)

    def test_empty_queryset_returns_empty_page_without_error(self):
        Question.objects.all().delete()
        request = self._get()
        page = paginate_keyset(Question.objects.all(), self.spec, request)

        self.assertEqual(page.items, [])
        self.assertFalse(page.has_prev)
        self.assertFalse(page.has_next)
        self.assertIsNone(page.urls["next"])
        self.assertIsNone(page.urls["prev"])


class UrlBuildingTests(KeysetEngineTestCase):
    """Ссылки сохраняют произвольные GET-параметры (задел на будущие фильтры)."""

    def setUp(self):
        super().setUp()
        self._make_questions(5)
        self.spec = _spec(sort_field="created", sort_direction="desc", page_size=2)

    def test_urls_preserve_extra_query_params(self):
        request = self._get(period="7")
        page = paginate_keyset(Question.objects.all(), self.spec, request)

        self.assertIn("period=7", page.urls["next"])


def _extract_query_param(url: str, key: str) -> str:
    """Мини-хэлпер для тестов: достаёт значение query-параметра из URL."""
    from urllib.parse import parse_qs, urlparse
    parsed = parse_qs(urlparse(url).query)
    return parsed[key][0]