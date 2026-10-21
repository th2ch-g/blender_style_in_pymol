"""Independent parameter mappings for the Molecular Nodes 4.5 appearance."""

from dataclasses import dataclass, field
from math import isfinite
from typing import Any

MOLECULAR_REPRESENTATIONS = (
    "cartoon",
    "ribbon",
    "spheres",
    "ball-and-stick",
    "sticks",
    "surface",
    "cartoon-rounded",
    "cartoon-cylinders",
    "preset-1",
    "preset-2",
    "preset-3",
    "preset-4",
    "oxdna-ribbon",
)
DENSITY_REPRESENTATIONS = ("density-surface", "density-wire", "density-iso-surface")
REPRESENTATIONS = (*MOLECULAR_REPRESENTATIONS, *DENSITY_REPRESENTATIONS)

MATERIALS = (
    "studio",
    "ambient-occlusion",
    "matte",
    "glossy",
    "clay",
    "flat",
    "outline",
    "transparent",
)

OPERATIONS = ("list", "help", "reset", "refresh", "select", "png", "ray", "gui")
COLOR_THEMES = ("auto", "keep", "element", "chain", "secondary-structure", "rainbow")
ALIASES = {
    "default": "studio",
    "ballstick": "ball-and-stick",
    "ball-and-sticks": "ball-and-stick",
    "spacefill": "spheres",
    "space-filling": "spheres",
    "tube": "ribbon",
    "ao": "ambient-occlusion",
    "flat-outline": "outline",
    "ss": "secondary-structure",
    "common": "element",
    "density-iso": "density-iso-surface",
    "density-isosurface": "density-iso-surface",
    "dna-spheres-cycles": "spheres",
    "dna-spheres-eevee": "spheres",
    "dna-surface": "surface",
    "dna-ball-and-stick": "ball-and-stick",
}


def canonical(value: Any) -> str:
    word = str(value).strip().lower().replace("_", "-")
    return ALIASES.get(word, word)


