#
# linter.py
# Linter for SublimeLinter3, a code checking framework for Sublime Text 3
#
# Written by alexander
# Copyright (c) 2014 alexander
#
# License: MIT
#

"""This module exports the Cfserver plugin class."""

import subprocess
import os
import threading
import re
import time

import sublime
import sublime_plugin

import SublimeLinter

# from Default.exec import ProcessListener, AsyncProcess

class Daemon:
    def __init__(self, cmd):
        self.start(cmd)
        self.id = 0
        self.responses = {}

    def getNextUniqueId(self):
        self.id += 1
        return self.id

    def getErrors(self, responseId):
        nAttempts = 10
        while (not responseId in self.responses and nAttempts>0):
            time.sleep(1)  # sleep 1s econd
            nAttempts -= 1

        return self.responses.pop(responseId)

    reErrors = re.compile(
        r'((.*)(\r?\n))*^ERRORS \"(?P<filename>.+)\"\s(?P<id>\d)\r?\n'
        r'(?P<allerrors>((.*)\r?\n)+)'
        r'^ERRORS-END\r?\n',
        re.MULTILINE)

    def on_data(self, data):
        s = data.decode(encoding="ASCII")
        print("on_data: s=%s" % (s))
        match = Daemon.reErrors.match(s)
        if match:
            self.responses[int(match.group('id'))] = match.group('allerrors')

    def on_finished(self):
       print("on_finished")

    def read_stdout(self):
        while True:
            data = os.read(self.proc.stdout.fileno(), 2**15)

            if len(data) > 0:
                self.on_data(data)
            else:
                self.proc.stdout.close()
                self.on_finished()
                break

    def read_stderr(self):
        while True:
            data = os.read(self.proc.stderr.fileno(), 2**15)

            if len(data) > 0:
                self.on_data(data)
            else:
                self.proc.stderr.close()
                break

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
            stderr = subprocess.PIPE,
            startupinfo=startupinfo)

        threading.Thread(target=self.read_stdout).start()
        threading.Thread(target=self.read_stderr).start()

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
unused
list-errors
''', "ascii"))


    def ensureActive(self, cmd):
        # if process was never started or if it exited, then restart
        if (self.proc == None or self.proc.poll() != None):
            self.start(cmd)

    def sendCommand(self, command):
        print("sending %s" % (command))
        self.proc.stdin.write(bytes(command + "\n", "ascii"))
        self.proc.stdin.flush()

class Cfserver(SublimeLinter.sublimelinter.Linter):

    """Provides an interface to cfserver."""

    syntax = ('c++')
    cmd = None
    executable = None
    version_args = '--version'
    version_re = r'(?P<version>\d+\.\d+\.\d+)'
    version_requirement = '>= 1.0'

    regex = r'(?:(?P<error>ERROR)|(?P<warning>WARN)|(?P<info>INFO)) (?P<line>\d+) (?P<col>\d+) (?P<message>.+)'
    multiline = True
    line_col_base = (0, 0)
    tempfile_suffix = None
    error_stream = None
    selectors = {}
    word_re = None
    defaults = {}
    inline_settings = None
    inline_overrides = None
    comment_re = None

    def __init__(self, view, syntax):
        SublimeLinter.sublimelinter.Linter.__init__(self, view, syntax)

    def get_settings():
        return sublime.load_settings("SublimeLinter-contrib-cfserver.sublime-settings")

    def get_setting(key, default=None, view=None):
        try:
            if view == None:
                view = sublime.active_window().active_view()
            s = view.settings()
            if s.has("sublimecontribcfserver_%s" % key):
                return s.get("sublimecontribcfserver_%s" % key)
        except:
            pass
        return Cfserver.get_settings().get(key, default)

    daemon = None

    def run(self, cmd, code):
        print("cfserver run started in %s" % (sublime.active_window().active_view().file_name()))
        return Cfserver.analyzeModule(sublime.active_window().active_view())


    @staticmethod
    def getDaemon():
        if Cfserver.daemon == None:
            Cfserver.daemon = Daemon(Cfserver.cfserverExecutable())
        else:
            Cfserver.daemon.ensureActive(Cfserver.cfserverExecutable())
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

    reErrorWithOffsets = re.compile(
        r'(?P<type>(ERROR|WARN|INFO)) '
        r'(?P<fromOfs>\d+) (?P<toOfs>\d+) (?P<message>.+)\r?\n')

    @staticmethod
    def analyzeModule(view):
        print("analyzeMethod called for file %s" % (view.file_name()))
        daemon = Cfserver.getDaemon()
        Cfserver.selectModule(view.file_name())
        idErrors = daemon.getNextUniqueId()
        daemon.sendCommand("analyze -n %d \"%s\" 0 end"
            % (idErrors,
               view.file_name().replace("\\", "\\\\")))
        errorsWithOffsets = daemon.getErrors(idErrors)

        matchErrorsWithOffsets = Cfserver.reErrorWithOffsets.finditer(errorsWithOffsets)
        allErrors = ''
        for matchedError in matchErrorsWithOffsets:
            fromOfs = int(matchedError.group('fromOfs'))
            (row, col) = view.rowcol(fromOfs)
            message = matchedError.group('message').replace("\r", "")
            allErrors += "%s %d %d %s\n" % (matchedError.group('type'),
                                          row,
                                          col,
                                          message)
        print("post translation allerrors: %s" % allErrors)
        return allErrors


# class CfserverEventListener(sublime_plugin.EventListener):
#     def on_activated(self, view):
#         print("CfserverEventListener.on_activated in %s" % (view.file_name()))
#         is_at_front = (view.window() is not None and view.window().active_view() == view)
#         if (is_at_front and view.file_name() != None):
#             Cfserver.selectModule(view.file_name())
