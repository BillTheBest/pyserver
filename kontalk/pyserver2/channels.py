# -*- coding: utf-8 -*-
'''Message Broker channels.'''
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


import os, time

from twisted.internet import defer

import kontalklib.logging as log
from kontalklib import token, database, utils
import kontalklib.c2s_pb2 as c2s
import kontalklib.s2s_pb2 as s2s

import version, broker

def protoservice(func):
    '''Apply this decorator to methods callable by protocol classes.'''
    func.servicemethod = True
    return func

class C2SChannel:
    '''Client channel implementation.'''

    userid = None
    zombie = False
    # default protocol is legacy
    client_protocol = version.DEFAULT_CLIENT_PROTOCOL

    def __init__(self, protocol, broker, config):
        self.protocol = protocol
        self.broker = broker
        self.config = config

    @protoservice
    def connected(self):
        addr = self.protocol.transport.getPeer()
        log.debug("new client connection from %s" % addr.host)
        return self.serverinfo()

    @protoservice
    def disconnected(self):
        if self.userid:
            addr = self.protocol.transport.getPeer()
            log.debug("user %s (%s) disconnected." % (self.userid, addr.host))
            if not self.zombie:
                self.broker.unregister_user_consumer(self.userid)
        else:
            log.debug("disconnected.")

    @protoservice
    def is_logged(self):
        return self.userid != None

    @protoservice
    def login(self, tx_id, auth_token, client_protocol = None, client_version = None, flags = 0):
        '''Client is trying to login.'''
        # check protocol version
        if client_protocol < version.CLIENT_PROTOCOL:
            return c2s.LoginResponse.STATUS_PROTOCOL_MISMATCH

        if client_protocol:
            self.client_protocol = client_protocol
        self.flags = flags

        try:
            userid = token.verify_user_token(auth_token, self.broker.keyring, str(self.config['server']['fingerprint']))
        except:
            import traceback
            traceback.print_exc()
            log.debug("[%s] token verification failed: %s" % (tx_id, auth_token))
            userid = None

        if userid:
            log.debug("[%s] user %s logged in." % (tx_id, userid))
            self.userid = userid
            # TODO consider flags
            self.broker.register_user_consumer(userid, self)
            return c2s.LoginResponse.STATUS_LOGGED_IN

        return c2s.LoginResponse.STATUS_AUTH_FAILED

    @protoservice
    def authenticate(self, tx_id, auth_token):
        '''Client tried to authenticate.'''
        log.debug("[%s] deprecated authentication mode" % (tx_id, ))
        try:
            userid = token.verify_user_token(auth_token, self.broker.keyring, str(self.config['server']['fingerprint']))
        except:
            import traceback
            traceback.print_exc()
            log.debug("[%s] token verification failed: %s" % (tx_id, auth_token))
            userid = None

        if userid:
            log.debug("[%s] user %s logged in." % (tx_id, userid))
            self.userid = userid
            self.broker.register_user_consumer(userid, self)
            return True

        return False

    @protoservice
    def serverinfo(self, tx_id = None, client_version = None, client_protocol = None):
        info = {
            'version' : '%s %s' % (version.PACKAGE, version.VERSION),
            'client-protocol' : version.CLIENT_PROTOCOL,
            'server-protocol' : version.SERVER_PROTOCOL,
            'fingerprint' : self.config['server']['fingerprint'],
            'network' : self.config['server']['network'],
            'supports' : []
        }

        if 'registration' in self.config:
            info['supports'].append('auth_token')

        # TODO supports should be modular
        # support for Google Cloud Messaging push notification service
        try:
            if self.config['server']['supports.google_gcm']:
                email = self.config['google_gcm']['projectid']
                info['supports'].append('google_gcm=' + email)
        except:
            pass

        return info

    @protoservice
    def post_message(self, tx_id, recipient = None, mime = None, flags = None, content = None):
        '''User posted a message.'''
        #log.debug("[%s] posting message for: %s (mime=%s, flags=%s)" % (tx_id, str(recipient), mime, str(flags)))

        # are we sending an attachment message?
        attachment = 'attachment' in flags
        if attachment and mime in self.config['fileserver']['accept_content']:
            fileid = str(content)
            # TODO check for errors
            (filename, _mime, _md5sum) = self.broker.storage.get_extra(fileid, '')
            # update userids
            self.broker.storage.update_extra_storage(fileid, recipient)
            # TODO risking thumbnail larger than the max allowed size
            content = utils.generate_preview_content(filename, mime)
        else:
            filename = None

        res = {}
        for rcpt in recipient:
            u = str(rcpt)
            length = len(content)
            mime_supported = mime in self.config['fileserver']['accept_content'] \
                if attachment else mime in self.config['broker']['accept_content']
            if not mime_supported:
                log.debug("[%s] mime type not supported: %s - dropping" % \
                    (tx_id, mime))
                res[u] = c2s.MessagePostResponse.MessageSent.STATUS_NOTSUPPORTED
            elif length > self.config['broker']['max_size']:
                log.debug("[%s] message too big (%d bytes) - dropping" % \
                    (tx_id, length))
                res[u] = c2s.MessagePostResponse.MessageSent.STATUS_BIG
            else:
                misc = {
                    'mime' : mime,
                    'flags' : flags
                }
                if filename:
                    misc['filename'] = fileid

                res[u] = self.broker.publish_user(self.userid, u, misc, content, broker.MSG_ACK_BOUNCE)

        return res

    @protoservice
    def ack_message(self, tx_id, messages):
        '''User acknowledged one or more messages.'''
        return self.broker.ack_user(self.userid, messages)

    @protoservice
    def lookup_users(self, tx_id, users):
        # setup a deferred to return
        d = defer.Deferred()
        start = time.time()

        def _stat_found(found, deferred = True):
            end = time.time()
            log.debug("lookup of %d users took %.2f seconds (found %d users)" % (len(users), end-start, len(found)))

            ret = {}
            for stat in found:
                userid, resource = utils.split_userid(stat['userid'])

                #log.debug("LOOKUP/%s" % (stat,))
                # check if user is online here
                if self.broker.user_online(stat['userid']):
                    if userid not in ret:
                        ret[userid] = {'userid' : userid}
                    ret[userid]['timediff'] = 0
                    if 'status' in stat and stat['status']:
                        ret[userid]['status'] = stat['status']
                    # user is online: remove timestamp
                    try:
                        del ret[userid]['timestamp']
                    except:
                        pass
                else:
                    # consider updating timestamp if user is not online here
                    if 'timestamp' in stat and stat['timestamp'] and (userid not in ret or 'timestamp' in ret[userid]):
                        if userid not in ret:
                            ret[userid] = {'userid' : userid}

                        ts = long(stat['timestamp'])
                        # update timestamp only if newer
                        #log.debug("TSDIFF %s old=%d new=%d" % (userid, ret[userid]['timestamp'] if 'timestamp' in ret[userid] else -1, ts))
                        if 'timestamp' not in ret[userid] or ret[userid]['timestamp'] < ts:
                            ret[userid]['timestamp'] = ts
                            ret[userid]['timediff'] = long(time.time()-ts)

                        if 'status' in stat and stat['status']:
                            ret[userid]['status'] = stat['status']

            log.debug("RESULT/%s" % (ret,))
            ret = ret.values()
            if deferred:
                d.callback(ret)
            else:
                return ret

        dstat = self.broker.lookup_users(users)
        if isinstance(dstat, defer.Deferred):
            dstat.addCallback(_stat_found)
            return d
        else:
            return _stat_found(dstat, False)

    @protoservice
    def user_update(self, flags = None, status_msg = None, google_regid = None):
        fields = {}
        if status_msg != None:
            # status message too long
            if len(status_msg) > utils.STATUS_MESSAGE_MAX_LENGTH:
                return c2s.UserInfoUpdateResponse.STATUS_BIG
            fields['status'] = status_msg if len(status_msg.strip()) > 0 else None

        if google_regid != None:
            google_regid = google_regid.strip()
            fields['google_registrationid'] = google_regid if len(google_regid) > 0 else None

        try:
            self.broker.usercache.set_user_data(self.userid, fields)
            if 'status' in fields:
                self.broker.broadcast_presence(self.userid, c2s.UserPresence.EVENT_STATUS_CHANGED, fields['status'])
            return c2s.UserInfoUpdateResponse.STATUS_SUCCESS
        except:
            import traceback
            traceback.print_exc()
            return c2s.UserInfoUpdateResponse.STATUS_ERROR

    @protoservice
    def user_presence_subscribe(self, userid, events):
        return self.broker.subscribe_user_presence(self.userid, userid, events)

    @protoservice
    def validate_user(self, tx_id, code):
        if not code or len(code) != utils.VALIDATION_CODE_LENGTH:
            return c2s.ValidationResponse.STATUS_FAILED, None

        # lookup the verification code
        valdb = database.validations(self.broker.db)

        userid = valdb.get_userid(code)
        if userid:
            # damn unicode!
            userid = str(userid)

            # delete verification entry in validations table
            valdb.delete(code)
            # touch user so we get a first presence
            self.broker.usercache.touch_user(userid)

            # here is your token
            log.debug("[%s] generating token for %s" % (tx_id, userid))
            str_token = token.user_token(userid,
                str(self.config['server']['fingerprint']))
            return c2s.ValidationResponse.STATUS_SUCCESS, str_token

        else:
            return c2s.ValidationResponse.STATUS_FAILED, None

    @protoservice
    def register_user(self, tx_id, username):
        # hiding username for privacy reasons
        log.debug("[%s] registering user via %s" % (tx_id, self.config['registration']['type']))
        if self.config['registration']['type'] == 'sms':
            res = self._register_sms(username)
            d = { 'status' : res }
            if res == c2s.RegistrationResponse.STATUS_CONTINUE:
                    d['sms_from'] = self.config['registration']['from']
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
        # TODO do not use directly - let the storage module do it
        valdb = database.validations(self.broker.db)
        userid = utils.sha1(phone) + utils.rand_str(8, utils.CHARSBOX_AZN_UPPERCASE)
        ret = valdb.update(userid)
        if ret[0] > 0:
            # send SMS
            code = ret[1]
            sms_from = self.config['registration']['from']

            if self.config['registration']['android_emu']:
                # android emulation
                import os
                os.system('adb emu sms send %s %s' % (sms_from, code))
            else:
                # send sms
                from nexmomessage import NexmoMessage
                msg = {
                    'reqtype' : 'json',
                    'username' : self.config['registration']['nx.username'],
                    'password': self.config['registration']['nx.password'],
                    'from': sms_from,
                    'to': phone
                }
                sms = NexmoMessage(msg)
                # FIXME send just the code for now
                sms.set_text_info(code)
                js = sms.send_request()
                log.debug("sms sent [response=%s]" % js)

            return c2s.RegistrationResponse.STATUS_CONTINUE
        else:
            return c2s.RegistrationResponse.STATUS_ERROR

    @protoservice
    def revalidate(self):
        valdb = database.validations(self.broker.db)
        userid = self.userid[:utils.USERID_LENGTH] + utils.rand_str(8, utils.CHARSBOX_AZN_UPPERCASE)
        log.debug("revalidating user %s as %s" % (self.userid, userid))
        ret = valdb.update(userid)
        if ret[0] > 0:
            return ret[1]
        else:
            return False

    def _incoming_box(self, data):
        # TODO check for missing keys
        # TODO avoid using c2s directly; instead create a method in C2SServerProtocol
        a = c2s.NewMessage()
        a.message_id = data['messageid']
        if 'originalid' in data:
            a.original_id = data['originalid']
        a.timestamp = data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
        a.sender = data['sender']
        a.mime = data['headers']['mime']
        a.flags.extend(data['headers']['flags'])
        a.content = data['payload']
        a.need_ack = (data['need_ack'] != broker.MSG_ACK_NONE)
        if 'filename' in data['headers']:
            a.url = self.config['fileserver']['download_url'] % data['headers']['filename']
            try:
                (filename, _mime, _md5sum) = self.broker.storage.get_extra(data['headers']['filename'], self.userid)
                a.length = os.path.getsize(filename)
            except:
                log.warn("attachment not found, unable to send length out")
        return a

    @protoservice
    def incoming(self, data, unused = None):
        '''Internal queue worker.'''
        #log.debug("incoming message: %s" % data)
        a = self._incoming_box(data)
        return self.protocol.sendBox(a)

    @protoservice
    def conflict(self):
        '''Called on resource conflict.'''
        log.debug("resource conflict for %s" % self.userid)
        # the zombie flag prevents the disconnected() method to unregister from the broker
        # since any descriptor will be replaced by the new client connection
        self.zombie = True
        self.protocol.transport.loseConnection()

    @protoservice
    def idle(self):
        # too much verbose -- log.debug("idle connection, sending ping to %s" % self.userid)
        pass

    @protoservice
    def ping_timeout(self):
        '''Called on ping timeout.'''
        log.debug("ping timeout for %s" % self.userid)
        self.protocol.transport.loseConnection()

    @protoservice
    def get_client_protocol(self):
        return self.client_protocol


