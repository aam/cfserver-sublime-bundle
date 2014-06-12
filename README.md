# Cfserver C/C++ bundle for Sublime
===================================

This bundle brings C/C++ static analysis capabilities provided by Advanced Tools [Cfserver](http://www.adv-tools.com/) to Sublime Text. The following features are currently provided:

* Errors/warnings reported by Cfserver.
* Navigation to definition/usage

Next on the list are:
* Code completion
* Analysis on the fly(without need to save file)

PRE-REQ
=======

You will need to have [Cfserver](http://www.adv-tools.com/) binary for your OS available locally in order to use this plugin. 

INSTALLATION
============

### Using Package Control

Installing through the [Package Control][1] plugin is the recommended way:

- Open the command palette (<kbd>Ctrl+Shift+P</kbd> or <kbd>⌘+Shift+P</kbd>)
- Type 'install'
- Select **Package Control: Install Package**
- Type 'Cfserver'
- Select 'Cfserver'

You may need to restart ST3 before you can start using all the features in the
package.

### Manually

To install this package manually, copy the the contents of this repository to a
new directory in the Sublime packages directory (on OSX:
~/Library/Application Support/Sublime Text 3/Packages).

You can also clone github repository directly into your packages directory:

    aam@mac:~/Library/Application Support/Sublime Text 3/Packages$ git clone https://github.com/aam/cfserver-sublime-bundle.git Cfserver
    Cloning into 'Cfserver'...
    remote: Counting objects: 59, done.
    remote: Compressing objects: 100% (47/47), done.
    remote: Total 59 (delta 25), reused 42 (delta 9)
    Unpacking objects: 100% (59/59), done.

Add the `cfserver_path` variable pointing to cfserver to your user settings:

    {
        "cfserver_path" : "c:\\Users\\baz\\cfserver.exe",
    }

LICENSE
=======

Copyright (c) 2014 Alexander Aprelev

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
