'''Configuration stuff'''

PORT = 8081 # what port to run the HTTP server on

VERSION = 'pre-alpha'
SAVE_RATE = 180 # interval between each database save, in seconds
GARBAGE_COLLECT_RATE = 60 # interval between GC runs, in seconds (not python gc)
DEFAULT_NICK = "TestUser_"
DEFAULT_NICK_I = 0
ADMINS = ['owain'] # what usernames have admin capability
CHAT_BUFFER = 1000 # how many lines of chat to buffer per conversation
CTCP_VERSION_NAME = "Annedroid/Server [https://github.com/doomcat/Annedroid]"
URL = "http://annedroid.slashingedge.co.uk" # where is this server running?

TEST_NO_IRC = False	# if you are developing and don't want to keep
		   	# (dis)connecting from servers and annoying people, you
			# can disable the actual IRC part. the database won't be
			# cleared, allowing you to test the HTTP part.
