"""
core/management/commands/backfill_user_created.py
─────────────────────────────────────────────────────
Backfill User.created=NULL -> текущая дата, ДО применения
AlterField(null=False).

.update() — bulk SQL UPDATE, не .save() построчно: не проходит через
auto_now_add (он на UPDATE всё равно не сработал бы) и не тратит один
round-trip на строку. Все NULL-записи получают ОДИНАКОВУЮ дату момента
запуска команды — реальная дата регистрации для них уже потеряна, это
осознанный компромисс (тот же, что применялся для Result.created и
Question.created). Тип поля — DateField (дневная точность), поэтому
пишем timezone.now().date(), а не полный datetime.

Запуск: python manage.py backfill_user_created
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import User


class Command(BaseCommand):
    help = "Backfill User.created=NULL -> today() перед миграцией на NOT NULL"

    def handle(self, *args, **options):
        null_qs = User.objects.filter(created__isnull=True)
        count = null_qs.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS("NULL не найдено — backfill не требуется."))
            return

        today = timezone.now().date()
        updated = null_qs.update(created=today)

        self.stdout.write(self.style.SUCCESS(
            f"Backfill завершён: {updated} строк User.created установлены в {today.isoformat()}"
        ))