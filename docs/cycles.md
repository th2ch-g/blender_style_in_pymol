# Refraction and subsurface scattering

`glass` and `subsurface` add real Cycles ray rendering to PyMOL. The interactive
viewport remains a fast preview: glass uses alpha blending and Fresnel
highlights, and SSS uses wrapped diffuse lighting. Light bending and volumetric
scattering are evaluated by Blender Cycles when rendering an image.

## Installation

Install [Blender](https://www.blender.org/download/) 4.0 or newer separately.
The plugin searches for `blender` on `PATH`, then installed macOS applications
through Spotlight. `BLENDER_EXECUTABLE` overrides discovery; set it to the
executable used by your Blender installation before starting PyMOL.

Blender runs in a separate background process with factory startup settings and
automatic script loading disabled. It does not load a user `.blend` file or
change preferences. Molecular Nodes and third-party Blender add-ons are not
required. The regular PyMOL renderer and viewport still work without Blender.

## Commands

```text
fetch 1crn, async=0
blender_style glass, representation=surface, color=chain
ray 1200, 900
png glass.png
blender_style subsurface, representation=surface, color=chain, samples=128
png subsurface.png, 1200, 900, ray=1
```

`ray`, `cmd.ray()`, `png ..., ray=1`, `cmd.png(..., ray=1)` and
`blender_style ray` all support Cycles. `renderer=auto` chooses Cycles when an
enabled view requests transmission or SSS, or explicitly selects Cycles.
Disabled views do not select the renderer. `samples` is stored with the view
and defaults to 64; higher values reduce Monte Carlo noise at greater cost.

```python
from blender_style_in_pymol import blender_style

blender_style(
    "glass", representation="surface", samples=128,
    params={"ior": 1.52, "roughness": 0.06, "transmission": 1.0},
)
cmd.ray(1200, 900)
cmd.png("glass.png")

blender_style(
    "subsurface", representation="surface", samples=128,
    params={"subsurface": 1.0, "subsurface_radius": 1.5},
)
cmd.png("subsurface.png", width=1200, height=900, ray=1)
```

For the PyMOL command language, place the parameter object in a local JSON file
and pass `params=material.json`. Optical parameter changes reuse prepared
geometry. Materials, renderer preferences and sample counts survive `.pse`
save/load. Blender must also be installed when rendering a restored scene.

| Parameter | Meaning | Default |
| --- | --- | --- |
| `ior` | Index of refraction, 1–4 | 1.45 |
| `roughness` | Principled surface roughness, 0–1 | 0.08 for glass, 0.45 for SSS |
| `transmission` | Principled transmission weight, 0–1 | 1 for glass, otherwise 0 |
| `subsurface` | Blend between diffuse and random-walk SSS, 0–1 | 1 for SSS, otherwise 0 |
| `subsurface_radius` | Red-channel scattering distance in scene angstroms | 1.0 |

The SSS radius ratio for red, green and blue is 1:0.2:0.1. Mesh coordinates and
scattering distances use the same conversion of 0.01 Blender units per
angstrom. These are artistic material controls, not measured molecular optical
properties. The shader follows Blender's [Principled BSDF](https://docs.blender.org/manual/en/4.0/render/shader_nodes/shader/principled.html)
transmission and subsurface components.

`transparency` remains a separate alpha blend with a transparent BSDF. Glass
defaults to `transparency=0`: its see-through appearance comes from physical
transmission. `transparent` keeps its original alpha-only meaning. Set
`opaque_background=0` for RGBA images; refracted backgrounds also support alpha.

## Explicit renderers and scene coverage

Use `renderer=cycles` on a view to path trace an ordinary material as well:

```text
blender_style studio, representation=surface, renderer=cycles, samples=64
ray 1200, 900
```

`blender_style ray, filename=figure.png, renderer=cycles` chooses Cycles for one
export. `renderer=pymol` explicitly requests the lightweight approximation. The
standard API also accepts `cmd.ray(renderer="cycles")` and
`cmd.ray(renderer="pymol")`; numeric PyMOL renderer arguments keep their meaning.

Cycles exports the current states of enabled managed meshes, including
multiple named views, vertex colors, object transforms, PyMOL camera rotation,
pan, orthographic/perspective projection and clipping distances. It uses the
plugin's three area lights, white environment illumination and the selected
background color. It does not export arbitrary PyMOL light settings, background
gradients, labels, distance objects, native cartoons/surfaces or external CGOs.
Visible unsupported geometry produces an error instead of an incomplete image.
Stereo and nonzero stereo shift are also rejected.

Use `lighting=auto` and `backend=auto` or `mesh` for Cycles materials. The auto
backend requires mesh generation for these materials and checks the memory
budget even for trajectories. Use `state=current` to render a large trajectory
without preparing all states. Cylindrical cartoons, preset 4, density and oxDNA
currently use native geometry and cannot enter the Cycles path. Presets with
native ligand overlays also need those overlays hidden or separately rebuilt
as mesh views. Closed, nonintersecting surfaces give the most predictable SSS
and transmission; separate chain surfaces can overlap.

Each render starts a CPU Cycles process, uses at most eight threads, a
deterministic seed, denoising, 16 total bounces and 12 transmission bounces.
Builds without OpenImageDenoise render without denoising; this is recorded in
the render metadata. Increase `samples` to reduce noise on those builds.
The process has a 600-second timeout. Temporary geometry, images and logs are
removed after completion. Allocation estimates cover exported arrays and image
buffers; Blender's own scene, acceleration structures and allocator overhead
are additional. The estimates are not a hard process memory limit.

## Reproducible validation

```sh
pixi run uv run --no-project --python .pixi/envs/default/bin/python python scripts/validate_cycles.py
```

The script renders an optical sphere in front of a colored pattern with IOR
1.0 and 1.5, and compares diffuse shading with SSS radii 0.1 and 2.0. It checks
nontrivial image differences, all four ray entry points, transparent PNG output
and a `.pse` round trip. Generated images, timing, material inputs and available
Blender peak RSS measurements are written to `.cache/cycles-validation/`.
The [published optical comparison](https://raw.githubusercontent.com/th2ch-g/blender_style_in_pymol/gallery/optics/optics.png)
is regenerated in CI.
