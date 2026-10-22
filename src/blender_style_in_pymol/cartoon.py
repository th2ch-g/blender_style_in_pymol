"""Backbone-oriented spline meshes with independent secondary-structure profiles."""

import numpy as np

from .mesh import Mesh, ambient_occlusion, combine, linear, normals, srgb, unit


def smooth(values, iterations=1):
    result = np.array(values, dtype=float, copy=True)
    for _ in range(iterations):
        result = (
            np.vstack((result[0], result[:-1]))
            + result
            + np.vstack((result[1:], result[-1]))
        ) / 3
    return result


def spline(points, subdivisions):
    """Evaluate automatic Bezier handles without overshooting short segments."""
    delta = np.diff(points, axis=0)
    lengths = np.linalg.norm(delta, axis=1)
    directions = unit(delta)
    tangent = unit(
        np.vstack((directions[0], directions)) + np.vstack((directions, directions[-1]))
    )
    left = np.r_[lengths[0], lengths]
    right = np.r_[lengths, lengths[-1]]
    left = np.minimum(left, 5 * right)
    right = np.minimum(right, 5 * left)
    handles_left = points - tangent * left[:, None] / 2.5614
    handles_right = points + tangent * right[:, None] / 2.5614
    t = np.linspace(0, 1, subdivisions, endpoint=False)
    b0, b1, b2, b3 = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t**2, t**3
    curve = (
        points[:-1, None] * b0[None, :, None]
        + handles_right[:-1, None] * b1[None, :, None]
        + handles_left[1:, None] * b2[None, :, None]
        + points[1:, None] * b3[None, :, None]
    )
    return np.vstack((curve.reshape(-1, 3), points[-1]))


def interpolate(values, samples):
    positions = np.linspace(0, len(values) - 1, samples)
    before = np.minimum(positions.astype(int), len(values) - 2)
    factor = positions - before
    return values[before] * (1 - factor[:, None]) + values[before + 1] * factor[:, None]


def tube(points, orientation, colors, kind, quality, params, rounded=False):
    subdivisions = {"low": 4, "medium": 7, "high": 12}[quality]
    centers = spline(points, subdivisions)
    tangent = unit(np.gradient(centers, axis=0))
    axis = interpolate(orientation, len(centers))
    axis -= (axis * tangent).sum(axis=1)[:, None] * tangent
    bad = np.linalg.norm(axis, axis=1) < 1e-6
    if np.any(bad):
        fallback = np.eye(3)[np.argmin(np.abs(tangent[bad]), axis=1)]
        axis[bad] = np.cross(tangent[bad], fallback)
    x = unit(axis)
    y = unit(np.cross(tangent, x))
    if kind == "H":
        angle = np.deg2rad(20)
        y = y * np.cos(angle) + tangent * np.sin(angle)
    if kind == "S":
        angle = np.deg2rad(30)
        x, y = (
            x * np.cos(angle) + y * np.sin(angle),
            y * np.cos(angle) - x * np.sin(angle),
        )
    if kind in ("H", "S"):
        sides = {"low": 8, "medium": 12, "high": 16}[quality] if rounded else 4
        angle = np.arange(sides) * 2 * np.pi / sides + np.pi / 4
        thickness = np.full(len(centers), params.get("cartoon_thickness", 0.6))
        width = np.full(len(centers), params.get("cartoon_width", 2.2))
        if kind == "S":
            remaining = np.linspace(len(points) - 1, 0, len(centers))
            width *= np.clip(remaining, 0, 1)
            width += 0.89 * np.clip(remaining, 0, 1) * (remaining < 1)
            width = np.maximum(width, 0.025)
    else:
        sides = {"low": 8, "medium": 12, "high": 20}[quality]
        angle = np.arange(sides) * 2 * np.pi / sides
        radius = (
            params.get("ribbon_radius", 1.6)
            if kind == "R"
            else params.get("loop_radius", 0.3)
        )
        thickness = width = np.full(len(centers), radius)
    vertices = (
        centers[:, None]
        + x[:, None] * (np.cos(angle)[None, :, None] * thickness[:, None, None])
        + y[:, None] * (np.sin(angle)[None, :, None] * width[:, None, None])
    ).reshape(-1, 3)
    row = np.arange(len(centers) - 1)[:, None] * sides
    col = np.arange(sides)[None]
    a, b = row + col, row + (col + 1) % sides
    c, d = a + sides, b + sides
    faces = np.stack(
        (np.stack((a, b, c), axis=-1), np.stack((b, d, c), axis=-1)), axis=-2
    ).reshape(-1, 3)
    ends = []
    for j in range(1, sides - 1):
        ends.extend(
            [
                [0, j + 1, j],
                [
                    (len(centers) - 1) * sides,
                    (len(centers) - 1) * sides + j,
                    (len(centers) - 1) * sides + j + 1,
                ],
            ]
        )
    faces = np.vstack((faces, ends))
    if params.get("color_interpolate", 0):
        color = srgb(interpolate(linear(colors), len(centers)))
    else:
        color = colors[
            np.rint(np.linspace(0, len(colors) - 1, len(centers))).astype(int)
        ]
    color = np.repeat(color, sides, axis=0)
    return Mesh(
        vertices, faces, normals(vertices, faces), color, np.zeros(len(vertices))
    ).compact()


