from Crypto.Cipher import DES
# from secrets import token_bytes
import Padding
import base64
import hashlib
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding


key = b'\xbe\x9aT\xc1SD%\xbe'


class DataEnc:

    def __init__(self):
        self.cipher = DES.new(key, DES.MODE_ECB)
        self.hash = hashlib.md5()
        with open('private_key.pem', mode='rb') as key_file:
            self.private_key = serialization.load_pem_private_key(
                key_file.read(),
                password=None,
                backend=default_backend()
            )

        with open('private_key.pem', 'r') as key_file:
            self.private_ = RSA.importKey(key_file.read())

    @staticmethod
    def pad(data):
        return Padding.appendNullPadding(data, 8).encode()

    def des_encrypt_64encode(self, data):
        data_encrypt = self.cipher.encrypt(data)
        return base64.b64encode(data_encrypt)

    @staticmethod
    def des_decrypt(d_key, message):
        cipher = DES.new(d_key, DES.MODE_ECB)
        message = base64.b64decode(message)
        data_decrypt = cipher.decrypt(message)
        data_decrypt_rm_pad = Padding.removeNullPadding(data_decrypt.decode(), 8)
        return data_decrypt_rm_pad

    def rsa_encrypt(self, message):
        cipher = PKCS1_v1_5.new(self.private_)
        cipher_text = cipher.encrypt(message)
        # cipher_text = self.private_key.encrypt(
        #     message,
        #     padding.PKCS1v15()
        # )
        return base64.b64encode(cipher_text)

    def rsa_decrypt(self, message):
        message = base64.b64decode(message)
        plain_text = self.private_key.decrypt(
            message,
            padding.PKCS1v15()
        )
        return plain_text

    def response_decrypt(self, _key, content):
        _key = self.rsa_decrypt(_key)
        content = self.des_decrypt(_key, content)
        return content.strip('{}')

    def md5(self, data):
        self.hash.update(data)
        return base64.b64encode(self.hash.digest())
