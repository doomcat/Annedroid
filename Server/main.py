#!/usr/bin/python -OO
'''
@author: Owain Jones [odj@aber.ac.uk]
'''

import data, jsonpickle, json
from logger import Logger
from twisted.words.protocols import irc
from twisted.internet import protocol, reactor
from twisted.web.server import Site, NOT_DONE_YET
from twisted.web.resource import Resource
from twisted.internet.task import LoopingCall, deferLater
from time import time, sleep
from hashlib import sha256

import config

global database, log, connections
database = None
log = Logger()
connections = {}

def to_json(object):
    #return json.dumps(object.__dict__)
    return str(jsonpickle.encode(object))

def to_json_simple(object):
    return json.dumps(object.__dict__)

def sync_time(client_time,timestamp):
    '''Synchronize a timestamp between client & server'''
    delta = int(time())-int(client_time)
    return int(timestamp)+delta

def parse_args(request):
    out = {}
    for arg in ['user','server','channel','message','last_checked','nick']:
        try: out[arg] = request.args[arg][0]
        except KeyError: pass
    return out

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
                    request.a = parse_args(request)
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
            a = request.a
            list = database.user[a['user']].master.server
            if a['server'] not in list.keys():
                list[a['server']] = data.Server()
                if 'nick' in request.args.keys():
                    nick = a['nick']
                else:
                    nick = get_default_nick()
                list[a['server']].nick = nick
                connections[a['user']+'_'+a['server']]\
                 = IRCFactory(a['user'], a['server'], a['nick'])
                reactor\
                .connectTCP(a['server'], 6667,\
                connections[a['user']+'_'+a['server']])
                
                return '{"message": "s:CONNECTING"}'
            else:
                return '{"message": "s:ALREADY_CONNECTED"}'
        
    class Disconnect(Page):
        isLeaf = True
        def run(self, request):
            a = request.a
            del database.user[a['user']].master.server[a['server']]
            connections[a['user']+'_'+a['server']].irc.quit()
            del connections[a['user']+'_'+a['server']]
            return '{"message": "s:DISCONNECTED"}'
        
    class Join(Page):
        isLeaf = True
        def run(self, request):
            a = request.a
            connections[a['user']+'_'+a['server']].irc.join(a['channel'])
            return '{"message": "s:JOINED"}'
        
    class Leave(Page):
        isLeaf = True
        def run(self, request):
            a = request.a
            connections[a['user']+'_'+a['server']].irc.leave(a['channel'])
            return '{"message": "s:LEFT"}'
        
    class Message(Page):
        isLeaf = True
        def run(self, request):
            a = request.a
            nick = connections[a['user']+'_'+a['server']].irc.nickname
            mobj = data.Message(a['server'],a['channel'],nick,a['message'])
            database.user[a['user']].master.server[a['server']]\
            .channels[a['channel']].messages.append(mobj)
            connections[a['user']+'_'+a['server']].irc\
            .msg(a['channel'], a['message'])
            return '{"message": "s:SENT"}'
    
    def __init__(self):
        Resource.__init__(self)
        self.putChild('connect',self.Connect())
        self.putChild('disconnect',self.Disconnect())
        self.putChild('join',self.Join())
        self.putChild('leave',self.Leave())
        self.putChild('message',self.Message())
    
class Events(Page):
    def run(self, request):
        a = request.a
        messages = database.user[a['user']].master.events
        out = '{"messages": [\n'
        for message in messages:
            out += to_json_simple(message)+',\n'
        out = out[:-2]
        out += '\n]}'
        return out

