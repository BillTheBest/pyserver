# -*- coding: utf-8 -*-
'''Pyserver2 configuration.'''

config = {
    'server' : {
        'fingerprint' : '96072D50F1A0EE5BD8664733F86AAD37AA187333',
        'c2s.bind' : ('localhost', 5554),
        's2s.bind' : ('localhost', 5556)
    },
    'broker' : {
        'storage_path' : '/tmp/kontalk'
    },
    'database' : {
        'host' : 'localhost',
        'port' : 3306,
        'user' : 'root',
        'password' : 'ciao',
        'dbname' : 'messenger1'
    }
}
