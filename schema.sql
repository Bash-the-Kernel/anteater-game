-- SQL schema for Anteater game authentication and progress

CREATE DATABASE IF NOT EXISTS anteater_game CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
USE anteater_game;

CREATE TABLE IF NOT EXISTS players (
  player_id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(64) NOT NULL UNIQUE,
  password_hash VARBINARY(128) NOT NULL,
  date_created DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS scores (
  score_id INT AUTO_INCREMENT PRIMARY KEY,
  player_id INT NOT NULL,
  score INT NOT NULL,
  date DATETIME NOT NULL,
  FOREIGN KEY (player_id) REFERENCES players(player_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS progress (
  progress_id INT AUTO_INCREMENT PRIMARY KEY,
  player_id INT NOT NULL,
  level INT NOT NULL DEFAULT 1,
  achievements JSON DEFAULT (JSON_ARRAY()),
  FOREIGN KEY (player_id) REFERENCES players(player_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
