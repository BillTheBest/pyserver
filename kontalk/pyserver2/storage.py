# -*- coding: utf-8 -*-
'''Message broker storage abstraction and implementations.'''
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


class MessageStorage:
    '''Interface for a message broker storage.'''

    def set_datasource(self, ds):
        '''Sets a datasource after-init.'''
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

    def extra_storage(self, uids, mime, content, name = None):
        '''Store a big file in the storage system.'''
        pass

    def update_extra_storage(self, name, uids):
        '''Updates local storage data with the supplied uids.'''
        pass

    def get_extra(self, name, uid):
        '''Returns the full path of a file in the extra storage.'''
        pass

    def purge_messages(self):
        '''Purges expired/unknown messages.'''
        pass

    def purge_extra(self):
        '''Purges expired/orphan files on extra storage.'''
        pass

    def purge_validations(self):
        '''Purges old validation entries.'''
        pass

    ''' TODO all these go to DHT '''

    """
    def get_timestamp(self, uid):
        '''Retrieves the timestamp of a user/mailbox.'''
        pass

    def touch_user(self, uid):
        '''Updates user last seen time to now.'''
        pass

    def update_user(self, uid, fields):
        '''Updates fields of the user status table.'''
        pass

    def get_user_stat(self, uid):
        '''Retrieves user stat data.'''
        pass

    def purge_users(self):
        '''Purges old user entries.'''
        pass
    """


class PersistentDictStorage(MessageStorage):
    '''PersistentDict-based message storage.
    WARNING not up-to-date with MessageStorage interface
    '''

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

    def extra_storage(self, uids, mime, content, name = None):
        if not name:
            name = utils.rand_str(40)
        filename = os.path.join(self._extra_path, name)
        f = open(filename, 'w')
        f.write(content)
        f.close()
        return (filename, name)

    def get_extra(self, name, uid):
        '''Returns the full path of a file in the extra storage.'''
        return os.path.join(self._extra_path, name), None, None

    def touch_user(self, uid):
        # TODO
        pass


