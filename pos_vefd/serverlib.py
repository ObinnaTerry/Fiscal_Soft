import selectors
import json

from redis.sentinel import Sentinel


class Message:

    def __init__(self, selector, sock, addr):

        self.selector = selector
        self.sock = sock
        self.addr = addr
        self._recv_buffer = b""
        self._send_buffer = b""
        self.crc_error = None
        self.error = None
        self.header = None
        self.request = None
        self.crc = None
        self.response_created = False

    def process_events(self, mask):

        if mask & selectors.EVENT_READ:
            self.read()

        if mask & selectors.EVENT_WRITE:
            self.write()

    def _set_selector_events_mask(self, mode):
        """Set selector to listen for events: mode is 'r', 'w', or 'rw'."""

        if mode == "r":
            events = selectors.EVENT_READ
        elif mode == "w":
            events = selectors.EVENT_WRITE
        elif mode == "rw":
            events = selectors.EVENT_READ | selectors.EVENT_WRITE
        else:
            raise ValueError(f"Invalid events mask mode {repr(mode)}.")
        self.selector.modify(self.sock, events, data=self)

    def read(self):

        try:
            data = b''

            while True:
                self.header += self.sock.recv(7)  # read first 7 bytes from ESD
                if self.header:
                    content_len = int.from_bytes(self.header[3:], byteorder='big')  # get content length
                else:
                    raise RuntimeError("Peer closed.")

                while len(data) < content_len + 2:
                    data += self.sock.recv(content_len)
                break

        except BlockingIOError:
            # Resource temporarily unavailable (errno EWOULDBLOCK)
            pass
        else:
            if data:
                self._recv_buffer += data[:-2]
                crc_recv = data[-2:]  # get crc. last 2 bytes
                self.crc_int(crc_recv)  # call method to calculate crc value
                if not self.get_crc(self.header + data[:-2]) == self.crc:  # check content integrity
                    self.crc_error = True
                self.process_request()
                #     self._send_buffer = bytes([3]) + "Error: CRC value mismatch".encode()
            else:
                raise RuntimeError("Peer closed.")

    def crc_int(self, crc_bytes):
        crc = int.from_bytes(crc_bytes, byteorder="big")
        self.crc = crc  # convert crc to int and set the value of the crc flag.

    def get_crc(self, data: bytes, poly=0x18005):
        """Gets CRC value of input bytes
        :param data: byte array of data
        :param poly:
        :return: CRC value
        """
        crc = 0x0000

        for b in data:

            cur_byte = 0xFF & b
            i = 0x80
            for _ in range(0, 8):
                if crc & 0x8000 != 0:
                    crc = (crc << 1) ^ poly
                else:
                    crc <<= 1
                if cur_byte & i != 0:
                    crc = crc ^ poly
                i >>= 1

        return crc & 0xFFFF

    def process_request(self):
        self.request = json.loads(self._recv_buffer)
        self._set_selector_events_mask("w")

    def create_response(self):  # todo: redis related data handling
        sentinel_ip = ''
        sentinel = Sentinel([(sentinel_ip, 26379)], socket_timeout=0.1)
        master = sentinel.master_for('mymaster', socket_timeout=0.1)
        invoice_number = master.rpop()
        self._send_buffer += invoice_number

    def create_error_response(self, error):  # todo: create error response and append to the send buffer
        # do create error message

        self.response_created = True
        pass

    def error_check(self):
        if int.from_bytes(self.header[0], byteorder='big') != 26:
            self.error = 'hearder_one'
        elif int.from_bytes(self.header[1], byteorder='big') != 93:
            self.error = 'hearder_two'
        elif int.from_bytes(self.header[2], byteorder='big') != 1 or int.from_bytes(self.header[2],
                                                                                    byteorder='big') != 2:
            self.error = 'cmid'

    def write(self):
        self.error_check()
        if self.error:
            self.create_error_response(self.error)
        elif self.crc_error:
            self.create_error_response('crc_error')
        else:
            self.create_response()
        self._write()

    def _write(self):

        if self._send_buffer:
            print("sending", repr(self._send_buffer), "to", self.addr)  # todo: logging
            try:
                # Should be ready to write
                sent = self.sock.sendall(self._send_buffer)
            except BlockingIOError:
                # Resource temporarily unavailable (errno EWOULDBLOCK)
                pass
            else:
                self._send_buffer = self._send_buffer[sent:]
                # Close when the buffer is drained. The response has been sent.
                if sent and not self._send_buffer:
                    self.close()

    def close(self):

        print("closing connection to", self.addr)  # todo: logging
        try:
            self.selector.unregister(self.sock)
        except Exception as e:
            print(
                f"error: selector.unregister() exception for",
                f"{self.addr}: {repr(e)}",
            )  # todo: logging
        try:
            self.sock.close()
        except OSError as e:
            print(
                f"error: socket.close() exception for",
                f"{self.addr}: {repr(e)}",
            )  # todo: logging
        finally:
            # Delete reference to socket object for garbage collection
            self.sock = None
