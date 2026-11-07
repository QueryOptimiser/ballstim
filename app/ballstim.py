"""
BallStim: start here.

Double-click "Start BallStim.bat" (Windows), or open this file in the PsychoPy
Coder and press Run. A settings form appears; nothing here needs editing.

For testing or batch use there is also a command line:
    python ballstim.py --row high --mode export --no-form
    python ballstim.py --row low --mode play --windowed --no-form
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ballstim_engine import SettingsError, clean_settings   # noqa: E402
from settings_io import load_rows                           # noqa: E402

TITLE = 'BallStim'
MODES = ['Play now', 'Export video']
RESOLUTIONS = ['1280x720', '1920x1080']

TIPS = {
    'balls': 'Balls at the start (1-30). Use a multiple of 3 for equal red, yellow and blue.',
    'ball_size': 'Radius of a big ball as a fraction of screen height (0.02-0.15).',
    'speed': 'Screen heights per second (0-1). 0.05 is very slow.',
    'events_per_minute': 'Maximum splits + merges per minute (0-120).',
    'ripple_chance': 'Chance of a ring ripple on each ball-to-ball collision (0-1).',
    'starburst_chance': 'Chance of a starburst on each merge (0-1).',
    'background': 'dark or light. On light, balls get a thin outline.',
    'duration_s': 'Length in seconds.',
    'seed': 'Same seed = identical animation every time.',
    'wait_for_scanner': 'Show "Waiting for scanner..." and start on the scanner key.',
    'scanner_key': 'Key the scanner sends at the start of a scan (often 5).',
    'fullscreen': 'Untick to play in a window, for checking.',
    'resolution': 'Video size.',
    'fps': 'Frames per second of the video.',
}
LABELS = {
    'balls': 'Number of balls', 'ball_size': 'Ball size', 'speed': 'Speed',
    'events_per_minute': 'Max splits + merges per minute', 'ripple_chance': 'Ripple chance (0 to 1)',
    'starburst_chance': 'Starburst chance (0 to 1)', 'background': 'Background',
    'duration_s': 'Duration (seconds)', 'seed': 'Seed', 'fullscreen': 'Full screen',
    'wait_for_scanner': 'Wait for scanner signal', 'scanner_key': 'Scanner key',
    'resolution': 'Video size', 'fps': 'Frames per second',
}
QUICK = ['balls', 'ball_size', 'speed', 'events_per_minute', 'ripple_chance',
         'starburst_chance', 'background', 'duration_s', 'seed']


def first(value, options):
    """Put the current value first so it is the dropdown's default."""
    return [value] + [o for o in options if o != value]


def run_form(rows):
    from psychopy import gui

    step1 = {'Setting row': list(rows), 'What to do': MODES}
    dlg = gui.DlgFromDict(step1, title=f'{TITLE}: choose', order=['Setting row', 'What to do'],
                          tip={'Setting row': 'Rows come from settings.xlsx',
                               'What to do': 'Play on this screen now, or save a video file'})
    if not dlg.OK:
        return None
    row_name, mode = step1['Setting row'], step1['What to do']
    base = clean_settings(rows[row_name])

    values = {k: base[k] for k in QUICK}
    values['background'] = first(base['background'], ['dark', 'light'])
    keys = list(QUICK)
    if mode == 'Play now':
        values.update(fullscreen=True, wait_for_scanner=False, scanner_key='5')
        keys += ['fullscreen', 'wait_for_scanner', 'scanner_key']
    else:
        values.update(resolution=RESOLUTIONS, fps=['60', '30'])
        keys += ['resolution', 'fps']
    step2 = {LABELS[k]: values[k] for k in keys}
    dlg = gui.DlgFromDict(step2, title=f'{TITLE}: {row_name} ({mode.lower()})',
                          order=[LABELS[k] for k in keys], tip={LABELS[k]: TIPS[k] for k in keys})
    if not dlg.OK:
        return None
    chosen = {k: step2[LABELS[k]] for k in keys}
    settings = dict(rows[row_name])
    settings.update({k: chosen[k] for k in QUICK})
    options = {k: chosen[k] for k in keys if k not in QUICK}
    return row_name, mode, settings, options


def message(text, error=False, dialog=True):
    print(text)
    if not dialog:
        return
    try:
        from psychopy import gui
        (gui.criticalDlg if error else gui.infoDlg)(TITLE, text)
    except Exception:
        pass


def console_progress(done, total):
    print(f'  rendering: {done}/{total} frames ({100 * done // total}%)', flush=True)


def main():
    ap = argparse.ArgumentParser(description='BallStim')
    ap.add_argument('--row')
    ap.add_argument('--mode', choices=['play', 'export'])
    ap.add_argument('--no-form', action='store_true')
    ap.add_argument('--windowed', action='store_true')
    ap.add_argument('--resolution', default='1280x720')
    ap.add_argument('--fps', type=int, default=60)
    ap.add_argument('--duration', type=int)
    args = ap.parse_args()

    try:
        rows = load_rows()
    except SettingsError as err:
        message(str(err), error=True, dialog=not args.no_form)
        return 1

    if args.no_form:
        if args.row not in rows:
            print(f'Unknown row {args.row!r}. Rows: {", ".join(rows)}')
            return 1
        row_name, settings = args.row, dict(rows[args.row])
        if args.duration:
            settings['duration_s'] = args.duration
        mode = 'Play now' if args.mode == 'play' else 'Export video'
        options = dict(fullscreen=not args.windowed, wait_for_scanner=False, scanner_key='5',
                       resolution=args.resolution, fps=str(args.fps))
    else:
        try:
            picked = run_form(rows)
        except SettingsError as err:
            message(f'That row in settings.xlsx has a problem:\n{err}', error=True)
            return 1
        if picked is None:
            return 0
        row_name, mode, settings, options = picked

    try:
        clean_settings(settings)
    except SettingsError as err:
        message(f'Those settings cannot be used:\n{err}', error=True, dialog=not args.no_form)
        return 1

    if mode == 'Play now':
        from player import play
        log = play(row_name, settings, fullscreen=options.get('fullscreen', True),
                   wait_for_scanner=options.get('wait_for_scanner', False),
                   scanner_key=str(options.get('scanner_key', '5')))
        if log:
            print(f'Event log saved: {log}')
    else:
        from export_video import export
        w, h = (int(v) for v in str(options.get('resolution', '1280x720')).split('x'))
        print(f'Exporting {row_name} at {w}x{h}, {options.get("fps")} fps...')
        path = export(row_name, settings, width=w, height=h, fps=int(options.get('fps', 60)),
                      progress=console_progress)
        message(f'Video saved:\n{path}\n\nThe event log and settings record are saved next to it.',
                dialog=not args.no_form)
    return 0


if __name__ == '__main__':
    os.chdir(Path(__file__).resolve().parent)
    sys.exit(main())
