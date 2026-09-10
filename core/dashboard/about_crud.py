"""
core/dashboard/about_crud.py
────────────────────────────────
CRUD-view для синглтон-модели About (страница "О нас") в дашборде.

About — ровно одна запись с фиксированным pk=1 (get_or_create гарантирует,
что при параллельных первых запросах не будет гонки/дублирования записей).

RBAC и sliding-window таймаут дашборда проверяет DashboardSecurityMiddleware —
свои проверки прав здесь не нужны.

Переводимые поля (см. core/translation.py::AboutTranslationOptions) — 10
текстовых полей (info/title/desc/goals_info/courses_info/teachers_info/
news_info/partners_info/working_hours/footer_info) обрабатываются тем же
fallback-паттерном, что и в subject_crud.py/courses_crud.py: пустой
uz-перевод заполняется значением видимого (основного) поля формы, ru/en
остаются как прислала форма.

Служебные поля (tg, insta, fb, location, phone, email) и чекбокс partners
не переводятся — сохраняются как есть.

Картинок у About нет — обработка файлов не требуется.
"""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from core.models import About

# Переводимые поля About (см. core/translation.py) — обрабатываются через
# единый fallback-паттерн: about_<field>, about_<field>_uz/_ru/_en.
_TRANSLATABLE_FIELDS = (
    "info", "title", "desc", "goals_info", "courses_info",
    "teachers_info", "news_info", "partners_info",
    "working_hours", "footer_info", "location",
)

# Служебные (нетранслируемые) текстовые поля — сохраняются как есть.
_PLAIN_FIELDS = ("tg", "insta", "fb", "phone", "email")


def _resolve_translation(raw_text, uz, ru, en):
    """
    Собирает итоговые значения uz/ru/en для одного переводимого поля.

    :param raw_text: значение основного (видимого) поля формы — используется
        как fallback для uz, если явный uz-перевод не пришёл.
    :param uz: значение скрытого поля <field>_uz
    :param ru: значение скрытого поля <field>_ru
    :param en: значение скрытого поля <field>_en
    """
    raw = (raw_text or "").strip()
    uz = (uz or "").strip() or raw
    ru = (ru or "").strip()
    en = (en or "").strip()
    return uz, ru, en


@login_required(login_url="login")
def edit_about(request):
    """
    Редактирование синглтон-записи About.

    GET  — форма с текущими данными (pk=1, создаётся при первом обращении).
    POST — служебные поля сохраняются как есть, переводимые поля — через
           fallback-паттерн (uz/ru/en); сохранение и редирект обратно
           на форму.
    """
    about_obj, _ = About.objects.get_or_create(id=1)

    if request.method != "POST":
        return render(request, "pages/dashboard/about_edit.html", {
            "about": about_obj,
        })

    post = request.POST

    # ── Служебные (нетранслируемые) поля ────────────────────────────────
    for field in _PLAIN_FIELDS:
        setattr(about_obj, field, (post.get(f"about_{field}") or "").strip())

    about_obj.partners = post.get("about_partners") == "1"

    # ── Переводимые поля (uz/ru/en, с fallback на основное поле) ────────
    for field in _TRANSLATABLE_FIELDS:
        raw = post.get(f"about_{field}")
        uz = post.get(f"about_{field}_uz")
        ru = post.get(f"about_{field}_ru")
        en = post.get(f"about_{field}_en")

        uz, ru, en = _resolve_translation(raw, uz, ru, en)

        setattr(about_obj, f"{field}_uz", uz)
        setattr(about_obj, f"{field}_ru", ru)
        setattr(about_obj, f"{field}_en", en)

    about_obj.save()

    return redirect("dashboard_about")