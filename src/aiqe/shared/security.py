"""
AIQE Security Helpers.

Provides cryptographic utilities, secret scanning, and safe
handling of sensitive values throughout AIQE.

Security principles enforced here:
    - Secrets are encrypted at rest using Fernet symmetric encryption
    - No secret ever appears in a log record (enforced in logging.py)
    - Repository content is never interpolated directly into AI prompts
    - Every security violation raises SecurityError and is logged

Why Fernet?
    Fernet (from the cryptography library) provides authenticated
    symmetric encryption. It guarantees that data encrypted with a
    given key cannot be decrypted without that key, and that tampered
    ciphertext is detected and rejected. It is the right tool for
    encrypting stored API keys and credentials.
"""

from __future__ import annotations

import re
from typing import Final

from cryptography.fernet import Fernet, InvalidToken

from aiqe.shared.exceptions import SecretsLeakError, SecurityError
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)

# Patterns that indicate a potential secret in a string.
# Used to scan AI prompts and log output before emission.
_SECRET_PATTERNS: Final[list[re.Pattern[str]]] = [
    re.compile(r"(?i)(api[_-]?key|apikey)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(secret|password|passwd|pwd)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(token|bearer)\s*[:=]\s*\S+"),
    re.compile(r"(?i)github_pat_[a-zA-Z0-9_]+"),
    re.compile(r"(?i)sk-[a-zA-Z0-9]{20,}"),          # OpenAI key pattern
    re.compile(r"(?i)anthropic-key-[a-zA-Z0-9]+"),
    re.compile(r"(?i)AIza[0-9A-Za-z-_]{35}"),         # Google API key
    re.compile(r"(?i)xoxb-[0-9A-Za-z-]+"),            # Slack bot token
]


def generate_encryption_key() -> str:
    """
    Generate a new Fernet encryption key.

    This key must be stored securely (e.g. in AIQE_ENCRYPTION_KEY
    environment variable). Losing it means losing access to all
    values encrypted with it.

    Returns:
        Base64-encoded Fernet key as a string.
    """
    return Fernet.generate_key().decode()


def encrypt_value(value: str, key: str) -> str:
    """
    Encrypt a sensitive string value using Fernet symmetric encryption.

    Used to encrypt API keys and credentials before storing them in
    the database or checkpoint files.

    Args:
        value: The plaintext string to encrypt.
        key: The Fernet encryption key (from AIQE_ENCRYPTION_KEY).

    Returns:
        The encrypted value as a base64-encoded string.

    Raises:
        SecurityError: If the encryption key is invalid.
    """
    try:
        fernet = Fernet(key.encode())
        return fernet.encrypt(value.encode()).decode()
    except Exception as e:
        msg = "Failed to encrypt value — check AIQE_ENCRYPTION_KEY"
        logger.error("encryption_failed", error=str(e))
        raise SecurityError(msg) from e


def decrypt_value(encrypted_value: str, key: str) -> str:
    """
    Decrypt a Fernet-encrypted string value.

    Args:
        encrypted_value: The base64-encoded encrypted string.
        key: The Fernet encryption key used for encryption.

    Returns:
        The decrypted plaintext string.

    Raises:
        SecurityError: If decryption fails (wrong key or tampered data).
    """
    try:
        fernet = Fernet(key.encode())
        return fernet.decrypt(encrypted_value.encode()).decode()
    except InvalidToken as e:
        msg = (
            "Failed to decrypt value — the encryption key may be wrong "
            "or the encrypted value may have been tampered with."
        )
        logger.error("decryption_failed")
        raise SecurityError(msg) from e
    except Exception as e:
        msg = "Unexpected error during decryption"
        logger.error("decryption_error", error=str(e))
        raise SecurityError(msg) from e


def scan_for_secrets(content: str, source: str = "unknown") -> None:
    """
    Scan a string for patterns that suggest it contains secrets.

    Must be called before interpolating any external content into
    AI prompts or log output. Repository content, file contents,
    and user-provided strings are all untrusted.

    Args:
        content: The string to scan.
        source: A description of where this content came from,
                for the audit log (e.g. "repository file", "cli argument").

    Raises:
        SecretsLeakError: If a secret pattern is detected.
    """
    for pattern in _SECRET_PATTERNS:
        if pattern.search(content):
            logger.error(
                "potential_secret_detected",
                source=source,
                pattern=pattern.pattern,
            )
            msg = (
                f"Potential secret detected in content from '{source}'. "
                "AIQE has stopped processing this content to prevent "
                "secrets from appearing in AI prompts or reports."
            )
            raise SecretsLeakError(msg)


def sanitize_for_prompt(content: str, source: str = "repository") -> str:
    """
    Sanitize external content before interpolating it into an AI prompt.

    This is AIQE's primary defense against prompt injection attacks.
    Repository content, test files, and user-provided strings must
    never be interpolated directly into prompts without this check.

    Steps:
        1. Scan for secret patterns — raise SecretsLeakError if found.
        2. Truncate to prevent token exhaustion attacks.
        3. Wrap in XML tags that signal to the model this is untrusted
           external content (part of prompt injection defense strategy).

    Args:
        content: External content to sanitize.
        source: Description of content origin for audit logging.

    Returns:
        Sanitized content safe for prompt interpolation.

    Raises:
        SecretsLeakError: If secrets are detected in the content.
    """
    # Step 1: scan for secrets
    scan_for_secrets(content, source)

    # Step 2: truncate to max 8000 chars to prevent token exhaustion
    max_length = 8000
    truncated = content[:max_length]
    if len(content) > max_length:
        truncated += f"\n\n[CONTENT TRUNCATED: {len(content) - max_length} chars omitted]"
        logger.warning(
            "content_truncated_for_prompt",
            source=source,
            original_length=len(content),
            truncated_length=max_length,
        )

    # Step 3: wrap in XML tags to signal untrusted content to the model
    return f"<external_content source='{source}'>\n{truncated}\n</external_content>"
