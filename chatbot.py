import sys
import irc.bot
import requests
import config
import sqlite3
import datetime
from datetime import timedelta
from threading import Thread
import time
from requests.utils import quote
from pytz import timezone
import random
if config.SETTINGS['enable_media_requests']:
	import pafy
	import vlc

class TwitchBot(irc.bot.SingleServerIRCBot):
	def __init__(self, username, client_id, token, channel_oauth, channel, conn, timezone):
		self.client_id = client_id
		self.token = token
		self.channel_oauth = channel_oauth
		self.channel = channel
		self.irc_channel = "#" + channel
		self.conn = conn
		self.cursor = conn.cursor()
		self.timezone = timezone
		self.duels = []

		# Get the channel id, we will need this for v5 API calls
		url = 'https://api.twitch.tv/kraken/users?login=' + channel
		headers = {'Client-ID': client_id, 'Accept': 'application/vnd.twitchtv.v5+json'}
		r = requests.get(url, headers=headers).json()
		self.channel_id = r['users'][0]['_id']

		# Create IRC bot connection
		server = 'irc.chat.twitch.tv'
		port = 6667
		print ('Connecting to ', server, ' on port ', str(port), '...')
		irc.bot.SingleServerIRCBot.__init__(self, [(server, port, 'oauth:'+token)], username, username)

	def on_welcome(self, c, e):
		print ('Joining ', self.channel)

		# You must request specific capabilities before you can use them
		c.cap('REQ', ':twitch.tv/membership')
		c.cap('REQ', ':twitch.tv/tags')
		c.cap('REQ', ':twitch.tv/commands')
		c.join(self.irc_channel)

		# call tick() from another thread so it can run at the same time
		thread = Thread(target=self.tick, args=(c,))
		thread.start()
		
		if config.SETTINGS['enable_media_requests']:
			thread = Thread(target=self.processMediaRequests, args=(c,))
			thread.start()

	def on_pubmsg(self, c, e):
		# Convert the json from twitch into a dict
		d = { i['key'] : i['value'] for i in e.tags }

		# Insert message into database (logs)
		self.cursor.execute("INSERT INTO log VALUES (?, ?, ?)", (d['display-name'], e.arguments[0], d['tmi-sent-ts'],))
		self.conn.commit()

		# If a chat message starts with an exclamation point, try to run it as a command
		if e.arguments[0][:1] == '!':
			cmd = e.arguments[0].split(' ')[0][1:]
			print ('Received command: ', cmd)
			self.do_command(e, cmd)
		return

	def do_command(self, e, cmd):
		c = self.connection

		# Check the database for custom commands
		self.cursor.execute("SELECT command, response, counter FROM commands")
		for command in self.cursor.fetchall():
			if (command[0] == cmd):
				# Update counter
				self.cursor.execute("UPDATE commands SET counter = counter + 1 WHERE command=?", (command[0],))
				self.conn.commit()

				# Replace {name} with the user who issued the command
				commandText = command[1].replace("{name}", e.tags[2]['value'])
				# Replace {counter}
				commandText = commandText.replace("{counter}", str(command[2] + 1))

				c.privmsg(self.irc_channel, commandText)
	
		# Add custom commands
		if cmd == "addcommand":
			if len(e.arguments[0].split(' ', 2)) == 3:
				new_cmd = e.arguments[0].split(' ', 2)[1][0:]
				response = e.arguments[0].split(' ', 2)[2][0:]
				try:
					self.cursor.execute("INSERT INTO commands VALUES (?, ?, 0)", (new_cmd, response,))
					self.conn.commit()
					c.privmsg(self.irc_channel, "Command !" + new_cmd + " was added!")
				except:
					c.privmsg(self.irc_channel, "Command !" + new_cmd + " was NOT added, maybe it already exists?")
		
		# Delete custom commands
		elif cmd == "delcommand":
			if len(e.arguments[0].split(' ', 1)) == 2:
				command_to_remove = e.arguments[0].split(' ', 1)[1][0:]
				self.cursor.execute("DELETE FROM commands WHERE command=?", (command_to_remove,))
				self.conn.commit()
				c.privmsg(self.irc_channel, "Command !" + command_to_remove + " was removed!")

		# Set counter for a custom command
		elif cmd == "setcounter":
			if len(e.arguments[0].split(' ', 2)) == 3:
				command = e.arguments[0].split(' ', 2)[1][0:]
				counter = e.arguments[0].split(' ', 2)[2][0:]
				self.cursor.execute("UPDATE commands SET counter = ? WHERE command=?", (counter, command, ))
				self.conn.commit()
				c.privmsg(self.irc_channel, "Command !" + command + " had its counter set to " + counter)
		
		# Poll the API to get current game.
		elif cmd == "game":
			# Set the game
			if len(e.arguments[0].split(' ', 1)) == 2:
				new_game = e.arguments[0].split(' ', 1)[1][0:]
				if self.isMod(e.tags[2]['value'].lower()):
					url = 'https://api.twitch.tv/kraken/channels/' + self.channel_id
					headers = {'Client-ID': self.client_id,
					'Accept': 'application/vnd.twitchtv.v5+json',
					'Content-Type': 'application/json',
					'Authorization': 'OAuth ' + self.channel_oauth}
					data = 'channel[game]=' + quote(new_game, safe="")
					r = requests.put(url=url, headers=headers, params=data)

					c.privmsg(self.irc_channel, "The game has been updated to: " + new_game)
			# Display the current game
			else:
				url = 'https://api.twitch.tv/kraken/channels/' + self.channel_id
				headers = {'Client-ID': self.client_id, 'Accept': 'application/vnd.twitchtv.v5+json'}
				r = requests.get(url, headers=headers).json()
				c.privmsg(self.irc_channel, r['display_name'] + ' is currently playing ' + r['game'])

		# Poll the API the get the current status(title) of the stream
		elif cmd == "title":
			# Set the title
			if len(e.arguments[0].split(' ', 1)) == 2:
				new_title = e.arguments[0].split(' ', 1)[1][0:]
				if self.isMod(e.tags[2]['value'].lower()):
					url = 'https://api.twitch.tv/kraken/channels/' + self.channel_id
					headers = {'Client-ID': self.client_id,
					'Accept': 'application/vnd.twitchtv.v5+json',
					'Content-Type': 'application/json',
					'Authorization': 'OAuth ' + self.channel_oauth}
					data = 'channel[status]=' + quote(new_title, safe="")
					r = requests.put(url=url, headers=headers, params=data)

					c.privmsg(self.irc_channel, "The title has been updated to: " + new_title)
			# Display the current title
			else:
				url = 'https://api.twitch.tv/kraken/channels/' + self.channel_id
				headers = {'Client-ID': self.client_id, 'Accept': 'application/vnd.twitchtv.v5+json'}
				r = requests.get(url, headers=headers).json()
				c.privmsg(self.irc_channel, r['display_name'] + ', the current title is: ' + r['status'])

		# Tell the viewers what they need to know about gambling
		elif cmd == "gamble":
			url = 'https://api.twitch.tv/kraken/channels/' + self.channel_id
			headers = {'Client-ID': self.client_id, 'Accept': 'application/vnd.twitchtv.v5+json'}
			r = requests.get(url, headers=headers).json()
			message = e.tags[2]['value'] + " gambled and lost all their money LUL. Don't gamble kids..."
			c.privmsg(self.irc_channel, message)
		
		# Check the database and tell the viewer how many points they have
		elif cmd == "points" or cmd == "p":
			# Checking another users points
			if len(e.arguments[0].split(' ')) == 2:
				name = e.arguments[0].split(' ')[1][0:]
			# Checking your own points
			else:
				name = e.tags[2]['value']

			self.cursor.execute("SELECT points FROM users WHERE name=?", (name.lower(),))
			points = self.cursor.fetchone()
			if points is not None:
				message = name + " has " + str(points[0]) + " points!"
				c.privmsg(self.irc_channel, message)

		# Display how long the stream has been live before
		elif cmd == "uptime":
			url = 'https://api.twitch.tv/kraken/streams/' + self.channel_id
			headers = {'Client-ID': self.client_id, 'Accept': 'application/vnd.twitchtv.v5+json'}
			r = requests.get(url, headers=headers).json()
			try:
				message = "Stream has been live for " + str(time_since('%Y-%m-%dT%H:%M:%SZ', r['stream']['created_at']))
			except:
				message = "Stream is not live."
			c.privmsg(self.irc_channel, message)

		# Display how long a user has been following the stream for
		elif cmd == "followage":
			# Checking another users followage
			if len(e.arguments[0].split(' ', 1)) == 2:
				name = e.arguments[0].split(' ')[1][0:]
			else:
				name = e.tags[2]['value']

			# Get user_id from displayname
			url = 'https://api.twitch.tv/kraken/users?login=' + name
			headers = {'Client-ID': self.client_id, 'Accept': 'application/vnd.twitchtv.v5+json'}
			r = requests.get(url, headers=headers).json()

			# Get followage data from their id
			user_id = r['users'][0]['_id']
			url = 'https://api.twitch.tv/kraken/users/' + user_id + '/follows/channels/' + self.channel_id
			headers = {'Client-ID': self.client_id, 'Accept': 'application/vnd.twitchtv.v5+json'}
			r = requests.get(url, headers=headers).json()

			try:
				message = name + " followed this channel " + str(time_since('%Y-%m-%dT%H:%M:%SZ', r['created_at']).days) + " days ago."
			except:
				message = name + " is not following this channel."

			c.privmsg(self.irc_channel, message)

		# View or change the rank of a user
		elif cmd == "rank":
			# View own rank
			if len(e.arguments[0].split(' ')) == 1:
				self.cursor.execute("SELECT rank FROM users WHERE name=?", (e.tags[2]['value'].lower(),))
				message = e.tags[2]['value'] + " has the rank of " + self.cursor.fetchone()[0]
				c.privmsg(self.irc_channel, message)
			# View someone elses rank
			elif len(e.arguments[0].split(' ')) == 2:
				self.cursor.execute("SELECT rank FROM users WHERE name = ?", (e.arguments[0].split(' ')[1][0:].lower(), ))
				rank = self.cursor.fetchone()
				if rank is not None:
					message = e.arguments[0].split(' ')[1][0:] + " has the rank of " + rank[0]
					c.privmsg(self.irc_channel, message)
			# Change someones rank
			elif len(e.arguments[0].split(' ')) == 3:
				if self.isMod(e.tags[2]['value'].lower()):
					name = e.arguments[0].split(' ')[1][0:]
					rank = e.arguments[0].split(' ')[2][0:]
					self.cursor.execute("UPDATE users SET rank = ? WHERE name=?", (rank.lower(), name.lower(),))
					self.conn.commit()
					message = name + " has been given the rank " + rank
					c.privmsg(self.irc_channel, message)

		# Show the top 5 users in points
		elif cmd == "top":
			self.cursor.execute("SELECT name, points FROM users WHERE rank is not 'blacklisted' AND rank is not 'bot' ORDER BY points DESC LIMIT 5")
			top_list = self.cursor.fetchall()
			if top_list is not None and len(top_list) == 5:
				message = top_list[0][0] + ": " + str(top_list[0][1]) + ", " + top_list[1][0] + ": " + str(top_list[1][1]) + ", " + \
					top_list[2][0] + ": " + str(top_list[2][1]) + ", " + top_list[3][0] + ": " + str(top_list[3][1]) + ", " + top_list[4][0] + ": " + str(top_list[4][1])
				c.privmsg(self.irc_channel, message)

		# Create a poll - !poll option1, option2, etc
		elif cmd == "poll":
			if self.isMod(e.tags[2]['value'].lower()) and len(e.arguments[0].split(' ', 1)) == 2:
				self.poll = [""]
				self.poll_voted = []
				self.results = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
				self.poll[0] = e.arguments[0].split(' ', 1)[1][0:]

				c.privmsg(self.irc_channel, "Created poll with options: " + e.arguments[0].split(' ', 1)[1][0:])
				c.privmsg(self.irc_channel, "Vote with !vote option")

		# Vote on an option from the poll
		elif cmd == "vote":
			name = e.tags[2]['value']
			if hasattr(self, 'poll') and len(e.arguments[0].split(' ', 1)) == 2 and not name.lower() in self.poll_voted and e.arguments[0].split(' ', 1)[1][0:] in self.poll[0].split(', '):
				options = self.poll[0].split(', ')
				self.poll_voted.append(name.lower())
				self.results[options.index(e.arguments[0].split(' ', 1)[1][0:])] += 1

		# Display the results of the poll
		elif cmd == "results":
			if self.isMod(e.tags[2]['value'].lower()) and hasattr(self, 'poll'):
				options = self.poll[0].split(', ')
				message = "Results: "
				for option in options:
					message += option + ": " + str(self.results[options.index(option)]) + " "

				c.privmsg(self.irc_channel, message)

		# Create a bet - !createbet multiplier option1, option2, etc
		elif cmd == "createbet":
			if self.isMod(e.tags[2]['value'].lower()) and len(e.arguments[0].split(' ', 2)) == 3 and str.isdigit(e.arguments[0].split(' ', 2)[1]):
				self.bet = [""]
				self.users_bet = []
				self.bet_mp = int(e.arguments[0].split(' ', 2)[1][0:])
				self.bet[0] = e.arguments[0].split(' ', 2)[2][0:]

				c.privmsg(self.irc_channel, "Created bet with multiplier of: "
				+ e.arguments[0].split(' ', 2)[1][0:]
				+ " and options of "
				+ e.arguments[0].split(' ', 2)[2][0:])

				c.privmsg(self.irc_channel, "Bet with !bet amount option")

		# Bet on an option - !bet amount option
		elif cmd == "bet":
			if hasattr(self, 'bet') and len(e.arguments[0].split(' ', 2)) == 3 and e.arguments[0].split(' ', 2)[2][0:] in self.bet[0].split(', ') and str.isdigit(e.arguments[0].split(' ', 2)[1]):
				name = e.tags[2]['value']
				options = self.bet[0].split(', ')
				option = e.arguments[0].split(' ', 2)[2][0:]
				bet_amount = e.arguments[0].split(' ', 2)[1][0:]
				self.cursor.execute("SELECT points FROM users WHERE name=?", (name.lower(),))
				points = self.cursor.fetchone()

				# Make sure the user has enough points to make this bet
				if points is not None and points[0] >= int(bet_amount):
					self.users_bet.append((name.lower(), bet_amount, option))
					self.cursor.execute("UPDATE users SET points = ? WHERE name=?", (points[0] - int(bet_amount), name.lower(),))
					self.conn.commit()
					c.privmsg(self.irc_channel, name + " has bet " + str(bet_amount) + " on option " + option)

		# End the bet, and distribute users their points if any won - !endbet option
		elif cmd == "endbet":
			name = e.tags[2]['value']
			if self.isMod(name) and hasattr(self, 'bet'):
				message = "Winners: "
				for user in self.users_bet:
					if user[2] == e.arguments[0].split(' ', 1)[1][0:]:
						won_amount = int(user[1]) * int(self.bet_mp)
						message += user[0] + ": " + str(won_amount) + ", "
						self.cursor.execute("UPDATE users SET points = points + ? WHERE name=?", (won_amount, user[0].lower(),))

				self.conn.commit()
				c.privmsg(self.irc_channel, message)
				self.users_bet = []

		# Check when a user was last seen watching the stream - !lastseen name
		elif cmd == "lastseen":
			if len(e.arguments[0].split(' ', 1)) == 2:
				self.cursor.execute("SELECT last_seen FROM users WHERE name = ?", (e.arguments[0].split(' ')[1][0:].lower(), ))
				last_seen_time = self.cursor.fetchone()

				if last_seen_time is not None:
					message = e.arguments[0].split(' ')[1][0:] + " was last seen at: " + last_seen_time[0]
				else:
					message = e.arguments[0].split(' ')[1][0:] + " has never been seen."

				c.privmsg(self.irc_channel, message)

		# Add a notice - !addnotice frequency offset notice_text
		elif cmd == "addnotice":
			if len(e.arguments[0].split(' ', 3)) == 4:
				self.cursor.execute("INSERT INTO notices VALUES (?, ?, ?)", (e.arguments[0].split(' ', 3)[1], e.arguments[0].split(' ', 3)[2], e.arguments[0].split(' ', 3)[3],))
				self.conn.commit()
				c.privmsg(self.irc_channel, "Notice '" + e.arguments[0].split(' ', 3)[3] + "' was added and will display every " + e.arguments[0].split(' ', 3)[1] + " minutes with an offset of " + e.arguments[0].split(' ', 3)[2])

		# Delete a notice - !delnotice notice_text
		elif cmd == "delnotice":
			if len(e.arguments[0].split(' ', 1)) == 2:
				notice_to_remove = e.arguments[0].split(' ', 1)[1][0:]
				self.cursor.execute("DELETE FROM notices WHERE notice=?", (notice_to_remove,))
				self.conn.commit()
				c.privmsg(self.irc_channel, "Notice '" + notice_to_remove + "' was removed!")

		# Duel another user - !duel user points
		elif cmd == "duel":
			# If there are 2 args, user is accpeting/denying a duel
			if len(e.arguments[0].split(' ')) == 2:
				# The user accpets the duel, pick a winner and adjust points
				if e.arguments[0].split(' ', 1)[1][0:] == "accept":
					for duel in self.duels:
						# We found a duel this user is in...
						if duel[0] == e.tags[2]['value'].lower() or duel[1] == e.tags[2]['value'].lower():
							user1 = duel[0]
							user2 = duel[1]
							# Make sure both users have enough points
							self.cursor.execute("SELECT points FROM users WHERE name = ?", (user1.lower(), ))
							r1 = self.cursor.fetchone()
							self.cursor.execute("SELECT points FROM users WHERE name = ?", (user2.lower(), ))
							r2 = self.cursor.fetchone()
							if r1 and r1[0] >= int(duel[2]) and r2 and r2[0] >= int(duel[2]):
								# Pick winner and loser
								winner = random.choice([user1, user2])
								if user1 == winner:
									loser = user2
								else:
									loser = user1

								# Adjust points
								self.cursor.execute("UPDATE users SET points = points + ? WHERE name=?", (int(duel[2]), winner.lower(),))
								self.cursor.execute("UPDATE users SET points = points - ? WHERE name=?", (int(duel[2]), loser.lower(),))
								self.conn.commit()
								# Remove duel from duels list
								self.duels[:] = []
								c.privmsg(self.irc_channel, winner + " won " + duel[2] + " points FeelsGoodMan")
								c.privmsg(self.irc_channel, loser + " lost " + duel[2] + " points FeelsBadMan")
							else:
								c.privmsg(self.irc_channel, "One of the users in the duel does not have enough points to play :(")
								self.duels[:] = []

				# The user denies or cancels the duel, remove it from the duels list
				elif e.arguments[0].split(' ', 1)[1][0:] == "deny" or e.arguments[0].split(' ', 1)[1][0:] == "cancel":
					for duel in self.duels:
						# We fount a duel this user is in...
						if duel[0] == e.tags[2]['value'].lower() or duel[1] == e.tags[2]['value'].lower():
							# Remove duel from duels list
							self.duels[:] = []
							c.privmsg(self.irc_channel, "The duel between " + duel[0] + " and " + duel[1] + " has been aborted.")

			# If there are 3 args, user is requesting a duel
			elif len(e.arguments[0].split(' ')) == 3:
				user1 = e.tags[2]['value']
				user2 = e.arguments[0].split(' ', 2)[1][0:]
				amount = e.arguments[0].split(' ', 2)[2][0:]
				inDuel = False
				for duel in self.duels:
					if user1 == duel[0] or user1 == duel[1] or user2 == duel[0] or user2 == duel[1]:
						inDuel = True

				if not inDuel:
					self.duels.append([user1.lower(), user2.lower(), amount])
					c.privmsg(self.irc_channel, "@" + user1 + " has requested a duel with @" + user2 + " for " + amount + " points! Use !duel accept or !duel deny")
				else:
					c.privmsg(self.irc_channel, "Either you or the other user is already in a duel! Type !duel deny to cancel and try again.")

		# Request a song to be played on the stream - !sr youtube_url
		elif cmd == "songrequest" or cmd == "sr":
			if config.SETTINGS['enable_media_requests']:
				try:
					url = e.arguments[0].split(' ', 2)[1][0:]
					video = pafy.new(url)
					# Verify the video is not too long or has too few views
					if video.length > config.SETTINGS['media_requests_max_length']:
						c.privmsg(self.irc_channel, "The video you requested is too long.")
					elif video.viewcount < config.SETTINGS['media_requests_min_views']:
						c.privmsg(self.irc_channel, "The video you requested does not have enough views.")
					else:
						self.playlist.append(url)
						c.privmsg(self.irc_channel, "[" + video.title + "] has been added to the playlist.")
				except:
					c.privmsg(self.irc_channel, "Error parsing video. Valid formats are the video ID or full URL.")
			else:
				c.privmsg(self.irc_channel, "Media requests are disabled.")

		# Add a defualt song to the playlist - !default youtube_url
		elif cmd == "default":
			if config.SETTINGS['enable_media_requests']:
				if self.isMod(e.tags[2]['value']):
					try:
						url = e.arguments[0].split(' ', 2)[1][0:]
						video = pafy.new(url)
						self.cursor.execute("INSERT INTO songs VALUES (?)", (url,))
						self.conn.commit()
						c.privmsg(self.irc_channel, "[" + video.title + "] has been added to the default playlist.")
					except:
						c.privmsg(self.irc_channel, "Error parsing video. Valid formats are the video ID or full URL.")
			else:
				c.privmsg(self.irc_channel, "Media requests are disabled.")

		# Display the prev, current, nad next songs
		elif cmd == "playlist" or cmd == "pl":
			if config.SETTINGS['enable_media_requests']:
				message = ""
				if self.last_song is not "":
					message += "Last Song: " + self.last_song
				
				if len(self.playlist) > 0:
					message += " Current Song: " + self.playlist[0]

				if len(self.playlist) > 1:
					message += " Next Song: " + self.playlist[1]
			else:
				message = "Media requests are disabled."

			c.privmsg(self.irc_channel, message)

		# Skip current song
		elif cmd == "skip":
			if config.SETTINGS['enable_media_requests']:
				if len(self.playlist) > 0 and self.isMod(e.tags[2]['value']) and self.isMod(e.tags[2]['value']):
					self.last_song = self.playlist[0]
					del self.playlist[0]
					self.player.pause()
					self.isPlaying = False
			else:
				c.privmsg(self.irc_channel, "Media requests are disabled.")

		elif cmd == "pause":
			if self.isMod(e.tags[2]['value']):
				if config.SETTINGS['enable_media_requests']:
					self.player.pause()
				else:
					c.privmsg(self.irc_channel, "Media requests are disabled.")

		elif cmd == "resume" or cmd == "play":
			if self.isMod(e.tags[2]['value']):
				if config.SETTINGS['enable_media_requests']:
					self.player.play()
				else:
					c.privmsg(self.irc_channel, "Media requests are disabled.")

		# Adjust volume (0-100)
		elif cmd == "volume":
			if config.SETTINGS['enable_media_requests']:
				if len(e.arguments[0].split(' ', 1)) == 2 and self.isMod(e.tags[2]['value']):
					volume = e.arguments[0].split(' ', 2)[1][0:]
					if volume.isdigit() and int(volume) <= 100 and int(volume) >= 0 and self.isMod(e.tags[2]['value']):
						self.player.audio_set_volume(int(volume))
						c.privmsg(self.irc_channel, "Volume has been set to " + volume)
			else:
				c.privmsg(self.irc_channel, "Media requests are disabled.")

	def songFinished(self, data):
		self.last_song = self.current_song
		del self.playlist[0]
		self.isPlaying = False

	def playSong(self, url, c):
		if not self.isPlaying:
			self.isPlaying = True
			self.current_song = url
			print("Now playing " + url)
			video = pafy.new(url)
			c.privmsg(self.irc_channel, "Now playing: [" + video.title + "] " + url)
			best = video.getbest()
			playurl = best.url

			Media = self.Instance.media_new(playurl)
			Media.get_mrl()
			self.player.set_media(Media)
			self.player.play()

	# Check if the user is a mod
	def isMod(self, name):
		self.cursor.execute("SELECT rank FROM users WHERE name=?", (name.lower(),))
		user = self.cursor.fetchone()
		return user and user[0] == "mod" or name.lower() == self.channel

	def processMediaRequests(self, c):
		# Init VLC for song requests, play a video to open the media player.
		url = 'https://www.youtube.com/watch?v=8-16MlvIMWw'
		video = pafy.new(url)
		best = video.getbest()
		playurl = best.url
		self.playlist = [url]
		self.last_song = ""

		self.Instance = vlc.Instance()
		self.player = self.Instance.media_player_new()
		self.current_song = ""
		self.player.event_manager().event_attach(vlc.EventType.MediaPlayerEndReached, self.songFinished)

		Media = self.Instance.media_new(playurl)
		Media.get_mrl()
		self.player.set_media(Media)
		self.isPlaying = True
		self.player.play()

		self.media_conn = sqlite3.connect('data.db')
		self.media_cursor = self.media_conn.cursor()

		while True:
			# Play requested song
			if len(self.playlist) > 0 and not self.isPlaying:
				self.playSong(self.playlist[0], c)
			# Play a song from the defualt list if there are any
			elif len(self.playlist) == 0 and not self.isPlaying:
				self.media_cursor.execute("SELECT url FROM songs ORDER BY RANDOM() LIMIT 1")
				url = self.media_cursor.fetchone()
				if url and url[0]:
					self.playlist.append(url[0])
					self.playSong(url[0], c)
			time.sleep(1)

	# Handles adding points and time-watched to the database for users in the chat
	def tick(self, c):
		# We need a new connection and cursor since they can only be used on the thread they were created on
		self.tick_conn = sqlite3.connect('data.db')
		self.tick_cursor = self.tick_conn.cursor()

		# Get and create a list of notices, the 3rd element is time_until_post
		self.tick_cursor.execute("SELECT * FROM notices")
		notices = self.tick_cursor.fetchall()

		notice_list = []
		for notice in notices:
			notice_list.append([notice[0], notice[1], notice[2], notice[1]])

		# Main points/time/notices loop
		while True:
			# Get a list of "chatters" from twitch
			url = 'http://tmi.twitch.tv/group/user/' + self.channel + '/chatters'
			r = requests.get(url, headers={}).json()

			# Check if the stream is live
			url = 'https://api.twitch.tv/kraken/streams/' + self.channel_id
			headers = {'Client-ID': self.client_id, 'Accept': 'application/vnd.twitchtv.v5+json'}
			r2 = requests.get(url, headers=headers).json()

			if r2['stream'] == None:
				sleep = 600
				add_time = 0
			else:
				sleep = 60
				add_time = 60

			# Process notices
			for notice in notice_list:
				notice[3] -= sleep / 60
				# Post notice if needed and reset the time until it's posted again
				if notice[3] <= 0:
					c.privmsg(self.irc_channel, notice[2])
					print("Posted notice: " + notice[2])
					notice[3] += notice[0]

			# Process all chatters
			current_time = datetime.datetime.now(timezone(self.timezone)).strftime('%I:%M:%S%p - %Y-%m-%d')
			if (r['chatters']):
				for viewer in r['chatters']['vips']:
					self.processUser(viewer, 1, add_time, current_time)
				for viewer in r['chatters']['moderators']:
					self.processUser(viewer, 1, add_time, current_time)
				for viewer in r['chatters']['staff']:
					self.processUser(viewer, 1, add_time, current_time)
				for viewer in r['chatters']['admins']:
					self.processUser(viewer, 1, add_time, current_time)
				for viewer in r['chatters']['global_mods']:
					self.processUser(viewer, 1, add_time, current_time)
				for viewer in r['chatters']['viewers']:
					self.processUser(viewer, 1, add_time, current_time)

			print("Ticking every: " + str(sleep) + " seconds")
			time.sleep(sleep)

	# Add points and time to database for user
	def processUser(self, viewer, points, add_time, current_time):
		# If the user isn't in the database, add them with "viewer" role, 0 points, 0 time
		self.tick_cursor.execute("SELECT * FROM users WHERE name=?", (viewer,))
		if not self.tick_cursor.fetchone():
			user_data = [(
				viewer,
				'viewer',
				0,
				0,
				current_time
			)]
			self.tick_cursor.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?)", user_data)
			self.tick_conn.commit()

		# Update the values in the database
		self.tick_cursor.execute("UPDATE users SET time = Time + ?, points = points + ?, last_seen = ? WHERE name=?", (add_time, points, current_time, viewer, ))
		self.tick_conn.commit()

# Return the amount of time since date in a deltatime
def time_since(datetimeFormat, date):
	date2 = datetime.datetime.utcnow().strftime(datetimeFormat)

	diff = datetime.datetime.strptime(date2, datetimeFormat)\
		- datetime.datetime.strptime(date, datetimeFormat)

	return diff

def main():
	# Make sure settings are set
	if config.SETTINGS['bot_name'] == "" or config.SETTINGS['client_id'] == "" or config.SETTINGS['oauth'] == "" or config.SETTINGS['channel_name'] == "" or config.SETTINGS['channel_oauth'] == "":
		print("You must edit config.py first")
		sys.exit(1)

	conn = sqlite3.connect('data.db')

	username = config.SETTINGS['bot_name']
	client_id = config.SETTINGS['client_id']
	token = config.SETTINGS['oauth']
	channel_oauth = config.SETTINGS['channel_oauth']
	channel = config.SETTINGS['channel_name'].lower()
	timezone = config.SETTINGS['timezone']

	bot = TwitchBot(username, client_id, token, channel_oauth, channel, conn, timezone)
	bot.start()

if __name__ == "__main__":
	main()
