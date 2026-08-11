"""
core/tests.py — Unit-тесты для core/media_utils.py

Покрытие:
  - process_uploaded_image (основная функция)
  - _reject_svg, _check_size, _normalize_mode, _downscale (хелперы)

Все тесты используют исключительно in-memory изображения (Pillow + BytesIO) —
файловая система не задействована.
"""

import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from core.media_utils import (
    InvalidImageError,
    _check_size,
    _downscale,
    _normalize_mode,
    _reject_svg,
    process_uploaded_image,
)
from PIL import Image, ImageDraw


# ═══════════════════════════════════════════════════════════════════════════════
# Хелперы для создания in-memory изображений / файлов
# ═══════════════════════════════════════════════════════════════════════════════

def _make_upload(mode: str, size: tuple[int, int], fmt: str, name: str, **save_kw) -> SimpleUploadedFile:
    """
    Создаёт SimpleUploadedFile с настоящим изображением в заданном формате.
    """
    img = Image.new(mode, size, color=(120, 80, 200))
    buf = io.BytesIO()
    img.save(buf, format=fmt, **save_kw)
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type=f"image/{fmt.lower()}")


def _make_text_jpg() -> SimpleUploadedFile:
    """Файл с текстовым содержимым, замаскированный под .jpg."""
    return SimpleUploadedFile("fake.jpg", b"this is not an image", content_type="image/jpeg")


def _make_svg_file() -> SimpleUploadedFile:
    """Файл .svg (должен быть отклонён на этапе _reject_svg)."""
    return SimpleUploadedFile("icon.svg", b"<svg>...</svg>", content_type="image/svg+xml")


def _make_oversized(max_mb: float) -> SimpleUploadedFile:
    """Файл больше допустимого размера."""
    size = int(max_mb * 1024 * 1024 + 1)
    return SimpleUploadedFile("big.jpg", b"x" * size, content_type="image/jpeg")


# ═══════════════════════════════════════════════════════════════════════════════
# Тесты: process_uploaded_image
# ═══════════════════════════════════════════════════════════════════════════════

