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
import time
import queue

import sublime
import sublime_plugin

class Definition:
    def __init__(self, filename, fromOfs, toOfs):
        self.filename = filename
        self.fromOfs = fromOfs
        self.toOfs = toOfs

class Handler:
    def __init__(self, type, proc):
        self.type = type
        self.proc = proc

    def isMatch(self, type):
        return type == self.type

class OutputCollector:
    def __init__(self, stdout):
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
        stdout = self.stdout
        buffers_queue = self.buffers_queue
        while True:
            data = os.read(stdout.fileno(), OutputCollector.BUF_SIZE)

            if len(data) > 0:
                buffers_queue.put(data, block=False, timeout=None)
            else:
                stdout.close()
                self.isParserStayingAlive = False
                break

    def parse(self):
        while self.isParserStayingAlive:
            self.parseSingleResponse(self.readLine())

    MAX_WAIT = 5 # seconds, before we wake up and check whether we have to exit
    def readLine(self):
        fulls = self.fulls
        while self.isParserStayingAlive:
            cr = fulls.find("\n")
            if (cr != -1):
                # got full line
                s = fulls[:cr]
                if s.endswith('\r'): # remove LF from Windows CR/LF
                    s = s[:-1];
                fulls = fulls[cr+1:] # skip over CR
                self.fulls = fulls
                return s

            # Now have to wait for next line
            try:
                data = self.buffers_queue.get(block=True, timeout=OutputCollector.MAX_WAIT)
                fulls += data.decode(encoding="ASCII")
            except queue.Empty:
                pass

    @staticmethod
    def firstWord(line):
        ndxSpace = line.find(" ")
        return line[:ndxSpace] if ndxSpace != -1 else line

    def readUntil(self, endCommand):
        strings = []
        while True:
            newline = self.readLine()
            strings.append(newline + "\n")
            if OutputCollector.firstWord(newline) == endCommand:
                return ''.join(strings)

    def parseSingleResponse(self, line):
        if line is None or line == "": return
        command = OutputCollector.firstWord(line)

        buffer = "%s\n%s\n" % (line, self.readUntil(command + "-END"))
        for handler in self.handlers:
            if handler.isMatch(command):
                handler.proc(buffer)

    def addHandler(self, handler):
        self.handlers.append(handler)

    def removeHandler(self, handler):
        self.handlers.remove(handler)

class Daemon:
    def __init__(self, cmd):
        self.start(cmd)
        self.id = 0
        self.responses = {}

    def getNextUniqueId(self):
        self.id += 1
        return self.id

    def start(self, cmd):
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        print("Starting " + cmd)

        self.proc = subprocess.Popen(
            [cmd, '--codeblocks', '--disable-cancel',
            ],
            stdin = subprocess.PIPE,
            stdout = subprocess.PIPE,
            stderr = None,
            startupinfo=startupinfo)

        self.outputCollector = OutputCollector(self.proc.stdout)

        print("Started cfserver proc pid=%d" % (self.proc.pid))

        self.proc.stdin.write(bytes(
r'''
# source "C:\\Users\\alexander.APRELEV\\Downloads\\CppTools\\CppTools\\lib\\profile.tcl"
begin-config cmode
gcc -c "gcc"
# #user-source-root "C:/Users/alexander.APRELEV/IdeaProjects/untitled"
define WIN32 "1"
define NDEBUG "1"
define _WINDOWS "1"
define _MBCS "1"
define _AFXDLL "1"
define _WIN32 "1"
warning -implicit_cast_to_bool
warning +name_never_referenced
warning -name_used_only_once
warning +redundant_cast
warning +redundant_qualifier
warning +static_call_from_value
warning -redundant_brackets
warning +report_multiple_defs
# option +out_errorcodes
end-config
begin-config cppmode
g++ -c "g++"
# #user-source-root "C:/Users/alexander.APRELEV/IdeaProjects/untitled"
define WIN32 "1"
define NDEBUG "1"
define _WINDOWS "1"
define _MBCS "1"
define _AFXDLL "1"
define _WIN32 "1"
warning -implicit_cast_to_bool
warning +name_never_referenced
warning -name_used_only_once
warning +redundant_cast
warning +redundant_qualifier
warning +static_call_from_value
warning -redundant_brackets
warning +report_multiple_defs
# option +out_errorcodes
end-config
option -deCR_on
unused
list-errors
''', "ascii"))


    def restartIfInactive(self, cmd):
        # if process was never started or if it exited, then restart
        if (self.proc == None or self.proc.poll() != None):
            self.start(cmd)
            return True
        else:
            return False

    def sendCommand(self, command):
        print(">> %s" % (command))
        self.proc.stdin.write(bytes(command + "\n", "ascii"))
        self.proc.stdin.flush()

