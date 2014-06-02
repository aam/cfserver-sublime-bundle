#
# linter.py
# Linter for Cfserver C/C++ static code analysis engine
#
# Copyright (c) 2014 Alexander Aprelev
#
# License: MIT
#

"""This module exports the Cfserver plugin class."""

import subprocess
import os
import threading
import re
import queue
import bisect
import time

import sublime
import sublime_plugin


class Definition:

    """ Representation of Cfserver concept of definition."""

    def __init__(self, filename, fromOfs, toOfs):
        """ Create new Cfserver definition."""

        self.filename = filename
        self.fromOfs = fromOfs
        self.toOfs = toOfs


class Handler:

    """ Handler of one type of Cfserver message."""

    """ As Cfserver output is being processed, instances of
        this class are called to handle particular type of
        message."""

    def __init__(self, type, proc):
        """ Create new handler."""

        self.type = type
        self.proc = proc

    def isMatch(self, type):
        """ Check whether this handler is applicable or not."""

        return type == self.type


class OutputCollector:

    """ Collector and processor of Cfserver output. """

    def __init__(self, stdout):
        """ Create new OutputCollector. """
        self.stdout = stdout

        self.handlers = []

        self.buffers_queue = queue.Queue()
        self.fulls = ""

        self.isParserStayingAlive = True

        self.readerThread = threading.Thread(target=self.read_stdout)
        self.readerThread.start()
        self.parserThread = threading.Thread(target=self.parse)
        self.parserThread.start()

    BUF_SIZE = 32767

    def read_stdout(self):
        """ Continuously read Cfserver stdout stream."""
        stdout = self.stdout
        buffers_queue = self.buffers_queue
        while not stdout.closed:
            data = os.read(stdout.fileno(), OutputCollector.BUF_SIZE)
            print("read_stdout %s" % (data))

            if len(data) > 0:
                buffers_queue.put(data, block=False, timeout=None)
            else:
                stdout.close()
                self.isParserStayingAlive = False
                break

    def parse(self):
        """ Continuously parse what was read."""
        while self.isParserStayingAlive:
            self.parseSingleResponse(self.readLine())

    # Number of seconds to wait, before we wake up
    # and check whether we have to exit
    MAX_WAIT = 5

    def readLine(self):
        """ Read just one line."""
        fulls = self.fulls
        while self.isParserStayingAlive:
            cr = fulls.find("\n")
            if (cr != -1):
                # got full line
                s = fulls[:cr]
                if s.endswith('\r'):  # remove LF from Windows CR/LF
                    s = s[:-1]
                fulls = fulls[cr+1:]  # skip over CR
                self.fulls = fulls
                return s

            # Now have to wait for next line
            try:
                data = self.buffers_queue.get(block=True,
                                              timeout=OutputCollector.MAX_WAIT)
                fulls += data.decode(encoding="ASCII")
            except queue.Empty:
                pass

    @staticmethod
    def firstWord(line):
        """ Take first word. """
        ndxSpace = line.find(" ")
        return line[:ndxSpace] if ndxSpace != -1 else line

    def readUntil(self, endCommand):
        """ Keep reading until [endCommand] is encountered."""
        strings = []
        while True:
            newline = self.readLine()
            strings.append(newline + "\n")
            if OutputCollector.firstWord(newline) == endCommand:
                return ''.join(strings)

    def parseSingleResponse(self, line):
        """ Parse one Cfserver response."""
        if line is None or line == "":
            return
        command = OutputCollector.firstWord(line)

        buffer = "%s\n%s\n" % (line, self.readUntil(command + "-END"))
        for handler in self.handlers:
            if handler.isMatch(command):
                handler.proc(buffer)

    def addHandler(self, handler):
        """ Add new Cfserver output handler."""
        self.handlers.append(handler)

    def removeHandler(self, handler):
        """ Remove previously added Cfserver output handler."""
        self.handlers.remove(handler)


