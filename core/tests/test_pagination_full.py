"""
core/tests/test_pagination_full.py
──────────────────────────────────────────────────────────────────────────
Комплексные тесты пагинации дашборда: Keyset Engine, Offset Engine,
facade и реестр (registry) — для КАЖДОГО списка, зарегистрированного в
LIST_REGISTRY, а не только для одной "показательной" модели.

Существующие тесты (core/tests/test_pagination_tokens.py,
core/tests/test_keyset_engine.py) проверяют механику курсоров и общий
Keyset Engine на примере одной модели (Question). Этот файл добавляет:

  1. RegistrySpecConsistencyTests
         Реестр сам по себе непротиворечив: допустимые значения engine,
         page_size > 0, sort_direction валиден, а sort_field для
         keyset-списков реально существует как поле модели (иначе
         __lt/__gt в keyset_engine упадёт в рантайме, а не на старте).

  2. OffsetEngineUnitTests
         offset_engine.paginate_offset() напрямую, без HTTP: пустой
         queryset, точный page_size, page_size+1, мусорный/отрицательный/
         нулевой/дробный/огромный ?page=, сохранение доп. GET-параметров.

  3. KeysetEngineAllListsTests
         paginate_keyset() прогоняется для КАЖДОГО keyset-списка реестра
         на его РЕАЛЬНЫХ данных (subject/potok/quiz/question/variant/
         selfctg/selfquestion/user/result) с уменьшенным page_size:
           - полный обход вперёд без дублей и пропусков;
           - "last" совпадает с последней страницей прямого обхода;
           - обратный обход (prev) воспроизводит прямой обход;
           - garbage cursor / invalid dir / fingerprint mismatch -> мягкий
             откат на первую страницу (никогда не исключение);
           - доп. GET-параметры сохраняются в сгенерированных ссылках.
         Плюс sentinel-тест: если в реестр добавят новый keyset-список,
         а сюда забудут дописать проверку — тест упадёт с явным указанием.

  4. OffsetEngineSelfuserIntegrationTests
         Offset-список selfuser (core/dashboard/selfuser_crud.py) через
         тот же offset_engine, что использует facade.

  5. DashboardListViewRBACTests
         HTTP-уровень (Client + urls.py): студент получает redirect на
         /dashboard/list/<tip>/ для КАЖДОГО tip, даже с мусорными cursor/
         dir/page в query string; админ получает 200 для каждого списка
         и переживает те же мусорные параметры без 500.
"""
from __future__ import annotations

import dataclasses
from datetime import date, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import jwt
from django.conf import settings
from django.test import RequestFactory, SimpleTestCase, TestCase

from core.dashboard.pagination.keyset_engine import paginate_keyset
from core.dashboard.pagination.offset_engine import paginate_offset
from core.dashboard.pagination.registry import LIST_REGISTRY, get_list_spec
from core.dashboard.pagination.tokens import encode_cursor
from core.dashboard.selfuser_crud import _selfuser_queryset
from core.models import Potok, Question, Result, Subject, Test, User, Variant
from core.models.auth import Role
from core.models.self import SelfCtg, SelfQuestion, SelfResult, SelfUser

from django.utils import timezone

def _qp(url: str) -> dict:
    """Достаёт GET-параметры из URL как плоский dict (последнее значение)."""
    parsed = parse_qs(urlparse(url).query)
    return {k: v[0] for k, v in parsed.items()}


# ═══════════════════════════════════════════════════════════════════════════
# 1. Реестр сам по себе непротиворечив
# ═══════════════════════════════════════════════════════════════════════════

