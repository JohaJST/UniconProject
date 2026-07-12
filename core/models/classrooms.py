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
        verbose_name_plural = '3. Subject'


class ClassRooms(models.Model):
    name = models.CharField(max_length=11)
    created = models.DateTimeField(auto_now_add=True, auto_now=False, null=True, blank=True, editable=False)
    updated = models.DateTimeField(auto_now_add=False, auto_now=True, null=True, blank=True)

    def __str__(self):
        return self.name

    def ClassRoomsFormat(self):
        return {
            self.name,
            self.updated,
            self.created,
        }

    class Meta:
        verbose_name_plural = '2. Class Rooms'


class ClassRoomsSubjects(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    classroom = models.ForeignKey(ClassRooms, on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True, auto_now=False, null=True, blank=True, editable=False)

    def __str__(self):
        return f"{self.subject} || {self.classroom}"
