#!/bin/sh

PYTHONPATH=../kontalklib:. exec twistd --pidfile kontalk2.pid -n kontalk -c server2.conf
