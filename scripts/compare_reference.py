"""Compare a real Molecular Nodes render to the same PyMOL atoms and camera."""

import argparse
import json
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

from blender_style_in_pymol import blender_style


def linear(value):
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def prepare(args):
    import pymol2

    with pymol2.PyMOL() as instance:
        cmd = instance.cmd
        cmd.load(str(args.structure), "sample")
        cmd.remove("solvent or hydro")
        cmd.viewport(args.width, args.height)
        cmd.orient("sample")
        cmd.turn("y", 20)
        cmd.turn("z", -15)
        cmd.zoom("sample", 3)
        cmd.clip("slab", 200)
        cmd.bg_color("white")
        cmd.set("opaque_background", 0)
        cmd.set("orthoscopic", 1)
        entry = blender_style(
            args.style, color=args.color, quality="high", _self=cmd, quiet=1
        )
        obj = entry["objects"][0]
        atoms = []
        cmd.iterate(
            obj,
            "atoms.append(dict(name=name,chain=chain,resi=resi,ss=ss,color=color))",
            space={"atoms": atoms},
        )
        for atom in atoms:
            atom["rgba_linear"] = [
                linear(c) for c in cmd.get_color_tuple(atom.pop("color"))
            ] + [1]
        view = cmd.get_view()
        vertical_span = (
            -2
            * view[11]
            * math.tan(math.radians(cmd.get_setting_float("field_of_view")) / 2)
        )
        structure = args.output / "reference-input.cif"
        cmd.save(str(structure), "sample")
        data = {
            "structure": str(structure.resolve()),
            "view": view,
            "width": args.width,
            "height": args.height,
            "vertical_span": vertical_span,
            "atoms": atoms,
            "bonds": [
                [*bond.index, bond.order] for bond in cmd.get_model("sample").bond
            ],
        }
        (args.output / "input.json").write_text(json.dumps(data))
        blender_style(
            "ray",
            filename=args.output / f"pymol-{args.style}.png",
            width=args.width,
            height=args.height,
            _self=cmd,
        )


def metrics(args):
    images = []
    for prefix in ("reference", "pymol"):
        image = Image.open(args.output / f"{prefix}-{args.style}.png").convert("RGBA")
        images.append(np.asarray(image) / 255)
    a, b = images
    mask_a, mask_b = a[:, :, 3] > 0.5, b[:, :, 3] > 0.5
    union, intersection = mask_a | mask_b, mask_a & mask_b
    result = {
        "silhouette_iou": float(
            np.count_nonzero(intersection) / max(np.count_nonzero(union), 1)
        ),
        "overlap_rgb_mae": float(
            np.abs(a[:, :, :3] - b[:, :, :3])[intersection].mean()
        ),
        "reference_visible_pixels": int(mask_a.sum()),
        "pymol_visible_pixels": int(mask_b.sum()),
    }
    canvas = Image.new("RGB", (args.width * 2, args.height), "white")
    for i, pixels in enumerate(images):
        tile = Image.fromarray((pixels * 255).astype("uint8"), "RGBA")
        canvas.paste(tile, (i * args.width, 0), tile)
    canvas.save(args.output / f"comparison-{args.style}.png")
    (args.output / f"metrics-{args.style}.json").write_text(
        json.dumps(result, indent=2)
    )
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--structure", type=Path, required=True)
    parser.add_argument("--addon", type=Path, required=True)
    parser.add_argument("--blender", default=shutil.which("blender"))
    parser.add_argument("--output", type=Path, default=Path(".cache/reference"))
    parser.add_argument(
        "--style",
        choices=("cartoon", "ribbon", "spheres", "ball-and-stick", "sticks", "surface"),
        default="cartoon",
    )
    parser.add_argument("--color", default="secondary-structure")
    parser.add_argument("--width", type=int, default=800)
    parser.add_argument("--height", type=int, default=600)
    parser.add_argument("--samples", type=int, default=64)
    args = parser.parse_args()
    if not args.blender:
        parser.error("Provide --blender or add Blender to PATH")
    args.output.mkdir(parents=True, exist_ok=True)
    prepare(args)
    subprocess.run(
        [
            str(args.blender),
            "--background",
            "--factory-startup",
            "--python-exit-code",
            "1",
            "--python",
            str(Path(__file__).with_name("reference_blender.py")),
            "--",
            "--addon",
            str(args.addon),
            "--input",
            str(args.output / "input.json"),
            "--output",
            str(args.output),
            "--style",
            args.style,
            "--samples",
            str(args.samples),
        ],
        check=True,
    )
    metrics(args)


if __name__ == "__main__":
    main()
