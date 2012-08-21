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
	self.cookie = ''
	self.readonly = False

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
    def __init__(self,server,channel,nick,message,highlight=False):
        self.timestamp = time()
        self.server = server
        self.channel = channel
        self.nick = nick
        self.message = message
        self.highlight = highlight

    def __key(self):
        return (self.timestamp, self.server, self.channel,
                self.nick, self.message)

    def __eq__(x,y):
        return x.__key() == y.__key()

    def __hash__(self):
        return hash(self.__key())
        
class Event(Message):
    def __init__(self,server,channel,nick,message,event,highlight=False):
        Message.__init__(self, server, channel, nick, message, highlight)
        self.event = event

    def __key(self):
        return (self.timestamp, self.server, self.channel,
                self.nick, self.message, self.event)
        
class File(Message):
    def __init__(self,server,channel,nick,message,highlight=False):
        Message.__init__(self,server,channel,nick,message,highlight)
        self.data = None
        
    def get(self):
        try:
            return open('downloads/'+self.nick+'_'+self.message)
        except IOError:
            return None