class Cfserver():
    def get_settings():
        return sublime.load_settings("Cfserver.sublime-settings")

    def get_setting(key, default=None, view=None):
        try:
            if view == None:
                view = sublime.active_window().active_view()
            s = view.settings()
            if s.has("cfserver_%s" % key):
                return s.get("cfserver_%s" % key)
        except:
            pass
        return Cfserver.get_settings().get(key, default)

    daemon = None

    def run(self, cmd, code):
        pass

    @staticmethod
    def getDaemon():
        restarted = False
        if Cfserver.daemon == None:
            Cfserver.daemon = Daemon(Cfserver.cfserverExecutable())
            restarted = True
        else:
            restarted = Cfserver.daemon.restartIfInactive(Cfserver.cfserverExecutable())

        if (restarted):
            Cfserver.daemon.outputCollector.addHandler(ErrorsHandler())
            Cfserver.daemon.outputCollector.addHandler(Handler("PROGRESS-START", 
                                                       Cfserver.reportProgressStart))
            Cfserver.daemon.outputCollector.addHandler(Handler("PROGRESS-END", 
                                                       Cfserver.reportProgressEnd))

        return Cfserver.daemon

    @staticmethod
    def cfserverExecutable():
        return Cfserver.get_setting("cfserver_path", "cfserver.exe")

    @staticmethod
    def selectModule(filename):
        daemon = Cfserver.getDaemon()
        daemon.sendCommand("module \"%s\" %s" % (
            filename.replace("\\", "\\\\"),
            "cppmode" if os.path.basename(filename).endswith(".cpp") else "cmode"))

    @staticmethod
    def analyzeModule(view):
        daemon = Cfserver.getDaemon()
        Cfserver.selectModule(view.file_name())
        idErrors = daemon.getNextUniqueId()
        daemon.sendCommand("analyze -n %d \"%s\" 0 end"
            % (idErrors,
               view.file_name().replace("\\", "\\\\")))

    reProgressStart = re.compile(
        r'PROGRESS-START \"(?P<message>.+)\"',
        re.MULTILINE)

    @staticmethod
    def reportProgressStart(message):
        match = Cfserver.reProgressStart.match(message)
        if match:
            sublime.status_message("Cfserver: %s" % (match.group('message')))

    @staticmethod
    def reportProgressEnd(message):
        sublime.status_message("")

