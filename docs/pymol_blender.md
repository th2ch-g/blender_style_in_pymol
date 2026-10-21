# Blender style command guide

`blender_style` is an independent Python plugin for PyMOL 3.1. It uses native
molecular objects, shaders and ray primitives. Blender and Molecular Nodes are
needed only for the optional reference comparison, not for normal use.

## Registration

After installing the package into the Python interpreter used by PyMOL:

```python
from blender_style_in_pymol import __init_plugin__

__init_plugin__()
```

This registers the command, tab completion and the **Plugin > Blender /
Molecular Nodes Style** dialog when the Qt plugin menu is available. Importing
the package alone does not import PyMOL or change a scene. `pixi run pymol`
registers the plugin at startup. `blender_style gui` also opens the dialog.

## Basic use

```text
blender_style
blender_style cartoon, selection=chain A, color=secondary-structure
blender_style studio, representation=surface, color=chain
blender_style ball-and-stick, selection=organic, name=ligand
blender_style transparent, representation=surface, transparency=0.5
blender_style list
blender_style help
```

The first argument can name either a representation or a material. The default
is `studio` on `cartoon`. `representation` and `material` explicitly override
these defaults. Underscores and hyphens are interchangeable; `ballstick`,
`spacefill`, `tube` and `ao` are aliases.

| Representation | Geometry |
| --- | --- |
| `cartoon` | Spiral rectangular helices, sheet arrows and smooth backbone curves |
| `cartoon-rounded` | Rounded native helix and sheet profiles |
| `cartoon-cylinders` | Native cylindrical helices, sheet arrows and loops |
| `ribbon` | Thick circular backbone tube, matching the Molecular Nodes ribbon family |
| `spheres` | Van der Waals radii scaled by 0.8 |
| `ball-and-stick` | Spheres scaled by 0.3 and bonds with a 0.3 Å radius |
| `sticks` | Bonds with a 0.2 Å radius |
| `surface` | Native solvent-excluded surface with scaled radii and surface occlusion |
| `preset-1` | Polymer tubes plus non-polymer balls and sticks |
| `preset-2` | Polymer cartoons, nearby peptide side chains and non-polymer balls and sticks |
| `preset-3` | Protein surface plus spheres for other atoms |
| `preset-4` | B-factor-scaled protein tubes plus spheres for other atoms |
| `density-surface` | One contour surface of a loaded volumetric map |
| `density-wire` | Native map contour mesh |
| `density-iso-surface` | Positive and negative contour surfaces, with optional wire contours |
| `oxdna-ribbon` | Oriented base ellipsoids, stems and a directional backbone |

Cartoon/ribbon views also show non-solvent ligands as sticks and isolated
non-polymer atoms as spheres. A molecule with fewer than two backbone anchors
falls back to sticks. Nucleic acids use native PyMOL backbones, rings and rungs;
these differ from Molecular Nodes rectangular base slabs.

## Materials and lighting

| Material | Appearance |
| --- | --- |
| `studio` | Broad, low-strength highlights with soft fill lighting |
| `ambient-occlusion` | Stronger native surface occlusion and subdued directional lighting |
| `matte` | Diffuse finish without specular highlights |
| `glossy` | Stronger, sharper highlights |
| `clay` | Matte finish and a warm clay color with `color=auto` |
| `flat` | Unlit color |
| `outline` | Flat color with ray-traced outlines |
| `transparent` | Alpha transparency, defaulting to 0.5 |

`transparency` accepts 0 (opaque) through 1 (invisible). These are PyMOL
material approximations. Surface occlusion works in the viewport and ray
output. Cartoon and atomic views use soft fill lights without geometric
ambient occlusion. Outlines appear in ray output; the viewport shows flat
color. There is no refraction, subsurface scattering, HDR environment lighting,
or Cycles/EEVEE shader execution.

PyMOL lighting is global. The last applied view with `lighting=auto` controls
scene lighting, including unrelated visible objects. `lighting=keep` leaves
lighting unchanged; an explicit material name selects its lighting profile.
Per-object transparency, surface occlusion and geometry remain independent.
The background and camera are preserved. Use native `bg_color`, `orient`
and `zoom` commands to change them.

## Colors

`auto` uses the Molecular Nodes 4.5 secondary-structure palette for cartoons
and ribbons: green helices, red sheets and blue loops. Atomic views use its
Common element palette. Auto-colored protein surfaces inherit the carbon
color, corresponding to the reference's alpha-carbon color source.

