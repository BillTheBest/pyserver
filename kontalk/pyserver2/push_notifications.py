# -*- coding: utf-8 -*-
'''Push notifications support.'''
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

import urllib, urllib2

import kontalklib.logging as log
from kontalklib import database


class PushNotifications:
    '''Push notifications manager.'''

    def __init__(self, config, db):
        self._config = config
        self._db = db
        self._cachedb = database.usercache(db)
        self._notify_cache = {}

    def notify(self, userid):
        if userid not in self._notify_cache:
            self._notify_cache[userid] = 0
            server = self._push_server(userid)
            if server:
                log.debug("pushing notification to %s" % userid)
                return server.notify()
        else:
            self._notify_cache[userid] += 1

    def notify_all(self, uhash):
        match = self._cachedb.get_generic(uhash)
        ret = []
        for u in match:
            ret.append(self.notify(u['userid']))
        return ret

    def mark_user_online(self, userid):
        try:
            del self._notify_cache[userid]
        except:
            pass

    def _push_server(self, userid):
        '''Returns a PushServer instance for the given userid - if available.'''
        e = self._cachedb.get(userid, True)
        if e[GooglePush.field]:
            return GooglePush(self._config, userid, e[GooglePush.field])


class PushServer:
    '''Push server interface.'''

    def __init__(self):
        pass

    def notify(self):
        raise NotImplementedError()


class GooglePush(PushServer):
    '''Google C2DM implementation.'''

    # API entrypoint for C2DM requests
    url = 'https://android.apis.google.com/c2dm/send'
    # usercache field for registration id
    field = 'google_registrationid'

    def __init__(self, config, userid, regid):
        # TODO request token by using credentials
        self.token = config['google_c2dm']['token']
        self.userid = userid
        self.regid = regid

    def notify(self):
        params = urllib.urlencode({
            'registration_id' : self.regid,
            'collapse_key' : 'new',
            'data.action' : 'org.kontalk.CHECK_MESSAGES'
        })
        headers = {
            'Authorization' : 'GoogleLogin auth=' + self.token
        }
        req = urllib2.Request(self.url, params, headers)
        fd = urllib2.urlopen(req)
        # TODO what do we do with the output??
        data = fd.read()
        return data
