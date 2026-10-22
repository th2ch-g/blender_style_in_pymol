"""Compare a real Molecular Nodes render to the same PyMOL atoms and camera."""

import argparse
import json
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image
from runtime import Viewer

from blender_style_in_pymol import blender_style
from blender_style_in_pymol.presets import MATERIALS


def linear(value):
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def prepare(args):
    viewer = Viewer(gui=args.gui)
    try:
        cmd = viewer.cmd
        cmd.load(str(args.structure), "sample")
        cmd.remove("solvent or hydro")
        candidates = {}
        cmd.iterate(
            "sample",
            "candidates.setdefault((segi, chain, resi, name), []).append((index, q, alt))",
            space={"candidates": candidates},
        )
        excluded = []
        for values in candidates.values():
            chosen = max(
                values,
                key=lambda value: (
                    not value[2],
                    value[1],
                    -ord(value[2][0]) if value[2] else 0,
                ),
            )[0]
            excluded.extend(value[0] for value in values if value[0] != chosen)
        if excluded:
            cmd.select_list("alternate_positions", "sample", excluded, mode="index")
            cmd.remove("alternate_positions")
            cmd.delete("alternate_positions")
        cmd.alter("sample", "alt=''")
        if cmd.count_atoms("sample and chain ''"):
            chains = set(cmd.get_chains("sample"))
            replacement = next(
                value for value in ("_", "X", "Z", "XX") if value not in chains
            )
            cmd.alter(
                "sample and chain ''",
                "chain=replacement",
                space={"replacement": replacement},
            )
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
            args.style,
            material=args.material,
            color=args.color,
            quality="high",
            backend=args.backend,
            _self=cmd,
            quiet=1,
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
            "material": args.material,
            "backend": entry["backend"],
            "transparency": entry["options"]["transparency"],
            "bonds": [
                [*bond.index, bond.order] for bond in cmd.get_model("sample").bond
            ],
        }
        (args.output / "input.json").write_text(json.dumps(data))
        for render in ("ray", "gpu") if args.gui else ("ray",):
            with viewer.context():
                blender_style(
                    "png" if render == "gpu" else "ray",
                    filename=args.output
                    / f"pymol{'-gpu' if render == 'gpu' else ''}-{args.style}.png",
                    width=args.width,
                    height=args.height,
                    _self=cmd,
                )
    finally:
        viewer.close()


def metrics(args, render="ray"):
    images = []
    for prefix in ("reference", "pymol-gpu" if render == "gpu" else "pymol"):
        image = Image.open(args.output / f"{prefix}-{args.style}.png").convert("RGBA")
        images.append(np.asarray(image) / 255)
    a, b = images
    threshold = 0.05 if getattr(args, "material", "studio") == "transparent" else 0.5
    mask_a, mask_b = a[:, :, 3] > threshold, b[:, :, 3] > threshold
    union, intersection = mask_a | mask_b, mask_a & mask_b
    result = {
        "silhouette_iou": float(
            np.count_nonzero(intersection) / max(np.count_nonzero(union), 1)
        ),
        "overlap_rgb_mae": float(np.abs(a[:, :, :3] - b[:, :, :3])[intersection].mean())
        if intersection.any()
        else None,
        "foreground_alpha_threshold": threshold,
        "alpha_mae": float(np.abs(a[:, :, 3] - b[:, :, 3])[union].mean())
        if union.any()
        else None,
        "reference_visible_pixels": int(mask_a.sum()),
        "pymol_visible_pixels": int(mask_b.sum()),
    }
    canvas = Image.new("RGB", (args.width * 2, args.height), "white")
    for i, pixels in enumerate(images):
        tile = Image.fromarray((pixels * 255).astype("uint8"), "RGBA")
        canvas.paste(tile, (i * args.width, 0), tile)
    suffix = "-gpu" if render == "gpu" else ""
    canvas.save(args.output / f"comparison{suffix}-{args.style}.png")
    (args.output / f"metrics{suffix}-{args.style}.json").write_text(
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
    parser.add_argument("--material", choices=MATERIALS, default="studio")
    parser.add_argument("--backend", choices=("auto", "mesh", "native"), default="auto")
    parser.add_argument("--gui", action="store_true")
    parser.add_argument(
        "--skip-blender",
        action="store_true",
        help="Reuse an existing reference render with the same input and camera",
    )
    parser.add_argument("--width", type=int, default=800)
    parser.add_argument("--height", type=int, default=600)
    parser.add_argument("--samples", type=int, default=64)
    args = parser.parse_args()
    if not args.blender and not args.skip_blender:
        parser.error("Provide --blender or add Blender to PATH")
    args.output.mkdir(parents=True, exist_ok=True)
    prepare(args)
    if not args.skip_blender:
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
                "--material",
                args.material,
                "--samples",
                str(args.samples),
            ],
            check=True,
        )
    metrics(args)
    if args.gui:
        metrics(args, "gpu")


if __name__ == "__main__":
    main()
