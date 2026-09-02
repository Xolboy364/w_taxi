"""
Parollarni xavfsiz saqlash uchun yordamchi funksiyalar (PBKDF2-HMAC-SHA256).
Bu fayl config.py va database.py bilan bir papkada turishi kerak.
"""
import hashlib
import hmac
import os

_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    """Parolni 'salt$hash' formatida qaytaradi (bazaga saqlash uchun)."""
    salt = os.urandom(16).hex()
    pwd_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), _ITERATIONS
    )
    return f"{salt}${pwd_hash.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Kiritilgan parolni bazadagi 'salt$hash' qiymati bilan solishtiradi."""
    if not stored or "$" not in stored:
        return False
    try:
        salt, hash_hex = stored.split("$", 1)
        pwd_hash = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), _ITERATIONS
        )
        return hmac.compare_digest(pwd_hash.hex(), hash_hex)
    except Exception:
        return False
