"""Synchronous exports with bounded image dimensions."""

from pathlib import Path

from .presets import integer, number


def image(cmd, filename, width, height, ray=True, memory_mb=512):
    if not filename:
        raise ValueError("filename is required for PNG export")
    path = Path(filename).expanduser()
    if path.suffix != ".png":
        raise ValueError("filename must end in .png")
    width = integer(width, "width", 16, 8192)
    height = integer(height, "height", 16, 8192)
    if width * height > 32_000_000:
        raise ValueError("Export is limited to 32 million pixels")
    budget = number(memory_mb, "memory_mb", 1, 65536)
    estimate = width * height * (64 if ray else 96)
    if estimate > budget * 1024**2:
        raise ValueError(
            "Estimated image buffers exceed memory_mb; reduce dimensions or increase the budget"
        )
    if not path.parent.is_dir():
        raise ValueError("The output directory does not exist")
    if not ray:
        renderer = cmd.get_renderer()
        if not renderer or not renderer[0]:
            raise ValueError(
                "GPU PNG export needs a PyMOL GUI; use blender_style ray in headless mode"
            )
    playing = cmd.get_movie_playing()
    sculpting = cmd.get_setting_boolean("sculpting")
    try:
        if not ray:
            cmd.draw(width, height, antialias=2, quiet=1)
            cmd.png(str(path), prior=1, quiet=1)
        else:
            cmd.png(str(path), width=width, height=height, ray=1, quiet=1)
    finally:
        if sculpting:
            cmd.set("sculpting", 1, quiet=1)
        if playing:
            cmd.mplay()
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError("PyMOL did not write the requested image")
    return str(path)
