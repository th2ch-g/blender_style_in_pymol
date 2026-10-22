"""Exercise real PyMOL selection, rollback, sessions, state and export behavior."""

from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image

from blender_style_in_pymol import __init_plugin__, blender_style
from blender_style_in_pymol.controller import manager_for
from blender_style_in_pymol.presets import MATERIALS, MOLECULAR_REPRESENTATIONS


def snapshot(cmd, selection="sample"):
    rows = []
    cmd.iterate(
        selection, "rows.append((rank, reps, color, vdw, ss, b))", space={"rows": rows}
    )
    return rows


def style(cmd, preset="studio", **kwargs):
    return blender_style(preset, quiet=1, _self=cmd, **kwargs)


@pytest.mark.parametrize(
    "representation",
    [rep for rep in MOLECULAR_REPRESENTATIONS if rep != "oxdna-ribbon"],
)
def test_all_geometry_preserves_source(cmd, representation):
    before = snapshot(cmd)
    coordinates = cmd.get_coords("sample").copy()
    entry = style(cmd, representation)
    assert cmd.count_atoms(entry["objects"][0]) == cmd.count_atoms("sample")
    assert all(row[1] == 0 for row in snapshot(cmd))
    assert [row[2:] for row in snapshot(cmd)] == [row[2:] for row in before]
    np.testing.assert_array_equal(cmd.get_coords("sample"), coordinates)
    style(cmd, "reset")
    assert snapshot(cmd) == before
    assert cmd.get_names("all") == ["sample"]


def test_overlap_partial_reset_and_sort(cmd):
    cmd.show("spheres", "sample and resi 1-3")
    before = snapshot(cmd)
    style(cmd, "spheres", selection="chain A", name="first_view")
    style(cmd, "sticks", selection="resi 8-18", name="second_view")
    cmd.sort("sample")
    style(cmd, "reset", name="first_view")
    assert all(row[1] == 0 for row in snapshot(cmd, "sample and resi 8-18"))
    assert any(row[1] != 0 for row in snapshot(cmd, "sample and resi 1-7"))
    style(cmd, "reset", name="second_view")
    assert snapshot(cmd) == before


@pytest.mark.parametrize(
    "kwargs",
    [
        {"style": "unknown"},
        {"representation": "unknown"},
        {"color": "not-a-color"},
        {"transparency": float("nan")},
        {"state": 1.5},
        {"state": -1},
        {"state": 99},
        {"selection": "none"},
        {"name": "sample"},
        {"params": {"unknown": 1}},
        {"params": {"loop_radius": float("inf")}},
    ],
)
def test_bad_requests_keep_existing_view(cmd, kwargs):
    entry = style(cmd)
    objects = cmd.get_names("all")
    before = snapshot(cmd)
    kwargs = dict(kwargs)
    requested = kwargs.pop("style", "studio")
    with pytest.raises((ValueError, RuntimeError)):
        style(cmd, requested, **kwargs)
    assert cmd.get_names("all") == objects
    assert snapshot(cmd) == before
    assert manager_for(cmd).entries["blender"] == entry


def test_preparation_failure_is_atomic(cmd):
    entry = style(cmd)
    names = cmd.get_names("all")
    with patch(
        "blender_style_in_pymol.geometry.prepare",
        side_effect=RuntimeError("injected failure"),
    ):
        with pytest.raises(RuntimeError, match="injected"):
            style(cmd, "spheres")
    assert manager_for(cmd).entries["blender"] == entry
    assert cmd.get_names("all") == names


@pytest.mark.parametrize("existing", [False, True])
def test_lighting_failure_rolls_back_commit(cmd, existing):
    if existing:
        style(cmd)
    before = snapshot(cmd)
    names = cmd.get_names("all")
    ambient = cmd.get_setting_float("ambient")
    manager = manager_for(cmd)
    with patch.object(manager, "_scene", side_effect=RuntimeError("scene failure")):
        with pytest.raises(RuntimeError, match="scene failure"):
            style(cmd, "spheres", selection="resi 5-15")
    assert snapshot(cmd) == before
    assert cmd.get_names("all") == names
    assert cmd.get_setting_float("ambient") == ambient


