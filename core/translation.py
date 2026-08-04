"""
core/translation.py
────────────────────────
Регистрация переводимых полей моделей для django-modeltranslation.

Языки: uz (базовый/default), ru, en — см. settings.MODELTRANSLATION_LANGUAGES.

ВАЖНО: Variant.text НЕ регистрируется на этом этапе — варианты ответов
остаются одноязычными. Это осознанное решение: перевод вариантов ответов
не входит в ТЗ текущего этапа. Если понадобится — заводить отдельным
этапом со своей data-миграцией backfill (по аналогии с этой).
"""
from modeltranslation.translator import register, TranslationOptions

from core.models import Subject, Test, Question, Variant
from core.models import About, Teachers, Courses, News


@register(Subject)
class SubjectTranslationOptions(TranslationOptions):
    fields = ('name',)


@register(Test)
class TestTranslationOptions(TranslationOptions):
    fields = ('name', 'desc')


@register(Question)
class QuestionTranslationOptions(TranslationOptions):
    fields = ('text',)


@register(Variant)
class VariantTranslationOptions(TranslationOptions):
    fields = ('text',)


@register(About)
class AboutTranslationOptions(TranslationOptions):
    fields = (
        'info', 'title', 'desc', 'goals_info',
        'news_info', 'teachers_info', 'courses_info',
        'partners_info', 'working_hours', 'footer_info',
    )


@register(Teachers)
class TeachersTranslationOptions(TranslationOptions):
    fields = ('position',)


@register(Courses)
class CoursesTranslationOptions(TranslationOptions):
    fields = ('name', 'desc', 'title',)


@register(News)
class NewsTranslationOptions(TranslationOptions):
    fields = ('title', 'desc',)

