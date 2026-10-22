"""Check real shader output, transparency, sessions and standard ray commands."""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image
from runtime import Viewer

from blender_style_in_pymol import blender_style


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".cache/gpu-validation"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    viewer = Viewer(gui=True)
    cmd = viewer.cmd
    try:
        cmd.fragment("trp", "sample")
        cmd.remove("hydro")
        cmd.orient("sample")
        cmd.bg_color("white")
        cmd.set("opaque_background", 0)
        entry = blender_style("ball-and-stick", backend="mesh", _self=cmd)

        def render(name):
            path = args.output / f"{name}.png"
            with viewer.context():
                blender_style("png", filename=path, width=320, height=240, _self=cmd)
            pixels = np.asarray(Image.open(path).convert("RGBA"))
            if np.count_nonzero(pixels[:, :, 3] > 128) < 100:
                raise AssertionError(f"Missing GPU geometry: {name}")
            if np.count_nonzero(pixels[:, :, 3] == 0) < 100:
                raise AssertionError(f"Missing transparent background: {name}")
            return pixels

        original = render("before-session")
        saved = args.output / "session.pse"
        cmd.save(str(saved))
        cmd.reinitialize()
        cmd.load(str(saved))
        restored = render("after-session")
        np.testing.assert_array_equal(original, restored)
        cmd.turn("y", 35)
        rotated = render("rotated")
        assert not np.array_equal(original, rotated)
        with viewer.context():
            cmd.do("ray 320, 240")
            cmd.png(str(args.output / "standard-ray.png"), prior=1)
            cmd.do(f"png {args.output / 'standard-png.png'}, 320, 240, ray=1")
        for name in ("standard-ray", "standard-png"):
            image = Image.open(args.output / f"{name}.png").convert("RGBA")
            pixels = np.asarray(image)
            assert image.size == (320, 240)
            assert np.count_nonzero(pixels[:, :, 3] > 128) > 100
        blender_style("transparent", representation="ball-and-stick", _self=cmd)
        transparent = render("transparent")
        assert transparent[:, :, 3].max() > 200
        assert cmd.get("bg_rgb") in ("white", "[ 1.000, 1.000, 1.000 ]")
        blender_style("reset", name="all", _self=cmd)
        assert not any(obj in cmd.get_names("all") for obj in entry["objects"])
        print("GPU shaders, alpha, session restore and standard ray commands passed")
    finally:
        viewer.close()


if __name__ == "__main__":
    main()