def test_material_failure_rolls_back_update(cmd):
    entry = style(cmd)
    before = snapshot(cmd)
    manager = manager_for(cmd)
    with patch.object(manager, "_scene", side_effect=RuntimeError("scene failure")):
        with pytest.raises(RuntimeError, match="scene failure"):
            style(cmd, "transparent")
    assert manager.entries["blender"] == entry
    assert snapshot(cmd) == before
    assert cmd.get_setting_float("cartoon_transparency", entry["objects"][0]) == 0


def test_object_transform_is_preserved(cmd):
    cmd.translate([8, 3, -2], object="sample", camera=0)
    cmd.rotate("z", 25, object="sample", camera=0)
    original = cmd.get_coords("sample").copy()
    entry = style(cmd, "spheres")
    np.testing.assert_allclose(cmd.get_coords(entry["objects"][0]), original, atol=1e-5)


def test_source_and_unrelated_object_settings_survive(cmd):
    cmd.fragment("ala", "other")
    cmd.set("sphere_scale", 0.53, "other")
    cmd.disable("other")
    before = snapshot(cmd, "other")
    style(cmd, "spheres", selection="sample")
    style(cmd, "reset")
    assert snapshot(cmd, "other") == before
    assert cmd.get_setting_float("sphere_scale", "other") == pytest.approx(0.53)
    assert "other" not in cmd.get_names("objects", enabled_only=1)


def test_new_objects_are_included_in_reapplication(cmd):
    initial = style(cmd)
    cmd.fragment("ala", "second")
    updated = style(cmd)
    assert updated["atoms"] > initial["atoms"]
    assert (
        sum(cmd.get_type(obj) == "object:molecule" for obj in updated["objects"]) == 2
    )


def test_empty_gui_export_has_clear_error(cmd, tmp_path):
    with pytest.raises(ValueError, match="GUI"):
        style(cmd, "png", filename=tmp_path / "image.png")


def test_material_updates_reuse_coordinates(cmd):
    entry = style(cmd)
    with patch.object(cmd, "create", side_effect=AssertionError("unnecessary copy")):
        updated = style(cmd, "glossy")
    assert updated["objects"] == entry["objects"]
    assert updated["options"]["material"] == "glossy"


@pytest.mark.parametrize(
    "representation,setting",
    [
        ("cartoon-rounded", "cartoon_fancy_helices"),
        ("cartoon-cylinders", "cartoon_cylindrical_helices"),
    ],
)
def test_quality_update_keeps_cartoon_shape(cmd, representation, setting):
    initial = style(cmd, representation, quality="low", backend="native")
    updated = style(cmd, representation, quality="high", backend="native")
    assert initial["objects"] == updated["objects"]
    assert cmd.get_setting_int(setting, updated["objects"][0]) == 1


def test_auto_clay_recolors(cmd):
    entry = style(cmd)
    before = snapshot(cmd, entry["objects"][0])
    updated = style(cmd, "clay")
    after = snapshot(cmd, updated["objects"][0])
    assert [x[2] for x in before] != [x[2] for x in after]


def test_scene_restore_preserves_user_edits(cmd):
    cmd.set("ambient", 0.12)
    cmd.set("shininess", 45)
    style(cmd)
    cmd.set("shininess", 99)
    style(cmd, "reset")
    assert cmd.get_setting_float("ambient") == pytest.approx(0.12)
    assert cmd.get_setting_float("shininess") == pytest.approx(99)


def test_lighting_keep_and_multiple_owners(cmd):
    ambient = cmd.get_setting_float("ambient")
    style(cmd, "matte", name="matte_view")
    style(cmd, "flat", name="flat_view", selection="chain B")
    assert cmd.get_setting_float("ambient") == 1
    style(cmd, "reset", name="flat_view")
    assert cmd.get_setting_float("ambient") == pytest.approx(0.55)
    style(cmd, "reset", name="matte_view")
    assert cmd.get_setting_float("ambient") == pytest.approx(ambient)
    style(cmd, lighting="keep")
    assert cmd.get_setting_float("ambient") == pytest.approx(ambient)


