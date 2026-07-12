from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models

from core.models.classrooms import ClassRooms

# ─────────────────────────────────────────────────────────────────────────────
# Role enum
# ─────────────────────────────────────────────────────────────────────────────


class Role(models.IntegerChoices):
    SUPERADMIN = 1, "Суперадмин"
    ADMIN = 2, "Администратор"
    TEACHER = 3, "Учитель"
    STUDENT = 4, "Ученик"


# ─────────────────────────────────────────────────────────────────────────────
# Manager
# ─────────────────────────────────────────────────────────────────────────────


class CustomUserManager(BaseUserManager):
    def create_user(self, username, password=None, role=Role.STUDENT, **extra_fields):
        """Создать обычного пользователя."""
        user = self.model(username=username, role=role, **extra_fields)
        if password is not None:
            user.set_password(password)
        user.save()
        return user

    def create_superuser(self, username, password, **extra_fields):
        """Создать суперадмина (для manage.py createsuperuser)."""
        return self.create_user(
            username,
            password,
            role=Role.SUPERADMIN,
            **extra_fields,
        )


# ─────────────────────────────────────────────────────────────────────────────
# User
# ─────────────────────────────────────────────────────────────────────────────


class User(AbstractBaseUser):
    """
    Пользователь системы.

    Роли хранятся в одном поле ``role`` (см. :class:`Role`).
    Свойства ``is_admin``, ``is_staff``, ``is_superuser`` вычисляются
    на лету — весь существующий код шаблонов и вьюшек работает без изменений.
    """

    # ── Личные данные ─────────────────────────────────────
    username = models.CharField(max_length=256, unique=True)
    name = models.CharField(max_length=256, default=" ", null=True)
    last_name = models.CharField(max_length=256, null=True)
    classroom = models.ForeignKey(ClassRooms, on_delete=models.SET_NULL, null=True)
    birthday = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)

    # ── Настройки ─────────────────────────────────────────
    log = models.JSONField(default=dict, null=True)
    lang = models.CharField(
        default="uz",
        max_length=2,
        null=True,
        choices=[("uz", "Uzbek"), ("ru", "Russian"), ("en", "English")],
    )

    # ── Роль (единое поле вместо is_admin / is_staff / is_superuser / ut) ──
    role = models.SmallIntegerField(
        verbose_name="Роль",
        choices=Role.choices,
        default=Role.STUDENT,
    )

    # ── Служебные флаги ───────────────────────────────────
    just = models.BooleanField(default=False)
    in_dashboard = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    interval = models.DateTimeField(
        auto_now_add=True,
        auto_now=False,
        null=True,
        blank=True,
        editable=True,
    )

    # ── Временные метки ───────────────────────────────────
    created = models.DateField(
        auto_now_add=True, auto_now=False, null=True, editable=False
    )
    updated = models.DateTimeField(auto_now_add=False, auto_now=True, null=True)

    objects = CustomUserManager()

    USERNAME_FIELD = "username"
    # role намеренно отсутствует: create_superuser() ставит SUPERADMIN автоматически
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "1. Пользователи"

    # ── Role helpers ──────────────────────────────────────

    def get_role(self) -> dict:
        """
        Возвращает подробную информацию о роли пользователя.

        Пример::

            user.get_role()
            # {
            #   'id': 2,
            #   'name': 'Администратор',
            #   'is_superadmin': False,
            #   'is_admin': True,
            #   'is_teacher': False,
            #   'is_student': False,
            # }
        """
        return {
            "id": self.role,
            "name": self.get_role_display(),
            "is_superadmin": self.role == Role.SUPERADMIN,
            "is_admin": self.role <= Role.ADMIN,
            "is_teacher": self.role == Role.TEACHER,
            "is_student": self.role == Role.STUDENT,
        }

    # ── Computed booleans (не поля БД) ───────────────────

    @property
    def is_superuser(self) -> bool:
        """Суперадмин — полный доступ, включая Django-admin."""
        return self.role == Role.SUPERADMIN

    @property
    def is_staff(self) -> bool:
        """True для Admin и Superadmin — открывает доступ к Django-admin."""
        return self.role <= Role.ADMIN

    @property
    def is_admin(self) -> bool:
        """True для Admin и Superadmin — используется в шаблонах и вьюшках."""
        return self.role <= Role.ADMIN

    @property
    def is_teacher(self) -> bool:
        return self.role == Role.TEACHER

    @property
    def is_student(self) -> bool:
        return self.role == Role.STUDENT

    # ── Django permission API (без PermissionsMixin) ──────

    def has_perm(self, perm, obj=None) -> bool:
        """Суперадмин имеет все разрешения; остальные — нет."""
        return self.is_active and self.is_superuser

    def has_module_perms(self, app_label) -> bool:
        """Суперадмин и Администратор видят Django-admin."""
        return self.is_active and self.is_staff

    # ── Строковые методы ─────────────────────────────────

    def full_name(self) -> str:
        return f"{self.last_name} {self.name}"

    def personal(self) -> dict:
        return {
            "username": self.username,
            "name": self.name,
            "lang": self.lang,
            "role": self.get_role(),
            "classroom": self.classroom,
            "created": self.created,
            "updated": self.updated,
        }

    def __str__(self) -> str:
        return f"{self.full_name()} || {self.username}"

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.full_name()
        return super().save(*args, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# OTP
# ─────────────────────────────────────────────────────────────────────────────


class Otp(models.Model):
    key = models.CharField(max_length=512)
    username = models.CharField(max_length=20)
    is_expired = models.BooleanField(default=False)
    tries = models.SmallIntegerField(default=0)
    extra = models.JSONField(default=dict)
    is_verified = models.BooleanField(default=False)
    step = models.CharField(max_length=25)

    created = models.DateTimeField(auto_now=False, auto_now_add=True, editable=False)
    updated = models.DateTimeField(auto_now=True, auto_now_add=False)

    def save(self, *args, **kwargs):
        if self.tries >= 3 or self.is_verified:
            self.is_expired = True
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.username} -> {self.key}"

    class Meta:
        verbose_name_plural = "8. One Time Password"


# ─────────────────────────────────────────────────────────────────────────────
# TG_User
# ─────────────────────────────────────────────────────────────────────────────


class TG_User(models.Model):
    user_id = models.BigIntegerField(unique=True)
    phone = models.CharField("Phone", unique=True, max_length=50)
    username = models.CharField(max_length=128, null=True)
    first_name = models.CharField(max_length=255, null=True)
    last_name = models.CharField(max_length=255, null=True)

    log = models.JSONField(default=dict)
    lang = models.CharField(
        default="uz",
        max_length=2,
        choices=[("uz", "Uzbek"), ("ru", "Russian"), ("en", "English")],
    )
    is_admin = models.BooleanField(default=False)

    created = models.DateTimeField(
        auto_now_add=True, auto_now=False, null=True, editable=False
    )
    updated = models.DateTimeField(auto_now_add=False, auto_now=True, null=True)

    class Meta:
        verbose_name_plural = "0. TG_Users"

    def full_name(self) -> str:
        return f"{self.last_name} {self.first_name}"

    def tg_user_format(self) -> dict:
        return {
            "tg_user_id": self.user_id,
            "mobile": self.phone,
            "username": self.username,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "lang": self.lang,
            "log": self.log,
            "created": self.created,
            "updated": self.updated,
        }

    def __str__(self) -> str:
        return f"{self.full_name()} || {self.phone}"
