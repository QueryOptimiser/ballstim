"""Render a setting row to an MP4 video, plus its event log and settings record."""
from pathlib import Path

from PIL import Image, ImageDraw

from ballstim_engine import STEP, Simulation, hex_to_rgb
from settings_io import EXPORT_DIR, write_run_record

SUPERSAMPLE = 2   # draw at 2x size, then shrink, for smooth edges


def _rgb(h):
    return tuple(round(v * 255) for v in hex_to_rgb(h))


def render_frame(sim, width, height):
    """Draw the simulation's current moment as a PIL image."""
    bg, shapes = sim.drawables()
    w, h = width * SUPERSAMPLE, height * SUPERSAMPLE
    img = Image.new('RGB', (w, h), _rgb(bg))
    d = ImageDraw.Draw(img)

    def px(x, y):
        return (x + sim.xw) / (2 * sim.xw) * w, (0.5 - y) * h

    for shp in shapes:
        kind = shp[0]
        if kind == 'circle':
            _, x, y, r, fill, outline = shp
            cx, cy = px(x, y)
            rr = r * h
            box = [cx - rr, cy - rr, cx + rr, cy + rr]
            if outline:
                d.ellipse(box, fill=_rgb(fill), outline=_rgb(outline), width=max(1, round(0.003 * h)))
            else:
                d.ellipse(box, fill=_rgb(fill))
        elif kind == 'ring':
            _, x, y, r, lw, col = shp
            cx, cy = px(x, y)
            rr = r * h
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=_rgb(col), width=max(1, round(lw * h)))
        elif kind == 'line':
            _, x1, y1, x2, y2, lw, col = shp
            d.line([px(x1, y1), px(x2, y2)], fill=_rgb(col), width=max(1, round(lw * h)))
    return img.reduce(SUPERSAMPLE) if SUPERSAMPLE > 1 else img


def export(row_name, settings, width=1280, height=720, fps=60, out_dir=EXPORT_DIR, progress=None):
    """Write <row>_seed<seed>_<w>x<h>_<fps>fps.mp4 and its records. Returns the video path."""
    import imageio_ffmpeg

    if fps not in (30, 60):
        raise ValueError('fps must be 30 or 60')
    sim = Simulation(settings, aspect=width / height)
    steps_per_frame = round((1 / fps) / STEP)
    n_frames = sim.s['duration_s'] * fps
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / f"{row_name}_seed{sim.s['seed']}_{width}x{height}_{fps}fps"
    video_path = str(base) + '.mp4'

    writer = imageio_ffmpeg.write_frames(video_path, (width, height), fps=fps, codec='libx264',
                                         pix_fmt_out='yuv420p', quality=8, macro_block_size=8,
                                         ffmpeg_log_level='error')
    writer.send(None)
    try:
        for k in range(n_frames):
            # frame k shows the animation at time k / fps (frame 0 = the start)
            writer.send(render_frame(sim, width, height).tobytes())
            for _ in range(steps_per_frame):
                sim.step()
            if progress and (k % fps == 0 or k == n_frames - 1):
                progress(k + 1, n_frames)
    finally:
        writer.close()
    write_run_record(base, row_name, settings, sim.events,
                     extra=dict(mode='export', video=Path(video_path).name, width=width, height=height,
                                fps=fps, frames=n_frames, stats=sim.stats,
                                note='Event times are seconds from the first frame of the video.'))
    return video_path
