"""
core/management/commands/check_user_created_nulls.py
──────────────────────────────────────────────────────
Диагностика перед миграцией User.created на NOT NULL: сколько строк
User имеют created=NULL и сколько всего строк в таблице.

Запуск: python manage.py check_user_created_nulls
"""
from django.core.management.base import BaseCommand

from core.models import User


class Command(BaseCommand):
    help = "Показывает количество User с created=NULL перед миграцией на NOT NULL"

    def handle(self, *args, **options):
        total = User.objects.count()
        null_count = User.objects.filter(created__isnull=True).count()

        self.stdout.write(f"Всего записей User: {total}")
        self.stdout.write(f"Записей с created=NULL: {null_count}")

        if null_count == 0:
            self.stdout.write(self.style.SUCCESS(
                "NULL не найдено — backfill не требуется, AlterField(null=False) можно применять сразу."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"Найдено {null_count} строк с NULL — backfill ОБЯЗАТЕЛЕН перед AlterField(null=False)."
            ))