"""
core/tests/test_delete_csrf.py — удаление в дашборде только через POST + CSRF.

  1. GET на /action/delete/... ничего не удаляет и редиректит на список.
  2. POST без CSRF-токена -> 403, объект на месте.
  3. POST с валидным токеном -> удаляет.
  4. Список рендерит <form method="post">, а не GET-ссылку на delete.
"""
from unittest.mock import patch

import jwt
from django.conf import settings
from django.test import Client, TestCase
from django.urls import reverse

from core.models import Subject
from core.models.auth import Role, User
from core.models.self import SelfResult, SelfUser

_REDIS_MOCKS = [
    patch("core.auth_jwt.middleware.AuthRedisService.is_token_revoked", return_value=False),
    patch("core.auth_jwt.middleware.AuthRedisService.validate_session", return_value=True),
    patch("core.auth_jwt.services.AuthRedisService.is_token_revoked", return_value=False),
    patch("core.auth_jwt.services.AuthRedisService.validate_session", return_value=True),
    patch("core.dashboard.home.AuthRedisService.is_dashboard_authorized", return_value=True),
]

_CSRF = "x" * 32  # валидный по формату секрет (CSRF_SECRET_LENGTH)


class DeletePostOnlyTests(TestCase):
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
            username="csrf_admin", password="testpass123",
            role=Role.ADMIN, is_active=True,
        )

    def _client(self, enforce_csrf=False) -> Client:
        c = Client(enforce_csrf_checks=enforce_csrf)
        token = jwt.encode(
            {"sub": str(self.admin.id), "device_id": "tst",
             "jti": "tst-jti", "type": "access"},
            settings.SECRET_KEY, algorithm="HS256",
        )
        c.cookies[settings.JWT_ACCESS_COOKIE_NAME] = token
        return c

    def _url(self, path, pk):
        return reverse("action", kwargs={"status": "delete", "path": path, "pk": pk})

    # ── 1. GET не удаляет ───────────────────────────────────────────
    def test_get_does_not_delete_and_redirects_to_list(self):
        subject = Subject.objects.create(name_uz="S")
        resp = self._client().get(self._url("subject", subject.pk))

        self.assertRedirects(
            resp, reverse("dlist", kwargs={"tip": "subject"}),
            fetch_redirect_response=False,
        )
        self.assertTrue(Subject.objects.filter(pk=subject.pk).exists())

    def test_get_on_selfuser_redirects_to_selfresult_list(self):
        su = SelfUser.objects.create(first_name="A", last_name="B")
        SelfResult.objects.create(user=su, score=1)

        resp = self._client().get(self._url("selfuser", su.pk))

        self.assertRedirects(
            resp, reverse("dlist", kwargs={"tip": "selfresult"}),
            fetch_redirect_response=False,
        )
        self.assertTrue(SelfUser.objects.filter(pk=su.pk).exists())
        self.assertEqual(SelfResult.objects.filter(user=su).count(), 1)

    # ── 2. POST без CSRF-токена -> 403 ──────────────────────────────
    def test_post_without_csrf_token_is_forbidden(self):
        subject = Subject.objects.create(name_uz="S")
        resp = self._client(enforce_csrf=True).post(self._url("subject", subject.pk))

        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Subject.objects.filter(pk=subject.pk).exists())

    # ── 3. POST с токеном удаляет ───────────────────────────────────
    def test_post_with_csrf_token_deletes(self):
        subject = Subject.objects.create(name_uz="S")
        c = self._client(enforce_csrf=True)
        c.cookies[settings.CSRF_COOKIE_NAME] = _CSRF

        resp = c.post(
            self._url("subject", subject.pk),
            {"csrfmiddlewaretoken": _CSRF},
        )

        self.assertRedirects(
            resp, reverse("dlist", kwargs={"tip": "subject"}),
            fetch_redirect_response=False,
        )
        self.assertFalse(Subject.objects.filter(pk=subject.pk).exists())

    def test_post_with_csrf_token_deletes_selfuser_with_history(self):
        su = SelfUser.objects.create(first_name="A", last_name="B")
        SelfResult.objects.create(user=su, score=1)
        c = self._client(enforce_csrf=True)
        c.cookies[settings.CSRF_COOKIE_NAME] = _CSRF

        resp = c.post(self._url("selfuser", su.pk), {"csrfmiddlewaretoken": _CSRF})

        self.assertEqual(resp.status_code, 302)
        self.assertFalse(SelfUser.objects.filter(pk=su.pk).exists())
        self.assertEqual(SelfResult.objects.filter(user_id=su.pk).count(), 0)

    # ── 4. Шаблон: форма POST вместо GET-ссылки ─────────────────────
    def test_list_renders_post_form_not_get_link(self):
        subject = Subject.objects.create(name_uz="S")
        resp = self._client().get(reverse("dlist", kwargs={"tip": "subject"}))
        html = resp.content.decode("utf-8", "replace")

        delete_url = self._url("subject", subject.pk)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(f'action="{delete_url}"', html)
        self.assertNotIn(f'href="{delete_url}"', html)
        self.assertIn("csrfmiddlewaretoken", html)