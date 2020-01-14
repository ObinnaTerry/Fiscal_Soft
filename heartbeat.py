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

    def __init__(self, interval=900):
        threading.Thread.__init__(self)

        self.interval = interval
        thread = threading.Thread(target=self.run)
        thread.daemon = True  # Daemonize thread so thread stops when main program exits
        thread.start()
        try:
            self.conn = sqlite3.connect('fiscal.db')
        except Error as e:
            print(e)  # change to logging
        self.cur = self.conn.cursor()
        self.cur.execute(create_HB_table)
        self.conn.commit()

    # def insert(self, res, result):
    #     self.cur.execute("INSERT INTO books VALUES (NULL,?,?)", (res, result))
    #     self.conn.commit()

    def run(self):
        """ Method that runs in the background """

        while True:
            try:
                response = requests.post('IP-Address',
                                         json=request_data,
                                         headers=HEADERS)
            except HTTPError as http_e:
                print(f'HTTP error occurred: {http_e}')  # change to logging later
                continue
            except Exception as err:
                print(f'Other error occurred: {err}')  # change to logging later
                continue
            else:
                if response and response.status_code == 200:
                    try:
                        message = response.json()['message']['body']['data']['sign']
                    except KeyError:
                        result = 'failure'
                        res = response.json()['message']['body']['data']['content']
                        self.cur.execute("INSERT INTO books VALUES (NULL,?,?)", (res, result))
                        self.conn.commit()
                        continue
                    else:
                        result = 'success'
                        res = response.json()['message']['body']['data']['content']
                        self.cur.execute("INSERT INTO books VALUES (NULL,?,?)", (res, result))
                        self.conn.commit()

                        # insert code that logs response to BD & log file

            time.sleep(self.interval)


print(json.dumps(request_data))
