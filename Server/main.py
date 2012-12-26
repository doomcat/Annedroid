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
            
            if a['message'].startswith('/me '):
                func = connections[a['user']+'_'+a['server']].irc.me
            else:
                func = connections[a['user']+'_'+a['server']].irc.msg
                
            func(a['channel'], a['message'])

            if a['channel'].startswith('#') or a['channel'].startswith('&'):
                channel = a['channel']
            else:
                channel = a['user']
                
            connections[a['user']+'_'+a['server']].irc\
            .privmsg(nick,channel,a['message'])
            
            return '{"message": "s:SENT"}'
    
    def __init__(self):
        Resource.__init__(self)
        self.putChild('connect',self.Connect())
        self.putChild('disconnect',self.Disconnect())
        self.putChild('join',self.Join())
        self.putChild('leave',self.Leave())
        self.putChild('message',self.Message())
    
class KeepAlive(Page):
    def messages_str(self, messages):
        out = '{"messages": [\n'
        for message in messages:
            out += to_json_simple(message)+',\n'
        out = out[:-2]+'\n]}'
            
        return out
    
    def message_provider(self, request):
        a = request.a
        return database.user[a['user']].master.server[a['server']]\
        .channels[a['channel']].messages
    
    def messages_get(self, request):
        a = request.a
        messages = self.message_provider(request)
            
        if 'last_checked' in a.keys():
            if a['last_checked'] is not '':
                t = float(a['last_checked'])
                return [m for m in messages if (m.timestamp > t)]
            
        return messages
            
    def run_loop(self, request):
        messages = self.messages_get(request)
        
        if len(messages) == 0:
            deferLater(reactor, 1, self.run_loop, request)
            return NOT_DONE_YET
        else:
            request.write(self.messages_str(messages))
            request.finish()
            return
            
    def run(self, request):
        messages = self.messages_get(request)
            
        if len(messages) == 0:
            deferLater(reactor, 1, self.run_loop, request)
            return NOT_DONE_YET
        else:
            return self.messages_str(messages)
        
class Channel(Page):
    def run(self, request):
        a = request.a
        messages = database.user[a['user']].master.server[a['server']]\
        .channels[a['channel']].messages
        
        out = '{"messages": [\n'
        for message in messages:
            out += to_json_simple(message)+',\n'
        out = out[:-2]+'\n]}'
        return out
        
    class New(KeepAlive):
        pass

    def __init__(self):
        Page.__init__(self)
        self.putChild('new', self.New())

class Events(KeepAlive):
    def message_provider(self, request):
        a = request.a
        return database.user[a['user']].master.events

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
            data.Event(self.server, channel, self.nickname, None, "CHANNEL_JOINED")
        )
        log.l("Joined %s" % (channel,))
    
    def join(self, channel):
        if channel.startswith('#') or channel.startswith('&'):
            irc.IRCClient.join(self, channel)
        
    def left(self, channel):
        del database.user[self.user].master.server[self.server]\
        .channels[channel]
        log.l("Left %s" % (channel,))
    
    def privmsg(self, user, channel, msg):
        addToEvents = False
        c = channel
        if database.user[self.user].master.server[self.server].nick\
        is channel or connections[self.user+'_'+self.server].nickname\
        is channel:
            c = user
            addToEvents = True
            eType = "PRIVMSG"
        if channel not in database.user[self.user].master.server[self.server]\
        .channels.keys():
            self.joined(c)
            
        chan = database.user[self.user].master.server[self.server]\
        .channels[c]
        
        if msg.startswith('/me '):
            message = data.Event(self.server, c, user, msg[4:], "ACTION")
        else:
            message = data.Message(self.server, c, user, msg)
        
        highlighted = database.user[self.user].master.events
        highlights = []
        highlights.extend(chan.highlights)
        highlights.extend(database.user[self.user].master.highlights)
        for highlight in highlights:
            if highlight.lower() in msg.lower():
                addToEvents = True
                eType = "HIGHLIGHT"
        if self.nickname.lower() in msg.lower() \
        or database.user[self.user].master.server[self.server].nick.lower() in \
        msg.lower():
            addToEvents = True
            eType = "HIGHLIGHT"
            
        if len(highlighted) > int(config.CHAT_BUFFER/10):
            highlighted = highlighted[:-int(config.CHAT_BUFFER/10)]
        chan.messages.append(message)
        
        if addToEvents is True:
            event = data.Event(self.server, c, user, message.message, eType)
            highlighted.append(event)
        
        if len(chan.messages) > config.CHAT_BUFFER:
            chan.messages = chan.messages[-config.CHAT_BUFFER:]
            
    def action(self, user, channel, data):
        self.privmsg(user, channel, "/me "+data)
        
    def receivedMOTD(self, motd):
        database.user[self.user].master.server[self.server].motd\
        = '\n'.join(motd)
        
    def topicUpdated(self, user, channel, newTopic):
        database.user[self.user].master.server[self.server].channels[channel]\
        .topic = newTopic
        event = data.Event(self.server, channel, user, newTopic, "NEW_TOPIC")
        database.user[self.user].master.server[self.server].channels[channel]\
        .messages.append(event)
        database.user[self.user].master.events.append(event)

    def userRenamed(self, user, oldName, newName):
        event = data.Event(self.server, None, oldName, newName, "NAME_CHANGED")
        database.user[self.user].master.events.append(event)

    def userJoined(self, user, channel):
        event = data.Event(self.server, channel, user, None, "JOINED")
        database.user[self.user].master.server[self.server].channels[channel]\
        .messages.append(event)
        database.user[self.user].master.events.append(event)
        
    def userLeft(self, user, channel):
        event = data.Event(self.server, channel, user, None, "LEFT")
        database.user[self.user].master.server[self.server].channels[channel]\
        .messages.append(event)
        database.user[self.user].master.events.append(event)
        
    def userQuit(self, user, quitMsg):
        event = data.Event(self.server, None, user, quitMsg, "QUIT")
        database.user[self.user].master.events.append(event)
        
    def userKicked(self, kickee, channel, kicker, message):
        event = data.Event(self.server, channel, kickee, kicker, "OTHER_KICKED")
        database.user[self.user].master.server[self.server].channels[channel]\
        .messages.append(event)
        database.user[self.user].master.events.append(event)

    def kickedFrom(self, channel, kicker, message):
        event = data.Event(self.server, channel, kicker, message, "SELF_KICKED")
        database.user[self.user].master.server[self.server].channels[channel]\
        .messages.append(event)
        database.user[self.user].master.events.append(event)

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
        p.versionName = config.CTCP_VERSION_NAME
        p.versionNum = config.VERSION
        p.versionEnv = ''
        
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
    
    site = Site(root)

    restore()

    lc = LoopingCall(save_data).start(config.SAVE_RATE)
    
    reactor.listenTCP(config.PORT, site)
    reactor.run()
    
    log.l("Twisted Reactor shutdown, saving database")
    database.save()