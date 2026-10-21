"""Read oxDNA orientations and render compact state-specific CGO primitives."""

import math
import re
from itertools import islice
from pathlib import Path

from .presets import integer, number

UNIT_ANGSTROM = 8.518


def _base(token):
    if token in ("A", "G", "C", "T", "U"):
        return token
    value = int(token)
    return "AGCT"[(value if value >= 0 else 3 - value) % 4]


def topology(path, max_nucleotides=None):
    with Path(path).expanduser().open() as stream:
        header = next(
            (
                line.split("#", 1)[0].split()
                for line in stream
                if line.split("#", 1)[0].strip()
            ),
            [],
        )
        if len(header) not in (2, 3) or (len(header) == 3 and header[2] != "5->3"):
            raise ValueError("Invalid oxDNA topology header")
        count, strands = map(int, header[:2])
        if max_nucleotides is not None and count > max_nucleotides:
            raise ValueError("Estimated oxDNA loading memory exceeds memory_mb")
        lines = []
        for line in stream:
            line = line.split("#", 1)[0].strip()
            if line:
                lines.append(line)
                if len(lines) > count:
                    raise ValueError("Too many oxDNA topology records")
    if min(count, strands) < 1:
        raise ValueError("Topology counts must be positive")
    rows = []
    if len(header) == 3 and header[2] == "5->3":
        if len(lines) != strands:
            raise ValueError("Topology strand count does not match its header")
        for strand, line in enumerate(lines, 1):
            parts = line.split()
            bases = re.findall(r"[ACGTU]|\(-?\d+\)", parts[0])
            if "".join(bases) != parts[0] or not bases:
                raise ValueError("Invalid oxDNA sequence")
            circular = "circular=true" in parts[1:]
            offset = len(rows)
            for i, base in enumerate(bases):
                previous = offset + (i - 1) % len(bases) if i or circular else -1
                following = (
                    offset + (i + 1) % len(bases)
                    if i + 1 < len(bases) or circular
                    else -1
                )
                rows.append((strand, _base(base.strip("()")), previous, following))
    else:
        for line in lines:
            strand, base, previous, following = line.split()
            rows.append((int(strand), _base(base), int(previous), int(following)))
    if len(rows) != count or len({row[0] for row in rows}) != strands:
        raise ValueError(
            "Topology nucleotide or strand count does not match its header"
        )
    for index, row in enumerate(rows):
        for neighbor in row[2:]:
            if neighbor < -1 or neighbor >= count or neighbor == index:
                raise ValueError("Invalid oxDNA backbone neighbor")
            if neighbor >= 0 and (
                rows[neighbor][0] != row[0] or index not in rows[neighbor][2:]
            ):
                raise ValueError("Non-reciprocal oxDNA backbone link")
    return rows


def _unit(vector):
    length = math.sqrt(sum(value * value for value in vector))
    if length < 1e-8:
        raise ValueError("oxDNA orientation vectors must be nonzero")
    return tuple(value / length for value in vector)


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def configurations(path, count):
    with Path(path).expanduser().open() as stream:
        while True:
            line = stream.readline()
            if not line:
                return
            if not line.strip():
                continue
            if not line.lstrip().startswith("t"):
                raise ValueError("Expected an oxDNA configuration time header")
            if not stream.readline().lstrip().startswith(
                "b"
            ) or not stream.readline().lstrip().startswith("E"):
                raise ValueError("Incomplete oxDNA configuration header")
            positions = []
            for _ in range(count):
                values = [float(value) for value in stream.readline().split()]
                if len(values) not in (9, 15) or not all(
                    math.isfinite(value) for value in values
                ):
                    raise ValueError(
                        "Each nucleotide needs finite position and orientation values"
                    )
                center = tuple(value * UNIT_ANGSTROM for value in values[:3])
                axis = _unit(values[3:6])
                normal = _unit(values[6:9])
                if abs(sum(a * b for a, b in zip(axis, normal))) > 0.1:
                    raise ValueError(
                        "oxDNA base vectors must be approximately perpendicular"
                    )
                positions.extend(
                    [
                        tuple(p + a for p, a in zip(center, axis)),
                        tuple(p + a for p, a in zip(center, normal)),
                        center,
                    ]
                )
            yield positions


