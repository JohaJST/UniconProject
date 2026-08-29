from django.db import models


class Subject(models.Model):
    name = models.CharField(max_length=255)
    created = models.DateTimeField(auto_now_add=True, auto_now=False, null=True, blank=True, editable=False)
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


class Potok(models.Model):
    start = models.DateField(null=True, blank=True)
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