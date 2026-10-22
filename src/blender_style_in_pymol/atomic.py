"""Smooth atomic meshes for bounded static scenes with physical shading."""

from functools import lru_cache

import numpy as np

from .mesh import Mesh, ambient_occlusion, combine, unit


@lru_cache(maxsize=3)
def sphere_template(quality):
    sides = {"low": 12, "medium": 20, "high": 32}[quality]
    rows = sides // 2
    azimuth = np.arange(sides) * 2 * np.pi / sides
    polar = np.arange(1, rows) * np.pi / rows
    vertices = np.column_stack(
        (
            (np.sin(polar)[:, None] * np.cos(azimuth)).ravel(),
            (np.sin(polar)[:, None] * np.sin(azimuth)).ravel(),
            np.repeat(np.cos(polar), sides),
        )
    )
    vertices = np.vstack(([0, 0, 1], vertices, [0, 0, -1]))
    faces = []
    for j in range(sides):
        faces.append([0, 1 + j, 1 + (j + 1) % sides])
    for i in range(rows - 2):
        for j in range(sides):
            a, b = 1 + i * sides + j, 1 + i * sides + (j + 1) % sides
            faces.extend([[a, a + sides, b], [b, a + sides, b + sides]])
    for j in range(sides):
        a, b = 1 + (rows - 2) * sides + j, 1 + (rows - 2) * sides + (j + 1) % sides
        faces.append([a, len(vertices) - 1, b])
    return vertices.astype(np.float32), np.asarray(faces, np.int32)


def sphere(center, radius, color, quality):
    vertices, faces = sphere_template(quality)
    return Mesh(
        vertices * radius + center,
        faces,
        vertices,
        np.tile(color, (len(vertices), 1)),
        np.zeros(len(vertices)),
    ).compact()


def cylinder(start, end, radius, color, quality):
    sides = {"low": 10, "medium": 16, "high": 24}[quality]
    axis = unit(end - start)
    x = unit(np.cross(axis, np.eye(3)[np.argmin(np.abs(axis))]))
    y = np.cross(axis, x)
    angle = np.arange(sides) * 2 * np.pi / sides
    n = x * np.cos(angle)[:, None] + y * np.sin(angle)[:, None]
    vertices = np.vstack((start + n * radius, end + n * radius))
    j = np.arange(sides)
    k = (j + 1) % sides
    faces = np.concatenate(
        (np.column_stack((j, k, j + sides)), np.column_stack((k, k + sides, j + sides)))
    )
    return Mesh(
        vertices,
        faces,
        np.vstack((n, n)),
        np.tile(color, (len(vertices), 1)),
        np.zeros(len(vertices)),
    ).compact()


def atomic(cmd, obj, state, quality, options, budget):
    model = cmd.get_model(obj, state=state)
    color_indices = {}
    cmd.iterate(
        obj, "color_indices[index] = color", space={"color_indices": color_indices}
    )
    coords = np.asarray([a.coord for a in model.atom])
    colors = np.asarray(
        [cmd.get_color_tuple(color_indices[a.index]) for a in model.atom]
    )
    rep = options.representation
    radius = options.params.get("bond_radius", 0.3 if rep == "ball-and-stick" else 0.2)
    scale = options.params.get("sphere_scale", 0.8 if rep == "spheres" else 0.3)
    radii = (
        np.asarray([a.vdw * scale for a in model.atom])
        if rep != "sticks"
        else np.full(len(coords), radius)
    )
    pieces = []
    bonded = {index for bond in model.bond for index in bond.index}
    for i, (position, r, color) in enumerate(zip(coords, radii, colors)):
        if rep != "sticks" or i in bonded:
            pieces.append(sphere(position, r, color, quality))
    if rep != "spheres":
        for bond in model.bond:
            a, b = bond.index
            if np.linalg.norm(coords[a] - coords[b]) < 1e-6:
                continue
            middle = (coords[a] + coords[b]) / 2
            pieces.append(cylinder(coords[a], middle, radius, colors[a], quality))
            pieces.append(cylinder(middle, coords[b], radius, colors[b], quality))
    mesh = combine(pieces)
    if mesh is not None:
        if mesh.nbytes + len(mesh.faces) * 1200 > budget:
            raise ValueError(
                "Atomic mesh exceeds memory_mb; use lower quality or backend=native"
            )
        mesh.occlusion = ambient_occlusion(mesh)
    return mesh
