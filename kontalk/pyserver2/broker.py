# -*- coding: utf-8 -*-
'''The Message Broker Service.'''
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

import os, socket, time
from Queue import Queue
import pickle, shelve
import logging as log

from twisted.application import internet
from twisted.internet.defer import Deferred

# local imports
from channels import *
from broker_twisted import *
import version, storage
from txrdq import ResizableDispatchQueue
from push_notifications import PushNotifications

import kontalk.config as config
from kontalklib import database, utils

# mime type for receipt messages
MIME_RECEIPT = 'internal/receipt'
# mime type for presence notifications
MIME_PRESENCE = 'internal/presence'


# no ack is required
MSG_ACK_NONE = 0
# ack will not be bounced to sender
MSG_ACK_MANUAL = 1
# ack will be bounced to sender
MSG_ACK_BOUNCE = 2

# helper for checking event masks
USER_EVENT_MASKS = {
    c2s.UserPresence.EVENT_ONLINE : c2s.USER_EVENT_MASK_ONLINE,
    c2s.UserPresence.EVENT_OFFLINE : c2s.USER_EVENT_MASK_OFFLINE,
    c2s.UserPresence.EVENT_STATUS_CHANGED : c2s.USER_EVENT_MASK_STATUS_CHANGED
}


class MessageBroker:
    '''Message broker connection manager.'''

    '''Map of the queue consumers.
    Queues in this map will contain the collection of workers for specific userids.'''
    _consumers = {}
    '''Map of channel callbacks.'''
    _callbacks = {}
    '''Map of presence subscriptions.'''
    _presence = {}
    '''Map of reverse-presence subscriptions.'''
    _presence_lists = {}
    '''The push notifications manager.'''
    push_manager = None

    def __init__(self, application):
        self.application = application
        self.storage = config.config['broker']['storage'][0](*config.config['broker']['storage'][1:])

    def setup(self):
        log.debug("broker init")

        # estabilish a connection to the database
        self.db = database.connect_config(config.config)
        # datasource it will not be used if not neededs
        self.storage.set_datasource(self.db)

        # create push notifications manager
        if config.config['server']['push_notifications']:
            log.debug("enabling push notifications support")
            self.push_manager = PushNotifications(self.db)

        # create listening service for clients
        factory = InternalServerFactory(C2SServerProtocol, C2SChannel, self)
        service = internet.TCPServer(port=config.config['server']['c2s.bind'][1],
            factory=factory, interface=config.config['server']['c2s.bind'][0])
        service.setServiceParent(self.application)

        # create listening service for servers
        factory = InternalServerFactory(S2SServerProtocol, S2SChannel, self)
        service = internet.TCPServer(port=config.config['server']['s2s.bind'][1],
            factory=factory, interface=config.config['server']['s2s.bind'][0])
        service.setServiceParent(self.application)

    def _usermsg_worker(self, msg):
        userid = msg['recipient']
        need_ack = msg['need_ack']
        #log.debug("queue data for user %s (need_ack=%s)" % (userid, need_ack))

        # generic user, post to every consumer
        if len(userid) == utils.USERID_LENGTH:
            try:
                for resource, q in self._consumers[userid].iteritems():
                    outmsg = dict(msg)
                    # branch the message :)
                    outmsg['messageid'] = self.message_id()
                    outmsg['originalid'] = msg['messageid']
                    outmsg['recipient'] += resource

                    # store to disk (if need_ack)
                    if need_ack:
                        try:
                            #log.debug("storing message %s to disk" % outmsg['messageid'])
                            self.storage.deliver(outmsg['recipient'], outmsg)
                        except:
                            # TODO handle errors
                            import traceback
                            traceback.print_exc()

                    # send to client listener
                    q.put(outmsg)

            except KeyError:
                log.debug("warning: no listener to deliver message!")
                # store to temporary spool
                self.storage.store(userid, msg)
                # send push notifications to all matching users
                try:
                    if self.push_manager:
                        self.push_manager.notify_all(userid)
                except:
                    # TODO notify errors
                    import traceback
                    traceback.print_exc()


        elif len(userid) == utils.USERID_LENGTH_RESOURCE:
            uhash, resource = utils.split_userid(userid)

            # store to disk (if need_ack)
            if need_ack:
                try:
                    #log.debug("storing message %s to disk" % msg['messageid'])
                    self.storage.store(userid, msg)
                except:
                    # TODO handle errors
                    import traceback
                    traceback.print_exc()

            try:
                # send to client consumer
                self._consumers[uhash][resource].put(msg)
            except:
                log.debug("warning: no listener to deliver message to resource %s!" % resource)
                # send push notification
                try:
                    if self.push_manager:
                        self.push_manager.notify(userid)
                except:
                    # TODO notify errors
                    import traceback
                    traceback.print_exc()

        else:
            log.warn("warning: unknown userid format %s" % userid)

    def register_user_consumer(self, userid, worker):
        uhash, resource = utils.split_userid(userid)

        if uhash in self._consumers:
            if resource in self._consumers[uhash]:
                # resource conflict - stop previous queue worker
                self._consumers[uhash][resource].stop()
                # disconnect client
                self._callbacks[userid]['conflict']()
        else:
            self._consumers[uhash] = {}

        self._callbacks[userid] = { 'conflict' : worker.conflict }
        self._consumers[uhash][resource] = ResizableDispatchQueue(worker.incoming)
        self._consumers[uhash][resource].start(5)

        # mark user as online in the push notifications manager
        if self.push_manager:
            self.push_manager.mark_user_online(userid)

        # broadcast presence
        self.broadcast_presence(userid, c2s.UserPresence.EVENT_ONLINE)

        """
        WARNING these two need to be called in this order!!!
        Otherwise bad things happen...
        """
        # load previously stored messages (for specific) and requeue them
        self._reload_usermsg_queue(userid)
        # load previously stored messages (for generic) and requeue them
        self._reload_usermsg_queue(uhash)

    def unregister_user_consumer(self, userid):
        uhash, resource = utils.split_userid(userid)

        try:
            # end user storage
            self.storage.stop(userid)
            # touch user
            self.storage.touch_user(userid)
            try:
                # remove callbacks
                del self._callbacks[userid]
            except:
                pass
            # stop previous queue if any
            self._consumers[uhash][resource].stop()
            del self._consumers[uhash][resource]
            if len(self._consumers[uhash]) == 0:
                del self._consumers[uhash]
        except:
            import traceback
            traceback.print_exc()

        # remove presence subscriptions
        self.unsubscribe_user_presence(userid)
        # broadcast presence
        self.broadcast_presence(userid, c2s.UserPresence.EVENT_OFFLINE)

    def message_id(self):
        return utils.rand_str(30)

    def broadcast_presence(self, userid, event, status = None):
        def _broadcast(self, by_userid, to_userid, event, status):
            log.debug("broadcasting event %d by user %s to user %s" % (event, by_userid, to_userid))
            m = c2s.UserPresence()
            m.event = event
            if status != None:
                m.status_message = status
            self.publish_user(by_userid, to_userid, { 'mime' : MIME_PRESENCE, 'flags' : [] }, m.SerializeToString(), MSG_ACK_NONE)

        subs_generic, subs_specific = self.get_presence_subscribers(userid)
        if subs_generic:
            for sub, mask in subs_generic.iteritems():
                if mask & USER_EVENT_MASKS[event]:
                    _broadcast(self, userid, sub, event, status)
        if subs_specific:
            for sub, mask in subs_specific.iteritems():
                if mask & USER_EVENT_MASKS[event]:
                    _broadcast(self, userid, sub, event, status)

    def get_presence_subscribers(self, userid):
        '''Returns a tuple containing presence subscribers respectively for the generic user and the specific user.'''
        uhash, resource = utils.split_userid(userid)
        try:
            generic = self._presence[uhash]['']
        except:
            generic = None
        try:
            specific = self._presence[uhash][resource]
        except:
            specific = None

        return generic, specific

    def subscribe_user_presence(self, userid, uid, events, internal = False):
        if not internal:
            log.debug("subscribing %s to presence notifications by %s for events %d" % (userid, uid, events))
        # invalid username
        if len(uid) != utils.USERID_LENGTH and len(uid) != utils.USERID_LENGTH_RESOURCE:
            return c2s.UserPresenceSubscribeResponse.STATUS_INVALID_USERNAME
        # invalid event mask
        if events > c2s.USER_EVENT_MASK_ALL:
            return c2s.UserPresenceSubscribeResponse.STATUS_ERROR

        uhash, resource = utils.split_userid(uid)
        if uhash not in self._presence:
            self._presence[uhash] = {}
        if resource not in self._presence[uhash]:
            self._presence[uhash][resource] = {}
        if userid not in self._presence_lists:
            self._presence_lists[userid] = []

        if events == 0:
            try:
                # remove from subscriptions map
                del self._presence[uhash][resource][userid]
            except:
                pass
            if not internal:
                try:
                    # remove from subscriptions lists
                    self._presence_lists[userid].remove(uid)
                except:
                    pass
        else:
            # add to subscriptions map
            self._presence[uhash][resource][userid] = events
            if not internal:
                # add to subscriptions lists
                if uid not in self._presence_lists:
                    self._presence_lists[userid].append(uid)

        return c2s.UserPresenceSubscribeResponse.STATUS_SUCCESS

    def unsubscribe_user_presence(self, userid):
        '''Unsubscribes user to any kind of event by any user.'''
        log.debug("ubsubscribing %s from all presence notifications" % userid)
        if userid in self._presence_lists:
            for sub in self._presence_lists[userid]:
                self.subscribe_user_presence(userid, sub, 0, True)
            del self._presence_lists[userid]

    def user_online(self, uid):
        '''Returns true if the specified user currently is a registered consumer.'''
        uhash, resource = utils.split_userid(uid)
        generic_online = (uhash in self._consumers and len(self._consumers[uhash]) > 0)

        if resource:
            return generic_online and resource in self._consumers[uhash]
        else:
            return generic_online

    def _reload_usermsg_queue(self, uid):
        stored = dict(self.storage.load(uid))
        if stored:
            # requeue messages
            for msgid, msg in stored.iteritems():
                self._usermsg_worker(msg)

    def publish_user(self, sender, userid, headers = None, msg = None, need_ack = MSG_ACK_NONE):
        '''Publish a message to a user, either generic or specific.'''

        # TODO many other checks
        if len(userid) != utils.USERID_LENGTH and len(userid) != utils.USERID_LENGTH_RESOURCE:
            log.warn("invalid userid format: %s" % userid)
            # TODO should we throw an exception here?
            return None

        # prepare message dict
        msg_id = self.message_id()
        outmsg = {
            'messageid' : msg_id,
            'sender' : sender,
            'recipient' : userid,
            'timestamp' : time.time(),
            'need_ack' : need_ack,
            'headers' : headers,
            'payload' : msg
        }

        # process message immediately
        self._usermsg_worker(outmsg)

        return msg_id

    def ack_user(self, sender, msgid_list):
        '''Manually acknowledge a message.'''

        # result returned to the confirming client
        res = {}
        # message receipts grouped by recipient
        rcpt_list = {}

        # retrieve the messages that needs to be acknowledged
        db = self.storage.load(sender)

        for msgid in msgid_list:
            try:
                msg = db[msgid]
                if msg['need_ack'] == MSG_ACK_BOUNCE:
                    #log.debug("found message to be acknowledged - %s" % msgid)

                    # group receipts by user so we can batch send
                    backuser = msg['sender']
                    if backuser not in rcpt_list:
                        rcpt_list[backuser] = []

                    e = {
                        'messageid' : msgid if 'originalid' not in msg else msg['originalid'],
                        'storageid' : msgid,
                        'status' : c2s.ReceiptMessage.Entry.STATUS_SUCCESS,
                        'timestamp' : time.strftime('%Y-%m-%d %H:%M:%S %z')
                    }
                    rcpt_list[backuser].append(e)

                res[msgid] = True

            except:
                log.debug("message not found - %s" % msgid)
                res[msgid] = False

        # push the receipts back to the senders
        for backuser, msglist in rcpt_list.iteritems():
            r = c2s.ReceiptMessage()
            for m in msglist:
                e = r.entry.add()
                e.message_id = m['messageid']
                e.status = m['status']
                e.timestamp = m['timestamp']

            if not self.publish_user(sender, backuser, { 'mime' : MIME_RECEIPT, 'flags' : [] }, r.SerializeToString(), MSG_ACK_MANUAL):
                # mark the messages NOT SAFE to delete
                for m in msglist:
                    res[m['storageid']] = False

        # it's safe to delete the messages now
        for msgid, safe in res.iteritems():
            if safe:
                self.storage.delete(sender, msgid)
        # can't use sync - it's not valid for all storages - db.sync()

        return res