class ProcessUploadedImageTests(SimpleTestCase):
    """Интеграционные тесты основного пайплайна."""

    # ── 1. Фейковый .jpg (текст) → InvalidImageError ─────────────────────────

    def test_fake_jpg_raises_invalid_image_error(self):
        """Текстовый файл с расширением .jpg должен быть отклонён на этапе Pillow."""
        fake = _make_text_jpg()

        with self.assertRaises(InvalidImageError) as ctx:
            process_uploaded_image(fake)

        self.assertIn("не распознан", str(ctx.exception))

    # ── 2. Крупный PNG (3000×2000) → даунскейл ≤ 1200px, WEBP ────────────────

    def test_large_png_resized_and_webp(self):
        """3000×2000 PNG → сжимается до ≤ 1200 по большей стороне, формат WEBP."""
        img = Image.new("RGB", (3000, 2000), color=(10, 20, 30))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        uploaded = SimpleUploadedFile("big.png", buf.read(), content_type="image/png")

        result = process_uploaded_image(uploaded, max_dimension=1200)

        # Проверяем, что результат — WEBP с ожидаемыми размерами.
        result.seek(0)
        processed = Image.open(result)
        self.assertEqual(processed.format, "WEBP")
        self.assertLessEqual(max(processed.size), 1200)

        # Проверяем имя (uuid4 hex + .webp, длина 32 + 5 = 37 символов без дефисов).
        self.assertTrue(result.name.endswith(".webp"))
        self.assertEqual(len(result.name), 32 + 5)

    def test_image_already_small_not_upscaled(self):
        """Если изображение уже ≤ max_dimension — не апскейлим."""
        uploaded = _make_upload("RGB", (400, 300), "PNG", "small.png")
        result = process_uploaded_image(uploaded, max_dimension=1200)

        result.seek(0)
        processed = Image.open(result)
        self.assertLessEqual(max(processed.size), 1200)
        # Стороны должны остаться 400×300 (не апскейл).
        self.assertEqual(processed.size, (400, 300))

    # ── 3. CMYK → успешная конвертация в WEBP ────────────────────────────────

    def test_cmyk_converts_to_rgb_webp(self):
        """CMYK-изображение должно нормализоваться в RGB и сохраниться как WEBP."""
        img = Image.new("CMYK", (400, 300), color=(50, 0, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)
        uploaded = SimpleUploadedFile("cmyk.jpg", buf.read(), content_type="image/jpeg")

        result = process_uploaded_image(uploaded)

        result.seek(0)
        processed = Image.open(result)
        self.assertEqual(processed.format, "WEBP")
        # Режим после нормализации должен быть RGB (нет альфа-канала в CMYK).
        self.assertEqual(processed.mode, "RGB")

    # ── 4. Превышение Image.MAX_IMAGE_PIXELS → InvalidImageError ─────────────

    def test_decompression_bomb_raises_invalid_image_error(self):
        """
        Pillow должен бросить DecompressionBombError, когда размер изображения
        превышает MAX_IMAGE_PIXELS. Временно снижаем порог до 100 px² через
        прямое присваивание (patch.object не перехватывает уже
        проимпортированный модуль).
        """
        # Создаём изображение 200×200 (40 000 px) — гарантированно > 100.
        img = Image.new("RGB", (200, 200), color=(1, 2, 3))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        uploaded = SimpleUploadedFile("bomb.png", buf.read(), content_type="image/png")

        import PIL.Image as _PILImage
        saved = _PILImage.MAX_IMAGE_PIXELS
        _PILImage.MAX_IMAGE_PIXELS = 100          # сбрасываем порог
        try:
            with self.assertRaises(InvalidImageError) as ctx:
                process_uploaded_image(uploaded)
            self.assertIn("разрешение", str(ctx.exception))
        finally:
            _PILImage.MAX_IMAGE_PIXELS = saved    # восстанавливаем

    # ── 5. Файл .svg → InvalidImageError ──────────────────────────────────────

    def test_svg_extension_rejected(self):
        """SVG по расширению имени файла должен быть отклонён."""
        svg = _make_svg_file()

        with self.assertRaises(InvalidImageError) as ctx:
            process_uploaded_image(svg)

        self.assertIn("SVG", str(ctx.exception))

    def test_svg_content_type_rejected(self):
        """SVG по content_type (даже без .svg в имени) должен быть отклонён."""
        svg = SimpleUploadedFile("icon", b"<svg>...</svg>", content_type="image/svg+xml")

        with self.assertRaises(InvalidImageError) as ctx:
            process_uploaded_image(svg)

        self.assertIn("SVG", str(ctx.exception))

    # ── Дополнительные кейсы ─────────────────────────────────────────────────

    def test_empty_file_raises_invalid_image_error(self):
        """Пустой файл должен быть отклонён Pillow."""
        empty = SimpleUploadedFile("empty.jpg", b"", content_type="image/jpeg")

        with self.assertRaises(InvalidImageError):
            process_uploaded_image(empty)

    def test_oversized_file_raises_before_pillow(self):
        """Файл > max_size_mb должен быть отклонён ДО вызова Pillow."""
        big = _make_oversized(max_mb=5)

        with self.assertRaises(InvalidImageError) as ctx:
            process_uploaded_image(big, max_size_mb=5)

        self.assertIn("Размер файла превышает", str(ctx.exception))

    def test_rgba_preserves_alpha(self):
        """RGBA-изображение должно сохранить альфа-канал в WEBP."""
        img = Image.new("RGBA", (200, 150), color=(255, 0, 0, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        uploaded = SimpleUploadedFile("rgba.png", buf.read(), content_type="image/png")

        result = process_uploaded_image(uploaded)

        result.seek(0)
        processed = Image.open(result)
        self.assertEqual(processed.mode, "RGBA")
        self.assertEqual(processed.format, "WEBP")


# ═══════════════════════════════════════════════════════════════════════════════
# Тесты: вспомогательные функции (_reject_svg, _check_size, и т.д.)
# ═══════════════════════════════════════════════════════════════════════════════

class RejectSvgTests(SimpleTestCase):
    """Unit-тесты внутренней _reject_svg."""

    def test_svg_extension_rejected(self):
        with self.assertRaises(InvalidImageError):
            _reject_svg(SimpleUploadedFile("icon.svg", b"", content_type=""))

    def test_svg_content_type_rejected(self):
        with self.assertRaises(InvalidImageError):
            _reject_svg(SimpleUploadedFile("icon", b"", content_type="image/svg+xml"))

    def test_png_passes(self):
        """PNG не должен отклоняться."""
        _reject_svg(SimpleUploadedFile("photo.png", b"", content_type="image/png"))

    def test_no_name_no_content_type_passes(self):
        """Если нет ни имени, ни content_type — не падаем, пропускаем."""
        # Django-валидация не разрешает пустые имена — используем plain object.
        class _FakeFile:
            name = ""
            content_type = ""
        _reject_svg(_FakeFile())


class CheckSizeTests(SimpleTestCase):
    """Unit-тесты _check_size."""

    def test_under_limit_passes(self):
        f = SimpleUploadedFile("ok.jpg", b"x" * 1000, content_type="image/jpeg")
        _check_size(f, max_size_mb=5)

    def test_exactly_at_limit_passes(self):
        size = int(5 * 1024 * 1024)
        f = SimpleUploadedFile("ok.jpg", b"x" * size, content_type="image/jpeg")
        _check_size(f, max_size_mb=5)

    def test_over_limit_raises(self):
        f = _make_oversized(max_mb=5)
        with self.assertRaises(InvalidImageError) as ctx:
            _check_size(f, max_size_mb=5)
        self.assertIn("превышает", str(ctx.exception))

    def test_no_size_raises(self):
        """Объект без атрибута .size → ошибка."""
        class NoSizeFile:
            pass

        with self.assertRaises(InvalidImageError):
            _check_size(NoSizeFile(), max_size_mb=5)


class NormalizeModeTests(SimpleTestCase):
    """Unit-тесты _normalize_mode."""

    def test_rgb_unchanged(self):
        img = Image.new("RGB", (10, 10))
        result = _normalize_mode(img)
        self.assertEqual(result.mode, "RGB")

    def test_rgba_unchanged(self):
        img = Image.new("RGBA", (10, 10))
        result = _normalize_mode(img)
        self.assertEqual(result.mode, "RGBA")

    def test_cmyk_to_rgb(self):
        img = Image.new("CMYK", (10, 10), color=(0, 0, 0, 0))
        result = _normalize_mode(img)
        self.assertEqual(result.mode, "RGB")

    def test_l_to_rgb(self):
        """Grayscale (L) → RGB."""
        img = Image.new("L", (10, 10))
        result = _normalize_mode(img)
        self.assertEqual(result.mode, "RGB")

    def test_la_to_rgba(self):
        """Grayscale + alpha (LA) → RGBA."""
        img = Image.new("LA", (10, 10))
        result = _normalize_mode(img)
        self.assertEqual(result.mode, "RGBA")


class DownscaleTests(SimpleTestCase):
    """Unit-тесты _downscale."""

    def test_already_small(self):
        img = Image.new("RGB", (400, 300))
        result = _downscale(img, 1200)
        self.assertEqual(result.size, (400, 300))

    def test_landscape_downscale(self):
        """3000×2000 → 1200×800 (max_dim=1200, пропорции сохранены)."""
        img = Image.new("RGB", (3000, 2000))
        result = _downscale(img, 1200)
        self.assertEqual(result.size, (1200, 800))

    def test_portrait_downscale(self):
        """2000×3000 → 800×1200."""
        img = Image.new("RGB", (2000, 3000))
        result = _downscale(img, 1200)
        self.assertEqual(result.size, (800, 1200))

    def test_square_downscale(self):
        """2000×2000 → 1200×1200."""
        img = Image.new("RGB", (2000, 2000))
        result = _downscale(img, 1200)
        self.assertEqual(result.size, (1200, 1200))

    def test_extreme_aspect_ratio(self):
        """5000×100 → 1200×24 (не падаем на экстремальных пропорциях)."""
        img = Image.new("RGB", (5000, 100))
        result = _downscale(img, 1200)
        self.assertEqual(result.size, (1200, 24))


# ═══════════════════════════════════════════════════════════════════════════════
# Интеграционные кейсы по умолчаниям
# ═══════════════════════════════════════════════════════════════════════════════

class ProcessUploadedImageDefaultsTests(SimpleTestCase):
    """Проверяем, что default-аргументы (max_size_mb=5, max_dimension=1200) работают."""

    def test_default_args_work(self):
        """Вызов без явных параметров использует 5 MB / 1200 px."""
        uploaded = _make_upload("RGB", (400, 300), "PNG", "defaults.png")
        result = process_uploaded_image(uploaded)
        self.assertTrue(result.name.endswith(".webp"))


class InvalidImageErrorTests(SimpleTestCase):
    """Самописное исключение."""

    def test_is_exception_subclass(self):
        self.assertTrue(issubclass(InvalidImageError, Exception))

    def test_message_propagated(self):
        with self.assertRaises(InvalidImageError) as ctx:
            raise InvalidImageError("тестовое сообщение")
        self.assertEqual(str(ctx.exception), "тестовое сообщение")
