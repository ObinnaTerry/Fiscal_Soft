from configparser import ConfigParser
import json
import base64
import hashlib
# from secrets import token_bytes

from Crypto.Cipher import DES
import Padding
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding

key = bytes([9, 6, 5, 9, 6, 0, 3, 3])


class DataEnc:
    """
    this class contains all encryption & decryption methods used for this this application
    """

    def __init__(self):
        self.cipher = DES.new(key, DES.MODE_ECB)
        self.hash = hashlib.md5()
        with open('private_key.pem', mode='rb') as key_file:  # load private key for RSA encryption & decryption
            self.private_key = serialization.load_pem_private_key(
                key_file.read(),
                password=None,
                backend=default_backend()
            )

        with open('private_key.pem', 'r') as key_file:  # load private key for DES encryption & decryption
            self.private_ = RSA.importKey(key_file.read())

    @staticmethod
    def pad(data):
        """
        add null padding to data.
        output: byte string
        """
        return Padding.appendNullPadding(data, 8).encode()

    def des_encrypt_64encode(self, data):
        """
        encrypts data using DES encryption.
        input: null padded json data. block size:8. input data type: byte
        output: base64 encoded DES encrypted byte string
        """
        data_encrypt = self.cipher.encrypt(data)
        return base64.b64encode(data_encrypt)

    @staticmethod
    def des_decrypt(d_key, message):
        """
        Decrypts DES encrypted data.
        input: d_key: 8-byte key; message: base64 encoded string
        output: decrypted message
        """
        cipher = DES.new(d_key, DES.MODE_ECB)
        message = base64.b64decode(message)
        data_decrypt = cipher.decrypt(message)  # returns decrypted byte strings
        data_decrypt_rm_pad = Padding.removeNullPadding(data_decrypt.decode(), 8)  # removes padding from byte string
        return data_decrypt_rm_pad

    def content_key(self, message):
        """
        encrypts message using RSA private key encryption.
        input: 8-byte key used for DES encryption.
        output: RSA encrypted, base64 encoded string
        """
        cipher = PKCS1_v1_5.new(self.private_)
        cipher_text = cipher.encrypt(message)
        # cipher_text = self.private_key.encrypt(
        #     message,
        #     padding.PKCS1v15()
        # )
        b_64 = base64.b64encode(cipher_text)
        return b_64.decode()

    def rsa_decrypt(self, message):
        """
        RSA decryption of message.
        input: input is the key returned by the server along with the content.
        output: byte string of decrypted key
        """
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

    def content_sign(self, data):
        self.hash.update(data)
        b_64 = base64.b64encode(self.hash.digest())
        return b_64.decode()

    def encrypted_content(self, data):
        """produces encrypted content"""
        data = json.dumps(data)  # created json formatted data
        data = self.pad(data)  # add padding
        data = self.des_encrypt_64encode(data)  # DES encrypt data
        return data.decode()  # encode data


def read_db_config(filename='config.ini', section='mysql'):
    """ Read database configuration file and return a dictionary object
    :param filename: name of the configuration file
    :param section: section of database configuration
    :return: a dictionary of database parameters
    """
    # create parser and read ini configuration file
    parser = ConfigParser()
    parser.read(filename)

    # get section, default to mysql
    db_cred = {}
    if parser.has_section(section):
        items = parser.items(section)
        for item in items:
            db_cred[item[0]] = item[1]
    else:
        raise Exception('{0} not found in the {1} file'.format(section, filename))

    return db_cred


def format_data(bus_id, content, sign, _key):
    """Returns json data for communication with the server.
    bus_id: business ID; type:str
    content: DES encrypted business data
    sign: MD5 sign of content
    _key: RSA encrypted 8-byte key
    """

    with open('content_data.json', 'r') as file:  # load pickle file containing data structure
        data = json.loads(file.read())

    data['message']['body']['data']['sign'] = sign
    data['message']['body']['data']['key'] = _key
    data['message']['body']['data']['content'] = content
    data['message']['body']['data']['bus_id'] = bus_id
    return data
