import os
import readline
import itertools


def no_arg_completion(text):
    return []


def commit_arg_completion(text):
    return ["confirmed"]


def fix_completion_dirname(name):
    if os.path.isdir(name) and name[-1] != "/":
        return name + "/"
    else:
        return name


def filename_arg_completion(text):
    dir = os.path.dirname(text)
    rdir = "." if dir == "" else dir
    return [fix_completion_dirname(os.path.join(dir, name)) for name in os.listdir(rdir)]


def validate_arg_completion(text):
    return ["candidate"] + filename_arg_completion(text)


class NCCompleter(object):
    def __init__(self, operations, option_args):
        self.operations = operations
        self.option_args = option_args

    def __call__(self, text, state):
        return self.complete_with(text, state, readline.get_line_buffer())

    def complete_command_argument(self, operation, text):
        if operation.name in ["kill_session", "get_schema", "create_subscription", "sleep"]:
            return []
        if operation.name == "commit":
            return ["confirmed"]

    def lookup_option(self, option_text):
        for (opts, descriptor) in self.option_args.values():
            if option_text in opts:
                return descriptor
        return None

    def complete_command_options(self, text, line_args):
        opname = line_args[0]
        try:
            operation = self.operations[opname]
        except KeyError:
            return []
        cmdargs = []
        word_count = len(line_args)
        if text == "":
            # the user pressed TAB for a new command option
            word_count += 1
        if word_count == 2:
            # command argument (filename for edit-config, datastore for validate, ...)
            cmdargs = operation.arg_completion(text)
            if operation.nargs == 1:
                return cmdargs
        if word_count > 2:
            opt_descriptor = self.lookup_option(line_args[word_count - 2])
            if opt_descriptor is not None:
                if "choices" in opt_descriptor:
                    return opt_descriptor["choices"]
                elif opt_descriptor["dest"] == "db":
                    return ["running", "candidate"]
                return []  # no completion for timeout or xpath
        opts = [self.option_args[option][0] for option in operation.command_opts]
        return cmdargs + list(itertools.chain(*opts))

    def complete_with(self, text, state, line):
        line_args = line.split()
        if len(line_args) > 1 or len(line_args) == 1 and text == "":
            variants = self.complete_command_options(text, line_args)
        else:
            variants = self.operations.keys()
        permitted = sorted(var for var in variants if var.startswith(text))
        if len(permitted) <= state:
            return None
        return permitted[state]
