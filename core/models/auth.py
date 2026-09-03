from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models

from core.models.classrooms import Potok, Subject

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

    ВАЖНО: поля ``in_dashboard`` и ``interval`` удалены из модели — состояние
    доступа к дашборду и sliding-window сессии теперь хранятся в Redis
    (см. ключи ``user:{user_id}:dashboard_auth`` и ``user:{user_id}:active_device``
    в Shared Context), а не в SQL-базе.
    """

    # ── Личные данные ─────────────────────────────────────
    username = models.CharField(max_length=256, unique=True, null=True, blank=True)
    name = models.CharField(max_length=256, default=" ", null=True)
    last_name = models.CharField(max_length=256, null=True)
    potok = models.ForeignKey(Potok, on_delete=models.SET_NULL, null=True)
    position = models.CharField(max_length=256, null=True, blank=True)
    company_name = models.CharField(max_length=256, null=True, blank=True)
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True)
    # ── Настройки ─────────────────────────────────────────
    # log = models.JSONField(default=dict, null=True, blank=True)
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
    # in_dashboard и interval удалены (см. docstring выше) — сессии дашборда
    # больше не зависят от SQL-базы данных.
    # just = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_result = models.BooleanField(default=False)

    # ── Временные метки ───────────────────────────────────
    # null убран — created теперь опорное поле сортировки Keyset Engine
    # для tip="user" (составное сравнение курсора (created, id)). Тип
    # ОСТАЁТСЯ DateField (дневная точность) — несколько User с одинаковым
    # created — штатная ситуация, tie-break по id полностью её покрывает.
    # Перед AlterField(null=False) существующие NULL нужно забэкфиллить
    # (см. management-команду backfill_user_created).
    created = models.DateField(
        auto_now_add=True, auto_now=False, editable=False
    )
    updated = models.DateTimeField(auto_now_add=False, auto_now=True, null=True)

    objects = CustomUserManager()

    USERNAME_FIELD = "username"
    # role намеренно отсутствует: create_superuser() ставит SUPERADMIN автоматически
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "1. Пользователи"
        indexes = [
            # Опорный индекс Keyset Engine — составное сравнение курсора
            # Q(created__lt=X) | Q(created=X, id__lt=Y). Обратный DESC-индекс
            # намеренно не создаётся (тот же паттерн, что и у Result/Question).
            models.Index(fields=['created', 'id'], name='user_created_id_idx'),
        ]
        
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
            "potok": self.potok,
            "created": self.created,
            "updated": self.updated,
        }

    def __str__(self) -> str:
        return f"{self.full_name()} || {self.username}"

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.full_name()
        return super().save(*args, **kwargs)
