# -*- coding: utf-8 -*-
'''Pyserver2 configuration.'''

from pyserver2 import storage


config = {
    'server' : {
        'fingerprint' : '37D0E678CDD19FB9B182B3804C9539B401F8229C',
        'c2s.bind' : ('localhost', 6126),
        's2s.bind' : ('localhost', 6127),
        'fileserver.bind' : ('localhost', 6128),
        'c2s.pack_size_max' : 1048576,  # 1 MB
        's2s.pack_size_max' : 10485760, # 10 MB
        'supports.google_c2dm' : True
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
            storage.MySQLStorage,
            '/tmp/kontalk'
        ),
        # messages bigger than this size will be refused
        'max_size' : 102400, # 100 KB
        # accepted content types
        'accept_content' : (
            'text/plain',
            'text/x-vcard',
            'text/vcard'
        )
    },
    'fileserver' : {
        # messages bigger than this size will be refused
        'max_size' : 10485760,  # 10 MB
        # accepted content types
        'accept_content' : (
            'text/plain',
            'text/x-vcard',
            'text/vcard',
            'image/gif',
            'image/png',
            'image/jpeg'
        ),
        'download_url' : 'http://10.0.2.2/messenger/download.php?name=%s'
    },
    'database' : {
        'host' : 'localhost',
        'port' : 3306,
        'user' : 'root',
        'password' : 'ciao',
        'dbname' : 'messenger1'
    },
    'google_c2dm' : {
        'email' : 'c2dm.account@gmail.com'
    }
}
