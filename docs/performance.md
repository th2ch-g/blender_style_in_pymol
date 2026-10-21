# Performance and memory

Atomic and protein styles use native PyMOL molecular representations. They
do not build Python triangle meshes or run callbacks on every movie frame.
Molecular coordinates are copied once per named view. Reapplying a native
style with only a material change reuses those copies. oxDNA stores compact
CGO primitives for each selected state; map styles use native contour objects
without copying the input voxel field.

## Quality and allocation policy

`quality=auto` chooses high quality for static selections up to 20,000 atoms,
medium for trajectories or larger selections, and low above 100,000 atoms or
two million atom-states. Explicit low/medium/high overrides the policy.
Multi-state views set global `defer_builds_mode=3` so native molecular display
geometry is rebuilt for the displayed state and previous-state geometry can
be discarded. The prior setting is restored on reset.

`memory_mb=512` checks a planning estimate before preparing geometry. This
includes coordinates, molecular metadata, representation-dependent geometry,
existing managed views and temporary replacement copies. oxDNA estimates
include every stored state's CGO; density estimates scale with voxel count
and signed contour count. Large exports have a separate image-buffer estimate.
Rejected requests leave the previous view intact.

The estimate is **not a process RSS cap**. Qt, native allocation caches,
driver buffers, the original structures and images add memory outside that
estimate. GPU/driver allocation is not measured separately. Use a smaller
selection, `state=current`, lower quality, a coarser map or trajectory stride
to reduce work. Increase the budget explicitly when that is appropriate.

## Measured example

The GUI benchmark uses a synthetic 8,000-atom protein with 20 states, rendered
in a 780 × 610 viewport on an Apple M4 with PyMOL 3.1.0 and OpenGL 2.1 Metal.
The motion is generated for validation; it is not an MD trajectory. Both the
native and styled paths traverse all states before their RSS is recorded.
The styled cartoon uses automatic medium quality.

| Measurement | Result |
| --- | ---: |
| Prepare named view | 49.2 ms |
| Material update, median of 10 | 4.93 ms |
| Native rotation, median / p95 | 1.21 / 2.09 ms |
| Styled rotation, median / p95 | 0.87 / 2.00 ms |
| Native state playback | 46.8 frames/s |
| Styled state playback | 44.9 frames/s |
| Styled state update, median / p95 | 22.01 / 23.79 ms |
| Copied coordinates | 1.83 MiB |
| Plugin allocation estimate | 45.04 MiB |
| Process RSS after native playback | 417.42 MiB |
| Process RSS after styling and playback | 515.42 MiB |
| RSS after 10 material updates | 515.42 MiB |
| RSS after another playback pass | 515.45 MiB |
| RSS after image validation | 554.89 MiB |

Timings cover 60 programmatic redraws per series and include `glFinish`.
Rotation is redraw throughput, not a claim that the display presents hundreds
of frames per second. Playback includes native geometry rebuilding. Results
vary by driver, structure, viewport and quality; this is one measured example.
The script also exports states 1, 2 and 20 and checks that they are nonempty
and differ, so a fast blank-frame path cannot pass validation.

Reset removes managed objects and restores source representations. It does
not force the Python/native/driver allocators to return pages to the OS; RSS
remained at 554.89 MiB after reset in this run. The second playback and repeated
material updates showed stable RSS, but this short run is not a long-duration
leak test.

## Reproduce

```sh
pixi run benchmark
pixi run uv run --no-project --python .pixi/envs/default/bin/python python \
    scripts/benchmark.py --gui --output .cache/benchmark-gui.json
```

The headless command measures preparation, material changes and RSS. It does
not report rotation or playback throughput. The GUI command requires an
available Qt/OpenGL display and adds synchronized redraws and frame images.
Use `--residues`, `--states`, `--frames`, `--representation` and `--output`
to change the workload. Density and oxDNA require their own inputs; the
synthetic protein benchmark is intended for the molecular representations.
CI publishes headless reports with the build artifacts and separately renders
the actual GPU/ray gallery under Xvfb and Mesa.
