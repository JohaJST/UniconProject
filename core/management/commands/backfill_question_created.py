"""
core/management/commands/backfill_question_created.py
───────────────────────────────────────────────────────
Backfill Question.created=NULL -> текущий timestamp, ДО применения
AlterField(null=False).

.update() — bulk SQL UPDATE, не .save() построчно: не проходит через
auto_now_add (он на UPDATE всё равно не сработал бы) и не тратит один
round-trip на строку. Все NULL-записи получают ОДИНАКОВЫЙ timestamp
момента запуска команды — реальная дата создания для них уже потеряна,
это осознанный компромисс (тот же, что применялся для Result.created).

Запуск: python manage.py backfill_question_created
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Question


class Command(BaseCommand):
    help = "Backfill Question.created=NULL -> now() перед миграцией на NOT NULL"

    def handle(self, *args, **options):
        null_qs = Question.objects.filter(created__isnull=True)
        count = null_qs.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS("NULL не найдено — backfill не требуется."))
            return

        now = timezone.now()
        updated = null_qs.update(created=now)

        self.stdout.write(self.style.SUCCESS(
            f"Backfill завершён: {updated} строк Question.created установлены в {now.isoformat()}"
        ))
        