class Daemon:

    """ Class responsible for starting/stopping Cfserver executable."""

    def __init__(self, cmd, in_log, out_log):
        """ Initialize new Daemon."""
        self.start(cmd, in_log, out_log)
        self.id = 0
        self.responses = {}
        self.registeredFiles = set()

    def getNextUniqueId(self):
        """ Generate unique id to be used for new Cfserver request."""
        self.id += 1
        return self.id

    def start(self, cmd, in_log, out_log):
        """ Start new Cfserver executable."""
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        print("Starting " + cmd)

        command_line = [cmd, '--codeblocks', '--disable-cancel']
        if in_log is not None and in_log != '':
            command_line.append(['--inLogName', in_log])
        if out_log is not None and out_log != '':
            command_line.append(['--outLogName', out_log])

        self.proc = subprocess.Popen(
            command_line,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            startupinfo=startupinfo)

        self.outputCollector = OutputCollector(self.proc.stdout)

        print("Started cfserver proc pid=%d" % (self.proc.pid))

        self.proc.stdin.write(bytes(
            r'''#
begin-config cmode
gcc
end-config
begin-config cppmode
g++
end-config
''', "ascii"))

    def restartIfInactive(self, cmd):
        """ Restart process if it was never started or if it exited."""

        if (self.proc is None or self.proc.poll() is not None):
            self.start(cmd)
            return True
        else:
            return False

    def sendCommand(self, command):
        """ Send new command to Cfserver executable."""
        print(">> %s" % (command))
        self.proc.stdin.write(bytes(command + "\n", "ascii"))
        self.proc.stdin.flush()

    def isFileRegistered(self, filename):
        """ Check whether we have registered this file already."""
        return filename in self.registeredFiles

    def registerFile(self, filename):
        """ Register new file with Cfserver."""
        self.registeredFiles.add(filename)


class Cfserver():

    """ Basic Sublime plugin functionality."""

    def get_settings():
        """ Retrieve settings."""
        return sublime.load_settings("Cfserver.sublime-settings")

    def get_setting(key, default=None, view=None):
        """ Retrieve one settings."""
        try:
            if view is None:
                view = sublime.active_window().active_view()
            s = view.settings()
            if s.has("cfserver_%s" % key):
                return s.get("cfserver_%s" % key)
        except:
            pass
        return Cfserver.get_settings().get(key, default)

    daemon = None

    @staticmethod
    def getDaemon():
        """ Retrieve existing daemon or creates new one."""
        restarted = False
        if Cfserver.daemon is None:
            Cfserver.daemon = Daemon(
                Cfserver.cfserverExecutable(),
                Cfserver.cfserverInLog(),
                Cfserver.cfserverOutLog())
            restarted = True
        else:
            restarted = Cfserver.daemon.restartIfInactive(
                Cfserver.cfserverExecutable())

        if (restarted):
            Cfserver.daemon.outputCollector.addHandler(ErrorsHandler())
            Cfserver.daemon.outputCollector.addHandler(
                Handler("ERRORS-CLEAR", Cfserver.clearErrors))
            Cfserver.daemon.outputCollector.addHandler(
                Handler("PROGRESS-START", Cfserver.reportProgressStart))
            Cfserver.daemon.outputCollector.addHandler(
                Handler("PROGRESS-END", Cfserver.reportProgressEnd))

        return Cfserver.daemon

    @staticmethod
    def cfserverExecutable():
        """ Retrieve cfserver executable name from settings."""
        return Cfserver.get_setting("cfserver_path", "cfserver.exe")

    @staticmethod
    def cfserverInLog():
        """ Retrieve location for cfserver in log from settings."""
        return Cfserver.get_setting("cfserver_inlog", "in")

    @staticmethod
    def cfserverOutLog():
        """ Retrieve location for cfserver out log from settings."""
        return Cfserver.get_setting("cfserver_outlog", "out")

    @staticmethod
    def registerFileIfNotLoaded(filename):
        """ Ask Cfserver to load the  file if see it for the first time."""
        daemon = Cfserver.getDaemon()
        if (not daemon.isFileRegistered(filename)):
            daemon.registerFile(filename)
            basename = os.path.basename(filename)
            print("registerFileIfNotLoaded basename='%s'" % basename)
            if basename.endswith(".h") or basename.endswith(".hh"):
                pass
            else:
                daemon.sendCommand("module \"%s\" %s" % (
                    filename.replace("\\", "\\\\"),
                    "cmode" if os.path.basename(filename).endswith(".c")
                    else "cppmode"))
            return True
        else:
            return False

    @staticmethod
    def analyzeModule(view):
        """ Issue Cfserver command to analyze file in given view."""
        daemon = Cfserver.getDaemon()
        filename = view.file_name().replace("\\", "\\\\")
        if not Cfserver.registerFileIfNotLoaded(view.file_name()):
            daemon.sendCommand("reload \"%s\"" % (filename))
        idErrors = daemon.getNextUniqueId()
        daemon.sendCommand(
            "analyze -n %d \"%s\" 0 end" % (idErrors, filename))

    reProgressStart = re.compile(
        r'PROGRESS-START \"(?P<message>.+)\"',
        re.MULTILINE)

    @staticmethod
    def reportProgressStart(message):
        """ Handle PROGRESS-START Cfserver response."""
        match = Cfserver.reProgressStart.match(message)
        if match:
            sublime.status_message("Cfserver: %s" % (match.group('message')))

    @staticmethod
    def reportProgressEnd(message):
        """ Handle PROGRESS-END Cfserver response."""
        sublime.status_message("")

    errorsInFile = {}  # Selection of errors in particular file.

    REGION_ERRORS = "cfserver_errors"
    REGION_WARNINGS = "cfserver_warnings"

    @staticmethod
    def clearErrors(message):
        """ Handle ERRORS-CLEAR Cfserver response."""
        # fishy, but there is no indication regarding what file
        # errors are being cleared for
        view = sublime.active_window().active_view()
        view.erase_regions(Cfserver.REGION_ERRORS)
        view.erase_regions(Cfserver.REGION_WARNINGS)
        Cfserver.errorsInFile = {}


