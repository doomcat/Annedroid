#!/usr/bin/python -OO
# -*- coding: utf-8 -*-
'''
@author: Owain Jones [odj@aber.ac.uk]
'''

import data, jsonpickle, json, re
from logger import Logger
from twisted.words.protocols import irc
from twisted.internet import protocol, reactor
from twisted.web.server import Site, NOT_DONE_YET
from twisted.web.resource import Resource
from twisted.internet.task import LoopingCall, deferLater
from time import time, sleep
from hashlib import sha256
from itertools import izip, cycle

url_regex = re.compile(r"""((?:[a-z][\w-]+:(?:/{1,3}|[a-z0-9%])|www\d{0,3}[.]|[a-z0-9.\-]+[.‌​][a-z]{2,4}/)(?:[^\s()<>]+|(([^\s()<>]+|(([^\s()<>]+)))*))+(?:(([^\s()<>]+|(‌​([^\s()<>]+)))*)|[^\s`!()[]{};:'".,<>?«»“”‘’]))""", re.DOTALL)

import config

global database, log, connections
database = None
log = Logger()
connections = {}

def xor_crypt_string(data, key):
    return ''.join(chr(ord(x) ^ ord(y)) for (x,y) in izip(data, cycle(key)))

def generate_cookie(user):
    t = str(time())
    return str(sha256(t).hexdigest())
    
def add_user_to_channel(dbuser,server,channel,user):
    user = user.split('!')[0]
    try:
        database.user[dbuser].master.server[server].channels[channel]\
        .users.add(user)
    except Exception as e:
        log.l(e)

def remove_user_from_channel(dbuser,server,channel,user):
    user = user.split('!')[0]
    try:
        database.user[dbuser].master.server[server].channels[channel]\
        .users.discard(user)
    except Exception as e:
        log.l(e)

def to_json(object):
    return str(jsonpickle.encode(object))

def to_json_simple(object):
    try:
        return json.dumps(object.__dict__)
    except Exception as e:
        log.l(e)
        return '{}'

def sync_time(client_time,timestamp):
    '''Synchronize a timestamp between client & server'''
    delta = int(time())-int(client_time)
    return int(timestamp)+delta

def parse_args(request):
    out = {}
    for arg in request.args:
    	out[arg] = request.args[arg][0]
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
                client_hash = request.args['token'][0]
                server_hash = database.user[username].cookie
                if client_hash == server_hash:
                    request.a = parse_args(request)
                    return self.run(request)
                
                return self.error(request)
            except KeyError:
                return self.error(request)
        else:
            return self.run(request)
    
#    def render_GET(self, request):
#            return self.render_POST(request)

    render_GET = render_POST
    
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
	database.user[username].cookie = generate_cookie(username)
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

class Registration42(Registration):
    def run(self, request):
        Registration.run(self, request)
        request.args['server'] = ['irc.aberwiki.org']
	request.args['user'] = request.args['username']
	request.args['ctime'] = ['lol_buttes']
	request.args['token'] = [str(sha256('lol_buttes'+request.args['password'][0]).hexdigest())]
	request.args['channel'] = ["#42"]
	request.a = parse_args(request)
	i = IRCServer.Connect()
	i.run(request)
	connections[request.args['user'][0]+'_'+'irc.aberwiki.org'].irc.join('#42')
	request.setHeader('Location','/login.php')
	return "Registered, connected and joined #42. Go back to /login.php"

class Auth(Page):
    needsAuth = False
    def run(self, request):
        if 'username' in request.args.keys()\
        and 'password' in request.args.keys():
            username = request.args['username'][0]
            password = request.args['password'][0]
        else:
            return '{"error": "s:BAD_AUTH"}'

        if username in database.user.keys()\
	and database.user[username].password == password:
	    if database.user[username].cookie == None\
	    or 'reauth' in request.args.keys():
	        cookie = generate_cookie(username)
	        database.user[username].cookie = cookie
            else:
                cookie = database.user[username].cookie
            return '{"cookie": "%s"}' % (cookie,)
	else:
	    return '{"error": "s:BAD_AUTH"}'