class RegistrySpecConsistencyTests(SimpleTestCase):
    """Не требует БД — строит queryset лениво, не исполняя запрос."""

    def test_all_specs_have_valid_engine(self):
        for tip, spec in LIST_REGISTRY.items():
            self.assertIn(spec.engine, ("none", "offset", "keyset"), tip)

    def test_all_specs_have_positive_page_size(self):
        for tip, spec in LIST_REGISTRY.items():
            self.assertGreater(spec.page_size, 0, tip)

    def test_all_specs_have_valid_sort_direction(self):
        for tip, spec in LIST_REGISTRY.items():
            self.assertIn(spec.sort_direction, ("asc", "desc"), tip)

    def test_paginated_specs_declare_sort_field(self):
        for tip, spec in LIST_REGISTRY.items():
            if spec.engine != "none":
                self.assertIsNotNone(spec.sort_field, tip)

    def test_keyset_sort_field_exists_on_underlying_model(self):
        """
        Для keyset-списков sort_field участвует в __lt/__gt-фильтрах —
        если поля нет на модели, это упадёт только при первом реальном
        запросе. Ловим рассинхронизацию заранее, на уровне метаданных.
        """
        for tip, spec in LIST_REGISTRY.items():
            if spec.engine != "keyset":
                continue
            model = spec.queryset_factory().model
            try:
                model._meta.get_field(spec.sort_field)
            except Exception as exc:  # noqa: BLE001 — хотим явный fail с деталями
                self.fail(f"{tip}: sort_field {spec.sort_field!r} отсутствует на {model}: {exc}")

    def test_get_list_spec_unknown_tip_returns_none(self):
        self.assertIsNone(get_list_spec("this_tip_does_not_exist"))


# ═══════════════════════════════════════════════════════════════════════════
# 2. Offset Engine — юнит-тесты движка напрямую
# ═══════════════════════════════════════════════════════════════════════════

class OffsetEngineUnitTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _make_subjects(self, n):
        Subject.objects.bulk_create(
            [Subject(name_uz=f"OFFTEST_{i}") for i in range(n)]
        )
        return Subject.objects.filter(name_uz__startswith="OFFTEST_").order_by("id")

    def test_empty_queryset_does_not_crash(self):
        page = paginate_offset(Subject.objects.none(), self.factory.get("/x"), page_size=5)
        self.assertEqual(page.items, [])
        self.assertEqual(page.total_pages, 1)
        self.assertFalse(page.has_prev)
        self.assertFalse(page.has_next)
        for key in ("start", "prev", "next", "last"):
            self.assertIsNone(page.urls[key])

    def test_exact_page_size_single_page(self):
        qs = self._make_subjects(5)
        page = paginate_offset(qs, self.factory.get("/x"), page_size=5)
        self.assertEqual(len(page.items), 5)
        self.assertEqual(page.total_pages, 1)
        self.assertFalse(page.has_next)
        self.assertFalse(page.has_prev)

    def test_page_size_plus_one_creates_second_page(self):
        qs = self._make_subjects(6)
        page1 = paginate_offset(qs, self.factory.get("/x"), page_size=5)
        self.assertEqual(len(page1.items), 5)
        self.assertEqual(page1.total_pages, 2)
        self.assertTrue(page1.has_next)
        self.assertIsNotNone(page1.urls["next"])

        page2 = paginate_offset(qs, self.factory.get("/x", {"page": "2"}), page_size=5)
        self.assertEqual(len(page2.items), 1)
        self.assertFalse(page2.has_next)
        self.assertTrue(page2.has_prev)

        ids_p1 = {s.id for s in page1.items}
        ids_p2 = {s.id for s in page2.items}
        self.assertEqual(len(ids_p1 & ids_p2), 0, "страницы не должны пересекаться")
        self.assertEqual(ids_p1 | ids_p2, set(qs.values_list("id", flat=True)))

    def test_garbage_page_falls_back_to_first(self):
        qs = self._make_subjects(6)
        for bad in ("abc", "", "!!!not-a-number###"):
            page = paginate_offset(qs, self.factory.get("/x", {"page": bad}), page_size=5)
            self.assertEqual(page.current_page, 1, f"page={bad!r}")

    def test_missing_page_param_defaults_to_first(self):
        qs = self._make_subjects(6)
        page = paginate_offset(qs, self.factory.get("/x"), page_size=5)
        self.assertEqual(page.current_page, 1)

    def test_negative_and_zero_page_falls_back_to_first(self):
        qs = self._make_subjects(6)
        for bad in ("-5", "0", "-1"):
            page = paginate_offset(qs, self.factory.get("/x", {"page": bad}), page_size=5)
            self.assertEqual(page.current_page, 1, f"page={bad!r}")

    def test_float_page_falls_back_to_first(self):
        qs = self._make_subjects(6)
        page = paginate_offset(qs, self.factory.get("/x", {"page": "1.5"}), page_size=5)
        self.assertEqual(page.current_page, 1)

    def test_page_beyond_range_clamped_to_last(self):
        qs = self._make_subjects(6)
        page = paginate_offset(qs, self.factory.get("/x", {"page": "999999"}), page_size=5)
        self.assertEqual(page.current_page, page.total_pages)
        self.assertEqual(page.current_page, 2)

    def test_extra_query_params_preserved_in_urls(self):
        qs = self._make_subjects(6)
        page = paginate_offset(qs, self.factory.get("/x", {"zzz_extra": "1"}), page_size=5)
        self.assertIn("zzz_extra=1", page.urls["next"])

    def test_urls_absent_on_single_page_result(self):
        qs = self._make_subjects(3)
        page = paginate_offset(qs, self.factory.get("/x"), page_size=10)
        for key in ("start", "prev", "next", "last"):
            self.assertIsNone(page.urls[key], key)

    def test_page_size_boundary_exact_multiple(self):
        """10 строк, page_size=5 -> ровно 2 полные страницы, без хвоста."""
        qs = self._make_subjects(10)
        page1 = paginate_offset(qs, self.factory.get("/x"), page_size=5)
        page2 = paginate_offset(qs, self.factory.get("/x", {"page": "2"}), page_size=5)
        self.assertEqual(len(page1.items), 5)
        self.assertEqual(len(page2.items), 5)
        self.assertEqual(page1.total_pages, 2)
        self.assertFalse(page2.has_next)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Keyset Engine — все зарегистрированные списки, на их реальных данных
