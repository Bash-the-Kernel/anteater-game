# Anteater Game Database Project - Final Report

## Application Description

The Anteater Game is a Python-based arcade game built with Pygame that integrates a MySQL database for user management and score tracking. Players control an anteater that extends its tongue to capture ants by forming loops. The game features:

- **User Authentication**: Secure signup/login system with bcrypt password hashing
- **Score Tracking**: Persistent high score leaderboard with level progression
- **Settings Menu**: In-game settings for username/password changes
- **Admin Panel**: Administrative controls for score management
- **Progressive Difficulty**: Dynamic ant spawning based on time elapsed

## Methodology

The project follows a modular architecture separating game logic from database operations:

1. **Game Engine** (`game.py`): Pygame-based game loop with real-time mechanics
2. **Authentication Module** (`auth.py`): Database operations and security functions
3. **CLI Tools** (`auth_test_cli.py`): Command-line interface for database management
4. **Database Schema** (`schema.sql`): MySQL table definitions and relationships

## Database Related

### ER Diagram

```
PLAYERS                    SCORES                     PROGRESS
+-------------+           +-------------+           +-------------+
| player_id   |<--------->| score_id    |           | progress_id |
| username    |     1:N   | player_id   |<--------->| player_id   |
| password_hash|           | score       |     1:1   | level       |
| date_created|           | date        |           | achievements|
| is_admin    |           | level       |           +-------------+
+-------------+           +-------------+
```

### DDL (Data Definition Language)

```sql
-- Players table with authentication and admin capabilities
CREATE TABLE players (
    player_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARBINARY(128) NOT NULL,
    date_created DATETIME NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Scores table for leaderboard functionality
CREATE TABLE scores (
    score_id INT AUTO_INCREMENT PRIMARY KEY,
    player_id INT NOT NULL,
    score INT NOT NULL,
    date DATETIME NOT NULL,
    level INT NOT NULL DEFAULT 1,
    FOREIGN KEY (player_id) REFERENCES players(player_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Progress table for future achievement system
CREATE TABLE progress (
    progress_id INT AUTO_INCREMENT PRIMARY KEY,
    player_id INT NOT NULL,
    level INT NOT NULL DEFAULT 1,
    achievements JSON DEFAULT (JSON_ARRAY()),
    FOREIGN KEY (player_id) REFERENCES players(player_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### DML (Data Manipulation Language)

**INSERT Operations:**
```sql
-- User registration
INSERT INTO players (username, password_hash, date_created) 
VALUES ('player1', BINARY_HASH, NOW());

-- Score recording
INSERT INTO scores (player_id, score, date, level) 
VALUES (1, 150, NOW(), 3);
```

**UPDATE Operations:**
```sql
-- Credential updates
UPDATE players SET username = 'newname', password_hash = NEW_HASH 
WHERE player_id = 1;

-- Admin promotion
UPDATE players SET is_admin = TRUE WHERE username = 'admin';
```

**DELETE Operations:**
```sql
-- Admin score removal
DELETE s FROM scores s 
JOIN players p ON s.player_id = p.player_id 
WHERE p.username = 'target_user';
```

**SELECT Operations:**
```sql
-- Leaderboard query
SELECT p.username, s.score, s.level, s.date 
FROM scores s JOIN players p ON p.player_id = s.player_id 
ORDER BY s.score DESC LIMIT 10;
```

## Process

### Development Workflow
1. **Database Design**: Created normalized schema with proper relationships
2. **Authentication System**: Implemented secure bcrypt password hashing
3. **Game Integration**: Connected Pygame frontend to MySQL backend
4. **User Interface**: Added settings and admin panels with pause functionality
5. **Testing**: CLI tools for database operations and user management

### Security Implementation
- **Password Security**: bcrypt hashing with automatic salting
- **SQL Injection Prevention**: Parameterized queries throughout
- **Admin Authorization**: Role-based access control for administrative functions
- **Input Validation**: Comprehensive error handling and data validation

## Challenges

1. **Database Migration**: Adding new columns to existing tables required careful migration handling
2. **Game State Management**: Implementing pause functionality across multiple game systems
3. **Real-time Integration**: Balancing database operations with 60 FPS game performance
4. **Cross-platform Compatibility**: Ensuring consistent behavior across different operating systems
5. **Error Handling**: Managing database connection failures gracefully during gameplay

## Limitations

1. **Single Database**: No connection pooling or failover mechanisms
2. **Local Storage**: No cloud backup or synchronization capabilities
3. **Performance**: Database queries on main game thread could cause frame drops
4. **Security**: Admin promotion requires manual database access
5. **Scalability**: No optimization for large numbers of concurrent users

## Future Work

### Technical Enhancements
- **Connection Pooling**: Implement database connection pooling for better performance
- **Async Operations**: Move database operations to background threads
- **Cloud Integration**: Add cloud save functionality and cross-device synchronization
- **Caching**: Implement Redis caching for frequently accessed data

### Feature Additions
- **Achievement System**: Expand progress table with comprehensive achievements
- **Multiplayer Support**: Real-time multiplayer with WebSocket integration
- **Tournament Mode**: Scheduled competitions with bracket systems
- **Social Features**: Friend lists, messaging, and score sharing

### Security Improvements
- **OAuth Integration**: Support for Google/Facebook authentication
- **Rate Limiting**: Prevent brute force attacks on login endpoints
- **Audit Logging**: Track all administrative actions and security events
- **Encryption**: Encrypt sensitive data at rest

## Conclusion

The Anteater Game Database Project successfully demonstrates the integration of a real-time game engine with a robust MySQL database backend. The implementation showcases proper database design principles, security best practices, and modular architecture patterns.

Key achievements include:
- Secure user authentication with industry-standard password hashing
- Persistent score tracking with normalized database design
- Administrative controls with role-based access
- Seamless integration between game mechanics and database operations

The project provides a solid foundation for future enhancements and demonstrates practical application of database concepts in game development. The modular design ensures maintainability and extensibility for additional features.

### Technical Stack Summary
- **Frontend**: Python 3.11, Pygame 2.x
- **Backend**: MySQL 8.0, mysql-connector-python
- **Security**: bcrypt password hashing
- **Architecture**: Modular MVC pattern with separation of concerns

The successful completion of this project validates the effectiveness of combining traditional database management with modern game development practices.