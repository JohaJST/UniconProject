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
        fields = ('id', 'text_uz', 'text_ru', 'text_en', 'img', 'varianta', 'created',)

class TestResource(resources.ModelResource):
    class Meta:
        model = Test
        fields = (
            'id', 'name_uz', 'name_ru', 'name_en',
            'desc_uz', 'desc_ru', 'desc_en',
            'subject', 'is_start', 'created',
        )
        

class TestVariantaResource(resources.ModelResource):
    class Meta:
        model = TestVarianta


class VariantResource(resources.ModelResource):
    class Meta:
        model = Variant
        fields = ('id', 'text_uz', 'text_ru', 'text_en', 'is_answer', 'question',)


class ClassRoomsSubjectsResource(resources.ModelResource):
    class Meta:
        model = ClassRoomsSubjects


class TestClassRoomResource(resources.ModelResource):
    class Meta:
        model = TestClassRoom


class SUbjectResource(resources.ModelResource):
    class Meta:
        model = Subject
        fields = ('id', 'name_uz', 'name_ru', 'name_en', 'created', 'updated',)

class PartnersResource(resources.ModelResource):
    class Meta:
        model = Partners

class AboutResource(resources.ModelResource):
    class Meta:
        model = About
        fields = (
            "id", "info_uz", "info_ru", "info_en",
            "tg", "title_uz", "title_ru", "title_en",
            "insta", "desc_uz", "desc_ru", "desc_en",
            "fb", "goals_info_uz", "goals_info_ru", "goals_info_en",
            "location", "news_info_uz", "news_info_ru", "news_info_en",
            "phone", "teachers_info_uz", "teachers_info_ru", "teachers_info_en",
            "email", "courses_info_uz", "courses_info_ru", "courses_info_en",
            "partners", "partners_info_uz", "partners_info_ru", "partners_info_en",
            "working_hours_uz", "working_hours_ru", "working_hours_en",
            "footer_info_uz", "footer_info_ru", "footer_info_en",
        )

class CoursesResource(resources.ModelResource):
    class Meta:
        model = Courses
        fields = (
            'id', 'title_uz', 'title_ru', 'title_en',
            'desc_uz', 'desc_ru', 'desc_en', 'photo',
            'name_uz', 'name_ru', 'name_en',
        )
        

class TeachersResource(resources.ModelResource):
    class Meta:
        model = Teachers
        fields = (
            'id', 'phone', 'photo', 'fio',
            'position_uz', 'position_ru', 'position_en',
        )
        

class NewsResource(resources.ModelResource):
    class Meta:
        model = News
        fields = (
            'id', 'title_uz', 'title_ru', 'title_en',
            'desc_uz', 'desc_ru', 'desc_en', 'photo',
            'date',
        )

class SelfAnswerResource(resources.ModelResource):
    class Meta:
        model = SelfAnswer
        fields = (
            'id', 'question', 'text_uz', 'text_ru', 'text_en', 'img', 'is_correct',
        )


class SelfQuestionResource(resources.ModelResource):
    class Meta:
        model = SelfQuestion
        fields = (
            'id', 'text_uz', 'text_ru', 'text_en', 'img',
        )

class SelfStudyResource(resources.ModelResource):
    class Meta:
        model = SelfStudy
        fields = (
            'id', 'html_text_uz', 'html_text_ru', 'html_text_en',
        )

class SelfImgResource(resources.ModelResource):
    class Meta:
        model = SelfImg

class SelfResultResource(resources.ModelResource):
    class Meta:
        model = SelfResult

