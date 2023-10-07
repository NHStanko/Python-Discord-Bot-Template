CREATE TABLE IF NOT EXISTS `blacklist` (
  `user_id` varchar(20) NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS `warns` (
  `id` int(11) NOT NULL,
  `user_id` varchar(20) NOT NULL,
  `server_id` varchar(20) NOT NULL,
  `moderator_id` varchar(20) NOT NULL,
  `reason` varchar(255) NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS `plays` (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id VARCHAR(20) NOT NULL,
  song_id VARCHAR(20) NOT NULL,
  times_played INTEGER NOT NULL
);

-- Create a money table, total loss and total gain
CREATE TABLE IF NOT EXISTS `money` (
  `user_id` varchar(20) NOT NULL,
  `money` int(11) NOT NULL DEFAULT '10000',
  `total_loss` int(11) NOT NULL DEFAULT '0',
  `total_gain` int(11) NOT NULL DEFAULT '0',
  `bankrupt_count` int(11) NOT NULL DEFAULT '0',
  `plays` int(11) NOT NULL DEFAULT '0'
);