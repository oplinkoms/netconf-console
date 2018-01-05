netconf-console
===============

A console application for interacting with NETCONF servers built on top
of `ncclient <http://ncclient.org/>`__.

Requirements and installation
-----------------------------

This application runs both in Python 2 and Python 3 environments. The
only package required for running this application is ``ncclient``; if
this is installed, all other necessary packages are installed as
dependencies. This means that if you can (successfully) run something
like ``pip install ncclient`` on the target platform, all requirements
should be met.

If you cannot, there still is a chance you can run it if the target
platform supports at least packages ``six`` and ``lxml``, which are
commonly present; and if it contains ``paramiko`` or at least
``cryptography``, you will be able to use SSH (without them you can only
use plain and nonstandard TCP transport). The missing piece,
``ncclient``, can be `downloaded <http://ncclient.org>`__ or
`cloned <https://github.com/ncclient/ncclient>`__ and compiled to a
"Python Wheel" - you can do this on any computer and copy the resulting
``.whl`` file to the target platform, it should work there. Pretty much
the same holds for ``paramiko``. You may also want to create a wheel for
the application itself by running ``python setup.py bdist_wheel``.

Installing and running the application
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you can and want to install the application and all necessary
libraries, just run ``python setup.py install``. Otherwise prepare all
necessary .whl files and the script ``netconf-console`` to the target
platform. If they are in the same directory, nothing else is needed,
otherwise you may need to add the wheel files to ``PYTHONPATH`` before
running the script.

Once installed or copied, you can just run the script with appropriate
options - see below.

Command-line mode
-----------------

The application can be run in two different modes: command-line mode and
interactive (console) mode. The command-line mode allows you to request
several RPC operations in one shell command. The command line would
contain the operation command options (``--get``, ``--lock``, etc.) in
the desired order, all common options (such as ``--host``, ``--port``
etc.) as well as command options (``--db``, ``--style``); the command
options are all used for the commands that accept them, so for example
no two commands can address different datastores.

An example of such command line:

::

    # netconf-console --host=example.com --db candidate --lock --edit-config=fragment1.xml \
    --rpc=commit-confirmed.xml --unlock --sleep 5 --rpc=confirm.xml

Interactive mode
----------------

The interactive mode is started by ``--interactive`` (or ``-i``). During
an interactive session the user issues commands, one per line, with
required arguments or options. The options are isolated now, so it is
possible to have two commands in one session accessing different
datastores. The interactive console provides limited support for
tab-completion of commands, options, and their arguments.

The previous example can look like this:

::

    # netconf-console --host=example.com -i
    netconf> lock
    netconf> edit-config fragment1.xml --db candidate
    netconf> rpc commit-confirmed.xml
    netconf> unlock
    netconf> get-config
    netconf> rpc confirm.xml
    netconf>

Note: some commands (``rpc``, ``edit-config`` and others) may accept
data from standard input in the command-line mode; this does not work in
the interactive mode.

Some capabilities of the interactive mode can be used in command-line
mode too using ``--expr`` pseudo-command: the argument is a command
(including options) as if it was added in the interactive mode, such as

::

    # netconf-console --expr 'get-config --db candidate' 'get-config'

Commands
--------

A command may accept an argument and a number of options. In
command-line mode, all option values are shared (see above); conversely,
in interactive mode the option needs to be provided for every command
where its desired value differs from the default. If a command does not
accept given option, it is a syntax error to provide it in interactive
mode (in command-line mode such situations are ignored).

``hello``
    Send just the initial ``hello`` message and display the reply. Does
    not accept any arguments or options.

``get``
    Send ``get`` RPC. Accepts options ``outputStyle``, ``with-defaults``,
    ``xpath``. As an alternative to ``xpath``, ``get`` accepts path as an
    argument.

``get-config``
    Send ``get-config`` RPC. Accepts the same set of options as ``get``
    plus ``db``.

``set``

    Sends ``edit-config`` with single leaf assignment.  Requires the assignment
    in the form ``<path>=<value>`` as an argument, accepts ``db``, ``test``,
    and ``operation``.  The path may contain (or actually needs to contain, in
    case it descends into a list instance) simple predicates in the form
    ``node[key1=value1][key2=value2]...``.

``delete``
    Sends ``edit-config`` with a single node to be deleted.  The node is
    determined by the path provided as an argument, see ``set`` for the path
    format.  Accepts ``db``, ``test``, and ``del-operation`` options.

