import datetime
import hashlib

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count
from django.shortcuts import redirect, render

from core.models import Potok, Result, Subject, Test, User
from core.models.auth import Role
from core.auth_jwt.exceptions import RateLimitError
from core.auth_jwt.services import AuthRedisService


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard home — drill-down view
# ─────────────────────────────────────────────────────────────────────────────

@login_required(login_url="login")
def home(request, status="subject", subject_id=None, potok_id=None, user_id=None):
    """
    Single view that handles all dashboard drill-down levels:

      /dashboard/                                  → status="subject"
      /dashboard/<status>/                         → status=<status>
      /dashboard/<status>/<subject_id>/            → potok list
      /dashboard/<status>/<potok_id>/              → user list for a potok
      /dashboard/<status>/<potok_id>/<user_id>/    → results for a user
    """

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
        "total_potoks": Potok.objects.count(),
        "total_tests": Test.objects.count(),
        "results_period": period_qs.count(),
        "avg_score": round(avg_raw, 1) if avg_raw is not None else 0,
    }

    # ── Recent results (sidebar / overview table) ─────────────────────────────
    recent = (
        Result.objects
        .select_related("user", "user__potok", "test", "test__subject")
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

    elif status == "potok":
        drill = Potok.objects.all().order_by("-start")
        breadcrumb = [
            ("Dashboard", "dashboard"),
            ("Potoklar", None),
        ]

    elif status == "user":
        _potok_id = potok_id if potok_id is not None else subject_id

        drill = (
            User.objects
            .filter(potok_id=_potok_id, role=Role.STUDENT, is_active=True)
            .annotate(
                attempt_count=Count("results", distinct=True),
                avg_score=Avg("results__foyiz"),
            )
            .order_by("-avg_score")
        )

        potok_name = (
            Potok.objects.filter(pk=_potok_id).values_list("start", "end").first()
        )
        breadcrumb = [
            ("Dashboard", "dashboard"),
            ("Potoklar", "dashboard_potok"),
            (str(_potok_id), None),
        ]

    elif status == "result":
        drill = (
            Result.objects
            .filter(user_id=user_id)
            .select_related("test", "test__subject", "user", "user__potok")
            .order_by("-created")
        )

        user_obj = (
            User.objects.select_related("potok").filter(pk=user_id).first()
        )
        user_name = user_obj.name if user_obj else ""
        potok_name = user_obj.potok.date_range if (user_obj and user_obj.potok) else ""

        breadcrumb = [
            ("Dashboard", "dashboard"),
            ("Potoklar", "dashboard_potok"),
            (potok_name, "dashboard_user"),
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
        "potok_id": potok_id,
        "user_id": user_id,
        "breadcrumb": breadcrumb,
    }
    return render(request, "pages/dashboard/index.html", ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard lock / unlock
# ─────────────────────────────────────────────────────────────────────────────

@login_required(login_url="login")
def lock(request):
    """
    Render the dashboard password gate (GET) or verify it (POST).

    Доступ к дашборду живёт в Redis-ключе user:{user_id}:dashboard_auth
    с TTL 600s (sliding window, продлевается в DashboardSecurityMiddleware
    на каждый запрос к защищённому пути).
    """
    if request.method == "POST":
        ip_raw = request.META.get("REMOTE_ADDR", "")
        ip_hash = hashlib.sha256(ip_raw.encode("utf-8")).hexdigest()

        try:
            AuthRedisService.check_lock_bruteforce(request.user.id, ip_hash)
        except RateLimitError:
            return render(request, "pages/dashboard/pass.html", {
                "error": "Слишком много попыток. Попробуйте позже.",
            })

        if request.user.check_password(request.POST.get("pass", "")):
            AuthRedisService.clear_login_attempts(request.user.id)
            AuthRedisService.authorize_dashboard(request.user.id)
            return redirect("dashboard")

        return render(request, "pages/dashboard/pass.html", {
            "error": "Неверный пароль",
        })

    return render(request, "pages/dashboard/pass.html")


# ─────────────────────────────────────────────────────────────────────────────
# Legacy endpoint — kept for import compatibility
# ─────────────────────────────────────────────────────────────────────────────

def locked(request):
    """Legacy redirect; superseded by ``lock``."""
    return redirect("lock")
