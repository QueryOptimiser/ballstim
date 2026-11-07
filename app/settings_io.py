"""Read setting rows from settings.xlsx and save run records."""
import csv
import json
from datetime import datetime
from pathlib import Path

from ballstim_engine import SettingsError, clean_settings

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_FILE = ROOT / 'settings.xlsx'
EXPORT_DIR = ROOT / 'exports'
LOG_DIR = ROOT / 'logs'


def load_rows(path=SETTINGS_FILE):
    """Return {row name: raw settings dict} in spreadsheet order."""
    from openpyxl import load_workbook
    if not Path(path).exists():
        raise SettingsError(f'Could not find {path}. It should sit next to the app folder.')
    try:
        wb = load_workbook(path, data_only=True, read_only=True)
    except PermissionError:
        raise SettingsError('settings.xlsx is open in another program. Close it and try again.')
    if 'Settings' not in wb.sheetnames:
        raise SettingsError("settings.xlsx has no sheet called 'Settings'.")
    rows = list(wb['Settings'].iter_rows(values_only=True))
    wb.close()
    header = [str(h).strip() if h is not None else '' for h in rows[0]]
    if 'name' not in header:
        raise SettingsError("The Settings sheet needs a 'name' column.")
    out = {}
    for values in rows[1:]:
        row = {h: v for h, v in zip(header, values) if h}
        name = row.get('name')
        if name in (None, ''):
            continue
        name = str(name).strip()
        if name in out:
            raise SettingsError(f"Two rows are called '{name}'. Each row needs its own name.")
        out[name] = row
    if not out:
        raise SettingsError('The Settings sheet has no filled rows.')
    return out


def stamp():
    return datetime.now().strftime('%Y%m%d_%H%M%S')


def write_run_record(base_path, row_name, settings, events, extra=None):
    """Save <base>_settings.json and <base>_events.csv next to each other."""
    base_path = Path(base_path)
    base_path.parent.mkdir(parents=True, exist_ok=True)
    record = dict(row=row_name, created=datetime.now().isoformat(timespec='seconds'),
                  settings=clean_settings(settings))
    if extra:
        record.update(extra)
    with open(str(base_path) + '_settings.json', 'w', encoding='utf-8') as f:
        json.dump(record, f, indent=2)
    with open(str(base_path) + '_events.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['time_s', 'event', 'detail', 'balls_on_screen'])
        for e in events:
            w.writerow([f"{e['t']:.3f}", e['event'], e['detail'], e['balls']])
    return str(base_path) + '_events.csv'
