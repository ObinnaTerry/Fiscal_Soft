import sqlite3
import threading
import time
from _encrypt import DataEnc, key
import json
import requests
from requests.exceptions import HTTPError
from sqlite3 import Error

encrypt = DataEnc()

b_data = {"id": "531030026147", "lon": 100.832004, "lat": 45.832004, "sw_version": "1.2"}

b_data_json = json.dumps(b_data)
b_data_pad = encrypt.pad(b_data_json)
b_data_des = encrypt.des_encrypt_64encode(b_data_pad)

sign = encrypt.md5(b_data_des)
key_ = encrypt.rsa_encrypt(key)

HEADERS = {
    'Content-Length': '1300',
    'Content-Type': 'application/json',
}

request_data = {
    "message": {
        "body": {
            "data": {
                "device": "531030026147",
                "serial": "000000",
                "bus_id": "MONITOR-R",
                "content": b_data_des.decode(),
                "sign": sign.decode(),
                "key": key_.decode()
            }
        }
    }
}

create_HB_table = """CREATE TABLE IF NOT EXISTS heartbeat_monitor (
                                        id integer PRIMARY KEY,
                                        response text NOT NULL,
                                        result text NOT NULL,
                                        time TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
                                    );"""


class HeartBeat(threading.Thread):
    """ heartbeat class for sending heartbeat monitoring signal
    """

    def __init__(self, interval=5):
        threading.Thread.__init__(self)

        self.interval = interval
        thread = threading.Thread(target=self.run)
        thread.daemon = True  # Daemonize thread so thread stops when main program exits
        thread.start()
        print(thread.getName())

    def run(self):
        """ Method that runs in the background """

        while True:
            try:
                conn = sqlite3.connect('fiscal.db')
            except Error as e:
                print(e)  # change to logging
                continue
            else:
                cur = conn.cursor()
                cur.execute(create_HB_table)
                conn.commit()
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
                        result = 'failure'
                        content = response.json()['message']['body']['data']['content']
                        print(content)
                        cur.execute("INSERT INTO heartbeat_monitor VALUES (NULL,?,?,datetime(CURRENT_TIMESTAMP,"
                                    "'localtime'))", (content, result))
                        conn.commit()
                        pass
                    else:
                        encrypted_content = response.json()['message']['body']['data']['content']
                        md5 = encrypt.md5(encrypted_content.encode())
                        if md5.decode() == sign_:
                            result = 'success'
                            _key = response.json()['message']['body']['data']['key']
                            decrypted_content = encrypt.response_decrypt(_key, encrypted_content)
                            cur.execute("INSERT INTO books VALUES (NULL,?,?, datetime(CURRENT_TIMESTAMP,'localtime'))",
                                        (decrypted_content, result))
                            conn.commit()
                        else:
                            print('MD5 mismatch, decryption aborted!')  # change to logging
                            pass
                else:
                    pass

            time.sleep(self.interval)

#
# g = HeartBeat()
# time.sleep(20)
