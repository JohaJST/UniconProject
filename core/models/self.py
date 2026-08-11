
import json

from django.db import models

class SelfQuestion(models.Model):
    text = models.CharField(max_length=255)
    img = models.ImageField(upload_to='self_questions/', null=True, blank=True)
    needs_review = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.id} // {self.text} // {'Yes' if self.img else 'No'}"

        
class SelfAnswer(models.Model):
    question = models.ForeignKey(SelfQuestion, on_delete=models.CASCADE)
    text = models.CharField(max_length=255)
    img = models.ImageField(upload_to='self_answers/', null=True, blank=True)
    is_correct = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.question.text} ({'True' if self.is_correct else 'False'})"

class SelfResult(models.Model):
    fio = models.CharField(max_length=255, default="No FIO")
    score = models.IntegerField(default=0)
    created = models.DateField(
        auto_now_add=True, auto_now=False, null=True, editable=False
    )
    updated = models.DateTimeField(auto_now_add=False, auto_now=True, null=True)
    foiz = models.FloatField(default=0.0)

    def save(self, *args, **kwargs):
        self.foiz = (self.score / 20) * 100
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.fio} // {self.score} // {self.created}"

class SelfStudy(models.Model):
    html_text = models.TextField(null=True, blank=True)
    style_text = models.TextField(null=True, blank=True)
    js_text = models.TextField(null=True, blank=True)
    
    def __str__(self):
        return self.id

class SelfImg(models.Model):
    img = models.ImageField(upload_to='self_imgs/')
    name = models.CharField(max_length=255, default="No Name")

    def __str__(self):
        return self.name
