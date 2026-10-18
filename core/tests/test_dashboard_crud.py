"""
core/tests/test_dashboard_crud.py — проверка чистки файлов при сбое сохранения
Courses (create и edit).

Сценарий: Model.save() реально записывает файл в storage (FileField.pre_save)
и БД-операцию, после чего бросает исключение. Транзакция откатывается, а
view обязан удалить уже записанный файл (путь вида "courses/<uuid>.webp").

MEDIA_ROOT подменяется временной директорией, поэтому реальные media не
затрагиваются. JWT/Redis мокаются так же, как в core/tests/test_self_check.py.
"""
import io
import os
import shutil
import tempfile
from unittest.mock import patch

import jwt
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.media_utils import process_uploaded_image
from core.models import Courses
from core.models.auth import Role, User

from core.dashboard.partners_crud import is_safe_http_url
from core.models import Partners, SelfStudy

def _make_jpg_bytes(color=(120, 80, 200), size=(100, 100)):
    from PIL import Image
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf.read()


def _list_files(root):
    """Множество относительных путей (через '/') всех файлов под root."""
    found = set()
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            rel = os.path.relpath(os.path.join(dirpath, name), root)
            found.add(rel.replace(os.sep, "/"))
    return found


def _save_then_fail(written):
    """
    Патчит Courses.save: настоящий save() (файл записан, SQL выполнен),
    затем исключение. Имя записанного файла кладётся в `written` — это
    доказывает, что файл действительно был на диске, и показывает его
    реальный путь (с upload_to).
    """
    real_save = Courses.save

    def save_then_fail(self, *args, **kwargs):
        real_save(self, *args, **kwargs)
        written.append(self.photo.name)
        raise RuntimeError("simulated failure after file write")

    return patch.object(Courses, "save", save_then_fail)


_REDIS_MOCKS = [
    patch("core.auth_jwt.middleware.AuthRedisService.is_token_revoked", return_value=False),
    patch("core.auth_jwt.middleware.AuthRedisService.validate_session", return_value=True),
    patch("core.auth_jwt.services.AuthRedisService.is_token_revoked", return_value=False),
    patch("core.auth_jwt.services.AuthRedisService.validate_session", return_value=True),
    patch("core.dashboard.home.AuthRedisService.is_dashboard_authorized", return_value=True),
]


class CoursesOrphanFileCleanupTests(TestCase):
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
            username="crud_admin", password="testpass123",
            role=Role.ADMIN, is_active=True,
        )

    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix="crud_media_")
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media_root)
        override.enable()
        self.addCleanup(override.disable)

        payload = {
            "sub": str(self.admin.id), "device_id": "tst",
            "jti": "tst-jti", "type": "access",
        }
        token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
        self.client.cookies[settings.JWT_ACCESS_COOKIE_NAME] = token

    def _upload(self, name="c.jpg"):
        return SimpleUploadedFile(name, _make_jpg_bytes(), content_type="image/jpeg")

    # ── create ───────────────────────────────────────────────────────
    def test_create_courses_cleans_file_when_save_fails_after_write(self):
        written = []
        url = reverse("action_no_pk", kwargs={"status": "create", "path": "courses"})

        with _save_then_fail(written):
            resp = self.client.post(url, {
                "courses_title": "T",
                "courses_name": "N",
                "courses_desc": "D",
                "courses_photo": self._upload(),
            })

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Courses.objects.count(), 0)

        # Файл действительно был записан — по пути с upload_to, а не "<uuid>.webp".
        self.assertEqual(len(written), 1)
        self.assertTrue(written[0].startswith("courses/"), written[0])
        self.assertTrue(written[0].endswith(".webp"), written[0])

        # ...и после обработки ошибки на диске ничего не осталось.
        self.assertEqual(_list_files(self.media_root), set())

    # ── edit ─────────────────────────────────────────────────────────
    def test_edit_courses_cleans_new_file_and_keeps_old_when_save_fails(self):
        old_file = process_uploaded_image(self._upload("old.jpg"))
        course = Courses.objects.create(
            title_uz="Old", name_uz="Old", desc_uz="Old", photo=old_file,
        )
        old_name = course.photo.name
        self.assertEqual(_list_files(self.media_root), {old_name})

        written = []
        url = reverse("action", kwargs={"status": "edit", "path": "courses", "pk": course.pk})

        with _save_then_fail(written):
            resp = self.client.post(url, {
                "courses_title": "New",
                "courses_name": "New",
                "courses_desc": "New",
                "courses_photo": self._upload("new.jpg"),
            })

        self.assertEqual(resp.status_code, 400)

        self.assertEqual(len(written), 1)
        self.assertTrue(written[0].startswith("courses/"), written[0])
        self.assertNotEqual(written[0], old_name)

        # Новый файл удалён, старый на месте.
        self.assertEqual(_list_files(self.media_root), {old_name})

        # Транзакция откатилась: в БД прежние значения и прежнее фото.
        course.refresh_from_db()
        self.assertEqual(course.photo.name, old_name)
        self.assertEqual(course.title_uz, "Old")

