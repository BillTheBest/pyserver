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
import json

from zope.interface import implements

from twisted.web import server, resource, static
from twisted.internet import defer
from twisted.application import internet, service
from twisted.cred.portal import IRealm, Portal
from twisted.web.guard import HTTPAuthSessionWrapper

from kontalklib import database, token, utils
import version, storage


def authenticated(func):
    '''Apply this decorator to methods which need login.'''
    func.authmethod = True
    return func

def post(func):
    '''Apply this decorator to for HTTP POST methods.'''
    func.httpmethod = 'POST'
    return func


class BaseRequest(resource.Resource):
    def __init__(self, endpoint, method):
        resource.Resource.__init__(self)
        self.endpoint = endpoint
        self.method = method

    def need_auth(self):
        return 'authmethod' in dir(self.method) and self.method.authmethod

    def post_method(self):
        return 'httpmethod' in dir(self.method) and self.method.httpmethod == 'POST'

    def _render(self, request, data = None):
        if self.need_auth() and not self.endpoint.logged:
            #log.debug("authenticated method - dropping request")
            return self.endpoint.unauthorized(request)

        if data != None:
            output = self.method(request, data)
        else:
            output = self.method(request)

        if output != server.NOT_DONE_YET:
            if output:
                return json.dumps(output)
            else:
                return self.endpoint.no_content(request)

        # return raw output
        return output

    def render_GET(self, request):
        if self.post_method():
            #log.debug("POST only method - dropping request")
            return self.endpoint.bad_request(request)
        return self._render(request)

    def render_POST(self, request):
        if not self.post_method():
            #log.debug("GET only method - dropping request")
            return self.endpoint.bad_request(request)

        try:
            data = json.load(request.content)
            return self._render(request, data)
        except:
            return self.endpoint.bad_request(request)


class Endpoint(resource.Resource):
    '''HTTP endpoint connection manager.'''
    logged = False
    queue = defer.DeferredQueue()

    def __init__(self, broker, userid):
        resource.Resource.__init__(self)
        self.broker = broker
        self.userid = userid
        self.putChild('login', BaseRequest(self, self.login))
        self.putChild('logout', BaseRequest(self, self.logout))
        self.putChild('polling', BaseRequest(self, self.polling))
        self.putChild('received', BaseRequest(self, self.received))

    def finish(self):
        pass

    def _quick_response(self, request, code, text = ''):
        request.setResponseCode(code)
        request.setHeader('content-type', 'text/plain')
        return text

    def bad_request(self, request):
        return self._quick_response(request, 400, 'bad request')

    def not_found(self, request):
        return self._quick_response(request, 404, 'not found')

    def unauthorized(self, request):
        return self._quick_response(request, 401, 'unauthorized')

    def no_content(self, request):
        return self._quick_response(request, 204)

    def render_GET(self, request):
        log.debug("request from %s: %s" % (self.userid, request.args))
        return self.bad_request(request)

    def render_json(self, request, data, finish = True):
        if data:
            data = json.dumps(data)
        else:
            return self.no_content(request)
        request.write(data)
        if finish:
            request.finish()

    def conflict(self):
        '''Called on resource conflict.'''
        log.debug("resource conflict for %s" % self.userid)

    def get_client_protocol(self):
        return version.CLIENT_PROTOCOL

    def incoming(self, data):
        '''Internal queue worker.'''
        # TODO handle notifyFinish()
        # http://twistedmatrix.com/documents/current/web/howto/web-in-60/interrupted.html
        self.queue.put(data)

    def _format_msg(self, msg):
        msg['timestamp'] = long(time.mktime(msg['timestamp'].timetuple()))
        return msg

    def _push(self, data, request):
        log.debug("pushing message: %s" % (data, ))
        # TODO multiple messages
        # TODO format output
        self.render_json(request, (self._format_msg(data), ))

    ## Web methods ##

    @authenticated
    def polling(self, request):
        d = self.queue.get()
        d.addCallback(self._push, request)
        return server.NOT_DONE_YET

    @authenticated
    @post
    def received(self, request, data):
        return self.broker.ack_user(self.userid, [str(x) for x in data])

    @authenticated
    @post
    def message(self, request):
        # TODO
        pass

    def login(self, request):
        log.debug("user %s logged in." % (self.userid))
        # TODO flags
        self.broker.register_user_consumer(self.userid, self)
        self.logged = True

    @authenticated
    def logout(self, request):
        log.debug("user %s logged out." % (self.userid))
        self.broker.unregister_user_consumer(self.userid)
        self.logged = False


class EndpointRealm(object):
    implements(IRealm)

    channels = {}

    def __init__(self, broker):
        self.broker = broker

    def requestAvatar(self, avatarId, mind, *interfaces):
        try:
            return interfaces[0], self.channels[avatarId], self.channels[avatarId].finish
        except KeyError:
            endpoint = Endpoint(self.broker, avatarId)
            self.channels[avatarId] = endpoint
            return interfaces[0], endpoint, endpoint.finish


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
        self.db = self.broker.db

        credFactory = utils.AuthKontalkTokenFactory(str(self.config['server']['fingerprint']), self.broker.keyring)

        # setup endpoint
        portal = Portal(EndpointRealm(self.broker), [utils.AuthKontalkToken()])
        resource = HTTPAuthSessionWrapper(portal, [credFactory])

        # TODO write something more suitable :)
        self.putChild('', static.Data('Kontalk HTTP service running.', 'text/plain'))
        self.putChild('endpoint', resource)

        # create http service
        factory = server.Site(self)
        fs_service = internet.TCPServer(port=self.config['server']['endpoint.bind'][1],
            factory=factory, interface=self.config['server']['endpoint.bind'][0])
        fs_service.setServiceParent(self.parent)
