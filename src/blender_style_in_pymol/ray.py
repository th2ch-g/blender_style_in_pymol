"""Prepare camera-dependent mesh shading for standard PyMOL ray commands."""

from contextlib import contextmanager
from threading import Thread
from weakref import ref


def install(cmd):
    if cmd.__dict__.get("_blender_ray_hooks"):
        return
    if not all(name in getattr(cmd, "keyword", {}) for name in ("ray", "png")):
        return
    original_ray, original_png = cmd.ray, cmd.png
    command = ref(cmd)

    def ray(
        width=0,
        height=0,
        antialias=-1,
        angle=0.0,
        shift=0.0,
        renderer=-1,
        quiet=1,
        async_=0,
        _self=None,
        **kwargs,
    ):
        target = command() if _self is None else _self
        asynchronous = int(kwargs.pop("async", async_))

        def render():
            image = None
            with scene(target, width, height, angle):
                result = original_ray(
                    width,
                    height,
                    antialias,
                    angle,
                    shift,
                    renderer,
                    quiet,
                    0,
                    _self=target,
                    **kwargs,
                )
                if _physical(target) and int(renderer) != 2:
                    image = original_png(None, prior=1, quiet=1, _self=target)
            if image:
                from pathlib import Path
                from tempfile import TemporaryDirectory

                with TemporaryDirectory(prefix="blender-style-ray-") as directory:
                    path = Path(directory) / "render.png"
                    path.write_bytes(image)
                    target.load_png(str(path), quiet=1)
            return result

        if asynchronous and _physical(target):
            thread = Thread(target=render, daemon=True, name="blender-style-ray")
            target._pymol._blender_ray_thread = thread
            thread.start()
            return 1
        if asynchronous:
            return original_ray(
                width,
                height,
                antialias,
                angle,
                shift,
                renderer,
                quiet,
                asynchronous,
                _self=target,
                **kwargs,
            )
        return render()

    def png(
        filename,
        width=0,
        height=0,
        dpi=-1.0,
        ray=0,
        quiet=1,
        prior=0,
        format=0,
        *,
        _self=None,
    ):
        target = command() if _self is None else _self
        if not int(ray) or int(prior) == 1:
            return original_png(
                filename, width, height, dpi, ray, quiet, prior, format, _self=target
            )
        from pymol.exporting import _unit2px

        resolution = float(dpi)
        if resolution < 0:
            resolution = target.get_setting_float("image_dots_per_inch")
        with scene(target, _unit2px(width, resolution), _unit2px(height, resolution)):
            return original_png(
                filename, width, height, dpi, ray, quiet, prior, format, _self=target
            )

    ray.__doc__, png.__doc__ = original_ray.__doc__, original_png.__doc__
    cmd.ray, cmd.png = ray, png
    for name, function in (("ray", ray), ("png", png)):
        cmd.keyword[name] = [function, *cmd.keyword[name][1:]]
    cmd._blender_ray_hooks = (original_ray, original_png)


def _physical(cmd):
    from .controller import SESSION_KEY

    entries = getattr(cmd._pymol.session, SESSION_KEY, {}).get("entries", {})
    return any(
        entry.get("backend") == "mesh" and entry["options"]["lighting"] == "auto"
        for entry in entries.values()
    )


@contextmanager
def scene(cmd, width=0, height=0, angle=0, memory_mb=None):
    if not _physical(cmd) or getattr(cmd._pymol, "_blender_ray_active", False):
        yield
        return
    import numpy as np

    from .controller import manager_for
    from .export import _mesh_only
    from .mesh import display_list, refine
    from .presets import Options

    cache = getattr(cmd._pymol.session, "blender_style_meshes", {})
    enabled = set(cmd.get_names("objects", enabled_only=1))
    entries = list(manager_for(cmd).entries.values())
    budget = (
        memory_mb
        if memory_mb is not None
        else min(entry["options"]["memory_mb"] for entry in entries)
    ) * 1024**2
    viewport = cmd.get_viewport()
    width, height = float(width), float(height)
    if not width and not height:
        width, height = viewport
    elif not width:
        width = height * viewport[0] / max(viewport[1], 1)
    elif not height:
        height = width * viewport[1] / max(viewport[0], 1)
    available = max(0, budget - width * height * 64)
    rotation = np.asarray(cmd.get_view()[:9]).reshape(3, 3)
    if float(angle):
        theta = np.deg2rad(float(angle))
        c, s = np.cos(theta), np.sin(theta)
        rotation = rotation @ np.array([[c, 0, -s], [0, 1, 0], [s, 0, c]])
    physical = {
        obj
        for entry in entries
        if entry["options"]["lighting"] == "auto"
        for obj in entry["objects"]
        if obj in cache
    }
    saved, replaced = {}, []
    cmd._pymol._blender_ray_active = True
    try:
        for entry in entries:
            options = Options(**entry["options"])
            if options.lighting != "auto":
                continue
            for obj in entry["objects"]:
                if obj not in cache or obj not in enabled:
                    continue
                state = cmd.get_setting_int("state", obj) or cmd.get_state()
                if len(cache[obj]) == 1:
                    state = 1
                if not 1 <= state <= len(cache[obj]):
                    continue
                mesh = cache[obj][state - 1]
                levels = (
                    2 if options.material in ("studio", "glossy", "transparent") else 1
                )
                while levels and len(mesh.faces) * 4**levels * 1200 > available * 0.7:
                    levels -= 1
                detailed = refine(mesh, levels) if levels else mesh
                replaced.append((obj, state, mesh, options))
                cmd.load_cgo(
                    display_list(detailed, options.material, rotation),
                    obj,
                    state=state,
                    zoom=0,
                    quiet=1,
                )
                available = max(0, available - len(detailed.faces) * 180)
                del detailed
        if _mesh_only(cmd, physical):
            for key, value in {
                "ambient": 1,
                "direct": 0,
                "reflect": 0,
                "specular": 0,
                "spec_reflect": 0,
                "specular_intensity": 0,
                "spec_direct": 0,
                "ray_shadows": 0,
                "depth_cue": 0,
                "ray_trace_fog": 0,
                "ray_transparency_specular": 0,
                "ray_trace_mode": 0,
                "transparency_mode": 0,
                "backface_cull": 0,
                "ray_transparency_oblique": 0,
            }.items():
                saved[key] = cmd.get(key)
                cmd.set(key, value, quiet=1)
        yield
    finally:
        try:
            for obj, state, mesh, options in replaced:
                cmd.load_cgo(
                    display_list(mesh, options.material, cmd.get_view()[:9]),
                    obj,
                    state=state,
                    zoom=0,
                    quiet=1,
                )
            for key, value in saved.items():
                cmd.set(key, value, quiet=1)
        finally:
            cmd._pymol._blender_ray_active = False
