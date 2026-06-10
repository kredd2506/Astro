# Astro — Collective-communication scaling in ASTRA-sim

Modeling **AllReduce / AllGather** scaling in
[ASTRA-sim](https://github.com/astra-sim/astra-sim) across **torus** and
**switch** topologies on the **analytical** and **ns-3** backends — comparing
**latency-bound** vs **bandwidth-bound** behavior as a function of collective
message size and node count.

📝 Write-up / blog: **[`site/`](site/)** (Jekyll "White Paper" theme).
The post: [`site/_posts/2026-06-10-modeling-allreduce-allgather-scaling-in-astra-sim.md`](site/_posts/2026-06-10-modeling-allreduce-allgather-scaling-in-astra-sim.md).

## What's here

```
experiments/
  gen_workload.py      bytes-based Chakra ET generator (reaches the small-message
                       latency-bound regime the stock integer-MB generator can't)
  run_sweep.py         emits torus/switch network + system configs, generates
                       workloads, runs the analytical backend, writes results CSV
  plot_results.py      latency-vs-size, effective-BW, scaling-vs-nodes, speedup heatmap
  results/
    analytical.csv     220 rows: 2 collectives x 2 topologies x 5 node counts x 11 sizes
    plots/*.png        the figures used in the blog post
site/                  the blog (Jekyll White Paper theme) with the write-up
astra-sim/             the simulator (NOT committed — clone it, see below)
```

## Reproduce

ASTRA-sim is cloned separately (it's large and has submodules):

```bash
git clone --recursive https://github.com/astra-sim/astra-sim.git

# build the image (Ubuntu 22.04 + abseil + protobuf) and the analytical backend
docker build -t astra-sim:latest astra-sim/
docker run --rm -v "$PWD":/app -w /app/astra-sim astra-sim:latest \
  ./build/astra_analytical/build.sh

# run the 220-point sweep, then plot on the host
docker run --rm -v "$PWD":/app -w /app astra-sim:latest \
  bash -lc 'PYTHONPATH=/app:/app/astra-sim python experiments/run_sweep.py'
python3 experiments/plot_results.py
```

## Method (one paragraph)

ASTRA-sim cleanly separates **workload** (the collective + message size, as a
Chakra execution trace), **system** (the collective *algorithm* — ring per
dimension here), and **network** (the *topology* and per-link bandwidth/latency).
I hold per-link physics identical (50 GB/s, 500 ns) so the only variable is
fabric structure: **switch** = `topology: [Switch]` (one logical hop, shared
bandwidth) vs **2-D torus** = `topology: [Ring, Ring]` (a multi-hop ring mesh,
e.g. 4×4 for 16 NPUs). The analytical runs use the **congestion-unaware** backend
(the one that supports multi-dimensional topologies); collective latency is the
max `sys[i] finished` cycle across ranks. An **ns-3** packet-level slice (8-node
switch vs ring at matched 400 Gbps / 500 ns) validates that the regimes survive
real congestion/protocol overhead.

## Headline findings

- Every curve has a **flat latency-bound floor** (small messages: time ≈ steps ×
  link latency) and a **slope-1 bandwidth-bound ramp** (large messages: time ≈
  bytes ÷ link bandwidth).
- **Torus speedup over switch is regime-dependent:** up to **14×** latency-bound
  at 64 NPUs / 1 KiB (switch ring does `N−1` sequential hops vs torus's
  ~`2(√N−1)`), collapsing to **~1.1–1.5×** bandwidth-bound at 1 GiB.
- The **latency→bandwidth crossover** moves with topology: at 16 NPUs, AllReduce
  crosses ~1 MB on the torus but ~4 MB on the switch.
