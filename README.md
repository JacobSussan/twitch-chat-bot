# twitch-chat-bot

## Setup
1) Create the database
2) Edit config.py

	2.1) bot_name: the username of the bot account
	
	2.2) client_id: your applications client id - https://glass.twitch.tv/console/apps
	
	2.3) oauth: token without "oath:"
	Get it from: https://twitchapps.com/tmi ON THE BOT ACCOUNT
	
	2.4) channel_oauth: token without "oath:"
	Enable "channel_editor" from: https://twitchtokengenerator.com/ and click "generate token" ON THE CHANNEL ACCOUNT

	2.5) channel_name: the username of the chat the bot should connect to
	
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
- let mods change game or title from chat
- give users a rank
- check your own or another viewers rank
- points ranks (!top - show users with the most points)
- commands that just respond text from database (ex: !ping says: "pong")
- poll system
	- !poll option1, option2, etc
	- !vote option
	- !results
- betting system
	- !createbet multiplier option1, option2, etc
	- !bet amount option
	- !endbet option

### On the roadmap

- notices that get put in chat every x minutes.
- counters (ie: this command has been used x times)
- songrequests (youtube and spoitify?)

### To think about
- should time be time watched when live or time spent in chat (off and online)