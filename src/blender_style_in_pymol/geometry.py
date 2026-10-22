"""Build molecular views using native primitives and compact smooth meshes."""

from .presets import geometry_settings, material_settings, needs_cycles

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


def mesh_estimate(representation, quality, atoms, backbone):
    if representation in ("spheres", "sticks", "ball-and-stick"):
        sphere_faces = {"low": 120, "medium": 360, "high": 960}[quality]
        bonds = (
            0
            if representation == "spheres"
            else {"low": 120, "medium": 192, "high": 288}[quality]
        )
        return atoms * (sphere_faces + bonds) * 1200
    if representation in ("surface", "preset-3"):
        return atoms * {"low": 60_000, "medium": 120_000, "high": 200_000}[quality]
    return backbone * {"low": 160_000, "medium": 320_000, "high": 600_000}[quality]


def mesh_backend(options, atoms, states, quality="high", backbone=0):
    supported = options.representation in (
        "surface",
        "preset-3",
        "cartoon",
        "cartoon-rounded",
        "ribbon",
        "preset-1",
        "preset-2",
        "spheres",
        "sticks",
        "ball-and-stick",
    )
    if needs_cycles(options):
        if (
            not supported
            or options.backend == "native"
            or options.params.get("bond_split", 0)
        ):
            raise ValueError(
                "Cycles materials require a supported mesh representation and backend=mesh or auto"
            )
        if options.lighting != "auto":
            raise ValueError("Cycles materials require lighting=auto")
        if (
            options.representation
            not in ("surface", "spheres", "sticks", "ball-and-stick")
            and not backbone
        ):
            raise ValueError(
                "This Cycles representation requires a polymer backbone; use spheres or surface"
            )
        return True
    if options.backend == "mesh" and (
        not supported or options.params.get("bond_split", 0)
    ):
        raise ValueError(
            "The requested representation or multiple-bond layout requires backend=native"
        )
    if (
        not supported
        or options.backend == "native"
        or options.params.get("bond_split", 0)
    ):
        return False
    if (
        options.representation
        in ("cartoon", "cartoon-rounded", "ribbon", "preset-1", "preset-2", "preset-3")
        and backbone == 0
    ):
        return False
    return options.backend == "mesh" or (
        states == 1
        and mesh_estimate(options.representation, quality, atoms, backbone)
        < options.memory_mb * 1024**2 * 0.8
    )


def prepare(cmd, obj: str, options, quality: str, use_mesh=False, budget=None):
    rep = options.representation
    settings = geometry_settings(rep, quality, options.params)
    settings.update(material_settings(options.material, quality, options.transparency))
    cmd.hide("everything", obj)
    for key, value in settings.items():
        cmd.set(key, value, obj, quiet=1)
    factor = (
        options.params.get("surface_scale", 1.5)
        if rep == "surface" and not use_mesh
        else 1
    )
    cmd.alter(
        obj,
        "vdw = radii.get(elem, vdw) * factor",
        space={"radii": VDW_RADII, "factor": factor},
        quiet=1,
    )
    if use_mesh:
        from .mesh import cache, load

        if rep in ("surface", "preset-3"):
            from .surface import surface as build
        elif rep in ("spheres", "sticks", "ball-and-stick"):
            from .atomic import atomic as build
        else:
            from .cartoon import cartoon as build

        name = cmd.get_unused_name("_bs_mesh")
        meshes = []
        available = options.memory_mb * 1024**2 if budget is None else budget
        try:
            for state in range(1, cmd.count_states(obj) + 1):
                mesh = build(cmd, obj, state, quality, options, available)
                if mesh is None:
                    break
                if mesh.nbytes * 2 + len(mesh.faces) * 1200 > available:
                    raise ValueError(
                        "Mesh preparation exceeds memory_mb; use lower quality or backend=native"
                    )
                available -= mesh.nbytes * 2 + len(mesh.faces) * 180
                if available < 0:
                    raise ValueError(
                        "Mesh states exceed memory_mb; use state=current or lower quality"
                    )
                meshes.append(mesh)
            if meshes:
                callback = load(cmd, name, meshes, options)
                cmd.disable(name)
                if callback:
                    cmd.disable(callback)
                cache(cmd)[name] = meshes
                if rep == "preset-3":
                    cmd.show("spheres", f"{obj} and not polymer.protein")
                elif rep not in ("surface", "spheres", "sticks", "ball-and-stick"):
                    if rep.startswith("preset-"):
                        _preset(cmd, obj, options)
                        cmd.hide("cartoon", f"{obj} and polymer.protein")
                    cmd.hide("cartoon", f"{obj} and polymer.nucleic")
                return [name, callback] if callback else [name]
            if needs_cycles(options):
                raise ValueError(
                    "No mesh could be generated for this Cycles view; use spheres or surface"
                )
        except Exception:
            cmd.delete(name)
            from .mesh import callback_names

            callback = callback_names(cmd).pop(name, None)
            if callback:
                cmd.delete(callback)
            getattr(cmd._pymol, "_blender_drawings", {}).pop(name, None)
            cache(cmd).pop(name, None)
            raise
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
    elif rep == "ribbon":
        cmd.cartoon("tube", obj)
        cmd.show("cartoon", obj)
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
                "spheres",
                f"{obj} and not polymer and not solvent and not neighbor {obj}",
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
