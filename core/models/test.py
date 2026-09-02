from django.db import models

from core.models.auth import User
from core.models.classrooms import Potok, Subject

# ─────────────────────────────────────────────────────────────────────────────
# Test  (Тест)
# ─────────────────────────────────────────────────────────────────────────────

class Test(models.Model):
    # name = models.CharField(max_length=200)
    # Пустая строка вместо NULL — стандартная практика для текстовых полей Django.
    # desc = models.TextField(default='', blank=True)
    subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tests',
    )
    
    potok = models.ForeignKey(
        Potok,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tests',
    )
    
    # is_start = models.BooleanField(default=False, db_index=True)
    created = models.DateTimeField(auto_now_add=True, auto_now=False, null=True, blank=True, editable=False)
    updated = models.DateTimeField(auto_now_add=False, auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = 'Тест'
        verbose_name_plural = '4. Тесты'
        ordering = ['-created']

    def __str__(self):
        return f'{self.potok} {self.subject}'


class Question(models.Model):
    text = models.TextField(default='', blank=True)
    img = models.ImageField(null=True, blank=True)
    test = models.ForeignKey(
        Test,
        on_delete=models.CASCADE,
        related_name='questions',
        db_column='test_id',
    )
    # null убран (по аналогии с Result.created, core/migrations/0010_...) —
    # created теперь опорное поле сортировки Keyset Engine для tip="question",
    # NULL там ломает составное сравнение курсора (created, id). Перед
    # применением AlterField(null=False) существующие NULL нужно забэкфиллить
    # (см. management-команду backfill_question_created).
    created = models.DateTimeField(auto_now_add=True, auto_now=False, blank=True, editable=False)
    updated = models.DateTimeField(auto_now_add=False, auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = 'Вопрос'
        verbose_name_plural = '6. Вопросы'
        ordering = ['id']
        indexes = [
            # Опорный индекс Keyset Engine — составное сравнение курсора
            # Q(created__lt=X) | Q(created=X, id__lt=Y). Обратный DESC-индекс
            # намеренно не создаётся (тот же паттерн, что и у Result).
            models.Index(fields=['created', 'id'], name='question_created_id_idx'),
        ]

    def __str__(self):
        return self.text or f'Вопрос #{self.pk}'


# ─────────────────────────────────────────────────────────────────────────────
# Variant  (Вариант ответа)
# ─────────────────────────────────────────────────────────────────────────────

class Variant(models.Model):
    text = models.TextField()
    is_answer = models.BooleanField(default=False, db_index=True)
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='answers',
    )
    # created удалён: дата создания варианта ответа нигде не используется
    # и только увеличивает размер таблицы.
    created = models.DateTimeField(auto_now_add=True, auto_now=False, null=True, blank=True, editable=False)
    updated = models.DateTimeField(auto_now_add=False, auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = 'Вариант ответа'
        verbose_name_plural = '7. Варианты ответов'

    def __str__(self):
        marker = '✓' if self.is_answer else '✗'
        return f'[{marker}] {self.text}'


# ─────────────────────────────────────────────────────────────────────────────
# Result  (Результат)
# ─────────────────────────────────────────────────────────────────────────────

class Result(models.Model):
    result = models.PositiveSmallIntegerField(null=True)
    foyiz = models.PositiveSmallIntegerField(null=True)
    totalQuestions = models.PositiveSmallIntegerField(null=True)
    time = models.PositiveSmallIntegerField(null=True)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='results',
    )
    test = models.ForeignKey(
        Test,
        on_delete=models.SET_NULL,
        null=True,
        related_name='results',
    )
    # null убран (см. core/migrations/0010_result_created_not_null.py) —
    # created теперь опорное поле сортировки Keyset Engine для tip="result",
    # NULL там ломает составное сравнение курсора (created, id).
    created = models.DateTimeField(auto_now_add=True, auto_now=False, blank=True, editable=False)
    updated = models.DateTimeField(auto_now_add=False, auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = 'Результат'
        verbose_name_plural = '8. Результаты'
        ordering = ['-created']
        indexes = [
            # Частый паттерн запроса: результаты конкретного пользователя
            # по конкретному тесту.
            models.Index(fields=['user', 'test'], name='result_user_test_idx'),
            # Опорный индекс Keyset Engine — составное сравнение курсора
            # Q(created__lt=X) | Q(created=X, id__lt=Y). Обратный DESC-индекс
            # намеренно не создан — Backward Index Scan по этому же индексу
            # достаточен и для PostgreSQL, и для SQLite.
            models.Index(fields=['created', 'id'], name='result_created_id_idx'),
        ]

