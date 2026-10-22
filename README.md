# blender_style_in_pymol

[![CI](https://github.com/th2ch-g/blender_style_in_pymol/actions/workflows/ci.yml/badge.svg)](https://github.com/th2ch-g/blender_style_in_pymol/actions/workflows/ci.yml)

Standalone `blender_style` command and Qt plugin for PyMOL. It provides
Molecular Nodes-inspired molecular representations, density contours, oxDNA
ribbons and soft studio materials using smooth meshes, an isolated OpenGL
shader and PyMOL's ray renderer. An optional Blender Cycles path adds real
refraction and random-walk subsurface scattering to standard `ray` commands.
Ordinary styles work without Blender. Cycles output requires Blender 4.0+;
Molecular Nodes is not a runtime dependency.

## Install

Use the locked environment in this repository:

```sh
pixi install --locked
pixi run pymol
```

Or install into an existing environment that already provides PyMOL 3.1:

```sh
uv pip install --python <pymol-python> "git+https://github.com/th2ch-g/blender_style_in_pymol.git"
```

Replace `<pymol-python>` with the Python interpreter used by PyMOL. Python
3.10+ is required. NumPy, SciPy, scikit-image, PyOpenGL and Pillow are installed
with the package. PyMOL itself is supplied by conda/pixi, not this package.
The dialog and interactive PNG export require a Qt/OpenGL session.
Headless PyMOL supports ray export.

Register the commands in PyMOL's Python console or `.pymolrc.py`:

```python
from blender_style_in_pymol import __init_plugin__

__init_plugin__()
```

This also adds **Plugin > Blender / Molecular Nodes Style** when the Qt menu
is available. `pixi run pymol` registers it automatically. Importing the package
alone does not import or start PyMOL or modify a scene.

## Gallery

All **16 representation choices and 10 materials** are rendered through PyMOL.
The previews below show ray output. The [full gallery](https://github.com/th2ch-g/blender_style_in_pymol/tree/gallery)
compares every case with interactive GPU output at 1200 × 900. `glass` and
`subsurface` use Cycles for ray output; their viewport images are approximations.
Protein examples use [crambin, PDB 1CRN](https://www.rcsb.org/structure/1CRN);
atomic examples use a tryptophan fragment. Density and oxDNA examples are synthetic.

![All representation choices rendered in PyMOL](https://raw.githubusercontent.com/th2ch-g/blender_style_in_pymol/gallery/representations.png)

![All material choices rendered in PyMOL](https://raw.githubusercontent.com/th2ch-g/blender_style_in_pymol/gallery/materials.png)

CI regenerates and publishes the dedicated `gallery` branch after tests pass.
Generated images and downloaded inputs are ignored in the source tree.
See [gallery generation](docs/gallery.md) for local reproduction and artifacts.

## Quick start

```text
fetch 1crn, async=0
blender_style cartoon
blender_style ribbon, color=chain
blender_style glossy, representation=ball-and-stick, selection=organic
blender_style transparent, representation=surface, transparency=0.5
ray 2400, 1800
png figure.png
blender_style reset, name=all
```

Use `name` to keep multiple views and `lighting=keep` to preserve the current
scene lighting. Named views support refresh, reset and ordinary `.pse` sessions.
Source molecular coordinates, colors, bonds and atom attributes remain intact.
`backend=auto` uses smooth meshes for supported static views that fit the
allocation estimate, and native PyMOL for trajectories and larger selections.
Use `backend=mesh` to request meshes explicitly or `backend=native` for native
atom picking and lower preparation cost. Standard `ray`, `cmd.ray()` and
`png ..., ray=1` refresh mesh shading for the current camera and state.

For refraction or subsurface scattering, install Blender and make `blender`
available on `PATH`, or set `BLENDER_EXECUTABLE` to its executable. Installed
macOS applications are also discovered through Spotlight.

```text
blender_style glass, representation=surface
ray 1200, 900
png glass.png
blender_style subsurface, representation=surface, samples=128
ray 1200, 900
png subsurface.png
```

These materials automatically choose mesh geometry and Cycles ray rendering.
The [Cycles guide](docs/cycles.md) covers optical parameters, supported scenes,
alpha output and the difference between viewport previews and path tracing.

## Representation coverage

Every molecular **Style** family in Molecular Nodes has a corresponding
representation. The density and oxDNA style families and the four legacy
4.5 presets are included too. This is representation-level coverage;
Blender's node graphs and every individual node socket are not reimplemented.

| Molecular Nodes family | `blender_style` choice |
| --- | --- |
| Style Cartoon | `cartoon`, `cartoon-rounded`, `cartoon-cylinders` |
| Style Ribbon | `ribbon` |
| Style Spheres | `spheres` |
| Style Ball and Stick | `ball-and-stick` |
| Style Sticks | `sticks` |
| Style Surface | `surface` |
| Style Preset 1–4 (legacy) | `preset-1`, `preset-2`, `preset-3`, `preset-4` |
| Density Style Surface | `density-surface` |
| Density Style Wire | `density-wire` |
| Density Style ISO Surface | `density-iso-surface` |
| oxDNA Style Ribbon | `oxdna-ribbon` |

Materials are `studio`, `ambient-occlusion`, `matte`, `glossy`, `clay`,
`flat`, `outline`, `transparent`, `glass` and `subsurface`. Color modes include secondary structure,
elements, chains, rainbow, original colors and custom colors.

```text
load density.ccp4, density
blender_style density-surface, selection=density
blender_load_oxdna duplex.top, trajectory.dat, name=dna, stride=5
blender_style oxdna-ribbon, selection=dna
```

Density uses native map objects. oxDNA loads classic or 5′→3′ topologies and
text configuration frames, retaining base orientation through compact CGO
primitives. See the [command guide](docs/pymol_blender.md) for parameters,
input requirements, picking and trajectory behavior.

## Fidelity and performance

Geometry and materials were compared with actual Molecular Nodes 4.5.9
renders across proteins, DNA and a molecular fragment. Example silhouette
intersection-over-union is 92.2–94.3% for protein cartoons, 97.7% for a DNA
cartoon, 96.7–97.9% for surfaces and 99.5% for a fragment's ball-and-stick view.
Eight materials were checked with shared colors and a matched camera. These
are calibration examples, not a guarantee for arbitrary structures. The
[fidelity report](docs/fidelity.md) describes the reference setup and differences.

The mesh backend uses relaxed chain-separated surfaces, oriented cartoon
profiles, rectangular nucleic bases, geometric occlusion and linear-light GGX
shading. It approximates the reference's roughness, soft area lights and
Fresnel outlines in the viewport and native ray output. Cycles export uses
the same meshes and colors with Principled BSDF transmission, random-walk SSS
and path-traced area lighting. It supports complete managed mesh scenes;
visible native representations or labels must be hidden or converted to meshes.
Native PyMOL ray output retains the existing behavior for mixed scenes.

Meshes are built once and held in indexed GPU buffers with a bounded cache.
Material changes reuse geometry. Native trajectory playback avoids building
Python meshes per frame; explicit mesh trajectories store all selected states.
Allocation estimates are checked before preparation. See
[benchmarks and memory behavior](docs/performance.md).

## Development

```sh
pixi run check
pixi run test
pixi run gallery --fetch
pixi run benchmark
```

Tests exercise real PyMOL lifecycle, source preservation, rollback, picking,
sessions, trajectories, density maps, oxDNA orientations and ray output.
CI checks Linux and macOS and renders paired GPU/ray images under Xvfb.
It also checks actual Cycles refraction, SSS and session round trips.

The command and documentation layout follow
[chimerax_style_in_pymol](https://github.com/th2ch-g/chimerax_style_in_pymol),
[molstar_style_in_pymol](https://github.com/th2ch-g/molstar_style_in_pymol) and
[cuemol_style_in_pymol](https://github.com/th2ch-g/cuemol_style_in_pymol).
This independent MIT-licensed implementation does not bundle Molecular Nodes
code, node assets, or materials. See [NOTICE](NOTICE) and [documentation](docs/README.md).
