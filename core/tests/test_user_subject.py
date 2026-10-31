"""
core/tests/test_user_subject.py — ученик + предмет (subject).

Покрытие:
  1. Форма создания (/form/user/): предмет в контексте, создание ученика
     с предметом, обязательность предмета для роли «Ученик», мусорный
     subject -> 400, админ без предмета допустим, тёзки -> 400.
  2. Форма редактирования: смена предмета, поле не пришло -> предмет
     не трогаем, у ученика пустой предмет -> 400.
  3. Страница логина: в списке только активные ученики с предметом.
"""
from unittest.mock import patch

import jwt
from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from core.models import Subject, User
from core.models.auth import Role

_REDIS_MOCKS = [
    patch("core.auth_jwt.middleware.AuthRedisService.is_token_revoked", return_value=False),
    patch("core.auth_jwt.middleware.AuthRedisService.validate_session", return_value=True),
    patch("core.auth_jwt.services.AuthRedisService.is_token_revoked", return_value=False),
    patch("core.auth_jwt.services.AuthRedisService.validate_session", return_value=True),
    patch("core.dashboard.home.AuthRedisService.is_dashboard_authorized", return_value=True),
]


def _form_data(**overrides):
    data = {
        "first_name": "Ivan",
        "last_name": "Petrov",
        "second_name": "Ivanovich",
        "password": "pass12345",
        "potok": "",
        "subject": "",
        "role": str(Role.STUDENT),
        "lang": "ru",
    }
    data.update(overrides)
    return data


class _AdminMixin:
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
            username="subj_admin", password="testpass123",
            role=Role.ADMIN, is_active=True,
        )
        cls.math = Subject.objects.create(name_uz="Matematika", name_ru="Математика", name_en="Math")
        cls.physics = Subject.objects.create(name_uz="Fizika", name_ru="Физика", name_en="Physics")

    def setUp(self):
        token = jwt.encode(
            {"sub": str(self.admin.id), "device_id": "tst",
             "jti": "tst-jti", "type": "access"},
            settings.SECRET_KEY, algorithm="HS256",
        )
        self.client.cookies[settings.JWT_ACCESS_COOKIE_NAME] = token


# ═══════════════════════════════════════════════════════════════════════════
# 1. Форма создания
# ═══════════════════════════════════════════════════════════════════════════

class CreateUserFormTests(_AdminMixin, TestCase):
    url_name = "userform"

    def _post(self, **overrides):
        return self.client.post(reverse(self.url_name), _form_data(**overrides))

    def test_get_contains_subjects_list(self):
        resp = self.client.get(reverse(self.url_name))
        self.assertEqual(resp.status_code, 200)
        subjects = set(resp.context["subjects"].values_list("id", flat=True))
        self.assertEqual(subjects, {self.math.id, self.physics.id})
        self.assertContains(resp, 'name="subject"')

    def test_student_created_with_subject(self):
        resp = self._post(subject=str(self.math.id))
        self.assertEqual(resp.status_code, 200)

        user = User.objects.get(last_name="Petrov")
        self.assertEqual(user.subject_id, self.math.id)
        self.assertEqual(user.role, Role.STUDENT)

    def test_success_response_still_has_subjects_in_context(self):
        resp = self._post(subject=str(self.math.id))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["subjects"].count(), 2)

    def test_student_without_subject_rejected(self):
        resp = self._post(subject="")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(User.objects.filter(last_name="Petrov").exists())
        self.assertIn("предмет", resp.context["error"].lower())
        # список предметов не пропал после ошибки
        self.assertEqual(resp.context["subjects"].count(), 2)

    def test_garbage_subject_rejected_without_500(self):
        for bogus in ("abc", "999999", "-1", "1;DROP"):
            resp = self._post(subject=bogus)
            self.assertEqual(resp.status_code, 400, bogus)
        self.assertFalse(User.objects.filter(last_name="Petrov").exists())

    def test_admin_may_be_created_without_subject(self):
        resp = self._post(role=str(Role.ADMIN), subject="")
        self.assertEqual(resp.status_code, 200)
        user = User.objects.get(last_name="Petrov")
        self.assertIsNone(user.subject_id)
        self.assertEqual(user.role, Role.ADMIN)

    def test_missing_role_rejected(self):
        resp = self._post(role="", subject=str(self.math.id))
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(User.objects.filter(last_name="Petrov").exists())

    def test_duplicate_fio_rejected_with_clear_message(self):
        self._post(subject=str(self.math.id))
        before = User.objects.count()

        resp = self._post(subject=str(self.physics.id))

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(User.objects.count(), before)
        self.assertIn("уже существует", resp.context["error"])

    def test_error_keeps_entered_data(self):
        resp = self._post(subject="")
        self.assertEqual(resp.context["user_data"]["first_name"], "Ivan")


# ═══════════════════════════════════════════════════════════════════════════
# 2. Форма редактирования
# ═══════════════════════════════════════════════════════════════════════════

