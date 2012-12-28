'''
@author: Owain Jones [odj@aber.ac.uk]
'''

import cPickle as pickle
import jsonpickle, logger
from time import time
from twisted.words.protocols import irc
from twisted.internet import protocol

log = logger.Logger()

def get():
    '''
    Static method.
    Unpickle the object from 'server.pkl' if it exists, otherwise create
    a new one.
    '''
    try:
        f = open('server.pkl','rb')
        obj = pickle.load(f)
        return obj
    except IOError:
        return Data()

class Data(object):
    '''
    Holds the data structure for the whole server (users, servers, nicks etc.)-
    the only thing it doesn't handle is the Twisted connections.
    '''
        
    def save(self):
        '''
        Pickle the current object to 'server.pkl'
        '''
        f = open('server.pkl', 'wb')
        pickle.dump(self, f, pickle.HIGHEST_PROTOCOL)
        self.changed = False

    def __init__(self):
        self.changed = True
        self.user = {}
    
class User(object):
    def __init__(self):
        self.password = None
        self.admin = False
        self.master = Master()

class Master(object):
    def __init__(self):
        self.highlights = set()
        self.ignore = set()
        self.blocked = set()
        self.events = []
        self.server = {}
        self.received_files = []
    
class Server(object):
    def __init__(self):
        self.nick = None
        self.channels = {}
        self.motd = None
    
class Channel(object):
    def __init__(self):
        self.highlights = set()
        self.ignore = set()
        self.blocked = set()
        self.users = set()
        self.messages = []
        self.buffer = []
        self.topic = None
    
class Message(object):
    def __init__(self,server,channel,nick,message):
        self.timestamp = time()
        self.server = server
        self.channel = channel
        self.nick = nick
        self.message = message
        
class Event(Message):
    def __init__(self,server,channel,nick,message,event):
        Message.__init__(self, server, channel, nick, message)
        self.event = event
        
class File(Message):
    def __init__(self,server,channel,nick,message):
        Message.__init__(self,server,channel,nick,message)
        self.data = None
        
    def get(self):
        try:
            return open('downloads/'+self.nick+'_'+self.message)
        except IOError:
            return None