# ═══════════════════════════════════════════════════════════════════════════

def _seed_subject(n):
    Subject.objects.bulk_create([Subject(name_uz=f"KSTEST_subject_{i}") for i in range(n)])
    ids = list(Subject.objects.filter(name_uz__startswith="KSTEST_subject_").values_list("id", flat=True))
    base = timezone.now()
    for offset, pk in enumerate(ids):
        Subject.objects.filter(pk=pk).update(created=base - timedelta(seconds=offset))


def _seed_potok(n):
    for i in range(n):
        Potok.objects.create(
            start=date.today() - timedelta(days=i),
            end=date.today() + timedelta(days=30),
        )


def _seed_quiz(n):
    base = timezone.now()
    for i in range(n):
        t = Test.objects.create()
        Test.objects.filter(pk=t.pk).update(created=base - timedelta(seconds=i))


def _seed_question(n):
    t = Test.objects.create()
    base = timezone.now()
    for i in range(n):
        q = Question.objects.create(test=t, text=f"KSTEST_q_{i}")
        Question.objects.filter(pk=q.pk).update(created=base - timedelta(seconds=i))


def _seed_variant(n):
    t = Test.objects.create()
    q = Question.objects.create(test=t, text="KSTEST_parent_question")
    for i in range(n):
        Variant.objects.create(question=q, text=f"KSTEST_v_{i}")


def _seed_selfctg(n):
    SelfCtg.objects.bulk_create([SelfCtg(name_uz=f"KSTEST_ctg_{i}") for i in range(n)])
    ids = list(SelfCtg.objects.filter(name_uz__startswith="KSTEST_ctg_").values_list("id", flat=True))
    base = timezone.now()
    for offset, pk in enumerate(ids):
        SelfCtg.objects.filter(pk=pk).update(created=base - timedelta(seconds=offset))


def _seed_selfquestion(n):
    for i in range(n):
        SelfQuestion.objects.create(text=f"KSTEST_sq_{i}")


def _seed_user(n):
    for i in range(n):
        User.objects.create_user(
            username=f"kstest_user_{i}", password="pagtest123", role=Role.STUDENT
        )


def _seed_result(n):
    author = User.objects.create_user(username="kstest_result_author", password="pagtest123", role=Role.STUDENT)
    t = Test.objects.create()
    base = timezone.now()
    for i in range(n):
        r = Result.objects.create(user=author, test=t, result=i, foyiz=i, totalQuestions=10)
        Result.objects.filter(pk=r.pk).update(created=base - timedelta(seconds=i))

