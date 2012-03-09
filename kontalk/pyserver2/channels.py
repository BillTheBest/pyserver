# -*- coding: utf-8 -*-
'''Message Broker channels.'''
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


import time
from kontalklib import token
import kontalk.config as config
import kontalklib.c2s_pb2 as c2s

import broker


class C2SChannel:
    '''Client channel implementation.'''

    userid = None

    def __init__(self, protocol, broker):
        self.protocol = protocol
        self.broker = broker

    def connected(self):
        # TODO
        print "connected!"

    def disconnected(self):
        print "disconnected."
        if self.userid:
            self.broker.unregister_user_consumer(self.userid)

    def authenticate(self, tx_id, auth_token):
        '''Client tried to authenticate.'''
        print "[%s] authenticating token: %s" % (tx_id, auth_token)
        userid = token.verify_user_token(auth_token, self.broker.db.servers(), config.config['server']['fingerprint'])
        if userid:
            print "[%s] user %s logged in." % (tx_id, userid)
            self.userid = userid
            self.broker.register_user_consumer(userid, self._incoming)
            return True

        return False

    def post_message(self, tx_id, recipient = None, mime = None, flags = None, content = None):
        '''User posted a message.'''
        print "[%s] posting message for: %s (mime=%s, flags=%s)" % \
            (tx_id, str(recipient), mime, str(flags))
        res = {}
        for rcpt in recipient:
            u = str(rcpt)
            res[u] = self.broker.publish_user(self.userid, str(rcpt),
                {
                    'mime' : str(mime),
                    'flags' : flags
                },
                content, broker.MSG_ACK_BOUNCE)
        return res

    def ack_message(self, tx_id, messages):
        '''User acknowledged one or more messages.'''
        return self.broker.ack_user(self.userid, messages)

    def _incoming(self, data, unused = None):
        '''Internal queue worker.'''
        # TODO check for missing keys
        print "incoming message:", data
        a = c2s.NewMessage()
        a.message_id = data['messageid']
        if 'original_id' in data:
            a.original_id = data['originalid']
        # TODO format timestamp :D
        a.timestamp = time.strftime('%Y-%m-%d %H:%M:%S %z', time.localtime(data['timestamp']))
        a.sender = data['sender']
        a.mime = data['headers']['mime']
        a.flags.extend(data['headers']['flags'])
        a.content = data['payload']
        self.protocol.sendBox(a)


class S2SChannel:
    '''Server channel implementation.'''
    # TODO
    # TODO
    # TODO

    fingerprint = None

    def __init__(self, protocol, broker):
        self.protocol = protocol
        self.broker = broker

    def connected(self):
        # TODO
        print "connected!"

    def disconnected(self):
        print "disconnected."
        if self.fingerprint:
            self.broker.unregister_server_queue(self.fingerprint)

    """
    TODO
    def handshake(self, tx_id, auth_token):
        print "authenticating token: %s" % auth_token
        userid = token.verify_user_token(auth_token, self.broker.db.servers(), config.config['server']['fingerprint'])
        if userid:
            print "user %s logged in." % userid
            self.userid = userid
            self.broker.register_user_queue(userid, self._incoming)
            return True

        return False
    """

    def _incoming(self, data):
        # TODO
        print "incoming message:", data
