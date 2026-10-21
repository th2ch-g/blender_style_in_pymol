# Representation coverage and fidelity

This plugin implements PyMOL counterparts of the Molecular Nodes representation
families. It does not run Blender Geometry Nodes or Blender materials. Coverage
of a representation does not imply identical geometry, shader output, or every
upstream socket and modifier.

## Coverage inventory

The inventory was checked against the official
[Style](https://bradyajohnston.github.io/MolecularNodes/nodes/style.html),
[Density](https://bradyajohnston.github.io/MolecularNodes/nodes/density.html) and
[DNA](https://bradyajohnston.github.io/MolecularNodes/nodes/dna.html) documentation,
and the [v520.2.0 source](https://github.com/BradyAJohnston/MolecularNodes/tree/v520.2.0/molecularnodes/nodes/geometry).
The four legacy presets were inspected in the installed Molecular Nodes 4.5.9
node asset, including their polymer selections and parameter defaults.

| Reference family | Counterpart | Main differences |
| --- | --- | --- |
| Cartoon | `cartoon`, `cartoon-rounded`, `cartoon-cylinders` | Native PyMOL spline frames and arrow transitions; nucleic rings/rungs replace rectangular base slabs |
| Ribbon | `ribbon` | Native backbone interpolation; no UV output |
| Spheres | `spheres` | Native sphere primitives replace point-cloud/mesh/instance modes |
| Ball and Stick | `ball-and-stick` | Uses supplied bonds; multiple bonds are optional; no distance-based bond inference |
| Sticks | `sticks` | Native cylinders and round caps |
| Surface | `surface` | PyMOL solvent-excluded surface; no voxel relaxation or independent chain surface separation |
| Preset 1 | `preset-1` | Polymer tubes plus other balls/sticks; no inferred bonds |
| Preset 2 | `preset-2` | Cartoon plus ligand-proximal side chains; proximity is evaluated at preparation time |
| Preset 3 | `preset-3` | Protein surface plus other spheres; native surface algorithm |
| Preset 4 | `preset-4` | B-factor-scaled native putty interpolation |
| Density Surface | `density-surface` | Native grid contour; no dust filtering |
| Density Wire | `density-wire` | Grid isolines instead of Blender triangulated-mesh edges |
| Density ISO Surface | `density-iso-surface` | Signed surfaces and optional mesh contours; no volume slicing |
| oxDNA Ribbon | `oxdna-ribbon` | Physical-unit base ellipsoids and tapered backbone segments; no custom instanced base geometry |

Older DNA sphere/surface/ball-and-stick nodes reuse the corresponding atomic
representations on nucleic atoms. The aliases `dna-spheres-cycles`,
`dna-spheres-eevee`, `dna-surface` and `dna-ball-and-stick` are accepted.
DNA-from-curve, trajectory importers, simulations, selections, assemblies and
geometry-processing nodes are upstream data generation/processing operations,
not additional molecular representations.

## Rendered reference comparison

Six examples were rendered with **Blender 4.5.2, Molecular Nodes 4.5.9 and
PyMOL 3.1.0**. These are the versions available for actual reference rendering;
the newer inventory above was checked from documentation and source.
Density, oxDNA and legacy presets have PyMOL render/lifecycle validation but
do not yet have a quantitative Blender image comparison.

The comparison script exports one set of coordinates, bonds, secondary
structure annotations, atom colors and an orthographic camera. It assigns
the shared annotations and linearized colors to the Blender reference. Both
images use 800 × 600 pixels. Blender uses Cycles CPU, 64 samples, the MN Default
material, a white environment, three soft area lights, Standard color transform
and transparent film. PyMOL uses the studio material and native ray tracing.
Using shared colors isolates geometry and shading; it does not test independent
upstream color assignment. The light models are approximately matched, not
identical. No AgX/Filmic tone-mapping match is claimed.

| Representation | Specimen | Silhouette IoU | Overlap RGB MAE |
| --- | --- | ---: | ---: |
| Cartoon | 1CRN | 0.8451 | 0.0692 |
| Ribbon | 1CRN | 0.9444 | 0.0686 |
| Spheres | Tryptophan fragment | 0.9994 | 0.0723 |
| Ball and stick | Tryptophan fragment | 0.9945 | 0.0462 |
| Sticks | Tryptophan fragment | 0.9940 | 0.0500 |
| Surface | 1CRN | 0.9540 | 0.1119 |

IoU is intersection divided by union of foreground masks at alpha > 0.5.
RGB MAE is mean absolute channel error over overlapping foreground pixels,
with channel values in [0, 1]. These six cases are calibration examples, not
an independent benchmark suite or proof of general visual equivalence.
Cartoon frame orientation and surface shading remain the largest differences.

Default radii, profile dimensions and palettes were checked against the node
assets. In particular, cartoon width/thickness controls correspond to native
profile half-extents; halving them again makes the PyMOL ribbons too thin.
Native extra loop/sheet smoothing is disabled to retain the reference backbone
path. Molecular Nodes Common colors are converted from linear values to display
sRGB for PyMOL.

## Reproduce a comparison

Install Blender and Molecular Nodes separately. Set `BLENDER_BIN` to the
Blender executable and `MOLECULAR_NODES_ADDON` to its installed add-on directory.
The script reads that installation and uses `--factory-startup`; it does not
install templates, modify the add-on or save Blender preferences.

```sh
pixi run gallery --fetch
pixi run uv run --no-project --python .pixi/envs/default/bin/python python \
    scripts/compare_reference.py \
    --structure .cache/reference/1crn.cif \
    --blender "$BLENDER_BIN" --addon "$MOLECULAR_NODES_ADDON" \
    --style cartoon --output .cache/reference/cartoon
```

Use `--style ribbon`, `spheres`, `ball-and-stick`, `sticks` or `surface`.
For atomic comparisons, save a local fragment with PyMOL and pass that file
with `--color element`. Output includes both rendered images, a side-by-side
comparison, metrics and input metadata. The reference script targets the 4.5
Python API; newer API layouts may need adaptation.

## Material limits

PyMOL supports scene lights, native specular highlights, alpha transparency,
surface occlusion and ray outlines. Those features approximate the studio,
matte, glossy, clay, flat, outline, transparent and occlusion looks. Cartoon
and atomic representations receive fill lighting, not geometric ambient
occlusion. Global lighting affects every visible object in the scene.
Blender roughness/metallic/IOR sockets, refraction, subsurface scattering,
HDR environments and Cycles/EEVEE shaders have no equivalent execution path.

The oxDNA loader's length conversion follows the
[oxDNA configuration specification](https://lorenzo-rovigatti.github.io/oxDNA/configurations.html).
Its orientation markers and rendered bases are a visualization of a coarse
model, not an all-atom reconstruction.
