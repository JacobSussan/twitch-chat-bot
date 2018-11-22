# twitch-chat-bot

## Setup
1) Create the database
2) Edit config.py

	2.1) bot_name: the username of the bot account
	
	2.2) client_id: your applications client id - https://glass.twitch.tv/console/apps
	
	2.3) oauth: token without "oath:" - https://twitchapps.com/tmi
	
	2.4) channel_name: the username of the chat the bot should connect to
	
3) Run chatbot.py with python3

## Features

### Implimented

- Log all messages posted in chat
- Points System: users get points for watching the stream and being in chat
- !game: display game
- !title: display title
- !gamble: tell the viewers what they need to know about gambling
- !points: display how many points a user has
- !uptime: display how long the stream has been live
- !followage: display how long a user has been following the stream

### On the roadmap
- commands that just respond text from database (ex: !ping says: "pong")
- notices that get put in chat every x minutes.
- counters (ie: this command has been used x times)
- songrequests (youtube and spoitify?)
- let mods change game or title from chat
- betting system (who will win this game?)
- poll system
- points ranks (!top - show users with the most points)
- check someone elses points or followage
- blacklist users

### To think about
- should time be time watched when live or time spent in chat (off and online)