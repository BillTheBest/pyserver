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
import os, time

from zope.interface import implements

from twisted.application import internet
from twisted.python import failure
from twisted.internet import defer
from twisted.web import server, resource, iweb
from twisted.cred import credentials, checkers, error
from twisted.cred.portal import IRealm, Portal
from twisted.web.guard import HTTPAuthSessionWrapper
from twisted.protocols.basic import FileSender
from twisted.python.log import err

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


class ServerlistDownload(resource.Resource):
    def __init__(self, db):
        resource.Resource.__init__(self)
        self.servers = database.servers(db)

    def render_GET(self, request):
        a = c2s.ServerList()
        a.timestamp = long(time.time())

        # add ourselves first
        e = a.entry.add()
        e.address = config.config['server']['host']
        e.port = config.config['server']['c2s.bind'][1]
        e.http_port = config.config['server']['fileserver.bind'][1]

        srvlist = self.servers.get_list(False, True)
        for srv in srvlist:
            e = a.entry.add()
            e.address = srv['host']
            e.port = int(srv['port'])
            e.http_port = int(srv['http_port'])

        request.setHeader('content-type', 'application/x-google-protobuf')
        return a.SerializeToString()


class FileDownload(resource.Resource):
    def __init__(self, fileserver, userid):
        resource.Resource.__init__(self)
        self.fileserver = fileserver
        self.userid = userid

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
        if 'f' in request.args:
            fn = request.args['f'][0]
            info = self.fileserver.storage.get_extra(fn, self.userid)
            if info:
                (filename, mime, md5sum) = info
                genfilename = utils.generate_filename(mime)
                request.setHeader('content-type', mime)
                request.setHeader('content-length', os.path.getsize(filename))
                request.setHeader('content-disposition', 'attachment; filename="%s"' % (genfilename))
                request.setHeader('x-md5sum', md5sum)

                # stream file to the client
                fp = open(filename, 'rb')
                d = FileSender().beginFileTransfer(fp, request)
                def finished(ignored):
                    fp.close()
                    request.finish()
                d.addErrback(err).addCallback(finished)
                return server.NOT_DONE_YET

            # file not found in extra storage
            else:
                return self.not_found(request)

        return self.bad_request(request)

    def logout(self):
        # TODO
        pass

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
        log.debug("[upload] requestAvatar: %s" % avatarId)
        uploader = FileUpload(self.fileserver, avatarId)
        return interfaces[0], uploader, uploader.logout

class FileDownloadRealm(object):
    implements(IRealm)

    def __init__(self, fileserver):
        self.fileserver = fileserver

    def requestAvatar(self, avatarId, mind, *interfaces):
        log.debug("[download] requestAvatar: %s" % avatarId)
        downloader = FileDownload(self.fileserver, avatarId)
        return interfaces[0], downloader, downloader.logout


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

        # setup download endpoint
        portal = Portal(FileDownloadRealm(self), [AuthKontalkToken(self.db)])
        resource = HTTPAuthSessionWrapper(portal, [credFactory])
        self.putChild('download', resource)

        # setup serverlist endpoint
        self.putChild('serverlist', ServerlistDownload(self.db))

        # create http service
        factory = server.Site(self)
        service = internet.TCPServer(port=config.config['server']['fileserver.bind'][1],
            factory=factory, interface=config.config['server']['fileserver.bind'][0])
        service.setServiceParent(self.application)