_SEEDERS = {
    "subject": _seed_subject,
    "potok": _seed_potok,
    "quiz": _seed_quiz,
    "question": _seed_question,
    "variant": _seed_variant,
    "selfctg": _seed_selfctg,
    "selfquestion": _seed_selfquestion,
    "user": _seed_user,
    "result": _seed_result,
}


class KeysetEngineAllListsTests(TestCase):
    """
    Для каждого keyset-списка из реестра: реальный queryset_factory и
    sort_field, но с уменьшенным (через dataclasses.replace) page_size,
    чтобы 7 созданных строк гарантированно давали 3 страницы (3, 3, 1)
    без раздувания фикстур до дефолтных 20.
    """

    PAGE_SIZE = 3
    ITEM_COUNT = 7

    def setUp(self):
        self.factory = RequestFactory()

    def _spec_for(self, tip):
        spec = get_list_spec(tip)
        self.assertIsNotNone(spec, tip)
        return dataclasses.replace(spec, page_size=self.PAGE_SIZE)

    def _get(self, **params):
        return self.factory.get("/dashboard/list/x/", data=params)

    def _run_full_check(self, tip):
        _SEEDERS[tip](self.ITEM_COUNT)
        spec = self._spec_for(tip)

        db_ids = set(spec.queryset_factory().values_list("id", flat=True))
        self.assertGreaterEqual(len(db_ids), self.ITEM_COUNT, tip)

        # ── Полный обход вперёд ──────────────────────────────────────────
        forward_pages = []
        seen_ids = []
        page = paginate_keyset(spec.queryset_factory(), spec, self._get())
        guard = 0
        while True:
            guard += 1
            self.assertLess(guard, 50, f"{tip}: подозрение на бесконечный цикл обхода")
            ids = [item.pk for item in page.items]
            forward_pages.append(ids)
            seen_ids.extend(ids)
            if not page.has_next:
                break
            page = paginate_keyset(
                spec.queryset_factory(), spec, self._get(**_qp(page.urls["next"]))
            )

        self.assertEqual(len(seen_ids), len(set(seen_ids)), f"{tip}: дубли между страницами")
        self.assertEqual(set(seen_ids), db_ids, f"{tip}: обход пропустил/добавил лишние строки")

        for p in forward_pages[:-1]:
            self.assertEqual(len(p), self.PAGE_SIZE, f"{tip}: не-последняя страница неполна")
        self.assertGreaterEqual(len(forward_pages), 2, f"{tip}: недостаточно страниц для проверки last/prev")

        # ── dir=last совпадает с последней страницей прямого обхода ─────
        last_page = paginate_keyset(spec.queryset_factory(), spec, self._get(dir="last"))
        self.assertEqual(
            [item.pk for item in last_page.items], forward_pages[-1], f"{tip}: dir=last расходится с обходом"
        )
        self.assertFalse(last_page.has_next, f"{tip}: last-страница не должна иметь has_next")

        # ── Обратный обход воспроизводит прямой обход ────────────────────
        backward_pages = [[item.pk for item in last_page.items]]
        cur = last_page
        guard = 0
        while cur.has_prev:
            guard += 1
            self.assertLess(guard, 50, f"{tip}: подозрение на бесконечный цикл обратного обхода")
            cur = paginate_keyset(spec.queryset_factory(), spec, self._get(**_qp(cur.urls["prev"])))
            backward_pages.append([item.pk for item in cur.items])
        backward_pages.reverse()
        self.assertEqual(backward_pages, forward_pages, f"{tip}: обратный обход не совпал с прямым")

        # ── Fallback: мусорный cursor ─────────────────────────────────────
        garbage_page = paginate_keyset(
            spec.queryset_factory(), spec, self._get(cursor="not-a-real-token-xyz", dir="next")
        )
        self.assertEqual(
            [item.pk for item in garbage_page.items], forward_pages[0], f"{tip}: мусорный cursor не откатился на старт"
        )

        # ── Fallback: невалидный dir ────────────────────────────────────
        baddir_page = paginate_keyset(spec.queryset_factory(), spec, self._get(dir="totally-invalid"))
        self.assertEqual(
            [item.pk for item in baddir_page.items], forward_pages[0], f"{tip}: невалидный dir не откатился на старт"
        )

        # ── Fallback: валидная подпись, но чужой filters_fingerprint ─────
        bogus_cursor = encode_cursor(
            sort_value=1, id_value=1, direction="next", filters_fingerprint="deadbeef-wrong-fp"
        )
        fp_page = paginate_keyset(spec.queryset_factory(), spec, self._get(cursor=bogus_cursor, dir="next"))
        self.assertEqual(
            [item.pk for item in fp_page.items], forward_pages[0], f"{tip}: fingerprint-mismatch не откатился на старт"
        )

        # ── Доп. GET-параметры сохраняются в сгенерированных ссылках ────
        extra_page = paginate_keyset(spec.queryset_factory(), spec, self._get(zzz_extra="1"))
        if extra_page.urls.get("next"):
            self.assertIn("zzz_extra=1", extra_page.urls["next"], tip)

        # ── has_prev/has_next на границах ─────────────────────────────────
        start_page = paginate_keyset(spec.queryset_factory(), spec, self._get())
        self.assertFalse(start_page.has_prev, f"{tip}: у первой страницы не должно быть has_prev")
        self.assertIsNone(start_page.urls["start"], tip)
        self.assertIsNone(start_page.urls["prev"], tip)

    def test_subject(self):
        self._run_full_check("subject")

    def test_potok(self):
        self._run_full_check("potok")

    def test_quiz(self):
        self._run_full_check("quiz")

    def test_question(self):
        self._run_full_check("question")

    def test_variant(self):
        self._run_full_check("variant")

    def test_selfctg(self):
        self._run_full_check("selfctg")

    def test_selfquestion(self):
        self._run_full_check("selfquestion")

    def test_user(self):
        self._run_full_check("user")

    def test_result(self):
        self._run_full_check("result")

    def test_all_registered_keyset_tips_are_covered_by_this_suite(self):
        """
        Защита от рассинхронизации: если в LIST_REGISTRY добавят новый
        keyset-список, а тест для него забудут написать выше — этот тест
        падает с явным указанием, какого tip не хватает, вместо того
        чтобы молча оставить список непротестированным.
        """
        keyset_tips = {tip for tip, spec in LIST_REGISTRY.items() if spec.engine == "keyset"}
        self.assertEqual(keyset_tips, set(_SEEDERS.keys()))


