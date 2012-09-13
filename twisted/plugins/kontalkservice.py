# -*- coding: utf-8 -*-
'''twistd plugin for pyserver.'''
'''
  Kontalk Pyserver
  Copyright (C) 2011 Kontalk Devteam <devteam@kontalk.org>

 This program is free software: you can redistribute it and/or modify
 it under the terms of the GNU General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 This program is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU General Public License for more details.

 You should have received a copy of the GNU General Public License
 along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

import sys

from zope.interface import implements

from twisted.python import usage
from twisted.plugin import IPlugin
from twisted.application.service import IServiceMaker, IService
from twisted.application import internet


class Options(usage.Options):
    optParameters = [["config", "c", "server.conf", "Configuration file."]]


class KontalkServiceMaker(object):
    implements(IServiceMaker, IPlugin)
    tapname = "kontalk"
    description = "A Kontalk messaging server."
    options = Options

    def makeService(self, options):
        from kontalk.pyserver2 import app
        appl = app.PyserverApp(options)
        return IService(appl.setup())


serviceMaker = KontalkServiceMaker()