``create``
    Sends ``edit-config`` with a single node to be created.  The node is
    determined by the path provided as an argument, see ``set`` for the path
    format.

``kill-session``
    Send ``kill-session`` RPC. Requires session identifier as an
    argument, accepts no options.

``discard-changes``
    Send ``discard-changes`` RPC. Accepts no arguments or options.

``lock``
    Send ``lock`` RPC towards the datastore indicated by ``db`` option.

``unlock``
    Send ``unlock`` RPC, counterpart of ``lock``.

``commit``
    Send ``commit`` request. Accepts optional ``confirmed`` as an
    argument and option ``timeout``.

``validate``
    Send ``validate`` RPC. Accepts one argument, which can be either the
    literal ``candidate`` (to validate the contents of the candidate
    datastore) or a filename pointing to a file with full configuration
    to be validated; defaults to ``-``, standard input.

``copy-running-to-startup``
    Send ``copy-config`` RPC with ``running`` datastore as the source
    and ``startup`` datastore as target. Accepts no arguments or
    options.

``copy-config``
    Send ``copy-config`` RPC. Accepts a filename for the source
    configuration as a argument (defaults to ``-``), and the ``db``
    option for the target datastore.

``edit-config``
    Send ``edit-config`` RPC. Accepts the same set of arguments and
    options as ``copy-config``.

``get-schema``
    Send ``get-schema`` RPC. Requires schema identifier as an argument.

``create-subscription``
    Send ``create-subscription`` RPC. Requires notification stream
    identifier as an argument. The notifications received from the
    server are displayed on standard output while the session is active
    - i.e. makes sense either in an interactive mode or in command-line
    mode with the command ``sleep``.

``rpc``
    If none of the commands above is sufficient, a custom RPC can be
    send using this command. Accepts a filename (or ``-`` as default) as
    an argument; the file contents is sent to the server enveloped in
    the ``rpc`` element.

``sleep``
    Do nothing, just sleep for given number of seconds provided as an
    argument.

As a backward-compatibility option, it is possible to provide a filename (or
``-`` for standard input) containing all messages that are supposed to be sent
to the server, separated by the NETCONF transport v1.0 message separator.  This
option cannot be used with any other command.  Note that RPC message-id is not
preserved.


Options
-------

There are two sets of options: global options and command options.
Global options affect overall behavior of the tool and can be provided
in the shell command line (i.e. not to individual commands in the
interactive mode). Command options affect individual commands and in
interactive mode they need to be provided per command.

Global options
~~~~~~~~~~~~~~

``help``
    Display a usage message and exit.

``host``
    Hostname or IP address of the NETCONF server.

``port``
    Port number of the NETCONF server.

``user``
    Username for the authentication on the server (defaults to
    ``admin``).

``password``
    Password for the authentication on the server (defaults to
    ``admin``). If the option is provided without a value, the password
    is read from the terminal.

``privKeyFile``
    File containing the user's private key.

``raw``
    Print all received replies in the original form. The option accepts
    one argument, name of file where the text should be stored; defaults
    to standard output.

``tcp``
    Use plain TCP for the communication with the server (without this
    option SSH is used).

``dry``
    Do not actually send any RPCs, just display them to standard output.

Local options
~~~~~~~~~~~~~

As written above, local (or command) options are meaningful only for
certain command.

``outputStyle``
    Affects the format of the displayed RPC reply. By default, the reply
    is pretty-printed, but otherwise kept as is. The option accepts
    ``plain`` (do no pretty-printing) and ``noaaa`` (remove the ``aaa``
    subtree from the reply from ``get`` or ``get-config`` requests).

``db``
    Target datastore for some of the RPC operations. Defaults to
    ``running``.

``timeout``
    Timeout in seconds for confirmed commit.

``with-defaults``
    Set default values handling. Accepted values are ``explicit``,
    ``trim``, ``report-all``, ``report-all-tagged``.

``xpath``
    Set the XPath filter for get or subscribe requests.

``ns``
    Set a namespace prefix list; useful in case ``xpath`` option uses
    namespace prefixes.

``test``
    Test-option value. Accepted values are ``test-only``,
    ``test-then-set`` and ``set``.

``operation``
    Value of the attribute ``nc:operation``.  Useful with the ``set``
    operation, can be ``merge`` (the default), ``replace``, ``create``.

``del-operation``
    Value of the attribute ``nc:operation`` when used with the ``delete``
    operation, can be ``remove`` (the default) or ``delete``.