class ErrorsInFile:

    """ Holder of all errors/warnings in particular file."""

    def __init__(self,
                 regionsLeftBoundaries=None,
                 messages=None):
        """ Initialize holder."""
        self.regionsLeftBoundaries = regionsLeftBoundaries
        self.messages = messages


class ErrorsHandler(Handler):

    """ Handler for ERRORS Cfserver response."""

    def __init__(self):
        """ Initialize handler."""
        super().__init__("ERRORS", self.proc)

    reErrors = re.compile(
        r'((.*)(\r?\n))*^ERRORS \"(?P<filename>.+)\"\s(?P<id>\d+)\r?\n'
        r'(?P<allerrors>((.*)\r?\n)+)'
        r'^ERRORS-END(\r?\n)?',
        re.MULTILINE)

    reErrorWithOffsets = re.compile(
        r'(?P<type>(ERROR|WARN|INFO)) '
        r'(?P<fromOfs>\d+) (?P<toOfs>\d+) (?P<message>.+)\r?\n')

    mark_error_png = None

    @staticmethod
    def getMarkErrorPng():
        """ Retrieve png for error mark."""
        if ErrorsHandler.mark_error_png is None:
            ErrorsHandler.mark_error_png = sublime.find_resources(
                "cfserver-mark-error.png")[0]
        return ErrorsHandler.mark_error_png

    mark_warning_png = None

    @staticmethod
    def getMarkWarningPng():
        """ Retrieve png for warning mark."""

        if ErrorsHandler.mark_warning_png is None:
            ErrorsHandler.mark_warning_png = sublime.find_resources(
                "cfserver-mark-warning.png")[0]
        return ErrorsHandler.mark_warning_png

    def proc(self, message):
        """ Parse and process errors reported by Cfserver."""
        match = ErrorsHandler.reErrors.match(message)
        # print("got message '%s' and match is '%s'" % (message, match))
        if match:
            view = sublime.active_window().find_open_file(
                match.group('filename'))
            if view:  # file is still around
                filename = view.file_name()
                matchErrorsWithOffsets = (
                    ErrorsHandler.reErrorWithOffsets.finditer(
                        match.group('allerrors')))
                regionsErrors = []
                regionsWarnings = []
                messages = {}
                for matchedError in matchErrorsWithOffsets:
                    fromOfs = int(matchedError.group('fromOfs'))
                    toOfs = int(matchedError.group('toOfs'))
                    message = matchedError.group('message').replace("\r", "")
                    error_type = matchedError.group('type')

                    region = sublime.Region(fromOfs, toOfs)
                    if (error_type == 'ERROR'):
                        regionsErrors.append(region)
                    else:
                        regionsWarnings.append(region)
                    if fromOfs not in messages:
                        messages[fromOfs] = []
                    messages[fromOfs].append((toOfs, message))

                for message in messages.values():
                    message.sort(key=lambda r: r[0])

                view.add_regions(Cfserver.REGION_ERRORS,
                                 regionsErrors,
                                 "invalid.deprecated",
                                 ErrorsHandler.getMarkErrorPng(),
                                 sublime.DRAW_NO_FILL)
                view.add_regions(Cfserver.REGION_WARNINGS,
                                 regionsWarnings,
                                 "invalid",
                                 ErrorsHandler.getMarkWarningPng(),
                                 sublime.DRAW_NO_FILL)
                Cfserver.errorsInFile[filename] = ErrorsInFile(
                    regionsLeftBoundaries=sorted(
                        list(r.a for r in regionsErrors) +
                        list(r.a for r in regionsWarnings)),
                    messages=messages)


