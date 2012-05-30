#!/bin/sh

PYTHONPATH=../kontalklib exec twistd -y start.py $*
