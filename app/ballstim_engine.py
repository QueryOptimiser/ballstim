"""
BallStim engine: the animation logic, independent of how it is drawn.

The same engine drives both live playback in PsychoPy and video export, so a
video and a live run with the same settings and seed show identical frames.

Building-block rule
-------------------
Every small ball is one "block" with one primary colour (red, yellow or blue).
A big ball is two blocks joined; its colour is the paint-mix of its two blocks.
Splitting and merging only regroup blocks, so the colour balance never drifts
and the number of balls always stays between n and 2n for n starting balls.
A small ball's radius is the big radius / sqrt(2), so two small balls cover the
same screen area as one big ball.

Determinism
-----------
The simulation always advances in fixed steps of 1/60 s and uses a seeded
random number generator. Same settings + same seed = same animation, every time.
"""
import colorsys
import math
import random

STEP = 1 / 60           # fixed simulation step in seconds
COOLDOWN = 0.8          # seconds a newly split or merged ball can only bounce
RIPPLE_TIME = 0.5
STARBURST_TIME = 0.45
BACKGROUNDS = {'dark': '#202124', 'light': '#F7F5F0'}
EFFECT_COLOUR = {'dark': '#E8EAED', 'light': '#5F6368'}
OUTLINE_ON_LIGHT = '#3C4043'

# Defaults used if a setting is missing. Keys match the spreadsheet column names.
DEFAULTS = dict(
    balls=3, ball_size=0.07, speed=0.05, saturation=1.0,
    split_merge=False, colour_mixing=False, events_per_minute=0,
    ripple_chance=0.0, starburst_chance=0.0, breathing=False,
    background='dark', duration_s=60, seed=1,
    red='#D55E00', yellow='#F0E442', blue='#56B4E9',
    orange='#E69F00', green='#009E73', purple='#CC79A7',
)

# Allowed ranges: values outside these are refused with a clear message.
LIMITS = dict(
    balls=(1, 30), ball_size=(0.02, 0.15), speed=(0.0, 1.0), saturation=(0.0, 1.0),
    events_per_minute=(0, 120), ripple_chance=(0.0, 1.0), starburst_chance=(0.0, 1.0),
    duration_s=(1, 3600), seed=(0, 10 ** 9),
)


class SettingsError(ValueError):
    pass


def clean_settings(raw):
    """Fill in defaults, convert types and check ranges. Returns a new dict."""
    s = dict(DEFAULTS)
    for key, value in raw.items():
        if key in DEFAULTS and value not in (None, ''):
            s[key] = value
    try:
        for key in ('balls', 'events_per_minute', 'seed', 'duration_s'):
            s[key] = int(round(float(s[key])))
        for key in ('ball_size', 'speed', 'saturation', 'ripple_chance', 'starburst_chance'):
            s[key] = float(s[key])
    except (TypeError, ValueError) as err:
        raise SettingsError(f'A number setting could not be read: {err}')
    for key in ('split_merge', 'colour_mixing', 'breathing'):
        v = s[key]
        s[key] = v if isinstance(v, bool) else str(v).strip().lower() in ('yes', 'y', 'true', '1')
    s['background'] = str(s['background']).strip().lower()
    if s['background'] not in BACKGROUNDS:
        raise SettingsError("background must be 'dark' or 'light'")
    for key, (lo, hi) in LIMITS.items():
        if not lo <= s[key] <= hi:
            raise SettingsError(f'{key} = {s[key]} is outside the allowed range {lo} to {hi}')
    for key in ('red', 'yellow', 'blue', 'orange', 'green', 'purple'):
        v = str(s[key]).strip()
        if not v.startswith('#'):
            v = '#' + v
        if len(v) != 7 or any(ch not in '0123456789abcdefABCDEF' for ch in v[1:]):
            raise SettingsError(f'{key} colour {s[key]!r} is not a hex code like #D55E00')
        s[key] = v.upper()
    if s['colour_mixing'] and not s['split_merge']:
        raise SettingsError('colour_mixing needs split_merge switched on')
    return s


def hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def rgb_to_hex(c):
    return '#%02X%02X%02X' % tuple(round(max(0.0, min(1.0, v)) * 255) for v in c)


def soften(hex_colour, saturation):
    if saturation >= 1:
        return hex_colour
    r, g, b = hex_to_rgb(hex_colour)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return rgb_to_hex(colorsys.hls_to_rgb(h, l, s * saturation))


def blend(c1, c2, p):
    a, b = hex_to_rgb(c1), hex_to_rgb(c2)
    p = max(0.0, min(1.0, p))
    return rgb_to_hex(tuple(x * (1 - p) + y * p for x, y in zip(a, b)))


class Ball:
    def __init__(self, blocks, x, y, vx, vy, t_born, phase=0.0):
        self.blocks = tuple(sorted(blocks))
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.t_born = t_born
        self.phase = phase

    @property
    def big(self):
        return len(self.blocks) == 2


class Simulation:
    """One run of the animation. Call step() to advance by STEP seconds."""

    def __init__(self, settings, aspect=16 / 9):
        self.s = clean_settings(settings)
        self.rng = random.Random(self.s['seed'])
        self.xw = aspect / 2          # half screen width, in screen heights
        self.t = 0.0
        self.last_event = -1e9
        self.effects = []             # (kind, x, y, t_start, base_radius)
        self.events = []              # log rows: dicts with t, event, detail, balls
        self.stats = dict(splits=0, merges=0, bounces=0, ripples=0, starbursts=0)
        self.balls = []
        s = self.s
        primary = {'R': s['red'], 'Y': s['yellow'], 'B': s['blue']}
        mixes = {('R', 'Y'): s['orange'], ('B', 'Y'): s['green'], ('B', 'R'): s['purple']}
        self.primary = {k: soften(v, s['saturation']) for k, v in primary.items()}
        self.mixes = {k: soften(v, s['saturation']) for k, v in mixes.items()}
        self.names = {'R': 'red', 'Y': 'yellow', 'B': 'blue', ('R', 'Y'): 'orange',
                      ('B', 'Y'): 'green', ('B', 'R'): 'purple'}
        self._spawn()

    # ---------------------------------------------------------- setup
    def _spawn(self):
        s, rng = self.s, self.rng
        if not s['split_merge']:
            pattern = [('R',), ('Y',), ('B',)]
        elif not s['colour_mixing']:
            pattern = [('R', 'R'), ('Y', 'Y'), ('B', 'B')]
        else:
            pattern = [('R', 'Y'), ('B', 'Y'), ('B', 'R')]
        for i in range(s['balls']):
            blocks = pattern[i % 3]
            r = self.radius_of(blocks)
            x = y = 0.0
            for _ in range(500):
                x = rng.uniform(-self.xw + r, self.xw - r)
                y = rng.uniform(-0.5 + r, 0.5 - r)
                if all(math.hypot(x - b.x, y - b.y) > self.radius_of(b.blocks) + r + 0.01 for b in self.balls):
                    break
            a = rng.uniform(0, 2 * math.pi)
            self.balls.append(Ball(blocks, x, y, math.cos(a) * s['speed'], math.sin(a) * s['speed'],
                                   -COOLDOWN, phase=rng.uniform(0, 2 * math.pi)))

    # ---------------------------------------------------------- helpers
    def radius_of(self, blocks):
        r = self.s['ball_size']
        return r / math.sqrt(2) if self.s['split_merge'] and len(blocks) == 1 else r

    def colour_of(self, ball):
        b = ball.blocks
        return self.primary[b[0]] if len(b) == 1 or b[0] == b[1] else self.mixes[b]

    def colour_name(self, ball):
        b = ball.blocks
        return self.names[b[0]] if len(b) == 1 or b[0] == b[1] else self.names[b]

    def _set_speed(self, ball):
        mag = math.hypot(ball.vx, ball.vy)
        if mag < 1e-9:
            a = self.rng.uniform(0, 2 * math.pi)
            ball.vx, ball.vy, mag = math.cos(a), math.sin(a), 1.0
        k = self.s['speed'] / mag
        ball.vx *= k
        ball.vy *= k

    def _event_allowed(self):
        epm = self.s['events_per_minute']
        return epm > 0 and self.t - self.last_event >= 60.0 / epm

    def _log(self, event, detail):
        self.events.append(dict(t=round(self.t, 4), event=event, detail=detail, balls=len(self.balls)))

    def _maybe_effect(self, kind, chance, x, y, base_r):
        if chance > 0 and self.rng.random() < chance:
            self.effects.append((kind, x, y, self.t, base_r))
            self.stats[kind + 's'] += 1
            self._log(kind, '')

    # ---------------------------------------------------------- physics
    def step(self):
        self.t += STEP
        s = self.s
        first_event = len(self.events)
        for b in self.balls:
            b.x += b.vx * STEP
            b.y += b.vy * STEP
            r = self.radius_of(b.blocks)
            if b.x < -self.xw + r:
                b.x, b.vx = -self.xw + r, abs(b.vx)
            if b.x > self.xw - r:
                b.x, b.vx = self.xw - r, -abs(b.vx)
            if b.y < -0.5 + r:
                b.y, b.vy = -0.5 + r, abs(b.vy)
            if b.y > 0.5 - r:
                b.y, b.vy = 0.5 - r, -abs(b.vy)

        new_balls, removed = [], set()
        n = len(self.balls)
        for i in range(n):
            for j in range(i + 1, n):
                if i in removed or j in removed:
                    continue
                a, b = self.balls[i], self.balls[j]
                ra, rb = self.radius_of(a.blocks), self.radius_of(b.blocks)
                dx, dy = b.x - a.x, b.y - a.y
                dist = math.hypot(dx, dy)
                if dist >= ra + rb or dist == 0:
                    continue
                nx, ny = dx / dist, dy / dist
                approaching = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny < 0
                overlap = ra + rb - dist
                a.x -= nx * overlap / 2
                a.y -= ny * overlap / 2
                b.x += nx * overlap / 2
                b.y += ny * overlap / 2
                if not approaching:
                    continue
                cx, cy = a.x + nx * ra, a.y + ny * ra
                fresh = self.t - a.t_born < COOLDOWN or self.t - b.t_born < COOLDOWN
                can_event = s['split_merge'] and not fresh and self._event_allowed()

                if can_event and a.big and b.big:
                    names = f'{self.colour_name(a)}+{self.colour_name(b)}'
                    for parent in (a, b):
                        px, py = -parent.vy, parent.vx
                        pl = math.hypot(px, py) or 1.0
                        px, py = px / pl, py / pl
                        r2 = self.radius_of(parent.blocks[:1])
                        for k, blk in enumerate(parent.blocks):
                            sgn = 1 if k == 0 else -1
                            child = Ball((blk,), parent.x + sgn * px * r2 * 1.05, parent.y + sgn * py * r2 * 1.05,
                                         parent.vx + sgn * px * s['speed'], parent.vy + sgn * py * s['speed'], self.t)
                            self._set_speed(child)
                            new_balls.append(child)
                    removed.update((i, j))
                    self.last_event = self.t
                    self.stats['splits'] += 2
                    self._log('split', names)
                    self._maybe_effect('ripple', s['ripple_chance'], cx, cy, ra)
                elif can_event and not a.big and not b.big and (s['colour_mixing'] or a.blocks == b.blocks):
                    m = Ball(a.blocks + b.blocks, (a.x + b.x) / 2, (a.y + b.y) / 2,
                             (a.vx + b.vx) / 2, (a.vy + b.vy) / 2, self.t)
                    self._set_speed(m)
                    new_balls.append(m)
                    removed.update((i, j))
                    self.last_event = self.t
                    self.stats['merges'] += 1
                    self._log('merge', f'{self.colour_name(a)}+{self.colour_name(b)}={self.colour_name(m)}')
                    self._maybe_effect('ripple', s['ripple_chance'], m.x, m.y, s['ball_size'])
                    self._maybe_effect('starburst', s['starburst_chance'], m.x, m.y, s['ball_size'])
                else:
                    ma, mb = ra * ra, rb * rb
                    va = a.vx * nx + a.vy * ny
                    vb = b.vx * nx + b.vy * ny
                    va2 = (va * (ma - mb) + 2 * mb * vb) / (ma + mb)
                    vb2 = (vb * (mb - ma) + 2 * ma * va) / (ma + mb)
                    a.vx += (va2 - va) * nx
                    a.vy += (va2 - va) * ny
                    b.vx += (vb2 - vb) * nx
                    b.vy += (vb2 - vb) * ny
                    self._set_speed(a)
                    self._set_speed(b)
                    an = a.vx * nx + a.vy * ny          # make sure they now move apart
                    if an > 0:
                        a.vx -= 2 * an * nx
                        a.vy -= 2 * an * ny
                    bn = b.vx * nx + b.vy * ny
                    if bn < 0:
                        b.vx -= 2 * bn * nx
                        b.vy -= 2 * bn * ny
                    self.stats['bounces'] += 1
                    self._log('bounce', f'{self.colour_name(a)}+{self.colour_name(b)}')
                    self._maybe_effect('ripple', s['ripple_chance'], cx, cy, min(ra, rb))
        if removed or new_balls:
            self.balls = [b for k, b in enumerate(self.balls) if k not in removed] + new_balls
        for e in self.events[first_event:]:
            e['balls'] = len(self.balls)          # balls on screen just after the event
        self.effects = [e for e in self.effects
                        if self.t - e[3] < (RIPPLE_TIME if e[0] == 'ripple' else STARBURST_TIME)]

    # ---------------------------------------------------------- what to draw
    def drawables(self):
        """Return (background colour, shapes) for the current moment.

        Shapes, drawn in order, with sizes in screen heights:
          ('circle', x, y, radius, fill_colour, outline_colour_or_None)
          ('ring',   x, y, radius, line_width, colour)
          ('line',   x1, y1, x2, y2, line_width, colour)
        """
        bgname = self.s['background']
        bg, eff = BACKGROUNDS[bgname], EFFECT_COLOUR[bgname]
        outline = OUTLINE_ON_LIGHT if bgname == 'light' else None
        out = []
        for kind, x, y, t0, base_r in self.effects:
            if kind == 'ripple':
                p = (self.t - t0) / RIPPLE_TIME
                out.append(('ring', x, y, base_r * 0.6 + 0.09 * p, 0.006 * (1 - p) + 0.001, blend(eff, bg, p)))
        for b in self.balls:
            r = self.radius_of(b.blocks)
            if self.s['breathing']:
                r *= 1 + 0.04 * math.sin(2 * math.pi * 0.15 * self.t + b.phase)
            if b.t_born > 0:
                r *= 0.75 + 0.25 * min(1.0, (self.t - b.t_born) / 0.18)   # quick pop-in
            out.append(('circle', b.x, b.y, r, self.colour_of(b), outline))
        for kind, x, y, t0, base_r in self.effects:
            if kind == 'starburst':
                p = (self.t - t0) / STARBURST_TIME
                inner = base_r * 1.15 + 0.05 * p
                outer = inner + 0.035 * (1 - p) + 0.01
                col = blend(eff, bg, p)
                for k in range(8):
                    ang = 2 * math.pi * k / 8 + math.pi / 8
                    out.append(('line', x + math.cos(ang) * inner, y + math.sin(ang) * inner,
                                x + math.cos(ang) * outer, y + math.sin(ang) * outer, 0.004, col))
        return bg, out
