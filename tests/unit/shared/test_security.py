"""Unit tests for AIQE security helpers."""
import pytest
from aiqe.shared.security import (
    decrypt_value,
    encrypt_value,
    generate_encryption_key,
    sanitize_for_prompt,
    scan_for_secrets,
)
from aiqe.shared.exceptions import SecretsLeakError, SecurityError


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        key = generate_encryption_key()
        original = "my-secret-api-key-12345"
        encrypted = encrypt_value(original, key)
        decrypted = decrypt_value(encrypted, key)
        assert decrypted == original

    def test_encrypted_value_differs_from_original(self):
        key = generate_encryption_key()
        original = "secret"
        encrypted = encrypt_value(original, key)
        assert encrypted != original

    def test_wrong_key_raises_security_error(self):
        key1 = generate_encryption_key()
        key2 = generate_encryption_key()
        encrypted = encrypt_value("secret", key1)
        with pytest.raises(SecurityError):
            decrypt_value(encrypted, key2)

    def test_generate_key_returns_string(self):
        key = generate_encryption_key()
        assert isinstance(key, str)
        assert len(key) > 0


class TestSecretScanning:
    def test_detects_api_key_pattern(self):
        with pytest.raises(SecretsLeakError):
            scan_for_secrets("api_key=sk-abc123xyz789", source="test")

    def test_detects_github_pat(self):
        with pytest.raises(SecretsLeakError):
            scan_for_secrets("github_pat_11ABCDEF", source="test")

    def test_clean_content_passes(self):
        scan_for_secrets("This is regular code content", source="test")

    def test_sanitize_wraps_in_xml(self):
        result = sanitize_for_prompt("print('hello')", source="file.py")
        assert "<external_content" in result
        assert "print('hello')" in result

    def test_sanitize_truncates_long_content(self):
        long_content = "x" * 10000
        result = sanitize_for_prompt(long_content, source="test")
        assert "CONTENT TRUNCATED" in result
