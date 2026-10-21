"""Pure-Python import, request validation, and adaptive quality checks."""

import os
import subprocess
import sys

import pytest

from blender_style_in_pymol import blender_style
from blender_style_in_pymol.options import read_params
from blender_style_in_pymol.presets import canonical, resolve_quality


def test_import_does_not_import_pymol():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import blender_style_in_pymol; assert 'pymol' not in sys.modules",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    assert result.returncode == 0, result.stderr


def test_list_without_pymol():
    assert "surface" in blender_style("list", quiet=1)["representations"]


def test_aliases_and_quality():
    assert canonical("ball_and_stick") == "ball-and-stick"
    assert canonical("spacefill") == "spheres"
    assert resolve_quality("auto", 500, 1) == "high"
    assert resolve_quality("auto", 25000, 1) == "medium"
    assert resolve_quality("auto", 500, 10) == "medium"
    assert resolve_quality("auto", 200000, 1) == "low"
    assert resolve_quality("high", 200000, 500) == "high"


def test_parameter_json(tmp_path):
    path = tmp_path / "params.json"
    path.write_text('{"loop_radius": 0.5}')
    assert read_params(path) == {"loop_radius": 0.5}
    path.write_text('{"bond_radius": -1}')
    with pytest.raises(ValueError):
        read_params(path)
