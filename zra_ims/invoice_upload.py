import time
import concurrent.futures
import logging
import logging.config

from mysql.connector import MySQLConnection, Error
import requests
from requests.exceptions import HTTPError

from zra_ims._encrypt import read_db_config, DataEnc, key, format_data
from zra_ims.heartbeat import HeartBeat

heartbeat = HeartBeat()  # start background heartbeat monitor process
enc = DataEnc()

logging.config.fileConfig(fname='logging.ini', disable_existing_loggers=False)

logger = logging.getLogger(__name__)


def query_invoice():
    try:

        query = """SELECT upload_id,
                    invoice_num, 
                    invoice_encrypted 
                    FROM invoice_upload 
                    WHERE upload_flag = 0
                    LIMIT 50"""

        dbconfig = read_db_config()
        conn = MySQLConnection(**dbconfig)
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()

        return rows

    except Error:
        logger.exception("dB query error")

    finally:
        cursor.close()
        conn.close()


def upload(content):
    HEADERS = {
        'Content-Length': '1300',
        'Content-Type': 'application/json',
    }
    content = content[2]  # index 2 contains encrypted content
    sign = enc.content_sign(content.encode())  # returns MD5 sign of encrypted content
    send_key = enc.content_key(key)  # returns RSA encrypted key
    request_data = format_data("INVOICE-REPORT-R", content, sign, send_key)
    try:
        response = requests.post('http://41.72.108.82:8097/iface/index',
                                 json=request_data,
                                 headers=HEADERS)
    except HTTPError:
        logger.exception("Exception occurred")
        raise
    except Exception:
        logger.exception("Exception occurred")
        raise
    else:
        if response and response.status_code == 200:  # successful client-server exchange
            return response.json()
        else:
            logger.info(f"invoice number{content[1]}: encountered server error. None 200 code returned")
            raise Exception('None 200 code returned')


def decrypt_response(response, invoice_num):
    try:
        sign_ = response.json()['message']['body']['data']['sign']
    except KeyError:  # server returned non-encrypted data
        content = response.json()['message']['body']['data']['content']
        logger.warning(f"invoice number{invoice_num}: upload failure\n"
                       f"server response: {content}")
        print(content)  # todo: used for troubleshooting. remove later
        return response, 2  # 2 signifies unsuccessful upload in the invoice_upload dB table
    else:
        encrypted_content = response.json()['message']['body']['data']['content']
        md5 = enc.content_sign(encrypted_content.encode())

        if md5.decode() == sign_:  # content is correct
            _key = response.json()['message']['body']['data']['key']
            decrypted_content = enc.response_decrypt(_key, encrypted_content)
            logger.info(f"invoice number{invoice_num}: upload successful --- {decrypted_content}")
            return decrypted_content, 1  # 1 signifies successful upload in the invoice_upload dB table
        logger.warning(f"invoice number{invoice_num}: upload failure\n"
                        f"MD5 mismatch! expected {md5}, got {sign_}")
        return 'MD5 mismatch', 2


def upload_update(response, upload_flag, upload_id, invoice_num):
    db_config = read_db_config()

    # prepare query and data
    query = """ UPDATE invoice_upload
                SET response = %s,
                SET upload_flag = %s
                WHERE upload_id = %s """

    data = (response, upload_flag, upload_id)

    try:
        conn = MySQLConnection(**db_config)

        # update book title
        cursor = conn.cursor()
        cursor.execute(query, data)

        # accept the changes
        conn.commit()

    except Error:
        logger.exception(f"dB update error for invoice number: {invoice_num}")

    finally:
        cursor.close()
        conn.close()


def main():
    while True:
        upload_list = query_invoice()

        if len(upload_list) == 0:  # no invoice for upload
            time.sleep(900)
            continue
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            # Start the load operations and mark each future with its URL
            future_to_url = {executor.submit(upload, content): content for content in upload_list}
            print(len(future_to_url))
            for future in concurrent.futures.as_completed(future_to_url):
                upload_id = future_to_url[future][0]
                invoice_num = future_to_url[future][1]
                try:
                    data = future.result()
                except Exception as exc:
                    print('%r generated an exception: %s' % (upload_id, exc))  # todo: remove later
                else:
                    decrypted_res = decrypt_response(data, invoice_num)
                    response, upload_flag = decrypted_res
                    upload_update(response, upload_flag, upload_id, invoice_num)
                    print('%r page is %d bytes' % (upload_id, data))  # todo: remove later

        if len(upload_list) < 25:
            time.sleep(900)


if __name__ == '__main__':
    main()