class S2SRequestChannel:
    def __init__(self, protocol, broker):
        self.protocol = protocol
        self.broker = broker
        self.protocol.service = self
        self.protocol.keyring = broker.keyring
        self.protocol.fingerprint = str(self.broker.config['server']['fingerprint'])

    def broadcast(self, box, tx_id = None):
        # TODO handle shutdown: self.protocol.trasport is null!!
        jobs = []
        for fp in self.broker.keyring:
            # do not send to local server
            if self.protocol.fingerprint != fp:
                tx_id, d = self.protocol.sendBox(fp, box, tx_id)
                log.debug("sent broadcast to %s (%s)" % (fp, tx_id))
                jobs.append(d)
        return defer.gatherResults(jobs)

    def lookup_broadcast(self, users):
        r = s2s.UserLookupRequest()
        r.user_id.extend(users)
        return self.broadcast(r)

    @protoservice
    def user_presence(self, fingerprint, userid, event, status = None):
        # TODO
        log.debug("user %s event %d (status=%s)" % (userid, event, status))

    @protoservice
    def lookup_users(self, fingerprint, users):
        '''Lookup users connected locally.'''
        log.debug("request lookup from %s for %s" % (fingerprint, users))
        ret = []
        for u in users:
            nstat = {'userid' : u}
            stat = self.broker.usercache.get_user_data(u)
            if stat:
                if stat['status']:
                    nstat['status'] = stat['status']

            if not self.broker.user_online(u) and stat:
                nstat['timestamp'] = stat['timestamp']

            ret.append(nstat)
        log.debug("lookup will return %s" % (ret, ))
        return ret


class S2SMessageChannel:
    '''Server channel for message sending implementation.'''
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
        userid = token.verify_user_token(auth_token, self.broker.db.servers(), self.config['server']['fingerprint'])
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
