"""Compact indexed meshes and native PyMOL display lists."""

from dataclasses import dataclass

import numpy as np
from scipy import sparse


def cache(cmd):
    session = cmd._pymol.session
    if not hasattr(session, "blender_style_meshes"):
        session.blender_style_meshes = {}
    return session.blender_style_meshes


def callback_names(cmd):
    session = cmd._pymol.session
    if not hasattr(session, "blender_style_callbacks"):
        session.blender_style_callbacks = {}
    return session.blender_style_callbacks


def unit(values):
    values = np.asarray(values, dtype=np.float64)
    return values / np.maximum(np.linalg.norm(values, axis=-1, keepdims=True), 1e-12)


def linear(rgb):
    rgb = np.asarray(rgb)
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)


def srgb(rgb):
    rgb = np.maximum(rgb, 0)
    return np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * rgb ** (1 / 2.4) - 0.055)


def adjacency(faces, count):
    edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    edges = np.concatenate([edges, edges[:, ::-1]])
    graph = sparse.coo_matrix(
        (np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(count, count)
    ).tocsr()
    graph.data[:] = 1
    graph.setdiag(1)
    return sparse.diags(1 / np.asarray(graph.sum(axis=1)).ravel()) @ graph


def normals(vertices, faces):
    triangles = vertices[faces]
    face_normals = np.cross(
        triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
    )
    result = np.zeros_like(vertices)
    for i in range(3):
        np.add.at(result, faces[:, i], face_normals)
    return unit(result)


@dataclass
class Mesh:
    vertices: np.ndarray
    faces: np.ndarray
    normals: np.ndarray
    colors: np.ndarray
    occlusion: np.ndarray

    def compact(self):
        self.vertices = self.vertices.astype(np.float32)
        self.faces = self.faces.astype(np.int32)
        self.normals = self.normals.astype(np.float32)
        self.colors = self.colors.astype(np.float32)
        self.occlusion = self.occlusion.astype(np.float32)
        return self

    @property
    def nbytes(self):
        return sum(
            a.nbytes
            for a in (
                self.vertices,
                self.faces,
                self.normals,
                self.colors,
                self.occlusion,
            )
        )


def combine(meshes):
    if not meshes:
        return None
    offsets = np.cumsum([0, *[len(m.vertices) for m in meshes]])
    return Mesh(
        np.concatenate([m.vertices for m in meshes]),
        np.concatenate([m.faces + offset for m, offset in zip(meshes, offsets)]),
        np.concatenate([m.normals for m in meshes]),
        np.concatenate([m.colors for m in meshes]),
        np.concatenate([m.occlusion for m in meshes]),
    ).compact()


def refine(mesh, levels=1):
    for _ in range(levels):
        faces = mesh.faces
        edges = np.concatenate((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]))
        edges.sort(axis=1)
        unique, inverse = np.unique(edges, axis=0, return_inverse=True)
        mid = inverse.reshape(3, len(faces)).T + len(mesh.vertices)
        a, b, c = faces.T
        ab, bc, ca = mid.T
        triangles = np.concatenate(
            (
                np.column_stack((a, ab, ca)),
                np.column_stack((ab, b, bc)),
                np.column_stack((ca, bc, c)),
                np.column_stack((ab, bc, ca)),
            )
        )
        mesh = Mesh(
            np.vstack((mesh.vertices, mesh.vertices[unique].mean(axis=1))),
            triangles,
            np.vstack((mesh.normals, mesh.normals[unique].mean(axis=1))),
            np.vstack((mesh.colors, mesh.colors[unique].mean(axis=1))),
            np.r_[mesh.occlusion, mesh.occlusion[unique].mean(axis=1)],
        ).compact()
    return mesh


