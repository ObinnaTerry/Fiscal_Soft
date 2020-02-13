import pickle
import sqlite3
import threading
import time
from _encrypt import DataEnc, key
import requests
from requests.exceptions import HTTPError
from sqlite3 import Error
from bus_id import BusId

encrypt = DataEnc()

b_data = {"id": "531030026147", "lon": 100.832004, "lat": 45.832004, "sw_version": "1.2"}

b_data_des = encrypt.encrypted_content(b_data)

sign = encrypt.content_sign(b_data_des.encode())
key_ = encrypt.content_key(key)

HEADERS = {
    'Content-Length': '1300',
    'Content-Type': 'application/json',
}

with open('content_data', 'rb') as file:  # load pickle file containing data structure
    data = pickle.load(file)

prep_data = BusId()
request_data = prep_data.format_data("MONITOR-R", b_data_des, sign, key_)

create_HB_table = """CREATE TABLE IF NOT EXISTS heartbeat_monitor (
                                        id integer PRIMARY KEY,
                                        response text NOT NULL,
                                        result text NOT NULL,
                                        time TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
                                    );"""

create_cmd_table = """CREATE TABLE IF NOT EXISTS commands (
                                        id integer PRIMARY KEY,
                                        command text NOT NULL,
                                        flag integer NOT NULL,
                                        time TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
                                    );"""


class HeartBeat(threading.Thread):

    def __init__(self, interval=5):
        """This class provides the run method which will run in the background whenever the main program is executed.
        It  is used by the EFD system to monitor the online status of V-EFD. The current device statue will be sent to
        EFD system at a specified interval. Commands stacked in the queue list on the EFD system will be
        submitted to the V-EFD as part of the response of heartbeat monitoring command.
        :param interval: send signal interval. time unit = seconds
        """
        threading.Thread.__init__(self)

        self.interval = interval
        thread = threading.Thread(target=self.run)
        thread.daemon = True  # Daemonize thread so thread stops when main program exits
        thread.start()
        print(thread.getName())

    def run(self):
        """ Method that runs in the background and handles sending of monitoring signal to the server and processing
        of server response
        """

        while True:
            bus_id_list = ["INVOICE-RETRIEVE-R", "INVOICE-APP-R", "INFO-MODI-R", "R-R-03", "R-R-02", "R-R-01"]
            try:
                conn = sqlite3.connect('fiscal.db')
            except Error as e:
                print(e)  # todo: change to logging later
                continue
            else:
                cur = conn.cursor()
                cur.execute(create_HB_table)
                conn.commit()
                cur.execute(create_cmd_table)
                conn.commit()
            try:
                response = requests.post('http://41.72.108.82:8097/iface/index',
                                         json=request_data,
                                         headers=HEADERS)
            except HTTPError as http_e:
                print(f'HTTP error occurred: {http_e}')  # todo: change to logging later
                pass
            except Exception as err:
                print(f'Other error occurred: {err}')  # todo: change to logging later
                pass
            else:
                if response and response.status_code == 200:  # successful client-server exchange
                    try:
                        sign_ = response.json()['message']['body']['data']['sign']
                    except KeyError:  # server returned non-encrypted data
                        result = 'failure'
                        content = response.json()['message']['body']['data']['content']
                        print(content)  # todo: used for troubleshooting. remove later
                        cur.execute("INSERT INTO heartbeat_monitor VALUES (NULL,?,?,datetime(CURRENT_TIMESTAMP,"
                                    "'localtime'))", (content, result))
                        conn.commit()
                        pass
                    else:
                        encrypted_content = response.json()['message']['body']['data']['content']
                        md5 = encrypt.content_sign(encrypted_content.encode())
                        if md5.decode() == sign_:  # content is correct
                            result = 'success'
                            _key = response.json()['message']['body']['data']['key']
                            decrypted_content = encrypt.response_decrypt(_key, encrypted_content)
                            cur.execute("INSERT INTO books VALUES (NULL,?,?, datetime(CURRENT_TIMESTAMP,'localtime'))",
                                        (decrypted_content, result))
                            conn.commit()
                            command_len = len(decrypted_content['commands'])
                            if command_len > 0:  # response data contains command instructions
                                for command in decrypted_content['commands']:
                                    if command['command'] == 'INFO-MODI-R':
                                        prep_data.server_exchange('INFO-MODI-R', prep_data.id)
                                    else:
                                        pass

                        else:
                            print('MD5 mismatch, decryption aborted!')  # todo: change to logging later
                            pass
                else:
                    pass
            cur.close()
            time.sleep(self.interval)