def test_all_states_current_and_refresh(cmd):
    original = cmd.get_coords("sample").copy()
    cmd.create("sample", "sample", 1, 2)
    cmd.load_coords(original + [0, 0, 2], "sample", state=2)
    entry = style(cmd)
    assert cmd.get_setting_int("defer_builds_mode") == 3
    assert cmd.count_states(entry["objects"][0]) == 2
    np.testing.assert_allclose(
        cmd.get_coords(entry["objects"][0], state=2), original + [0, 0, 2], atol=1e-5
    )
    cmd.load_coords(original + [0, 0, 4], "sample", state=2)
    refreshed = style(cmd, "refresh")[0]
    np.testing.assert_allclose(
        cmd.get_coords(refreshed["objects"][0], state=2),
        original + [0, 0, 4],
        atol=1e-5,
    )
    cmd.frame(2)
    current = style(cmd, state="current")
    assert current["states"] == 1
    assert cmd.get_setting_int("defer_builds_mode") == 0
    np.testing.assert_allclose(
        cmd.get_coords(current["objects"][0], state=1), original + [0, 0, 4], atol=1e-5
    )


def test_session_round_trip_and_reset(cmd, tmp_path):
    before = snapshot(cmd)
    style(cmd)
    session = tmp_path / "styles.pse"
    cmd.save(str(session))
    cmd.reinitialize()
    cmd.load(str(session))
    style(cmd, "reset")
    assert snapshot(cmd) == before
    assert cmd.get_names("all") == ["sample"]


def test_manual_delete_and_reinitialize(cmd):
    before = snapshot(cmd)
    entry = style(cmd)
    cmd.delete(entry["objects"][0])
    manager_for(cmd).maintenance()
    assert snapshot(cmd) == before
    cmd.set("ambient", 0.8)
    style(cmd)
    cmd.reinitialize()
    manager_for(cmd).maintenance()
    assert not manager_for(cmd).entries
    assert cmd.get_setting_float("ambient") == pytest.approx(0.14)


def test_memory_limit_before_copy(cmd):
    before = snapshot(cmd)
    with patch(
        "blender_style_in_pymol.controller.resolve_quality", return_value="high"
    ):
        with patch.object(cmd, "count_states", return_value=10000):
            with pytest.raises(ValueError, match="memory"):
                style(cmd, memory_mb=1)
    assert snapshot(cmd) == before
    assert cmd.get_names("all") == ["sample"]


def test_native_pick_maps_to_original(cmd):
    entry = style(cmd, selection="sample and resi 5-10")
    copy = entry["objects"][0]
    cmd.select("pk1", f"{copy} and index 1")
    assert style(cmd, "select", selection="pk1") == 1
    assert cmd.index("sele")[0][0] == "sample"
    selected = []
    cmd.iterate("sele", "selected.append(resi)", space={"selected": selected})
    assert selected == ["5"]


@pytest.mark.parametrize("material", MATERIALS)
def test_real_ray_output(cmd, tmp_path, material):
    cmd.bg_color("white")
    cmd.orient("sample")
    cmd.zoom("sample", 5)
    style(cmd, material, representation="spheres")
    path = tmp_path / f"{material}.png"
    style(cmd, "ray", filename=path, width=180, height=140)
    image = np.asarray(Image.open(path).convert("RGB"))
    assert image.shape == (140, 180, 3)
    assert np.count_nonzero(image.min(axis=2) < 230) > 50


def test_command_registration_and_native_ray(cmd, tmp_path):
    __init_plugin__(_self=cmd)
    cmd.do("blender_style spheres, selection=sample, quiet=1")
    assert "blender" in manager_for(cmd).entries
    path = tmp_path / "native.png"
    cmd.png(str(path), 180, 140, ray=1)
    assert path.is_file()
