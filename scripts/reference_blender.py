"""Render installed Molecular Nodes with a camera and atoms exported by PyMOL.

Run inside Blender with --background --factory-startup --python, followed by
-- --addon ADDON_DIRECTORY --input INPUT_JSON --output OUTPUT_DIRECTORY.
This script does not install or modify the Blender add-on.
"""

import argparse
import json
import sys
from pathlib import Path


def main():
    import bpy
    import numpy as np
    from mathutils import Matrix, Vector

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--addon", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--style", default="cartoon")
    parser.add_argument("--material", default="studio")
    parser.add_argument("--samples", type=int, default=64)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    addon = args.addon.resolve()
    dependencies = (
        addon.parents[1]
        / ".local"
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
    sys.path.insert(0, str(dependencies))
    sys.path.insert(0, str(addon.parent))

    import molecularnodes as mn

    mn.register()
    data = json.loads(args.input.read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    from biotite.structure import BondList

    reader = mn.Molecule._read(data["structure"])
    array = reader.array
    original_array = array[0] if array.coord.ndim == 3 else array
    lookup = {
        (
            str(atom.chain_id),
            str(atom.res_id) + str(atom.ins_code),
            str(atom.atom_name),
        ): i
        for i, atom in enumerate(original_array)
    }
    remap = [
        lookup[(atom["chain"], atom["resi"], atom["name"])] for atom in data["atoms"]
    ]
    array.bonds = BondList(
        len(original_array),
        np.asarray(
            [
                [remap[a], remap[b], order if order in (1, 2, 3) else 1]
                for a, b, order in data["bonds"]
            ],
            dtype=np.uint32,
        ),
    )
    molecule = mn.Molecule(array, reader=reader)
    molecule.create_object(name="Reference molecule")
    atoms = data["atoms"]
    atom_array = molecule.array[0] if molecule.array.coord.ndim == 3 else molecule.array
    if len(atom_array) != len(atoms):
        raise ValueError("Reference atom counts do not match")
    keys = {(atom["chain"], atom["resi"], atom["name"]): atom for atom in atoms}
    ordered = [
        keys[
            (
                str(atom.chain_id),
                str(atom.res_id) + str(atom.ins_code),
                str(atom.atom_name),
            )
        ]
        for atom in atom_array
    ]
    molecule.store_named_attribute(
        np.array([{"H": 1, "S": 2}.get(atom["ss"], 3) for atom in ordered], dtype=int),
        name="sec_struct",
        atype="INT",
    )
    molecule.store_named_attribute(
        np.array([atom["rgba_linear"] for atom in ordered]),
        name="Color",
        atype="FLOAT_COLOR",
    )
    reference_style = args.style.replace("-", "_")
    style_class = {
        "cartoon": mn.StyleCartoon,
        "ribbon": mn.StyleRibbon,
        "spheres": mn.StyleSpheres,
        "ball_and_stick": mn.StyleBallAndStick,
        "sticks": mn.StyleSticks,
        "surface": mn.StyleSurface,
    }[reference_style]
    style = style_class()
    if hasattr(style, "quality"):
        style.quality = 3
    material = reference_material(
        bpy, args.material, data.get("transparency", 0), addon
    )
    molecule.add_style(style, color=None, material=material)

    view = np.asarray(data["view"])
    rotation = view[:9].reshape(3, 3).T
    center = view[12:15]
    scale = molecule._world_scale
    matrix = np.eye(4)
    matrix[:3, :3] = rotation
    matrix[:3, 3] = -rotation @ center * scale
    molecule.object.matrix_world = Matrix(matrix.tolist())

    scene = bpy.context.scene
    camera_data = bpy.data.cameras.new("Reference camera")
    camera = bpy.data.objects.new("Reference camera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = (0, 0, -view[11] * scale)
    camera.rotation_euler = (0, 0, 0)
    camera_data.type = "ORTHO"
    width, height = data["width"], data["height"]
    camera_data.ortho_scale = data["vertical_span"] * scale * width / height
    camera_data.clip_start = 0.001
    camera_data.clip_end = 100
    scene.camera = camera

    world = bpy.data.worlds.new("Reference world")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (1, 1, 1, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35
    scene.world = world
    for name, position, power, size in (
        ("Key", (-0.45, 0.55, 0.8), 3, 0.65),
        ("Fill", (0.5, 0.15, 0.6), 1.2, 0.75),
        ("Rim", (0.1, -0.5, 0.35), 1.8, 0.5),
    ):
        light = bpy.data.lights.new(name, "AREA")
        light.energy = power
        light.shape = "DISK"
        light.size = size
        obj = bpy.data.objects.new(name, light)
        scene.collection.objects.link(obj)
        obj.location = position
        obj.rotation_euler = (-Vector(position)).to_track_quat("-Z", "Y").to_euler()

    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1
    scene.render.filepath = str(args.output / f"reference-{args.style}.png")
    bpy.ops.render.render(write_still=True)
    result = {
        "blender": bpy.app.version_string,
        "material": args.material,
        "style": args.style,
        "samples": args.samples,
        "atoms": len(atoms),
        "view_transform": "Standard",
        "engine": "Cycles CPU",
    }
    (args.output / f"reference-{args.style}.json").write_text(
        json.dumps(result, indent=2)
    )


def reference_material(bpy, name, transparency, addon):
    assets = {
        "studio": "MN Default",
        "ambient-occlusion": "MN Ambient Occlusion",
        "outline": "MN Flat Outline",
    }
    if name in assets:
        return assets[name]
    material = bpy.data.materials.new("Reference " + name)
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    if "MN Color Input" not in bpy.data.node_groups:
        with bpy.data.libraries.load(
            str(addon / "assets" / "node_data_file.blend"), link=False
        ) as (available, requested):
            requested.node_groups = ["MN Color Input"]
    attribute = nodes.new("ShaderNodeGroup")
    attribute.node_tree = bpy.data.node_groups["MN Color Input"]
    if name == "flat":
        surface = nodes.new("ShaderNodeEmission")
        links.new(attribute.outputs["Color"], surface.inputs["Color"])
    else:
        surface = nodes.new("ShaderNodeBsdfPrincipled")
        surface.inputs["Roughness"].default_value = {
            "matte": 0.85,
            "clay": 0.9,
            "glossy": 0.18,
            "transparent": 0.22,
        }[name]
        surface.inputs["IOR"].default_value = 1.45
        if name in ("matte", "clay"):
            surface.inputs["Specular IOR Level"].default_value = 0
        links.new(attribute.outputs["Color"], surface.inputs["Base Color"])
        if transparency:
            transparent = nodes.new("ShaderNodeBsdfTransparent")
            mix = nodes.new("ShaderNodeMixShader")
            mix.inputs[0].default_value = transparency
            links.new(surface.outputs[0], mix.inputs[1])
            links.new(transparent.outputs[0], mix.inputs[2])
            surface = mix
    links.new(surface.outputs[0], output.inputs["Surface"])
    return material


if __name__ == "__main__":
    main()
