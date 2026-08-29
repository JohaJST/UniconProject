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
from core.models.self import SelfCtg
from modeltranslation.translator import register, TranslationOptions

from core.models import Subject, Question, Variant
from core.models import About, Teachers, Courses, News
from core.models import SelfAnswer, SelfQuestion, SelfStudy

@register(Subject)
class SubjectTranslationOptions(TranslationOptions):
    fields = ('name',)



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


@register(SelfAnswer)
class SelfAnswerTranslationOptions(TranslationOptions):
    fields = ('text',)


@register(SelfQuestion)
class SelfQuestionTranslationOptions(TranslationOptions):
    fields = ('text',)


@register(SelfStudy)
class SelfStudyTranslationOptions(TranslationOptions):
    fields = ('html_text',)


@register(SelfCtg)
class SelfCtgTranslationOptions(TranslationOptions):
    fields = ('name',)
    