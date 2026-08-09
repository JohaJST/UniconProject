from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from modeltranslation.admin import TranslationAdmin

from core.models import (
    ClassRooms,
    ClassRoomsSubjects,
    OldResult,
    Question,
    Result,
    Subject,
    Test,
    TestClassRoom,
    TestVarianta,
    TG_User,
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
    SelfImg,
)

from .resource import (
    CLassroomResource,
    ClassRoomsSubjectsResource,
    OldResulrResource,
    QuestionResource,
    ResultResource,
    SUbjectResource,
    TestClassRoomResource,
    TestResource,
    TestVariantaResource,
    TG_UserResource,
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
    SelfImgResource,
)


class UserAdmin(ImportExportModelAdmin):
    resource_class = UserResource


class TestClassRoomAdmin(ImportExportModelAdmin):
    resource_class = TestClassRoomResource


class ClassRoomSubjectAdmin(ImportExportModelAdmin):
    resource_class = ClassRoomsSubjectsResource


class TgUserAdmin(ImportExportModelAdmin):
    resource_class = TG_UserResource


class VariantAdmin(TranslationAdmin, ImportExportModelAdmin):
    resource_class = VariantResource


class TestAdmin(TranslationAdmin, ImportExportModelAdmin):
    resource_class = TestResource


class TestVariantaAdmin(ImportExportModelAdmin):
    resource_class = TestVariantaResource


class QuestionAdmin(TranslationAdmin, ImportExportModelAdmin):
    resource_class = QuestionResource


class SubjectAdmin(TranslationAdmin, ImportExportModelAdmin):
    resource_class = SUbjectResource


class ClassroomAdmin(ImportExportModelAdmin):
    resource_class = CLassroomResource


class OldAdmin(ImportExportModelAdmin):
    resource_class = OldResulrResource


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

class SelfImgAdmin(ImportExportModelAdmin):
    resource_class = SelfImgResource


admin.site.register(User, UserAdmin)
admin.site.register(TG_User, TgUserAdmin)
admin.site.register(TestClassRoom, TestClassRoomAdmin)
admin.site.register(ClassRooms, ClassroomAdmin)
admin.site.register(Subject, SubjectAdmin)
admin.site.register(Test, TestAdmin)
admin.site.register(TestVarianta, TestVariantaAdmin)
admin.site.register(Question, QuestionAdmin)
admin.site.register(Variant, VariantAdmin)
admin.site.register(Result, ResultAdmin)
admin.site.register(OldResult, OldAdmin)
admin.site.register(ClassRoomsSubjects, ClassRoomSubjectAdmin)
admin.site.register(Partners, PartnersAdmin)
admin.site.register(About, AboutAdmin)
admin.site.register(Courses, CoursesAdmin)
admin.site.register(Teachers, TeachersAdmin)
admin.site.register(News, NewsAdmin)
admin.site.register(SelfResult, SelfResultAdmin)
admin.site.register(SelfAnswer, SelfAnswerAdmin)
admin.site.register(SelfQuestion, SelfQuestionAdmin)
admin.site.register(SelfStudy, SelfStudyAdmin)
admin.site.register(SelfImg, SelfImgAdmin)