def load(
    topology_file,
    trajectory,
    name="oxdna",
    start=1,
    stop=0,
    stride=1,
    memory_mb=512,
    _self=None,
):
    """Load classic or 5->3 oxDNA topology and text configurations into marker atoms.

    Coordinates are converted from oxDNA units to angstroms. Orientation markers
    are visualization data, not reconstructed chemical atoms. Frames are read
    incrementally; start/stop are inclusive, and stop=0 reads to end of file.
    """
    if _self is None:
        from pymol import cmd as _self
    from chempy import Atom, Bond, models

    start = integer(start, "start", 1, 1_000_000)
    stop = integer(stop, "stop", 0, 1_000_000)
    stride = integer(stride, "stride", 1, 1_000_000)
    budget = number(memory_mb, "memory_mb", 1, 65536) * 1024**2
    if stop and stop < start:
        raise ValueError("stop must be at or after start")
    if (
        not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name)
        or name.lower() in ("all", "none", "sele", "enabled", "visible")
        or name in _self.get_names("all")
    ):
        raise ValueError("name must be an unused identifier starting with a letter")
    rows = topology(topology_file, max_nucleotides=int(budget // (3 * 2048)))
    if len(rows) * 3 * 2048 > budget:
        raise ValueError("Estimated oxDNA loading memory exceeds memory_mb")
    model = models.Indexed()
    for index, (strand, base, previous, following) in enumerate(rows):
        for marker in ("A1", "A3", "CM"):
            atom = Atom()
            atom.name, atom.resn, atom.resi = marker, base, str(index + 1)
            atom.chain, atom.symbol, atom.hetatm = str(strand), "C", 1
            model.add_atom(atom)
        for neighbor in (previous, following):
            if neighbor > index:
                bond = Bond()
                bond.index, bond.order = [index * 3 + 2, neighbor * 3 + 2], 1
                model.add_bond(bond)
    staging = _self.get_unused_name("_bs_oxdna_input")
    loaded = 0
    try:
        frames = configurations(trajectory, len(rows))
        for frame, positions in enumerate(islice(frames, stop or None), 1):
            if frame < start or (frame - start) % stride:
                continue
            loaded += 1
            if len(model.atom) * (2048 + loaded * 12) > budget:
                raise ValueError(
                    "Estimated oxDNA trajectory memory exceeds memory_mb; use stride or stop"
                )
            for atom, position in zip(model.atom, positions):
                atom.coord = position
            _self.load_model(model, staging, state=loaded, zoom=0, quiet=1)
        if not loaded:
            raise ValueError("No configurations matched the requested frame range")
        _self.hide("everything", staging)
        _self.show("lines", f"{staging} and name CM")
        _self.set_name(staging, name)
    except Exception:
        _self.delete(staging)
        raise
    return {"object": name, "nucleotides": len(rows), "states": loaded}


def style(cmd, obj, options):
    from pymol.cgo import COLOR, CONE, CYLINDER, ELLIPSOID, SPHERE

    cgobj = cmd.get_unused_name("_bs_oxdna")
    try:
        colors = {}
        cmd.iterate(obj, "colors[index] = color", space={"colors": colors})
        for state in range(1, cmd.count_states(obj) + 1):
            model = cmd.get_model(obj, state=state)
            groups = {}
            for atom in model.atom:
                groups.setdefault((atom.segi, atom.chain, atom.resi), {})[atom.name] = (
                    atom
                )
            if not groups or any(
                set(atoms) != {"A1", "A3", "CM"} for atoms in groups.values()
            ):
                raise ValueError(
                    "oxdna-ribbon requires full orientation markers from blender_load_oxdna"
                )
            primitives = []
            backbones = {}
            for atoms in groups.values():
                center = atoms["CM"].coord
                axis = _unit(tuple(a - b for a, b in zip(atoms["A1"].coord, center)))
                normal = _unit(tuple(a - b for a, b in zip(atoms["A3"].coord, center)))
                lateral = _unit(_cross(normal, axis))
                backbone = tuple(p - 3.4 * a for p, a in zip(center, axis))
                base = tuple(p + 3.4 * a for p, a in zip(center, axis))
                color = cmd.get_color_tuple(colors[atoms["CM"].index])
                backbones[atoms["CM"].index] = (backbone, color)
                primitives.extend([COLOR, *color, SPHERE, *backbone, 2.0])
                primitives.extend(
                    [
                        CYLINDER,
                        *backbone,
                        *base,
                        options.params.get("bond_radius", 0.7),
                        *color,
                        *color,
                    ]
                )
                base_color = (
                    (0.0, 0.82, 0.87)
                    if options.color == "auto" and options.material != "clay"
                    else color
                )
                scale = options.params.get("sphere_scale", 1.0)
                primitives.extend(
                    [
                        COLOR,
                        *base_color,
                        ELLIPSOID,
                        *base,
                        scale * 3,
                        *axis,
                        *(v * 2 / 3 for v in lateral),
                        *(v / 3 for v in normal),
                    ]
                )
            for bond in model.bond:
                a, b = (model.atom[i].index for i in bond.index)
                if a not in backbones or b not in backbones:
                    continue
                p, first = backbones[a]
                q, second = backbones[b]
                radius = options.params.get("ribbon_radius", 0.8)
                primitives.extend(
                    [CONE, *p, *q, radius, radius * 0.3, *first, *second, 1.0, 1.0]
                )
            cmd.load_cgo(primitives, cgobj, state=state, zoom=0, quiet=1)
        cmd.set("cgo_transparency", options.transparency, cgobj)
        cmd.disable(cgobj)
        return [cgobj]
    except Exception:
        cmd.delete(cgobj)
        raise
