from django.db import models


class Subject(models.Model):
    name = models.CharField(max_length=255)
    # null убран (аналогично Result/Question/User) — created теперь опорное
    # поле сортировки Keyset Engine для tip="subject", NULL там ломает
    # составное сравнение курсора (created, id). Перед AlterField(null=False)
    # существующие NULL нужно забэкфиллить — см. management-команду
    # backfill_subject_created.
    created = models.DateTimeField(auto_now_add=True, auto_now=False, blank=True, editable=False)
    updated = models.DateTimeField(auto_now_add=False, auto_now=True, null=True, blank=True)

    def __str__(self):
        return self.name

    def subject_format(self):
        return {
            self.name,
            self.created,
            self.updated
        }

    class Meta:
        verbose_name_plural = '3. Subject(Kurs)'
        indexes = [
            # Опорный индекс Keyset Engine — составное сравнение курсора
            # Q(created__lt=X) | Q(created=X, id__lt=Y).
            models.Index(fields=['created', 'id'], name='subject_created_id_idx'),
        ]


class Potok(models.Model):
    # null убран у start (это поле сортировки списка "potok") — по тем же
    # причинам, что и у created в остальных списках: NULL несовместим
    # с составным сравнением курсора Keyset Engine. Перед AlterField
    # (null=False) существующие NULL нужно забэкфиллить — см.
    # management-команду backfill_potok_start.
    start = models.DateField(blank=True)
    end = models.DateField(null=True, blank=True)

    created = models.DateTimeField(auto_now_add=True, auto_now=False, null=True, blank=True, editable=False)
    updated = models.DateTimeField(auto_now_add=False, auto_now=True, null=True, blank=True)

    @property
    def date_range(self) -> str:
        """Человекочитаемый диапазон потока: «22 мая 2026г - 27 мая 2026г»."""
        months = ("января", "февраля", "марта", "апреля", "мая", "июня",
                  "июля", "августа", "сентября", "октября", "ноября", "декабря")

        def fmt(dt):
            if not dt:
                return "—"
            return f"{dt.day} {months[dt.month - 1]} {dt.year}г"

        return f"{fmt(self.start)} - {fmt(self.end)}"

    def __str__(self):
        return self.date_range

    class Meta:
        ordering = ['-start']
        indexes = [
            # Опорный индекс Keyset Engine для tip="potok" — sort_field="start"
            # (НЕ "created", это осознанная бизнес-сортировка потока по
            # дате начала). Составное сравнение курсора:
            # Q(start__lt=X) | Q(start=X, id__lt=Y).
            models.Index(fields=['start', 'id'], name='potok_start_id_idx'),
        ]