class Channel(Page):
    def run(self, request):
        a = request.a
        messages = database.user[a['user']].master.server[a['server']]\
        .channels[a['channel']].messages
        out = '{"messages": [\n'
        for message in messages:
            out += to_json_simple(message)+',\n'
        out = out[:-2]
        out += '\n]}'
        return out
        
    class New(Page):
        def run(self, request):
            request.user = request.args['user'][0]
            request.server = request.args['server'][0]
            request.channel = request.args['channel'][0]
            
            if len(database.user[request.user].master.server[request.server]\
                .channels[request.channel].buffer) == 0:
                request.oneshot = False
                deferLater(reactor, 1, self.run, request)
                return NOT_DONE_YET
            else:
                request.oneshot = True
            
            messages = database.user[request.user].master\
            .server[request.server].channels[request.channel].buffer
            out = '{"messages": [\n'
            for message in messages:
                out += to_json_simple(message)+',\n'
            out = out[:-2]
            out += '\n]}'
            database.user[request.user].master.server[request.server]\
            .channels[request.channel].buffer = []
            
            request.write(out)
            request.finish()

    def __init__(self):
        Page.__init__(self)
        self.putChild('new', self.New())

class Eval(Page):
    isLeaf = True
    needsAdmin = True
    def run(self, request):
        a = request.a
        out = eval(a['message'],globals(),locals())
        log.l("Eval: %s" % (out,))
        return '{"output": "%s"}' % (out,)

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
        for channel in database.user[self.user].master.server[self.server]\
        .channels:
            rejoin(self.user,self.server,channel)
        
    def joined(self, channel):
        database.user[self.user].master.server[self.server].channels[channel]\
        = data.Channel()
        database.user[self.user].master.events.append(
            data.Event(self.server, channel, self.user, None, "CHANNEL_JOINED")
        )
        log.l("Joined %s" % (channel,))
    
    def left(self, channel):
        del database.user[self.user].master.server[self.server]\
        .channels[channel]
        log.l("Left %s" % (channel,))
    
    def privmsg(self, user, channel, msg):
        if channel not in database.user[self.user].master.server[self.server]\
        .channels.keys():
        #    database.user[self.user].master.server[self.server]\
        #    .channels[channel] = Channel()
            self.joined(channel)
            
        chan = database.user[self.user].master.server[self.server]\
        .channels[channel]
        
        message = data.Message(self.server, channel, user, msg)
        highlighted = database.user[self.user].master.events
        
        for highlight in chan.highlights:
            if highlight.lower() in msg.lower():
                highlighted.append(data.Event(self.server, channel, user, msg,\
                "highlight"))
                
        if self.nickname.lower() in msg.lower() \
        or database.user[self.user].master.server[self.server].nick.lower() in \
        msg.lower():
            highlighted.append(data.Event(self.server, channel, user, msg,\
            "highlight"))
            
        if len(highlighted) > int(config.CHAT_BUFFER/10):
            highlighted = highlighted[:-int(config.CHAT_BUFFER/10)]
        chan.messages.append(message)
        if len(chan.messages) > config.CHAT_BUFFER:
            chan.messages = chan.messages[:-config.CHAT_BUFFER]

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

def reconnect(user,server,nick):
    connections[user+'_'+server] = IRCFactory(user, server, nick)
    reactor.connectTCP(server, 6667, connections[user+'_'+server])

def rejoin(user,server,channel):
    connections[user+'_'+server].irc.join(channel)

def restore():
    for user in database.user:
        for server in database.user[user].master.server:
            nick = database.user[user].master.server[server].nick
            reconnect(user,server,nick)   

if __name__ == '__main__':
    log.l("Yes, this is dog")
    
    database = data.get()
    
    for user in config.ADMINS:
        try:
            database.user[user].admin = True
            log.l("Made user %s an admin" % (user,))
        except KeyError:
            log.l("Failed to set %s to admin - user doesn't exist yet."\
                   % (user,))
    
    root = Page()
    root.putChild('saveDB',SaveDB())
    root.putChild('info',Info())
    root.putChild('server',IRCServer())
    root.putChild('channel',Channel())
    root.putChild('events',Events())
    root.putChild('register',Registration())
    root.putChild('eval',Eval())
    
    site = Site(root)

    restore()

    lc = LoopingCall(save_data).start(60)
    
    reactor.listenTCP(8080, site)
    reactor.run()
    
    log.l("Twisted Reactor shutdown, saving database")
    database.save()