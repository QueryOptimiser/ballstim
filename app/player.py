"""Play a setting row live in PsychoPy, with an optional wait for the scanner's start signal."""
from ballstim_engine import STEP, Simulation
from settings_io import LOG_DIR, stamp, write_run_record


def play(row_name, settings, fullscreen=True, wait_for_scanner=False, scanner_key='5',
         window_size=(1280, 720), screen=0):
    """Run the animation. Escape stops it early. Returns the path of the event log."""
    from psychopy import core, event, visual

    win = visual.Window(size=window_size, fullscr=fullscreen, screen=screen, units='height',
                        color='#000000', colorSpace='hex', allowGUI=not fullscreen)
    win.mouseVisible = False
    win.recordFrameIntervals = True
    sim = Simulation(settings, aspect=win.size[0] / win.size[1])
    bg, _ = sim.drawables()
    win.color = bg

    px_per_height = win.size[1]    # line widths are given in pixels

    def pixels(w):
        return max(1.0, w * px_per_height)

    circles = [visual.Circle(win, radius=0.01, edges=96, fillColor=bg, lineColor=None, colorSpace='hex')
               for _ in range(64)]
    rings = [visual.Circle(win, radius=0.01, edges=96, fillColor=None, lineColor=bg, colorSpace='hex')
             for _ in range(40)]
    lines = [visual.Line(win, start=(0, 0), end=(0.01, 0.01), lineColor=bg)
             for _ in range(160)]
    pools = {'circle': circles, 'ring': rings, 'line': lines}
    cache = {k: [dict() for _ in v] for k, v in pools.items()}

    def update(stim, state, **values):
        for key, value in values.items():
            if state.get(key) != value:
                setattr(stim, key, value)
                state[key] = value

    if wait_for_scanner:
        msg = visual.TextStim(win, text='Waiting for scanner...', height=0.04,
                              color='#9AA0A6', colorSpace='hex')
        msg.draw()
        win.flip()
        keys = event.waitKeys(keyList=[scanner_key, 'escape'])
        if 'escape' in keys:
            win.close()
            return None

    clock = core.Clock()
    duration = sim.s['duration_s']
    win.frameIntervals = []
    while True:
        now = clock.getTime()
        if now >= duration or event.getKeys(['escape']):
            break
        # advance the simulation in fixed steps up to the current time
        while sim.t + STEP <= now:
            sim.step()
        _, shapes = sim.drawables()
        used = {'circle': 0, 'ring': 0, 'line': 0}
        for shp in shapes:
            kind = shp[0]
            i = used[kind]
            if i >= len(pools[kind]):
                continue
            stim, state = pools[kind][i], cache[kind][i]
            used[kind] += 1
            if kind == 'circle':
                _, x, y, r, fill, outline = shp
                update(stim, state, pos=(x, y), radius=r, fillColor=fill,
                       lineColor=outline, lineWidth=pixels(0.003) if outline else 0)
            elif kind == 'ring':
                _, x, y, r, lw, col = shp
                update(stim, state, pos=(x, y), radius=r, lineColor=col, lineWidth=pixels(lw))
            else:
                _, x1, y1, x2, y2, lw, col = shp
                update(stim, state, start=(x1, y1), end=(x2, y2), lineColor=col, lineWidth=pixels(lw))
            stim.draw()
        win.flip()

    dropped = win.nDroppedFrames
    win.close()
    base = LOG_DIR / f'{stamp()}_{row_name}_play'
    return write_run_record(base, row_name, settings, sim.events,
                            extra=dict(mode='play', fullscreen=fullscreen, wait_for_scanner=wait_for_scanner,
                                       scanner_key=scanner_key, stats=sim.stats, dropped_frames=dropped,
                                       note='Event times are seconds from the start of the animation '
                                            '(after the scanner signal, if used).'))