class CfserverEventListener(sublime_plugin.EventListener):

    """ Plugin event listener."""

    def on_activated(self, view):
        """ Handle on_activated event."""
        if is_supported_language(view) and view.file_name() is not None:
            # Cfserver.selectModule(view.file_name())
            Cfserver.analyzeModule(view)

    def on_load_async(self, view):
        """ Handle on_load_async event."""
        if is_supported_language(view) and view.file_name() is not None:
            # Cfserver.selectModule(view.file_name())
            Cfserver.analyzeModule(view)

    def on_post_save_async(self, view):
        """ Handle on_post_save_async event."""
        if is_supported_language(view) and view.file_name() is not None:
            # Cfserver.selectModule(view.file_name())
            Cfserver.analyzeModule(view)

    def on_query_completions(self, view, prefix, locations):
        """ Handle on_query_completions event."""
        if is_supported_language(view) and view.file_name is not None:
            print("on_query_completions: in %s with %s at %s " %
                  (view, prefix, locations))
            return [("Try this " + prefix, "sugs")]

    def on_selection_modified_async(self, view):
        """Handle selection changes (cursor moves or text selected)."""
        filename = view.file_name()
        if is_supported_language(view) and filename is not None:
            if (filename in Cfserver.errorsInFile):
                selection = view.sel()[0]
                errors = Cfserver.errorsInFile[filename]
                rightmostLower = bisect.bisect_left(
                    errors.regionsLeftBoundaries, selection.a)
                if rightmostLower:
                    rightmostLowerMessages = (
                        errors.messages[
                            errors.regionsLeftBoundaries[rightmostLower - 1]])
                    messages = []
                    for m in rightmostLowerMessages:
                        if m[0] < selection.a:
                            continue
                        messages.append(m[1])
                    view.set_status("cfserver_errors", ",".join(messages))
                    return
        view.erase_status("cfserver_errors")


def is_supported_language(view):
    """ Confirm whether view hosts source C/C++ code."""
    if view.is_scratch() or view.file_name() is None:
        return False
    caret = view.sel()[0].a
    return (view.score_selector(caret, "source.c++ ") +
            view.score_selector(caret, "source.c ")) > 0


