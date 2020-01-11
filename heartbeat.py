import threading
import time


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
