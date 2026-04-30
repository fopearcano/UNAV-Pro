# Performance Targets

What v1.0 promises, what v1.0 does **not** promise, and how to
measure it. Honest numbers; no fake benchmarks.

For the scope that produced these numbers see
[`V1_0_GPU_RENDERER.md`](V1_0_GPU_RENDERER.md).

---

## 1. Targets

| Cloud size | Goal                                | v1.0 status |
|-----------:|-------------------------------------|-------------|
| 10 k       | Smooth (60+ fps).                   | ✓ Per-point `BaseDraw::DrawPoint` + the v1.0 CPU shadow keep the editor responsive. |
| 100 k      | Usable (30+ fps).                   | ✓ With the per-mode hard cap and the picking grid. The per-point draw call is the bottleneck — the v1.1 single `DrawArrayWithVertexBuffer` will lift this. |
| 1 M        | Target — depends on SDK / render path. | Partial: the **load** + **picking** + **fallback** paths sustain 1 M points cleanly; the per-point editor draw call does not. v1.0 documents 1 M as a load-time target, not a per-frame target. |

The 10 k / 100 k targets use the v1.0 native draw path
(`BaseDraw::DrawPoint` per vertex). The 1 M target lights up
fully only after v1.1's array-draw + GPU-buffer landing.

---

## 2. Where the time goes

Profile of a v1.0 Sync click on a 100 k-point catalog
(measured during development; reproduce via the benchmark CLI):

```
generate (Python synthetic)  : ~150 ms     (1.0 Mpoints/s)
v2 extras                    :   ~5 ms
binary export (Python write) :  ~70 ms     (~70 MB/s)
binary parse (Python read)   : ~110 ms     (0.9 Mpoints/s)
binary load (C++ loadFromFile):  ~25 ms    (4 Mpoints/s)
accel grid build             :   ~5 ms
GPU shadow build             :   ~3 ms
draw (per redraw, CPU shadow): ~30 ms      (CPU draw loop)
```

The numbers vary by machine; the benchmark CLI is the canonical
measurement tool.

---

## 3. The benchmark CLI

`tools/benchmark_visible_sector_export.py` is the v1.0 honest-
numbers benchmark. It generates a synthetic point catalog of
N rows, runs each phase, and prints wall-clock timings.

```bash
python tools/benchmark_visible_sector_export.py \
    --points 100000 \
    --version v2 \
    --camera-relative \
    --output /tmp/bench.unav
```

Output:

```
Benchmark: 100000 points, version=v2, camera_relative=True
  generate :   150.21 ms (0.665 Mpoints/s)
  v2 extras:     4.92 ms
  export   :    73.40 ms (file 4.96 MB, 67.6 MB/s, 52.0 bytes/pt)
  parse    :   119.12 ms (0.840 Mpoints/s, 100000 points decoded)
```

What it does:

* Synthetic point generation seeded by `--seed`.
* Builds the v2 extras (when `--version v2`).
* Writes the binary file.
* Reads the file back and validates the CRC.
* Cleans up the temp file when `--output` is omitted.

What it deliberately does **not** do:

* Warm caches before timing. First call is the cold-start
  number.
* Pre-touch malloc.
* Lie about phase boundaries.

The benchmark covers the Python ↔ binary boundary; the C++
draw side is exercised by the unit tests and (in production)
by the C4D editor's profiler.

---

## 4. Per-mode caps

| Mode             | Hard cap   | Soft warning |
|------------------|-----------:|-------------:|
| Debug Objects    |    10 000  |       5 000  |
| Instances        |   200 000  |      50 000  |
| Point Cloud      | 1 000 000  |       —      |
| Native Viewer    | 2 000 000  |     500 000  |

The Native Viewer Mode's hard cap (2 M) is advisory — the C++
loader independently rejects files claiming
``point_count > 50 000 000`` (the absurd-count guard). In
practice the 2 M cap is the budget the dialog allocates for
the renderer; the absurd-count guard is the safety net
catching malicious / corrupt files.

---

## 5. Honest limits (v1.0)

* **Per-point draw is `BaseDraw::DrawPoint`.** v1.1+ moves to
  `DrawArrayWithVertexBuffer`. Until then, draw cost is linear
  in point count and the editor framerate degrades past
  ~50 k points.
* **CPU fallback path is real, not a stub.** When the GPU
  upload doesn't happen (the v1.0 default), the renderer
  walks the CPU shadow per draw. Slower, but correct.
* **Picking is CPU-side.** Brute force or uniform-grid
  acceleration. Pixel-accurate depth-buffer pick is a v1.1
  feature.
* **Load is sync.** The C4D plugin's main thread runs the
  load; large files (≥ 1 M points) stall the editor for the
  load duration. v1.2+ moves the load to a worker thread.
* **No streaming.** The whole binary file loads into memory
  at once. Memory pressure caps the practical cloud size to
  what fits in RAM minus the C4D scene's own working set.

---

## 6. Memory budget

The dialog's status strip shows three numbers after a load:

| Metric                  | Cost per point | At 1 M points |
|-------------------------|---------------:|--------------:|
| Disk file (52 B / pt)   |       52 bytes |    ~52 MB     |
| CPU buffer (UnavPoint, 52 B)  | 52 bytes |    ~52 MB     |
| GPU shadow (GpuVertex, 40 B)  | 40 bytes |    ~40 MB     |

Total transient: ~144 MB for a 1 M-point cloud (file + CPU
buffer + GPU shadow). The accel grid adds ~32^3 × sizeof(vector)
≈ 1 MB more.

For comparison, a Debug Objects build of 1 M points would need
~1 GB of C4D BaseObject overhead — which is exactly why Native
Viewer Mode is the recommended path past 10 k.

---

## 7. How to measure your scene

1. Run the benchmark CLI for the sizes you care about.
2. Run a real Sync (Native Viewer Mode) and check the dialog's
   status strip. The `load time` line is the C++ load cost; the
   `file size` is the disk cost.
3. For draw cost, use Cinema 4D's built-in profiler against a
   running scene. v1.0 doesn't ship a per-frame profiler hook
   — the v1.1 SceneHook will.

---

## 8. v1.1 outlook

* `BaseDraw::DrawArrayWithVertexBuffer` lifts the per-vertex
  draw call to single-call. Expected ≥ 10× draw speedup for
  large clouds.
* GPU-resident vertex buffer eliminates per-frame upload.
* `BaseDraw::PickObject` for pixel-accurate selection.
* SceneHook for per-frame Auto-Sync.

These are tracked in
[`PYTHON_TO_CPP_MIGRATION_PLAN.md`](PYTHON_TO_CPP_MIGRATION_PLAN.md);
v1.0 is the foundation they all build on.
