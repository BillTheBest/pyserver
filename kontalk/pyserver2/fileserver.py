# -*- coding: utf-8 -*-
'''The Fileserver Service.'''
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

from twisted.application import internet, service
from twisted.python import failure
from twisted.internet import defer
from twisted.web import server, resource, iweb
from twisted.cred import credentials, checkers, error
from twisted.cred.portal import IRealm, Portal
from twisted.web.guard import HTTPAuthSessionWrapper
from twisted.protocols.basic import FileSender
from twisted.python.log import err

import kontalklib.c2s_pb2 as c2s
from kontalklib import database, token, utils
import version, storage


class IKontalkToken(credentials.ICredentials):

    def checkToken():
        pass


class KontalkToken(object):
    implements(IKontalkToken)

    def __init__(self, token, config):
        self.token = token
        self.config = config

    def checkToken(self, db):
        log.debug("checking token %s" % self.token)
        try:
            return token.verify_user_token(self.token, database.servers(db), self.config['server']['fingerprint'])
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

    def __init__(self, config):
        self.config = config

    def getChallenge(self, request):
        log.debug(('getChallenge', request))
        return {}

    def decode(self, response, request):
        key, token = response.split('=', 1)
        log.debug("got token from request: %s" % token)
        if key == 'auth':
            return KontalkToken(token, self.config)

        raise error.LoginFailed('Invalid token')


class ServerlistDownload(resource.Resource):
    def __init__(self, fileserver):
        resource.Resource.__init__(self)
        self.servers = database.servers(fileserver.db)
        self.config = fileserver.config

    def render_GET(self, request):
        a = c2s.ServerList()
        a.timestamp = long(time.time())

        # add ourselves first
        e = a.entry.add()
        e.address = self.config['server']['host']
        e.port = self.config['server']['c2s.bind'][1]
        e.http_port = self.config['server']['fileserver.bind'][1]

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
                log.debug("sending file type %s, path %s, md5sum %s" % (mime, filename, md5sum))
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
        self.config = fileserver.config
        self.userid = userid

    def _quick_response(self, request, code, text):
        request.setResponseCode(code)
        request.setHeader('content-type', 'text/plain')
        return text

    def bad_request(self, request):
        return self._quick_response(request, 400, 'bad request')

    def render_POST(self, request):
        log.debug("request from %s: %s" % (self.userid, request.requestHeaders))
        a = c2s.FileUploadResponse()

        # check mime type
        mime = request.getHeader('content-type')
        if mime not in self.config['fileserver']['accept_content']:
            a.status = c2s.FileUploadResponse.STATUS_UNSUPPORTED
        else:
            # check length
            length = request.getHeader('content-length')
            if length != None:
                length = long(length)
                if length <= self.config['fileserver']['max_size']:
                    # store file to storage
                    # TODO convert to file-object management for lighter memory consumption
                    data = request.content.read()
                    if len(data) == length:
                        (filename, fileid) = self.fileserver.storage.extra_storage(('', ), mime, data)
                        log.debug("file stored to disk (filename=%s, fileid=%s)" % (filename, fileid))
                        a.status = c2s.FileUploadResponse.STATUS_SUCCESS
                        a.file_id = fileid
                    else:
                        log.debug("file length not matching content-length header (%d/%d)" % (len(data), length))
                        a.status = c2s.FileUploadResponse.STATUS_ERROR
                else:
                    log.debug("file too big (%d bytes)" % length)
                    a.status = c2s.FileUploadResponse.STATUS_BIG
            else:
                log.debug("content-length header not found")
                a.status = c2s.FileUploadResponse.STATUS_ERROR

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


class Fileserver(resource.Resource, service.Service):
    '''Fileserver connection manager.'''

    def __init__(self, application, config, broker=None):
        resource.Resource.__init__(self)
        self.setServiceParent(application)
        self.config = config
        self.broker = broker

    def print_version(self):
        log.info("%s Fileserver version %s" % (version.NAME, version.VERSION))

    def startService(self):
        service.Service.startService(self)
        if self.broker:
            # daemon mode - print init message
            log.debug("fileserver init")
            self.storage = self.broker.storage
            self.db = self.broker.db
        else:
            # standalone - print version
            self.print_version()
            # create storage and database connection on our own
            self.storage = storage.__dict__[self.config['broker']['storage'][0]](*self.config['broker']['storage'][1:])
            self.db = database.connect_config(self.config)
            self.storage.set_datasource(self.db)

        # setup upload endpoint
        portal = Portal(FileUploadRealm(self), [AuthKontalkToken(self.db)])
        credFactory = AuthKontalkTokenFactory(self.config)
        resource = HTTPAuthSessionWrapper(portal, [credFactory])
        self.putChild('upload', resource)

        # setup download endpoint
        portal = Portal(FileDownloadRealm(self), [AuthKontalkToken(self.db)])
        resource = HTTPAuthSessionWrapper(portal, [credFactory])
        self.putChild('download', resource)

        # setup serverlist endpoint
        self.putChild('serverlist', ServerlistDownload(self))

        # create http service
        factory = server.Site(self)
        fs_service = internet.TCPServer(port=self.config['server']['fileserver.bind'][1],
            factory=factory, interface=self.config['server']['fileserver.bind'][0])
        fs_service.setServiceParent(self.parent)


class FileserverApp:
    '''Standalone Fileserver application starter.'''

    def __init__ (self, argv):
        self.application = service.Application("Pyserver.Fileserver")
        # FIXME this won't work with twistd - need to write a twistd plugin
        self._cfgfile = 'server.conf'
        for i in range(len(argv)):
            if argv[i] == '-c':
                self._cfgfile = argv[i + 1]

    def setup(self):
        # load configuration
        fp = open(self._cfgfile, 'r')
        self.config = json.load(fp)
        fp.close()

        log.init(self.config)

        # fileserver service
        self.fileserver = Fileserver(self.application, self.config)

        return self.application
