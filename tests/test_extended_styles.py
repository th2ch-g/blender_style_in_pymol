"""Validate map contours, legacy compositions and oriented oxDNA state output."""

from unittest.mock import patch

import numpy as np
import pytest
from chempy.brick import Brick
from PIL import Image

from blender_style_in_pymol import blender_load_oxdna, blender_style
from blender_style_in_pymol.controller import manager_for
from blender_style_in_pymol.presets import DENSITY_REPRESENTATIONS


def density(cmd):
    x, y, z = np.mgrid[-4:4:24j, -4:4:24j, -4:4:24j]
    field = (
        np.exp(-((x - 1.5) ** 2 + y * y + z * z))
        - np.exp(-((x + 1.5) ** 2 + y * y + z * z))
    ).astype(np.float32)
    cmd.load_brick(
        Brick.from_numpy(field, grid=(8 / 23,) * 3, origin=(-4,) * 3), "density"
    )
    return field


@pytest.mark.parametrize("representation", DENSITY_REPRESENTATIONS)
def test_map_render_reset_and_session(cmd, tmp_path, representation):
    field = density(cmd)
    cmd.disable("sample")
    entry = blender_style(
        representation, selection="density", params={"threshold": 0.2}, _self=cmd
    )
    assert all(
        cmd.get_type(obj) in ("object:surface", "object:mesh")
        for obj in entry["objects"]
    )
    assert len(entry["objects"]) == (
        2 if representation == "density-iso-surface" else 1
    )
    np.testing.assert_array_equal(cmd.get_volume_field("density"), field)
    cmd.orient("density")
    cmd.zoom("density", 1)
    cmd.bg_color("white")
    image = tmp_path / "map.png"
    blender_style("ray", filename=image, width=180, height=140, _self=cmd)
    pixels = np.asarray(Image.open(image).convert("RGB"))
    assert np.count_nonzero(pixels.min(axis=2) < 230) > 100
    session = tmp_path / "density.pse"
    cmd.save(str(session))
    cmd.reinitialize()
    cmd.load(str(session))
    blender_style("reset", _self=cmd)
    assert set(cmd.get_names("all")) == {"sample", "density"}
    np.testing.assert_array_equal(cmd.get_volume_field("density"), field)


def test_density_failure_and_molecular_replacement(cmd):
    density(cmd)
    first = blender_style("cartoon", selection="sample", _self=cmd)
    with patch.object(cmd, "isosurface", side_effect=RuntimeError("injected")):
        with pytest.raises(RuntimeError, match="injected"):
            blender_style("density-surface", selection="density", _self=cmd)
    assert manager_for(cmd).entries["blender"] == first
    with pytest.raises(ValueError, match="memory"):
        blender_style("density-surface", memory_mb=1, _self=cmd)
    blender_style("density-surface", _self=cmd)
    masks = []
    cmd.iterate("sample", "masks.append(reps)", space={"masks": masks})
    assert all(masks)
    blender_style("cartoon", selection="sample", _self=cmd)
    assert manager_for(cmd).entries["blender"]["atoms"] == cmd.count_atoms("sample")


def test_multistate_density_and_contours(cmd):
    field = density(cmd)
    cmd.load_brick(
        Brick.from_numpy(
            np.roll(field, 3, axis=0), grid=(8 / 23,) * 3, origin=(-4,) * 3
        ),
        "density",
        state=2,
    )
    entry = blender_style(
        "density-iso-surface",
        selection="density",
        params={"threshold": 0.2, "contours": 1},
        _self=cmd,
    )
    assert len(entry["objects"]) == 4
    assert entry["states"] == 2
    assert all(cmd.count_states(obj) == 2 for obj in entry["objects"])
    assert cmd.get_setting_int("defer_builds_mode") == 3
    blender_style("reset", _self=cmd)
    assert cmd.get_setting_int("defer_builds_mode") == 0


def test_preset_compositions(cmd):
    cmd.pseudoatom("ligand", name="C1", elem="C", resn="LIG", pos=[0, 0, 0])
    cmd.pseudoatom("ligand", name="O1", elem="O", resn="LIG", pos=[1.3, 0, 0])
    cmd.bond("ligand and name C1", "ligand and name O1")
    for preset in ("preset-1", "preset-2", "preset-3", "preset-4"):
        entry = blender_style(preset, _self=cmd)
        assert (
            sum(cmd.get_type(obj) == "object:molecule" for obj in entry["objects"]) == 2
        )
        ligand = next(
            row["object"] for row in entry["mapping"] if row["source"] == "ligand"
        )
        reps = []
        cmd.iterate(ligand, "values.append(reps)", space={"values": reps})
        assert all(value & 2 for value in reps)


