import logging

from redis.sentinel import Sentinel
from mysql.connector import MySQLConnection, Error

from zra_ims._encrypt import read_db_config


log = logging.getLogger(__name__)
sentinel_ip = ''  # IP address of the server running the redis-sentinel
try:
    sentinel = Sentinel([(sentinel_ip, 26379)], socket_timeout=0.1)
except Exception:
    log.warning('cant connect to sentinel instance')
    raise
else:
    master = sentinel.master_for('mymaster', socket_timeout=0.1)


def invoice_range_update():
    db_config = read_db_config()

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
                    WHERE use_flag = 0"""

        dbconfig = read_db_config()
        conn = MySQLConnection(**dbconfig)
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()

        return rows

    except Error:
        log.exception("MYSQL error occurred:")

    finally:
        cursor.close()
        conn.close()


def redis_insert():
    # k = db.
    pass
