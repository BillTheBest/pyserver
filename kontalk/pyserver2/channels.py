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
import logging as log

from kontalklib import token, database, utils
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
        addr = self.protocol.transport.getPeer()
        log.debug("new client connection from %s" % addr.host)

    def disconnected(self):
        if self.userid:
            addr = self.protocol.transport.getPeer()
            log.debug("user %s (%s) disconnected." % (self.userid, addr.host))
            self.broker.unregister_user_consumer(self.userid)
        else:
            log.debug("disconnected.")

    def is_logged(self):
        return self.userid != None

    def authenticate(self, tx_id, auth_token):
        '''Client tried to authenticate.'''
        log.debug("[%s] authenticating token: %s" % (tx_id, auth_token))
        try:
            userid = token.verify_user_token(auth_token, database.servers(self.broker.db), config.config['server']['fingerprint'])
        except:
            import traceback
            traceback.print_exc()
            log.debug("[%s] token verification failed!" % (tx_id))
            userid = None

        if userid:
            log.debug("[%s] user %s logged in." % (tx_id, userid))
            self.userid = userid
            self.broker.register_user_consumer(userid, self._incoming)
            return True

        return False

    def post_message(self, tx_id, recipient = None, mime = None, flags = None, content = None):
        '''User posted a message.'''
        log.debug("[%s] posting message for: %s (mime=%s, flags=%s)" % \
            (tx_id, str(recipient), mime, str(flags)))
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

    def validate_user(self, tx_id, code):
        if not code or len(code) != utils.VALIDATION_CODE_LENGTH:
            return c2s.ValidationResponse.STATUS_FAILED, None

        # lookup the verification code
        valdb = database.validations(self.broker.db)

        userid = valdb.get_userid(code)
        if userid:
            # delete verification entry in validations table
            valdb.delete(code)

            # here is your token
            str_token = token.user_token(userid,
                config.config['server']['fingerprint'])
            return c2s.ValidationResponse.STATUS_SUCCESS, str_token

        else:
            return c2s.ValidationResponse.STATUS_FAILED, None

    def register_user(self, tx_id, username):
        log.debug("registering username %s" % username)
        if config.config['registration']['type'] == 'sms':
            res = self._register_sms(username)
            d = { 'status' : res }
            if res == c2s.RegistrationResponse.STATUS_CONTINUE:
                    d['sms_from'] = config.config['registration']['from']
            return d

        else:
            # TODO support for other registration types
            return { 'status' : c2s.RegistrationResponse.STATUS_ERROR }

    def _register_sms(self, n):
        # validate phone number syntax
        if not n or len(n.strip()) == 0:
            log.debug("number empty - %s" % n)
            return c2s.RegistrationResponse.STATUS_INVALID_USERNAME

        phone = phone_num = n.strip()
        # exclude the initial plus to verify the digits
        if (phone[0] == '+'):
            phone_num = phone[1:]

        # not all digits...
        if not phone_num.isdigit():
            log.debug("number is not all-digits - %s" % phone_num)
            return c2s.RegistrationResponse.STATUS_INVALID_USERNAME

        # replace double-zero with plus
        if phone[0:2] == '00':
            phone = '+' + phone[2:]

        # insert validation record
        valdb = database.validations(self.broker.db)
        userid = utils.sha1(phone) + utils.rand_str(8, utils.CHARSBOX_AZN_UPPERCASE)
        ret = valdb.update(userid)
        if ret[0] > 0:
            # send SMS
            code = ret[1]
            sms_from = config.config['registration']['from']

            if config.config['registration']['android_emu']:
                # android emulation
                import os
                os.system('adb emu sms send %s %s' % (sms_from, code))
            else:
                # send sms
                from nexmomessage import NexmoMessage
                msg = {
                    'reqtype' : 'json',
                    'username' : config.config['registration']['nx.username'],
                    'password': config.config['registration']['nx.password'],
                    'from': sms_from,
                    'to': phone
                }
                sms = NexmoMessage(msg)
                # FIXME send just the code for now
                sms.set_text_info(code)
                sms.send_request()

            return c2s.RegistrationResponse.STATUS_CONTINUE
        else:
            return c2s.RegistrationResponse.STATUS_ERROR


    def _incoming(self, data, unused = None):
        '''Internal queue worker.'''
        # TODO check for missing keys
        log.debug("incoming message: %s" % data)
        # TODO avoid using c2s directly; instead create a method in C2SServerProtocol
        a = c2s.NewMessage()
        a.message_id = data['messageid']
        if 'original_id' in data:
            a.original_id = data['originalid']
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
        log.debug("connected!")

    def disconnected(self):
        log.debug("disconnected.")
        if self.fingerprint:
            self.broker.unregister_server_queue(self.fingerprint)

    """
    TODO
    def handshake(self, tx_id, auth_token):
        log.debug("authenticating token: %s" % auth_token)
        userid = token.verify_user_token(auth_token, self.broker.db.servers(), config.config['server']['fingerprint'])
        if userid:
            log.debug("server %s logged in." % userid)
            self.userid = userid
            self.broker.register_user_queue(userid, self._incoming)
            return True

        return False
    """

    def _incoming(self, data):
        # TODO
        log.debug("incoming message:", data)
