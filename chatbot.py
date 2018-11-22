import sys
import irc.bot
import requests
import config
import sqlite3
import datetime
from datetime import timedelta
from threading import Thread
import time

class TwitchBot(irc.bot.SingleServerIRCBot):
	def __init__(self, username, client_id, token, channel, conn):
		self.client_id = client_id
		self.token = token
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
		self.cursor.executemany("INSERT INTO log VALUES (?, ?, ?)", (d['display-name'], e.arguments[0], d['tmi-sent-ts'],))
		self.conn.commit()

		# If a chat message starts with an exclamation point, try to run it as a command
		if e.arguments[0][:1] == '!':
			cmd = e.arguments[0].split(' ')[0][1:]
			print ('Received command: ', cmd)
			self.do_command(e, cmd)
		return

	def do_command(self, e, cmd):
		c = self.connection

		# Poll the API to get current game.
		if cmd == "game":
			url = 'https://api.twitch.tv/kraken/channels/' + self.channel_id
			headers = {'Client-ID': self.client_id, 'Accept': 'application/vnd.twitchtv.v5+json'}
			r = requests.get(url, headers=headers).json()
			c.privmsg(self.irc_channel, r['display_name'] + ' is currently playing ' + r['game'])

		# Poll the API the get the current status(title) of the stream
		elif cmd == "title":
			url = 'https://api.twitch.tv/kraken/channels/' + self.channel_id
			headers = {'Client-ID': self.client_id, 'Accept': 'application/vnd.twitchtv.v5+json'}
			r = requests.get(url, headers=headers).json()
			c.privmsg(self.irc_channel, r['display_name'] + ' channel title is currently ' + r['status'])

		# Tell the viewers what they need to know about gambling
		elif cmd == "gamble":
			url = 'https://api.twitch.tv/kraken/channels/' + self.channel_id
			headers = {'Client-ID': self.client_id, 'Accept': 'application/vnd.twitchtv.v5+json'}
			r = requests.get(url, headers=headers).json()
			message = e.tags[2]['value'] + " gambled and lost all their money LUL. Don't gamble kids..."
			c.privmsg(self.irc_channel, message)
		
		# Check the database and tell the viewer how many points they have
		elif cmd == "points":
			self.cursor.execute("SELECT points FROM users WHERE name=?", (e.tags[2]['value'].lower(),))
			message = e.tags[2]['value'] + " has " + str(self.cursor.fetchone()[0]) + " points!"
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
			url = 'https://api.twitch.tv/kraken/users/' + e.tags[11]['value'] + '/follows/channels/' + self.channel_id
			headers = {'Client-ID': self.client_id, 'Accept': 'application/vnd.twitchtv.v5+json'}
			r = requests.get(url, headers=headers).json()

			try:
				message = e.tags[2]['value'] + " followed this channel " + \
					str(time_since('%Y-%m-%dT%H:%M:%SZ', r['created_at']).days) + " days ago."

			except KeyError:
				message = e.tags[2]['value'] + " is not following this channel."

			c.privmsg(self.irc_channel, message)

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
	if config.SETTINGS['bot_name'] == "" or config.SETTINGS['client_id'] == "" or config.SETTINGS['oauth'] == "" or config.SETTINGS['channel_name'] == "":
		print("You must edit config.py first")
		sys.exit(1)

	conn = sqlite3.connect('data.db')

	username = config.SETTINGS['bot_name']
	client_id = config.SETTINGS['client_id']
	token = config.SETTINGS['oauth']
	channel = config.SETTINGS['channel_name'].lower()

	bot = TwitchBot(username, client_id, token, channel, conn)
	bot.start()

if __name__ == "__main__":
	main()
