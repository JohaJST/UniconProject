from django.urls import path, include

from core.auth import refresh_token_view
from .about import about, self, self_check
from core.auth import change_account_language, sign_in, sign_out
from core.quiz import (
    create_test,
    index,
    required,
    test,
    test_answer,
    test_result,
    user_profile,
)

from .dashboard import action, dlist, form, home, lock, ai_translate

# ── Пути, которые должны попадать под языковой префикс (/uz/..., /en/...) ──
# Оборачиваются в i18n_patterns() в src/urls.py (корневом URLConf).
i18n_urlpatterns = [
    path("", about, name="about"),
    path("self/", self, name="self"),
    path("self/check/", self_check, name="self_check"),
    path("login/", sign_in, name="login"),
    path("i18n/", include("django.conf.urls.i18n")),
]

# ── Обычные пути — без изменений имён/порядка ───────────────────────────────
urlpatterns = [
    path("test/", index, name="home"),
    path("logout/", sign_out, name="logout"),
    path("user/", user_profile, name="user_profile"),
    path("test/<int:test_id>/", test, name="test"),
    path("test/<int:test_id>/result/", test_result, name="test_result"),
    path("test/answer/", test_answer, name="test_answer"),
    path("test/create/", create_test, name="create_test"),
    path("dashboard/", home, name="dashboard"),
    path("dashboard/ai-translate/", ai_translate, name="ai_translate"),
    path("dashboard/list/<str:tip>/", dlist, name="dlist"),
    path("action/<str:status>/<str:path>/<int:pk>/", action, name="action"),
    path("action/<str:status>/<str:path>/", action, name="action_no_pk"),
    path("subject/<int:pk>/", index, name="sub"),
    path("form/user/", form, name="userform"),
    path("required/", required, name="required"),
    path("lock/", lock, name="lock"),
    path("locked/", lock, name="locked"),
    path("token/refresh/", refresh_token_view, name="token_refresh"),
    path("account/language/", change_account_language, name="change_language"),
]