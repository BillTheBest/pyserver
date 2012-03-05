# Copyright (c) 2008 Johan Euphrosine
# See LICENSE for details.

from twisted.protocols.basic import Int32StringReceiver
from txprotobuf_pb2 import BoxContainer


class Protocol(Int32StringReceiver):

    def stringReceived(self, data):
        box = BoxContainer()
        box.ParseFromString(data)
        if box.name != "":
            out_klass = getattr(txprotobuf_pb2, box.name)
            out = out_klass()
            if box.value != "":
                out.ParseFromString(box.value)
            self.boxReceived(out)

    def boxReceived(self, data):
        raise NotImplementedError