class ErrorsHandler(Handler):
    def __init__(self):
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
        if ErrorsHandler.mark_error_png == None:
            ErrorsHandler.mark_error_png = sublime.find_resources("cfserver-mark-error.png")[0]
        return ErrorsHandler.mark_error_png

    mark_warning_png = None    
    @staticmethod
    def getMarkWarningPng():
        if ErrorsHandler.mark_warning_png == None:
            ErrorsHandler.mark_warning_png = sublime.find_resources("cfserver-mark-warning.png")[0]
        return ErrorsHandler.mark_warning_png

    def proc(self, message):
        match = ErrorsHandler.reErrors.match(message)
        if match:
            view = sublime.active_window().find_open_file(match.group('filename'))
            if view: # file is still around
                matchErrorsWithOffsets = ErrorsHandler.reErrorWithOffsets.finditer(match.group('allerrors'))
                regionsErrors = []
                regionsWarnings = []
                cnt = 0
                for matchedError in matchErrorsWithOffsets:
                    fromOfs = int(matchedError.group('fromOfs'))
                    toOfs = int(matchedError.group('toOfs'))
                    message = matchedError.group('message').replace("\r", "")
                    error_type = matchedError.group('type');

                    region = sublime.Region(fromOfs, toOfs)
                    if (error_type == 'ERROR'):
                        regionsErrors.append(region)
                    else:
                        regionsWarnings.append(region)
                    cnt+=1
                view.add_regions(
                    "cfserver_errors",
                    regionsErrors,
                    "invalid.deprecated",
                    ErrorsHandler.getMarkErrorPng(),
                    sublime.DRAW_NO_FILL)
                view.add_regions("cfserver_warnings",
                    regionsWarnings,
                    "invalid",
                    ErrorsHandler.getMarkWarningPng(),
                    sublime.DRAW_NO_FILL)

class CfserverEventListener(sublime_plugin.EventListener):
    def on_activated(self, view):
        if is_supported_language(view) and view.file_name is not None:
            #Cfserver.selectModule(view.file_name())
            Cfserver.analyzeModule(view)

    def on_load_async(self, view):
        if is_supported_language(view) and view.file_name is not None:
            #Cfserver.selectModule(view.file_name())
            Cfserver.analyzeModule(view)

    def on_post_save_async(self, view):
        if is_supported_language(view) and view.file_name is not None:
            #Cfserver.selectModule(view.file_name())
            Cfserver.analyzeModule(view)

    def on_query_completions(self, view, prefix, locations):
        if is_supported_language(view) and view.file_name is not None:
            print("on_query_completions: in %s with %s at %s " %
                (view, prefix, locations))
            return [("Try this " + prefix, "sugs")]

def is_supported_language(view):
    if view.is_scratch() or view.file_name() == None:
        return False
    caret = view.sel()[0].a
    return (view.score_selector(caret, "source.c++ ") +
            view.score_selector(caret, "source.c ")) > 0

class CfserverGotoBase(sublime_plugin.TextCommand):

    def get_target(self, tu, data, offset, found_callback, folders):
        pass

    def found_callback(self, target):
        if target == None:
            sublime.status_message("Don't know where the %s is!" % self.goto_type)
        elif not isinstance(target, list):
            open(self.view, target)
        else:
            self.targets = target
            self.view.window().show_quick_panel(target, self.open_file)

    def open_file(self, idx):
        if idx >= 0:
            target = self.targets[idx]
            if isinstance(target, list):
                target = target[1]
            open(self.view, target)

    def run(self, edit):
        print("CfserverGotoBase %s" % edit)
        return


    def is_enabled(self):
        return is_supported_language(sublime.active_window().active_view())

    def is_visible(self):
        return is_supported_language(sublime.active_window().active_view())


class CfserverGotoImplementation(CfserverGotoBase):
    pass

class CfserverGotoDef(CfserverGotoBase):
    def run(self, edit):
        view = self.view
        offset = view.sel()[0].a
        text = view.word(offset)
        print("looking for definition of '%s'" % edit)

        daemon = Cfserver.getDaemon()
        Cfserver.selectModule(view.file_name())
        idErrors = daemon.getNextUniqueId()
        daemon.sendCommand("goto-def \"%s\" %d" % (view.file_name().replace("\\", "\\\\"), offset))
        defs = daemon.waitForUsages("defs", text)
        if defs == None:
            sublime.status_message("Don't know where %s is defined." % text)
            return
        view.window().open_file(defs[0].filename)
        view.sel().clear()
        view.sel().add(sublime.Region(defs[0].fromOfs, defs[0].toOfs))
        view.show(view.sel())