class EditUserSubjectTests(_AdminMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.student = User.objects.create_user(
            username="edit_student", password="pass12345",
            role=Role.STUDENT, name="Anna", last_name="Sidorova",
            second_name="", subject=self.math,
        )
        self.url = reverse("action", kwargs={
            "status": "edit", "path": "user", "pk": self.student.pk,
        })

    def _edit_data(self, **overrides):
        data = {
            "first_name": "Anna",
            "last_name": "Sidorova",
            "second_name": "",
            "position": "",
            "company_name": "",
            "potok": "",
            "subject": str(self.math.id),
            "role": str(Role.STUDENT),
            "lang": "ru",
            "password": "",
        }
        data.update(overrides)
        return data

    def test_get_contains_subjects_and_preselected_current(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["subjects"].count(), 2)
        html = resp.content.decode("utf-8")
        self.assertRegex(html, rf'value="{self.math.id}"\s*selected')

    def test_subject_can_be_changed(self):
        resp = self.client.post(self.url, self._edit_data(subject=str(self.physics.id)))
        self.assertEqual(resp.status_code, 302)
        self.student.refresh_from_db()
        self.assertEqual(self.student.subject_id, self.physics.id)

    def test_subject_kept_when_field_not_sent(self):
        data = self._edit_data()
        del data["subject"]
        resp = self.client.post(self.url, data)
        self.assertEqual(resp.status_code, 302)
        self.student.refresh_from_db()
        self.assertEqual(self.student.subject_id, self.math.id)

    def test_student_cannot_be_saved_with_empty_subject(self):
        resp = self.client.post(self.url, self._edit_data(subject=""))
        self.assertEqual(resp.status_code, 400)
        self.student.refresh_from_db()
        self.assertEqual(self.student.subject_id, self.math.id)  # не обнулился
        self.assertEqual(resp.context["subjects"].count(), 2)

    def test_garbage_subject_rejected(self):
        for bogus in ("abc", "999999"):
            resp = self.client.post(self.url, self._edit_data(subject=bogus))
            self.assertEqual(resp.status_code, 400, bogus)
        self.student.refresh_from_db()
        self.assertEqual(self.student.subject_id, self.math.id)

    def test_admin_role_may_have_empty_subject(self):
        resp = self.client.post(
            self.url, self._edit_data(role=str(Role.ADMIN), subject="")
        )
        self.assertEqual(resp.status_code, 302)
        self.student.refresh_from_db()
        self.assertIsNone(self.student.subject_id)

    def test_password_unchanged_when_empty(self):
        old_hash = self.student.password
        self.client.post(self.url, self._edit_data(password=""))
        self.student.refresh_from_db()
        self.assertEqual(self.student.password, old_hash)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Страница логина
# ═══════════════════════════════════════════════════════════════════════════

class LoginPageStudentListTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.math = Subject.objects.create(name_uz="Matematika")
        cls.good = User.objects.create_user(
            username="login_good", password="x", role=Role.STUDENT,
            name="Good", last_name="Student", subject=cls.math,
        )
        cls.no_subject = User.objects.create_user(
            username="login_nosubj", password="x", role=Role.STUDENT,
            name="No", last_name="Subject", subject=None,
        )
        cls.inactive = User.objects.create_user(
            username="login_inactive", password="x", role=Role.STUDENT,
            name="In", last_name="Active", subject=cls.math, is_active=False,
        )
        cls.finished = User.objects.create_user(
            username="login_finished", password="x", role=Role.STUDENT,
            name="Fin", last_name="Ished", subject=cls.math, is_result=True,
        )
        cls.admin = User.objects.create_user(
            username="login_admin", password="x", role=Role.ADMIN,
            name="Ad", last_name="Min", subject=cls.math,
        )

    def _users_in_context(self):
        resp = self.client.get("/ru/login/")
        self.assertEqual(resp.status_code, 200)
        return set(resp.context["u"].values_list("id", flat=True)), resp

    def test_only_active_students_with_subject_listed(self):
        ids, _ = self._users_in_context()
        self.assertEqual(ids, {self.good.id})

    def test_excluded_users(self):
        ids, _ = self._users_in_context()
        for u in (self.no_subject, self.inactive, self.finished, self.admin):
            self.assertNotIn(u.id, ids, u.username)

    def test_subjects_passed_to_template(self):
        _, resp = self._users_in_context()
        self.assertIn(self.math.id, set(resp.context["c"].values_list("id", flat=True)))

    def test_student_created_via_form_appears_on_login(self):
        """Сквозной сценарий: создали через модель так же, как форма -> виден на логине."""
        new_student = User.objects.create_user(
            username=None, password="1234", role=Role.STUDENT,
            name="Nuri", last_name="Karimov", second_name="",
            subject_id=self.math.id,
        )
        ids, _ = self._users_in_context()
        self.assertIn(new_student.id, ids)