# -*- coding: utf-8 -*-
'''Pyserver2 configuration.'''

from pyserver2 import storage


config = {
    'server' : {
        'fingerprint' : '96072D50F1A0EE5BD8664733F86AAD37AA187333',
        'c2s.bind' : ('localhost', 6126),
        's2s.bind' : ('localhost', 6127),
        'fileserver.bind' : ('localhost', 6128),
        'c2s.pack_size_max' : 1048576, # 1 MB
        's2s.pack_size_max' : 10485760 # 10 MB
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
        ),
        # messages bigger than this size will be stored in the filesystem
        'filesystem.threshold' : 102400, # 100 KB
        'filesystem.download.url' : 'http://10.0.2.2/messenger/download.php?name=%s'
    },
    'database' : {
        'host' : 'localhost',
        'port' : 3306,
        'user' : 'root',
        'password' : 'ciao',
        'dbname' : 'messenger1'
    }
}
