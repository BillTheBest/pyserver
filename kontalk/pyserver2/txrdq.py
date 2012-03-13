# -*- coding: utf-8 -*-
'''This code is under Public Domain.'''

from twisted.internet import defer, task
import pickle, cPickle


class DeferredPool(object):
    def __init__(self, initialContents=None):
        self._pool = set()
        self._waiting = []
        if initialContents:
            for d in initialContents:
                self.add(d)

    def _fired(self, result, d):
        self._pool.remove(d)
        if not self._pool:
            waiting, self._waiting = self._waiting, []
            for waiter in waiting:
                waiter.callback(None)
        return result

    def add(self, d):
        d.addBoth(self._fired, d)
        self._pool.add(d)
        return d

    def deferUntilEmpty(self, testImmediately=True):
        if testImmediately and not self._pool:
            return defer.succeed(None)
        else:
            d = defer.Deferred()
            self._waiting.append(d)
            return d


class QueueStopped(Exception):
    pass


class ResizableDispatchQueue(object):

    _sentinel = object()

    def __init__(self, func):
        self._queue = defer.DeferredQueue()
        self._func = func
        self._pool = DeferredPool()
        self._coop = task.Cooperator()
        self._currentWidth = 0
        self._pendingStops = 0
        self._stopped = False

    def put(self, obj):
        if self._stopped:
            raise QueueStopped()
        self._queue.put(obj)

    def pending(self):
        return list(self._queue.pending)

    def stop(self):
        self._stopped = True
        # Flush waiters who can now never get a usable item from the queue.
        while self._queue.waiting:
            self._queue.put(self._sentinel)
        d = self._pool.deferUntilEmpty()
        d.addCallback(lambda _: self.pending())
        return d

    def _call(self, obj):
        if not obj is self._sentinel:
            return defer.maybeDeferred(self._func, obj)

    def next(self):
        if self._stopped:
            raise StopIteration
        elif self._pendingStops:
            self._pendingStops -= 1
            self._currentWidth -= 1
            raise StopIteration
        else:
            d = self._queue.get()
            d.addCallback(self._call)
            return d

    def narrow(self, n=1):
        self._setWidth(self.width - n)

    def widen(self, n=1):
        self._setWidth(self.width + n)

    start = widen

    def _getWidth(self):
        return self._currentWidth - self._pendingStops

    def _setWidth(self, width):
        targetWidth = self._currentWidth - self._pendingStops
        extra = width - targetWidth
        if extra > 0:
            # Make ourselves wider.
            delta = extra - self._pendingStops
            if delta >= 0:
                self._pendingStops = 0
                for i in xrange(delta):
                    self._pool.add(self._coop.coiterate(self))
                self._currentWidth += delta
            else:
                self._pendingStops -= extra
        elif extra < 0:
            # Make ourselves narrower.
            self._pendingStops -= extra

    width = property(_getWidth, _setWidth)

    def setWidth(self, width):
        self.width = width

class PersistentDispatchQueue(ResizableDispatchQueue):

    def __init__(self, filename, func):
        ResizableDispatchQueue.__init__(self, func)
        try:
            # reload queue data from storage
            _file = open(filename, 'rb')
            self.elements = cPickle.load(_file)
            _file.close()

            for elem in self.elements:
                ResizableDispatchQueue.put(self, elem)
        except:
            self.elements = []

        self._filename = filename
        # file will be opened on first sync
        self._file = None

    def put(self, obj):
        ResizableDispatchQueue.put(self, obj)
        # save to disk
        self.elements.append(obj)
        self._sync()

    def next(self):
        d = ResizableDispatchQueue.next(self)
        if len(self.elements) > 0:
            del self.elements[0]
            self._sync()
        return d

    def stop(self):
        #log.debug("stopping queue (cleaning %s)" % self._filename)
        ResizableDispatchQueue.stop(self)
        self._file.close()
        os.remove(self._filename)

    def _sync(self):
        #log.debug("writing down %d elements to %s" % (len(self.elements), self._filename))
        if not self._file:
            self._file = open(self._filename, 'wb')
        self._file.seek(0)
        self._file.truncate()
        if len(self.elements) > 0:
            cPickle.dump(self.elements, self._file, pickle.HIGHEST_PROTOCOL)
        self._file.flush()
