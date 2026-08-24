from import_export import resources

from .models import (
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
    SelfUser
)


class UserResource(resources.ModelResource):
    class Meta:
        model = User
        # Хеш пароля никогда не должен попадать в CSV/Excel-экспорт.
        exclude = ("password",)



class PotokResource(resources.ModelResource):
    class Meta:
        model = Potok

class ResultResource(resources.ModelResource):
    class Meta:
        model = Result


class QuestionResource(resources.ModelResource):
    class Meta:
        model = Question
        # ИСПРАВЛЕНО: поле 'varianta' удалено из модели — вместо него FK 'test'.
        fields = ('id', 'text_uz', 'text_ru', 'text_en', 'img', 'test', 'created',)

class TestResource(resources.ModelResource):
    class Meta:
        model = Test
        fields = (
            'id', 'potok', 'subject', 'created', 'updated',
        )
        


class VariantResource(resources.ModelResource):
    class Meta:
        model = Variant
        fields = ('id', 'text_uz', 'text_ru', 'text_en', 'is_answer', 'question',)



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

class SelfResultResource(resources.ModelResource):
    class Meta:
        model = SelfResult


class SelfUserResource(resources.ModelResource):
    class Meta:
        model = SelfUser
