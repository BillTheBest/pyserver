# -*- coding: utf-8 -*-
'''Pyserver2 configuration.'''

from pyserver2 import storage


config = {
    'server' : {
        'fingerprint' : '96072D50F1A0EE5BD8664733F86AAD37AA187333',
        'c2s.bind' : ('localhost', 6126),
        's2s.bind' : ('localhost', 6127)
    },
    'registration' : {
        'type' : 'sms',
        #'from' : 'Kontalk',
        'from' : '12345',
        'nx.username' : 'key',
        'nx.password' : 'secret',
        'android_emu' : True
    },
    'broker' : {
        'storage' : (
            storage.PersistentDictStorage,
            '/tmp/kontalk'
        )
    },
    'database' : {
        'host' : 'localhost',
        'port' : 3306,
        'user' : 'root',
        'password' : 'ciao',
        'dbname' : 'messenger1'
    }
}
