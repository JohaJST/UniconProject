"""
core/tests/test_self_check.py ― Integration tests for Self Check CRUD.

Coverage:
  1. Create valid question + answers
  2. needs_review flag when translations are empty
  3. Validation: no correct answer → 400
  4. IDOR protection on answer edit
  5. Delete question cleans image files
"""

import io
from unittest.mock import patch

import jwt
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from core.models.auth import Role, User
from core.models.self import SelfAnswer, SelfQuestion


def _make_jpg_bytes(color=(120, 80, 200), size=(100, 100)):
    from PIL import Image
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf.read()


# Патчи, которые живут на уровне класса — стартуют в setUpClass,
# стопают в tearDownClass.
_REDIS_MOCKS = [
    patch("core.auth_jwt.middleware.AuthRedisService.is_token_revoked", return_value=False),
    patch("core.auth_jwt.middleware.AuthRedisService.validate_session", return_value=True),
    patch("core.auth_jwt.services.AuthRedisService.is_token_revoked", return_value=False),
    patch("core.auth_jwt.services.AuthRedisService.validate_session", return_value=True),
    patch("core.dashboard.home.AuthRedisService.is_dashboard_authorized", return_value=True),
]


class SelfCheckTests(TestCase):
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
            username="testadmin", password="testpass123",
            role=Role.ADMIN, is_active=True,
        )
        cls.other_q = SelfQuestion.objects.create(
            text_uz="Other", text_ru="Other", text_en="Other")
        cls.other_a = SelfAnswer.objects.create(
            question=cls.other_q, text_uz="Other answer",
            text_ru="Other answer", text_en="Other answer", is_correct=True)

    def setUp(self):
        payload = {
            "sub": str(self.admin.id), "device_id": "tst",
            "jti": "tst-jti", "type": "access",
        }
        token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
        self.client.cookies[settings.JWT_ACCESS_COOKIE_NAME] = token

    # ── 1 ──────────────────────────────────────────────────────────
    def test_create_valid_question(self):
        jpg = _make_jpg_bytes()
        img = SimpleUploadedFile("q.jpg", jpg, content_type="image/jpeg")

        data = {
            "question_text": "What is 2+2?",
            "question_text_uz": "2+2 nechiga teng?",
            "question_text_ru": "Skolko budet 2+2?",
            "question_text_en": "What is 2+2?",
            "question_image": img,
            "answer_text_0": "4", "answer_text_0_uz": "4",
            "answer_text_0_ru": "4", "answer_text_0_en": "4",
            "answer_correct_0": "1",
            "answer_text_1": "5", "answer_text_1_uz": "5",
            "answer_text_1_ru": "5", "answer_text_1_en": "5",
        }

        resp = self.client.post(reverse("self_check_create"), data)
        self.assertRedirects(resp, reverse("dlist", kwargs={"tip": "selfquestion"}))

        q = SelfQuestion.objects.filter(text_uz="2+2 nechiga teng?").first()
        self.assertIsNotNone(q)
        self.assertFalse(q.needs_review)
        self.assertTrue(q.img)
        self.assertTrue(q.img.name.endswith(".webp"))

        answers = list(q.selfanswer_set.order_by("id"))
        self.assertEqual(len(answers), 2)
        self.assertTrue(answers[0].is_correct)
        self.assertFalse(answers[1].is_correct)

    # ── 2 ──────────────────────────────────────────────────────────
    def test_needs_review_flag(self):
        data = {
            "question_text": "Python question",
            "question_text_uz": "", "question_text_ru": "",
            "question_text_en": "Python question",
            "answer_text_0": "A", "answer_text_0_uz": "",
            "answer_text_0_ru": "", "answer_text_0_en": "A",
            "answer_correct_0": "1",
            "answer_text_1": "B", "answer_text_1_uz": "",
            "answer_text_1_ru": "", "answer_text_1_en": "B",
        }

        resp = self.client.post(reverse("self_check_create"), data)
        self.assertRedirects(resp, reverse("dlist", kwargs={"tip": "selfquestion"}))

        q = SelfQuestion.objects.filter(text_uz="Python question").first()
        self.assertIsNotNone(q)
        self.assertTrue(q.needs_review)

    # ── 3 ──────────────────────────────────────────────────────────
    def test_form_validation_no_correct_answer(self):
        before = SelfQuestion.objects.count()
        data = {
            "question_text": "No right", "question_text_uz": "No right",
            "question_text_ru": "No right", "question_text_en": "No right",
            "answer_text_0": "A", "answer_text_0_uz": "A",
            "answer_text_0_ru": "A", "answer_text_0_en": "A",
            "answer_text_1": "B", "answer_text_1_uz": "B",
            "answer_text_1_ru": "B", "answer_text_1_en": "B",
        }

        resp = self.client.post(reverse("self_check_create"), data)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(SelfQuestion.objects.count(), before)

    # ── 4 ──────────────────────────────────────────────────────────
    def test_idor_protection_on_edit(self):
        my_q = SelfQuestion.objects.create(
            text_uz="My q", text_ru="My ru", text_en="My en")
        SelfAnswer.objects.create(
            question=my_q, text_uz="My a", text_ru="My ru", text_en="My en")

        stolen_id = self.other_a.id
        old_other = self.other_a.text_uz

        data = {
            "question_text": "Edited", "question_text_uz": "Edited",
            "question_text_ru": "Edited", "question_text_en": "Edited",
            "answer_id_0": str(stolen_id),
            "answer_text_0": "Hacked", "answer_text_0_uz": "Hacked",
            "answer_text_0_ru": "Hacked", "answer_text_0_en": "Hacked",
            "answer_correct_0": "1",
            "answer_text_1": "Other", "answer_text_1_uz": "Other",
            "answer_text_1_ru": "Other", "answer_text_1_en": "Other",
        }

        resp = self.client.post(
            reverse("self_check_edit", kwargs={"pk": my_q.pk}), data)
        self.assertRedirects(resp, reverse("dlist", kwargs={"tip": "selfquestion"}))

        self.other_a.refresh_from_db()
        self.assertEqual(self.other_a.text_uz, old_other)
        self.assertTrue(
            SelfAnswer.objects.filter(question=my_q, text_uz="Hacked").exists())

    # ── 5 ──────────────────────────────────────────────────────────
    def test_delete_question_cleans_files(self):
        from core.media_utils import process_uploaded_image

        jpg = _make_jpg_bytes()
        img = SimpleUploadedFile("q.jpg", jpg, content_type="image/jpeg")

        q = SelfQuestion.objects.create(text_uz="Del", text_ru="D", text_en="D")
        q_img = process_uploaded_image(img)
        q.img = q_img; q.save()

        a = SelfAnswer.objects.create(
            question=q, text_uz="A", text_ru="A", text_en="A", is_correct=True)
        a_img = process_uploaded_image(img)
        a.img = a_img; a.save()

        qn, an = q.img.name, a.img.name

        with patch("core.dashboard.action.default_storage.delete") as m:
            resp = self.client.get(reverse("action", kwargs={
                "status": "delete", "path": "selfquestion", "pk": q.pk}))

        self.assertRedirects(resp, reverse("dlist", kwargs={"tip": "selfquestion"}))
        called = {c.args[0] for c in m.call_args_list}
        self.assertIn(qn, called)
        self.assertIn(an, called)
        self.assertFalse(SelfQuestion.objects.filter(pk=q.pk).exists())
