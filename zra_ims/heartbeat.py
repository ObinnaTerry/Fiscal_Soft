import threading
import time

from mysql.connector import MySQLConnection, Error
import requests
from requests.exceptions import HTTPError

from zra_ims._encrypt import DataEnc, read_db_config, key, format_data

encrypt = DataEnc()

b_data = {"id": "531030026147", "lon": 100.832004, "lat": 45.832004, "sw_version": "1.2"}

b_data_des = encrypt.encrypted_content(b_data)

sign = encrypt.content_sign(b_data_des.encode())
key_ = encrypt.content_key(key)

HEADERS = {
    'Content-Length': '1300',
    'Content-Type': 'application/json',
}

request_data = format_data("MONITOR-R", b_data_des, sign, key_)

db_config = read_db_config()


def insert_heartbeat(request, bus_id, response_encrypted, response_decrypted, result, log_time):
    """ Insert values to the heartbeat_monitor table.
    :param request: encrypted request data
    :param bus_id:
    :param response_encrypted: encrypted response data
    :param response_decrypted: decrypted response data
    :param result: 0 - failure (i.e. server returned content code other than 200). 1- success (server returned content code 200)
    :param log_time:
    :return: None
    """

    global conn
    global cursor

    query = "INSERT INTO heartbeat_monitor(request, bus_id, response_encrypted, response_decrypted, result, " \
            "log_time) VALUES(%s,%s,%s,%s,%s,%s) "
    args = (request, bus_id, response_encrypted, response_decrypted, result, log_time)

    try:
        conn = MySQLConnection(**db_config)
        cursor = conn.cursor()
        cursor.execute(query, args)

        if cursor.lastrowid:
            print('last insert id', cursor.lastrowid)  # todo: change to logging
        else:
            print('last insert id not found')  # todo: change to logging

        conn.commit()
    except Error as error:
        conn.rollback()
        print(error)  # todo: change to logging

    finally:
        cursor.close()
        conn.close()


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
        print(thread.getName())  # todo: used for debugging. remove later

    def run(self):
        """ Method that runs in the background and handles sending of monitoring signal to the server and processing
        of server response
        """

        while True:
            # bus_id_list = ["INVOICE-RETRIEVE-R", "INVOICE-APP-R", "INFO-MODI-R", "R-R-03", "R-R-02", "R-R-01"]

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
                    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
                    try:
                        sign_ = response.json()['message']['body']['data']['sign']
                    except KeyError:  # server returned non-encrypted data
                        result = 0
                        content = response.json()['message']['body']['data']['content']
                        print(content)  # todo: used for troubleshooting. remove later
                        insert_heartbeat(request_data, "MONITOR-R", None, content, result, timestamp)
                        pass
                    else:
                        encrypted_content = response.json()['message']['body']['data']['content']
                        md5 = encrypt.content_sign(encrypted_content.encode())
                        if md5.decode() == sign_:  # content is correct
                            result = 1
                            _key = response.json()['message']['body']['data']['key']
                            decrypted_content = encrypt.response_decrypt(_key, encrypted_content)
                            insert_heartbeat(request_data, "MONITOR-R", encrypted_content, decrypted_content, result,
                                             timestamp)
                            # command_len = len(decrypted_content['commands'])
                            # if command_len > 0:  # response data contains command instructions
                            #     for command in decrypted_content['commands']:
                            #         if command['command'] == 'INFO-MODI-R':
                            #             prep_data.server_exchange('INFO-MODI-R', b_data)
                            #         else:
                            #             pass

                        else:
                            print('MD5 mismatch, decryption aborted!')  # todo: change to logging later
                            pass
                else:
                    print('A server error occurred')  # todo: change to logging later
                    pass

            time.sleep(self.interval)
