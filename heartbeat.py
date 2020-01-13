import threading
import time
from _encrypt import DataEnc, key
import json
import requests


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


class HeartBeat(threading.Thread):
    """ heartbeat class for sending heartbeat monitoring signal
    """

    def __init__(self, interval=900):
        threading.Thread.__init__(self)

        self.interval = interval
        thread = threading.Thread(target=self.run)
        thread.daemon = True  # Daemonize thread so thread stops when main program exits
        thread.start()

    def run(self):
        """ Method that runs in the background """

        while True:
            # more code to be inserted here
            time.sleep(self.interval)


print(json.dumps(request_data))