class CfserverFind(sublime_plugin.TextCommand):

    """ Navigation command."""

    def set_find_command(self, find_command):
        self.find_command = find_command

    def is_enabled(self):
        return is_supported_language(sublime.active_window().active_view())

    def is_visible(self):
        return is_supported_language(sublime.active_window().active_view())

    """ Support navigation to definitions."""

    def run(self, edit):
        """ Send find command request to Cfserver."""
        view = self.view
        offset = view.sel()[0].a
        #  text = view.word(offset)
        print("looking for definition of '%s'" % edit)

        daemon = Cfserver.getDaemon()
        Cfserver.registerFileIfNotLoaded(view.file_name())

        Cfserver.daemon.outputCollector.addHandler(UsagesHandler())

        daemon.sendCommand(
            "%s \"%s\" %d" % (
                self.find_command,
                view.file_name().replace("\\", "\\\\"),
                offset))


class UsagesHandler(Handler):

    """ Handler for USAGES Cfserver response."""

    def __init__(self):
        """ Initialize handler."""
        super().__init__("USAGES", self.proc)

    reUsages = re.compile(
        r'((.*)(\r?\n))*^USAGES (?P<type>.+) \"(?P<name>.+)\"\r?\n'
        r'(?P<allusages>((.+)\r?\n)+)'
        r'^USAGES-END(\r?\n)?',
        re.MULTILINE)

    reUsage = re.compile(
        r'^(?P<type>.+) '
        r'\"(?P<filename>.+)\" '
        r'(?P<fromOfs>\d+) (?P<toOfs>\d+) '
        r'\"(?P<quote>[^\"]+)\" '
        r'.+\r?\n',
        re.MULTILINE)

    def proc(self, message):
        """ Parse and process usages reported by Cfserver."""
        Cfserver.daemon.outputCollector.removeHandler(self)

        match = UsagesHandler.reUsages.match(message)
        if match is None:
            return

        matchUsage = UsagesHandler.reUsage.finditer(match.group('allusages'))
        if matchUsage is None:
            return

        hits = []
        for matchedUsage in matchUsage:
            matchtype = matchedUsage.group('type')
            filename = matchedUsage.group('filename')
            fromOfs = int(matchedUsage.group('fromOfs'))
            toOfs = int(matchedUsage.group('toOfs'))
            quote = bytes(matchedUsage.group('quote'),
                          "ascii").decode("unicode_escape").strip()
            print("quote is '%s'" % quote)
            hits.append((matchtype, filename, fromOfs, toOfs, quote))

        if len(hits) > 1:
            sublime.active_window().show_quick_panel(
                ["%s: %s" % (h[0], h[4]) for h in hits],
                lambda index: UsagesHandler.selectHit(
                    hits[index] if index != -1 else None))
        elif len(hits) == 1:
            UsagesHandler.selectHit(hits[0])

    @staticmethod
    def selectHit(hit):
        if hit:
            (matchtype, filename, fromOfs, toOfs, quote) = hit
            view = sublime.active_window().open_file(filename)
            if view.is_loading():
                threading.Thread(
                    target=UsagesHandler.navigate_to_location_once_loaded,
                    args=(view, hit)).start()
            else:
                view.sel().clear()
                view.sel().add(sublime.Region(fromOfs, toOfs))
                view.show_at_center(view.sel()[0])

    @staticmethod
    def navigate_to_location_once_loaded(view, hit):
        while view.is_loading():
            time.sleep(1)  # sleep for 1 sec
        view.sel().clear()
        (matchtype, filename, fromOfs, toOfs, quote) = hit
        view.sel().add(sublime.Region(fromOfs, toOfs))
        view.show_at_center(view.sel()[0])


class CfserverGotoDef(CfserverFind):

    def __init__(self, view):
        super().__init__(view)
        self.set_find_command("goto-def")


class CfserverFindUsages(CfserverFind):

    def __init__(self, view):
        super().__init__(view)
        self.set_find_command("find-usages")


class CfserverFindDecls(CfserverFind):

    def __init__(self, view):
        super().__init__(view)
        self.set_find_command("find-declarators")


class CfserverFindParents(CfserverFind):

    def __init__(self, view):
        super().__init__(view)
        self.set_find_command("find-parents")


class CfserverFindInheritors(CfserverFind):

    def __init__(self, view):
        super().__init__(view)
        self.set_find_command("find-inheritors")
