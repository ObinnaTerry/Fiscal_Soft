from Crypto.Cipher import DES
from secrets import token_bytes
import Padding
import base64

key = token_bytes(8)


class DataEnc:

    def __init__(self):
        self.cipher = DES.new(key, DES.MODE_ECB)

    @staticmethod
    def pad(data):
        return Padding.appendNullPadding(data, 8).encode()

    def des_encrypt_64encode(self, data):
        data_encrypt = self.cipher.encrypt(data)
        return base64.b64encode(data_encrypt)