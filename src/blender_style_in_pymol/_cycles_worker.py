"""Isolated Blender worker; invoked by cycles.py, never imported by PyMOL."""

import json
import math
import sys
from pathlib import Path


def linear(rgb):
    import numpy as np

    rgb = np.asarray(rgb)
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)


def material(bpy, item):
    name, optical = item["material"], item["optical"]
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    color = nodes.new("ShaderNodeVertexColor")
    color.layer_name = "Color"
    if name in ("flat", "ambient-occlusion", "outline"):
        surface = nodes.new("ShaderNodeEmission")
        links.new(color.outputs["Color"], surface.inputs["Color"])
    else:
        surface = nodes.new("ShaderNodeBsdfPrincipled")
        surface.inputs["Roughness"].default_value = optical["roughness"]
        surface.inputs["IOR"].default_value = optical["ior"]
        surface.inputs["Transmission Weight"].default_value = optical["transmission"]
        surface.inputs["Subsurface Weight"].default_value = optical["subsurface"]
        surface.inputs["Subsurface Radius"].default_value = (1.0, 0.2, 0.1)
        surface.inputs["Subsurface Scale"].default_value = (
            optical["subsurface_radius"] * 0.01
        )
        surface.subsurface_method = "RANDOM_WALK"
        if name in ("matte", "clay"):
            surface.inputs["Specular IOR Level"].default_value = 0
        links.new(color.outputs["Color"], surface.inputs["Base Color"])
    if name in ("ambient-occlusion", "outline"):
        occlusion = nodes.new("ShaderNodeAmbientOcclusion")
        occlusion.inputs["Distance"].default_value = 0.1
        power = nodes.new("ShaderNodeMath")
        power.operation = "POWER"
        power.inputs[1].default_value = 1.5
        links.new(occlusion.outputs["AO"], power.inputs[0])
        factor = power.outputs[0]
        if name == "outline":
            ramp = nodes.new("ShaderNodeMapRange")
            ramp.inputs["From Max"].default_value = 0.30909145
            ramp.inputs["To Max"].default_value = 0.65065384
            links.new(factor, ramp.inputs["Value"])
            fresnel = nodes.new("ShaderNodeFresnel")
            fresnel.inputs["IOR"].default_value = 0.95
            inverse = nodes.new("ShaderNodeMath")
            inverse.operation = "SUBTRACT"
            inverse.inputs[0].default_value = 1
            links.new(fresnel.outputs[0], inverse.inputs[1])
            multiply = nodes.new("ShaderNodeMath")
            multiply.operation = "MULTIPLY"
            links.new(ramp.outputs[0], multiply.inputs[0])
            links.new(inverse.outputs[0], multiply.inputs[1])
            factor = multiply.outputs[0]
        mix_color = nodes.new("ShaderNodeMixRGB")
        mix_color.blend_type = "MULTIPLY"
        mix_color.inputs[0].default_value = 1
        links.new(color.outputs["Color"], mix_color.inputs[1])
        links.new(factor, mix_color.inputs[2])
        links.new(mix_color.outputs[0], surface.inputs["Color"])
    if item["transparency"]:
        transparent = nodes.new("ShaderNodeBsdfTransparent")
        mix = nodes.new("ShaderNodeMixShader")
        mix.inputs[0].default_value = item["transparency"]
        links.new(surface.outputs[0], mix.inputs[1])
        links.new(transparent.outputs[0], mix.inputs[2])
        surface = mix
    links.new(surface.outputs[0], output.inputs["Surface"])
    return material


