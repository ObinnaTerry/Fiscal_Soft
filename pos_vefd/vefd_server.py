import socket
import selectors
import sys
import logging
import logging.config

from pos_vefd import serverlib

sel = selectors.DefaultSelector()

logging.config.fileConfig(fname='file.ini', disable_existing_loggers=False)

logger = logging.getLogger(__name__)


def accept_wrapper(sock):
    conn, addr = sock.accept()  # Should be ready to read
    logger.info("accepted connection from", addr)
    conn.setblocking(False)
    message = serverlib.Message(sel, conn, addr)
    sel.register(conn, selectors.EVENT_READ, data=message)


host, port = ("127.0.0.1", 3000)  # loop-back address. change to server address.

lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# Avoid bind() exception: OSError: [Errno 48] Address already in use
lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
lsock.bind((host, port))
lsock.listen()
logger.info("listening on", (host, port))
lsock.setblocking(False)
sel.register(lsock, selectors.EVENT_READ, data=None)


def main():
    while True:
        events = sel.select(timeout=None)
        for key, mask in events:
            if key.data is None:
                accept_wrapper(key.fileobj)
            else:
                message = key.data
                try:
                    message.process_events(mask)
                except Exception:
                    logger.exception(
                        "main: error: exception for",
                        f"{message.addr}",
                    )
                    message.close()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        sel.close()
        sys.exit()
