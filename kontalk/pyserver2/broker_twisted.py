# -*- coding: utf-8 -*-
'''Twisted-related broker code.'''
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


from twisted.internet.protocol import ServerFactory, connectionDone
from twisted.internet.task import LoopingCall
from twisted.internet import reactor, protocol, defer, error

import time
from kontalklib import txprotobuf, utils

import kontalklib.c2s_pb2 as c2s
import kontalklib.s2s_pb2 as s2s

# in 30 seconds clients will be kicked out if they don't respond

# how many seconds to wait for next idle signal
IDLE_DELAY = 15
# how many seconds to wait for ping response
PING_DELAY = 15


class InternalServerProtocol(txprotobuf.Protocol):

    def connectionMade(self):
        return self.service.connected()

    def connectionLost(self, reason=connectionDone):
        return self.service.disconnected()


class S2SMessageServerProtocol(InternalServerProtocol):

    def __init__(self, config):
        txprotobuf.Protocol.__init__(self, s2s)
        self.MAX_LENGTH = config['server']['s2s.pack_size_max']

    def boxReceived(self, (host, port), data, tx_id = None):
        # TODO
        pass


class S2SRequestServerProtocol(txprotobuf.DatagramProtocol):
    '''Server-to-server request protocol.'''

    '''Timeout delay.'''
    timeout_delay = 5

    def __init__(self, config):
        txprotobuf.DatagramProtocol.__init__(self, s2s)
        '''Map of packets waiting for a response.'''
        self._tx = {}

    def _timeout(self, user_defer):
        '''Handles a deferred timeout.'''
        if not user_defer.called:
            user_defer.errback(error.TimeoutError('Server did not respond.'))

    def boxReceived(self, fingerprint, tx_id, data):
        # optional reply
        r = None
        name = data.__class__.__name__
        #print "box received from %s (%s)" % (fingerprint, tx_id), data

        fingerprint = str(fingerprint)
        tx_id = str(tx_id)

        # tx is pending response
        if fingerprint in self._tx and tx_id in self._tx[fingerprint]:
            self._tx[fingerprint][tx_id].callback((str(fingerprint), tx_id, data))
            del self._tx[fingerprint][tx_id]

        # process requests anyway

        if name == 'UserPresence':
            self.service.user_presence(fingerprint, str(data.user_id), data.event, data.status_message)

        elif name == 'UserLookupRequest':
            found = self.service.lookup_users(fingerprint, [str(x) for x in data.user_id])
            r = c2s.UserLookupResponse()
            print "FOUND", found
            for u in found:
                e = r.entry.add()
                e.user_id = u['userid']
                if 'status' in u and u['status']:
                    e.status = u['status']
                if 'timestamp' in u:
                    e.timestamp = u['timestamp']
                if 'timediff' in u:
                    e.timediff = u['timediff']

        if r:
            # we don't want a deferred for a response packet
            txprotobuf.DatagramProtocol.sendBox(self, self.keyring.s2s_addr(fingerprint), r, tx_id)

    def sendBox(self, fingerprint, data, tx_id = None):
        tx_id = txprotobuf.DatagramProtocol.sendBox(self, self.keyring.s2s_addr(fingerprint), data, tx_id)
        # store the request
        d = defer.Deferred()
        if fingerprint not in self._tx:
            self._tx[fingerprint] = dict()
        self._tx[fingerprint][tx_id] = d
        reactor.callLater(self.timeout_delay, self._timeout, d)

        return tx_id, d


class C2SServerProtocol(InternalServerProtocol):
    pinger = None
    ping_txid = None

    def __init__(self, config):
        txprotobuf.Protocol.__init__(self, c2s)
        self.MAX_LENGTH = config['server']['c2s.pack_size_max']
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
        """
        TODO this breaks compatibility with Android client < 16
        info = InternalServerProtocol.connectionMade(self)
        # send serverinfo
        r = c2s.ServerInfo()
        r.version = info['version']
        r.client_protocol = info['client-protocol']
        r.fingerprint = info['fingerprint']
        r.network = info['network']
        r.supports.extend(info['supports'])
        self.sendBox(r)
        """
        # start idler
        self.idler.start(IDLE_DELAY, False)

    def connectionLost(self, reason=connectionDone):
        try:
            # stop idler
            self.idler.stop()
        except:
            pass
        try:
            # stop pinger
            self.pinger.stop()
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
        self.pinger = None

    def boxReceived(self, data, tx_id = None):
        # reset idler
        try:
            self.idler.reset()
        except:
            pass

        # optional reply
        r = None
        name = data.__class__.__name__

        if name == 'LoginRequest':
            r = c2s.LoginResponse()
            (r.status, userid) = self.service.login(str(tx_id), data.token, data.client_protocol, data.client_version, data.flags)
            if userid:
                r.user_id = userid

        elif name == 'AuthenticateRequest':
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
                # lookup can delay operations by a long time, so defer it
                def lookup_complete(found, tx_id, return_value = False):
                    r = c2s.UserLookupResponse()
                    for u in found:
                        e = r.entry.add()
                        e.user_id = u['userid']
                        if 'status' in u:
                            e.status = u['status']
                        if 'timestamp' in u:
                            e.timestamp = u['timestamp']
                        if 'timediff' in u:
                            e.timediff = u['timediff']
                    if return_value:
                        return r
                    else:
                        self.sendBox(r, tx_id)

                # force generic users only
                found = self.service.lookup_users(tx_id, [str(x)[:utils.USERID_LENGTH] for x in data.user_id])
                if isinstance(found, defer.Deferred):
                    found.addCallback(lookup_complete, tx_id)
                else:
                    r = lookup_complete(found, tx_id, True)

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
                flags = None
                if data.HasField('flags'):
                    flags = data.flags
                if data.HasField('status_message'):
                    status_msg = data.status_message.encode('utf-8')
                else:
                    status_msg = None
                if data.HasField('google_registration_id'):
                    google_regid = str(data.google_registration_id)
                else:
                    google_regid = None

                r.status = self.service.user_update(flags, status_msg, google_regid)

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
                self.pinger = None

        elif name == 'ValidationCodeRequest':
            if self.service.is_logged():
                code = self.service.revalidate()
                r = c2s.ValidationCodeResponse()
                if type(code) == str:
                    r.status = c2s.ValidationCodeResponse.STATUS_SUCCESS
                    r.code = code
                else:
                    r.status = c2s.ValidationCodeResponse.STATUS_ERROR

        if r:
            self.sendBox(r, tx_id)

        # reset idler (again)
        try:
            self.idler.reset()
        except:
            pass


class InternalServerFactory(ServerFactory):

    def __init__(self, protocol, service_class, broker, config):
        self.protocol = protocol
        self.service = service_class
        self.broker = broker
        self.config = config

    def buildProtocol(self, address):
        p = self.protocol(self.config)
        p.factory = self
        p.service = self.service(protocol=p, broker=self.broker, config=self.config)
        return p