def oxdna_files(tmp_path, new):
    top = tmp_path / "dna.top"
    top.write_text(
        "4 1 5->3\nACGT\n" if new else "4 1\n1 A -1 1\n1 C 0 2\n1 G 1 3\n1 T 2 -1\n"
    )
    trajectory = tmp_path / "dna.dat"
    trajectory.write_text(
        "".join(
            f"t = {state}\nb = 10 10 10\nE = 0 0 0\n"
            + "".join(f"{i * 0.4} 0 0 {axis} 0 0 1 0 0 0 0 0 0\n" for i in range(4))
            for state, axis in ((0, "0 1 0"), (1, "1 0 0"))
        )
    )
    return top, trajectory


@pytest.mark.parametrize("new", [False, True])
def test_oxdna_orientations_states_session(cmd, tmp_path, new):
    top, trajectory = oxdna_files(tmp_path, new)
    result = blender_load_oxdna(top, trajectory, _self=cmd)
    assert result["nucleotides"] == 4
    assert result["states"] == 2
    assert cmd.count_atoms("oxdna") == 12
    centers = cmd.get_coords("oxdna and name CM", state=1)
    assert centers[1, 0] == pytest.approx(0.4 * 8.518)
    quality_before = [
        cmd.get_setting_int(key)
        for key in ("cgo_sphere_quality", "cgo_ellipsoid_quality")
    ]
    entry = blender_style("oxdna-ribbon", selection="oxdna", _self=cmd)
    assert len(entry["objects"]) == 2
    cgo = entry["objects"][1]
    assert cmd.get_type(cgo) == "object:cgo"
    assert cmd.count_states(cgo) == 2
    cmd.disable("sample")
    cmd.orient("oxdna")
    cmd.zoom("oxdna", 8)
    cmd.bg_color("white")
    pixels = []
    for state in (1, 2):
        cmd.frame(state)
        filename = tmp_path / f"state-{state}.png"
        blender_style("ray", filename=filename, width=180, height=140, _self=cmd)
        pixels.append(np.asarray(Image.open(filename).convert("RGB")))
        assert np.count_nonzero(pixels[-1].min(axis=2) < 230) > 100
    assert not np.array_equal(*pixels)
    session = tmp_path / "oxdna.pse"
    cmd.save(str(session))
    cmd.reinitialize()
    cmd.load(str(session))
    blender_style("reset", _self=cmd)
    assert set(cmd.get_names("all")) == {"sample", "oxdna"}
    assert [
        cmd.get_setting_int(key)
        for key in ("cgo_sphere_quality", "cgo_ellipsoid_quality")
    ] == quality_before


def test_invalid_oxdna_is_atomic(cmd, tmp_path):
    top, trajectory = oxdna_files(tmp_path, True)
    trajectory.write_text(trajectory.read_text() + "t = 3\nb = 1 1 1\nE = 0 0 0\n")
    with pytest.raises(ValueError, match="finite"):
        blender_load_oxdna(top, trajectory, _self=cmd)
    assert cmd.get_names("all") == ["sample"]
    result = blender_load_oxdna(top, trajectory, stop=1, _self=cmd)
    assert result["states"] == 1
    cmd.delete("oxdna")
    with pytest.raises(ValueError, match="orientation markers"):
        blender_style("oxdna-ribbon", _self=cmd)
    assert cmd.get_names("all") == ["sample"]


def test_oxdna_ray_retains_ellipsoid_extent(cmd, tmp_path):
    top, trajectory = tmp_path / "one.top", tmp_path / "one.dat"
    top.write_text("1 1\n1 A -1 -1\n")
    trajectory.write_text("t = 0\nb = 10 10 10\nE = 0 0 0\n0 0 0 1 0 0 0 0 1\n")
    blender_load_oxdna(top, trajectory, _self=cmd)
    blender_style("oxdna-ribbon", selection="oxdna", _self=cmd)
    cmd.disable("sample")
    cmd.bg_color("white")
    cmd.set("orthoscopic", 1)
    cmd.set_view((1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, -40, 0, 0, 0, 10, 70, -20))
    path = tmp_path / "base.png"
    blender_style("ray", filename=path, width=320, height=240, _self=cmd)
    pixels = np.asarray(Image.open(path).convert("RGB"))
    y, x = np.where((pixels[:, :, 0] < 30) & (pixels[:, :, 1] > 90))
    assert len(x) > 100
    assert np.ptp(x) / np.ptp(y) > 1.3