class MySQLStorage(MessageStorage):
    '''MySQL-based message storage.'''

    '''User messages cache.'''
    _cache = {}

    def __init__(self, path, db = None):
        log.debug("init MySQL storage")
        self._extra_path = path
        try:
            os.makedirs(self._extra_path)
        except:
            pass

        self._db = db
        self._update_ds()

    def set_datasource(self, ds):
        self._db = ds
        self._update_ds()

    def _update_ds(self):
        if self._db:
            self.userdb = database.usercache(self._db)
            self.msgdb = database.messages(self._db)
            self.attdb = database.attachments(self._db)
            self.valdb = database.validations(self._db)
        else:
            self.userdb = None
            self.msgdb = None
            self.attdb = None
            self.valdb = None

    def _invalidate(self, uid, msgid = None):
        try:
            if msgid:
                for i in range(len(self._cache[uid])):
                    if self._cache[uid][i]['id'] == msgid:
                        del self._cache[uid][i]
                        break
            else:
                del self._cache[uid]
        except:
            pass

    def stop(self, uid):
        '''Invalidates user message cache.'''
        self._invalidate(uid)
        # invalidate generic too if uid is specific
        if len(uid) == utils.USERID_LENGTH_RESOURCE:
            self._invalidate(uid[:utils.USERID_LENGTH])

    def _format_msg(self, msg):
        '''Converts a database row from the messages table to a broker message.'''
        dm = { 'headers' : {} }

        # message metadata
        dm['messageid'] = msg['id']
        dm['timestamp'] = msg['timestamp']
        if msg['orig_id']:
            dm['originalid'] = msg['orig_id']
        dm['sender'] = msg['sender']
        dm['recipient'] = msg['recipient']
        dm['need_ack'] = msg['need_ack']
        # TODO if msg['group']:

        # headers
        dm['headers']['mime'] = msg['mime']
        dm['headers']['ttl'] = msg['ttl']
        dm['headers']['flags'] = []
        if msg['encrypted'] != 0:
            dm['headers']['flags'].append('encrypted')
        if msg['filename']:
            dm['headers']['filename'] = msg['filename']

        # payload
        dm['payload'] = msg['content']
        return dm

    def load(self, uid):
        '''Loads a storage for a userid.'''
        msgdict = {}

        # special case: null uid -- retrieve message count by userid
        if not uid:
            msglist = self.msgdb.need_notification()
            for msg in msglist:
                msgdict[msg['recipient']] = msg['num']
        else:
            try:
                msglist = self._cache[uid]
            except KeyError:
                msglist = self.msgdb.incoming(uid, True)
                self._cache[uid] = msglist

            for msg in msglist:
                msgdict[msg['id']] = self._format_msg(msg)

        return msgdict

    def store(self, uid, msg, force = False):
        '''Used to persist a message.'''
        orig_id = utils.dict_get_none(msg, 'originalid')
        filename = utils.dict_get_none(msg['headers'], 'filename')
        encrypted = 'encrypted' in msg['headers']['flags']
        self.msgdb.insert(
            msg['messageid'],
            database.format_timestamp(msg['timestamp']),
            msg['sender'],
            uid,
            None,   # TODO groups
            msg['headers']['mime'],
            msg['payload'],
            encrypted,
            filename,
            # FIXME TTL self-managed!?!?!?
            100,
            msg['need_ack'],
            orig_id)
        # too much caching can kill you :)
        self._invalidate(uid)

    def deliver(self, userid, msg, force = False):
        '''Used to persist a message that was intended to a generic userid.'''
        # store again with specific userid
        self.store(userid, msg, force)
        # delete old generic message
        self.msgdb.delete(msg['originalid'])

    def delete(self, uid, msgid):
        '''Deletes a single message.'''
        self.msgdb.delete(msgid)
        # too much caching can kill you :)
        self._invalidate(uid, msgid)

    def extra_storage(self, uids, mime, content, name = None):
        '''Store a big file in the storage system.'''
        # TODO do not store files with same md5sum, they are supposed to be duplicates

        if not name:
            name = utils.rand_str(40)
        # content to filesystem
        filename = os.path.join(self._extra_path, name)
        f = open(filename, 'w')
        f.write(content)
        f.close()

        # calculate md5sum for file
        # this is intentionally done to verify that the file is not corruputed on disk
        md5sum = utils.md5sum(filename)

        # store in attachments
        for rcpt in uids:
            # TODO check insert errors
            self.attdb.insert(rcpt[:utils.USERID_LENGTH], name, mime, md5sum)

        return (filename, name)

    def update_extra_storage(self, name, uids):
        '''Updates local storage data with the supplied uids.'''
        # retrieve unmanaged attachment
        att = self.attdb.get(name, '')
        if att:
            for u in uids:
                try:
                    self.attdb.insert(u[:utils.USERID_LENGTH], name, att['mime'], att['md5sum'])
                except:
                    pass
            self.attdb.delete(name, '')

    def get_extra(self, name, uid):
        '''Returns the full path of a file in the extra storage.'''
        att = self.attdb.get(name, uid)
        if att:
            return str(os.path.join(self._extra_path, att['filename'])), str(att['mime']), str(att['md5sum'])

    def purge_messages(self):
        '''Purges expired/unknown messages.'''
        # decrease TTL for messages without a usercache entry
        self.msgdb.ttl_expired()
        # delete expired messages
        self.msgdb.purge_expired(1)

    def purge_extra(self):
        '''Purges expired/orphan files on extra storage.'''
        return self.attdb.purge_expired()

    def purge_validations(self):
        '''Purges old validation entries.'''
        return self.valdb.purge_expired()

    ''' TODO all these go to DHT '''

    """
    def get_timestamp(self, uid):
        '''Retrieves the timestamp of a user/mailbox.'''
        dd = self.userdb.get(uid, False)
        return long(time.mktime(dd['timestamp'].timetuple())) if dd else None

    def touch_user(self, uid):
        '''Updates user last seen time to now.'''
        if len(uid) == utils.USERID_LENGTH_RESOURCE:
            self.userdb.update(uid)

    def update_user(self, uid, fields):
        '''Updates fields of the user status table.'''
        # TODO optimize access to database
        if len(uid) == utils.USERID_LENGTH_RESOURCE:
            self.userdb.update(uid, None, **fields)

    def get_user_stat(self, uid):
        '''Retrieves user stat data.'''
        # TODO cached access
        dd = self.userdb.get(uid, False)
        if dd:
            dd['timestamp'] = long(time.mktime(dd['timestamp'].timetuple()))
        return dd

    def purge_users(self):
        '''Purges old user entries.'''
        return self.userdb.purge_old_entries()
    """
