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