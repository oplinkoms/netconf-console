#!/usr/bin/env python

from __future__ import print_function

import sys
import argparse
import readline
import getpass
from ncclient import manager, transport
from lxml import etree
from ncclient.operations.rpc import RPCError
from contextlib import contextmanager
import six
import traceback
import re

from . import nctransport, completions, operations


class OperationArgAction(argparse.Action):
    def __init__(self, *args, **kwargs):
        self.operation = kwargs["const"]
        super(OperationArgAction, self).__init__(*args, **kwargs)

    def __call__(self, parser, ns, values, option_string=None):
        if self.operation.nargs == "?":
            values = [] if values == self.operation else [values]
        ns.operations.append((self.operation, values))


quoted_rgx = r'"[^\\"]*(?:\\.[^\\"]*)*"|[^ ]+'


def parse_expr_args(expression):
    expr = " " + expression
    spaces = re.compile(" +")
    quoted = re.compile(quoted_rgx)
    while expr != "":
        spm = spaces.match(expr)
        if spm is None:
            raise ParserException("Syntax error before " + expr.split()[0])
        expm = quoted.match(expr[spm.end():])
        if expm is None:
            raise ParserException("Syntax error before " + expr[spm.end():].split()[0])
        ex = expm.group()
        if ex[0] == '"':
            yield re.sub(r"\\(.)", r"\1", ex[1:-1])
        else:
            yield ex
        expr = expr[spm.end() + expm.end():]


class ExpressionOperation(operations.Operation):
    def __init__(self, exprparser, process_errors=True):
        self.exprparser = exprparser
        self.process_errors = process_errors

    def invoke(self, mc, ns, expression):
        expression = expression.strip()
        if expression == '':
            return None
        try:
            ns = self.exprparser.parse_args(parse_expr_args(expression),
                                            namespace=argparse.Namespace(**vars(ns)))
        except ParserException as e:
            print(e, file=sys.stderr)
            return None
        if hasattr(ns, 'cmd_parser') and ns.cmd_parser is not None:
            ns.cmd_parser.print_help()
            return None
        try:
            if hasattr(ns, "value"):
                return ns.op.invoke(mc, ns, ns.value)
            else:
                return ns.op.invoke(mc, ns)
        except RPCError as e:
            if self.process_errors:
                return e.xml
            raise
        except Exception as e:
            if self.process_errors:
                report_exception(e, ns.debug)
                return None
            raise


def report_exception(exc, debug=False):
    if debug:
        traceback.print_exc(file=sys.stderr)
    else:
        msg = str(exc)
        if len(msg) > 100:
            msg = msg[:80] + "..."
        print('Operation failed: %s - %s' % (exc.__class__.__name__, msg))


class ParserException(Exception):
    pass


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise ParserException(message)


def expression_parser(parsercls=argparse.ArgumentParser, custom_help=False, **kwargs):
    exprparser = parsercls(prog='', **kwargs)
    exprs = exprparser.add_subparsers(help="Netconf commands")
    for opcls in operations.OPERATIONS:
        op = opcls()
        parserargs = dict(parents=[command_options_parser(op)], help=op.help)
        if custom_help:
            parserargs['add_help'] = False
        cmdparser = exprs.add_parser(op.option, **parserargs)
        if custom_help:
            cmdparser.add_argument("-h", "--help", action="store_const", const=cmdparser,
                                   dest="cmd_parser", help="show this help message")
        if op.nargs == 1:
            cmdparser.add_argument("value")
        elif op.nargs == "?":
            cmdparser.add_argument("value", nargs=op.nargs)
        cmdparser.set_defaults(op=op)
    return exprparser


command_option_args = {
    "style": (["-s", "--outputStyle"],
              dict(dest="style", default=[],
                   choices=["plain", "noaaa"], nargs="*")),
    "db": (["--db"],
           dict(dest="db", default="running",
                help="Database for commands that operate on a database.")),
    "timeout": (["--timeout"],
                dict(dest="timeout", default=600, type=int,
                     help="Confirmed commit timeout (in seconds).")),
    "wdefaults": (["--with-defaults"],
                  dict(dest="wdefaults", default=None,
                       choices=["explicit", "trim", "report-all", "report-all-tagged"],
                       help="Use with --get, --get-config, or --copy-config.")),
    "winactive": (["--with-inactive"],
                  dict(dest="winactive", action="store_true",
                       help="Send with-inactive parameter.  Use with --get, "
                       "--get-config, --copy-config, or --edit-config.")),  # FIXME: not supported
    "xpath": (["-x", "--xpath"],
              dict(dest="xpath",
                   help="XPath filter to be used with --get, --get-config, "
                   "and --create-subscription; kept for backward compatibility, "
                   "the operations accept direct arguments if provided.")),
    "test": (
        ["-t", "--test-option"],
        dict(dest="test",
             choices=["test-then-set", "set", "test-only"],
             help="Value of test-option used with edit-config (defaults to test-then-set)")),
    "operation": (
        ["-o", "--operation"],
        dict(dest="operation", default="merge",
             choices=["merge", "replace", "create"],
             help="Value of the operation attribute used with --set.")),
    "deloperation": (
        ["--del-operation"],
        dict(dest="deloperation", default="remove",
             choices=["remove", "delete"],
             help="Value of the operation attribute used with --delete."))
}


