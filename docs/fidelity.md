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
| Cartoon | `cartoon`, `cartoon-rounded`, `cartoon-cylinders` | Independent spline frames and arrow transitions; oriented rectangular nucleic bases in mesh mode |
| Ribbon | `ribbon` | Bezier backbone interpolation; no UV output |
| Spheres | `spheres` | Indexed sphere meshes or native primitives; no Blender instance output |
| Ball and Stick | `ball-and-stick` | Uses supplied bonds; multiple bonds are optional; no distance-based bond inference |
| Sticks | `sticks` | Indexed cylinders and round caps, or native primitives |
| Surface | `surface` | Chain-separated volume meshing, radius projection and relaxation; native mode uses a solvent-excluded surface |
| Preset 1 | `preset-1` | Polymer tubes plus other balls/sticks; no inferred bonds |
| Preset 2 | `preset-2` | Cartoon plus ligand-proximal side chains; proximity is evaluated at preparation time |
| Preset 3 | `preset-3` | Relaxed protein surface plus native spheres for other atoms |
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

Actual references use **Blender 4.5.2, Molecular Nodes 4.5.9 and PyMOL 3.1.0**.
The newer inventory above was checked from documentation and source. Density,
oxDNA and legacy presets have PyMOL render/lifecycle validation but no quantitative
Blender image comparison. Cylindrical cartoons and B-factor putty use native PyMOL.

The comparison exports the same coordinates, supplied bonds, secondary structure,
atom colors and orthographic camera to both renderers. Alternative locations are
resolved consistently. Images are 800 × 600. Blender uses Cycles CPU, 64 samples,
a white environment at strength 0.35, three disk area lights, Standard color
transform and transparent film. No AgX/Filmic match is claimed. Shared colors
isolate geometry and shading; this does not validate independent color assignment.

The following studio comparisons use high-quality meshes and PyMOL ray tracing.
GPU images were also generated and checked. These structures were used during
development, so this is a calibration set rather than an independent benchmark.

| Representation | Specimen | Silhouette IoU | Overlap RGB MAE |
| --- | --- | ---: | ---: |
| Cartoon | 1CRN | 0.9218 | 0.0550 |
| Cartoon | 1UBQ | 0.9226 | 0.0466 |
| Cartoon | 1A6M | 0.9429 | 0.0743 |
| Cartoon / nucleic bases | 1BNA | 0.9770 | 0.0491 |
| Surface | 1UBQ | 0.9738 | 0.0294 |
| Surface | 1A6M | 0.9793 | 0.0409 |
| Surface | 1BNA | 0.9674 | 0.0339 |
| Ball and stick | Tryptophan fragment | 0.9945 | 0.0115 |

The earlier native-only 1CRN cartoon measured IoU 0.8451 and RGB MAE 0.0692;
its surface measured 0.9540 and 0.1119. All six original native calibration
images used 1CRN, including atomic styles; they were previously mislabeled
as tryptophan in this report. The current fragment comparison above is a
separate, explicitly exported tryptophan structure.

IoU is foreground intersection divided by union at alpha > 0.5. RGB MAE is
mean absolute channel error on overlapping foreground, with values in [0, 1].
The metrics do not establish identical geometry or photorealistic equivalence.
Spline transitions, occlusion and multi-object lighting remain approximations.

### Materials

The original eight materials were compared on the same 1CRN cartoon. `studio`,
`ambient-occlusion` and `outline` use the installed MN Default, MN Ambient
Occlusion and MN Flat Outline assets as references. `matte`, `glossy`, `clay`
and `transparent` use explicitly configured Principled materials, while `flat`
uses emission. They are plugin material choices, not a claim that all eight
are named upstream assets. The reference uses MN Color Input for both mesh
and instanced atom colors. Clay uses the shared secondary-structure colors in
this shader comparison; its automatic clay palette is tested in the gallery.

