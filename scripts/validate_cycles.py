"""Verify real refraction, random-walk SSS and standard ray integration."""

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from runtime import Viewer

from blender_style_in_pymol import __init_plugin__, blender_style


def validate(output, samples=64):
    output.mkdir(parents=True, exist_ok=True)
    viewer = Viewer(gui=False)
    cmd = viewer.cmd
    __init_plugin__(_self=cmd)
    metadata = {}

    def style(material, **kwargs):
        return blender_style(
            material, samples=samples, quality="high", _self=cmd, quiet=1, **kwargs
        )

    def render(name, route="api"):
        path = output / f"{name}.png"
        before = (
            cmd.get_view(),
            cmd.get("ambient"),
            cmd.get_names("objects", enabled_only=1),
        )
        if route == "command":
            cmd.do("ray 400, 300")
            cmd.png(str(path), prior=1)
        elif route == "png":
            cmd.png(str(path), width=400, height=300, ray=1)
        elif route == "plugin":
            style("ray", filename=path, width=400, height=300)
        elif route == "async":
            cmd.ray(400, 300, async_=1)
            thread = cmd._pymol._blender_ray_thread
            thread.join(timeout=60)
            assert not thread.is_alive(), "Asynchronous Cycles rendering did not finish"
            cmd.png(str(path), prior=1)
        else:
            cmd.ray(400, 300)
            cmd.png(str(path), prior=1)
        assert before == (
            cmd.get_view(),
            cmd.get("ambient"),
            cmd.get_names("objects", enabled_only=1),
        )
        metadata[name] = dict(cmd._pymol._blender_last_cycles)
        pixels = np.asarray(Image.open(path).convert("RGBA"))
        assert pixels.shape == (300, 400, 4)
        return pixels

    try:
        cmd.set("orthoscopic", 1)
        cmd.set("opaque_background", 1)
        cmd.bg_color("white")
        cmd.viewport(400, 300)
        cmd.pseudoatom("lens", elem="C", pos=[0, 0, 1.5])
        for y in range(-3, 4):
            for x in range(-3, 4):
                cmd.pseudoatom(
                    "pattern",
                    elem="C",
                    pos=[x * 0.48, y * 0.48, -1.5],
                    color="blue" if (x + y) % 2 else "red",
                )
        style(
            "flat",
            selection="pattern",
            representation="spheres",
            name="pattern_view",
            color="keep",
            backend="mesh",
            params={"sphere_scale": 0.12},
        )
        style(
            "glass",
            selection="lens",
            representation="spheres",
            color="white",
            name="lens_view",
            params={"ior": 1, "roughness": 0},
        )
        cmd.zoom("lens or pattern", 0.8)
        straight = render("ior-1", "command")
        style(
            "glass",
            selection="lens",
            representation="spheres",
            color="white",
            name="lens_view",
            params={"ior": 1.5, "roughness": 0},
        )
        refracted = render("ior-1.5", "png")
        difference = (
            np.abs(straight[:, :, :3].astype(float) - refracted[:, :, :3]) / 255
        )
        refraction_delta = float(difference.mean())
        assert refraction_delta > 0.005, (
            "Changing IOR must bend the visible background pattern"
        )
        assert np.count_nonzero(difference.max(axis=2) > 0.15) > 500
        cmd.save(str(output / "glass.pse"))
        cmd.reinitialize()
        cmd.load(str(output / "glass.pse"))
        restored = render("glass-restored", "async")
        assert np.abs(restored.astype(float) - refracted).mean() < 1.0

        style("reset", name="all")
        cmd.delete("all")
        cmd.pseudoatom("sample", elem="C")
        cmd.set("orthoscopic", 1)
        cmd.set("opaque_background", 1)
        cmd.bg_color("white")
        style(
            "subsurface",
            representation="spheres",
            color="#e07352",
            renderer="cycles",
            params={"subsurface": 0},
        )
        cmd.zoom("sample", 1.1)
        diffuse = render("diffuse", "plugin")
        style(
            "subsurface",
            representation="spheres",
            color="#e07352",
            params={"subsurface_radius": 0.1},
        )
        shallow = render("sss-0.1")
        style(
            "subsurface",
            representation="spheres",
            color="#e07352",
            params={"subsurface_radius": 2.0},
        )
        deep = render("sss-2.0", "command")
        foreground = diffuse[:, :, :3].min(axis=2) < 230
        sss_delta = float(
            np.abs(deep[:, :, :3].astype(float) - diffuse[:, :, :3])[foreground].mean()
            / 255
        )
        radius_delta = float(
            np.abs(deep[:, :, :3].astype(float) - shallow[:, :, :3])[foreground].mean()
            / 255
        )
        assert sss_delta > 0.01 and radius_delta > 0.005
        assert metadata["sss-2.0"]["materials"][0]["subsurface"] == 1
        assert metadata["sss-2.0"]["materials"][0]["subsurface_radius"] == 2
        cmd.set("opaque_background", 0)
        transparent = render("sss-alpha")
        assert transparent[0, 0, 3] == 0
        assert transparent[:, :, 3].max() == 255
        style("flat", representation="spheres", renderer="cycles")
        cmd.turn("y", 25)
        cmd.move("x", 0.7)
        camera_iou = {}
        for orthoscopic in (0, 1):
            cmd.set("orthoscopic", orthoscopic)
            cycles = render(f"camera-{orthoscopic}")[:, :, 3] > 127
            path = output / f"camera-{orthoscopic}-pymol.png"
            style("ray", filename=path, width=400, height=300, renderer="pymol")
            native = np.asarray(Image.open(path).convert("RGBA"))[:, :, 3] > 127
            iou = float((cycles & native).sum() / (cycles | native).sum())
            assert iou > 0.985, "Cycles and PyMOL cameras must frame the same geometry"
            camera_iou[str(orthoscopic)] = iou
        report = {
            "refraction_rgb_delta": refraction_delta,
            "subsurface_rgb_delta": sss_delta,
            "radius_rgb_delta": radius_delta,
            "camera_iou": camera_iou,
            "renders": metadata,
        }
        (output / "validation.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        names = ("ior-1", "ior-1.5", "diffuse", "sss-2.0")
        overview = Image.new("RGB", (800, 640), "white")
        draw = ImageDraw.Draw(overview)
        for i, name in enumerate(names):
            x, y = (i % 2) * 400, (i // 2) * 320
            with Image.open(output / f"{name}.png") as img:
                overview.paste(img.convert("RGB"), (x, y))
            draw.text((x + 12, y + 304), name, fill="black")
        overview.save(output / "optics.png")
        print(json.dumps({k: v for k, v in report.items() if k != "renders"}, indent=2))
        return report
    finally:
        viewer.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".cache/cycles-validation"))
    parser.add_argument("--samples", type=int, default=64)
    args = parser.parse_args()
    validate(args.output, args.samples)
