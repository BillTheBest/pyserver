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
from twisted.internet.task import LoopingCall
from twisted.internet import reactor

import time
from kontalklib import txprotobuf

import kontalk.config as config
import kontalklib.c2s_pb2 as c2s
import kontalklib.s2s_pb2 as s2s

# in 30 seconds clients will be kicked out if they don't respond

# how many seconds to wait for next idle signal
IDLE_DELAY = 15
# how many seconds to wait for ping response
PING_DELAY = 15


class InternalServerProtocol(txprotobuf.Protocol):

    def connectionMade(self):
        self.service.connected()

    def connectionLost(self, reason=connectionDone):
        self.service.disconnected()


class S2SServerProtocol(InternalServerProtocol):

    def __init__(self):
        txprotobuf.Protocol.__init__(self, s2s)
        self.MAX_LENGTH = config.config['server']['s2s.pack_size_max']

    def boxReceived(self, data, tx_id = None):
        # TODO
        pass


class C2SServerProtocol(InternalServerProtocol):
    pinger = None
    ping_txid = None

    def __init__(self):
        txprotobuf.Protocol.__init__(self, c2s)
        self.MAX_LENGTH = config.config['server']['c2s.pack_size_max']
        self.idler = LoopingCall(self.onIdle)
        if 'reset' not in dir(self.idler):
            def reset(self):
                try:
                    self.idler.stop()
                except:
                    pass
                try:
                    self.idler.start(IDLE_DELAY, False)
                except:
                    pass
            self.idler.reset = reset

    def connectionMade(self):
        InternalServerProtocol.connectionMade(self)
        # start idler
        self.idler.start(IDLE_DELAY, False)

    def connectionLost(self, reason=connectionDone):
        try:
            # stop idler
            self.idler.stop()
        except:
            pass
        InternalServerProtocol.connectionLost(self, reason)

    def onIdle(self):
        self.service.idle()
        # send ping
        a = c2s.Ping()
        a.timestamp = long(time.time())
        self.ping_txid = self.sendBox(a)
        # ping is sent, wait for response
        if not self.pinger:
            self.pinger = reactor.callLater(PING_DELAY, self.pingTimeout)

    def pingTimeout(self):
        try:
            self.idler.stop()
        except:
            pass
        self.service.ping_timeout()

    def boxReceived(self, data, tx_id = None):
        # reset idler
        try:
            self.idler.reset()
        except:
            pass

        # optional reply
        r = None
        name = data.__class__.__name__
        if name == 'AuthenticateRequest':
            r = c2s.AuthenticateResponse()
            r.valid = self.service.authenticate(str(tx_id), data.token)

        elif name == 'MessagePostRequest':
            if self.service.is_logged():
                r = c2s.MessagePostResponse()
                if len(data.recipient) > 0:
                    res = self.service.post_message(str(tx_id),
                        tuple(data.recipient),
                        str(data.mime),
                        tuple(data.flags),
                        data.content)
                    for userid, msgid in res.iteritems():
                        me = r.entry.add()
                        me.user_id = userid
                        if type(msgid) == str:
                            me.status = c2s.MessagePostResponse.MessageSent.STATUS_SUCCESS
                            me.message_id = msgid
                        elif msgid:
                            me.status = msgid
                        else:
                            me.status = c2s.MessagePostResponse.MessageSent.STATUS_ERROR

        elif name == 'MessageAckRequest':
            if self.service.is_logged():
                r = c2s.MessageAckResponse()
                res = self.service.ack_message(str(tx_id), tuple(data.message_id))
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
                res = self.service.register_user(str(tx_id), str(data.username))
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
                res, token = self.service.validate_user(str(tx_id), str(data.validation_code))
                r.status = res
                if token:
                    r.token = token

        elif name == 'UserLookupRequest':
            if self.service.is_logged():
                r = c2s.UserLookupResponse()
                found = self.service.lookup_users(str(tx_id), tuple(data.user_id))
                for u in found:
                    e = r.entry.add()
                    e.user_id = u['userid']
                    if 'status' in u:
                        e.status = u['status']
                    if 'timestamp' in u:
                        e.timestamp = u['timestamp']
                    if 'timediff' in u:
                        e.timediff = u['timediff']

        elif name == 'ServerInfoRequest':
            r = c2s.ServerInfoResponse()
            info = self.service.serverinfo(str(tx_id), str(data.client_version), data.client_protocol)
            r.version = info['version']
            r.client_protocol = info['client-protocol']
            r.server_protocol = info['server-protocol']
            r.fingerprint = info['fingerprint']
            r.supports.extend(info['supports'])

        elif name == 'UserInfoUpdateRequest':
            if self.service.is_logged():
                r = c2s.UserInfoUpdateResponse()
                if data.HasField('status_message'):
                    status_msg = str(data.status_message)
                else:
                    status_msg = None
                if data.HasField('google_registration_id'):
                    google_regid = str(data.google_registration_id)
                else:
                    google_regid = None

                r.status = self.service.user_update(status_msg, google_regid)

        elif name == 'UserPresenceSubscribeRequest':
            if self.service.is_logged():
                r = c2s.UserPresenceSubscribeResponse()
                r.status = self.service.user_presence_subscribe(str(data.user_id), data.events)

        elif name == 'Pong':
            # client has responded: check tx_id
            if self.ping_txid == tx_id:
                # reset ping timeout check
                try:
                    self.pinger.cancel()
                except:
                    pass

        if r:
            self.sendBox(r, tx_id)

        # reset idler (again)
        try:
            self.idler.reset()
        except:
            pass


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
