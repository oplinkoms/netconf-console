"Abstractions of operations that can be invoked on a Netconf server."

import time
import sys
import re
from lxml import etree
import ncclient
from ncclient.xml_ import new_ele, sub_ele, qualify, validated_element
from ncclient import manager
from ncclient.operations import util
from ncclient.transport import SessionListener, ssh
from ncclient.operations.rpc import RPC
from ncclient.operations import retrieve
from . import completions

NOTIFICATION_NS = "urn:ietf:params:xml:ns:netconf:notification:1.0"
TAILF_AAA_NS = "http://tail-f.com/ns/aaa/1.1"
IETF_NACM_NS = "urn:ietf:params:xml:ns:yang:ietf-netconf-acm"
DEFAULTS_NS = "urn:ietf:params:xml:ns:yang:ietf-netconf-with-defaults"
INACTIVE_NS = "http://tail-f.com/ns/netconf/inactive/1.0"


class ExecuteRpc(RPC):
    "Custom general-purpose RPC"
    def request(self, rpc):
        return self._request(rpc)


def extend_get_node(rpc, node, filter=None, defaults=None, inactive=None):
    if filter is not None:
        node.append(util.build_filter(filter, rpc._assert))
    if defaults is not None:
        etree.SubElement(node, qualify("with-defaults", DEFAULTS_NS)).text = defaults
    if inactive is not None:
        etree.SubElement(node, qualify("with-inactive", INACTIVE_NS))
    return node


class GetConfigRpc(retrieve.GetConfig):
    """The *get-config* RPC, with support for with-defaults."""

    def request(self, source, filter=None, defaults=None, nsmap={}):
        node = new_ele("get-config", nsmap=nsmap)
        node.append(util.datastore_or_url("source", source, self._assert))
        return self._request(extend_get_node(self, node, filter, defaults))


class GetRpc(retrieve.Get):
    """The *get* RPC, with support for with-defaults."""

    def request(self, filter=None, defaults=None, nsmap={}):
        node = new_ele("get", nsmap=nsmap)
        return self._request(extend_get_node(self, node, filter, defaults))


class ValidateRpc(RPC):
    "*validate* RPC, with support for config data"
    # The Validate implementation in ncclient is invalid now (Jun 2016)

    DEPENDS = [":validate"]

    def request(self, source):
        """Validate the contents of the specified configuration.

        *source* is the name of the configuration datastore being
         validated or `config` element containing the configuration
         subtree to be validated

        :seealso: :ref:`srctarget_params`
        """
        node = new_ele("validate")
        if type(source) is str:
            src = util.datastore_or_url("source", source, self._assert)
        else:
            validated_element(source, ("config", qualify("config")))
            src = new_ele("source")
            src.append(source)
        node.append(src)
        return self._request(node)


manager.VENDOR_OPERATIONS.update(rpc=ExecuteRpc, get_config_ncc=GetConfigRpc, get_ncc=GetRpc,
                                 validate_ncc=ValidateRpc)


class Operation(object):
    name = None
    option = None
    help = None
    nargs = 0
    dest = None
    command_opts = []
    choices = None
    arg_completion = staticmethod(completions.no_arg_completion)

    def invoke(self, mc, ns):
        pass


class Hello(Operation):
    name = option = "hello"
    help = "Connect to the server and print its capabilities"

    def invoke(self, mc, *ignored):
        caps = list(mc.server_capabilities)
        hello = new_ele("hello")
        xcaps = sub_ele(hello, "capabilities")
        for cap in caps:
            sub_ele(xcaps, "capability").text = cap
        return hello


class GetOperation(Operation):
    command_opts = ["style", "wdefaults", "xpath"]
    nargs = "?"

    def invoke(self, mc, ns, path=None):
        replydata = self._invoke(mc, ns, path)
        if "noaaa" in ns.style:
            aaa = replydata.find(qualify("aaa", TAILF_AAA_NS))
            if aaa is not None:
                replydata.remove(aaa)
            nacm = replydata.find(qualify("nacm", IETF_NACM_NS))
            if nacm is not None:
                replydata.remove(nacm)
        return replydata


class Get(GetOperation):
    name = option = "get"
    help = "Takes an optional -x argument for XPath filtering"

    def _invoke(self, mc, ns, path=None):
        reply = mc.get_ncc(xpath_filter(ns, path), ns.wdefaults, nsmap(ns))
        return reply.data


class GetConfig(GetOperation):
    name = "get_config"
    option = "get-config"
    help = "Takes an optional --db argument, default is 'running'" \
           ", and an optional -x argument for XPath filtering"
    command_opts = GetOperation.command_opts + ["db"]

    def _invoke(self, mc, ns, path=None):
        reply = mc.get_config_ncc(ns.db, xpath_filter(ns, path), ns.wdefaults, nsmap(ns))
        return reply.data


