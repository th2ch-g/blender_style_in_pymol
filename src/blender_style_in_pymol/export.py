"""Synchronous exports with bounded image dimensions."""

from pathlib import Path

from .presets import integer, number


def image(
    cmd, filename, width, height, ray=True, memory_mb=512, renderer="auto", samples=None
):
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
        device = cmd.get_renderer()
        if not device or not device[0]:
            raise ValueError(
                "GPU PNG export needs a PyMOL GUI; use blender_style ray in headless mode"
            )
    playing = cmd.get_movie_playing()
    sculpting = cmd.get_setting_boolean("sculpting")
    try:
        if not ray:
            if cmd.get_setting_boolean("opaque_background"):
                cmd.draw(width, height, antialias=2, quiet=1)
                cmd.png(str(path), prior=1, quiet=1)
            else:
                _transparent_gpu(cmd, path, width, height)
            errors = [
                drawing.error
                for _, drawings in getattr(cmd._pymol, "_blender_drawings", {}).values()
                for drawing in drawings
                if drawing.error
            ]
            if errors:
                raise RuntimeError(errors[0])
        else:
            from .cycles import render as render_cycles
            from .cycles import requested
            from .ray import scene

            if renderer not in ("auto", "pymol", "cycles"):
                raise ValueError("renderer must be auto, pymol, or cycles")
            if requested(cmd, renderer):
                render_cycles(cmd, width, height, samples, memory_mb=budget)
                cmd.png(str(path), prior=1, quiet=1)
            else:
                with scene(cmd, width, height, memory_mb=memory_mb):
                    cmd.ray(width, height, renderer=0, quiet=1)
                    cmd.png(str(path), prior=1, quiet=1)
    finally:
        if sculpting:
            cmd.set("sculpting", 1, quiet=1)
        if playing:
            cmd.mplay()
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError("PyMOL did not write the requested image")
    return str(path)


def _transparent_gpu(cmd, path, width, height):
    from io import BytesIO

    import numpy as np
    from PIL import Image

    kind, values = cmd.get_setting_tuple("bg_rgb")
    background = tuple(values) if kind == 4 else values[0]
    gradient = cmd.get_setting_boolean("bg_gradient")
    images = []
    try:
        cmd.set("bg_gradient", 0, quiet=1)
        for color in ("black", "white"):
            cmd.bg_color(color)
            cmd.draw(width, height, antialias=2, quiet=1)
            data = cmd.png(None, prior=1, quiet=1)
            images.append(
                np.asarray(Image.open(BytesIO(data)).convert("RGB"), np.float32) / 255
            )
    finally:
        cmd.set("bg_rgb", background, quiet=1)
        cmd.set("bg_gradient", int(gradient), quiet=1)
    black, white = images
    alpha = np.clip(1 - np.max(white - black, axis=2), 0, 1)
    rgb = np.clip(black / np.maximum(alpha[:, :, None], 1 / 255), 0, 1)
    pixels = np.dstack((rgb, alpha))
    Image.fromarray(np.rint(pixels * 255).astype(np.uint8), "RGBA").save(path)


def _mesh_only(cmd, cache):
    from .cycles import enabled_objects

    callbacks = set(getattr(cmd._pymol.session, "blender_style_callbacks", {}).values())
    for obj in enabled_objects(cmd):
        if obj in callbacks:
            continue
        kind = cmd.get_type(obj)
        if kind == "object:molecule":
            visible = []
            cmd.iterate(obj, "visible.append(reps != 0)", space={"visible": visible})
            if any(visible):
                return False
        elif kind == "object:cgo" and obj not in cache:
            return False
        elif kind not in (
            "object:group",
            "object:callback",
            "object:map",
            "object:cgo",
        ):
            return False
    return True
