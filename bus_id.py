import requests
from requests.exceptions import HTTPError
from _encrypt import DataEnc, key
import pickle
from sqlite3 import Error
import sqlite3
import time

HEADERS = {
    'Content-Length': '1300',
    'Content-Type': 'application/json',
}
monitor = None
enc = DataEnc()

create_log_table = """CREATE TABLE IF NOT EXISTS exchange_log (
                                        id integer PRIMARY KEY,
                                        request text NOT NULL,
                                        request_type text NOT NULL,
                                        response text,
                                        result text,
                                        time TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
                                    );"""


class BusId:

    def __init__(self):
        self.id = {"id": "531030026147"}
        db_connect = False
        while not db_connect:
            try:
                self.conn = sqlite3.connect('fiscal.db')
            except Error as e:
                print(e)  # change to logging
                time.sleep(3)
                continue
            else:
                db_connect = True
                cur = self.conn.cursor()
                cur.execute(create_log_table)  # create a log table is not exist on start-up
                self.conn.commit()
                cur.close()

        with open('content_data', 'rb') as file:  # load pickle file containing data structure
            self.data = pickle.load(file)

    def format_data(self, bus_id, content, sign, _key):
        """
        Returns json data for communication with the server
        bus_id: business ID
        content: DES encrypted business data
        sign: MD5 sign of content
        _key: RSA encrypted 8-byte key
        """

        self.data['message']['body']['data']['sign'] = sign
        self.data['message']['body']['data']['key'] = _key
        self.data['message']['body']['data']['content'] = content
        self.data['message']['body']['data']['bus_id'] = bus_id
        return self.data

    def server_exchange(self, bus_id, raw_content):
        """
        handles all exchanges with the server.
        bus_id: business ID for the exchange
        raw_content: unencrypted business data
        """
        content = enc.encrypted_content(raw_content)  # encrypts content
        sign = enc.content_sign(content.encode())  # returns MD5 sign of encrypted content
        if bus_id == 'R-R-01':
            _key = ''
        else:
            _key = enc.content_key(key)  # returns RSA encrypted key
        request_data = self.format_data(bus_id, content, sign, _key)
        try:
            response = requests.post('http://41.72.108.82:8097/iface/index',
                                     json=request_data,
                                     headers=HEADERS)
        except HTTPError as http_e:
            print(f'HTTP error occurred: {http_e}')  # change to logging later
            pass
        except Exception as err:
            print(f'Other error occurred: {err}')  # change to logging later
            pass
        else:
            if response and response.status_code == 200:
                try:
                    sign_ = response.json()['message']['body']['data']['sign']
                except KeyError:  # server returned non-encrypted data
                    cur = self.conn.cursor()
                    result = 'failure'
                    content = response.json()['message']['body']['data']['content']
                    print(content)
                    cur.execute("INSERT INTO exchange_log VALUES (NULL,?,?,?,?,datetime(CURRENT_TIMESTAMP,"
                                "'localtime'))", (request_data, bus_id, content, result))
                    self.conn.commit()
                    cur.close()
                    pass
                else:  # server returned encrypted data
                    encrypted_content = response.json()['message']['body']['data']['content']
                    md5 = enc.content_sign(encrypted_content.encode())
                    if md5.decode() == sign_:
                        if bus_id == 'R-R-01':  # no decryption required
                            decrypted_content = encrypted_content
                        else:
                            _key = response.json()['message']['body']['data']['key']
                            decrypted_content = enc.response_decrypt(_key, encrypted_content)
                        result = 'success' if decrypted_content['code'] == 200 else 'failure'
                        cur = self.conn.cursor()
                        cur.execute("INSERT INTO exchange_log VALUES (NULL,?,?,?,?,datetime(CURRENT_TIMESTAMP,"
                                    "'localtime'))", (request_data, bus_id, decrypted_content, result))
                        self.conn.commit()
                        cur.close()

    def content_proc(self, bus_id, data):
        """
        Processes decrypted server response
        data: decrypted content from server response
        bus_id: business ID from decrypted data
        """
        if bus_id == 'R-R-01':
            if data['code'] == 200:  # private key successfully obtained
                secret = data['secret']
                write_list = ['-----BEGIN RSA PRIVATE KEY-----\n', f'{secret}\n', '-----END RSA PRIVATE KEY-----']
                with open('primary_key.pem', 'w') as pri_key_file:  # Write private key to file
                    pri_key_file.writelines(write_list)
            else:  # private key not successfully obtained, sends a new request to server
                with open('initialisation_data', 'rb') as file:
                    initialisation_data = pickle.load(file)
                time.sleep(3)  # wait 3 secs before attempting to resend initialization request
                self.server_exchange(bus_id, initialisation_data)  # add this file a pickle file

        if bus_id == 'R-R-02':
            if data['code'] == 200:  # tax info successfully obtained
                with open('tax_info', 'ab') as tax_file:
                    pickle.dump(data, tax_file)
            else:
                # with open('tax_info_data', 'rb') as file:
                #     tax_info_data = pickle.load(file)
                time.sleep(3)  # wait 3 secs before attempting to resend tax info request
                self.server_exchange(bus_id, self.id)

        if bus_id == 'R-R-03':
            if data['code'] == 200:
                # more code. do something. set an initialization flag to True
                pass
            else:  # initialization failed
                time.sleep(3)  # wait 3 secs before attempting to resend tax info request
                self.server_exchange(bus_id, self.id)

        if bus_id == 'INFO-MODI-R':
            if data['code'] == 200:
                with open('tax_info', 'w+') as tax_file:  # open and overwrite existing data
                    pickle.dump(data, tax_file)
            else:
                time.sleep(3)
                self.server_exchange(bus_id, self.id)

        if bus_id == 'INVOICE-APP-R':
            if data['code'] == 200:
                # more code. process the the received invoice range
                pass
            else:
                time.sleep(3)
                self.server_exchange(bus_id, self.id)


