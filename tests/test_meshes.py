"""Validate geometry, bounded allocation, persistence and material transactions."""

from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image

from blender_style_in_pymol import blender_style
from blender_style_in_pymol.mesh import cache, callback_names
from blender_style_in_pymol.surface import build


def apply(cmd, style="cartoon", **kwargs):
    return blender_style(style, _self=cmd, quiet=1, **kwargs)


def test_mesh_quality_and_material_cache(cmd):
    first = apply(cmd, quality="low")
    mesh = next(iter(cache(cmd).values()))[0]
    faces = len(mesh.faces)
    with patch(
        "blender_style_in_pymol.cartoon.cartoon",
        side_effect=AssertionError("rebuilt geometry"),
    ):
        second = apply(cmd, "glossy", quality="low")
    assert first["objects"] == second["objects"]
    assert next(iter(cache(cmd).values()))[0] is mesh
    third = apply(cmd, quality="high")
    assert third["objects"] != second["objects"]
    assert len(next(iter(cache(cmd).values()))[0].faces) > faces
    apply(cmd, "reset")
    assert not cache(cmd)
    assert not callback_names(cmd)


def test_mesh_session_and_camera_export(cmd, tmp_path):
    entry = apply(cmd, quality="low")
    path = tmp_path / "saved.pse"
    cmd.save(str(path))
    cmd.reinitialize()
    cmd.load(str(path))
    assert cache(cmd)
    assert all(obj in cmd.get_names("all") for obj in entry["objects"])
    cmd.orient("sample")
    ambient = cmd.get_setting_float("ambient")
    pixels = []
    for i in range(2):
        image = tmp_path / f"view-{i}.png"
        apply(cmd, "ray", filename=image, width=240, height=180)
        pixels.append(np.asarray(Image.open(image)))
        cmd.turn("y", 45)
    assert not np.array_equal(*pixels)
    assert cmd.get_setting_float("ambient") == pytest.approx(ambient)
    apply(cmd, "reset")
    assert cmd.get_names("all") == ["sample"]
    assert not cache(cmd)


def test_callback_failure_removes_staged_geometry(cmd):
    entry = apply(cmd, backend="native")
    names = cmd.get_names("all")
    with patch.object(
        cmd, "load_callback", side_effect=RuntimeError("injected callback failure")
    ):
        with pytest.raises(RuntimeError, match="callback failure"):
            apply(cmd, backend="mesh")
    assert cmd.get_names("all") == names
    assert all(obj in names for obj in entry["objects"])
    assert not cache(cmd)
    assert not callback_names(cmd)


def test_explicit_mesh_states_differ(cmd, tmp_path):
    cmd.create("sample", "sample", 1, 2)
    coords = cmd.get_coords("sample", state=2)
    coords[:, 0] += 4 * np.sin(coords[:, 2] * 0.15)
    cmd.load_coords(coords, "sample", state=2)
    entry = apply(cmd, backend="mesh", quality="low")
    assert entry["states"] == 2
    meshes = next(iter(cache(cmd).values()))
    assert len(meshes) == 2
    assert not np.array_equal(meshes[0].vertices, meshes[1].vertices)
    cmd.orient("sample")
    pixels = []
    for state in (1, 2):
        cmd.frame(state)
        image = tmp_path / f"frame-{state}.png"
        apply(cmd, "ray", filename=image, width=240, height=180)
        rgb = np.asarray(Image.open(image).convert("RGB"))
        assert np.count_nonzero(rgb.max(axis=2) > 30) > 100
        pixels.append(rgb)
    assert not np.array_equal(*pixels)


def test_atomic_radius_and_winding(cmd):
    cmd.delete("all")
    cmd.pseudoatom("sample", elem="C", pos=[2, 3, 4])
    apply(cmd, "spheres", backend="mesh", quality="low")
    mesh = next(iter(cache(cmd).values()))[0]
    np.testing.assert_allclose(
        np.linalg.norm(mesh.vertices - [2, 3, 4], axis=1), 1.7 * 0.8, atol=1e-6
    )
    triangles = mesh.vertices[mesh.faces]
    face_normals = np.cross(
        triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
    )
    assert np.all(
        np.sum(face_normals * (triangles.mean(axis=1) - [2, 3, 4]), axis=1) > 0
    )


def test_surface_grid_is_bounded_before_allocation():
    coords = np.array([[0.0, 0.0, 0.0], [1e4, 1e4, 1e4]])
    with pytest.raises(ValueError, match="grid exceeds"):
        build(coords, np.ones(2), coords, np.ones((2, 3)), "high", {}, 1024**2)