class DiscardChanges(Operation):
    name = "discard_changes"
    option = "discard-changes"

    def invoke(self, mc, ns):
        reply = mc.discard_changes()
        return reply._root[0]


class Commit(Operation):
    name = "commit"
    option = "commit"
    nargs = "?"
    choices = ['confirmed']
    command_opts = ["timeout"]
    arg_completion = staticmethod(completions.commit_arg_completion)

    def invoke(self, mc, ns, confirmed=False):
        reply = mc.commit(confirmed, str(ns.timeout))
        return reply._root[0]


class KillSession(Operation):
    name = "kill_session"
    option = "kill-session"
    help = "Takes a session-id as argument"
    nargs = 1
    dest = "session_id"

    def invoke(self, mc, ns, session):
        reply = mc.kill_session(session)
        return reply._root[0]


class Validate(Operation):
    name = option = "validate"
    help = ("Takes either 'candidate', or a filename or '-' as an optinal"
            " argument, the default is '-'.  If it is 'candidate', the request for"
            " validation of the candidate datastore is sent, otherwise the contents"
            " of the file is sent as configuration to be validated.")
    nargs = "?"
    arg_completion = staticmethod(completions.validate_arg_completion)

    def invoke(self, mc, ns, src="-"):
        if src == "candidate":
            source = src
        else:
            source = etree.parse(sys.stdin if src == "-"
                                 else open(src, "r")).getroot()
        reply = mc.validate_ncc(source)
        return reply._root[0]


class CopyRunningToStartup(Operation):
    option = "copy-running-to-startup"
    name = "copy_running_to_startup"

    def invoke(self, mc, ns):
        reply = mc.copy_config("running", "startup")
        return reply._root[0]


class CopyConfig(Operation):
    option = "copy-config"
    name = "copy_config"
    nargs = "?"
    arg_completion = staticmethod(completions.filename_arg_completion)
    help = ("Takes a filename or '-' as an optional"
            " argument. The contents of the file"
            " is data for a single NETCONF copy-config operation"
            " (put into the <config> XML element)."
            " Takes an optional --db argument, default is 'running'.")
    command_opts = ["db"]

    def invoke(self, mc, ns, filename="-"):
        data = etree.parse(sys.stdin if filename == "-" else open(filename, "r"))
        copy = new_ele("copy-config")
        sub_ele(sub_ele(copy, "target"), ns.db)
        sub_ele(sub_ele(copy, "source"), "config").append(data.getroot())
        reply = mc.rpc(copy)
        return reply._root[0]


class EditConfig(Operation):
    option = "edit-config"
    name = "edit_config"
    nargs = "?"
    arg_completion = staticmethod(completions.filename_arg_completion)
    help = ("Takes a filename (or '-' for standard input) as"
            " argument. The contents of the file"
            " is data for a single NETCONF edit-config operation"
            " (put into the <config> XML element)."
            " Takes an optional --db argument, default is 'running'.")
    command_opts = ["db", "test"]

    def invoke(self, mc, ns, filename="-"):
        data = etree.parse(sys.stdin if filename == "-" else open(filename, "r"))
        config = new_ele("config")
        config.append(data.getroot())
        reply = mc.edit_config(config, test_option=ns.test, target=ns.db)
        return reply._root[0]


class PathExpressionException(Exception):
    pass


