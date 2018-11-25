CREATE TABLE IF NOT EXISTS `log` ( `name` TEXT, `message` TEXT, `time` INTEGER );
CREATE TABLE IF NOT EXISTS `users` ( `name` TEXT, `rank` TEXT, `points` INTEGER, `time` INTEGER );
CREATE TABLE IF NOT EXISTS "commands" ( `command` TEXT NOT NULL UNIQUE, `response` TEXT NOT NULL );