"""Small reproducible visualization inputs, without external data dependencies."""

import math
from pathlib import Path

import numpy as np

from blender_style_in_pymol import blender_load_oxdna


def density(cmd):
    from chempy.brick import Brick

    x, y, z = np.mgrid[-8:8:48j, -8:8:48j, -8:8:48j]
    positive = np.exp(-((x - 2.5) ** 2 + (y - 0.4) ** 2 + z * z) / 4)
    negative = np.exp(-((x + 2.5) ** 2 + (y + 0.4) ** 2 + z * z) / 4)
    field = (positive - negative).astype(np.float32)
    cmd.load_brick(
        Brick.from_numpy(field, grid=(16 / 47,) * 3, origin=(-8,) * 3), "density"
    )
    return "Synthetic signed Gaussian field"


def oxdna(cmd, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    top, trajectory = directory / "duplex.top", directory / "duplex.dat"
    count = 18
    top.write_text(f"{2 * count} 2 5->3\n" + "ACGTACGTACGTACGTAC\nGTACGTACGTACGTACGT\n")
    rows = []
    for strand in range(2):
        for i in range(count):
            level = i if strand == 0 else count - i - 1
            angle = level * 2 * math.pi / 10.5 + strand * math.pi
            position = (0.7 * math.cos(angle), 0.7 * math.sin(angle), level * 0.4)
            axis = (-math.cos(angle), -math.sin(angle), 0)
            normal = (0, 0, 1 if strand == 0 else -1)
            rows.append(
                " ".join(
                    f"{value:.8f}"
                    for value in (*position, *axis, *normal, 0, 0, 0, 0, 0, 0)
                )
            )
    trajectory.write_text("t = 0\nb = 20 20 20\nE = 0 0 0\n" + "\n".join(rows) + "\n")
    blender_load_oxdna(top, trajectory, name="sample", _self=cmd)
    return "Synthetic oxDNA duplex (36 nucleotides)"
