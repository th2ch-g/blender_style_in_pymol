"""Chain-separated, relaxed molecular surfaces with interpolated linear colors."""

import numpy as np
from scipy.spatial import cKDTree
from skimage.measure import marching_cubes

from .mesh import (
    Mesh,
    adjacency,
    ambient_occlusion,
    combine,
    linear,
    normals,
    srgb,
    unit,
)


def grid_spec(coords, radii, quality):
    if not np.isfinite(coords).all() or not np.isfinite(radii).all():
        raise ValueError("Surface coordinates and radii must be finite")
    spacing = {"low": 1.2, "medium": 0.85, "high": 2 / 3}[quality]
    padding = float(np.max(radii)) + spacing * 2
    lower = np.floor(coords.min(axis=0) - padding)
    upper = np.ceil(coords.max(axis=0) + padding)
    shape = np.maximum(np.ceil((upper - lower) / spacing).astype(int) + 1, 3)
    return lower, shape, spacing


def build(coords, radii, color_coords, colors, quality, params, budget):
    scale = params.get("surface_scale", 1.5)
    probe = params.get("probe_radius", 1.0)
    effective = radii * scale
    lower, shape, spacing = grid_spec(coords, effective + probe, quality)
    cells = int(np.prod(shape.astype(object)))
    if cells * 16 > budget:
        raise ValueError(
            "Surface grid exceeds memory_mb; use lower quality, separate chains, or a smaller selection"
        )
    tree = cKDTree(coords)
    field = np.empty(cells, np.float32)
    yz = int(shape[1] * shape[2])
    for start in range(0, cells, 65536):
        ids = np.arange(start, min(start + 65536, cells))
        grid = np.column_stack(
            (ids // yz, (ids // shape[2]) % shape[1], ids % shape[2])
        )
        points = lower + grid * spacing
        distance, index = tree.query(points)
        field[start : start + len(ids)] = distance < effective[index] + probe
    vertices, faces, _, _ = marching_cubes(
        field.reshape(tuple(shape)), level=0.1, spacing=(spacing,) * 3
    )
    del field
    vertices += lower
    _, nearest = tree.query(vertices)
    vertices = (
        coords[nearest] + unit(vertices - coords[nearest]) * effective[nearest, None]
    )
    graph = adjacency(faces, len(vertices))
    initial = vertices.copy()
    for _ in range(2):
        vertices = graph @ vertices
    vertex_normals = normals(vertices, faces)
    # Marching cubes emits inward winding for the occupied density convention.
    if np.mean(np.sum(vertex_normals * (vertices - coords[nearest]), axis=1)) < 0:
        faces = faces[:, ::-1].copy()
        vertex_normals *= -1
    vertices -= (
        vertex_normals * (1.8 * np.linalg.norm(vertices - initial, axis=1))[:, None]
    )
    for _ in range(2):
        vertices = graph @ vertices
    for _ in range(int(params.get("surface_relaxation", 10))):
        average = graph @ vertices
        vertex_normals = normals(vertices, faces)
        concavity = np.clip(
            np.sum((average - vertices) * vertex_normals, axis=1) / spacing * 3, 0, 1
        )
        concavity = graph @ (graph @ concavity)
        vertices += (average - vertices) * concavity[:, None]
    vertex_normals = normals(vertices, faces)
    _, nearest_color = cKDTree(color_coords).query(vertices)
    color = linear(colors[nearest_color])
    for _ in range(int(params.get("color_blur", 2))):
        color = graph @ color
    return Mesh(
        vertices, faces, vertex_normals, srgb(color), np.zeros(len(vertices))
    ).compact()


def surface(cmd, obj, state, quality, options, budget):
    selection = obj
    if options.representation == "preset-3":
        selection += " and polymer.protein"
    model = cmd.get_model(selection, state=state)
    color_indices = {}
    cmd.iterate(
        selection,
        "color_indices[index] = color",
        space={"color_indices": color_indices},
    )
    groups = {}
    for atom in model.atom:
        key = (
            (atom.segi, atom.chain)
            if options.params.get("surface_separate_chains", 1)
            else ()
        )
        groups.setdefault(key, []).append(atom)
    meshes = []
    for atoms in groups.values():
        coords = np.asarray([a.coord for a in atoms])
        radii = np.asarray([a.vdw for a in atoms])
        anchors = [a for a in atoms if a.name in ("CA", "C3'")]
        if not anchors or not options.params.get("surface_color_ca", 1):
            anchors = atoms
        color_coords = np.asarray([a.coord for a in anchors])
        colors = np.asarray(
            [cmd.get_color_tuple(color_indices[a.index]) for a in anchors]
        )
        mesh = build(
            coords, radii, color_coords, colors, quality, options.params, budget
        )
        meshes.append(mesh)
        budget -= mesh.nbytes + len(mesh.faces) * 160
        if budget < 0:
            raise ValueError(
                "Surface meshes exceed memory_mb; use lower quality or a smaller selection"
            )
    mesh = combine(meshes)
    if mesh is not None:
        mesh.occlusion = ambient_occlusion(mesh)
    return mesh
