"""Molecular Nodes-inspired visualization without importing or starting PyMOL."""

__version__ = "0.3.0"


def blender_load_oxdna(
    topology,
    trajectory,
    name="oxdna",
    start=1,
    stop=0,
    stride=1,
    memory_mb=512,
    _self=None,
):
    """Load oxDNA topology and text configurations; see the command guide."""
    from .oxdna import load

    return load(topology, trajectory, name, start, stop, stride, memory_mb, _self)


def blender_style(
    style="studio",
    selection="all",
    representation=None,
    color="auto",
    quality="auto",
    name="blender",
    material=None,
    transparency=None,
    lighting="auto",
    state=0,
    memory_mb=512,
    params=None,
    filename="",
    width=1200,
    height=900,
    quiet=0,
    _self=None,
    backend="auto",
    renderer="auto",
    samples=None,
):
    """
    DESCRIPTION
        Molecular Nodes-inspired geometry and soft studio lighting in PyMOL.

    USAGE
        blender_style [style [, selection [, representation [, color]]]]
        blender_style cartoon, color=secondary-structure
        blender_style studio, representation=surface, color=chain
        blender_style ball-and-stick, selection=organic, name=ligand
        blender_style transparent, representation=surface, transparency=0.5
        blender_style glass, representation=surface
        blender_style subsurface, representation=surface, samples=128
        blender_style list
        blender_style refresh, name=all
        blender_style reset, name=all
        blender_style select, selection=pk1
        blender_style ray, filename=figure.png, width=2400, height=1800
        blender_style gui

    ARGUMENTS
        style: representation or material name; list shows all names.
        selection: PyMOL atom selection; managed copies are excluded.
        representation: geometry override (cartoon by default).
        color: auto, keep, element, chain, secondary-structure, rainbow,
            a PyMOL color name, or #rrggbb.
        quality: auto, low, medium, high. Auto scales with atom/state count.
        backend: auto, mesh, or native. Auto prefers meshes for small static views.
        renderer: auto, pymol, or cycles. Glass and SSS automatically use Cycles.
        samples: Cycles samples per pixel, 1..4096 (default 64).
        name: managed view name; reuse replaces that view.
        material: studio, ambient-occlusion, matte, glossy, clay, flat,
            outline, transparent, glass, subsurface. Overrides the style's material.
        transparency: fraction 0..1; transparent defaults to 0.5.
        lighting: auto, keep, or a material name. Scene lighting is global.
        state: 0 copies all states; current or a positive integer copies one.
        memory_mb: conservative preparation estimate limit, in MiB.
        params: dictionary or local JSON file with geometry and optical parameters.
        filename, width, height: PNG or ray export path and pixel dimensions.

    NOTES
        Coordinates, bonds, colors and attributes of source atoms are preserved.
        Reset restores source representations and owned lighting. Native views
        support atom picking; mesh views support sessions and standard ray export.
        Use refresh after editing source coordinates or attributes.
        Mesh materials use approximate GGX lighting and geometric occlusion.
        Standard ray, cmd.ray and png ray=1 refresh camera-dependent shading.
        Cycles ray output requires Blender 4.0+ on PATH or BLENDER_EXECUTABLE.
        The viewport approximates glass and SSS; Cycles computes refraction and
        random-walk subsurface scattering. Visible native geometry is rejected
        by Cycles export. Molecular Nodes is not required.
    """
    from .presets import (
        COLOR_THEMES,
        MATERIALS,
        OPERATIONS,
        REPRESENTATIONS,
        canonical,
        integer,
    )

    quiet = integer(quiet, "quiet", 0, 1)
    operation = canonical(style)
    if operation == "list":
        result = {
            "representations": REPRESENTATIONS,
            "materials": MATERIALS,
            "colors": COLOR_THEMES,
            "operations": OPERATIONS,
        }
        if not int(quiet):
            for key, values in result.items():
                print(f"{key}: {', '.join(values)}")
        return result
    if operation == "help":
        print(blender_style.__doc__)
        return blender_style.__doc__
    if _self is None:
        from pymol import cmd as _self
    from .controller import manager_for
    from .ray import install

    install(_self)
    manager = manager_for(_self)
    if operation in ("reset", "refresh"):
        return getattr(manager, operation)(str(name))
    if operation == "select":
        return manager.select_source(str(selection))
    if operation == "gui":
        from .gui import show_dialog

        return show_dialog(_self)
    if operation in ("png", "ray"):
        from .export import image

        return image(
            _self,
            filename,
            width,
            height,
            ray=operation == "ray",
            memory_mb=memory_mb,
            renderer=renderer,
            samples=samples,
        )
    from .options import parse

    options = parse(
        _self,
        style=operation,
        selection=selection,
        representation=representation,
        color=color,
        quality=quality,
        name=name,
        material=material,
        transparency=transparency,
        lighting=lighting,
        state=state,
        memory_mb=memory_mb,
        params=params,
        backend=backend,
        renderer=renderer,
        samples=64 if samples is None else samples,
    )
    entry = manager.apply(options)
    if not int(quiet):
        print(
            f"blender_style: {options.name}, {options.representation}/{options.material}, "
            f"{entry['atoms']} atoms, {entry['states']} states, {entry['quality']} quality; "
            f"{entry.get('backend', 'native')} rendering, prepared in {entry['seconds']:.3f} s"
        )
    return entry


def __init_plugin__(app=None, _self=None):
    if _self is None:
        from pymol import cmd as _self
    from .presets import MATERIALS, OPERATIONS, REPRESENTATIONS
    from .ray import install

    install(_self)
    _self.extend("blender_style", blender_style)
    _self.extend("blender_load_oxdna", blender_load_oxdna)
    if hasattr(_self, "auto_arg"):
        from pymol.shortcut import Shortcut

        _self.auto_arg[0]["blender_style"] = [
            Shortcut((*REPRESENTATIONS, *MATERIALS, *OPERATIONS)),
            "style or operation",
            ",",
        ]
        _self.auto_arg[1]["blender_style"] = [_self.selection_sc, "selection", ","]
        _self.auto_arg[2]["blender_style"] = [
            Shortcut(REPRESENTATIONS),
            "representation",
            ",",
        ]
    if not getattr(_self._pymol, "_blender_style_menu", False):
        try:
            from pymol.plugins import HAVE_QT, addmenuitemqt

            if HAVE_QT:
                addmenuitemqt(
                    "Blender / Molecular Nodes Style",
                    lambda: blender_style("gui", _self=_self),
                )
                _self._pymol._blender_style_menu = True
        except (ImportError, RuntimeError):
            pass
