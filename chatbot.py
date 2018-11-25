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

class TwitchBot(irc.bot.SingleServerIRCBot):
	def __init__(self, username, client_id, token, channel_oauth, channel, conn):
		self.client_id = client_id
		self.token = token
		self.channel_oauth = channel_oauth
		self.channel = channel
		self.irc_channel = "#" + channel
		self.conn = conn
		self.cursor = conn.cursor()

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
		c.join('#' + self.channel)

		# call tick() from another thread so it can run at the same time
		thread = Thread(target=self.tick)
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
		self.cursor.execute("SELECT command, response FROM commands")
		for command in self.cursor.fetchall():
			if (command[0] == cmd):
				c.privmsg(self.irc_channel, "@" + e.tags[2]['value'] + ", "+ command[1])
	
		# Add custom commands
		if cmd == "addcommand":
			new_cmd = e.arguments[0].split(' ', 2)[1][0:]
			response = e.arguments[0].split(' ', 2)[2][0:]
			self.cursor.execute("INSERT INTO commands VALUES (?, ?)", (new_cmd, response,))
			self.conn.commit()
			c.privmsg(self.irc_channel, "Command !" + new_cmd + " was added!")
		
		# Delete custom commands
		elif cmd == "delcommand":
			command_to_remove = e.arguments[0].split(' ', 1)[1][0:]
			self.cursor.execute("DELETE FROM commands WHERE command=?", (command_to_remove,))
			self.conn.commit()
			c.privmsg(self.irc_channel, "Command !" + command_to_remove + " was removed!")
		
		# Poll the API to get current game.
		elif cmd == "game":
			try:
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
			except IndexError:
				url = 'https://api.twitch.tv/kraken/channels/' + self.channel_id
				headers = {'Client-ID': self.client_id, 'Accept': 'application/vnd.twitchtv.v5+json'}
				r = requests.get(url, headers=headers).json()
				c.privmsg(self.irc_channel, r['display_name'] + ' is currently playing ' + r['game'])

		# Poll the API the get the current status(title) of the stream
		elif cmd == "title":
			try:
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
			except IndexError:
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
		elif cmd == "points":
			try:
				name = e.arguments[0].split(' ')[1][0:]
			except IndexError:
				name = e.tags[2]['value']

			self.cursor.execute("SELECT points FROM users WHERE name=?", (name.lower(),))
			message = name + " has " + str(self.cursor.fetchone()[0]) + " points!"
			c.privmsg(self.irc_channel, message)

		# Display how long the stream has been live before
		elif cmd == "uptime":
			url = 'https://api.twitch.tv/kraken/streams/' + self.channel_id
			headers = {'Client-ID': self.client_id, 'Accept': 'application/vnd.twitchtv.v5+json'}
			r = requests.get(url, headers=headers).json()
			message = "Stream has been live for " + str(time_since('%Y-%m-%dT%H:%M:%SZ', r['stream']['created_at']))
			c.privmsg(self.irc_channel, message)

		# Display how long a user has been following the stream for
		elif cmd == "followage":
			try:
				name = e.arguments[0].split(' ')[1][0:]
			except IndexError:
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
				message = name + " followed this channel " + \
					str(time_since('%Y-%m-%dT%H:%M:%SZ', r['created_at']).days) + " days ago."

			except KeyError:
				message = name + " is not following this channel."

			c.privmsg(self.irc_channel, message)

		# View or change the rank of a user
		elif cmd == "rank":
			# View own rank
			if len(e.arguments[0].split(' ')) == 1:
				self.cursor.execute("SELECT rank FROM users WHERE name=?", (e.tags[2]['value'].lower(),))
				message = e.tags[2]['value'] + " has the rank of " + self.cursor.fetchone()[0]
			# View someone elses rank
			elif len(e.arguments[0].split(' ')) == 2:
				self.cursor.execute("SELECT rank FROM users WHERE name = ?", (e.arguments[0].split(' ')[1][0:].lower(), ))
				message = e.arguments[0].split(' ')[1][0:] + " has the rank of " + self.cursor.fetchone()[0]
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
			message = "1: " + top_list[0][0] + ": " + str(top_list[0][1]) + ", 2: " + top_list[1][0] + ": " + str(top_list[1][1]) + ", 3: " + top_list[2][0] + ": " + str(top_list[2][1]) + ", 4: " + top_list[3][0] + ": " + str(top_list[3][1]) + ", 5: " + top_list[4][0] + ": " + str(top_list[4][1])
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
			if hasattr(self, 'poll') and len(e.arguments[0].split(' ', 2)) == 2 and not name.lower() in self.poll_voted and e.arguments[0].split(' ', 1)[1][0:] in self.poll[0].split(', '):
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
			if self.isMod(e.tags[2]['value'].lower()) and len(e.arguments[0].split(' ', 2)) == 3:
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
			if hasattr(self, 'bet') and len(e.arguments[0].split(' ', 2)) == 3 and e.arguments[0].split(' ', 2)[2][0:] in self.bet[0].split(', '):
				name = e.tags[2]['value']
				options = self.bet[0].split(', ')
				option = e.arguments[0].split(' ', 2)[2][0:]
				bet_amount = e.arguments[0].split(' ', 2)[1][0:]
				self.cursor.execute("SELECT points FROM users WHERE name=?", (name.lower(),))
				points = self.cursor.fetchone()[0]

				# Make sure the user has enough points to make this bet
				if points >= int(bet_amount):
					self.users_bet.append((name.lower(), bet_amount, option))
					self.cursor.execute("UPDATE users SET points = ? WHERE name=?", (points - int(bet_amount), name.lower(),))
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

	# Check if the user is a mod
	def isMod(self, name):
		self.cursor.execute("SELECT rank FROM users WHERE name=?", (name.lower(),))
		user = self.cursor.fetchone()
		return user and user[0] == "mod"

	# Handles adding points and time-watched to the database for users in the chat
	def tick(self):
		# We need a new connection and cursor since they can only be used on the thread they were created on
		self.tick_conn = sqlite3.connect('data.db')
		self.tick_cursor = self.tick_conn.cursor()

		# Main points/time loop
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

			# Process all chatters
			if (r['chatters']):
				for viewer in r['chatters']['vips']:
					self.processUser(viewer, 1, add_time)
				for viewer in r['chatters']['moderators']:
					self.processUser(viewer, 1, add_time)
				for viewer in r['chatters']['staff']:
					self.processUser(viewer, 1, add_time)
				for viewer in r['chatters']['admins']:
					self.processUser(viewer, 1, add_time)
				for viewer in r['chatters']['global_mods']:
					self.processUser(viewer, 1, add_time)
				for viewer in r['chatters']['viewers']:
					self.processUser(viewer, 1, add_time)

			print("Ticking every: " + str(sleep) + " seconds")
			time.sleep(sleep)

	# Add points and time to database for user
	def processUser(self, viewer, points, add_time):
		# If the user isn't in the database, add them with "viewer" role, 0 points, 0 time
		self.tick_cursor.execute("SELECT * FROM users WHERE name=?", (viewer,))
		if not self.tick_cursor.fetchone():
			user_data = [(
				viewer,
				'viewer',
				0,
				0
			)]
			self.tick_cursor.executemany("INSERT INTO users VALUES (?, ?, ?, ?)", user_data)
			self.tick_conn.commit()

		# Update the values in the database
		self.tick_cursor.execute("UPDATE users SET time = Time + ?, points = points + ? WHERE name=?", (add_time, points, viewer,))
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

	bot = TwitchBot(username, client_id, token, channel_oauth, channel, conn)
	bot.start()

if __name__ == "__main__":
	main()
