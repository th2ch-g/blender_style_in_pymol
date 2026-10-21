"""Native map contours with transactional ownership and no copied voxel arrays."""

from copy import deepcopy
from dataclasses import asdict
from fnmatch import fnmatchcase
from time import perf_counter

from .colors import define, validate
from .presets import material_settings, resolve_quality


def apply(manager, options):
    cmd = manager.cmd
    started = perf_counter()
    validate(cmd, options.color)
    if options.color in ("element", "chain", "secondary-structure", "rainbow"):
        raise ValueError("Density colors must be auto, keep, a color name, or #rrggbb")
    if options.name in cmd.get_names("all") and options.name not in manager.entries:
        raise ValueError(f"name '{options.name}' already belongs to another object")
    pattern = "*" if options.selection == "all" else options.selection
    maps = [
        name
        for name in cmd.get_names("objects")
        if cmd.get_type(name) == "object:map" and fnmatchcase(name, pattern)
    ]
    if not maps:
        raise ValueError("Density styles require a loaded map name or map-name pattern")
    threshold = options.params.get("threshold", 0.8)
    signed = options.representation == "density-iso-surface"
    if signed and threshold <= 0:
        raise ValueError("Signed ISO surfaces require a positive threshold")
    counts = {name: cmd.count_states(name) for name in maps}
    if any(options.state > count for count in counts.values()):
        raise ValueError("Requested state is absent from a selected map")
    states = max(counts.values()) if options.state == 0 else 1
    voxels = 0
    for name in maps:
        for state in (
            range(1, counts[name] + 1) if options.state == 0 else [options.state]
        ):
            voxels += cmd.get_volume_field(name, state=state, copy=0).size
    estimate = voxels * (256 if signed else 128)
    resident = sum(entry["estimated_bytes"] for entry in manager.entries.values())
    if resident + estimate > options.memory_mb * 1024**2:
        raise ValueError(
            "Estimated density contour memory exceeds memory_mb; use one state or a coarser map"
        )
    quality = resolve_quality(options.quality, 0, states)
    objects = []
    old = manager.entries.get(options.name)
    previous = None
    source = cmd.get_unused_name("_bs_source")
    try:
        cmd.select(source, "none", enable=0, quiet=1)
        settings = material_settings(options.material, quality, options.transparency)
        for name in maps:
            levels = [threshold, -threshold] if signed else [threshold]
            for level in levels:
                wire = options.representation == "density-wire"
                contours = signed and options.params.get("contours", 0)
                only = signed and options.params.get("only_contours", 0)
                kinds = ["wire"] if wire or only else ["surface"]
                if contours and not only:
                    kinds.append("wire")
                for kind in kinds:
                    obj = cmd.get_unused_name("_bs_density")
                    objects.append(obj)
                    kwargs = {
                        "state": 0 if options.state == 0 else 1,
                        "source_state": options.state,
                        "quiet": 1,
                    }
                    if kind == "wire":
                        cmd.isomesh(obj, name, level, **kwargs)
                        cmd.set("mesh_width", 1.2, obj)
                        cmd.set(
                            "mesh_radius", options.params.get("wire_radius", 0.06), obj
                        )
                    else:
                        cmd.isosurface(
                            obj, name, level, side=-1 if level < 0 else 1, **kwargs
                        )
                    cmd.disable(obj)
                    for setting, value in settings.items():
                        cmd.set(setting, value, obj, quiet=1)
                    color = options.color
                    if color == "auto":
                        color = (
                            "#557BDA"
                            if signed and level > 0
                            else "#E66666"
                            if signed
                            else "#7CBC65"
                        )
                        if options.material == "clay":
                            color = "#C89B7D"
                        if kind == "wire" and signed:
                            color = "#334455"
                    if color == "keep":
                        color = cmd.get_object_color_index(name)
                    elif color.startswith("#"):
                        color = define(
                            cmd,
                            "_bs_hex_" + color[1:].lower(),
                            tuple(int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)),
                        )
                    cmd.color(color, obj, quiet=1)
        entry = {
            "kind": "density",
            "options": asdict(options),
            "objects": objects,
            "source_selection": source,
            "mapping": [],
            "maps": maps,
            "atoms": 0,
            "states": states,
            "quality": quality,
            "coordinate_bytes": 0,
            "estimated_bytes": estimate,
            "seconds": perf_counter() - started,
        }
        previous = deepcopy(manager.data)
        scene = manager._scene_snapshot()
        cmd.group(options.name, " ".join(objects), quiet=1)
        cmd.group(options.name, action="close", quiet=1)
        manager.entries.pop(options.name, None)
        manager.entries[options.name] = entry
        manager._scene(force=True)
        for obj in objects:
            cmd.enable(obj)
        manager._restore_sources()
        if old:
            manager._delete([*old["objects"], old["source_selection"]])
        entry["seconds"] = perf_counter() - started
        return dict(entry)
    except Exception:
        if previous is not None:
            manager.data.clear()
            manager.data.update(previous)
            manager._restore_scene(scene)
            if options.name not in manager.entries:
                manager._delete([options.name])
        manager._delete([*objects, source])
        manager._restore_sources()
        raise
