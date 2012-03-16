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

import kontalklib.c2s_pb2 as c2s
import kontalklib.s2s_pb2 as s2s


class InternalServerProtocol(txprotobuf.Protocol):

    def connectionMade(self):
        self.service.connected()

    def connectionLost(self, reason=connectionDone):
        self.service.disconnected()


class S2SServerProtocol(InternalServerProtocol):

    def __init__(self):
        txprotobuf.Protocol.__init__(self, s2s)

    def boxReceived(self, data, tx_id = None):
        # TODO
        pass


class C2SServerProtocol(InternalServerProtocol):
    # max length: 200 KB
    MAX_LENGTH = 204800

    def __init__(self):
        txprotobuf.Protocol.__init__(self, c2s)

    def boxReceived(self, data, tx_id = None):
        # optional reply
        r = None
        name = data.__class__.__name__
        if name == 'AuthenticateRequest':
            r = c2s.AuthenticateResponse()
            r.valid = self.service.authenticate(tx_id, data.token)

        elif name == 'MessagePostRequest':
            if self.service.is_logged():
                r = c2s.MessagePostResponse()
                if len(data.recipient) > 0:
                    res = self.service.post_message(tx_id,
                        tuple(data.recipient),
                        data.mime,
                        tuple(data.flags),
                        data.content)
                    for userid, msgid in res.iteritems():
                        me = r.entry.add()
                        me.user_id = userid
                        if msgid:
                            me.status = c2s.MessagePostResponse.MessageSent.STATUS_SUCCESS
                            me.message_id = msgid
                        else:
                            me.status = c2s.MessagePostResponse.MessageSent.STATUS_ERROR

        elif name == 'MessageAckRequest':
            if self.service.is_logged():
                r = c2s.MessageAckResponse()
                res = self.service.ack_message(tx_id, tuple(data.message_id))
                for _msgid in data.message_id:
                    msgid = str(_msgid)
                    e = r.entry.add()
                    e.message_id = msgid
                    try:
                        success = res[msgid]
                        if success:
                            e.status = c2s.MessageAckResponse.Entry.STATUS_SUCCESS
                        else:
                            e.status = c2s.MessageAckResponse.Entry.STATUS_NOTFOUND
                    except:
                        import traceback
                        traceback.print_exc()
                        e.status = c2s.MessageAckResponse.Entry.STATUS_ERROR

        elif name == 'RegistrationRequest':
            if not self.service.is_logged():
                r = c2s.RegistrationResponse()
                res = self.service.register_user(tx_id, str(data.username))
                r.status = res['status']
                if 'token' in res:
                    r.token = res['token']
                if 'sms_from' in res:
                    r.sms_from = res['sms_from']
                if 'email_from' in res:
                    r.email_from = res['email_from']

        elif name == 'ValidationRequest':
            if not self.service.is_logged():
                r = c2s.ValidationResponse()
                res, token = self.service.validate_user(tx_id, str(data.validation_code))
                r.status = res
                if token:
                    r.token = token

        elif name == 'UserLookupRequest':
            if self.service.is_logged():
                r = c2s.UserLookupResponse()
                found = self.service.lookup_users(tx_id, tuple(data.user_id))
                for u in found:
                    e = r.entry.add()
                    e.user_id = u['userid']
                    if 'status' in u:
                        e.status = u['status']
                    if 'timestamp' in u:
                        e.timestamp = u['timestamp']

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
