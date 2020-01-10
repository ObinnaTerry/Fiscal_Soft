from Crypto.Cipher import DES
from secrets import token_bytes
import Padding
import base64
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding

key = token_bytes(8)


class DataEnc:

    def __init__(self):
        self.cipher = DES.new(key, DES.MODE_ECB)
        with open('private_key.pem', mode='rb') as key_file:
            self.private_key = serialization.load_pem_private_key(
                key_file.read(),
                password=None,
                backend=default_backend()
            )
        with open("public_key.pem", "rb") as key_file:
            self.public_key = serialization.load_pem_public_key(
                key_file.read(),
                backend=default_backend()
            )
        print(key)

    @staticmethod
    def pad(data):
        return Padding.appendNullPadding(data, 8).encode()

    def des_encrypt_64encode(self, data):
        data_encrypt = self.cipher.encrypt(data)
        return base64.b64encode(data_encrypt)

    def rsa_encrypt(self, message):
        cipher_text = self.public_key.encrypt(
            message,
            padding.PKCS1v15()
        )
        return base64.b64encode(cipher_text)