# ═══════════════════════════════════════════════════════════════════════════
# 4. Offset Engine — интеграция со списком selfuser
# ═══════════════════════════════════════════════════════════════════════════

class OffsetEngineSelfuserIntegrationTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _seed(self, n):
        ctg = SelfCtg.objects.create(name_uz="OFFSU_ctg")
        for i in range(n):
            su = SelfUser.objects.create(first_name=f"OFFSU_{i}", last_name="Test")
            SelfResult.objects.create(user=su, ctg=ctg, score=i, foiz=i * 10, totalQuestions=10)

    def test_full_traversal_covers_all_rows_without_duplicates(self):
        self._seed(7)
        qs = _selfuser_queryset()

        page1 = paginate_offset(qs, self.factory.get("/x"), page_size=3)
        self.assertEqual(len(page1.items), 3)
        self.assertTrue(page1.has_next)

        page2 = paginate_offset(qs, self.factory.get("/x", {"page": "2"}), page_size=3)
        self.assertEqual(len(page2.items), 3)

        page3 = paginate_offset(qs, self.factory.get("/x", {"page": "3"}), page_size=3)
        self.assertEqual(len(page3.items), 1)
        self.assertFalse(page3.has_next)

        seen_ids = {u.id for u in page1.items} | {u.id for u in page2.items} | {u.id for u in page3.items}
        db_ids = set(SelfUser.objects.filter(first_name__startswith="OFFSU_").values_list("id", flat=True))
        self.assertEqual(seen_ids, db_ids)

    def test_users_without_attempts_do_not_crash_ordering(self):
        """last_attempt=None (пользователь без единой попытки) должен уйти
        в конец сортировки (nulls_last), а не сломать запрос."""
        SelfUser.objects.create(first_name="OFFSU_no_attempts", last_name="Nobody")
        self._seed(2)
        qs = _selfuser_queryset()
        page = paginate_offset(qs, self.factory.get("/x"), page_size=10)
        self.assertEqual(len(page.items), 3)
        self.assertEqual(page.items[-1].first_name, "OFFSU_no_attempts")

    def test_garbage_page_on_selfuser_list_falls_back_gracefully(self):
        self._seed(5)
        qs = _selfuser_queryset()
        for bad in ("abc", "-1", "0", "999"):
            page = paginate_offset(qs, self.factory.get("/x", {"page": bad}), page_size=2)
            self.assertGreaterEqual(page.current_page, 1)
            self.assertLessEqual(page.current_page, page.total_pages)


