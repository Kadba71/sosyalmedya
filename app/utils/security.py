import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings


def _build_fernet_key(secret_source: str) -> bytes:
    digest = hashlib.sha256(secret_source.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


class TokenCipher:
    def __init__(self, settings: Settings) -> None:
        secret_source = settings.app_encryption_key or settings.secret_key
        self._fernet = Fernet(_build_fernet_key(secret_source))

    def encrypt(self, value: str | None) -> str | None:
        if not value:
            return None
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, value: str | None) -> str | None:
        if not value:
            return None
        try:
            return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Stored token could not be decrypted.") from exc
