"""
core/tests/test_pagination_tokens.py — Unit-тесты для
core/dashboard/pagination/tokens.py

Покрытие:
  - encode_cursor / decode_cursor: валидный цикл кодирование -> декодирование
  - decode_cursor: просроченный токен (max_age=0 + sleep)
  - decode_cursor: испорченная подпись (изменённый символ)
  - decode_cursor: мусорная/пустая строка не роняет исключение
  - make_filters_fingerprint: детерминированность независимо от порядка
    ключей и типов значений (фильтров-тест на "смену фильтра" намеренно
    не пишем — сейчас в дашборде нет ни одного реального фильтра списка,
    неоткуда взять реалистичный сценарий, механизм закладывается на будущее)
"""
import time

from django.test import SimpleTestCase

from core.dashboard.pagination.tokens import (
    decode_cursor,
    encode_cursor,
    make_filters_fingerprint,
)


class EncodeDecodeCursorTests(SimpleTestCase):
    """Валидный цикл кодирование -> декодирование."""

    def test_round_trip_valid_token(self):
        token = encode_cursor(
            sort_value="2026-08-24T20:50:00",
            id_value=42,
            direction="next",
            filters_fingerprint="deadbeef",
        )
        data = decode_cursor(token)

        self.assertIsNotNone(data)
        self.assertEqual(data["sort"], "2026-08-24T20:50:00")
        self.assertEqual(data["id"], 42)
        self.assertEqual(data["dir"], "next")
        self.assertEqual(data["fp"], "deadbeef")

    def test_round_trip_int_sort_value(self):
        """sort_field="id" списки (variant/selfquestion) кодируют int напрямую."""
        token = encode_cursor(sort_value=17, id_value=17, direction="prev", filters_fingerprint="")
        data = decode_cursor(token)

        self.assertIsNotNone(data)
        self.assertEqual(data["sort"], 17)
        self.assertEqual(data["id"], 17)

    def test_token_is_nonempty_string(self):
        token = encode_cursor(sort_value=1, id_value=1, direction="next", filters_fingerprint="x")
        self.assertIsInstance(token, str)
        self.assertTrue(len(token) > 0)


class DecodeCursorExpiryTests(SimpleTestCase):
    """Просроченный токен."""

    def test_expired_token_returns_none(self):
        token = encode_cursor(sort_value=1, id_value=1, direction="next", filters_fingerprint="")
        time.sleep(1.1)

        result = decode_cursor(token, max_age=0)
        self.assertIsNone(result)

    def test_fresh_token_within_max_age_is_valid(self):
        token = encode_cursor(sort_value=1, id_value=1, direction="next", filters_fingerprint="")
        result = decode_cursor(token, max_age=3600)
        self.assertIsNotNone(result)


class DecodeCursorTamperingTests(SimpleTestCase):
    """Испорченная подпись / мусорные строки."""

    def test_tampered_signature_returns_none(self):
        token = encode_cursor(sort_value=1, id_value=1, direction="next", filters_fingerprint="")

        # Меняем один символ где-то в середине строки токена — подпись
        # перестаёт совпадать с телом.
        mid = len(token) // 2
        tampered_char = "A" if token[mid] != "A" else "B"
        tampered = token[:mid] + tampered_char + token[mid + 1:]

        result = decode_cursor(tampered)
        self.assertIsNone(result)

    def test_empty_string_returns_none(self):
        self.assertIsNone(decode_cursor(""))

    def test_none_token_returns_none(self):
        self.assertIsNone(decode_cursor(None))

    def test_garbage_string_does_not_raise(self):
        # Совершенно случайный текст в ?cursor= — не должно быть исключения.
        result = decode_cursor("this-is-not-a-real-token-at-all")
        self.assertIsNone(result)

    def test_garbage_string_with_special_chars_does_not_raise(self):
        result = decode_cursor("???///===   spaces and junk!!")
        self.assertIsNone(result)


class MakeFiltersFingerprintTests(SimpleTestCase):
    """Детерминированность отпечатка фильтров."""

    def test_same_params_different_key_order_same_fingerprint(self):
        fp1 = make_filters_fingerprint({"subject": "5", "potok": "3"})
        fp2 = make_filters_fingerprint({"potok": "3", "subject": "5"})
        self.assertEqual(fp1, fp2)

    def test_different_values_different_fingerprint(self):
        fp1 = make_filters_fingerprint({"subject": "5"})
        fp2 = make_filters_fingerprint({"subject": "6"})
        self.assertNotEqual(fp1, fp2)

    def test_empty_params_deterministic(self):
        """Сейчас в list.html фильтров нет — отпечаток пустого набора
        должен быть стабильным и всегда совпадать сам с собой."""
        fp1 = make_filters_fingerprint({})
        fp2 = make_filters_fingerprint({})
        self.assertEqual(fp1, fp2)

    def test_int_and_str_values_normalized_equally(self):
        """Значения приводятся к str() — 5 и "5" дают одинаковый отпечаток."""
        fp1 = make_filters_fingerprint({"subject": 5})
        fp2 = make_filters_fingerprint({"subject": "5"})
        self.assertEqual(fp1, fp2)

    def test_fingerprint_is_hex_md5_length(self):
        fp = make_filters_fingerprint({"a": "1"})
        self.assertEqual(len(fp), 32)
        int(fp, 16)  # не бросает — валидная hex-строка