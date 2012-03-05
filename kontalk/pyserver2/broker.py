# -*- coding: utf-8 -*-
'''The Message Broker Service.'''
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

import os, socket, time
from Queue import Queue

from twisted.application import internet, service
from twisted.internet.defer import Deferred

# local imports
import txprotobuf
from broker_twisted import *
import version
import kontalk.config as config


class MessageBrokerChannel:
    def __init__(self, protocol, broker):
        self.protocol = protocol
        self.broker = broker


class MessageBroker:
    '''Message broker connection manager.'''

    # keys: generic or specific userid, values: Queue
    _queues = {}

    def __init__(self, application):
        self.application = application

    def setup(self):
        # create listening service
        factory = InternalServerFactory(MessageBrokerChannel, self)
        service = internet.TCPServer(port=config.config['server']['broker.bind'][1],
            factory=factory, interface=config.config['server']['broker.bind'][0])
        service.setServiceParent(self.application)
