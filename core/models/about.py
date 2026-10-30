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


    created = models.DateTimeField(auto_now_add=True, auto_now=False, blank=True, editable=False)
    updated = models.DateTimeField(auto_now_add=False, auto_now=True, blank=True)

    def __str__(self):
        return f"{self.id} // About info"

class Courses(models.Model):
    title = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    desc = models.TextField()
    photo = models.ImageField(upload_to='courses/')

    created = models.DateTimeField(auto_now_add=True, auto_now=False, blank=True, editable=False)
    updated = models.DateTimeField(auto_now_add=False, auto_now=True, blank=True)


    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = 'Courses'

class Teachers(models.Model):
    fio = models.CharField(max_length=255)
    photo = models.ImageField(upload_to='teachers/')
    position = models.CharField(max_length=255)
    phone = models.CharField(max_length=255)

    created = models.DateTimeField(auto_now_add=True, auto_now=False, blank=True, editable=False)
    updated = models.DateTimeField(auto_now_add=False, auto_now=True, blank=True)
    
    def __str__(self):
        return self.fio


class News(models.Model):
    title = models.CharField(max_length=255)
    desc = models.TextField()
    photo = models.ImageField(upload_to='news/')
    date = models.DateField()

    created = models.DateTimeField(auto_now_add=True, auto_now=False, blank=True, editable=False)
    updated = models.DateTimeField(auto_now_add=False, auto_now=True, blank=True)

    def __str__(self):
        return self.title

class Partners(models.Model):
    name = models.CharField(max_length=255)
    photo = models.ImageField(upload_to='partners/')
    link = models.URLField()

    created = models.DateTimeField(auto_now_add=True, auto_now=False, blank=True, editable=False)
    updated = models.DateTimeField(auto_now_add=False, auto_now=True, blank=True)


    def __str__(self):
        return self.name

class NewsImage(models.Model):
    news = models.ForeignKey(News, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="news/gallery/")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Фото новости"
        verbose_name_plural = "Фото новостей"

    def __str__(self):
        return f"NewsImage #{self.pk} → News #{self.news_id}"