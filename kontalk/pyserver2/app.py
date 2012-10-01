# -*- coding: utf-8 -*-
'''Pyserver application entry.'''
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

import kontalklib.logging as log
from Queue import Queue
import json

from twisted.application import internet, service

from broker import MessageBroker
from fileserver import Fileserver
from monitor import WebMonitor


class PyserverApp:
    '''Application starter.'''

    def __init__ (self, argv):
        self.application = service.Application("Pyserver")
        self._cfgfile = 'server.conf'
        if 'config' in argv:
            self._cfgfile = argv['config']

    def setup(self):
        # load configuration
        fp = open(self._cfgfile, 'r')
        self.config = json.load(fp)
        fp.close()

        log.init(self.config)

        # broker service
        self.broker = MessageBroker(self.application, self.config)
        # fileserver service
        if self.config['server']['fileserver.enabled']:
            self.fileserver = Fileserver(self.application, self.config, self.broker)

        # monitor service
        if self.config['server']['monitor.enabled']:
            self.monitor = WebMonitor(self.application, self.config, self.broker)

        return self.application