class IRCServer(Resource):
    class Nick(Page):
        def run(self, request):
            a = request.a
            if 'nick' in a.keys() and a['nick'] != '':
                connections[a['user']+'_'+a['server']].irc.setNick(a['nick'])
            return '{"nick": "%s"}'\
            % (connections[a['user']+'_'+a['server']].nickname,)
            
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
		connections[a['user']+'_'+a['server']].setNick(a['nick'])
                
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
	    IRCServer.Connect().run(request)
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
            try:
		if database.user[a['user']].readonly == True: return '{"error": "s:PERMISSION_DENIED"}'
	    except AttributeError:
	        pass
            nick = connections[a['user']+'_'+a['server']].irc.nickname
            args = 2
	    cmd = False
            
            if a['message'].startswith('/me '):
                func = connections[a['user']+'_'+a['server']].irc.me
                a['message'] = a['message'][4:]
		cmd = True
            elif a['message'].startswith('/nick '):
                func = connections[a['user']+'_'+a['server']].irc.setNick
                a['message'] = a['message'][6:]
		cmd = True
            elif a['message'].startswith('/away'):
                func = connections[a['user']+'_'+a['server']].irc.away
                a['message'] = a['message'][5:]
                args = 1
		cmd = True
            elif a['message'].startswith('/back'):
                func = connections[a['user']+'_'+a['server']].irc.back
                args = 0
		cmd = True
            else:
                func = connections[a['user']+'_'+a['server']].irc.msg
                
            if args == 2:
                func(a['channel'], a['message'])
            elif args == 1:
                func(a['message'])
            else:
                func()

            if a['channel'].startswith('#') or a['channel'].startswith('&'):
                channel = a['channel']
            else:
                channel = a['user']
                
	    if cmd is True:
		connections[a['user']+'_'+a['server']].irc\
		.privmsg(nick+'!self',channel,request.args['message'][0])
	    else:
                connections[a['user']+'_'+a['server']].irc\
                .privmsg(nick+'!self',channel,a['message'])
            
            return '{"message": "s:SENT"}'
    
    def __init__(self):
        Resource.__init__(self)
        self.putChild('connect',self.Connect())
        self.putChild('disconnect',self.Disconnect())
        self.putChild('join',self.Join())
        self.putChild('leave',self.Leave())
        self.putChild('message',self.Message())
        self.putChild('nick',self.Nick())
    
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
    
    def messages_get(self, request, limit=0):
        a = request.a
	before = False
        messages = self.message_provider(request)
	if 'before' in a.keys() and (a['before'] == True or a['before'].lower() == 'true'):
		before = True
            
        if 'last_checked' in a.keys():
            if a['last_checked'] is not '':
                t = float(a['last_checked'])
		if before == True:
			out = [m for m in messages if(m.timestamp < t)]
		else:
	                out = [m for m in messages if (m.timestamp > t)]
                if limit != 0 and len(out) > limit:
                    return out[-limit:]
                return out
            
        return messages
            
    def run_loop(self, request):
        limit = 0
        if 'limit' in request.a.keys():
            limit = int(request.a['limit'])

        messages = self.messages_get(request,limit)

        if len(messages) == 0:
            deferLater(reactor, 1, self.run_loop, request)
            return NOT_DONE_YET
        else:
            request.write(self.messages_str(messages))
            request.finish()
            request.notifyFinish()
            #return
            
    def run(self, request):
        limit = 0
        if 'limit' in request.a.keys():
            limit = int(request.a['limit'])        
            
        messages = self.messages_get(request,limit)

        if len(messages) == 0 and 'wait' in request.a.keys()\
        and request.a['wait'] in [True, 'true', 'True']:
            deferLater(reactor, 1, self.run_loop, request)
            return NOT_DONE_YET
        else:
            return self.messages_str(messages)

