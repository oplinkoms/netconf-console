"""NETCONF over plain TCP implementation. Derives heavily from SSH to
reuse in/out processing methods."""

from ncclient import transport
import socket
from contextlib import contextmanager
import os


class SSHSession(transport.SSHSession):
    "SSHSession extension capable of saving the raw data."
    def __init__(self, device_handler, raw_file):
        self.raw_file = raw_file
        super(SSHSession, self).__init__(device_handler)
        self.last_pos = 0

    def _parse10(self):
        with self.raw_processing(self._parsing_pos10):
            super(SSHSession, self)._parse10()

    def _parse11(self):
        with self.raw_processing(self._parsing_pos11):
            super(SSHSession, self)._parse11()

    @contextmanager
    def raw_processing(self, position):
        if self.raw_file is not None:
            self.raw_file.write(self._buffer.getvalue()[self.last_pos:].decode("utf8"))
        try:
            yield
        finally:
            self.last_pos = self._buffer.tell()


class TCPChannel(object):
    def __init__(self, host, port):
        for res in socket.getaddrinfo(host, port,
                                      socket.AF_UNSPEC, socket.SOCK_STREAM):
            af, socktype, proto, canonname, sa = res
            try:
                sock = socket.socket(af, socktype, proto)
            except socket.error:
                sock = None
                continue
            try:
                sock.connect(sa)
            except socket.error:
                sock.close()
                sock = None
                continue
            break
        if sock is None:
            raise Exception("Could not connect to the host")
        self.sock = sock
        self.active = True

    def fileno(self):
        return self.sock.fileno()

    def close(self):
        self.sock.close()
        self.active = False

    def is_active(self):
        return self.active

    def recv(self, *args):
        return self.sock.recv(*args)

    def send(self, data):
        return self.sock.send(data.encode('UTF-8'))

    def send_ready(self):
        return True


class TCPSession(SSHSession):
    """TCP session as an extension of SSH session - parsing is the same,
but connect and authentication differs greatly.

    """
    def connect(self, host, port=2023, username=None, password=None, **ignored):
        self._channel = TCPChannel(host, port)
        sockname = self._channel.sock.getsockname()
        self._channel.send("[%s;%s;tcp;%d;%d;%s;%s;%s;]\n" %
                           (username, sockname[0], os.getuid(), os.getgid(), "",
                            os.getenv("HOME", "/tmp"), ""))
        self._connected = True
        self._transport = self._channel
        self._post_connect()
