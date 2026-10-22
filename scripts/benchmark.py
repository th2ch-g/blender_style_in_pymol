"""Measure native styling, material updates, RSS and optional synchronized GUI frames."""

import argparse
import json
import math
import platform
from pathlib import Path
from statistics import median
from time import perf_counter

import numpy as np
import psutil
from PIL import Image
from runtime import Viewer

from blender_style_in_pymol import blender_style


def synthetic(residues):
    from chempy import Atom, Bond, models

    model = models.Indexed()
    for i in range(residues):
        block, local = divmod(i, 20)
        angle = local * 1.7453
        center = (
            block % 10 * 15 + 2.3 * math.cos(angle),
            block // 10 * 15 + 2.3 * math.sin(angle),
            local * 1.5,
        )
        for name, element, offset in (
            ("N", "N", (-0.7, 0, -0.4)),
            ("CA", "C", (0, 0, 0)),
            ("C", "C", (0.7, 0, 0.4)),
            ("O", "O", (0.9, 0.8, 0.5)),
        ):
            atom = Atom()
            atom.name, atom.symbol, atom.resn, atom.resi = (
                name,
                element,
                "ALA",
                str(local + 1),
            )
            atom.chain, atom.ss = f"C{block}", "H" if local < 12 else "L"
            atom.coord = [a + b for a, b in zip(center, offset)]
            model.add_atom(atom)
        base = 4 * i
        edges = [(base, base + 1), (base + 1, base + 2), (base + 2, base + 3)]
        if local:
            edges.append((base - 2, base))
        for a, b in edges:
            bond = Bond()
            bond.index, bond.order = [a, b], 1
            model.add_bond(bond)
    return model


def timing_frames(viewer, frames, states=False):
    if not viewer.gui:
        return None
    viewer.pump()
    viewer.draw()
    durations = []
    for index in range(frames):
        start = perf_counter()
        if states:
            viewer.cmd.frame(index % viewer.cmd.count_states("sample") + 1)
        else:
            viewer.cmd.turn("y", 1)
        viewer.draw()
        durations.append(perf_counter() - start)
    return {
        "frames": frames,
        "median_ms": median(durations) * 1000,
        "p95_ms": float(np.percentile(durations, 95) * 1000),
        "fps": len(durations) / sum(durations),
    }


def verify_playback(viewer, states, output):
    if not viewer.gui:
        return None
    output.mkdir(parents=True, exist_ok=True)
    pixels = []
    counts = {}
    for state in sorted({1, min(2, states), states}):
        viewer.cmd.frame(state)
        path = output / f"state-{state}.png"
        with viewer.context():
            blender_style("png", filename=path, width=500, height=400, _self=viewer.cmd)
        rgb = np.asarray(Image.open(path).convert("RGB"))
        count = int(np.count_nonzero(rgb.max(axis=2) > 30))
        if count < 100:
            raise RuntimeError(f"Playback frame {state} is empty")
        pixels.append(rgb)
        counts[state] = count
    if states > 1 and all(np.array_equal(pixels[0], frame) for frame in pixels[1:]):
        raise RuntimeError("Playback frames did not change")
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--residues", type=int, default=2000)
    parser.add_argument("--states", type=int, default=20)
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument("--gui", action="store_true")
    parser.add_argument("--representation", default="cartoon")
    parser.add_argument("--backend", choices=("auto", "native", "mesh"), default="auto")
    parser.add_argument(
        "--quality", choices=("auto", "low", "medium", "high"), default="auto"
    )
    parser.add_argument("--output", type=Path, default=Path(".cache/benchmark.json"))
    args = parser.parse_args()
    if min(args.residues, args.states, args.frames) < 1:
        parser.error("Counts must be positive")
    viewer = Viewer(gui=args.gui, width=1000, height=800)
    cmd = viewer.cmd
    process = psutil.Process()
    try:
        if args.states > 1:
            cmd.set("defer_builds_mode", 3)
        cmd.load_model(synthetic(args.residues), "sample")
        coordinates = cmd.get_coords("sample")
        for state in range(2, args.states + 1):
            cmd.create("sample", "sample", 1, state)
            positions = coordinates.copy()
            positions[:, 0] += np.sin(coordinates[:, 2] * 0.1 + state * 0.2) * 0.4
            cmd.load_coords(positions, "sample", state=state)
        cmd.hide("everything")
        cmd.show("cartoon", "sample")
        cmd.orient("sample")
        cmd.zoom("sample", 5)
        viewer.pump()
        baseline_frames = timing_frames(viewer, args.frames)
        baseline_playback = timing_frames(
            viewer, max(args.frames, args.states), states=True
        )
        baseline_rss = process.memory_info().rss
        start = perf_counter()
        entry = blender_style(
            args.representation,
            backend=args.backend,
            quality=args.quality,
            _self=cmd,
            quiet=1,
        )
        apply_seconds = perf_counter() - start
        preparation_rss = process.memory_info().rss
        rotation = timing_frames(viewer, args.frames)
        playback = timing_frames(viewer, max(args.frames, args.states), states=True)
        rendered_rss = process.memory_info().rss
        updates = []
        for i in range(10):
            start = perf_counter()
            blender_style(
                "matte" if i % 2 else "studio",
                representation=args.representation,
                backend=args.backend,
                quality=args.quality,
                _self=cmd,
                quiet=1,
            )
            updates.append(perf_counter() - start)
        updated_rss = process.memory_info().rss
        timing_frames(viewer, max(args.frames, args.states), states=True)
        steady_rss = process.memory_info().rss
        playback_images = verify_playback(
            viewer, args.states, args.output.with_suffix("")
        )
        validation_rss = process.memory_info().rss
        blender_style("reset", name="all", _self=cmd)
        reset_rss = process.memory_info().rss
        report = {
            "platform": platform.system(),
            "architecture": platform.machine(),
            "pymol": cmd.get_version()[0],
            "renderer": cmd.get_renderer() if args.gui else None,
            "viewport": cmd.get_viewport() if args.gui else None,
            "atoms": len(coordinates),
            "states": args.states,
            "representation": args.representation,
            "quality": entry["quality"],
            "backend": entry["backend"],
            "apply_seconds": apply_seconds,
            "material_update_median_ms": median(updates) * 1000,
            "coordinate_mib": entry["coordinate_bytes"] / 1024**2,
            "estimated_mib": entry["estimated_bytes"] / 1024**2,
            "rss_mib": {
                "baseline": baseline_rss / 1024**2,
                "prepared": preparation_rss / 1024**2,
                "rendered": rendered_rss / 1024**2,
                "after_10_updates": updated_rss / 1024**2,
                "after_second_playback": steady_rss / 1024**2,
                "after_validation_images": validation_rss / 1024**2,
                "after_reset": reset_rss / 1024**2,
            },
            "baseline_rotation": baseline_frames,
            "baseline_playback": baseline_playback,
            "baseline_policy": "Native cartoon, with defer_builds_mode=3 for multiple states",
            "styled_rotation": rotation,
            "styled_playback": playback,
            "playback_visible_pixels": playback_images,
            "notes": "Synthetic motion, not an MD trajectory. GUI frames include glFinish. RSS includes PyMOL/Qt/driver allocation; reset need not return allocator pages to the OS.",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
    finally:
        viewer.close()


if __name__ == "__main__":
    main()
