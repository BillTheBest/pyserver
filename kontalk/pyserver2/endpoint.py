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
        self.putChild('logout', BaseRequest(self, self.logout))
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
        call.cancel()
        timeout.cancel()

    def _error(self, err, req):
        if err.type != defer.CancelledError:
            import traceback
            log.error("error: %s" % (traceback.format_exc(), ))

    def _polling_timeout(self, request, callback):
        try:
            # FIXME Lighttpd ModProxyCore will not finish the request
            #utils.no_content(request)
            request.finish()
        except:
            import traceback
            log.error("error: %s" % (traceback.format_exc(), ))


    ## Web methods ##

    def polling(self, request):
        d = self.queue.get()
        d.addCallback(self._push, request)
        d.addErrback(self._error, request)
        # TODO timeout value
        timeout = reactor.callLater(5, self._polling_timeout, request, d)
        request.notifyFinish().addErrback(self._response_error, d, timeout)
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


class EndpointLogin(JSONResource):
    '''HTTP endpoint session request resource.'''

    def __init__(self, endpoint, userid):
        resource.Resource.__init__(self)
        self.endpoint = endpoint
        self.userid = userid

    def render_GET(self, request):
        return self.render_JSON(request, self.endpoint.login(self.userid))

    def finish(self):
        pass


class EndpointLoginRealm(object):
    implements(IRealm)

    def __init__(self, endpoint):
        self.endpoint = endpoint

    def requestAvatar(self, avatarId, mind, *interfaces):
        endpoint = EndpointLogin(self.endpoint, avatarId)
        return interfaces[0], endpoint, endpoint.finish


class Endpoint(resource.Resource):
    '''HTTP endpoint connection manager.'''

    def __init__(self, config, broker):
        resource.Resource.__init__(self)
        self.broker = broker
        self.channels = {}

        # login via http auth
        credFactory = utils.AuthKontalkTokenFactory(str(config['server']['fingerprint']), broker.keyring)
        portal = Portal(EndpointLoginRealm(self), [utils.AuthKontalkToken()])
        child = HTTPAuthSessionWrapper(portal, [credFactory])
        self.putChild('login', child)

        # TODO write something more suitable :)
        self.putChild('', static.Data('Kontalk HTTP service running.', 'text/plain'))

    def getChild(self, path, request):
        try:
            return self.children[path]
        except KeyError:
            # no child found, assume channel id
            try:
                return self.channels[path]
            except KeyError:
                return resource.NoResource()

    def render_GET(self, request):
        # TODO write something more suitable :)
        return utils._quick_response(request, 200, 'Kontalk HTTP service running.')

    def login(self, userid):
        '''Create a channel for the requested userid.'''
        # register user consumer
        sid = utils.rand_str(40, utils.CHARSBOX_AZN_LOWERCASE)
        ch = EndpointChannel(self, sid, userid)
        self.broker.register_user_consumer(userid, ch, supports_mailbox=True)
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
