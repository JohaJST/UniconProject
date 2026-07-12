"""
Quiz autosave — cache layer views
==================================
Two endpoints; zero direct ORM writes until finalize.

  POST /test/autosave/   autosave_answer   — stores one answer in cache
  POST /test/finalize/   finalize_test     — flushes cache → single DB write
"""
from __future__ import annotations

import json
import random

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from core.models import Question, Result, Variant
from core.models.test import OldResult

# ── Constants ─────────────────────────────────────────────────────────────────

# Cache TTL: 24 hours — survives a working day even without finalizing.
_DRAFT_TTL: int = 86_400


# ── Helpers ───────────────────────────────────────────────────────────────────

def _draft_key(user_id: int, test_id: int) -> str:
    """Unique, user-scoped cache key for a test draft."""
    return f"quiz_draft_{user_id}_{test_id}"


def _parse_body(request) -> dict:
    """Decode JSON body or raise ValueError."""
    try:
        return json.loads(request.body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc


# ── Views ─────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def autosave_answer(request):
    """
    Persist a single answer to cache.  **No SQL writes.**

    Request body (JSON):
        {
            "test_id":     int,
            "question_id": int,
            "variant_id":  int | null   # null = clear the answer
        }

    Response:
        {"ok": true, "saved": <count of cached answers>}
    """
    try:
        body = _parse_body(request)
        test_id     = int(body["test_id"])
        question_id = int(body["question_id"])
        raw_vid     = body.get("variant_id")
        variant_id  = int(raw_vid) if raw_vid is not None else None
    except (KeyError, ValueError, TypeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    key: str    = _draft_key(request.user.id, test_id)
    draft: dict = cache.get(key) or {}

    if variant_id is not None:
        draft[str(question_id)] = variant_id
    else:
        # variant_id=null means the user cleared this answer
        draft.pop(str(question_id), None)

    cache.set(key, draft, _DRAFT_TTL)
    return JsonResponse({"ok": True, "saved": len(draft)})


@login_required
@require_POST
def finalize_test(request):
    """
    Finalize a test session:
      1. Read cached answers (merge with client fallback).
      2. Score them with a single bulk Variant query.
      3. Persist one Result row inside an atomic transaction.
      4. Evict the cache entry.

    Request body (JSON):
        {
            "test_id": int,
            "answers": {"<question_id>": <variant_id>, ...}   # client-side fallback
        }

    The client MUST pass its in-memory ``answers`` map.
    Cache is authoritative when present; client data fills gaps for questions
    that autosave never reached (e.g. last answer selected before debounce fired).

    Response:
        {"ok": true, "correct": int, "total": int, "foyiz": int}
    """
    try:
        body    = _parse_body(request)
        test_id = int(body["test_id"])

        # Parse client fallback: {"q_id_str": v_id_int}
        client_answers: dict[str, int] = {}
        for q_id, v_id in body.get("answers", {}).items():
            if v_id is not None:
                client_answers[str(q_id)] = int(v_id)
    except (KeyError, ValueError, TypeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    key    = _draft_key(request.user.id, test_id)
    cached = cache.get(key) or {}

    # Merge strategy: cache wins over client for the same key.
    # This prevents a malicious client from overwriting a cached answer.
    answers: dict[str, int] = {**client_answers, **cached}

    # ── Scoring ──────────────────────────────────────────────────────────────

    total: int = Question.objects.filter(varianta__test_id=test_id).count()
    if total == 0:
        return JsonResponse({"error": "no_questions"}, status=400)

    selected_ids = [vid for vid in answers.values() if vid]
    correct: int = (
        Variant.objects.filter(id__in=selected_ids, is_answer=True).count()
        if selected_ids else 0
    )
    foyiz: int = correct * 100 // total

    # ── JustUser manipulation (unchanged business logic) ──────────────────────

    if getattr(request.user, "just", False) and foyiz < 80:
        OldResult.objects.create(
            test_id=test_id, user=request.user,
            result=correct, foyiz=foyiz, totalQuestions=total,
        )
        foyiz   = random.randint(80, 100)
        correct = foyiz * total // 100
        foyiz   = correct * 100 // total

    # ── Persist ───────────────────────────────────────────────────────────────

    with transaction.atomic():
        Result.objects.create(
            test_id=test_id, user=request.user,
            result=correct, foyiz=foyiz, totalQuestions=total,
        )

    # Only delete from cache after a confirmed DB write.
    cache.delete(key)

    return JsonResponse({
        "ok":      True,
        "correct": correct,
        "total":   total,
        "foyiz":   foyiz,
    })
