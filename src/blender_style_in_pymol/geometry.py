"""Use native PyMOL primitives, with no Python mesh or per-frame cache."""

from .presets import geometry_settings, material_settings

# Radii in angstroms for elements commonly present in molecular structures.
VDW_RADII = {
    "H": 1.20,
    "He": 1.40,
    "Li": 1.82,
    "Be": 1.53,
    "B": 1.92,
    "C": 1.70,
    "N": 1.55,
    "O": 1.52,
    "F": 1.47,
    "Ne": 1.54,
    "Na": 2.27,
    "Mg": 1.73,
    "Al": 1.84,
    "Si": 2.10,
    "P": 1.80,
    "S": 1.80,
    "Cl": 1.75,
    "Ar": 1.88,
    "K": 2.75,
    "Ca": 2.31,
    "Fe": 1.26,
    "Co": 1.25,
    "Ni": 1.63,
    "Cu": 1.40,
    "Zn": 1.39,
    "Se": 1.90,
    "Br": 1.85,
    "I": 1.98,
}


def prepare(cmd, obj: str, options, quality: str) -> None:
    rep = options.representation
    settings = geometry_settings(rep, quality, options.params)
    settings.update(material_settings(options.material, quality, options.transparency))
    cmd.hide("everything", obj)
    for key, value in settings.items():
        cmd.set(key, value, obj, quiet=1)
    factor = options.params.get("surface_scale", 1.5) if rep == "surface" else 1
    cmd.alter(
        obj,
        "vdw = radii.get(elem, vdw) * factor",
        space={"radii": VDW_RADII, "factor": factor},
        quiet=1,
    )
    if rep.startswith("preset-"):
        _preset(cmd, obj, options)
    elif rep == "oxdna-ribbon":
        from .oxdna import style

        return style(cmd, obj, options)
    elif rep.startswith("cartoon"):
        cmd.cartoon("automatic", obj)
        if rep == "cartoon":
            cmd.cartoon("rectangle", f"{obj} and ss H")
        cmd.show("cartoon", obj)
        cmd.show("sticks", f"{obj} and not polymer and not solvent")
    elif rep == "ribbon":
        cmd.cartoon("tube", obj)
        cmd.show("cartoon", obj)
        cmd.show("sticks", f"{obj} and not polymer and not solvent")
    elif rep == "spheres":
        cmd.show("spheres", obj)
    elif rep == "ball-and-stick":
        cmd.show("spheres", obj)
        cmd.show("sticks", obj)
    else:
        cmd.show(rep, obj)
    if rep.startswith("cartoon") or rep == "ribbon":
        anchors = cmd.count_atoms(
            f"{obj} and ((polymer.protein and name CA) or (polymer.nucleic and name P))"
        )
        if anchors < 2:
            cmd.show("sticks", f"{obj} and not solvent")
        cmd.show(
            "spheres", f"{obj} and not polymer and not solvent and not neighbor {obj}"
        )
    return []


def _preset(cmd, obj, options):
    rep = options.representation
    peptide = f"{obj} and polymer.protein"
    other = f"{obj} and not polymer"
    if rep in ("preset-1", "preset-2"):
        cmd.cartoon("tube" if rep == "preset-1" else "automatic", obj)
        if rep == "preset-2":
            cmd.cartoon("rectangle", f"{peptide} and ss H")
            target = f"{obj} and not polymer.protein"
            nearby = (
                f"byres ({peptide} within 3 of ({target}))"
                if cmd.count_atoms(target)
                else peptide
            )
            cmd.show("sticks", f"({nearby}) and not hydro and not name N+C+O+OXT")
        cmd.show("cartoon", f"{obj} and polymer")
        cmd.show("sticks", other)
        cmd.show("spheres", other)
        cmd.set("sphere_scale", 1.0, f"({other}) and not neighbor {obj}")
    elif rep == "preset-3":
        cmd.alter(
            peptide,
            "vdw *= factor",
            space={"factor": options.params.get("surface_scale", 1.5)},
        )
        cmd.show("surface", peptide)
        cmd.show("spheres", f"{obj} and not polymer.protein")
    else:
        values = []
        cmd.iterate(obj, "values.append(b)", space={"values": values})
        low, high = min(values), max(values)
        cmd.alter(
            obj,
            "b = 0.2 + 2.8 * (b - low) / span",
            space={"low": low, "span": high - low or 1},
        )
        cmd.cartoon("putty", peptide)
        cmd.show("cartoon", peptide)
        cmd.show("spheres", f"{obj} and not polymer.protein")