def number(value: Any, name: str, low: float, high: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number between {low} and {high}") from exc
    if not isfinite(result) or not low <= result <= high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return result


def integer(value: Any, name: str, low: int, high: int) -> int:
    result = number(value, name, low, high)
    if not result.is_integer():
        raise ValueError(f"{name} must be an integer")
    return int(result)


PARAMETERS = {
    "sphere_scale": (0.01, 4.0),
    "bond_radius": (0.01, 3.0),
    "ribbon_radius": (0.05, 5.0),
    "cartoon_width": (0.1, 8.0),
    "cartoon_thickness": (0.05, 3.0),
    "loop_radius": (0.05, 3.0),
    "surface_scale": (0.5, 3.0),
    "probe_radius": (0.0, 5.0),
    "threshold": (-1e6, 1e6),
    "wire_radius": (0.005, 2.0),
    "contours": (0, 1),
    "only_contours": (0, 1),
    "bond_split": (0, 1),
}


@dataclass(frozen=True)
class Options:
    style: str = "studio"
    selection: str = "all"
    representation: str = "cartoon"
    material: str = "studio"
    color: str = "auto"
    quality: str = "auto"
    name: str = "blender"
    transparency: float = 0.0
    lighting: str = "auto"
    state: int = 0
    memory_mb: float = 512.0
    params: dict = field(default_factory=dict)


def resolve_quality(quality: str, atoms: int, states: int) -> str:
    if quality != "auto":
        return quality
    if atoms > 100_000 or atoms * states > 2_000_000:
        return "low"
    if atoms > 20_000 or states > 1:
        return "medium"
    return "high"


def estimate_bytes(representation, quality, atoms, backbone, coordinate_bytes):
    level = ("low", "medium", "high").index(quality)
    if representation in ("surface", "preset-3"):
        geometry = atoms * (2_048, 4_096, 8_192)[level]
    elif representation.startswith(("cartoon", "preset")) or representation == "ribbon":
        geometry = backbone * (8_064, 21_120, 49_152)[level]
    elif representation == "oxdna-ribbon":
        geometry = atoms * 2048
    else:
        geometry = atoms * (256 if representation == "ball-and-stick" else 128)
    return coordinate_bytes + atoms * 384 + geometry


def geometry_settings(representation: str, quality: str, params: dict) -> dict:
    level = ("low", "medium", "high").index(quality)
    settings = {
        "cartoon_sampling": (5, 9, 14)[level],
        "cartoon_oval_quality": (6, 10, 16)[level],
        "cartoon_tube_quality": (6, 10, 16)[level],
        "cartoon_loop_quality": (6, 10, 16)[level],
        "cartoon_smooth_loops": 0,
        "cartoon_flat_sheets": 0,
        "cartoon_fancy_sheets": int(representation == "cartoon-rounded"),
        "cartoon_fancy_helices": int(representation == "cartoon-rounded"),
        "cartoon_cylindrical_helices": int(representation == "cartoon-cylinders"),
        "cartoon_discrete_colors": 0,
        "cartoon_oval_length": params.get("cartoon_width", 2.2),
        "cartoon_oval_width": params.get("cartoon_thickness", 0.6),
        "cartoon_rect_length": params.get("cartoon_width", 2.2),
        "cartoon_rect_width": params.get("cartoon_thickness", 0.6),
        "cartoon_loop_radius": params.get("loop_radius", 0.3),
        "cartoon_tube_radius": params.get("ribbon_radius", 1.6),
        "cartoon_nucleic_acid_mode": 4,
        "cartoon_ladder_mode": 1,
        "cartoon_ring_mode": 3,
        "cartoon_ring_finder": 1,
        "cartoon_ring_width": 0.3,
        "cartoon_ring_transparency": 0,
        "sphere_quality": (1, 2, 3)[level],
        "stick_quality": (8, 12, 20)[level],
        "stick_radius": params.get("bond_radius", 0.2),
        "stick_ball": 0,
        "stick_color": -1,
        "sphere_color": -1,
        "cartoon_color": -1,
        "surface_color": -1,
        "valence": int(params.get("bond_split", 0)),
        "sphere_scale": params.get("sphere_scale", 0.8),
        "surface_quality": (0, 1, 2)[level],
        "surface_mode": 1,
        "surface_solvent": 0,
        "surface_smooth_edges": 1,
        "solvent_radius": params.get("probe_radius", 1.0),
        "transparency_mode": 2,
        "defer_builds_mode": 3,
    }
    if representation == "ball-and-stick":
        settings["stick_radius"] = params.get("bond_radius", 0.3)
        settings["sphere_scale"] = params.get("sphere_scale", 0.3)
    if representation in ("preset-1", "preset-2"):
        settings["sphere_scale"] = params.get("sphere_scale", 0.3)
        settings["stick_radius"] = params.get("bond_radius", 0.25)
    if representation == "preset-1":
        settings["cartoon_tube_radius"] = params.get("ribbon_radius", 1.4)
    if representation == "preset-2":
        settings["cartoon_rect_length"] = params.get("cartoon_width", 2.4)
        settings["cartoon_rect_width"] = params.get("cartoon_thickness", 0.4)
        settings["cartoon_loop_radius"] = params.get("loop_radius", 0.2)
    if representation == "preset-3":
        settings["sphere_scale"] = params.get("sphere_scale", 0.5)
    if representation == "preset-4":
        settings.update(
            cartoon_putty_transform=7,
            cartoon_putty_radius=1,
            cartoon_putty_scale_min=-1,
            cartoon_putty_scale_max=-1,
        )
    return settings


def lighting_settings(material: str) -> dict:
    settings = {
        "ambient": 0.55,
        "direct": 0.15,
        "reflect": 0.2,
        "specular": 0.08,
        "specular_intensity": 0.35,
        "shininess": 20,
        "spec_reflect": 0.08,
        "spec_direct": 0,
        "light_count": 4,
        "light": (-0.4, -0.5, -1.0),
        "light2": (0.5, -0.2, -0.8),
        "light3": (0.2, 0.7, -0.5),
        "depth_cue": 0,
        "ray_trace_fog": 0,
        "ray_shadows": 0,
        "ray_trace_mode": 0,
        "ray_trace_gain": 0.08,
        "ray_trace_color": "black",
        "two_sided_lighting": 1,
        "antialias": 2,
    }
    if material in ("matte", "clay", "ambient-occlusion"):
        settings.update(specular=0, specular_intensity=0, spec_reflect=0)
    if material == "ambient-occlusion":
        settings.update(ambient=0.65, direct=0.1, reflect=0.25)
    elif material == "glossy":
        settings.update(
            specular=0.8, specular_intensity=0.65, spec_reflect=0.8, shininess=70
        )
    elif material in ("flat", "outline"):
        settings.update(ambient=1, direct=0, reflect=0, specular=0, spec_reflect=0)
        if material == "outline":
            settings.update(ray_trace_mode=1)
    elif material == "transparent":
        settings.update(specular=0.5, spec_reflect=0.45, shininess=55)
    return settings


def material_settings(material: str, quality: str, transparency: float) -> dict:
    occlusion = material not in ("flat", "outline", "transparent")
    return {
        "ambient_occlusion_mode": 2 if occlusion else 0,
        "ambient_occlusion_scale": 16 if material == "ambient-occlusion" else 10,
        "ambient_occlusion_smooth": {"low": 5, "medium": 10, "high": 15}[quality],
        "transparency": transparency,
        "cartoon_transparency": transparency,
        "sphere_transparency": transparency,
        "stick_transparency": transparency,
    }
