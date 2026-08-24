from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from modeltranslation.admin import TranslationAdmin

from core.models import (
    Potok,
    Question,
    Result,
    Subject,
    Test,
    User,
    Variant,
    Partners,
    About,
    Courses,
    Teachers,
    News,
    SelfAnswer,
    SelfQuestion,
    SelfResult,
    SelfStudy,
    SelfUser,
)

from .resource import (
    PotokResource,
    QuestionResource,
    ResultResource,
    SUbjectResource,
    TestResource,
    UserResource,
    VariantResource,
    PartnersResource,
    AboutResource,
    CoursesResource,
    TeachersResource,
    NewsResource,
    SelfAnswerResource,
    SelfQuestionResource,
    SelfResultResource,
    SelfStudyResource,
    SelfUserResource,
)


class UserAdmin(ImportExportModelAdmin):
    resource_class = UserResource



class PotokSubjectAdmin(ImportExportModelAdmin):
    resource_class = PotokResource


class VariantAdmin(TranslationAdmin, ImportExportModelAdmin):
    resource_class = VariantResource


class TestAdmin(ImportExportModelAdmin):
    resource_class = TestResource


class QuestionAdmin(TranslationAdmin, ImportExportModelAdmin):
    resource_class = QuestionResource


class SubjectAdmin(TranslationAdmin, ImportExportModelAdmin):
    resource_class = SUbjectResource


class PotokAdmin(ImportExportModelAdmin):
    resource_class = PotokResource


class ResultAdmin(ImportExportModelAdmin):
    resource_class = ResultResource

class PartnersAdmin(ImportExportModelAdmin):
    resource_class = PartnersResource


class AboutAdmin(TranslationAdmin, ImportExportModelAdmin):
    resource_class = AboutResource


class CoursesAdmin(TranslationAdmin, ImportExportModelAdmin):
    resource_class = CoursesResource


class TeachersAdmin(TranslationAdmin, ImportExportModelAdmin):
    resource_class = TeachersResource


class NewsAdmin(TranslationAdmin, ImportExportModelAdmin):
    resource_class = NewsResource

class SelfResultAdmin(ImportExportModelAdmin):
    resource_class = SelfResultResource

class SelfAnswerAdmin(TranslationAdmin, ImportExportModelAdmin):
    resource_class = SelfAnswerResource

class SelfQuestionAdmin(TranslationAdmin, ImportExportModelAdmin):
    resource_class = SelfQuestionResource

class SelfStudyAdmin(TranslationAdmin, ImportExportModelAdmin):
    resource_class = SelfStudyResource

class SelfUserAdmin(ImportExportModelAdmin):
    resource_class = SelfUserResource


admin.site.register(User, UserAdmin)
admin.site.register(Subject, SubjectAdmin)
admin.site.register(Test, TestAdmin)
admin.site.register(Question, QuestionAdmin)
admin.site.register(Variant, VariantAdmin)
admin.site.register(Result, ResultAdmin)
admin.site.register(Potok, PotokAdmin)
admin.site.register(Partners, PartnersAdmin)
admin.site.register(About, AboutAdmin)
admin.site.register(Courses, CoursesAdmin)
admin.site.register(Teachers, TeachersAdmin)
admin.site.register(News, NewsAdmin)
admin.site.register(SelfResult, SelfResultAdmin)
admin.site.register(SelfUser, SelfUserAdmin)
admin.site.register(SelfAnswer, SelfAnswerAdmin)
admin.site.register(SelfQuestion, SelfQuestionAdmin)
admin.site.register(SelfStudy, SelfStudyAdmin)

