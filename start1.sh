#!/bin/sh

PYTHONPATH=../kontalklib:. exec twistd --pidfile kontalk1.pid -n kontalk -c server.conf
