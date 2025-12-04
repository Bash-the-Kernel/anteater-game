import pygame
import random
import os
import sys
from collections import deque
from typing import Optional
import math
import wave
import struct

from auth import get_db_connection

try:
    conn = get_db_connection()
    print("Connected to DB successfully!")
    conn.close()
except Exception as e:
    print("DB connection failed:", e)


# Initialize pygame
pygame.init()

# --- Constants ---
WIDTH, HEIGHT = 800, 600
FPS = 60
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED   = (200, 50, 50)
GREEN = (50, 200, 50)

# --- Setup ---
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Anteater Game")
clock = pygame.time.Clock()
font = pygame.font.SysFont(None, 36)

# Initialize mixer and ensure capture sound exists
pygame.mixer.init(frequency=44100, size=-16, channels=2)

ASSETS_DIR = os.path.join(os.path.dirname(__file__), 'assets')
CAPTURE_WAV = os.path.join(ASSETS_DIR, 'capture.wav')
CAPTURE_SOUND = None
ANTEATER_PNG = os.path.join(os.path.dirname(__file__), 'anteater.png')
ART_ANTEATER = None

def make_capture_wav(path, freq=1200, duration=0.06, rate=44100):
    # write a short sine wave WAV file (mono -> we'll load as stereo)
    nframes = int(rate * duration)
    amplitude = 12000
    with wave.open(path, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        frames = bytearray()
        for i in range(nframes):
            t = float(i) / rate
            v = int(amplitude * math.sin(2.0 * math.pi * freq * t))
            frames += struct.pack('<h', v)
        wf.writeframes(frames)

if not os.path.isdir(ASSETS_DIR):
    os.makedirs(ASSETS_DIR, exist_ok=True)
if not os.path.exists(CAPTURE_WAV):
    try:
        make_capture_wav(CAPTURE_WAV)
    except Exception:
        pass

try:
    CAPTURE_SOUND = pygame.mixer.Sound(CAPTURE_WAV)
except Exception:
    CAPTURE_SOUND = None

# Try to load an artist-provided anteater sprite (PNG with alpha)
if os.path.exists(ANTEATER_PNG):
    try:
        ART_ANTEATER = pygame.image.load(ANTEATER_PNG).convert_alpha()
    except Exception:
        ART_ANTEATER = None

# Import auth helpers
try:
    from auth import signup, login, add_score, get_top_scores, is_admin, delete_user_scores
except Exception:
    # If auth is unavailable at import time, provide stubs so the game still runs
    def signup(u, p):
        raise RuntimeError('auth not available')
    def login(u, p):
        raise RuntimeError('auth not available')
    def add_score(pid, s):
        pass

# --- Classes ---
class Anteater:
    def __init__(self, grid_size=20):
        # anteater body (positioned at top center)
        self.rect = pygame.Rect(WIDTH // 2 - 25, 50, 50, 50)

        # Grid and snake-like tongue
        self.grid_size = grid_size
        # tongue segments stored as (x, y) grid coords; origin is top-left of screen
        # tongue starts from the cell below the anteater (tongue shoots downward)
        start_x = (self.rect.centerx) // self.grid_size
        start_y = (self.rect.bottom) // self.grid_size
        self.tongue = deque()
        self.tongue.append((start_x, start_y))

        # direction is a (dx, dy) tuple in grid units. default: down (0, 1)
        self.direction = (0, 1)
        self.next_direction = self.direction

        self.extending = False
        self.retracting = False
        # speed measured in frames per grid move (lower is faster)
        self.move_cooldown = 5
        self.move_timer = 0
        # tuning parameters
        self.max_segments = 40  # maximum tongue length in grid segments
        self.min_loop_area = 2  # minimum number of cells to consider a loop

        # when self-collision detected, we'll form a loop and capture ants
        self.loop_active = False
        self.loop_cells = set()
        # capture timer: when loop formed, wait a short time showing trapped ants then clear
        self.capture_timer = 0
        self.capture_delay_frames = 60  # 1 second at 60 FPS
        # store trapped ants when a loop forms
        self.trapped_ants = []
        # ordered list of grid cells that form the loop (from head to collision)
        self.loop_path = []

    def reset_tongue(self):
        start_x = (self.rect.centerx) // self.grid_size
        start_y = (self.rect.bottom) // self.grid_size
        self.tongue = deque()
        self.tongue.append((start_x, start_y))
        self.direction = (0, 1)
        self.next_direction = self.direction
        self.move_timer = 0
        self.loop_active = False
        self.loop_cells = set()
        self.loop_path = []
        self.trapped_ants = []
        self.capture_timer = 0

    def handle_input(self, keys):
        # Allow turning with arrow keys while extending; prevent direct reverse
        if keys[pygame.K_LEFT]:
            if self.direction != (1, 0):
                self.next_direction = (-1, 0)
        elif keys[pygame.K_RIGHT]:
            if self.direction != (-1, 0):
                self.next_direction = (1, 0)
        elif keys[pygame.K_UP]:
            if self.direction != (0, 1):
                self.next_direction = (0, -1)
        elif keys[pygame.K_DOWN]:
            if self.direction != (0, -1):
                self.next_direction = (0, 1)

    def update(self):
        # move tongue on grid when extending
        if self.extending and not self.loop_active:
            self.move_timer += 1
            if self.move_timer >= self.move_cooldown:
                self.move_timer = 0
                self.direction = self.next_direction
                head_x, head_y = self.tongue[0]
                dx, dy = self.direction
                new_head = (head_x + dx, head_y + dy)

                # bounds check - prevent going off-screen
                max_x = WIDTH // self.grid_size - 1
                max_y = HEIGHT // self.grid_size - 1
                nx, ny = new_head
                if nx < 0 or nx > max_x or ny < 0 or ny > max_y:
                    # stop extending if out of bounds
                    self.extending = False
                    self.retracting = True
                    return

                # self-collision detection: if new head hits existing segment -> loop formed
                if new_head in list(self.tongue):
                    try:
                        idx = list(self.tongue).index(new_head)
                        loop_segment = list(self.tongue)[:idx+1]
                        # store ordered path and cells
                        self.loop_path = loop_segment[:]
                        self.loop_cells = set(loop_segment)
                        self.loop_active = True
                        # start capture timer and stop extending / start retracting
                        self.capture_timer = self.capture_delay_frames
                        self.extending = False
                        self.retracting = True
                    except ValueError:
                        pass
                else:
                    # extend
                    if len(self.tongue) < self.max_segments:
                        self.tongue.appendleft(new_head)
                    else:
                        # reached max length, stop extending and start retract
                        self.extending = False
                        self.retracting = True

        # retracting: shorten tongue from head so the tongue pulls back toward anteater
        if self.retracting:
            self.move_timer += 1
            if self.move_timer >= self.move_cooldown:
                self.move_timer = 0
                if len(self.tongue) > 1:
                    try:
                        self.tongue.popleft()
                    except Exception:
                        self.tongue.pop()
                else:
                    # fully retracted
                    self.retracting = False
                    # When fully retracted, ensure the tongue will launch downward
                    # on the next extend (prevents leftover direction like 'up')
                    self.direction = (0, 1)
                    self.next_direction = (0, 1)
                    # reset move timer so the next move timing is consistent
                    self.move_timer = 0

    def draw(self, surface):
        # Draw tongue segments first so they appear to emerge from snout
        for i, (gx, gy) in enumerate(self.tongue):
            rect = pygame.Rect(gx * self.grid_size, gy * self.grid_size, self.grid_size, self.grid_size)
            pygame.draw.rect(surface, RED, rect)

        # Draw anteater body using artist PNG if provided, otherwise procedural sprite
        global ANTEATER_SPRITE, ART_ANTEATER
        if ART_ANTEATER is not None:
            # scale artist art to rect size if needed
            if ART_ANTEATER.get_width() != self.rect.width or ART_ANTEATER.get_height() != self.rect.height:
                try:
                    scaled = pygame.transform.smoothscale(ART_ANTEATER, (self.rect.width, self.rect.height))
                    surface.blit(scaled, self.rect.topleft)
                except Exception:
                    surface.blit(ART_ANTEATER, self.rect.topleft)
            else:
                surface.blit(ART_ANTEATER, self.rect.topleft)
        else:
            if ANTEATER_SPRITE is None or ANTEATER_SPRITE.get_width() != self.rect.width or ANTEATER_SPRITE.get_height() != self.rect.height:
                ANTEATER_SPRITE = create_anteater_sprite(self.rect.width, self.rect.height)
            surface.blit(ANTEATER_SPRITE, self.rect.topleft)

        # Optionally highlight loop cells with subtle border
        if self.loop_active and self.loop_cells:
            for (gx, gy) in self.loop_cells:
                rect = pygame.Rect(gx * self.grid_size, gy * self.grid_size, self.grid_size, self.grid_size)
                pygame.draw.rect(surface, (255, 200, 200), rect, 1)

    def get_tongue_cells(self):
        return list(self.tongue)

    def get_loop_polygon_pixels(self):
        # produce an ordered polygon outlining the set of loop cells
        if not self.loop_cells:
            return []
        if self.loop_path and len(self.loop_path) >= self.min_loop_area:
            cells = set(self.loop_path)
            edges = set()
            for (gx, gy) in cells:
                x0 = gx * self.grid_size
                y0 = gy * self.grid_size
                x1 = x0 + self.grid_size
                y1 = y0 + self.grid_size
                neighbors = [(gx, gy-1), (gx+1, gy), (gx, gy+1), (gx-1, gy)]
                corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
                for i, n in enumerate(neighbors):
                    if n not in cells:
                        a = corners[i]
                        b = corners[(i+1) % 4]
                        edges.add((a, b))

            if not edges:
                return []

            adj = {}
            for a, b in edges:
                adj.setdefault(a, []).append(b)

            start = min(adj.keys(), key=lambda p: (p[1], p[0]))
            poly = [start]
            cur = start
            prev = None
            max_steps = len(edges) * 3
            steps = 0
            while steps < max_steps:
                steps += 1
                nexts = adj.get(cur, [])
                if not nexts:
                    break
                nxt = None
                for c in nexts:
                    if c != prev:
                        nxt = c
                        break
                if nxt is None:
                    nxt = nexts[0]
                if nxt == start:
                    break
                poly.append(nxt)
                prev = cur
                cur = nxt

            return poly

        # fallback: centroid-sorted
        pts = []
        for (gx, gy) in self.loop_cells:
            cx = gx * self.grid_size + self.grid_size // 2
            cy = gy * self.grid_size + self.grid_size // 2
            pts.append((cx, cy))
        if not pts:
            return []
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        pts.sort(key=lambda p: math.atan2(p[1]-cy, p[0]-cx))
        return pts

class Ant:
    """Ant that spawns on screen edges (excluding top) and uses tank-like controls.

    Movement is driven by a simple state machine: throttle (-1,0,1) and turn (-1,0,1)
    which are picked randomly every few frames.
    """
    SIZE = 20

    def __init__(self):
        self.trapped = False
        self.trapped_pos = None

        # spawn on left, right, or bottom edge; avoid the top where the anteater is
        edges = ['left', 'right', 'bottom']
        edge = random.choice(edges)
        margin = 10
        min_y = max(anteater.rect.bottom + 20, margin)
        max_y = HEIGHT - self.SIZE - margin
        if min_y > max_y:
            min_y = margin
            max_y = HEIGHT - self.SIZE - margin

        if edge == 'left':
            x = margin
            y = random.randint(min_y, max_y)
            angle = 0.0  # pointing right
        elif edge == 'right':
            x = WIDTH - self.SIZE - margin
            y = random.randint(min_y, max_y)
            angle = math.pi  # pointing left
        else:  # bottom
            x = random.randint(margin, WIDTH - self.SIZE - margin)
            y = HEIGHT - self.SIZE - margin
            angle = -math.pi/2  # pointing up

        self.rect = pygame.Rect(int(x), int(y), self.SIZE, self.SIZE)
        self.x = float(self.rect.x)
        self.y = float(self.rect.y)
        self.angle = angle + random.uniform(-0.6, 0.6)
        self.speed = random.uniform(0.8, 2.0)  # forward speed

        # tank control state
        self.throttle = 0  # -1, 0, 1
        self.turn = 0  # -1, 0, 1
        self.rotation_speed = random.uniform(0.03, 0.12)
        self.accel = 0.05
        self.max_speed = 3.0

        # AI decision timer
        self.behavior_timer = random.randint(20, 80)

    def randomize_behavior(self):
        self.throttle = random.choice([-1, 0, 1])
        self.turn = random.choice([-1, 0, 1])
        self.behavior_timer = random.randint(20, 80)

    def update(self):
        if self.trapped:
            return

        # AI: update behavior occasionally
        self.behavior_timer -= 1
        if self.behavior_timer <= 0:
            self.randomize_behavior()

        # apply rotation
        self.angle += self.turn * self.rotation_speed

        # apply throttle (simple acceleration)
        self.speed += self.throttle * self.accel
        self.speed = max(-1.0, min(self.max_speed, self.speed))

        # move
        dx = math.cos(self.angle) * self.speed
        dy = math.sin(self.angle) * self.speed
        self.x += dx
        self.y += dy

        # keep inside screen bounds; if hitting the top area, steer away
        bounced = False
        if self.x < 0:
            self.x = 0
            bounced = True
        if self.x + self.SIZE > WIDTH:
            self.x = WIDTH - self.SIZE
            bounced = True
        if self.y < 0:
            self.y = 0
            bounced = True
        if self.y + self.SIZE > HEIGHT:
            self.y = HEIGHT - self.SIZE
            bounced = True

        if bounced:
            # rotate away a bit
            self.angle += math.pi * 0.5

        self.rect.x = int(self.x)
        self.rect.y = int(self.y)

    def draw(self, surface):
        global ANT_SPRITE
        if ANT_SPRITE is None:
            ANT_SPRITE = create_ant_sprite(self.SIZE)
        # rotate sprite surface according to angle
        rot = pygame.transform.rotate(ANT_SPRITE, -math.degrees(self.angle))
        r = rot.get_rect(center=self.rect.center)
        surface.blit(rot, r.topleft)

# --- Game Setup ---
anteater = Anteater(grid_size=20)
initial_ants = 6
ants = [Ant() for _ in range(initial_ants)]
score = 0
particles = []
popups = []
MAX_PARTICLES = 120

# Level / difficulty ramp (level increases every 60 seconds)
# game_start_ticks is None until the player actually starts playing (after login)
game_start_ticks = None
current_level = 1
last_level = 1
max_ants = 30

# simple ant sprite (drawn programmatically)
def create_ant_sprite(size, color=(20,20,20)):
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    cx = size // 2
    cy = size // 2
    pygame.draw.circle(surf, color, (cx, cy), size//2)
    # eyes
    eye_r = max(1, size//10)
    pygame.draw.circle(surf, (255,255,255), (cx + size//6, cy - size//6), eye_r)
    pygame.draw.circle(surf, (0,0,0), (cx + size//6, cy - size//6), max(1, eye_r//2))
    pygame.draw.circle(surf, (255,255,255), (cx + size//12, cy - size//6), eye_r)
    pygame.draw.circle(surf, (0,0,0), (cx + size//12, cy - size//6), max(1, eye_r//2))
    return surf

ANT_SPRITE = None

# Anteater sprite cache
ANTEATER_SPRITE = None

def create_anteater_sprite(w, h):
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    body_color = (140, 100, 60)  # brownish
    snout_color = (120, 80, 50)
    eye_color = (255, 255, 255)
    pupil = (30, 20, 10)

    # body ellipse
    pygame.draw.ellipse(surf, body_color, (0, int(h*0.15), w, int(h*0.75)))
    # belly lighter stripe
    pygame.draw.ellipse(surf, (180,150,110), (int(w*0.15), int(h*0.35), int(w*0.7), int(h*0.45)))
    # snout (downwards triangle-ish)
    snout_w = max(6, w//4)
    snout_h = max(10, h//3)
    pygame.draw.polygon(surf, snout_color, [(w*0.5 - snout_w//2, int(h*0.8)), (w*0.5 + snout_w//2, int(h*0.8)), (w*0.5, int(h*0.95))])
    # eye
    ex = int(w*0.6)
    ey = int(h*0.35)
    pygame.draw.circle(surf, eye_color, (ex, ey), max(2, w//20))
    pygame.draw.circle(surf, pupil, (ex, ey), max(1, w//40))
    return surf

# Game over / high score state
dead = False
show_scores = False
top_scores = []

# --- Simple Text Input helper for Pygame ---
class TextInput:
    def __init__(self, x, y, w, h, text='', hidden=False):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.active = False
        self.hidden = hidden

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
        if event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key == pygame.K_RETURN:
                self.active = False
            else:
                if event.unicode and len(self.text) < 64:
                    self.text += event.unicode

    def draw(self, surf):
        pygame.draw.rect(surf, (230, 230, 230), self.rect)
        pygame.draw.rect(surf, BLACK, self.rect, 2 if self.active else 1)
        disp = '*' * len(self.text) if self.hidden else self.text
        txt = font.render(disp, True, BLACK)
        surf.blit(txt, (self.rect.x + 4, self.rect.y + (self.rect.height - txt.get_height())//2))

# --- Auth / UI state ---
login_mode = True  # True = login, False = signup
username_input = TextInput(250, 200, 300, 40, '')
password_input = TextInput(250, 260, 300, 40, '', hidden=True)
current_player_id: Optional[int] = None
auth_message = ''

# --- Settings Menu State ---
show_settings = False
settings_username_input = TextInput(250, 200, 300, 40, '')
settings_password_input = TextInput(250, 260, 300, 40, '', hidden=True)
settings_message = ''

# --- Admin State ---
show_admin = False
is_current_user_admin = False
admin_target_input = TextInput(200, 280, 400, 40, '')
admin_message = ''

def point_in_polygon(x, y, polygon):
    # ray casting algorithm for point in polygon (polygon as list of (x,y))
    inside = False
    n = len(polygon)
    if n < 3:
        return False
    px, py = x, y
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i+1) % n]
        if ((y1 > py) != (y2 > py)) and (px < (x2 - x1) * (py - y1) / (y2 - y1 + 1e-9) + x1):
            inside = not inside
    return inside

def capture_ants_in_loop(anteater, ants_list):
    # Return list of ants inside current loop polygon (do not remove here)
    pts = anteater.get_loop_polygon_pixels()
    if not pts:
        return []

    captured = []
    for ant in ants_list:
        ax = ant.rect.centerx
        ay = ant.rect.centery
        if point_in_polygon(ax, ay, pts):
            captured.append(ant)

    return captured


class Particle:
    def __init__(self, pos, vel, color, life=30):
        self.x, self.y = pos
        self.vx, self.vy = vel
        self.color = color
        self.life = life

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.15  # gravity-ish
        self.life -= 1

    def draw(self, surf):
        if self.life <= 0:
            return
        alpha = max(20, min(255, int(255 * (self.life / 30.0))))
        s = pygame.Surface((6, 6), pygame.SRCALPHA)
        s.fill((*self.color, alpha))
        surf.blit(s, (int(self.x), int(self.y)))


class ScorePopup:
    def __init__(self, pos, text, color=(255,255,100), life=60):
        self.x, self.y = pos
        self.text = text
        self.color = color
        self.life = life
        self.initial_life = life

    def update(self):
        self.y -= 0.6
        self.life -= 1

    def draw(self, surf):
        alpha = max(0, min(255, int(255 * (self.life / self.initial_life))))
        txt = font.render(self.text, True, self.color)
        s = pygame.Surface((txt.get_width(), txt.get_height()), pygame.SRCALPHA)
        s.blit(txt, (0,0))
        s.set_alpha(alpha)
        surf.blit(s, (int(self.x - txt.get_width()/2), int(self.y - txt.get_height()/2)))

def check_player_death():
    global dead
    # if any ant (non-trapped) collides with anteater rect => death
    for a in ants:
        if not getattr(a, 'trapped', False) and a.rect.colliderect(anteater.rect):
            dead = True
            return True
    return False

# --- Main Game Loop ---
running = True
while running:
    clock.tick(FPS)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        # If user not logged in, route events to input boxes
        if current_player_id is None:
            username_input.handle_event(event)
            password_input.handle_event(event)

        # If settings menu is open, route events to settings inputs
        if show_settings:
            settings_username_input.handle_event(event)
            settings_password_input.handle_event(event)
        
        # If admin menu is open, route events to admin inputs
        if show_admin:
            admin_target_input.handle_event(event)

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE and current_player_id is not None:
                # Toggle settings menu (only when logged in)
                if show_admin:
                    show_admin = False
                else:
                    show_settings = not show_settings
                    if show_settings:
                        # Pre-fill current username if available
                        settings_username_input.text = username_input.text
                        settings_password_input.text = ''
                        settings_message = ''
            elif event.key == pygame.K_F1 and current_player_id is not None and is_current_user_admin:
                # Toggle admin menu (F1 key for admins only)
                show_admin = not show_admin
                if show_admin:
                    admin_target_input.text = ''
                    admin_message = ''
            elif not show_settings and not show_admin:  # Only handle game controls when menus not open
                if event.key == pygame.K_SPACE:
                    # start extending
                    anteater.extending = True
                    anteater.retracting = False
                if event.key == pygame.K_r:
                    # reset tongue and release any trapped ants
                    anteater.reset_tongue()
                    for a in ants:
                        if getattr(a, 'trapped', False):
                            a.trapped = False
                            a.trapped_pos = None
                    anteater.trapped_ants = []
                    anteater.loop_path = []
                    anteater.loop_cells = set()
                    anteater.capture_timer = 0
        if event.type == pygame.KEYUP and not show_settings and not show_admin:
            if event.key == pygame.K_SPACE:
                # stop extending, start retracting
                anteater.extending = False
                anteater.retracting = True

    # read continuous key state for turning (only when menus not open)
    if not show_settings and not show_admin:
        keys = pygame.key.get_pressed()
        anteater.handle_input(keys)

    # --- Update ---
    # Only update game when not paused by menus, login, or game over
    if not show_settings and not show_admin:
        anteater.update()
        for ant in ants:
            # Only update ants when not paused by login overlay or showing scores
            if current_player_id is not None and not show_scores and not dead:
                ant.update()
    # If a loop has just formed, mark ants inside as trapped and start capture timer (only when not in settings)
    if not show_settings and anteater.loop_active and anteater.trapped_ants == []:
        trapped = capture_ants_in_loop(anteater, ants)
        for ant in trapped:
            ant.trapped = True
            # store their current position so they visually remain trapped
            ant.trapped_pos = (ant.rect.x, ant.rect.y)
        anteater.trapped_ants = trapped
        # if there are no trapped ants, clear the loop immediately (nothing to capture)
        if not trapped:
            anteater.loop_active = False
            anteater.loop_cells = set()
            anteater.loop_path = []
            anteater.capture_timer = 0

    # Tongue collision: if any ant touches a tongue segment while tongue exists, capture immediately (only when not in settings)
    if not show_settings and anteater.get_tongue_cells():
        # build tongue rects
        tongue_rects = []
        for (gx, gy) in anteater.get_tongue_cells():
            r = pygame.Rect(gx * anteater.grid_size, gy * anteater.grid_size, anteater.grid_size, anteater.grid_size)
            tongue_rects.append(r)
        to_remove = []
        for ant in ants:
            if getattr(ant, 'trapped', False):
                continue
            # rectangle overlap check
            collided = False
            for tr in tongue_rects:
                if ant.rect.colliderect(tr):
                    collided = True
                    break
            if collided:
                to_remove.append(ant)
        for ant in to_remove:
            try:
                ants.remove(ant)
            except ValueError:
                pass
            # spawn capture particles at ant center
            for i in range(8):
                if len(particles) >= MAX_PARTICLES:
                    break
                ang = random.uniform(0, math.pi*2)
                spd = random.uniform(1.0, 3.0)
                vx = math.cos(ang) * spd
                vy = math.sin(ang) * spd
                particles.append(Particle((ant.rect.centerx, ant.rect.centery), (vx, vy), (255, 200, 50), life=30))
            # sound on capture
            try:
                # play capture sound if available
                try:
                    if CAPTURE_SOUND:
                        CAPTURE_SOUND.play()
                except Exception:
                    pass
            except Exception:
                pass
            ants.append(Ant())
            pts = 10
            score += pts
            # spawn a small popup showing points
            popups.append(ScorePopup((ant.rect.centerx, ant.rect.top - 6), f"+{pts}", color=(255,220,100), life=50))

    # If there are trapped ants, countdown capture timer and capture when timer expires (only when not in settings)
    if not show_settings and anteater.loop_active and anteater.trapped_ants:
        if anteater.capture_timer > 0:
            anteater.capture_timer -= 1
        else:
            # capture complete: remove trapped ants, respawn new ones, add score
            captured_count = len(anteater.trapped_ants)
            for ant in anteater.trapped_ants:
                try:
                    ants.remove(ant)
                except ValueError:
                    pass
                ants.append(Ant())
            # award score (persist only on death)
            points = captured_count * 10
            score += points
            # spawn popup at loop centroid if available
            try:
                poly = anteater.get_loop_polygon_pixels()
                if poly:
                    cx = sum(p[0] for p in poly)//len(poly)
                    cy = sum(p[1] for p in poly)//len(poly)
                else:
                    cx, cy = WIDTH//2, HEIGHT//2
            except Exception:
                cx, cy = WIDTH//2, HEIGHT//2
            popups.append(ScorePopup((cx, cy), f"+{points}", color=(255,180,120), life=80))
            # small particle burst at centroid
            for i in range(min(20, MAX_PARTICLES - len(particles))):
                ang = random.uniform(0, math.pi*2)
                spd = random.uniform(1.0, 4.0)
                vx = math.cos(ang) * spd
                vy = math.sin(ang) * spd
                particles.append(Particle((cx, cy), (vx, vy), (255, 200, 80), life=40))
            # clear loop state
            anteater.loop_active = False
            anteater.loop_cells = set()
            anteater.trapped_ants = []

    # Check for death only during normal play
    # update level based on elapsed time only when a player is logged in and game is active
    if not show_settings and game_start_ticks is not None and current_player_id is not None and not show_scores and not dead:
        elapsed_seconds = (pygame.time.get_ticks() - game_start_ticks) // 1000
        current_level = elapsed_seconds // 60 + 1
        # if level increased, ramp difficulty (spawn more ants up to max)
        if current_level > last_level:
            last_level = current_level
            # spawn a few new ants
            for _ in range(min(3 * (current_level-1), max_ants - len(ants))):
                ants.append(Ant())
    else:
        # keep level as last known value while not actively playing (e.g., before login)
        current_level = last_level

    if not show_settings and not dead:
        if check_player_death():
            # persist final score with level if logged in
            if current_player_id is not None:
                try:
                    add_score(current_player_id, score, current_level)
                except Exception:
                    pass
            # fetch top scores for display
            try:
                top_scores = get_top_scores(10)
            except Exception:
                top_scores = []
            show_scores = True

    # --- Draw ---
    screen.fill(WHITE)
    # Draw loop filled polygon (under ants and tongue)
    if anteater.loop_active and anteater.loop_path:
        poly_pts = anteater.get_loop_polygon_pixels()
        if poly_pts:
            # create transparent surface to draw filled polygon
            surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            pygame.draw.polygon(surf, (255, 150, 150, 90), poly_pts)
            # pulsing outline alpha
            t = pygame.time.get_ticks()
            pulse = 128 + int(127 * math.sin(t / 250.0))
            outline_color = (255, 80, 80, pulse)
            # draw outline slightly thicker by drawing multiple outlines
            pygame.draw.polygon(surf, outline_color, poly_pts, 3)
            screen.blit(surf, (0, 0))

    # Draw ants: if trapped, draw at trapped_pos and don't update movement; fade based on timer
    for ant in ants:
        if getattr(ant, 'trapped', False) and getattr(ant, 'trapped_pos', None) is not None:
            tx, ty = ant.trapped_pos
            # fade alpha as timer goes down
            alpha = 255
            if anteater.capture_delay_frames > 0:
                ratio = max(0.0, min(1.0, anteater.capture_timer / anteater.capture_delay_frames))
                alpha = int(255 * ratio)
            # draw trapped ant on an alpha surface
            ant_surf = pygame.Surface((ant.rect.width, ant.rect.height), pygame.SRCALPHA)
            ant_surf.fill((0, 0, 0, alpha))
            screen.blit(ant_surf, (tx, ty))
        else:
            ant.draw(screen)

    # update and draw particles
    for p in particles[:]:
        p.update()
        if p.life <= 0:
            particles.remove(p)
        else:
            p.draw(screen)

    # update and draw score popups
    for popup in popups[:]:
        popup.update()
        if popup.life <= 0:
            popups.remove(popup)
        else:
            popup.draw(screen)

    score_text = font.render(f"Score: {score}", True, BLACK)
    screen.blit(score_text, (10, 10))
    lvl_text = font.render(f"Level: {current_level}", True, BLACK)
    screen.blit(lvl_text, (10, 40))

    # Draw tongue on top of the filled polygon / ants
    anteater.draw(screen)
    
    # Show settings hint when logged in and not in other menus
    if current_player_id is not None and not show_scores and not show_settings and not show_admin:
        hint_text = font.render('Press ESC for Settings', True, (100, 100, 100))
        screen.blit(hint_text, (WIDTH - hint_text.get_width() - 10, 10))
        
        # Show admin hint for admin users
        if is_current_user_admin:
            admin_hint = font.render('Press F1 for Admin', True, (100, 100, 100))
            screen.blit(admin_hint, (WIDTH - admin_hint.get_width() - 10, 35))

    # If dead/show_scores, draw overlay with top scores and options
    if show_scores:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0,0,0,200))
        screen.blit(overlay, (0,0))
        title = font.render('Game Over - High Scores', True, WHITE)
        screen.blit(title, (WIDTH//2 - title.get_width()//2, 80))
        # list top scores (row: username, score, level, date)
        y = 140
        idx = 1
        for row in top_scores:
            try:
                uname = row[0]
                sc = row[1]
                lvl = row[2] if len(row) > 2 else '?'
                dt = row[3] if len(row) > 3 else None
            except Exception:
                # fallback if shape unexpected
                uname = str(row[0]) if len(row) > 0 else 'unknown'
                sc = row[1] if len(row) > 1 else 0
                lvl = row[2] if len(row) > 2 else '?'
                dt = row[3] if len(row) > 3 else None

            # format date if possible
            date_str = ''
            try:
                if dt is None:
                    date_str = ''
                elif hasattr(dt, 'strftime'):
                    date_str = dt.strftime('%Y-%m-%d %H:%M')
                else:
                    date_str = str(dt)
            except Exception:
                date_str = str(dt)

            txt = font.render(f'{idx}. {uname} — {sc} (L{lvl}) {date_str}', True, WHITE)
            screen.blit(txt, (WIDTH//2 - txt.get_width()//2, y))
            y += 30
            idx += 1

        # restart and quit buttons
        restart_btn = pygame.Rect(WIDTH//2 - 120, HEIGHT - 140, 100, 40)
        quit_btn = pygame.Rect(WIDTH//2 + 20, HEIGHT - 140, 100, 40)
        pygame.draw.rect(screen, (100,200,100), restart_btn)
        pygame.draw.rect(screen, (200,100,100), quit_btn)
        screen.blit(font.render('Restart', True, BLACK), (restart_btn.x+10, restart_btn.y+6))
        screen.blit(font.render('Quit', True, BLACK), (quit_btn.x+30, quit_btn.y+6))

        # check for click
        if pygame.mouse.get_pressed()[0]:
            mx, my = pygame.mouse.get_pos()
            if restart_btn.collidepoint((mx,my)):
                # reset game state
                dead = False
                show_scores = False
                score = 0
                ants.clear()
                ants.extend([Ant() for _ in range(10)])
                anteater.reset_tongue()
                # restart level timer only if logged in
                if current_player_id is not None:
                    game_start_ticks = pygame.time.get_ticks()
            if quit_btn.collidepoint((mx,my)):
                pygame.quit()
                sys.exit()

    # If not logged in, draw login/signup UI overlay and skip game input
    if current_player_id is None:
        # dim background
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0,0,0,120))
        screen.blit(overlay, (0,0))
        title = font.render('Login / Signup', True, WHITE)
        screen.blit(title, (WIDTH//2 - title.get_width()//2, 120))
        username_input.draw(screen)
        password_input.draw(screen)
        # draw buttons
        login_btn = pygame.Rect(250, 320, 140, 40)
        signup_btn = pygame.Rect(410, 320, 140, 40)
        pygame.draw.rect(screen, (100,200,100), login_btn)
        pygame.draw.rect(screen, (100,100,200), signup_btn)
        screen.blit(font.render('Login', True, BLACK), (login_btn.x + 30, login_btn.y + 6))
        screen.blit(font.render('Signup', True, BLACK), (signup_btn.x + 20, signup_btn.y + 6))
        # message
        if auth_message:
            msg = font.render(auth_message, True, (255,220,220))
            screen.blit(msg, (WIDTH//2 - msg.get_width()//2, 380))

        # handle mouse clicks for buttons
        if pygame.mouse.get_pressed()[0]:
            mx, my = pygame.mouse.get_pos()
            if login_btn.collidepoint((mx,my)):
                try:
                    pid = login(username_input.text, password_input.text)
                    current_player_id = pid
                    is_current_user_admin = is_admin(pid)
                    game_start_ticks = pygame.time.get_ticks()
                    auth_message = 'Logged in'
                except Exception as e:
                    auth_message = f'Login failed: {e}'
            if signup_btn.collidepoint((mx,my)):
                try:
                    pid = signup(username_input.text, password_input.text)
                    current_player_id = pid
                    is_current_user_admin = is_admin(pid)
                    game_start_ticks = pygame.time.get_ticks()
                    auth_message = 'Account created & logged in'
                except Exception as e:
                    auth_message = f'Signup failed: {e}'

    # Settings menu overlay (only when logged in)
    if show_settings and current_player_id is not None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0,0,0,180))
        screen.blit(overlay, (0,0))
        
        title = font.render('Settings', True, WHITE)
        screen.blit(title, (WIDTH//2 - title.get_width()//2, 100))
        
        # Username and password inputs with better spacing
        username_label = font.render('New Username:', True, WHITE)
        screen.blit(username_label, (200, 160))
        settings_username_input.rect = pygame.Rect(200, 190, 400, 40)
        settings_username_input.draw(screen)
        
        password_label = font.render('New Password:', True, WHITE)
        screen.blit(password_label, (200, 250))
        settings_password_input.rect = pygame.Rect(200, 280, 400, 40)
        settings_password_input.draw(screen)
        
        # Buttons with better spacing
        update_btn = pygame.Rect(200, 350, 140, 40)
        cancel_btn = pygame.Rect(360, 350, 140, 40)
        pygame.draw.rect(screen, (100,200,100), update_btn)
        pygame.draw.rect(screen, (200,100,100), cancel_btn)
        screen.blit(font.render('Update', True, BLACK), (update_btn.x + 30, update_btn.y + 6))
        screen.blit(font.render('Cancel', True, BLACK), (cancel_btn.x + 30, cancel_btn.y + 6))
        
        # Instructions
        instr1 = font.render('Press ESC to close settings', True, (200,200,200))
        screen.blit(instr1, (WIDTH//2 - instr1.get_width()//2, 420))
        
        # Message
        if settings_message:
            msg = font.render(settings_message, True, (255,220,220))
            screen.blit(msg, (WIDTH//2 - msg.get_width()//2, 450))
        
        # Handle button clicks
        if pygame.mouse.get_pressed()[0]:
            mx, my = pygame.mouse.get_pos()
            if update_btn.collidepoint((mx,my)):
                new_username = settings_username_input.text.strip()
                new_password = settings_password_input.text.strip()
                
                if new_username and new_password:
                    try:
                        # Import update function from auth module
                        from auth import update_user_credentials
                        update_user_credentials(current_player_id, new_username, new_password)
                        username_input.text = new_username  # Update main username
                        settings_message = 'Credentials updated successfully!'
                        # Clear password field
                        settings_password_input.text = ''
                    except Exception as e:
                        settings_message = f'Update failed: {e}'
                else:
                    settings_message = 'Please enter both username and password'
            
            if cancel_btn.collidepoint((mx,my)):
                show_settings = False
                settings_message = ''

    # Admin menu overlay (only for admins)
    if show_admin and current_player_id is not None and is_current_user_admin:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0,0,0,180))
        screen.blit(overlay, (0,0))
        
        title = font.render('Admin Panel', True, WHITE)
        screen.blit(title, (WIDTH//2 - title.get_width()//2, 100))
        
        # Target username input
        target_label = font.render('Username to remove scores:', True, WHITE)
        screen.blit(target_label, (200, 250))
        admin_target_input.draw(screen)
        
        # Buttons
        delete_btn = pygame.Rect(200, 350, 180, 40)
        cancel_btn = pygame.Rect(400, 350, 140, 40)
        pygame.draw.rect(screen, (200,50,50), delete_btn)
        pygame.draw.rect(screen, (100,100,100), cancel_btn)
        screen.blit(font.render('Delete Scores', True, WHITE), (delete_btn.x + 20, delete_btn.y + 6))
        screen.blit(font.render('Cancel', True, WHITE), (cancel_btn.x + 30, cancel_btn.y + 6))
        
        # Instructions
        instr1 = font.render('Press F1 to close admin panel', True, (200,200,200))
        screen.blit(instr1, (WIDTH//2 - instr1.get_width()//2, 420))
        
        # Message
        if admin_message:
            msg = font.render(admin_message, True, (255,220,220))
            screen.blit(msg, (WIDTH//2 - msg.get_width()//2, 450))
        
        # Handle button clicks
        if pygame.mouse.get_pressed()[0]:
            mx, my = pygame.mouse.get_pos()
            if delete_btn.collidepoint((mx,my)):
                target_user = admin_target_input.text.strip()
                if target_user:
                    try:
                        deleted_count = delete_user_scores(current_player_id, target_user)
                        admin_message = f'Deleted {deleted_count} scores for {target_user}'
                        admin_target_input.text = ''
                    except Exception as e:
                        admin_message = f'Delete failed: {e}'
                else:
                    admin_message = 'Please enter a username'
            
            if cancel_btn.collidepoint((mx,my)):
                show_admin = False
                admin_message = ''

    # show capture countdown when loop is active and trapped ants exist
    if anteater.loop_active and anteater.trapped_ants:
        secs = anteater.capture_timer / FPS
        cnt_text = font.render(f"Capturing in: {secs:.1f}s", True, (150, 0, 0))
        screen.blit(cnt_text, (10, 50))

    pygame.display.flip()

pygame.quit()
sys.exit()