- `keep` preserves source atom colors in the copies.
- `element` colors individual atoms, including atoms contributing to surfaces.
- `chain` uses a small, deterministic pastel palette.
- `secondary-structure` uses existing PyMOL `ss` assignments.
- `rainbow` follows residue order.
- A PyMOL color name or `#rrggbb` applies a uniform color.

The plugin does not assign secondary structure or infer new bonds. Load
annotations with the structure or run PyMOL's `dss` before applying the style
if assignments are needed. Van der Waals radii in the copies follow the
reference conventions for common elements; other elements retain source
radii. Source radii remain unchanged.

## Density maps

Load a PyMOL-supported map, such as CCP4/MRC, DX or CUBE, before applying a
density style. Here `selection` is an exact map name, a shell-style name
pattern, or `all`; it is not an atom selection. Molecular objects stay visible.

```text
load map.ccp4, density
blender_style density-surface, selection=density, name=map_view
blender_style density-wire, selection=density, name=wire_view, lighting=keep
```

```python
blender_style("density-iso-surface", selection="density",
              params={"threshold": 0.4, "contours": 1, "wire_radius": 0.06})
```

`threshold` defaults to 0.8 in the map's stored value units. Signed ISO
surfaces use both positive and negative values of this threshold and require
a positive threshold. `contours=1` adds mesh lines; `only_contours=1` omits the
solid surfaces. `wire_radius` sets the ray cylinder radius in angstroms;
interactive mesh width is 1.2 pixels. Auto colors are green for ordinary
density, blue/red for positive/negative ISO surfaces, and dark for contour
lines. A uniform color or `keep` is also accepted.

Map grids are read without an additional voxel copy. Native contour objects
support all/current/specific map states and normal session saving. The memory
estimate includes all generated state contours. PyMOL's grid contours differ
from Blender's mesh-edge wires; dust removal, volume slicing and arbitrary
node fields are not implemented.

## oxDNA

```text
blender_load_oxdna duplex.top, trajectory.dat, name=dna, start=1, stop=100, stride=5
blender_style oxdna-ribbon, selection=dna
```

The loader accepts classic 3′→5′ and newer 5′→3′ topology files, circular
strands, canonical and integer base types, and plain-text configurations
with 9 or 15 values per nucleotide. `start` and `stop` are inclusive frame
numbers; `stop=0` reads to EOF. Frames are streamed, and `memory_mb` bounds an
allocation estimate before each retained frame is loaded. Existing objects
are never overwritten by the loader. Invalid input removes the staged object.

One oxDNA length unit becomes 8.518 Å. Each nucleotide is stored as three
orientation markers (`CM`, `A1`, `A3`), which preserve the center, base axis
and base normal through trajectories and `.pse` sessions. These are
visualization markers, not reconstructed chemical atoms. Do not interpret
them as an all-atom molecular model. Input coordinates are not unwrapped
across periodic boundaries; unwrap them before loading when necessary.

The representation creates compact native CGO ellipsoids, cylinders, spheres
and tapered backbone segments for each state. Playback does not run Python
geometry construction. `ribbon_radius`, `bond_radius` and `sphere_scale`
control backbone, stems and bases. Auto colors distinguish strands and use
cyan bases. The shape is a physical-unit approximation of the oxDNA style;
it does not execute the upstream Geometry Nodes graph.

Select complete nucleotide markers, such as `byres (dna and resi 1-10)`.
CGO surfaces do not provide atom picking; the underlying marker copy can be
shown with native PyMOL spheres for picking and mapped with `blender_style
select`. oxDNA material or quality changes rebuild its CGO view. Its memory
estimate includes stored primitives for all selected states.
The global CGO sphere/ellipsoid quality follows the last oxDNA view and is
restored when that view is reset.

## Named views, picking and restoration

```text
blender_style cartoon, selection=polymer, name=backbone
blender_style ball-and-stick, selection=organic, name=ligand, lighting=keep
blender_style select, selection=pk1
blender_style reset, name=ligand
blender_style reset, name=all
```

Each named view is a group of native molecular copies. Selected source atoms
are hidden while any managed view uses them. Unselected source atoms keep
their original representations. Coordinates, atom attributes, bonds and colors
of the originals are preserved. Overlapping views can be removed independently.
`reset` restores source representations and removes the managed objects.

Native atom picking works on the molecular copies. After picking an atom,
`blender_style select, selection=pk1` puts the corresponding source atom into
`sele`. The mapping uses atom ranks, so sorting the source does not invalidate
it. Delete/recreate operations that replace atom identity require a refresh.

