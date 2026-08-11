"""
core/media_utils.py
─────────────────────
Безопасная обработка загружаемых пользователем изображений.

Пайплайн:
  1. Быстрая проверка размера файла (ДО чтения содержимого).
  2. Отклонение SVG по расширению/content_type (потенциальный XSS-вектор,
     Pillow всё равно не умеет их растеризовать).
  3. Валидация через Pillow (Image.verify()) с защитой от decompression
     bomb и битых/поддельных файлов.
  4. Повторное открытие + load() (verify() делает объект непригодным
     для дальнейшей работы).
  5. Нормализация цветового режима (RGB/RGBA).
  6. Даунскейл по наибольшей стороне (LANCZOS).
  7. Кодирование в WEBP и упаковка в ContentFile со случайным именем.

Использовать только эту функцию для сохранения пользовательских
изображений (аватары, вопросы теста, фото курсов/новостей и т.д.) —
никогда не сохранять файл, пришедший от пользователя, "как есть".
"""
from __future__ import annotations

import io
import uuid

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from PIL import Image, UnidentifiedImageError
from PIL import Image as PILImage  # для DecompressionBombError ниже

try:
    # В новых версиях Pillow исключение доступно как Image.DecompressionBombError
    from PIL import DecompressionBombError
except ImportError:  # pragma: no cover — старые версии Pillow
    DecompressionBombError = Image.DecompressionBombError  # type: ignore[attr-defined]


# ─────────────────────────────────────────────────────────────────────────────
# Ограничение Pillow против decompression bomb атак (изображения с
# гигантским разрешением при малом весе файла).
# ─────────────────────────────────────────────────────────────────────────────
Image.MAX_IMAGE_PIXELS = 40_000_000


class InvalidImageError(Exception):
    """
    Загруженный файл не прошёл проверку и не может быть обработан
    как безопасное изображение (не тот тип, повреждён, слишком большой
    вес/разрешение, подделка под изображение и т.п.).
    """
    pass


# Расширения/MIME, которые заведомо отклоняются, даже не доходя до Pillow.
_FORBIDDEN_EXTENSIONS = (".svg",)
_FORBIDDEN_CONTENT_TYPES = ("image/svg+xml",)


def _reject_svg(uploaded_file: UploadedFile) -> None:
    """Отклоняет SVG по расширению имени файла и по content_type."""
    name = (getattr(uploaded_file, "name", "") or "").lower()
    if name.endswith(_FORBIDDEN_EXTENSIONS):
        raise InvalidImageError("SVG-файлы не поддерживаются")

    content_type = (getattr(uploaded_file, "content_type", "") or "").lower()
    if content_type in _FORBIDDEN_CONTENT_TYPES:
        raise InvalidImageError("SVG-файлы не поддерживаются")


def _check_size(uploaded_file: UploadedFile, max_size_mb: float) -> None:
    """
    Проверяет вес файла ДО чтения содержимого — используем метаданные
    файла (`.size`), а не читаем поток в память.
    """
    max_size_bytes = max_size_mb * 1024 * 1024
    size = getattr(uploaded_file, "size", None)
    if size is None:
        raise InvalidImageError("Не удалось определить размер файла")
    if size > max_size_bytes:
        raise InvalidImageError(
            f"Размер файла превышает допустимый лимит в {max_size_mb} МБ"
        )


def _normalize_mode(image: Image.Image) -> Image.Image:
    """
    Приводит изображение к RGB или RGBA:
      - если режим уже RGB/RGBA — не трогаем;
      - если у изображения есть альфа-канал или прозрачность (info["transparency"],
        режимы вроде "P" с прозрачной палитрой, "LA" и т.п.) — конвертируем в RGBA;
      - иначе — в RGB.
    """
    if image.mode in ("RGB", "RGBA"):
        return image

    has_alpha = (
        "A" in image.mode
        or image.mode == "P" and "transparency" in image.info
    )

    return image.convert("RGBA") if has_alpha else image.convert("RGB")


def _downscale(image: Image.Image, max_dimension: int) -> Image.Image:
    """
    Уменьшает изображение так, чтобы наибольшая сторона не превышала
    ``max_dimension``, сохраняя пропорции. Если изображение уже меньше —
    не апскейлит.
    """
    width, height = image.size
    largest_side = max(width, height)

    if largest_side <= max_dimension:
        return image

    scale = max_dimension / float(largest_side)
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))

    return image.resize(new_size, Image.LANCZOS)


def process_uploaded_image(
    uploaded_file: UploadedFile,
    max_size_mb: float = 5,
    max_dimension: int = 1200,
) -> ContentFile:
    """
    Валидирует и безопасно обрабатывает загруженное пользователем изображение.

    :param uploaded_file: файл из request.FILES
    :param max_size_mb: максимальный допустимый вес файла в мегабайтах
    :param max_dimension: максимальная длина большей стороны итогового изображения
    :raises InvalidImageError: файл не прошёл валидацию по любой из причин
        (запрещённый тип, превышен размер, повреждён/поддельный файл,
        decompression bomb и т.д.)
    :return: ContentFile с обработанным изображением в формате WEBP,
        имя файла — ``<uuid4().hex>.webp``
    """
    # 1. Проверка веса — до чтения содержимого файла.
    _check_size(uploaded_file, max_size_mb)

    # 2. Отклоняем SVG по расширению и content_type.
    _reject_svg(uploaded_file)

    # 3. Валидация через Pillow: открываем и вызываем verify().
    uploaded_file.seek(0)
    try:
        probe = Image.open(uploaded_file)
        probe.verify()
    except DecompressionBombError as exc:
        raise InvalidImageError("Изображение имеет слишком большое разрешение") from exc
    except UnidentifiedImageError as exc:
        raise InvalidImageError("Файл не распознан как изображение") from exc
    except (OSError, ValueError) as exc:
        raise InvalidImageError("Файл повреждён или имеет неверный формат") from exc

    # 4. verify() делает объект Image непригодным для дальнейшей работы —
    #    открываем заново и полноценно загружаем пиксельные данные.
    uploaded_file.seek(0)
    try:
        image = Image.open(uploaded_file)
        image.load()
    except DecompressionBombError as exc:
        raise InvalidImageError("Изображение имеет слишком большое разрешение") from exc
    except UnidentifiedImageError as exc:
        raise InvalidImageError("Файл не распознан как изображение") from exc
    except (OSError, ValueError) as exc:
        raise InvalidImageError("Файл повреждён или имеет неверный формат") from exc

    # 5. Нормализация цветового режима.
    image = _normalize_mode(image)

    # 6. Даунскейл по наибольшей стороне.
    image = _downscale(image, max_dimension)

    # 7. Кодирование в WEBP и упаковка в ContentFile со случайным именем.
    buffer = io.BytesIO()
    try:
        image.save(buffer, format="WEBP", quality=85)
    except (OSError, ValueError) as exc:
        raise InvalidImageError("Не удалось сохранить изображение") from exc

    buffer.seek(0)
    filename = f"{uuid.uuid4().hex}.webp"

    return ContentFile(buffer.read(), name=filename)