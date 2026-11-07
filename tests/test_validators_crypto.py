from bot.services.crypto import CryptoService
from bot.validators import (
    normalize_full_name,
    normalize_instagram,
    normalize_phone,
    normalize_telegram,
    validate_birth_date,
)


def test_full_name():
    assert normalize_full_name("  іван   петренко  ") == "Іван Петренко"
    assert normalize_full_name("Іван") is None


def test_phone():
    assert normalize_phone("+380 (50) 123-45-67") == "+380501234567"
    assert normalize_phone("0501234567") == "+380501234567"
    assert normalize_phone("123") is None


def test_nicks():
    assert normalize_instagram("https://instagram.com/test.name") == "@test.name"
    assert normalize_telegram("@valid_nick") == "@valid_nick"
    assert normalize_telegram("bad") is None


def test_birth_date_and_crypto():
    assert validate_birth_date("25.03.2006") is True
    assert validate_birth_date("31.02.2006") is False
    service = CryptoService("MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=", "salt")
    encrypted = service.encrypt("secret")
    assert service.decrypt(encrypted) == "secret"
    assert service.user_hash(123) == service.user_hash(123)
