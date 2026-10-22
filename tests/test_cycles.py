"""Test Cycles dispatch, portable scene exports and failure boundaries."""

import json
from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image

from blender_style_in_pymol import __init_plugin__, blender_style
from blender_style_in_pymol.cycles import export_scene, requested
from blender_style_in_pymol.mesh import cache


def glass(cmd, **kwargs):
    return blender_style(
        "glass",
        representation="spheres",
        selection="resi 1",
        quality="low",
        _self=cmd,
        quiet=1,
        **kwargs,
    )


def test_standard_ray_and_png_dispatch_cycles(cmd, tmp_path):
    __init_plugin__(_self=cmd)
    glass(cmd, samples=17)
    image = tmp_path / "mock.png"
    Image.new("RGB", (160, 120), "white").save(image)
    with patch(
        "blender_style_in_pymol.cycles.render",
        side_effect=lambda *a, **k: cmd.load_png(str(image)),
    ) as render:
        cmd.ray(320, 240)
        assert render.call_args.args == (cmd, 320, 240)
        cmd.do("ray 400, 300")
        assert tuple(map(int, render.call_args.args[1:])) == (400, 300)
        cmd.png(str(tmp_path / "preview.png"), width=160, height=120, ray=1)
        assert render.call_args.args == (cmd, 160, 120)


def test_disabled_glass_does_not_select_cycles(cmd):
    entry = glass(cmd)
    assert requested(cmd)
    cmd.disable(entry["options"]["name"])
    assert not requested(cmd)
    cmd.enable(entry["options"]["name"])
    assert requested(cmd)
    cmd.group("parent", entry["options"]["name"])
    cmd.disable("parent")
    assert not requested(cmd)
    cmd.enable("parent")
    assert not requested(cmd, "pymol")


def test_export_preserves_optics_transform_and_state(cmd, tmp_path):
    cmd.create("sample", "sample", 1, 2)
    cmd.translate([3, 0, 0], "sample", state=2, camera=0)
    entry = glass(cmd, params={"ior": 1.7, "subsurface": 0.4, "subsurface_radius": 2.5})
    cmd.frame(2)
    cmd.hide("everything", "sample")
    mesh_name = next(obj for obj in entry["objects"] if obj in cache(cmd))
    matrix = np.eye(4)
    matrix[0, 3] = 2
    cmd.set_object_ttt(mesh_name, matrix.ravel().tolist())
    before = cmd.get_view()
    data = export_scene(cmd, tmp_path, 320, 240, 23)
    assert data["samples"] == 23
    assert data["objects"][0]["optical"]["ior"] == 1.7
    assert data["objects"][0]["optical"]["subsurface_radius"] == 2.5
    assert data["objects"][0]["matrix"][3] == 2
    arrays = np.load(tmp_path / data["objects"][0]["file"])
    np.testing.assert_array_equal(arrays["vertices"], cache(cmd)[mesh_name][1].vertices)
    assert cmd.get_view() == before
    assert (
        json.loads((tmp_path / "scene.json").read_text())["objects"] == data["objects"]
    )


def test_cycles_rejects_partial_scene(cmd, tmp_path):
    glass(cmd)
    with pytest.raises(ValueError, match="visible native"):
        export_scene(cmd, tmp_path, 320, 240)


def test_missing_blender_does_not_mutate_scene(cmd):
    glass(cmd)
    before = cmd.get_names("objects"), cmd.get_view(), cmd.get("ambient")
    with patch("shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="BLENDER_EXECUTABLE"):
            cmd.ray(320, 240)
    assert (cmd.get_names("objects"), cmd.get_view(), cmd.get("ambient")) == before


@pytest.mark.parametrize("kwargs", [{"backend": "native"}, {"lighting": "keep"}])
def test_cycles_rejects_incompatible_modes_before_mutation(cmd, kwargs):
    before = cmd.get_names("all")
    with pytest.raises(ValueError, match="Cycles materials"):
        glass(cmd, **kwargs)
    assert cmd.get_names("all") == before


def test_cycles_scene_budget_precedes_writes(cmd, tmp_path):
    glass(cmd)
    cmd.hide("everything", "sample")
    with pytest.raises(ValueError, match="buffers exceed"):
        export_scene(cmd, tmp_path, 8192, 8192)
    assert list(tmp_path.iterdir()) == []


def test_optical_updates_reuse_geometry(cmd):
    first = glass(cmd)
    meshes = dict(cache(cmd))
    with patch(
        "blender_style_in_pymol.atomic.atomic",
        side_effect=AssertionError("rebuilt geometry"),
    ):
        second = glass(cmd, params={"ior": 1.7, "subsurface": 0.3})
    assert first["objects"] == second["objects"]
    assert all(cache(cmd)[name][0] is values[0] for name, values in meshes.items())
