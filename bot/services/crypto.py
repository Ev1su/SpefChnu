import hashlib
import hmac

from cryptography.fernet import Fernet


class Cipher:
    def __init__(self, key: str):
        self.fernet = Fernet(key.encode())

    def encrypt(self, value: str | int) -> str:
        return self.fernet.encrypt(str(value).encode()).decode()

    def decrypt(self, value: str) -> str:
        return self.fernet.decrypt(value.encode()).decode()


class CryptoService(Cipher):
    def __init__(self, key: str, salt: str = ""):
        super().__init__(key)
        self.salt = salt

    def user_hash(self, user_id: int) -> str:
        return hmac.new(self.salt.encode(), str(user_id).encode(), hashlib.sha256).hexdigest()


def user_hash(user_id: int, salt: str) -> str:
    return hmac.new(salt.encode(), str(user_id).encode(), hashlib.sha256).hexdigest()