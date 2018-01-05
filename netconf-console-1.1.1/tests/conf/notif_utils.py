import _confd
from _confd import XmlTag, Value, TagValue
from _confd import dp
import socket
from notifier_ns import ns
from datetime import datetime as dt


def init(dname="ncpy"):
    global ctrsock, dx, sock  # must not be deallocated
    ctrsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    dx = dp.init_daemon(dname)
    dp.connect(dx, ctrsock, dp.CONTROL_SOCKET, '127.0.0.1', 4565)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    dp.connect(dx, sock, dp.WORKER_SOCKET, '127.0.0.1', 4565)
    stream = dp.register_notification_stream(dx, object(), sock, 'test-stream')
    dp.register_done(dx)
    return stream


def notify_value(stream, value):
    tagval = [TagValue(XmlTag(ns.hash, ns.notifier_pythonnotif),
                       Value((ns.notifier_pythonnotif, ns.hash), _confd.C_XMLBEGIN)),
              TagValue(XmlTag(ns.hash, ns.notifier_whatsup),
                       Value(value)),
              TagValue(XmlTag(ns.hash, ns.notifier_pythonnotif),
                       Value((ns.notifier_pythonnotif, ns.hash), _confd.C_XMLEND))]
    dp.notification_send(stream, _confd.DateTime(*dt.now().timetuple()), tagval)