def main():
    import _cycles
    import bpy
    import numpy as np
    from mathutils import Matrix, Vector

    if bpy.app.version < (4, 0, 0):
        raise RuntimeError("Blender 4.0 or newer is required")
    directory = Path(sys.argv[sys.argv.index("--") + 1])
    data = json.loads((directory / "scene.json").read_text(encoding="utf-8"))
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    view = np.asarray(data["view"])
    rotation = view[:9].reshape(3, 3).T
    if data["angle"]:
        theta = math.radians(data["angle"])
        c, s = math.cos(theta), math.sin(theta)
        rotation = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]) @ rotation
    transform = np.eye(4)
    transform[:3, :3] = rotation
    transform[:3, 3] = (-rotation @ view[12:15] + [view[9], view[10], 0]) * 0.01
    for i, item in enumerate(data["objects"]):
        arrays = np.load(directory / item["file"], allow_pickle=False)
        vertices, faces = arrays["vertices"], arrays["faces"]
        mesh = bpy.data.meshes.new(f"Mesh {i}")
        mesh.vertices.add(len(vertices))
        mesh.vertices.foreach_set("co", (vertices * 0.01).ravel())
        mesh.loops.add(faces.size)
        mesh.loops.foreach_set("vertex_index", faces.ravel())
        mesh.polygons.add(len(faces))
        mesh.polygons.foreach_set("loop_start", np.arange(len(faces)) * 3)
        mesh.polygons.foreach_set("loop_total", np.full(len(faces), 3))
        mesh.polygons.foreach_set("use_smooth", np.ones(len(faces), dtype=bool))
        mesh.update(calc_edges=True)
        mesh.normals_split_custom_set_from_vertices(arrays["normals"].tolist())
        colors = mesh.color_attributes.new("Color", "FLOAT_COLOR", "POINT")
        rgba = np.column_stack((linear(arrays["colors"]), np.ones(len(vertices))))
        colors.data.foreach_set("color", rgba.ravel())
        mesh.materials.append(material(bpy, item))
        obj = bpy.data.objects.new(f"Molecule {i}", mesh)
        bpy.context.scene.collection.objects.link(obj)
        object_matrix = np.asarray(item["matrix"]).reshape(4, 4).copy()
        object_matrix[:3, 3] *= 0.01
        obj.matrix_world = Matrix((transform @ object_matrix).tolist())

    scene = bpy.context.scene
    camera_data = bpy.data.cameras.new("PyMOL camera")
    camera = bpy.data.objects.new("PyMOL camera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = (0, 0, -view[11] * 0.01)
    camera.rotation_euler = (0, 0, 0)
    camera_data.sensor_fit = "HORIZONTAL"
    width, height = data["width"], data["height"]
    tangent = math.tan(math.radians(data["field_of_view"]) * 0.5)
    if data["orthoscopic"]:
        camera_data.type = "ORTHO"
        camera_data.ortho_scale = -2 * view[11] * tangent * 0.01 * width / height
    else:
        camera_data.type = "PERSP"
        camera_data.lens = camera_data.sensor_width / (2 * tangent * width / height)
    camera_data.clip_start = max(0.00001, view[15] * 0.01)
    camera_data.clip_end = max(camera_data.clip_start + 0.01, view[16] * 0.01)
    scene.camera = camera

    world = bpy.data.worlds.new("Studio")
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    light = nodes["Background"]
    light.inputs["Color"].default_value = (1, 1, 1, 1)
    light.inputs["Strength"].default_value = 0.35
    background = nodes.new("ShaderNodeBackground")
    background.inputs["Color"].default_value = (*linear(data["background"]), 1)
    ray = nodes.new("ShaderNodeLightPath")
    mix = nodes.new("ShaderNodeMixShader")
    links.new(ray.outputs["Is Camera Ray"], mix.inputs[0])
    links.new(light.outputs[0], mix.inputs[1])
    links.new(background.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], nodes["World Output"].inputs["Surface"])
    scene.world = world
    for name, position, power, size in (
        ("Key", (-0.45, 0.55, 0.8), 3, 0.65),
        ("Fill", (0.5, 0.15, 0.6), 1.2, 0.75),
        ("Rim", (0.1, -0.5, 0.35), 1.8, 0.5),
    ):
        light = bpy.data.lights.new(name, "AREA")
        light.energy, light.shape, light.size = power, "DISK", size
        obj = bpy.data.objects.new(name, light)
        scene.collection.objects.link(obj)
        obj.location = position
        obj.rotation_euler = (-Vector(position)).to_track_quat("-Z", "Y").to_euler()

    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = data["samples"]
    scene.cycles.seed = 0
    scene.cycles.use_denoising = bool(getattr(_cycles, "with_openimagedenoise", False))
    if scene.cycles.use_denoising:
        scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.cycles.max_bounces = 16
    scene.cycles.transmission_bounces = 12
    scene.cycles.transparent_max_bounces = 16
    scene.cycles.film_transparent_glass = True
    scene.render.resolution_x, scene.render.resolution_y = width, height
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = data["transparent"]
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure, scene.view_settings.gamma = 0, 1
    scene.render.filepath = str(directory / "render.png")
    bpy.ops.render.render(write_still=True)
    metadata = {
        "blender": bpy.app.version_string,
        "engine": "Cycles CPU",
        "denoising": scene.cycles.use_denoising,
        "materials": [
            {"name": item["material"], **item["optical"]} for item in data["objects"]
        ],
        "vertices": sum(
            len(obj.data.vertices) for obj in scene.objects if obj.type == "MESH"
        ),
    }
    try:
        import resource

        metadata["peak_rss_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (
            1024**2 if sys.platform == "darwin" else 1024
        )
    except ImportError:
        pass
    (directory / "result.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
