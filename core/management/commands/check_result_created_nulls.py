
"""
core/management/commands/check_result_created_nulls.py
──────────────────────────────────────────────────────────
Диагностика перед миграцией 00XX_result_created_not_null: сколько строк
Result имеют created=NULL и сколько всего строк в таблице.

Запуск: python manage.py check_result_created_nulls
"""
from django.core.management.base import BaseCommand

from core.models import Result


class Command(BaseCommand):
    help = "Показывает количество Result с created=NULL перед миграцией на NOT NULL"

    def handle(self, *args, **options):
        total = Result.objects.count()
        null_count = Result.objects.filter(created__isnull=True).count()

        self.stdout.write(f"Всего записей Result: {total}")
        self.stdout.write(f"Записей с created=NULL: {null_count}")

        if null_count == 0:
            self.stdout.write(self.style.SUCCESS(
                "NULL не найдено — data-миграция (RunPython backfill) отработает как no-op."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"Найдено {null_count} строк с NULL — data-миграция обязательна перед AlterField(null=False)."
            ))