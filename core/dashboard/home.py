import datetime

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count
from django.shortcuts import redirect, render

from core.models import ClassRooms, Result, Subject, Test, User
from core.models.auth import Role


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard home — drill-down view
# ─────────────────────────────────────────────────────────────────────────────

@login_required(login_url="login")
def home(request, status="subject", subject_id=None, classroom_id=None, user_id=None):
    """
    Single view that handles all dashboard drill-down levels:

      /dashboard/                                 → status="subject"
      /dashboard/<status>/                        → status=<status>
      /dashboard/<status>/<subject_id>/           → classroom list for a subject
      /dashboard/<status>/<classroom_id>/         → user list for a classroom
      /dashboard/<status>/<classroom_id>/<user_id>/  → results for a user

    Note: the two URL patterns that carry a single integer use different kwarg
    names in urls.py (``subject_id`` vs ``classroom_id``), but Django always
    resolves the *first* matching pattern (``dashboard_classroom``), so the
    integer arrives as ``subject_id`` in both cases.  The "user" branch
    therefore normalises via ``_classroom_id`` below.
    """
    if not request.user.in_dashboard:
        return redirect("lock")

    # ── Period filter ─────────────────────────────────────────────────────────
    try:
        period = int(request.GET.get("period", 7))
        if period not in (1, 7, 30):
            period = 7
    except (ValueError, TypeError):
        period = 7

    cutoff = datetime.date.today() - datetime.timedelta(days=period)

    # ── KPIs ──────────────────────────────────────────────────────────────────
    period_qs = Result.objects.filter(created__gte=cutoff)
    avg_raw = period_qs.aggregate(avg=Avg("foyiz"))["avg"]

    kpi = {
        "students": User.objects.filter(role=Role.STUDENT, is_active=True).count(),
        "active_tests": Test.objects.filter(is_start=True).count(),
        "total_tests": Test.objects.count(),
        "results_period": period_qs.count(),
        "avg_score": round(avg_raw, 1) if avg_raw is not None else 0,
    }

    # ── Recent results (sidebar / overview table) ─────────────────────────────
    recent = (
        Result.objects
        .select_related("user", "user__classroom", "test", "test__subject")
        .order_by("-created", "-id")[:12]
    )

    # ── Drill-down + breadcrumb ───────────────────────────────────────────────
    drill = None
    breadcrumb = []

    if status == "subject":
        drill = (
            Subject.objects
            .annotate(
                attempt_count=Count("tests__results", distinct=True),
                avg_score=Avg("tests__results__foyiz"),
            )
            .order_by("-attempt_count")
        )
        breadcrumb = [
            ("Dashboard", "dashboard"),
            ("Subjects", None),
        ]

    elif status == "classroom":
        drill = (
            ClassRooms.objects
            .filter(classroomssubjects__subject_id=subject_id)
            .annotate(
                attempt_count=Count("user__results", distinct=True),
                avg_score=Avg("user__results__foyiz"),
            )
            .distinct()
            .order_by("-attempt_count")
        )
        # Persist subject selection for subsequent drill-downs
        request.user.log["subject_id"] = subject_id
        request.user.save(update_fields=["log"])

        subject_name = (
            Subject.objects.filter(pk=subject_id).values_list("name", flat=True).first() or ""
        )
        breadcrumb = [
            ("Dashboard", "dashboard"),
            ("Subjects", "dashboard_subject"),
            (subject_name, None),
        ]

    elif status == "user":
        # Due to identical URL pattern shapes, the classroom pk arrives as
        # ``subject_id`` when matched by ``dashboard_classroom`` first.
        _classroom_id = classroom_id if classroom_id is not None else subject_id

        drill = (
            User.objects
            .filter(classroom_id=_classroom_id, role=Role.STUDENT, is_active=True)
            .annotate(
                attempt_count=Count("results", distinct=True),
                avg_score=Avg("results__foyiz"),
            )
            .order_by("-avg_score")
        )

        log_subject_id = request.user.log.get("subject_id")
        subject_name = (
            Subject.objects.filter(pk=log_subject_id).values_list("name", flat=True).first() or ""
        )
        classroom_name = (
            ClassRooms.objects.filter(pk=_classroom_id).values_list("name", flat=True).first() or ""
        )
        breadcrumb = [
            ("Dashboard", "dashboard"),
            ("Subjects", "dashboard_subject"),
            (subject_name, "dashboard_classroom"),
            (classroom_name, None),
        ]

    elif status == "result":
        log_subject_id = request.user.log.get("subject_id")

        drill = (
            Result.objects
            .filter(user_id=user_id, test__subject_id=log_subject_id)
            .select_related("test", "test__subject", "user", "user__classroom")
            .order_by("-created")
        )

        subject_name = (
            Subject.objects.filter(pk=log_subject_id).values_list("name", flat=True).first() or ""
        )
        user_obj = (
            User.objects.select_related("classroom").filter(pk=user_id).first()
        )
        user_name = user_obj.name if user_obj else ""
        classroom_name = user_obj.classroom.name if (user_obj and user_obj.classroom) else ""

        breadcrumb = [
            ("Dashboard", "dashboard"),
            ("Subjects", "dashboard_subject"),
            (subject_name, "dashboard_classroom"),
            (classroom_name, "dashboard_user"),
            (user_name, None),
        ]

    else:
        return redirect("dashboard")

    ctx = {
        "kpi": kpi,
        "recent": recent,
        "drill": drill,
        "status": status,
        "period": period,
        "subject_id": subject_id,
        "classroom_id": classroom_id,
        "user_id": user_id,
        "breadcrumb": breadcrumb,
    }
    return render(request, "pages/dashboard/index.html", ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard lock / unlock
# ─────────────────────────────────────────────────────────────────────────────

@login_required(login_url="login")
def lock(request):
    """Render the dashboard password gate (GET) or verify it (POST)."""
    if request.user.role == 4:
        return redirect("home")

    if request.method == "POST":
        in_dash = request.user.check_password(request.POST.get("pass", ""))
        request.user.in_dashboard = in_dash
        request.user.save(update_fields=["in_dashboard"])
        return redirect("dashboard") if in_dash else redirect("lock")

    return render(request, "pages/dashboard/pass.html")


# ─────────────────────────────────────────────────────────────────────────────
# Legacy endpoint — kept for import compatibility
# ─────────────────────────────────────────────────────────────────────────────

def locked(request):
    """Legacy redirect; superseded by ``lock``."""
    return redirect("lock")
