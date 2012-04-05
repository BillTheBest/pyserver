# -*- coding: utf-8 -*-
'''The Fileserver Service.'''
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


import logging as log

from zope.interface import implements

from twisted.application import internet
from twisted.python import failure
from twisted.internet import defer
from twisted.web import server, resource, iweb
from twisted.cred import credentials, checkers, error
from twisted.cred.portal import IRealm, Portal
from twisted.web.guard import HTTPAuthSessionWrapper

import kontalklib.c2s_pb2 as c2s
import kontalk.config as config
from kontalklib import database, token, utils


class IKontalkToken(credentials.ICredentials):

    def checkToken():
        pass


class KontalkToken(object):
    implements(IKontalkToken)

    def __init__(self, token):
        self.token = token

    def checkToken(self, db):
        log.debug("checking token %s", self.token)
        try:
            return token.verify_user_token(self.token, database.servers(db), config.config['server']['fingerprint'])
        except:
            import traceback
            traceback.print_exc()
            log.debug("token verification failed!")


class AuthKontalkToken(object):
    implements(checkers.ICredentialsChecker)

    credentialInterfaces = IKontalkToken,

    def __init__(self, db):
        self.db = db

    def _cbTokenValid(self, userid):
        log.debug("token userid=%s" % userid)
        if userid:
            return userid
        else:
            return failure.Failure(error.UnauthorizedLogin())

    def requestAvatarId(self, credentials):
        log.debug("avatarId: %s" % credentials)
        return defer.maybeDeferred(
            credentials.checkToken, self.db).addCallback(
            self._cbTokenValid)


class AuthKontalkTokenFactory(object):
    implements(iweb.ICredentialFactory)

    scheme = 'kontalktoken'

    def getChallenge(self, request):
        log.debug(('getChallenge', request))
        return {}

    def decode(self, response, request):
        key, token = response.split('=', 1)
        log.debug("got token from request: %s", token)
        if key == 'auth':
            return KontalkToken(token)

        raise error.LoginFailed('Invalid token')


class FileUpload(resource.Resource):
    def __init__(self, fileserver, userid):
        resource.Resource.__init__(self)
        self.fileserver = fileserver
        self.userid = userid

    def render_POST(self, request):
        log.debug("request from %s: %s" % (self.userid, request.requestHeaders))
        a = c2s.FileUploadResponse()

        mime = request.getHeader('content-type')
        if mime not in config.config['fileserver']['accept_content']:
            a.status = c2s.FileUploadResponse.STATUS_UNSUPPORTED
        else:
            # store file to storage
            (filename, fileid) = self.fileserver.storage.extra_storage(('', ), mime, request.content.read())
            a.status = c2s.FileUploadResponse.STATUS_SUCCESS
            a.file_id = fileid

        request.setHeader('content-type', 'application/x-google-protobuf')
        return a.SerializeToString()

    def logout(self):
        # TODO
        pass


class FileUploadRealm(object):
    implements(IRealm)

    def __init__(self, fileserver):
        self.fileserver = fileserver

    def requestAvatar(self, avatarId, mind, *interfaces):
        log.debug("requestAvatar: %s" % avatarId)
        uploader = FileUpload(self.fileserver, avatarId)
        return interfaces[0], uploader, uploader.logout


class Fileserver(resource.Resource):
    '''Fileserver connection manager.'''

    def __init__(self, application, broker):
        resource.Resource.__init__(self)
        self.application = application
        self.broker = broker
        self.storage = self.broker.storage
        self.db = self.broker.db

    def setup(self):
        log.debug("fileserver init")

        # setup upload endpoint
        portal = Portal(FileUploadRealm(self), [AuthKontalkToken(self.db)])
        credFactory = AuthKontalkTokenFactory()
        resource = HTTPAuthSessionWrapper(portal, [credFactory])
        self.putChild('upload', resource)

        # TODO setup download endpoint

        # create http service
        factory = server.Site(self)
        service = internet.TCPServer(port=config.config['server']['fileserver.bind'][1],
            factory=factory, interface=config.config['server']['fileserver.bind'][0])
        service.setServiceParent(self.application)
