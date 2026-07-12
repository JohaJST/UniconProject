from import_export import resources

from .models import (
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


class UserResource(resources.ModelResource):
    class Meta:
        model = User


class TG_UserResource(resources.ModelResource):
    class Meta:
        model = TG_User


class CLassroomResource(resources.ModelResource):
    class Meta:
        model = ClassRooms

class ResultResource(resources.ModelResource):
    class Meta:
        model = Result


class OldResulrResource(resources.ModelResource):
    class Meta:
        model = OldResult


class QuestionResource(resources.ModelResource):
    class Meta:
        model = Question

class TestResource(resources.ModelResource):
    class Meta:
        model = Test


class TestVariantaResource(resources.ModelResource):
    class Meta:
        model = TestVarianta


class VariantResource(resources.ModelResource):
    class Meta:
        model = Variant


class ClassRoomsSubjectsResource(resources.ModelResource):
    class Meta:
        model = ClassRoomsSubjects


class TestClassRoomResource(resources.ModelResource):
    class Meta:
        model = TestClassRoom


class SUbjectResource(resources.ModelResource):
    class Meta:
        model = Subject
