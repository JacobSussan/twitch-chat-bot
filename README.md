# twitch-chat-bot

## Setup
0) Install dependencies
	- irc
	- pafy & python-vlc if you want to enable media requests
1) Create the databases
2) Edit config.py
	2.1) bot_name: the username of the bot account
	
	2.2) client_id: your applications client id - https://glass.twitch.tv/console/apps
	
	2.3) oauth: token without "oath:"
	
	Get it from: https://twitchapps.com/tmi ON THE BOT ACCOUNT
	
	2.4) channel_oauth: token without "oath:" Enable "channel_editor" from: https://twitchtokengenerator.com/ and click "generate token" ON THE CHANNEL ACCOUNT
	2.5) channel_name: the username of the chat the bot should connect to
	
	2.6) timezone
	
	2.7) True or False - media requests allow viewers to request songs to be played on stream
	
	2.8) max length of the video requested for it to be added
	
	2.9) min views of the video requested for it to be added
	
3) Run chatbot.py with python3

## Features

### Implimented

- Log all messages posted in chat
- custom commands (ex: !ping says: "pong")
	- !addcommand command response
	- !delcommand command
	- {name} replace with the name of the user who issued the command
	- {counter} replace with number of times the command has been used, for example: "streamer has !died 15 times"
	- !setcounter command number - !setcounter died 0
- !game: display or change game - "!game Minecraft" will change the game to Minecraft, "!game" will display the current game
- !title: display or change title - "!title join!" will change the title to "join!", "!title" will display the current title
- !gamble: tell the viewers what they need to know about gambling
- !points or !p: display how many points a user has
- !uptime: display how long the stream has been live
- !followage: display how long a user has been following the stream
- rank system:
	- !rank - display your own rank
	- !rank user - display the rank of "user"
	- !rank user mod - change the rank of "user" to "mod"
- !top - show the 5 users with the most points
- poll system
	- !poll option1, option2, etc - create a poll
	- !vote option - vote on a poll
	- !results - show and clear results
- betting system
	- !createbet multiplier option1, option2, etc
	- !bet amount option
	- !endbet option - end the bet and give people who bet on "option" points based on how much they bet and the multiplier
- !lastseen user: display the last time "user" was seen watching the stream
- notices - frequency and offset in minutes, offsets are to stop all notices from posting at the same time. Checked every minute when the stream is online, every 10 minutes when the stream is offline
	- !addnotice frequency offset notice_text - !addnotice 60 10 follow my twitter!  --  will post "follow my twitter" in chat every 60 minutes, starting 10 minutes after the bot starts.
	- !delnotice notice_text - delete the notice that matches "notice_text"
- duels
	- !duel name ammount
	- !duel accept
	- !duel deny
	- !duel cancel
- songrequests (youtube)
	- !playlist or !pl			- Display the last, current, and next songs
	- !sr or !songrequest		- Request a song
	- !skip						- Skip the current song
	- !volume					- Change the volume (0-100)
	- !default					- Add a song to the defualt playlist
	- !pause
	- !resume
