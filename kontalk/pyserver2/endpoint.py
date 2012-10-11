# -*- coding: utf-8 -*-
'''Broker HTTP endpoint.'''
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


import kontalklib.logging as log
import os, time
import json, base64

from zope.interface import implements

from twisted.web import server, resource, static
from twisted.internet import defer, reactor
from twisted.application import internet, service
from twisted.cred.portal import IRealm, Portal
from twisted.web.guard import HTTPAuthSessionWrapper

from kontalklib import database, token, utils
import broker, version, storage


def post(func):
    '''Apply this decorator to HTTP POST methods.'''
    func.httpmethod = 'POST'
    return func


class JSONResource(resource.Resource):
    '''A Resource that outputs data in JSON format.'''

    def render_JSON(self, request, data):
        if data != server.NOT_DONE_YET:
            if data:
                request.setHeader('content-type', 'application/json')
                return json.dumps(data)
            else:
                request.setHeader('content-type', 'text/plain')
                return utils.no_content(request)

        # return raw output
        request.setHeader('content-type', 'application/octet-stream')
        return data


class BaseRequest(resource.Resource):
    def __init__(self, endpoint, method):
        resource.Resource.__init__(self)
        self.endpoint = endpoint
        self.method = method

    def post_method(self):
        return 'httpmethod' in dir(self.method) and self.method.httpmethod == 'POST'

    def _render(self, request, data = None):
        request.setHeader('content-type', 'application/json')
        if data != None:
            output = self.method(request, data)
        else:
            output = self.method(request)

        if output != server.NOT_DONE_YET:
            if output:
                return json.dumps(output)
            else:
                return utils.no_content(request)

        # return raw output
        return output

    def render_GET(self, request):
        if self.post_method():
            #log.debug("POST only method - dropping request")
            return utils.bad_request(request)
        return self._render(request)

    def render_POST(self, request):
        if not self.post_method():
            #log.debug("GET only method - dropping request")
            return utils.bad_request(request)

        try:
            data = json.load(request.content)
            return self._render(request, data)
        except:
            import traceback
            log.error("error: %s" % (traceback.format_exc(), ))
            return utils.bad_request(request)


class EndpointChannel(JSONResource):
    '''HTTP endpoint channel.'''

    def __init__(self, endpoint, sid, userid):
        resource.Resource.__init__(self)
        self.endpoint = endpoint
        self.broker = self.endpoint.broker
        self.sessionid = sid
        self.userid = userid
        self.queue = defer.DeferredQueue()
        self.zombie = False
        self.pollingDefer = None
        self.putChild('logout', BaseRequest(self, self.logout))
        self.putChild('pending', BaseRequest(self, self.pending))
        self.putChild('polling', BaseRequest(self, self.polling))
        self.putChild('received', BaseRequest(self, self.received))
        self.putChild('message', BaseRequest(self, self.message))

    def render_GET(self, request):
        #log.debug("request from %s: %s" % (self.userid, request.args))
        return utils.bad_request(request)

    def render_json(self, request, data, finish = True):
        if data:
            data = json.dumps(data)
        else:
            return utils.no_content(request)
        request.write(data)
        if finish:
            request.finish()

    def conflict(self):
        '''Called on resource conflict.'''
        log.debug("resource conflict for %s" % self.userid)
        self.zombie = True
        self.endpoint.destroy(self.sessionid)

    def get_client_protocol(self):
        return version.CLIENT_PROTOCOL

    def incoming(self, data):
        '''Internal queue worker.'''
        self.queue.put(data)

    def _format_msg(self, msg):
        msg['content'] = base64.b64encode(msg['payload'])
        msg['need_ack'] = (msg['need_ack'] != broker.MSG_ACK_NONE)
        msg['mime'] = msg['headers']['mime']
        msg['flags'] = msg['headers']['flags']
        msg['timestamp'] = long(time.mktime(msg['timestamp'].timetuple()))

        if 'filename' in msg['headers']:
            msg['url'] = self.broker.config['fileserver']['download_url'] % msg['headers']['filename']
            try:
                (filename, _mime, _md5sum) = self.broker.storage.get_extra(msg['headers']['filename'], self.userid)
                a.length = os.path.getsize(filename)
            except:
                log.warn("attachment not found, unable to send length out")
            del msg['filename']

        # clean private data
        del msg['payload']
        del msg['need_ack']
        del msg['headers']
        return msg

    def _push(self, data, request):
        if type(data) == list:
            output = [self._format_msg(x) for x in data]
        else:
            output = (self._format_msg(data), )
        self.render_json(request, output)

    def _response_error(self, err, call, timeout):
        log.error("response error: %s" % (err, ))
        call.cancel()
        timeout.cancel()

    def _error(self, err, req):
        if err.type != defer.CancelledError:
            import traceback
            log.error("error: %s" % (traceback.format_exc(), ))

    def _polling_timeout(self, request, callback):
        try:
            # WARNING Lighttpd ModProxyCore will not finish the request
            utils.no_content(request)
            request.finish()
        except:
            import traceback
            log.error("error: %s" % (traceback.format_exc(), ))


    ## Web methods ##

    def pending(self, request):
        '''Requeues pending incoming messages to be retrieved by polling.'''
        self.broker.pending_messages(self.userid, True)

    def polling(self, request):
        '''Polling for incoming messages.'''
        if self.pollingDefer:
            self.pollingDefer.cancel()

        self.pollingDefer = self.queue.get()
        self.pollingDefer.addCallback(self._push, request)
        self.pollingDefer.addErrback(self._error, request)
        # TODO timeout value
        timeout = reactor.callLater(30, self._polling_timeout, request, self.pollingDefer)
        request.notifyFinish().addErrback(self._response_error, self.pollingDefer, timeout)
        return server.NOT_DONE_YET

    @post
    def received(self, request, data):
        '''Ack messages.'''
        return self.broker.ack_user(self.userid, [str(x) for x in data])

    @post
    def message(self, request, data):
        '''Send a message.'''
        log.debug("sending message: %s" % (data, ))

        # TODO check for missing keys
        content = data['content']
        mime = data['mime']

        # TODO attachments & flags
        attachment = False
        filename = None
        flags = []

        res = {}
        for rcpt in data['to']:
            u = str(rcpt)
            length = len(content)
            mime_supported = mime in self.broker.config['fileserver']['accept_content'] \
                if attachment else mime in self.broker.config['broker']['accept_content']
            if not mime_supported:
                log.debug("[%s] mime type not supported: %s - dropping" % \
                    (tx_id, mime))
                res[u] = c2s.MessagePostResponse.MessageSent.STATUS_NOTSUPPORTED
            elif length > self.broker.config['broker']['max_size']:
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

        log.debug("message sent! %s" % (res, ))
        return res


    def logout(self, request):
        log.debug("user %s logged out." % (self.userid))
        if not self.zombie:
            self.broker.unregister_user_consumer(self.userid)
        # destroy session
        self.endpoint.destroy(self.sessionid)