def command_options_parser(operation=None):
    cmd_opt_parser = argparse.ArgumentParser(add_help=False)
    cmd_group = cmd_opt_parser.add_argument_group("Command options")
    options = command_option_args.keys() if operation is None else operation.command_opts
    for opt in options:
        args, kws = command_option_args[opt]
        cmd_group.add_argument(*args, **kws)
    return cmd_opt_parser


def argparser():
    parser = argparse.ArgumentParser(prog="netconf-console", parents=[command_options_parser()])
    parser.add_argument("-v", "--version", dest="version",
                        help="force NETCONF version 1.0 or 1.1")  # FIXME: not supported
    parser.add_argument("-u", "--user", dest="username", default="admin",
                        help="username")
    parser.add_argument("-p", "--password", dest="password", default="admin", const=None, nargs="?",
                        help="password")
    parser.add_argument("--host", dest="host", default="127.0.0.1",
                        help="NETCONF agent hostname")
    parser.add_argument("--port", dest="port", default=2022, type=int,
                        help="NETCONF agent SSH port")
    parser.add_argument("--privKeyFile", help="File which contains the private key.")
    parser.add_argument("--raw", type=argparse.FileType("w"), nargs="?", const=sys.stdout)
    parser.add_argument("--tcp", action="store_true"),
    parser.add_argument("-N", "--ns", dest="ns",
                        help="Namespace prefix; useful for get queries with xpath filter.",
                        nargs="*")

    parser.add_argument("--debug", action="store_true")

    cmds = parser.add_argument_group("Commands")
    parser.set_defaults(operations=[])
    for opcls in operations.OPERATIONS:
        op = opcls()
        cmds.add_argument("--%s" % op.option,
                          dest=op.dest,
                          nargs=op.nargs,
                          action=OperationArgAction,
                          const=op,
                          choices=op.choices,
                          help=op.help)

    exprparser = expression_parser()
    parser.add_argument("-e", "--expr",
                        action=OperationArgAction,
                        nargs=1,
                        const=ExpressionOperation(exprparser))
    parser.add_argument("--dry", action="store_true", default=False,
                        help="Do not send anything, return the RPC to be sent (debugging only).")
    parser.add_argument("--interactive", "-i", action="store_true",
                        help="Run the console interactively (do not use with commands).")
    parser.add_argument("filename",
                        nargs="?",
                        help="Filename (or '-') containing v1.0-delimited list of NETCONF RPCs. "
                        "Retained for backward compatibility, it is suggested to use "
                        "a sequence of --get, --set, etc. commands instead. "
                        "Cannot be combined with other commands.")
    return parser


class SSHSession(transport.SSHSession):
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


def connect(ns):
    password = ns.password
    if password is None:
        password = getpass.getpass()
    connect_args = dict(host=ns.host, port=ns.port,
                        username=ns.username, password=password,
                        key_filename=ns.privKeyFile,
                        hostkey_verify=False, look_for_keys=False, allow_agent=False)
    device_handler = manager.make_device_handler(None)
    if not ns.tcp and not ns.raw:
        # use the public API only
        session = transport.SSHSession(device_handler)
    elif ns.tcp:
        session = nctransport.TCPSession(device_handler, ns.raw)
    else:
        session = nctransport.SSHSession(device_handler, ns.raw)
    if not ns.tcp and ("hostkey_verify" not in connect_args or connect_args["hostkey_verify"]):
        session.load_known_hosts()
    try:
        session.connect(**connect_args)
    except Exception:
        if session.transport:
            session.close()
        raise
    return manager.Manager(session, device_handler, **connect_args)


def interactive_data():
    readline.parse_and_bind("tab: complete")
    readline.set_completer_delims(" ")
    readline.set_completer(completions.NCCompleter(operations.OPERATION_OPTS,
                                                   command_option_args))
    try:
        while True:
            command = six.moves.input('netconf> ')
            yield command
    except EOFError:
        return


def interactive_operations(exprparser, mc):
    if sys.stdin.isatty():
        data = interactive_data()
    else:
        data = sys.stdin
    operation = ExpressionOperation(exprparser)
    for command in data:
        if not mc.connected:
            return
        yield (operation, [command])
    return


def connect_and_process(ns):
    with connect(ns) as mc:
        try:
            if ns.filename:
                operations_iter = operations.FilenameOperations(ns.filename).operations()
            elif ns.interactive:
                expr_parser = expression_parser(SafeParser, custom_help=True)
                expr_parser.set_defaults(debug=ns.debug)
                operations_iter = interactive_operations(expr_parser, mc)
            else:
                operations_iter = ns.operations
            for (operation, args) in operations_iter:
                reply = operation.invoke(mc, ns, *args)
                if reply is not None:
                    print(etree.tostring(reply, encoding=six.text_type,
                                         pretty_print=("plain" not in ns.style)))
        except RPCError as e:
            print(etree.tostring(e.xml, encoding=six.text_type, pretty_print=True))
            return -1
    return 0


def main():
    parser = argparser()
    ns = parser.parse_args(sys.argv[1:])
    if ns.operations == [] and ns.filename is None:
        ns.interactive = True
    if ns.interactive and ns.operations != [] or \
       ns.interactive and ns.filename is not None or \
       ns.operations != [] and ns.filename is not None:
        parser.print_help()
        return 1
    if ns.dry:
        operations.run_rpc_dry()
    try:
        return connect_and_process(ns)
    except Exception as e:
        report_exception(e, ns.debug)
        return -1


if __name__ == "__main__":
    sys.exit(main())
