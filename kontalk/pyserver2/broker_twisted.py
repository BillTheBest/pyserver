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

from twisted.internet.protocol import ServerFactory, connectionDone

from kontalklib import txprotobuf

import kontalklib.c2s_pb2
import kontalklib.s2s_pb2

from kontalklib.c2s_pb2 import *
from kontalklib.s2s_pb2 import *


class InternalServerProtocol(txprotobuf.Protocol):

    def connectionMade(self):
        self.service.connected()

    def connectionLost(self, reason=connectionDone):
        self.service.disconnected()


class S2SServerProtocol(InternalServerProtocol):

    def __init__(self):
        txprotobuf.Protocol.__init__(self, kontalklib.s2s_pb2)

    def boxReceived(self, data, tx_id = None):
        # TODO
        pass


class C2SServerProtocol(InternalServerProtocol):

    def __init__(self):
        txprotobuf.Protocol.__init__(self, kontalklib.c2s_pb2)

    def boxReceived(self, data, tx_id = None):
        #print "box received: " + data.__class__.__name__

        # optional reply
        r = None
        name = data.__class__.__name__
        if name == 'AuthenticateRequest':
            r = AuthenticateResponse()
            r.valid = self.service.authenticate(tx_id, data.token)

        elif name == 'MessagePostRequest':
            r = MessagePostResponse()
            q = self.service.post_message(tx_id,
                tuple(data.recipient),
                data.mime,
                tuple(data.flags),
                data.content)
            if q:
                # TODO
                pass

        if r:
            self.sendBox(r, tx_id)


class InternalServerFactory(ServerFactory):

    def __init__(self, protocol, service_class, broker):
        self.protocol = protocol
        self.protocols = []
        self.service = service_class
        self.broker = broker

    def buildProtocol(self, address):
        p = self.protocol()
        p.factory = self
        p.service = self.service(protocol=p, broker=self.broker)
        self.protocols.append(p)
        return p
