#!/bin/sh

PYTHONPATH=../kontalklib:. exec twistd --pidfile kontalk3.pid -n kontalk -c server3.conf