class ConfigureList(Page):
    def get_list(self, request):
        pass
    
    def set_list(self, request):
        list = self.get_list(request)
        list.clear()
        if request.a['message'] == ' ': return
        for item in request.a['message'].split(' '):
            list.add(item)
    
    def print_list(self, request):
        out = '{"list": [\n'
        list = self.get_list(request)
        if len(list) == 0:
            return '{"list": []}'
        for word in list:
            out += '"%s",\n' % (word,)
        out = out[:-2]+'\n]}'
        return out
    
    def run(self, request):
        a = request.a
        if 'message' in a.keys() and a['message'] != '':
            self.set_list(request)
            return '{"message": "s:LIST_SET"}'
        else:
            return self.print_list(request)
        
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

    class Topic(Page):
	def run(self, request):
		a = request.a
		topic = database.user[a['user']].master.server[a['server']]\
		.channels[a['channel']].topic

		return '{"topic": "%s"}' % (topic,)

    class Highlights(ConfigureList):
        def get_list(self, request):
            a = request.a
            return database.user[a['user']].master.server[a['server']]\
            .channels[a['channel']].highlights
            
    class Blocked(ConfigureList):
        def get_list(self, request):
            a = request.a
            return database.user[a['user']].master.server[a['server']]\
            .channels[a['channel']].blocked

    class Ignore(ConfigureList):
        def get_list(self, request):
            a = request.a
            return database.user[a['user']].master.server[a['server']]\
            .channels[a['channel']].ignore

    class Users(ConfigureList):
        def get_list(self, request):
            a = request.a
            return database.user[a['user']].master.server[a['server']]\
            .channels[a['channel']].users

        def set_list(self, request):
            pass

    class Clear(Page):
        def run(self, request):
            a = request.a
            if 'clear' in a.keys()\
            and (a['clear'] is True or a['clear'] == 'true'):
                database.user[a['user']].master.server[a['server']]\
                .channels[a['channel']].messages = []
	    return '{"status": "cleared"}'

    def __init__(self):
        Page.__init__(self)
	self.putChild('topic',self.Topic())
        self.putChild('new', self.New())
        self.putChild('highlights', self.Highlights())
        self.putChild('blocked', self.Blocked())
        self.putChild('ignore', self.Ignore())
        self.putChild('users', self.Users())
        self.putChild('clear', self.Clear())

class Events(KeepAlive):
    def message_provider(self, request):
        a = request.a
        return database.user[a['user']].master.events

class Highlights(ConfigureList):
    def get_list(self, request):
        a = request.a
        return database.user[a['user']].master.highlights

class Blocked(ConfigureList):
    def get_list(self, request):
        a = request.a
        return database.user[a['user']].master.blocked

class Ignore(ConfigureList):
    def get_list(self, request):
        a = request.a
        return database.user[a['user']].master.ignore

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

