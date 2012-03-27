# -*- coding: utf-8 -*-
'''Message broker storage abstraction and implementatins.'''
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


import os
from kontalklib import utils
import logging as log


class MessageStorage:
    '''Interface for a message broker storage.'''

    def set_datasource(self, ds):
        '''Sets a datasource after-init.'''
        pass

    def get_timestamp(self, uid):
        '''Retrieves the timestamp of a user/mailbox.'''
        pass

    def stop(self, uid):
        '''Stops a storage for a userid.'''
        pass

    def load(self, uid):
        '''Loads a storage for a userid.'''
        pass

    def store(self, uid, msg, force = False):
        '''Used to persist a message.'''
        pass

    def deliver(self, userid, msg, force = False):
        '''Used to persist a message that was intended to a generic userid.'''
        pass

    def delete(self, uid, msgid):
        '''Deletes a single message.'''
        pass

    def extra_storage(self, content, name = None):
        '''Store a big file in the storage system.'''
        pass


class PersistentDictStorage(MessageStorage):
    '''PersistentDict-based message storage.'''

    '''Map of mailbox storages.'''
    _mboxes = {}

    def __init__(self, path):
        log.debug("init dict-based storage on %s" % path)
        self._path = path
        try:
            os.makedirs(self._path)
        except:
            pass
        self._extra_path = os.path.join(path, 'extra')
        try:
            os.makedirs(self._extra_path)
        except:
            pass

    def _get_storage(self, uid, flag = 'c', force = False, cache = True):
        if uid not in self._mboxes or force:
            db = utils.PersistentDict(os.path.join(self._path, uid + '.mbox'), flag)
            if not cache:
                return db
            self._mboxes[uid] = db
        return self._mboxes[uid]

    def get_timestamp(self, uid):
        # TODO
        pass

    def stop(self, uid):
        is_generic = (len(uid) == utils.USERID_LENGTH)
        # avoid creating a useless mbox
        utils.touch(os.path.join(self._path, uid + '.mbox'), is_generic)
        # also touch the generic mbox
        if not is_generic:
            utils.touch(os.path.join(self._path, uid[:utils.USERID_LENGTH] + '.mbox'))

    def load(self, uid):
        try:
            return self._get_storage(uid, 'r', False, False)
        except:
            return None

    def store(self, uid, msg, force = False):
        db = self._get_storage(uid)
        if msg['messageid'] not in db or force:
            db[msg['messageid']] = msg
            db.sync()

    def deliver(self, userid, msg, force = False):
        # store the new message
        db = self._get_storage(userid)
        if msg['messageid'] not in db or force:
            db[msg['messageid']] = msg
            db.sync()

        # delete the old message in the generic user mailbox
        db = self._get_storage(userid[:utils.USERID_LENGTH])
        try:
            del db[msg['originalid']]
            db.sync()
        except:
            pass

    def delete(self, uid, msgid):
        try:
            db = self._get_storage(uid)
            del db[msgid]
            db.sync()
        except:
            import traceback
            traceback.print_exc()

    def extra_storage(self, content, name = None):
        if not name:
            name = utils.rand_str(40)
        filename = os.path.join(self._extra_path, name)
        f = open(filename, 'w')
        f.write(content)
        f.close()
        return (filename, name)


class MySQLStorage(MessageStorage):
    '''MySQL-based message storage.'''

    def __init__(self, db = None):
        self._db = db

    def set_datasource(self, ds):
        self._db = ds

    def get_timestamp(self, uid):
        '''Retrieves the timestamp of a user/mailbox.'''
        pass

    def stop(self, uid):
        '''Stops a storage for a userid.'''
        pass

    def load(self, uid):
        '''Loads a storage for a userid.'''
        pass

    def store(self, uid, msg, force = False):
        '''Used to persist a message.'''
        pass

    def deliver(self, userid, msg, force = False):
        '''Used to persist a message that was intended to a generic userid.'''
        pass

    def delete(self, uid, msgid):
        '''Deletes a single message.'''
        pass

    def extra_storage(self, content, name = None):
        '''Store a big file in the storage system.'''
        pass