def display_list(mesh, material, rotation=None):
    from pymol.cgo import BEGIN, COLOR, END, NORMAL, TRIANGLE, TRIANGLES, VERTEX

    if rotation is not None:
        from .lighting import shade

        faces = mesh.faces[:, ::-1]
        color = shade(mesh, material, rotation)
        values = np.empty((len(faces), 28), np.float32)
        values[:, 0] = TRIANGLE
        values[:, 1:10] = mesh.vertices[faces].reshape(-1, 9)
        values[:, 10:19] = mesh.normals[faces].reshape(-1, 9)
        values[:, 19:28] = color[faces].reshape(-1, 9)
        return values.ravel().tolist()

    strength = 0 if material in ("flat", "outline", "transparent") else 0.4
    if material == "ambient-occlusion":
        strength = 1.0
    color = srgb(linear(mesh.colors) * (1 - strength * mesh.occlusion[:, None]))
    ids = mesh.faces.ravel()
    values = np.empty((len(ids), 12), np.float32)
    values[:, 0] = NORMAL
    values[:, 1:4] = mesh.normals[ids]
    values[:, 4] = COLOR
    values[:, 5:8] = color[ids]
    values[:, 8] = VERTEX
    values[:, 9:12] = mesh.vertices[ids]
    return [BEGIN, TRIANGLES, *values.ravel().tolist(), END]


def load(cmd, name, meshes, options):
    from .gpu import Drawing

    physical = options.lighting == "auto"
    registry = getattr(cmd._pymol, "_blender_drawings", None)
    if registry is None:
        registry = cmd._pymol._blender_drawings = {}
    names = callback_names(cmd)
    callback, drawings = names.get(name, cmd.get_unused_name("_bs_shader")), []
    try:
        for state, mesh in enumerate(meshes, 1):
            rotation = cmd.get_view()[:9] if physical else None
            cmd.load_cgo(
                display_list(mesh, options.material, rotation),
                name,
                state=state,
                zoom=0,
                quiet=1,
            )
            if physical:
                drawing = Drawing(mesh, options.material, options.transparency)
                drawings.append(drawing)
                cmd.load_callback(drawing, callback, state, 1, 0, 1, 0)
    except Exception:
        if name not in names:
            cmd.delete(callback)
        raise
    if physical:
        registry[name] = callback, drawings
        names[name] = callback
    cmd.set("cgo_transparency", options.transparency, name, quiet=1)
    cmd.set(
        "cgo_lighting",
        int(
            not physical
            and options.material not in ("flat", "outline", "ambient-occlusion")
        ),
        name,
        quiet=1,
    )
    return callback if physical else None


def ambient_occlusion(mesh):
    """Approximate mesh visibility using area-weighted oriented surface patches."""
    from scipy.spatial import cKDTree

    triangles = mesh.vertices[mesh.faces]
    centers = triangles.mean(axis=1)
    vectors = np.cross(
        triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
    )
    areas = np.linalg.norm(vectors, axis=1) * 0.5
    face_normals = unit(vectors)
    octant = np.sum((face_normals > 0) * [1, 2, 4], axis=1)
    keys = np.column_stack((np.floor(centers / 1.25).astype(np.int32), octant))
    _, groups = np.unique(keys, axis=0, return_inverse=True)
    area = np.bincount(groups, weights=areas)
    positions = np.column_stack(
        [np.bincount(groups, weights=areas * centers[:, i]) for i in range(3)]
    ) / np.maximum(area[:, None], 1e-12)
    patch_normals = unit(
        np.column_stack(
            [np.bincount(groups, weights=areas * face_normals[:, i]) for i in range(3)]
        )
    )
    tree = cKDTree(positions)
    result = np.empty(len(mesh.vertices), np.float32)
    k = min(128, len(positions))
    for start in range(0, len(mesh.vertices), 512):
        p = mesh.vertices[start : start + 512]
        n = mesh.normals[start : start + 512]
        p = p + n * 0.05
        distance, index = tree.query(p, k=k)
        distance, index = distance.reshape(len(p), k), index.reshape(len(p), k)
        direction = (positions[index] - p[:, None]) / np.maximum(
            distance[:, :, None], 1e-6
        )
        receiving = np.maximum(np.sum(direction * n[:, None], axis=2), 0)
        facing = np.maximum(-np.sum(direction * patch_normals[index], axis=2), 0)
        contribution = (
            area[index]
            / (np.pi * distance**2 + area[index] + 1e-8)
            * receiving
            * facing
        )
        result[start : start + len(p)] = np.minimum(contribution.sum(axis=1), 0.97)
    return result
