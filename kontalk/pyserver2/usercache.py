# -*- coding: utf-8 -*-
'''Network user cache abstraction and implementations.'''
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
from kontalklib import database, utils
import kontalklib.logging as log


class Usercache:
    '''Interface for a usercache storage.'''

    def set_datasource(self, ds):
        '''Sets a datasource after-init.'''
        pass

    def touch_user(self, userid):
        '''Updates user last seen time to now.'''
        pass

    def set_user_data(self, userid, fields):
        '''Updates data of a user.'''
        pass

    def get_user_data(self, uid):
        '''Retrieves user data.'''
        pass

    def purge_users(self):
        '''Purges old user entries.'''
        pass


class MySQLUsercache(Usercache):
    '''MySQL-based usercache.'''

    def __init__(self, db = None):
        log.debug("init MySQL usercache")
        self.set_datasource(db)

    def set_datasource(self, ds):
        self._db = ds
        self._update_ds()

    def _update_ds(self):
        if self._db:
            self.userdb = database.usercache(self._db)
        else:
            self.userdb = None

    def touch_user(self, userid):
        '''Updates user last seen time to now.'''
        if len(userid) == utils.USERID_LENGTH_RESOURCE:
            self.userdb.update(userid)

    def set_user_data(self, userid, fields):
        '''Updates data of a user.'''
        if len(userid) == utils.USERID_LENGTH_RESOURCE:
            self.userdb.update(userid, None, **fields)

    def get_user_data(self, uid):
        '''Retrieves user data.'''
        dd = self.userdb.get(uid, False)
        if dd:
            dd['timestamp'] = long(time.mktime(dd['timestamp'].timetuple()))
        return dd

    def purge_users(self):
        '''Purges old user entries.'''
        return self.userdb.purge_old_entries()