Reusing a name replaces its view after successful preparation. Invalid
parameters, failed preparation and failed lighting updates retain the previous
view. Material-only updates reuse coordinates and existing molecular objects
for the atomic, protein and legacy preset styles. Density and oxDNA views
rebuild their generated geometry.
Resetting a lighting owner restores the preceding owner's settings; after the
last owner is removed, the previous scene settings return. Manual lighting
edits made after applying the style are retained.

The native geometry and restoration metadata are stored in normal `.pse`
sessions. A saved view can be displayed without the plugin. Reinstall/import
the plugin to use refresh, reset and source-picking commands after reopening.
The metadata is associated with the PyMOL instance, not a process-wide scene.

## States and memory

`state=0` copies every loaded state. A positive integer copies just that state
and displays it as a static object; `state=current` uses the current frame.
Use ordinary `frame`, movie and playback commands for multi-state views.

```text
blender_style cartoon, state=0, quality=auto, memory_mb=512
frame 10
blender_style refresh
blender_style surface, state=current
```

Copies do not automatically follow later edits to source coordinates,
annotations or topology. `refresh` rebuilds a view from its original selection
expression. `refresh, name=all` rebuilds all views. Previously loaded states
play without a Python per-frame callback.

The active multi-state views use PyMOL's global `defer_builds_mode=3`, as well
as per-object deferred builds. This is required for state updates and for
discarding previous-state display geometry. The setting is restored when the
last multi-state view is removed, including when `lighting=keep` was used.

`quality=auto` selects high quality for small static models, medium for
trajectories or more than 20,000 atoms, and low above 100,000 atoms or two
million atom-states. Explicit low/medium/high overrides this policy.
`memory_mb` checks a conservative coordinate/geometry allocation estimate
before copying or raising quality. It includes existing managed views and
temporary replacement copies. It is not a hard process-RSS or driver-memory
limit. See [performance](performance.md).

## Geometry parameters

Pass a Python dictionary or a small local JSON object file. Unknown keys,
non-finite numbers and out-of-range values are rejected before mutation.

```python
from blender_style_in_pymol import blender_style

blender_style("ribbon", params={"ribbon_radius": 0.7})
blender_style("ball-and-stick", params={"sphere_scale": 0.35, "bond_radius": 0.2})
blender_style("cartoon", params={"cartoon_width": 2.2, "loop_radius": 0.3})
```

| Key | Default | Allowed range |
| --- | --- | --- |
| `sphere_scale` | 0.8; 0.3 for ball-and-stick | 0.01–4 |
| `bond_radius` | 0.2 Å; 0.3 Å for ball-and-stick | 0.01–3 Å |
| `ribbon_radius` | 1.6 Å | 0.05–5 Å |
| `cartoon_width` | 2.2, matching the reference profile control | 0.1–8 |
| `cartoon_thickness` | 0.6, matching the reference profile control | 0.05–3 |
| `loop_radius` | 0.3 Å | 0.05–3 Å |
| `surface_scale` | 1.5 × reference atomic radii | 0.5–3 |
| `probe_radius` | 1.0 Å | 0–5 Å |
| `bond_split` | 0 | 0 or 1; show supplied multiple-bond orders |
| `threshold` | 0.8 map units | −1,000,000–1,000,000; positive for signed ISO |
| `wire_radius` | 0.06 Å | 0.005–2 Å |
| `contours`, `only_contours` | 0 | 0 or 1 |

Width and thickness map to PyMOL profile half-extents; they are not full
cross-section dimensions. The correspondence was checked with rendered
Molecular Nodes geometry, rather than inferred from the socket labels alone.
Legacy presets have their own reference defaults: preset 1 uses a 1.4 Å
protein tube; preset 2 uses 2.4/0.4/0.2 cartoon width, thickness and loop
radius; non-polymer bonds in presets 1–2 have 0.25 Å radius. Preset 3 scales
protein radii by 1.5 and other spheres by 0.5. Preset 4 linearly maps source
B-factors to 0.2–3 Å tube radii in the copies, leaving original B-factors intact.

## Image export

```text
blender_style png, filename=viewport.png, width=1200, height=900
blender_style ray, filename=figure.png, width=2400, height=1800
ray 2400, 1800
png native_ray.png
```

GPU PNG needs a Qt/OpenGL session. Ray export also works headlessly and
uses native PyMOL primitives. The entire visible scene is exported.
`unset opaque_background` requests a transparent background.
Image buffers have a separate estimate checked against `memory_mb`; dimensions
are limited to 8192 per axis and 32 million total pixels. A larger budget
permits larger exports without changing molecular quality.
