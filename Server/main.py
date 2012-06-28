#!/usr/bin/python -OO
'''
@author: Owain Jones [odj@aber.ac.uk]
'''

import data, jsonpickle
from logger import Logger
from twisted.words.protocols import irc
from twisted.internet import protocol, reactor
from twisted.web.server import Site
from twisted.web.resource import Resource
from twisted.internet.task import LoopingCall
from time import time
from hashlib import sha256

import config

global database, log, connections
database = None
log = Logger()
connections = {}

def to_json(object):
    #return json.dumps(object.__dict__)
    return str(jsonpickle.encode(object))

def sync_time(client_time,timestamp):
    '''Synchronize a timestamp between client & server'''
    delta = int(time())-int(client_time)
    return int(timestamp)+delta

class Page(Resource):
    '''Default Page class: handles checking for authentication etc., making it
    easier to implement new pages via subclassing'''
    needsAuth = True    # Does the request need to have user,time and token?
    needsAdmin = False  # Can only admins do this?
    def render_POST(self, request):
        request.setHeader("content-type", "application/json")
        if self.needsAuth is True:
            try:
                server_time = str(int(time()))
                username = request.args['user'][0]
                if self.needsAdmin and database.user[username].admin != True:
                    return self.error(request)
                client_time = request.args['ctime'][0]
                client_hash = request.args['token'][0]
                server_pass = database.user[username].password
                server_hash = sha256(client_time+server_pass).hexdigest()
                if client_hash == server_hash:
                    return self.run(request)
                
                return self.error(request)
            except KeyError:
                return self.error(request)
        else:
            return self.run(request)
    
    def render_GET(self, request):
        if self.needsAuth is True:
            return self.error(request)
        else:
            return self.render_POST(request)
    
    def run(self, request):
        pass
    
    def error(self, request):
        request.setHeader("content-type", "application/json")
        request.setResponseCode(403)
        return '{"message": "s:PERMISSION_DENIED"}'
    
class Registration(Page):
    needsAuth = False
    def run(self, request):
        username = request.args['username'][0]
        password = request.args['password'][0]
        if username in database.user.keys():
            return '{"message": "s:ALREADY_REGISTERED"}'
        database.user[username] = data.User()
        database.user[username].password = password
        log.l("New user "+username+" registered.")
        return '{"message": "s:REGISTER_SUCCESS"}'

    def __init__(self):
        Page.__init__(self)
        self.putChild('form', self.Form())

    class Form(Resource):
        isLeaf = True
        def render_GET(self, request):
            request.setHeader("content-type", "text/html")
            return '''
<html><body><form method="POST" action="/register">
    <p> Username: <input name="username" type="text" /></p>
    <p> Password: <input name="password" type="password" /></p>
    <p><input type="submit" value="Register!" /></p>
</form></body></html>
'''

class IRCServer(Resource):
    class Connect(Page):
        isLeaf = True
        def run(self, request):
            user = request.args['user'][0]
            server = request.args['server'][0]
            list = database.user[user].master.server
            if server not in list.keys():
                list[server] = data.Server()
                if 'nick' in request.args.keys():
                    nick = request.args['nick'][0]
                else:
                    nick = get_default_nick()
                list[server].nick = nick
                connections[user+'_'+server] = IRCFactory(user, server, nick)
                reactor.connectTCP(server, 6667, connections[user+'_'+server])
                
                return '{"message": "s:CONNECTING"}'
            else:
                return '{"message": "s:ALREADY_CONNECTED"}'
        
    class Disconnect(Page):
        isLeaf = True
        def run(self, request):
            user = request.args['user'][0]
            server = request.args['server'][0]
            del database.user[user].master.server[server]
            connections[user+'_'+server].irc.quit()
            del connections[user+'_'+server]
            return '{"message": "s:DISCONNECTED"}'
        
    class Join(Page):
        isLeaf = True
        def run(self, request):
            user = request.args['user'][0]
            server = request.args['server'][0]
            channel = request.args['channel'][0]
            connections[user+'_'+server].irc.join(channel)
            return '{"message": "s:JOINED"}'
    
    def __init__(self):
        Resource.__init__(self)
        self.putChild('connect',self.Connect())
        self.putChild('disconnect',self.Disconnect())
        self.putChild('join',self.Join())
    
class SaveDB(Page):
    isLeaf = True
    needsAdmin = True
    def run(self, request):
        log.l("Forced save of database")
        database.save()
        return '{"message": "Database saved."}'

class Info(Page):
    isLeaf = True
    def run(self, request):
        username = request.args['user'][0]
        return to_json(database.user[username])

def save_data():
    log.l("Periodic database save")
    database.save()

def get_default_nick():
    return config.DEFAULT_NICK+str(++config.DEFAULT_NICK_I)

class IRCConnection(irc.IRCClient):
    def _get_nickname(self):
        return self.factory.nickname
    def _get_server(self):
        return self.factory.server
    def _get_user(self):
        return self.factory.user
    nickname = property(_get_nickname)
    server = property(_get_server)
    user = property(_get_user)

    def signedOn(self):
        log.l("Signed on as %s" % (self.nickname,))
        
    def joined(self, channel):
        database.user[self.user].master.server[self.server].channels[channel] \
        = data.Channel()
        log.l("Joined %s" % (channel,))
    
    def privmsg(self, user, channel, msg):
        chan = database.user[self.user].master.server[self.server].channels[channel]
        message = data.Message(self.server, channel, user, msg)
        #if(str(msg).)
        for highlight in chan.highlights:
            if highlight in msg:
                chan.highlighted.append(message)
        if self.nickname in msg:
            chan.highlighted.append(message)
        chan.messages.append(message)
        log.l("Msg -> %s, List -> %s" % (msg,len(chan.messages)))

class IRCFactory(protocol.ClientFactory):
    protocol = IRCConnection
    
    def __init__(self, user, server, nickname):
        self.nickname = nickname
        self.server = server
        self.user = user
        #connections[user+'_'+server] = self
        
    def clientConnectionLost(self, connector, reason):
        log.l("Lost connection (%s), reconnecting..." % (reason,))
        connector.connect()
        
    def clientConnectionFailed(self, connector, reason):
        log.l("Couldn't connect: %s" % (reason,))
        
    def buildProtocol(self, addr):
        p = IRCConnection()
        p.factory = self
        self.proto = p
        self.irc = p
        return p

if __name__ == '__main__':
    log.l("Yes, this is dog")
    
    database = data.get()
    
    for user in database.user:
        database.user[user].admin = False
    try:
        database.user['owain'].admin = True
    except KeyError:
        log.l("User 'owain' doesn't exist yet.")

    root = Page()
    root.putChild('saveDB',SaveDB())
    root.putChild('info',Info())
    root.putChild('server',IRCServer())
    registration = Registration()
    root.putChild('register', registration)
    
    site = Site(root)

    lc = LoopingCall(save_data).start(60)
    
    reactor.listenTCP(8080, site)
    reactor.run()
    
    log.l("Twisted Reactor shutdown, saving database")
    database.save()