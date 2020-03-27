import time
import concurrent.futures

from mysql.connector import MySQLConnection, Error
import requests
from requests.exceptions import HTTPError

from zra_ims._encrypt import read_db_config, DataEnc, key, format_data

enc = DataEnc()


def query_invoice():
    try:

        query = """SELECT upload_id, 
                    invoice_encrypted 
                    FROM invoice_range 
                    where upload_flag = 0"""

        dbconfig = read_db_config()
        conn = MySQLConnection(**dbconfig)
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()

        return rows

    except Error as e:
        print(e)

    finally:
        cursor.close()
        conn.close()


def upload(content):
    HEADERS = {
        'Content-Length': '1300',
        'Content-Type': 'application/json',
    }
    content = content[1]
    sign = enc.content_sign(content.encode())  # returns MD5 sign of encrypted content
    send_key = enc.content_key(key)  # returns RSA encrypted key
    request_data = format_data("INVOICE-REPORT-R", content, sign, send_key)
    try:
        response = requests.post('http://41.72.108.82:8097/iface/index',
                                 json=request_data,
                                 headers=HEADERS)
    except HTTPError as http_e:
        print(f'HTTP error occurred: {http_e}')  # todo: change to logging later
        raise
    except Exception as err:
        print(f'Other error occurred: {err}')  # todo: change to logging later
        raise
    else:
        if response and response.status_code == 200:  # successful client-server exchange
            return response.json()
        else:
            raise Exception('None 200 code returned')


def decrypt_response(response):
    try:
        sign_ = response.json()['message']['body']['data']['sign']
    except KeyError:  # server returned non-encrypted data
        content = response.json()['message']['body']['data']['content']
        print(content)  # todo: used for troubleshooting. remove later
        return response, 2
    else:
        encrypted_content = response.json()['message']['body']['data']['content']
        md5 = enc.content_sign(encrypted_content.encode())

        if md5.decode() == sign_:  # content is correct
            _key = response.json()['message']['body']['data']['key']
            decrypted_content = enc.response_decrypt(_key, encrypted_content)
            return decrypted_content, 1
        return 'MD5 mismatch', 2


def upload_update(response, upload_flag, upload_id):

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

    except Error as error:
        print(error)  # todo: logging

    finally:
        cursor.close()
        conn.close()


def main():
    result = []  # contains results from completed exchange with server
    result_ex = []  # contains results from exchanges that resulted in an exception
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
                try:
                    data = future.result()
                except Exception as exc:
                    result_ex.append((upload_id, exc))
                    print('%r generated an exception: %s' % (upload_id, exc))  # todo: remove later
                else:
                    decrypted_res = decrypt_response(data)
                    response, upload_flag = decrypted_res
                    upload_update(response, upload_flag, upload_id)
                    result.append((upload_id, decrypted_res))
                    print('%r page is %d bytes' % (upload_id, data))  # todo: remove later

        #  call another function to handle result analysis and db insertion
        if len(upload_list) < 25:
            time.sleep(900)


if __name__ == '__main__':
    main()
