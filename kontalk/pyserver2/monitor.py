# -*- coding: utf-8 -*-
'''The web monitoring Service.'''
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

import time
import kontalklib.logging as log

from twisted.application import internet, service
from twisted.python import failure
from twisted.internet import defer, task

try:
    from twisted.web import http
except ImportError:
    from twisted.protocols import http


from nevow import appserver, rend, loaders, static, inevow

import version


class WebMonitor(rend.Page, service.Service):
    '''Web monitor interface.'''

    addSlash = True
    child_images = static.File('monitor/images')
    docFactory = loaders.xmlfile('monitor/index.html')

    def __init__(self, application, config, broker):
        rend.Page.__init__(self)
        self.setServiceParent(application)
        self.config = config
        self.broker = broker

    def renderHTTP(self, ctx):
        request = inevow.IRequest(ctx)
        username, password = request.getUser(), request.getPassword()
        if (username, password) != (str(self.config['monitor']['username']), str(self.config['monitor']['password'])):
            request.setHeader('WWW-Authenticate', 'Basic realm="'+str(self.config['server']['network'])+'"')
            request.setResponseCode(http.UNAUTHORIZED)
            return "Authentication required."

        return rend.Page.renderHTTP(self, ctx)

    def data_title(self, context, data):
        return version.NAME + ' ' + version.VERSION

    def data_uptime(self, context, data):
        uptime = long(self.broker.uptime())
        mins, secs = divmod(uptime, 60)
        hours, mins = divmod(mins, 60)
        return '%02d:%02d:%02d' % \
            (hours, mins, secs)

    def data_local_users(self, context, data):
        return self.broker.users_cached_count()

    def data_local_online(self, context, data):
        return self.broker.users_online_count()

    def data_local_last_week(self, context, data):
        # TODO
        return 'n/a'

    def startService(self):
        service.Service.startService(self)
        log.debug("monitor init")
        self.storage = self.broker.storage
        self.db = self.broker.db

        # create http service
        self.putChild('favicon.ico', static.File('monitor/favicon.ico'))

        factory = appserver.NevowSite(self)
        fs_service = internet.TCPServer(port=self.config['server']['monitor.bind'][1],
            factory=factory, interface=self.config['server']['monitor.bind'][0])
        fs_service.setServiceParent(self.parent)