| Material | Ray RGB MAE | Reference |
| --- | ---: | --- |
| Studio | 0.0550 | MN Default |
| Ambient occlusion | 0.0465 | MN Ambient Occlusion |
| Matte | 0.0565 | Roughness 0.85, specular level 0 |
| Glossy | 0.0597 | Roughness 0.18, IOR 1.45 |
| Clay | 0.0565 | Roughness 0.9, specular level 0 |
| Flat | 0.0040 | Emission |
| Outline | 0.0494 | MN Flat Outline |
| Transparent | 0.0645 | Roughness 0.22, IOR 1.45, transparent mix 0.5 |

The transparent case uses alpha > 0.05 for foreground: ray IoU 0.9247, alpha
MAE 0.0750; GPU IoU 0.9205, RGB MAE 0.0676, alpha MAE 0.0764. A 0.5 alpha
threshold would incorrectly discard much of a transparent object. The separate
tryptophan glossy comparison gives ray/GPU RGB MAE 0.0196/0.0203, and its
ambient-occlusion ray comparison gives 0.0133.

### Geometry and shading model

The independent mesh implementation follows the inspected 4.5 node parameters:
chain-separated occupancy volumes, nearest-atom radius projection, concavity
relaxation and linear-color smoothing for surfaces; backbone carbon/nitrogen
frames, sheet smoothing and profile rotation for cartoons; C4-prime backbones
and base-oriented rectangles for nucleic acids. Width/thickness controls are
profile half-extents. Common element colors are converted from linear RGB to
sRGB. The package does not contain upstream node assets or source code.

An area-weighted surface-patch visibility estimate supplies geometric occlusion.
The GPU shader uses linear-light diffuse/GGX shading, roughness and an approximate
three-area-light model. Ray tracing samples the same model on adaptively refined
triangles and uses native ray intersections. Occlusion is approximate and baked
at preparation; it is not a path-traced visibility integral.

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
    --style cartoon --backend mesh --gui --output .cache/reference/cartoon
```

Use `--style ribbon`, `spheres`, `ball-and-stick`, `sticks` or `surface`.
Use `--material` for any material, and omit `--gui` for headless ray-only runs.
For atomic comparisons, save a local fragment with PyMOL and pass that file
with `--color element`. Output includes both rendered images, a side-by-side
comparison, metrics and input metadata. The reference script targets the 4.5
Python API; newer API layouts may need adaptation.

## Remaining differences

Mesh and native backends have different lighting and geometry. Automatic mode
chooses the native path for trajectories and selections exceeding the mesh
planning threshold. Mesh surfaces have no native atom picking IDs. `lighting=keep`
uses native CGO lighting with baked occlusion instead of the dedicated shader.

Standard `ray`, `cmd.ray()` and `png ..., ray=1` refresh the current-state shading
and restore settings afterward. In a scene containing only physical meshes,
ray output disables native lighting temporarily to avoid double shading. Mixed
native/mesh scenes retain scene lights, which can change the mesh ray appearance.
GPU transparent faces are sorted per mesh, not globally across intersecting
objects. View-dependent effects use an orthographic approximation, so strong
perspective or stereo can differ from Blender.

Version 0.3 adds an optional Cycles renderer for actual refraction, random-walk
SSS, area-light shadows and indirect illumination. The [Cycles guide](cycles.md)
documents its separate physical-effect tests. These renders use the plugin's
meshes, rather than rebuilding Molecular Nodes geometry in Blender. The viewport
and native PyMOL ray renderer remain approximations. Arbitrary node graphs,
HDR environments and EEVEE are not exposed. Blender's named Squishy and
Transparent Outline assets are not imported as separate materials.
The native backend has surface-only occlusion and ray-only outlines.

The oxDNA loader's length conversion follows the
[oxDNA configuration specification](https://lorenzo-rovigatti.github.io/oxDNA/configurations.html).
Its orientation markers and rendered bases visualize a coarse model; they are
not an all-atom reconstruction.
