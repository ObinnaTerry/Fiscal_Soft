import json
from datetime import datetime

import requests
from requests.exceptions import HTTPError
from mysql.connector import MySQLConnection, Error

from zra_ims._encrypt import DataEnc, read_db_config, key, format_data

HEADERS = {
    'Content-Length': '1300',
    'Content-Type': 'application/json',
}

enc = DataEnc()
db_config = read_db_config()


def invoice_range_insert(invoice_code, start_num, end_num, total, create_time):
    global conn
    global cursor

    query = "INSERT INTO invoice_range(invoice_code, start_num, end_num, total, create_time) VALUES(%s,%s,%s,%s,%s) "
    args = (invoice_code, start_num, end_num, total, create_time)

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


class SetUp:

    def __init__(self):
        """Contains methods that handles and processes client-server exchange.
        format_data method takes in inputs and produces a corresponding json data to be used in client-server exchange.
        server_exchange method handles all client-server exchange.
        content_proc method processes server response and takes actions depending based on the bus_id.
        """

        self.id = {"id": "531030026147"}

    def server_exchange(self, bus_id, raw_content):
        """handles all exchanges with the server. the response from the server is decrypted, the content_proc method
        is then called to process the decrypted content
        bus_id: business ID for the server exchange
        raw_content: unencrypted business data
        """

        content = enc.encrypted_content(raw_content)  # encrypts content
        sign = enc.content_sign(content.encode())  # returns MD5 sign of encrypted content
        if bus_id == 'R-R-01':
            send_key = ''
        else:
            send_key = enc.content_key(key)  # returns RSA encrypted key
        request_data = format_data(bus_id, content, sign, send_key)
        try:
            response = requests.post('http://41.72.108.82:8097/iface/index',
                                     json=request_data,
                                     headers=HEADERS)
        except HTTPError as http_e:
            print(f'HTTP error occurred: {http_e}')
            # pass
        except Exception as err:
            print(f'Other error occurred: {err}')
            # pass
        else:
            if response and response.status_code == 200:  # server successfully responded
                try:
                    sign_ = response.json()['message']['body']['data']['sign']
                except KeyError:  # server returned non-encrypted data
                    return -1
                else:  # server returned encrypted data
                    encrypted_content = response.json()['message']['body']['data']['content']
                    md5 = enc.content_sign(encrypted_content.encode())
                    if md5.decode() == sign_:
                        if bus_id == 'R-R-01':  # no decryption required
                            decrypted_content = encrypted_content
                        else:
                            _key = response.json()['message']['body']['data']['key']
                            decrypted_content = enc.response_decrypt(_key, encrypted_content)
                        self.content_proc(bus_id, decrypted_content)  # call the content_proc method to further
                        # process the received data
                    else:
                        raise Exception('MD5 mismatch!')
            else:  # server haven't responded in an expected manner
                raise Exception('Error encountered')

    def content_proc(self, bus_id, data):
        """Processes decrypted server response. This method handles different data input according to the bus_id and
        its corresponding business requirement.
        data: decrypted content from server response. type: dict
        bus_id: business ID from decrypted data. type: str
        """

        if bus_id == 'R-R-01':
            if data['code'] == 200:  # private key successfully obtained
                secret = data['secret']
                write_list = ['-----BEGIN RSA PRIVATE KEY-----\n', f'{secret}\n', '-----END RSA PRIVATE KEY-----']
                with open('primary_key.pem', 'w') as pri_key_file:  # Write private key to file
                    pri_key_file.writelines(write_list)
            else:  # private key not successfully obtained, sends a new request to server
                raise Exception('Pri-key APP failure: ', data)

        if bus_id == 'R-R-02':
            if data['code'] == 200:  # tax info successfully obtained
                with open('tax_info.json', 'w') as tax_file:
                    json.dumps(tax_file)
            else:
                raise Exception('tax-info APP failure: ', data)

        if bus_id == 'R-R-03':
            if data['code'] == 200:  # successfully initialized
                print('Initialization successful')
            else:  # initialization failed
                raise Exception('Initialization failure: ', data)

        if bus_id == 'INVOICE-APP-R':
            if data['code'] == 200:
                invoice = data['invoice']
                for invoice_range in invoice:
                    invoice_code = invoice_range['code']
                    start_num = invoice_range['number-begin']
                    end_num = invoice_range['number-end']
                    total = int(end_num) - int(start_num) + 1

                    invoice_range_insert(invoice_code, start_num, end_num, total, datetime.now())
            else:
                raise Exception('Invoice range APP failure: ', data)


if __name__ == '__main__':

    pri_key_data = {"license": "531030026147", "sn": "187603000010", "sw_version": "1.2", "model": "IP-100",
                    "manufacture": "Inspur", "imei": "359833002198832", "os": "linux2.6.36", "hw_sn": "3458392322"}

    exchange_list = ['R-R-01', 'R-R-02', 'R-R-03', 'INVOICE-APP-R']

    setup = SetUp()

    for code in exchange_list:
        if code == 'R-R-01':
            result = setup.server_exchange(code, pri_key_data)
            if result == -1:
                print('Pri-key app failed. Aborted!')
            break  # no need to try the other 2 codes without a pri-key
        setup.server_exchange(code, setup.id)
