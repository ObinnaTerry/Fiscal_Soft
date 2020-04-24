import logging
import threading
from datetime import datetime

from redis.sentinel import Sentinel
from mysql.connector import MySQLConnection, Error
import requests
from requests.exceptions import HTTPError
import numpy as np

from _encrypt import read_db_config, format_data, DataEnc, key

enc = DataEnc()
log = logging.getLogger(__name__)
sentinel_ip = ''  # IP address of the server running the redis-sentinel
db_config = read_db_config()

try:
    sentinel = Sentinel([(sentinel_ip, 26379)], socket_timeout=0.1)
except Exception:
    log.warning('cant connect to sentinel instance')
    raise
else:
    master = sentinel.master_for('mymaster', socket_timeout=0.1)


def invoice_range_update():

    query = """ UPDATE invoice_range
                SET use_flag = %s
                WHERE use_flag = %s """

    data = (2, 1)

    try:
        conn = MySQLConnection(**db_config)

        cursor = conn.cursor()
        cursor.execute(query, data)

        conn.commit()

    except Error:
        log.exception("MYSQL error occurred:")

    finally:
        cursor.close()
        conn.close()


def query_invoice():
    try:

        query = """SELECT invoice_code, start_num, end_num, 
                    FROM invoice_range 
                    WHERE use_flag = 0
                    LIMIT 1"""

        conn = MySQLConnection(**db_config)
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()

        return rows

    except Error:
        log.exception("MYSQL error occurred:")

    finally:
        cursor.close()
        conn.close()


def invoice_range_insert(invoice_code, start_num, end_num, total, use_flag, create_time):
    global conn
    global cursor

    query = "INSERT INTO invoice_range(invoice_code, start_num, end_num, total, create_time) VALUES(%s,%s,%s,%s,%s) "
    args = (invoice_code, start_num, end_num, total, use_flag, create_time)

    # use_flag:
    # 0 - unused
    # 1 - in use
    # 2 - used

    try:
        conn = MySQLConnection(**db_config)
        cursor = conn.cursor()
        cursor.execute(query, args)

        conn.commit()
    except Error:
        conn.rollback()
        log.exception('Error occurred inserting to invoice_range table')

    finally:
        cursor.close()
        conn.close()


class RedisInsert(threading.Thread):

    def __init__(self):

        threading.Thread.__init__(self)

        self.id = {"id": "531030026147"}  # id is the device code provided by the ZRA
        self.invoice_range = query_invoice()
        self.invoice_code = str(self.invoice_range[0][0])
        self.start_num = self.invoice_range[0][1]
        self.end_num = self.invoice_range[0][2]
        self.invoice_generator = map(lambda x: '_'.join([self.invoice_code, str(x)]), np.arange(1, 1000000))
        self.result = np.array_split(list(self.invoice_generator), 20)
        self.HEADERS = {
            'Content-Length': '1300',
            'Content-Type': 'application/json',
        }

    def server_exchange(self, bus_id, raw_content):
        """handles all exchanges with the server. the response from the server is decrypted, the content_proc method
        is then called to process the decrypted content
        bus_id: business ID for the server exchange
        raw_content: unencrypted business data
        """

        content = enc.encrypted_content(raw_content)  # encrypts content
        sign = enc.content_sign(content.encode())  # returns MD5 sign of encrypted content

        content_key = enc.content_key(key)  # returns RSA encrypted key
        request_data = format_data(bus_id, content, sign, content_key)
        try:
            response = requests.post('http://41.72.108.82:8097/iface/index',
                                     json=request_data,
                                     headers=self.HEADERS)
        except HTTPError:
            log.exception('HTTP error occurred')
            # todo: send mail
        except Exception:
            log.exception('HTTP error occurred')
            # todo: send mail
        else:
            if response and response.status_code == 200:  # server successfully responded
                try:
                    sign_ = response.json()['message']['body']['data']['sign']
                except KeyError:  # server returned non-encrypted data
                    log.error(f"server returned unencrypted data: \n{response.json()['message']}")
                else:  # server returned encrypted data
                    encrypted_content = response.json()['message']['body']['data']['content']
                    md5 = enc.content_sign(encrypted_content.encode())
                    if md5.decode() == sign_:
                        _key = enc.rsa_decrypt(response.json()['message']['body']['data']['key'])
                        decrypted_content = enc.response_decrypt(_key, encrypted_content)
                        self.process_content(decrypted_content)  # call the process_content method to further
                        # process the received data
                    else:
                        log.error(f'MD5 mismatch! expected {md5}, got {sign_}')
                        # todo: send mail
            else:  # server haven't responded in an expected manner
                log.error(f'{response.status_code} status code received. Expected 200')
                # todo: send mail

    def process_content(self, data):

        if data['code'] == 200:
            invoice = data['invoice']
            for invoice_range in invoice:
                invoice_code = invoice_range['code']
                start_num = invoice_range['number-begin']
                end_num = invoice_range['number-end']
                total = int(end_num) - int(start_num) + 1

                invoice_range_insert(invoice_code, start_num, end_num, total, 0, datetime.now())

    def run(self):
        for invoice_chunk in self.result:
            try:
                master.lpush('invoices', *invoice_chunk)
            except:
                log.exception('Error writing to redis')
            else:
                log.info(f"Write to redis completed. \ninvoice code: {self.invoice_code}. "
                         f"invoice range: {'_'.join([self.start_num, self.end_num])}")

            invoice_range_update()
            self.server_exchange('INVOICE-APP-R', self.id)