def test_surface_colors_and_normals(cmd):
    apply(cmd, "surface", color="chain", quality="low")
    mesh = next(iter(cache(cmd).values()))[0]
    assert np.isfinite(mesh.vertices).all()
    np.testing.assert_allclose(np.linalg.norm(mesh.normals, axis=1), 1, atol=1e-5)
    assert np.all((mesh.colors >= 0) & (mesh.colors <= 1))
    assert np.all((mesh.occlusion >= 0) & (mesh.occlusion <= 1))
    assert len(np.unique(mesh.colors.round(4), axis=0)) == 2


def test_trajectory_auto_uses_native(cmd):
    cmd.create("sample", "sample", 1, 2)
    entry = apply(cmd)
    assert entry["backend"] == "native"
    assert not cache(cmd)


def test_keep_lighting_uses_native_mesh_display(cmd):
    entry = apply(cmd, lighting="keep")
    assert entry["backend"] == "mesh"
    assert not callback_names(cmd)
    assert cmd.get_setting_int("cgo_lighting", entry["objects"][1]) == 1


def test_standard_ray_command_api_and_png_match(cmd, tmp_path):
    apply(cmd, material="glossy", quality="low")
    cmd.orient("sample")
    cmd.turn("y", 41)
    expected = tmp_path / "plugin.png"
    apply(cmd, "ray", filename=expected, width=240, height=180)
    baseline = np.asarray(Image.open(expected))
    ambient = cmd.get_setting_float("ambient")
    for method in ("command", "api", "png"):
        path = tmp_path / f"{method}.png"
        if method == "command":
            cmd.do("ray 240, 180")
            cmd.png(str(path), prior=1)
        elif method == "api":
            cmd.ray(240, 180)
            cmd.png(str(path), prior=1)
        else:
            cmd.png(str(path), width=240, height=180, ray=1)
        np.testing.assert_array_equal(np.asarray(Image.open(path)), baseline)
        assert cmd.get_setting_float("ambient") == pytest.approx(ambient)


def test_ray_transparency_accumulates_and_restores_settings(cmd, tmp_path):
    apply(cmd, material="transparent", quality="low")
    cmd.orient("sample")
    cmd.set("opaque_background", 0)
    mode = cmd.get_setting_int("transparency_mode")
    path = tmp_path / "transparent.png"
    cmd.png(str(path), width=240, height=180, ray=1)
    alpha = np.asarray(Image.open(path).convert("RGBA"))[:, :, 3]
    assert alpha.max() > 200
    assert np.count_nonzero(alpha == 0) > 100
    assert cmd.get_setting_int("transparency_mode") == mode


def test_ray_failure_restores_scene(cmd):
    from blender_style_in_pymol.ray import scene

    apply(cmd, quality="low")
    lighting = cmd.get_setting_float("ambient")
    enabled = cmd.get_names("objects", enabled_only=1)
    with pytest.raises(RuntimeError, match="render failure"):
        with scene(cmd, 240, 180):
            assert cmd.get_setting_float("ambient") == 1
            raise RuntimeError("render failure")
    assert cmd.get_setting_float("ambient") == pytest.approx(lighting)
    assert cmd.get_names("objects", enabled_only=1) == enabled
    assert not cmd._pymol._blender_ray_active


def test_asynchronous_ray_finishes_with_restored_scene(cmd, tmp_path):
    apply(cmd, quality="low")
    cmd.orient("sample")
    ambient = cmd.get_setting_float("ambient")
    cmd.ray(160, 120, async_=1)
    thread = cmd._pymol._blender_ray_thread
    thread.join(timeout=20)
    assert not thread.is_alive()
    assert cmd.get_setting_float("ambient") == pytest.approx(ambient)
    path = tmp_path / "async.png"
    cmd.png(str(path), prior=1)
    assert Image.open(path).size == (160, 120)


def test_nucleic_base_has_closed_outward_faces():
    from blender_style_in_pymol.nucleic import base

    mesh = base(np.array([1, 2, 3]), [0, 0, 1], [1, 0, 0], [0.2, 0.4, 0.8], 0.8)
    triangles = mesh.vertices[mesh.faces]
    face_normals = np.cross(
        triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
    )
    assert np.all(
        np.sum(face_normals * (triangles.mean(axis=1) - [1, 2, 6.5]), axis=1) > 0
    )
    np.testing.assert_allclose(mesh.vertices[:, 2].min(), 3)
    np.testing.assert_allclose(mesh.vertices[:, 2].max(), 10)