class Search(Page):
    isLeaf = True
    def run(self, request):
        user = request.a['user']
        nick = ''
        words = []
        events = []
        server = ''
        channel = ''
	urls = False

        if 'nick' in request.a.keys():
            nick = request.a['nick']
        if 'words' in request.a.keys() and request.a['words'] != '':
            words = request.a['words'].split(' ')
        if 'events' in request.a.keys() and request.a['events'] != '':
            events = request.a['events'].split(' ')
        if 'server' in request.a.keys():
            server = request.a['server']
        if 'channel' in request.a.keys():
            channel = request.a['channel']
	if 'urls' in request.a.keys()\
	and (request.a['urls'] == True or request.a['urls'].lower() == 'true'):
	    urls = True

        if nick is '' and words is [] and events is []:
            return '{"results": []}'

        results = set()

        for s in database.user[user].master.server:
            for c in database.user[user].master.server[s]\
            .channels:
                for msg in database.user[user].master.server[s]\
                .channels[c].messages:
		    if not urls:
                        if self.is_result(msg, nick, words, events):
                            results.add(msg)
                    else:
                        if self.has_url(msg):
                            results.add(msg)
                        
        for e in database.user[user].master.events:
            if not urls:
                if self.is_result(e, nick, words, events):
                    results.add(e)
            else:
                if self.has_url(e):
                    results.add(e)

        if len(results) == 0:
            return '{"results": []}'

        out = '{"results": [\n'
        for r in results:
            out += to_json_simple(r)+',\n'
        out = out[:-2]+'\n]}'

        return out

    def is_result(self, msg, nick, words, events):
	add = 0
	if len(nick) > 1 and msg.nick.lower().startswith(nick.lower()):
		add += 1
	if words != []:
		if msg.message != None:
			for word in words:
				if word != ''\
				and word.lower() in msg.message.lower():
					add += 1
		else:
			add -= 1
	if events != []:
		if 'event' in msg.__dict__.keys() and msg.event != None:
			for event in events:
				if event != ''\
				and event.lower() in msg.event.lower():
					add += 1
		else:
			add -= 1
	if add > 0: return True
	return False

    def has_url(self, msg):
        if msg.message != None:
            return url_regex.search(msg.message)
        return False

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
    #nickname = property(_get_nickname)
    server = property(_get_server)
    user = property(_get_user)

    def signedOn(self):
        log.l("%s signed onto %s as %s" % (self.user,self.server,self.nickname,))
        for channel in database.user[self.user].master.server[self.server]\
        .channels:
            rejoin(self.user,self.server,channel)
        
    def joined(self, channel):
	if channel not in \
	database.user[self.user].master.server[self.server].channels.keys():
	    database.user[self.user].master.server[self.server]\
	    .channels[channel] = data.Channel()
        database.user[self.user].master.events.append(
            data.Event(self.server, channel, self.nickname, None, "CHANNEL_JOINED")
        )
        add_user_to_channel(self.user, self.server, channel, self.nickname)
        log.l("%s joined %s on %s" % (self.user,channel,self.server))
    
    def join(self, channel):
        if channel.startswith('#') or channel.startswith('&'):
            irc.IRCClient.join(self, channel)
        
    def left(self, channel):
        del database.user[self.user].master.server[self.server]\
        .channels[channel]
        log.l("%s left %s on %s" % (self.user,channel,self.server))
    
    def privmsg(self, user, channel, msg):
	msg = msg.decode('utf-8')
        addToEvents = False
	highlight = ''
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
        
        add_user_to_channel(self.user, self.server, c, user)
        
        if user.endswith('!self') is False:
            ignore = database.user[self.user].master.ignore
            ignore = ignore.union(database.user[self.user].master\
                        .server[self.server].channels[channel].ignore)
            for u in ignore:
                if u.lower() is user.lower().split('!')[0]:
                    return
                
            blocked = database.user[self.user].master.blocked
            blocked = blocked.union(database.user[self.user].master\
                        .server[self.server].channels[channel].blocked)
            for word in blocked:
                if word.lower() in msg.lower():
                    return
            
        if user.endswith('!self') is False:
            highlighted = database.user[self.user].master.events
            highlights = []
            highlights.extend(chan.highlights)
            highlights.extend(database.user[self.user].master.highlights)
            for h in highlights:
                if h.lower() in msg.lower():
                    addToEvents = True
                    highlight += h+' '
            if self.nickname.lower() in msg.lower() \
            or database.user[self.user].master.server[self.server].nick.lower()\
            in msg.lower():
                addToEvents = True
                highlight += self.nickname.lower()+' '

        if msg.startswith('/me '):
            message = data.Event(self.server, c, user, msg[4:], "ACTION", highlight)
        else:
            message = data.Message(self.server, c, user, msg, highlight)
                    
        if addToEvents is True:
            highlighted.append(message)

        chan.messages.append(message)
            
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
        add_user_to_channel(self.user, self.server, channel, user)

    def userRenamed(self, user, oldName, newName):
        event = data.Event(self.server, None, oldName, newName, "NAME_CHANGED")
        database.user[self.user].master.events.append(event)
        remove_user_from_channel(self.user, self.server, channel, oldName)
        add_user_to_channel(self.user, self.server, channel, newName)

    def userJoined(self, user, channel):
        event = data.Event(self.server, channel, user, None, "JOINED")
        database.user[self.user].master.server[self.server].channels[channel]\
        .messages.append(event)
        database.user[self.user].master.events.append(event)
        add_user_to_channel(self.user, self.server, channel, user)
        
    def userLeft(self, user, channel):
        event = data.Event(self.server, channel, user, None, "LEFT")
        database.user[self.user].master.server[self.server].channels[channel]\
        .messages.append(event)
        database.user[self.user].master.events.append(event)
        remove_user_from_channel(self.user, self.server, channel, user)
        
    def userQuit(self, user, quitMsg):
        event = data.Event(self.server, None, user, quitMsg, "QUIT")
        database.user[self.user].master.events.append(event)
        
    def userKicked(self, kickee, channel, kicker, message):
        event = data.Event(self.server, channel, kickee, kicker, "OTHER_KICKED")
        database.user[self.user].master.server[self.server].channels[channel]\
        .messages.append(event)
        database.user[self.user].master.events.append(event)
        remove_user_from_channel(self.user, self.server, channel, user)

    def kickedFrom(self, channel, kicker, message):
        event = data.Event(self.server, channel, kicker, message, "SELF_KICKED")
        database.user[self.user].master.server[self.server].channels[channel]\
        .messages.append(event)
        database.user[self.user].master.events.append(event)
        remove_user_from_channel(self.user, self.server, channel, self.nickname)

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
    if config.TEST_NO_IRC == True: return
    for user in database.user:
        for server in database.user[user].master.server:
            nick = database.user[user].master.server[server].nick
            reconnect(user,server,nick)   

