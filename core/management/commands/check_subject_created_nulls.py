from django.core.management.base import BaseCommand
from core.models import Subject


class Command(BaseCommand):
    help = "Показывает количество Subject с created=NULL перед миграцией на NOT NULL"

    def handle(self, *args, **options):
        total = Subject.objects.count()
        null_count = Subject.objects.filter(created__isnull=True).count()

        self.stdout.write(f"Всего записей Subject: {total}")
        self.stdout.write(f"Записей с created=NULL: {null_count}")

        if null_count == 0:
            self.stdout.write(self.style.SUCCESS(
                "NULL не найдено — backfill не требуется, AlterField(null=False) можно применять сразу."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"Найдено {null_count} строк с NULL — backfill ОБЯЗАТЕЛЕН перед AlterField(null=False)."
            ))