def cartoon(cmd, obj, state, quality, options, budget):
    model = cmd.get_model(f"{obj} and polymer.protein", state=state)
    metadata = {}
    cmd.iterate(
        f"{obj} and polymer.protein",
        "metadata[index] = (color, ss)",
        space={"metadata": metadata},
    )
    residues = {}
    for atom in model.atom:
        residues.setdefault((atom.segi, atom.chain, atom.resi), {}).setdefault(
            atom.name, atom
        )
    chains = []
    current = []
    previous_key = None
    for key, atoms in residues.items():
        if "CA" not in atoms:
            if current:
                chains.append(current)
                current = []
            continue
        if current and (
            key[:2] != previous_key[:2]
            or np.linalg.norm(np.asarray(atoms["CA"].coord) - current[-1]["CA"].coord)
            > 4.5
        ):
            chains.append(current)
            current = []
        current.append(atoms)
        previous_key = key
    if current:
        chains.append(current)
    meshes = []
    for chain in chains:
        if len(chain) < 2:
            continue
        points = np.asarray([a["CA"].coord for a in chain], float)
        orientation = np.asarray(
            [
                0.55 * np.asarray(a.get("C", a["CA"]).coord)
                + 0.45 * np.asarray(a.get("N", a["CA"]).coord)
                - a["CA"].coord
                for a in chain
            ]
        )
        ss = np.array([metadata[a["CA"].index][1] for a in chain])
        colors = np.asarray(
            [cmd.get_color_tuple(metadata[a["CA"].index][0]) for a in chain]
        )
        fallback = np.gradient(np.gradient(points, axis=0), axis=0)
        missing = np.linalg.norm(orientation, axis=1) < 1e-6
        orientation[missing] = fallback[missing]
        orientation = unit(orientation)
        for i in range(1, len(orientation)):
            cutoff = -0.7 if ss[i] == "H" else 0
            if (
                ss[i] == ss[i - 1]
                and np.dot(orientation[i], orientation[i - 1]) < cutoff
            ):
                orientation[i] *= -1
        if options.representation in ("ribbon", "preset-1"):
            pieces = [(np.arange(len(points)), "R")]
        else:
            sheet = ss == "S"
            points[sheet] = 0.5 * (points[sheet] + smooth(points, 3)[sheet])
            orientation[sheet] = smooth(orientation)[sheet]
            pieces = []
            breaks = np.r_[0, np.flatnonzero(ss[:-1] != ss[1:]) + 1, len(ss)]
            for start, end in zip(breaks[:-1], breaks[1:]):
                kind = ss[start] if ss[start] in ("H", "S") and end - start > 1 else "L"
                if kind == "L":
                    start, end = max(0, start - 1), min(len(ss), end + 1)
                if end - start > 1:
                    pieces.append((np.arange(start, end), kind))
            for i in range(len(ss) - 1):
                if (
                    ss[i] in ("H", "S")
                    and ss[i + 1] in ("H", "S")
                    and ss[i] != ss[i + 1]
                ):
                    pieces.append((np.array([i, i + 1]), "L"))
        for ids, kind in pieces:
            p = points[ids].copy()
            color = colors[ids].copy()
            if kind == "L" and len(ids) > 2:
                if ss[ids[0]] in ("H", "S"):
                    color[0] = color[1]
                if ss[ids[-1]] in ("H", "S"):
                    color[-1] = color[-2]
            if kind == "S":
                p[0] -= unit(p[1] - p[0]) * 0.2
                p[-1] += unit(p[-1] - p[-2]) * 0.2
            mesh = tube(
                p,
                orientation[ids],
                color,
                kind,
                quality,
                options.params,
                rounded=options.representation == "cartoon-rounded",
            )
            meshes.append(mesh)
            budget -= mesh.nbytes + len(mesh.faces) * 160
            if budget < 0:
                raise ValueError(
                    "Cartoon mesh exceeds memory_mb; use lower quality or a smaller selection"
                )
    from .nucleic import pieces as nucleic_pieces

    meshes.extend(nucleic_pieces(cmd, obj, state, quality, options))
    mesh = combine(meshes)
    if mesh is not None:
        mesh.occlusion = ambient_occlusion(mesh)
    return mesh