def garbage_collect():
    if config.CHAT_BUFFER == -1: return
    objects = 0
    for user in database.user:
        for server in database.user[user].master.server:
            for channel in database.user[user].master.server[server].channels:
                c = database.user[user].master.server[server].channels[channel]
                l = len(c.messages)
                if l > int(config.CHAT_BUFFER):
                    database.user[user].master.server[server].channels[channel]\
			.messages = database.user[user].master.server[server].\
			channels[channel].messages[-int(config.CHAT_BUFFER):]
                    objects += (l-len(c.messages))
        m = database.user[user].master.events
        l = len(m)
        if l > int(config.CHAT_BUFFER):
            database.user[user].master.events\
             = database.user[user].master.events[-int(config.CHAT_BUFFER):]
            objects += (l-len(m))
    log.l("Garbage Collection run: %s objects cleared." % (objects,))

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

    for user in config.READONLY:
        try:
            database.user[user].readonly = True
            log.l("Made user %s readonly" % (user,))
        except KeyError:
            log.l("Failed to make %s readonly - user doesn't exist yet."\
                   % (user,))
    
    root = Page()
    root.putChild('saveDB',SaveDB())
    root.putChild('info',Info())
    root.putChild('server',IRCServer())
    root.putChild('channel',Channel())
    root.putChild('events',Events())
    root.putChild('register',Registration())
    root.putChild('auth',Auth())
    root.putChild('highlights',Highlights())
    root.putChild('ignore',Ignore())
    root.putChild('blocked',Blocked())
    root.putChild('register42',Registration42())    
    root.putChild('search',Search())
    site = Site(root)

    restore()

    lc = LoopingCall(save_data).start(config.SAVE_RATE)
    if config.CHAT_BUFFER != 0:
        gc = LoopingCall(garbage_collect).start(config.GARBAGE_COLLECT_RATE)
    
    reactor.listenTCP(config.PORT, site)
    reactor.run()
    
    log.l("Twisted Reactor shutdown, saving database")
    database.save()