class Endpoint(resource.Resource):
    '''HTTP endpoint connection manager.'''

    # TODO write something more suitable :)
    intro = 'Kontalk HTTP service running.'

    def __init__(self, config, broker):
        resource.Resource.__init__(self)
        self.broker = broker
        self.channels = {}

        self.putChild('', static.Data(self.intro, 'text/plain'))
        self.putChild('validate', BaseRequest(self, self.validate))
        self.putChild('login', BaseRequest(self, self.login))

    def getChild(self, path, request):
        try:
            return self.children[path]
        except KeyError:
            # no child found, assume channel id
            try:
                return self.channels[path]
            except KeyError:
                return resource.NoResource()

    ## Web methods ##

    def validate(self, request):
        '''Check a validation code and generates a user token to login with.'''
        code = request.args['c'][0]
        if not code or len(code) != utils.VALIDATION_CODE_LENGTH:
            return utils.bad_request(request)

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
            log.debug("generating token for %s" % (userid, ))
            str_token = token.user_token(userid,
                str(self.broker.config['server']['fingerprint']))
            return {'auth': str_token, 'userid': userid }

        else:
            return utils.not_found(request)


    @post
    def login(self, request, data):
        '''Create a channel for the requested userid.'''
        try:
            auth = data['auth']
            userid = token.verify_user_token(auth, self.broker.keyring, self.broker.fingerprint)
        except:
            import traceback
            traceback.print_exc()
            log.debug("token verification failed!")
            return utils.unauthorized(request)

        sid = utils.rand_str(40, utils.CHARSBOX_AZN_LOWERCASE)
        ch = EndpointChannel(self, sid, userid)
        self.broker.register_user_consumer(userid, ch, supports_mailbox=True, pending=False)
        log.debug("user %s logged in." % (userid, ))

        self.channels[sid] = ch
        return { 'id' : sid }

    def destroy(self, sid):
        '''Destroy a channel assigned to a sessionid.'''
        if sid in self.channels:
            del self.channels[sid]


class EndpointService(resource.Resource, service.Service):
    '''HTTP endpoint Twisted service.'''

    def __init__(self, application, config, broker):
        resource.Resource.__init__(self)
        self.setServiceParent(application)
        self.config = config
        self.broker = broker

    def startService(self):
        service.Service.startService(self)
        log.debug("HTTP endpoint init")
        self.storage = self.broker.storage

        # create http service
        factory = server.Site(Endpoint(self.config, self.broker))
        fs_service = internet.TCPServer(port=self.config['server']['endpoint.bind'][1],
            factory=factory, interface=self.config['server']['endpoint.bind'][0])
        fs_service.setServiceParent(self.parent)
