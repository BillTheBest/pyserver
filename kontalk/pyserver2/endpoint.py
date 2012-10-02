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
from twisted.application import internet, service
from twisted.cred.portal import IRealm, Portal
from twisted.web.guard import HTTPAuthSessionWrapper

from kontalklib import database, token, utils
import version, storage

class BaseRequest(resource.Resource):
    def __init__(self, endpoint):
        resource.Resource.__init__(self)
        self.endpoint = endpoint


class ChannelRequest(BaseRequest):

    def render_GET(self, request):
        data = { 'id' : self.endpoint.requestChannel() }
        return json.dumps(data)


class DataChannel(BaseRequest):
    isLeaf = True

    def __init__(self, endpoint):
        BaseRequest.__init__(self, endpoint)

    def render_GET(self, request):
        log.debug(request.path)
        return 'TEST'


class Endpoint(resource.Resource):
    _children = {
        'channel' : ChannelRequest,
    }
    channels = {}

    def __init__(self, broker, userid):
        resource.Resource.__init__(self)
        self.broker = broker
        self.userid = userid

    def getChild(self, path, request):
        log.debug("path: %s" % path)
        try:
            return self.children[path]
        except KeyError:
            try:
                child = self._children[path](self)
                self.putChild(path, child)
                return child
            except KeyError:
                # assume channel id
                return self.channels[path]

    def _quick_response(self, request, code, text):
        request.setResponseCode(code)
        request.setHeader('content-type', 'text/plain')
        return text

    def bad_request(self, request):
        return self._quick_response(request, 400, 'bad request')

    def not_found(self, request):
        return self._quick_response(request, 404, 'not found')

    def render_GET(self, request):
        log.debug("request from %s: %s" % (self.userid, request.args))
        return self.bad_request(request)

    def requestChannel(self):
        log.debug("requesting channel for %s" % (self.userid))
        chid = utils.rand_str(40, utils.CHARSBOX_AZN_LOWERCASE)
        self.channels[chid] = DataChannel(self)
        return chid

    def logout(self):
        # TODO
        pass


class EndpointRealm(object):
    implements(IRealm)

    def __init__(self, broker):
        self.broker = broker

    def requestAvatar(self, avatarId, mind, *interfaces):
        endpoint = Endpoint(self.broker, avatarId)
        return interfaces[0], endpoint, endpoint.logout


class EndpointService(resource.Resource, service.Service):
    '''HTTP endpoint connection manager.'''

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
        portal = Portal(EndpointRealm(self), [utils.AuthKontalkToken()])
        resource = HTTPAuthSessionWrapper(portal, [credFactory])

        # TODO write something more suitable :)
        self.putChild('', static.Data('Kontalk HTTP service running.', 'text/plain'))
        self.putChild('endpoint', resource)

        # create http service
        factory = server.Site(self)
        fs_service = internet.TCPServer(port=self.config['server']['endpoint.bind'][1],
            factory=factory, interface=self.config['server']['endpoint.bind'][0])
        fs_service.setServiceParent(self.parent)