class XpathParser(object):
    """Simplified xpath expression parser building a XML tree.

    The supported xpath syntax is very limited:

    `/prefix:node[child1=value1][...]/prefix:node/...`

    All prefixes used need to be present in the namespace map. It is necessary
    to use prefixes only when crossing namespace boundary, otherwise the node
    inherits the namespaces from its parent.
    """

    QuotedT = r"%(q)s(?P<%(vname)s>[^%(q)s\\]*(?:\\.[^%(q)s\\]*)*)%(q)s"
    DirectValRx = r"(?P<value3>[^\]]*)"
    IdentT = "(?P<%(iname)s>[^:='\"\[/]+)"
    NodeSpecT = "(?:%s:)?%s"
    PredicateRx = ("\[ *%s(?: *= *(?:%s|%s|%s))? *\]" %
                   (NodeSpecT % (IdentT % {"iname": "pprefix"},
                                 IdentT % {"iname": "ptag"}),
                    QuotedT % {"q": "'", "vname": "value1"},
                    QuotedT % {"q": '"', "vname": "value2"},
                    DirectValRx))
    XpathRx = "(?:/%s(?:%s)*)+" % (NodeSpecT %
                                   (IdentT % {"iname": "prefix"},
                                    IdentT % {"iname": "tag"}),
                                   PredicateRx)
    XpathExpr = re.compile(XpathRx)
    NodeExpr = re.compile(NodeSpecT % (IdentT % {"iname": "prefix"},
                                       IdentT % {"iname": "tag"}))
    PredicateExpr = re.compile(PredicateRx)

    def __init__(self, expression, nsmap):
        self.expression = expression
        self.nsmap = nsmap

    def build_tree_on(self, top_node):
        "Build the path-matching tree for the expression rooted at given node."
        # Something better than doing that manually?
        if XpathParser.XpathExpr.match(self.expression) is None:
            raise PathExpressionException("Invalid path expression")
        self.pos = 0
        try:
            return self.build_tree(top_node)
        except Exception as e:
            raise PathExpressionException("Failed to parse path expression", e)

    def build_tree(self, element, namespace=None):
        "Build the tree for the remaining part of the expression."
        nmatch = XpathParser.NodeExpr.match(self.expression, self.pos + 1)
        gdict = nmatch.groupdict()
        (child, namespace) = self.build_node(element,
                                             gdict["tag"],
                                             gdict["prefix"],
                                             namespace)
        self.pos = nmatch.end()
        self.build_predicate(child, namespace)
        if self.pos < len(self.expression) and self.expression[self.pos] == "/":
            return self.build_tree(child, namespace)
        else:
            return (child, self.expression[self.pos:])

    def build_node(self, element, tag, pfx, namespace):
        elem_ns = self.nsmap.get(pfx, namespace)
        if elem_ns is None:
            expr = tag
        else:
            expr = "{%s}%s" % (elem_ns, tag)
        node = etree.SubElement(element, expr)
        return (node, elem_ns)

    def build_predicate(self, node, namespace):
        pmatch = XpathParser.PredicateExpr.match(self.expression, self.pos)
        if pmatch is None:
            return
        gdict = pmatch.groupdict()
        (child, nns) = self.build_node(node,
                                       gdict["ptag"], gdict["pprefix"],
                                       namespace)
        values = [gdict[valname]
                  for valname in ("value1", "value2", "value3")
                  if gdict[valname] is not None]
        if values != []:
            child.text = values[0]
        self.pos = pmatch.end()
        return self.build_predicate(node, namespace)


class ModifOp(Operation):
    def invoke(self, mc, ns, expr):
        pfxmap = nsmap(ns)
        config = new_ele("config", nsmap=pfxmap)
        (target, rest) = XpathParser(expr, pfxmap).build_tree_on(config)
        self.modify_target(ns, target, rest)
        reply = mc.edit_config(config, test_option=ns.test, target=ns.db)
        return reply._root[0]


class Set(ModifOp):
    option = name = "set"
    help = ("Takes an expression in the form `path=value`. The path may use "
            "prefixes defined with --ns.")
    nargs = 1
    command_opts = ["db", "test", "operation"]

    def modify_target(self, ns, target, rest):
        if rest == "" or rest[0] != "=":
            raise PathExpressionException(
                "The expression needs to take form <path>=<value>")
        attrib = "{%s}%s" % (ncclient.xml_.BASE_NS_1_0, "operation")
        target.attrib[attrib] = ns.operation
        target.text = rest[1:]


class Delete(ModifOp):
    option = name = "delete"
    help = ("Takes a path as an argument. The path may use "
            "prefixes defined with --ns.")
    nargs = 1
    command_opts = ["db", "test", "deloperation"]

    def modify_target(self, ns, target, rest):
        if rest != "":
            raise PathExpressionException(
                "The expression must be a valid path")
        attrib = "{%s}%s" % (ncclient.xml_.BASE_NS_1_0, "operation")
        target.attrib[attrib] = ns.deloperation


class Create(ModifOp):
    option = name = "create"
    help = ("Takes a path to a node to be created as an argument. "
            "The path may use prefixes defined with --ns.")
    nargs = 1
    command_opts = ["db", "test"]

    def modify_target(self, ns, target, rest):
        if rest != "":
            raise PathExpressionException(
                "The expression must be a valid path")
        attrib = "{%s}%s" % (ncclient.xml_.BASE_NS_1_0, "operation")
        target.attrib[attrib] = "create"


class GetSchema(Operation):
    option = "get-schema"
    name = "get_schema"
    help = "Takes an identifier (typically YANG module name) as parameter"
    nargs = 1

    def invoke(self, mc, ns, identifier):
        reply = mc.get_schema(identifier)
        return reply._root[0]


