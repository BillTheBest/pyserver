# -*- coding: utf-8 -*-
'''Pyserver2 application entry.'''
'''
  Kontalk pyserver2
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


class Pyserver2App:
    '''Application starter.'''

    def __init__ (self, argv):
        self.application = service.Application("Pyserver2")
        # FIXME this won't work with twistd - need to write a twistd plugin
        self._cfgfile = 'server.conf'
        for i in range(len(argv)):
            if argv[i] == '-c':
                self._cfgfile = argv[i + 1]

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

        return self.application
