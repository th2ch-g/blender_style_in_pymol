# Performance and memory

Automatic rendering balances preparation cost and fidelity. Supported static
views use smooth meshes if their allocation estimate fits below 80% of the
requested budget. Trajectories and larger selections use native PyMOL by default.
Use `backend=mesh` to request explicit mesh preparation, or `backend=native` for
native picking and lower preparation cost.

Meshes are generated once, then drawn through indexed buffers. The OpenGL
cache is limited to 128 MiB per context and evicts older buffers; no geometry
is rebuilt while rotating an opaque static view. Transparent faces are sorted
for each changed view direction. Explicit mesh trajectories retain every
selected state's mesh in CPU memory and upload/evict its GPU buffers as needed.
Material changes reuse mesh arrays but update callbacks and ray proxies.

Native trajectories use deferred PyMOL state geometry. oxDNA stores compact
CGO primitives per state; density contours use native map data without an extra
voxel copy. These representations retain their separate allocation estimates.

## Quality and allocation policy

`quality=auto` chooses high for static selections up to 20,000 atoms, medium for
trajectories or larger selections, and low above 100,000 atoms or two million
atom-states. This is separate from the backend choice: a large high-quality
selection may still select native rendering. Explicit low/medium/high overrides
quality. Multi-state views set and later restore global `defer_builds_mode=3`.

`memory_mb=512` checks a conservative estimate before preparing geometry. It
includes molecular copies, indexed arrays, ray display lists, all explicit mesh
states, existing views and temporary replacement work. Surface voxel dimensions
are checked before grid allocation; queries and occlusion evaluation are chunked.
Ray refinement is reduced to fit its temporary allocation estimate. Rejected
preparation leaves the previous view intact.

This is **not a process RSS cap**. Qt, native allocation caches, the original
structures, driver resources and images add memory outside the estimate. The
GPU cache limit does not include PyMOL's own GL resources. Use smaller selections,
`state=current`, lower quality or the native backend to reduce work. The
`blender_style png/ray` helpers separately check image dimensions and buffers;
standard PyMOL `ray` retains its normal resolution arguments.

## Measured examples

Measured with PyMOL 3.1.0 on Apple M4/OpenGL 2.1 Metal, using a 780 × 610 viewport
and 60 synchronized redraws per series. Inputs are synthetic proteins; the
20-state motion is generated for validation and is not an MD trajectory.

| Workload | Preparation | Material update median | Rotation median / p95 | Styled playback |
| --- | ---: | ---: | ---: | ---: |
| 8,000 atoms × 20 states, native/medium | 43.5 ms | 4.79 ms | 0.84 / 1.64 ms | 46.1 frames/s |
| 800 atoms × 1 state, cartoon mesh/high | 627.6 ms | 26.26 ms | 0.50 / 1.04 ms | Static |
| 400 atoms × 1 state, surface mesh/high | 742.0 ms | 26.52 ms | 0.63 / 1.08 ms | Static |

The trajectory's native baseline was 47.0 frames/s, versus 46.1 with styling.
Its median/p95 state update was 21.56/22.98 ms. Rotation timings are programmatic
redraw throughput including `glFinish`, not a claim about display refresh rate.
The surface run's baseline is a native cartoon, so it is not a like-for-like
surface speed comparison. These workloads do not predict all structures/drivers.

| Workload | Planning estimate | RSS before styling | RSS after drawing | RSS after 10 material changes | RSS after another drawing pass |
| --- | ---: | ---: | ---: | ---: | ---: |
| 8,000 atoms × 20 states, native/medium | 45.0 MiB | 433.9 MiB | 523.8 MiB | 523.8 MiB | 524.4 MiB |
| 800 atoms × 1 state, cartoon mesh/high | 114.7 MiB | 182.0 MiB | 266.2 MiB | 299.8 MiB | 299.8 MiB |
| 400 atoms × 1 state, surface mesh/high | 76.4 MiB | 173.5 MiB | 270.9 MiB | 300.8 MiB | 306.1 MiB |

Mesh preparation and the first material changes grow native/Python allocation
caches. Reset removes objects and restores source representations but does not
force allocators or the driver to return pages to the OS. After image validation
and reset, these runs retained 576.2, 372.1 and 374.2 MiB respectively. This short
measurement is not a long-duration leak test or a hard upper bound. The script
exports real GPU frames and checks nonempty, changing trajectory images.

## Reproduce

```sh
pixi run benchmark
pixi run uv run --no-project --python .pixi/envs/default/bin/python python \
    scripts/benchmark.py --gui --output .cache/benchmark-trajectory.json
pixi run uv run --no-project --python .pixi/envs/default/bin/python python \
    scripts/benchmark.py --gui --residues 200 --states 1 --backend mesh \
    --output .cache/benchmark-mesh-cartoon.json
pixi run uv run --no-project --python .pixi/envs/default/bin/python python \
    scripts/benchmark.py --gui --residues 100 --states 1 --backend mesh \
    --representation surface --output .cache/benchmark-mesh-surface.json
```

Headless runs measure preparation, updates and RSS. GUI runs require Qt/OpenGL
and add synchronized redraws and image validation. `--quality`, `--backend`,
`--residues`, `--states`, `--frames` and `--representation` control the workload.
CI publishes headless reports and separately validates shaders, session restore,
transparent images and standard ray commands under Xvfb/Mesa.
