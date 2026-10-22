"""Validate the complete request before allocating objects or changing a scene."""

import json
import re
from pathlib import Path

from .presets import (
    MATERIALS,
    PARAMETERS,
    REPRESENTATIONS,
    Options,
    canonical,
    integer,
    number,
)


def read_params(value):
    if value is None or value == "":
        return {}
    if isinstance(value, (str, Path)):
        path = Path(value).expanduser()
        if path.stat().st_size > 65536:
            raise ValueError("Parameter files must be smaller than 64 KiB")
        value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("params must be a dictionary or a local JSON object file")
    unknown = set(value) - set(PARAMETERS)
    if unknown:
        raise ValueError("Unknown parameters: " + ", ".join(sorted(unknown)))
    return {
        key: (
            integer
            if key
            in (
                "contours",
                "only_contours",
                "bond_split",
                "surface_relaxation",
                "surface_separate_chains",
                "surface_color_ca",
                "color_blur",
                "color_interpolate",
            )
            else number
        )(val, key, *PARAMETERS[key])
        for key, val in value.items()
    }


def parse(cmd, **values):
    style = canonical(values["style"])
    if style not in (*REPRESENTATIONS, *MATERIALS):
        raise ValueError(f"Unknown style '{style}'; use blender_style list")
    representation = (
        canonical(values["representation"])
        if values["representation"]
        else (style if style in REPRESENTATIONS else "cartoon")
    )
    material = (
        canonical(values["material"])
        if values["material"]
        else (style if style in MATERIALS else "studio")
    )
    if representation not in REPRESENTATIONS:
        raise ValueError("Unknown representation; use blender_style list")
    if material not in MATERIALS:
        raise ValueError("Unknown material; use blender_style list")
    name = str(values["name"])
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name) or name.lower() in (
        "all",
        "none",
        "sele",
        "enabled",
        "visible",
    ):
        raise ValueError("name must be an unreserved identifier starting with a letter")
    quality = str(values["quality"]).lower()
    if quality not in ("auto", "low", "medium", "high"):
        raise ValueError("quality must be auto, low, medium, or high")
    backend = str(values.get("backend", "auto")).lower()
    if backend not in ("auto", "native", "mesh"):
        raise ValueError("backend must be auto, native, or mesh")
    renderer = str(values.get("renderer", "auto")).lower()
    if renderer not in ("auto", "pymol", "cycles"):
        raise ValueError("renderer must be auto, pymol, or cycles")
    lighting = canonical(values["lighting"])
    if lighting not in ("auto", "keep", *MATERIALS):
        raise ValueError("lighting must be auto, keep, or a material name")
    state = (
        cmd.get_state()
        if str(values["state"]).lower() == "current"
        else integer(values["state"], "state", 0, 1_000_000)
    )
    transparency = values["transparency"]
    if transparency is None or transparency == "":
        transparency = 0.5 if material == "transparent" else 0.0
    params = read_params(values["params"])
    if material in ("flat", "outline", "ambient-occlusion") and any(
        params.get(key, 0) > 0 for key in ("transmission", "subsurface")
    ):
        raise ValueError(
            "Transmission and subsurface parameters require a lit material"
        )
    return Options(
        style=style,
        selection=str(values["selection"]),
        representation=representation,
        material=material,
        color=canonical(values["color"]),
        quality=quality,
        name=name,
        transparency=number(transparency, "transparency", 0, 1),
        lighting=lighting,
        state=state,
        memory_mb=number(values["memory_mb"], "memory_mb", 1, 65536),
        params=params,
        backend=backend,
        renderer=renderer,
        samples=integer(values.get("samples", 64), "samples", 1, 4096),
    )