class NotificationListener(SessionListener):

    def callback(self, root, raw):
        tag, attrs = root
        if tag != qualify("notification", NOTIFICATION_NS):
            return
        print(raw)

    def errback(self, err):
        # ignore
        pass


class CreateSubscription(Operation):
    option = "create-subscription"
    name = "create_subscription"
    help = "Takes an optional stream name as a parameter, and an optional -x for XPath filtering"
    nargs = "?"
    command_opts = ["xpath"]

    listener = None

    def start_listener(self, mc):
        if self.listener is not None:
            return
        self.listener = NotificationListener()
        mc._session.add_listener(self.listener)

    def invoke(self, mc, ns, stream=None):
        sub = etree.Element(qualify("create-subscription", NOTIFICATION_NS))
        if stream is not None:
            etree.SubElement(sub, qualify("stream", NOTIFICATION_NS)).text = stream
        if ns.xpath is not None:
            etree.SubElement(sub, qualify("filter", NOTIFICATION_NS), type="xpath", select=ns.xpath)
        self.start_listener(mc)
        reply = mc.rpc(sub)
        return reply._root[0]


class Lock(Operation):
    name = option = "lock"
    help = "Lock the database."
    command_opts = ["db"]

    def invoke(self, mc, ns):
        reply = mc.lock(ns.db)
        return reply._root[0]


class Unlock(Operation):
    name = option = "unlock"
    help = "Unlock the database."
    command_opts = ["db"]

    def invoke(self, mc, ns):
        reply = mc.unlock(ns.db)
        return reply._root[0]


class XRpc(Operation):
    def _invoke(self, mc, elem):
        reply = mc.rpc(elem)
        return reply._root[0]

    def invoke(self, mc, ns, elem):
        return self._invoke(mc, elem)


class Rpc(XRpc):
    option = name = "rpc"
    help = ("Takes an optional filename (or '-' for standard input) as "
            " argument. The contents of the file"
            " is a single NETCONF rpc operation (w/o the surrounding"
            " <rpc>).")
    nargs = "?"
    arg_completion = staticmethod(completions.filename_arg_completion)

    def invoke(self, mc, ns, filename="-"):
        if filename == "-":
            tree = etree.parse(sys.stdin)
        else:
            with open(filename, "r") as data:
                tree = etree.parse(data)
        return self._invoke(mc, tree.getroot())


class Sleep(Operation):
    option = name = "sleep"
    nargs = 1

    def invoke(self, _mc, _ns, timeout):
        time.sleep(float(timeout))
        return new_ele("ok")


class FilenameOperations(object):
    """Iterator over a sequence of operations given by a file containing"
    v1.0-separated NETCONF messages."""

    def __init__(self, filename):
        self.filename = filename

    def operations(self):
        if self.filename == "-":
            data = sys.stdin.read()
        else:
            with open(self.filename) as fdata:
                data = fdata.read()
        messages = [msg.strip() for msg in data.split(ssh.MSG_DELIM)]
        trees = [etree.fromstring(msg) for msg in messages if msg != ""]
        if trees[0].tag == "{%s}%s" % (ncclient.xml_.BASE_NS_1_0, "hello"):
            # we are sending hello anyway, no need to do it
            trees = trees[1:]
        trees = [tree[0] for tree in trees]
        if trees[-1].tag == "{%s}%s" % (ncclient.xml_.BASE_NS_1_0, "close-session"):
            # this is done automatically and would throw an exception
            trees = trees[:-1]
        for tree in trees:
            yield (XRpc(), [tree])


def run_rpc_dry():
    # debugging: replace the RPC._request method to return the rpc object
    class _Reply(object):
        def __init__(self, rpc, subelem):
            elem = new_ele("rpc", {"message-id": rpc._id})
            elem.append(subelem)
            self.data = elem
            self._root = [elem]

    def convert_query(rpc, op):
        return _Reply(rpc, op)
    RPC._request = convert_query


OPERATIONS = [Hello, Get, GetConfig, KillSession, DiscardChanges,
              Lock, Unlock, Commit, Validate, CopyRunningToStartup,
              CopyConfig, EditConfig, Set, Delete, Create, GetSchema,
              CreateSubscription, Rpc, Sleep]

OPERATION_OPTS = {op.option: op for op in OPERATIONS}


def xpath_filter(ns, path=None):
    filter = None
    if path is None:
        path = ns.xpath
    if path is not None:
        filter = ("xpath", path)
    return filter


def nsmap(ns):
    if ns.ns is not None:
        return dict(ns_assignment.split("=") for ns_assignment in ns.ns)
    else:
        return {}
