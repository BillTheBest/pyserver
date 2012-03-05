# -*- coding: utf-8 -*-
'''Twisted-related broker code.'''
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

from twisted.internet.protocol import ServerFactory
import txprotobuf


class InternalServerProtocol(txprotobuf.Protocol):

    def __init__(self):
        pass

    def connectionMade(self):
        print "connection made!"

    def boxReceived(self, data):
        print "box received", data


class InternalServerFactory(ServerFactory):
    protocol = InternalServerProtocol

    def __init__(self, service_class, broker):
        self.protocols = []
        self.service = service_class
        self.broker = broker

    def buildProtocol(self, address):
        p = self.protocol()
        p.factory = self
        p.service = self.service(protocol=p, broker=self.broker)
        self.protocols.append(p)
        return p