class _AdminClientMixin:
    """Общая обвязка: JWT-кука админа, Redis-моки, временный MEDIA_ROOT."""

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
            username="crud_admin2", password="testpass123",
            role=Role.ADMIN, is_active=True,
        )

    def setUp(self):
        self.media_root = tempfile.mkdtemp(prefix="crud_media_")
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media_root)
        override.enable()
        self.addCleanup(override.disable)

        payload = {
            "sub": str(self.admin.id), "device_id": "tst",
            "jti": "tst-jti", "type": "access",
        }
        token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
        self.client.cookies[settings.JWT_ACCESS_COOKIE_NAME] = token

    def _upload(self, name="p.jpg"):
        return SimpleUploadedFile(name, _make_jpg_bytes(), content_type="image/jpeg")


_BAD_LINKS = (
    "javascript:x",
    "JAVASCRIPT:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "ftp://example.com",
    "//example.com",
    "example.com",
    "http://",
    "https:///path",
    "http://:80",
)
_GOOD_LINKS = ("http://example.com", "https://example.com/a?b=1", "HTTPS://Example.com")


class PartnersLinkValidationTests(_AdminClientMixin, TestCase):
    def test_validator_rejects_bad_and_accepts_good(self):
        for link in _BAD_LINKS:
            self.assertFalse(is_safe_http_url(link), link)
        for link in _GOOD_LINKS:
            self.assertTrue(is_safe_http_url(link), link)
        self.assertFalse(is_safe_http_url(""))
        self.assertFalse(is_safe_http_url(None))

    def test_create_rejects_bad_scheme_with_400_and_creates_nothing(self):
        url = reverse("action_no_pk", kwargs={"status": "create", "path": "partners"})
        for link in _BAD_LINKS:
            resp = self.client.post(url, {
                "partners_name": "P", "partners_link": link,
                "partners_photo": self._upload(),
            })
            self.assertEqual(resp.status_code, 400, link)
        self.assertEqual(Partners.objects.count(), 0)
        self.assertEqual(_list_files(self.media_root), set())

    def test_create_accepts_https(self):
        url = reverse("action_no_pk", kwargs={"status": "create", "path": "partners"})
        resp = self.client.post(url, {
            "partners_name": "P", "partners_link": "https://example.com",
            "partners_photo": self._upload(),
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Partners.objects.get().link, "https://example.com")

    def test_edit_rejects_bad_scheme_and_keeps_old_link(self):
        partner = Partners.objects.create(
            name="Old", link="https://old.example.com",
            photo=process_uploaded_image(self._upload("old.jpg")),
        )
        url = reverse("action", kwargs={"status": "edit", "path": "partners", "pk": partner.pk})
        for link in _BAD_LINKS:
            resp = self.client.post(url, {"partners_name": "New", "partners_link": link})
            self.assertEqual(resp.status_code, 400, link)
        partner.refresh_from_db()
        self.assertEqual(partner.link, "https://old.example.com")
        self.assertEqual(partner.name, "Old")

    def test_edit_accepts_http(self):
        partner = Partners.objects.create(
            name="Old", link="https://old.example.com",
            photo=process_uploaded_image(self._upload("old.jpg")),
        )
        url = reverse("action", kwargs={"status": "edit", "path": "partners", "pk": partner.pk})
        resp = self.client.post(url, {"partners_name": "New", "partners_link": "http://new.example.com"})
        self.assertEqual(resp.status_code, 302)
        partner.refresh_from_db()
        self.assertEqual(partner.link, "http://new.example.com")


class SelfStudyStrTests(TestCase):
    def test_str_returns_string(self):
        obj = SelfStudy.objects.create()
        self.assertEqual(str(obj), str(obj.id))
        self.assertIsInstance(str(obj), str)


class DeleteMissingObjectTests(_AdminClientMixin, TestCase):
    def test_delete_nonexistent_returns_404(self):
        for path in ("courses", "teachers", "news", "partners"):
            url = reverse("action", kwargs={"status": "delete", "path": path, "pk": 9999})
            resp = self.client.post(url)
            self.assertEqual(resp.status_code, 404, path)

    def test_delete_existing_partner_still_redirects(self):
        partner = Partners.objects.create(
            name="X", link="https://x.example.com",
            photo=process_uploaded_image(self._upload()),
        )
        url = reverse("action", kwargs={"status": "delete", "path": "partners", "pk": partner.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Partners.objects.filter(pk=partner.pk).exists())
        self.assertEqual(_list_files(self.media_root), set())