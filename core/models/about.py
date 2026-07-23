from email.policy import default
from logging import info
from os import name
from xxlimited import new

from django.db import models


class About(models.Model):
    info = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    desc = models.TextField()
    goals_info = models.TextField()
    courses_info = models.TextField()
    teachers_info = models.TextField()
    news_info = models.TextField()
    partners_info = models.TextField()
    tg = models.CharField(max_length=255)
    insta = models.CharField(max_length=255)
    fb = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    phone = models.CharField(max_length=255)
    email = models.CharField(max_length=255)
    working_hours = models.CharField(max_length=255)
    footer_info = models.CharField(max_length=255)
    partners = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.id} // About info"

class courses(models.Model):
    title = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    desc = models.TextField()
    photo = models.ImageField(upload_to='courses/')

    def __str__(self):
        return self.name

class Teachers(models.Model):
    fio = models.CharField(max_length=255)
    photo = models.ImageField(upload_to='teachers/')
    position = models.CharField(max_length=255)
    phone = models.CharField(max_length=255)

    
    def __str__(self):
        return self.fio


class News(models.Model):
    title = models.CharField(max_length=255)
    desc = models.TextField()
    photo = models.ImageField(upload_to='news/')
    date = models.DateField()

    def __str__(self):
        return self.title

class Partners(models.Model):
    name = models.CharField(max_length=255)
    photo = models.ImageField(upload_to='partners/')
    link = models.URLField()
    
    def __str__(self):
        return self.name