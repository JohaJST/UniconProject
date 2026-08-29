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
    # Переименовано: `test` → `varianta`, чтобы отражать реальную связь
    # (FK ведёт к TestVarianta, а не к Test).
    # db_column='test_id' сохраняет имя столбца в БД — без потери данных.
    test = models.ForeignKey(
        Test,
        on_delete=models.CASCADE,
        related_name='questions',
        db_column='test_id',
    )
    created = models.DateTimeField(auto_now_add=True, auto_now=False, null=True, blank=True, editable=False)
    updated = models.DateTimeField(auto_now_add=False, auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = 'Вопрос'
        verbose_name_plural = '6. Вопросы'
        ordering = ['id']

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
    # PositiveSmallIntegerField вместо IntegerField: значения 0–32 767,
    # что более чем достаточно для счётчиков правильных ответов и процентов.
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
    created = models.DateTimeField(auto_now_add=True, auto_now=False, null=True, blank=True, editable=False)
    updated = models.DateTimeField(auto_now_add=False, auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = 'Результат'
        verbose_name_plural = '8. Результаты'
        ordering = ['-created']
        indexes = [
            # Частый паттерн запроса: результаты конкретного пользователя
            # по конкретному тесту.
            models.Index(fields=['user', 'test'], name='result_user_test_idx'),
        ]

    def __str__(self):
        return f'{self.user} | {self.result}/{self.totalQuestions} ({self.foyiz}%)'

