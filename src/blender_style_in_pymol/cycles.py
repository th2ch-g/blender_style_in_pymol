"""Optional Cycles rendering of the current managed mesh scene."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from .presets import Options, integer, needs_cycles, number


def visible_entries(cmd):
    from .controller import SESSION_KEY

    enabled = enabled_objects(cmd)
    cache = getattr(cmd._pymol.session, "blender_style_meshes", {})
    entries = getattr(cmd._pymol.session, SESSION_KEY, {}).get("entries", {})
    return [
        entry
        for entry in entries.values()
        if any(obj in cache and obj in enabled for obj in entry["objects"])
    ]


def enabled_objects(cmd):
    from .controller import SESSION_KEY

    enabled = set(cmd.get_names("objects", enabled_only=1))
    groups = set(cmd.get_names("group_objects")) - enabled
    if not groups:
        return enabled
    hidden_molecules = set()
    for group in groups:
        hidden_molecules.update(cmd.get_object_list(f"%{group}"))
    enabled.difference_update(hidden_molecules)
    entries = getattr(cmd._pymol.session, SESSION_KEY, {}).get("entries", {})
    for entry in entries.values():
        if entry["options"]["name"] in groups or hidden_molecules.intersection(
            entry["objects"]
        ):
            enabled.difference_update(entry["objects"])
    return enabled


def requested(cmd, renderer="auto"):
    if str(renderer).lower() == "cycles":
        return True
    if str(renderer).lower() not in ("auto", "-1"):
        return False
    return any(needs_cycles(Options(**e["options"])) for e in visible_entries(cmd))


def executable():
    configured = os.environ.get("BLENDER_EXECUTABLE")
    path = shutil.which(configured or "blender")
    if (
        path is None
        and configured is None
        and sys.platform == "darwin"
        and shutil.which("mdfind")
    ):
        try:
            result = subprocess.run(
                [
                    "mdfind",
                    "kMDItemCFBundleIdentifier == 'org.blenderfoundation.blender'",
                ],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            for application in sorted(result.stdout.splitlines()):
                candidate = Path(application) / "Contents" / "MacOS" / "Blender"
                if candidate.is_file() and os.access(candidate, os.X_OK):
                    path = str(candidate)
                    break
        except (OSError, subprocess.TimeoutExpired):
            pass
    if path is None:
        raise RuntimeError(
            "Cycles rendering requires Blender 4.0 or newer. Add blender to PATH "
            "or set BLENDER_EXECUTABLE to its executable; renderer=pymol uses the preview approximation."
        )
    return path


def dimensions(cmd, width, height):
    width, height = int(width), int(height)
    viewport = cmd.get_viewport()
    if not width and not height:
        width, height = viewport
    elif not width:
        width = round(height * viewport[0] / max(viewport[1], 1))
    elif not height:
        height = round(width * viewport[1] / max(viewport[0], 1))
    width = integer(width, "width", 16, 8192)
    height = integer(height, "height", 16, 8192)
    if width * height > 32_000_000:
        raise ValueError("Export is limited to 32 million pixels")
    return width, height


def export_scene(
    cmd, directory, width, height, samples=None, angle=0, shift=0, memory_mb=None
):
    import numpy as np

    from .export import _mesh_only
    from .presets import optical_parameters

    if float(shift) or cmd.get_setting_boolean("stereo"):
        raise ValueError(
            "Cycles export currently supports monoscopic views with shift=0"
        )
    entries = visible_entries(cmd)
    if not entries:
        raise ValueError("Cycles export requires an enabled blender_style mesh view")
    cache = getattr(cmd._pymol.session, "blender_style_meshes", {})
    if not _mesh_only(cmd, cache):
        raise ValueError(
            "Cycles export cannot include visible native objects or labels. "
            "Hide them or create mesh views for the complete scene."
        )
    enabled = enabled_objects(cmd)
    meshes = []
    estimate = width * height * 96
    budget = (
        number(
            min(entry["options"]["memory_mb"] for entry in entries)
            if memory_mb is None
            else memory_mb,
            "memory_mb",
            1,
            65536,
        )
        * 1024**2
    )
    for entry in entries:
        options = Options(**entry["options"])
        for obj in entry["objects"]:
            if obj not in cache or obj not in enabled:
                continue
            state = cmd.get_setting_int("state", obj) or cmd.get_state()
            if len(cache[obj]) == 1:
                state = 1
            if not 1 <= state <= len(cache[obj]):
                continue
            mesh = cache[obj][state - 1]
            estimate += mesh.nbytes * 3 + len(mesh.faces) * 320
            if estimate > budget:
                raise ValueError(
                    "Estimated Cycles scene buffers exceed memory_mb; reduce quality or image dimensions"
                )
            meshes.append((obj, mesh, options))
    if not meshes:
        raise ValueError("The current state contains no visible managed meshes")
    data = {
        "width": width,
        "height": height,
        "view": list(cmd.get_view()),
        "field_of_view": cmd.get_setting_float("field_of_view"),
        "orthoscopic": cmd.get_setting_boolean("orthoscopic"),
        "samples": integer(
            samples
            if samples is not None
            else max(e["options"].get("samples", 64) for e in entries),
            "samples",
            1,
            4096,
        ),
        "angle": float(angle),
        "objects": [],
    }
    opaque = cmd.get_setting_int("ray_opaque_background")
    data["transparent"] = not (
        cmd.get_setting_boolean("opaque_background") if opaque < 0 else opaque
    )
    kind, value = cmd.get_setting_tuple("bg_rgb")
    data["background"] = list(value if kind == 4 else cmd.get_color_tuple(value[0]))
    for i, (obj, mesh, options) in enumerate(meshes):
        filename = f"mesh-{i}.npz"
        np.savez(
            directory / filename,
            vertices=mesh.vertices,
            faces=mesh.faces,
            normals=mesh.normals,
            colors=mesh.colors,
            occlusion=mesh.occlusion,
        )
        ttt = cmd.get_object_ttt(obj)
        matrix = np.eye(4)
        if ttt:
            ttt = np.asarray(ttt).reshape(4, 4)
            matrix[:3, :3] = ttt[:3, :3]
            matrix[:3, 3] = ttt[:3, :3] @ ttt[3, :3] + ttt[:3, 3]
        data["objects"].append(
            {
                "file": filename,
                "material": options.material,
                "transparency": options.transparency,
                "optical": optical_parameters(options.material, options.params),
                "matrix": matrix.ravel().tolist(),
            }
        )
    (directory / "scene.json").write_text(json.dumps(data), encoding="utf-8")
    return data


def render(cmd, width=0, height=0, samples=None, angle=0, shift=0, *, memory_mb=None):
    blender = executable()
    width, height = dimensions(cmd, width, height)
    started = perf_counter()
    with TemporaryDirectory(prefix="blender-style-cycles-") as temporary:
        directory = Path(temporary)
        data = export_scene(
            cmd, directory, width, height, samples, angle, shift, memory_mb
        )
        worker = Path(__file__).with_name("_cycles_worker.py")
        args = [
            blender,
            "--background",
            "--factory-startup",
            "--disable-autoexec",
            "--threads",
            str(min(os.cpu_count() or 1, 8)),
            "--python-exit-code",
            "1",
            "--python",
            str(worker),
            "--",
            str(directory),
        ]
        try:
            with (directory / "render.log").open(
                "w+", encoding="utf-8", errors="replace"
            ) as log:
                result = subprocess.run(
                    args, stdout=log, stderr=subprocess.STDOUT, timeout=600, check=False
                )
                if result.returncode:
                    log.seek(0, 2)
                    log.seek(max(0, log.tell() - 8192))
                    detail = log.read()
                    raise RuntimeError(
                        f"Blender Cycles failed ({result.returncode}):\n{detail}"
                    )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(
                "Cycles rendering exceeded 600 seconds; reduce samples or dimensions"
            ) from error
        output = directory / "render.png"
        if not output.is_file():
            raise RuntimeError("Cycles finished without writing an image")
        metadata = json.loads((directory / "result.json").read_text(encoding="utf-8"))
        metadata.update(
            seconds=perf_counter() - started,
            width=width,
            height=height,
            samples=data["samples"],
        )
        cmd.load_png(str(output), quiet=1)
        cmd._pymol._blender_last_cycles = metadata
        return output.read_bytes()
