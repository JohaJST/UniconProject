"""
core/dashboard/selfstudy_crud.py
────────────────────────────────
CRUD-view для синглтон-модели SelfStudy (страница самостоятельного
изучения) в дашборде.

SelfStudy — ровно одна запись с фиксированным pk=1 (get_or_create
гарантирует отсутствие гонки/дублирования при параллельных первых
запросах).

RBAC и sliding-window таймаут дашборда проверяет DashboardSecurityMiddleware —
свои проверки прав здесь не нужны.

В отличие от About, здесь всего одно переводимое поле (html_text, см.
core/translation.py::SelfStudyTranslationOptions), и никакого
fallback-паттерна не требуется: uz/ru/en — равноценные поля, каждое
сохраняется как прислала форма, без валидации.
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from core.models import SelfStudy


@login_required(login_url="login")
def edit_selfstudy(request):
    """
    Редактирование синглтон-записи SelfStudy.

    GET  — форма с текущими данными (pk=1, создаётся при первом обращении).
    POST — html_text_uz/ru/en сохраняются как есть, без валидации и
           fallback-логики; сохранение и редирект обратно на форму.
    """
    selfstudy_obj, _ = SelfStudy.objects.get_or_create(id=1)

    if request.method != "POST":
        return render(request, "pages/dashboard/selfstudy_edit.html", {
            "selfstudy": selfstudy_obj,
        })

    post = request.POST

    selfstudy_obj.html_text_uz = post.get("selfstudy_html_uz") or ""
    selfstudy_obj.html_text_ru = post.get("selfstudy_html_ru") or ""
    selfstudy_obj.html_text_en = post.get("selfstudy_html_en") or ""
    selfstudy_obj.save()

    return redirect("dashboard_selfstudy")