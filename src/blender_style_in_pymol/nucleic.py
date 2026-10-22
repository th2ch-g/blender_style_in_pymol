"""C4-prime backbones and oriented rectangular nucleic bases."""

import numpy as np

from .mesh import Mesh, unit


def base(position, z, x, color, thickness):
    z = unit(z)
    x = unit(x - np.dot(x, z) * z)
    y = np.cross(z, x)
    corners = np.array(
        [
            [-1, -1, 0],
            [1, -1, 0],
            [1, 1, 0],
            [-1, 1, 0],
            [-1, -1, 1],
            [1, -1, 1],
            [1, 1, 1],
            [-1, 1, 1],
        ],
        float,
    )
    corners *= [2.5 / np.sqrt(2), thickness / np.sqrt(2), 7]
    corners = position + corners @ np.array([x, y, z])
    quads = np.array(
        [
            [0, 3, 2, 1],
            [4, 5, 6, 7],
            [0, 1, 5, 4],
            [1, 2, 6, 5],
            [2, 3, 7, 6],
            [3, 0, 4, 7],
        ]
    )
    vertices = corners[quads].reshape(-1, 3)
    face_normals = unit(
        np.cross(
            corners[quads[:, 1]] - corners[quads[:, 0]],
            corners[quads[:, 2]] - corners[quads[:, 0]],
        )
    )
    faces = np.concatenate([np.array([[0, 1, 2], [0, 2, 3]]) + i * 4 for i in range(6)])
    return Mesh(
        vertices,
        faces,
        np.repeat(face_normals, 4, axis=0),
        np.tile(color, (24, 1)),
        np.zeros(24),
    ).compact()


def pieces(cmd, obj, state, quality, options):
    from .cartoon import tube

    selection = f"{obj} and polymer.nucleic"
    model = cmd.get_model(selection, state=state)
    metadata = {}
    cmd.iterate(selection, "metadata[index] = color", space={"metadata": metadata})
    residues = {}
    for atom in model.atom:
        residues.setdefault((atom.segi, atom.chain, atom.resi), {}).setdefault(
            atom.name.replace("*", "'"), atom
        )
    chains, chain = [], []
    previous = None
    for key, atoms in residues.items():
        if "C4'" not in atoms:
            if chain:
                chains.append(chain)
                chain = []
            continue
        if chain and (
            key[:2] != previous[:2]
            or np.linalg.norm(np.asarray(atoms["C4'"].coord) - chain[-1]["C4'"].coord)
            > 10
        ):
            chains.append(chain)
            chain = []
        chain.append(atoms)
        previous = key
    if chain:
        chains.append(chain)
    meshes = []
    ribbon = options.representation in ("ribbon", "preset-1")
    for chain in chains:
        positions, orientations, colors = [], [], []
        for atoms in chain:
            anchor = atoms["C4'"]
            position = np.asarray(anchor.coord)
            pyrimidine = "N9" not in atoms
            first, second = ("N3", "C6") if pyrimidine else ("N1", "C8")
            orientation = np.array([0.0, 0.0, 1.0])
            if all(name in atoms for name in ("C1'", first, second)):
                z = np.asarray(atoms[first].coord) - atoms["C1'"].coord
                x = np.asarray(atoms[first].coord) - atoms[second].coord
                orientation = unit(x)
                color = cmd.get_color_tuple(metadata[atoms.get("C5", anchor).index])
                meshes.append(base(position, z, x, color, 0.5 if ribbon else 0.8))
            positions.append(position)
            orientations.append(orientation)
            colors.append(cmd.get_color_tuple(metadata[anchor.index]))
        if len(positions) > 1:
            positions = np.asarray(positions)
            positions[0] -= unit(positions[1] - positions[0]) * 2
            positions[-1] += unit(positions[-1] - positions[-2]) * 2
            params = {
                **options.params,
                "ribbon_radius": options.params.get(
                    "nucleic_radius", 1.6 if ribbon else 2.0
                ),
            }
            meshes.append(
                tube(
                    positions,
                    np.asarray(orientations),
                    np.asarray(colors),
                    "R",
                    quality,
                    params,
                )
            )
    return meshes
