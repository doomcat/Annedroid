#!/bin/bash

#pw=`echo hunter2 | sha256sum | cut -d ' ' -f 1`
pw=f52fbd32b2b3b86ff88ef6c490628285f482af15ddcb29541f94bcf526a3f6c7
last_checked=0
args="user=owain&token=$pw&ctime=&server=irc.aberwiki.org&channel=#42&last_checked=$last_checked&wait=true"

while true; do
	echo $args
	curl --data $args http://localhost:8081/channel/new | while read line; do
		last_checked=`echo $line | cut -d '"' -f 3 | cut -d ' ' -f 2`
	done
	args="user=owain&token=$pw&ctime=&server=irc.aberwiki.org&channel=#42&last_checked=$last_checked&wait=true"

	echo
	sleep 1
done
