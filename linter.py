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
import SublimeLinter
import sublime

# from Default.exec import ProcessListener, AsyncProcess


class CfserverListener:
    def on_data(self, proc, data):
        print("CfserverListener.on_data: proc=%s data=%s" % (proc, data))

    def on_finished(self, proc):
        print("CfserverListener.on_finished: proc=%s" % (proc))
        pass

class Cfserver(Linter):

    """Provides an interface to cfserver."""

    syntax = ('c++')
    cmd = None
    executable = None
    version_args = '--version'
    version_re = r'(?P<version>\d+\.\d+\.\d+)'
    version_requirement = '>= 1.0'
    regex = 'ERROR (?P<line>\d+) (?P<col>\d+) (?P<error>\d+) (?P<message>.+)'
    multiline = False
    line_col_base = (1, 1)
    tempfile_suffix = None
    error_stream = util.STREAM_BOTH
    selectors = {}
    word_re = None
    defaults = {}
    inline_settings = None
    inline_overrides = None
    comment_re = None
    cfserver = None
    cfserverListener = CfserverListener()

    def __init__(self, view, syntax):
        Linter.__init__(self, view, syntax)

    def write_stdin(self):
        Cfserver.cfserver.stdin.write(bytes(
r'''
source "C:\\Users\\alexander.APRELEV\\Downloads\\CppTools\\CppTools\\lib\\profile.tcl"
# version 0.8.3 (Win32) build no. 1 on Feb 28 2012 14:45:38
# Command: "C:/Users/alexander.APRELEV/.IntelliJIdea13/system/plugins-sandbox/plugins/CppTools/lib/cfserver.exe" --idea --catchexceptions --inLogName C:\\Users\\alexander.APRELEV\\.IntelliJIdea13\\system\\plugins-sandbox\\plugins\\CppTools\\logs\\untitled\in --outLogName C:\\Users\\alexander.APRELEV\\.IntelliJIdea13\\system\\plugins-sandbox\\plugins\\CppTools\\logs\\untitled\\out
# Library: $Id: lib.tcl, 2010/11/26 14:27 shd Exp $
#timer: 0.003
source "C:\\Users\\alexander.APRELEV\\Downloads\\CppTools\\CppTools\\lib\\lib.tcl"
#timer: 0.004
use-abs-path
begin-config cmode
gcc -c "gcc"
#timer: 0.53
user-source-root "C:/Users/alexander.APRELEV/IdeaProjects/untitled"
define WIN32 "1"
'''
            , "ascii"))
        Cfserver.cfserver.stdin.flush()

    def read_stdout(self):
        while True:
            data = os.read(Cfserver.cfserver.stdout.fileno(), 2**15)

            if len(data) > 0:
                if Cfserver.cfserverListener:
                    Cfserver.cfserverListener.on_data(self, data)
            else:
                Cfserver.cfserver.stdout.close()
                if Cfserver.cfserverListener:
                    Cfserver.cfserverListener.on_finished(self)
                break

    def read_stderr(self):
        while True:
            data = os.read(Cfserver.cfserver.stderr.fileno(), 2**15)

            if len(data) > 0:
                if Cfserver.cfserverListener:
                    Cfserver.cfserverListener.on_data(self, data)
            else:
                Cfserver.cfserver.stderr.close()
                break

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

    def run(self, cmd, code):
        print("cfserver")

        print("Initialized cfserver linter. [Re]starting cfserver = %s" % Cfserver.cfserver)
        if Cfserver.cfserver != None and Cfserver.cfserver.poll() == None:
            print("Cfserver already running with pid %d" % (Cfserver.cfserver.pid))
        else:
            startupinfo = None
            if os.name == "nt":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            cmd = Cfserver.get_setting("cfserver_path", "cfserver.exe")

            print("Starting " + cmd)

            Cfserver.cfserver = util.popen(cmd)

            if Cfserver.cfserver.stdout:
                threading.Thread(target=self.read_stdout).start()

            if Cfserver.cfserver.stderr:
                threading.Thread(target=self.read_stderr).start()

            print("Started cfserver pid=%d" % (Cfserver.cfserver.pid))
        self.write_stdin()


#        print("cfserver linter %s run cmd=%s, code=%s" % (self, cmd, code))
        return (
            r'ERRORS "c:\\Users\\alexander.APRELEV\\IdeaProjects\\untitled\\test.cpp" 0\n'
            r'ERROR 215 216 27 "\r" "after" ";"\n'
            r'ERROR 225 227 15 "STRUCT "\n'
            r'ERROR 253 254 27 "\r" "after" ";"\n'
            r'ERRORS-END"\n')