# ═══════════════════════════════════════════════════════════════════════════
# 5. HTTP-уровень: RBAC + устойчивость к мусорным параметрам на всех tip
# ═══════════════════════════════════════════════════════════════════════════

_REDIS_MOCKS = [
    patch("core.auth_jwt.middleware.AuthRedisService.is_token_revoked", return_value=False),
    patch("core.auth_jwt.middleware.AuthRedisService.validate_session", return_value=True),
    patch("core.auth_jwt.services.AuthRedisService.is_token_revoked", return_value=False),
    patch("core.auth_jwt.services.AuthRedisService.validate_session", return_value=True),
    patch("core.dashboard.home.AuthRedisService.is_dashboard_authorized", return_value=True),
]


def _tip_url(tip: str) -> str:
    """selfuser обслуживается по адресу /dashboard/list/selfresult/ (см.
    core/dashboard/list.py::dlist), а не по своему ключу реестра."""
    return "selfresult" if tip == "selfuser" else tip


class DashboardListViewRBACTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for p in _REDIS_MOCKS:
            p.start()

    @classmethod
    def tearDownClass(cls):
        for p in _REDIS_MOCKS:
            p.stop()
        super().tearDownClass()

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="pg_admin_rbac", password="pagtest123", role=Role.ADMIN
        )
        cls.student = User.objects.create_user(
            username="pg_student_rbac", password="pagtest123", role=Role.STUDENT
        )

    def _client_for(self, user):
        c = self.client_class()
        payload = {
            "sub": str(user.id),
            "device_id": "pgtest-device",
            "jti": f"pgtest-jti-{user.id}",
            "type": "access",
        }
        token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
        c.cookies[settings.JWT_ACCESS_COOKIE_NAME] = token
        return c

    def test_student_blocked_from_every_registered_list(self):
        c = self._client_for(self.student)
        for tip in LIST_REGISTRY:
            resp = c.get(f"/dashboard/list/{_tip_url(tip)}/")
            self.assertEqual(resp.status_code, 302, tip)

    def test_student_blocked_even_with_garbage_pagination_params(self):
        c = self._client_for(self.student)
        for tip in LIST_REGISTRY:
            resp = c.get(f"/dashboard/list/{_tip_url(tip)}/?cursor=garbage&dir=whatever&page=abc")
            self.assertEqual(resp.status_code, 302, tip)

    def test_admin_gets_200_for_every_registered_list(self):
        c = self._client_for(self.admin)
        for tip in LIST_REGISTRY:
            resp = c.get(f"/dashboard/list/{_tip_url(tip)}/")
            self.assertEqual(resp.status_code, 200, tip)

    def test_admin_survives_garbage_pagination_params_on_every_list(self):
        c = self._client_for(self.admin)
        garbage_suffixes = (
            "?cursor=garbage&dir=next",
            "?dir=totally-invalid",
            "?page=-999",
            "?page=abc",
            "?page=99999999",
            "?cursor=&dir=prev",
        )
        for tip in LIST_REGISTRY:
            url = f"/dashboard/list/{_tip_url(tip)}/"
            for suffix in garbage_suffixes:
                resp = c.get(url + suffix)
                self.assertEqual(resp.status_code, 200, f"{tip}{suffix}")

    def test_unknown_tip_does_not_500(self):
        c = self._client_for(self.admin)
        resp = c.get("/dashboard/list/this_tip_does_not_exist/")
        self.assertEqual(resp.status_code, 200)