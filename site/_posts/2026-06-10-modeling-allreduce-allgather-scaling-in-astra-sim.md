---
layout: post
title: "Modeling AllReduce / AllGather Scaling in ASTRA-sim: Torus vs Switch, Latency-Bound vs Bandwidth-Bound"
description: "A message-size x node-count sweep of collective communication across torus and switch fabrics on ASTRA-sim's analytical (and ns-3) backends, and where each topology wins."
category: systems
tags: [astra-sim, distributed-ml, collectives, allreduce, allgather, networks, ns-3, simulation]
comments: false
---

When you train a large model across many accelerators, a surprising fraction of
wall-clock time is *not* spent doing math — it is spent in **collective
communication**: `AllReduce` to average gradients, `AllGather` to assemble
sharded tensors. How long those collectives take depends on three things that
interact in non-obvious ways: the **message size**, the **number of nodes**, and
the **interconnect topology**.

I used [ASTRA-sim](https://github.com/astra-sim/astra-sim) — Georgia Tech and
Intel's distributed-ML network simulator — to model that interaction directly.
The question: *as message size and node count vary, when is a collective
**latency-bound** versus **bandwidth-bound**, and how does that boundary move
between a multi-hop **torus** and a one-hop **switch** fabric?*

## TL;DR

- I swept **AllReduce** and **AllGather** over **5 node counts (4–64)** × **11
  message sizes (1 KiB–1 GiB)** × **2 topologies** on ASTRA-sim's analytical
  backend (220 runs), holding per-link bandwidth (50 GB/s) and latency (500 ns)
  identical so the *only* variable is fabric structure.
- Every curve shows the same two regimes: a **flat latency-bound floor** for
  small messages (time ≈ number of algorithm steps × per-link latency) and a
  **slope-1 bandwidth-bound ramp** for large messages (time ≈ bytes ÷ link
  bandwidth).
- **The torus's advantage is a strong function of regime.** Latency-bound at
  scale, a 2-D torus beats a switch by up to **14×** (at 64 NPUs, 1 KiB),
  because the switch's ring collective does `N−1` sequential steps while the
  torus does only ~`2(√N−1)`. Bandwidth-bound at 1 GiB, that advantage collapses
  to **~1.1–1.5×** — the two fabrics move nearly the same data volume.

## Setup

ASTRA-sim separates three concerns, which is exactly what makes this sweep
clean:

| Layer | What it specifies | How I varied it |
|---|---|---|
| **Workload** | the collective + message size (Chakra execution trace) | synthetic single-op `AllReduce`/`AllGather` traces, **1 KiB → 1 GiB** |
| **System** | the collective *algorithm* (ring, etc.) | ring per dimension |
| **Network** | the *topology* + per-link BW/latency | **switch** (1 dim) vs **2-D torus** (Ring×Ring) |

**Topologies, held to identical link physics (50 GB/s, 500 ns):**

```yaml
# switch (one hop, bandwidth shared across the collective)
topology:   [ Switch ]
npus_count: [ 16 ]
bandwidth:  [ 50.0 ]   # GB/s
latency:    [ 500.0 ]  # ns

# 2-D torus (a multi-hop ring mesh; here 4x4 = 16 NPUs)
topology:   [ Ring, Ring ]
npus_count: [ 4, 4 ]
bandwidth:  [ 50.0, 50.0 ]
latency:    [ 500.0, 500.0 ]
```

The stock workload generator only takes integer **MB**, which can't reach the
small-message latency-bound regime, so I wrote a **bytes-based** Chakra
generator to sweep cleanly on a log scale from 1 KiB. The analytical runs use
the **congestion-unaware** backend — the model built for multi-dimensional
(hierarchical) topologies — so the *same* backend drives both fabrics. Each run
parses the per-rank `sys[i] finished, <cycles>` lines and takes the **max across
ranks** (the collective finishes when the slowest rank does).

Everything is reproducible from a single Docker image; the harness (generator,
sweep, plotter) is in the repo.

## Result 1 — the two regimes, and where torus separates from switch

![Latency vs message size, AllReduce and AllGather, 16 NPUs]({{ site.baseurl }}/assets/astra/analytical_fig1_latency_vs_size_16npus.png)

Read each curve left to right. On the left, latency is **flat** — doubling a
tiny message barely moves it, because time is dominated by the fixed per-step
link latency, not the payload. This is the **latency-bound** regime. On the
right, every curve becomes a **straight slope-1 line** on log-log axes: latency
is now proportional to bytes, i.e. **bandwidth-bound**.

The two topologies sit on top of each other while latency-bound (same number of
algorithm steps), then the **torus pulls clearly below the switch** as messages
grow — its 2 links/node give more aggregate bandwidth than the switch's shared
fabric. At 16 NPUs, AllReduce crosses from latency- to bandwidth-bound around
**~1 MB on the torus** but only around **~4 MB on the switch**: the switch's
higher latency floor keeps it latency-bound longer.

## Result 2 — effective bandwidth saturating toward the roofline

![Effective bus bandwidth vs message size, 16 NPUs]({{ site.baseurl }}/assets/astra/analytical_fig2_effbw_vs_size_16npus.png)

The same data as *delivered* bandwidth (bytes ÷ time). Small messages waste the
fabric — almost all the time is latency, so effective bandwidth is near zero.
As messages grow, each curve climbs and **saturates toward a topology-dependent
roofline**. The torus's roofline is higher; the switch saturates lower. The knee
of this curve *is* the latency→bandwidth crossover from Result 1.

## Result 3 — scaling with node count depends on the regime

![Latency vs node count, small vs large message]({{ site.baseurl }}/assets/astra/analytical_fig3_scaling_vs_nodes.png)

This is the part that bites in practice. **Latency-bound (left, 4 KB):** the
switch's latency grows almost **linearly with N** — 24 → 57 → 121 → 251 → 509 µs
from 4 to 64 NPUs — because ring-on-switch executes `N−1` sequential hops. The
torus grows far more slowly (steps scale with the longest dimension, ~`√N`).
**Bandwidth-bound (right, 256 MB):** both fabrics flatten out — adding nodes
barely changes time because the per-node data volume of a ring collective is
nearly independent of `N` — and the gap narrows to a constant factor.

## Result 4 — putting it together: when does topology matter?

![Torus speedup over switch across the size x node grid]({{ site.baseurl }}/assets/astra/analytical_fig4_torus_speedup.png)

One picture for the whole study: torus speedup over switch for AllReduce across
every (size, node) cell. The story is a **gradient**:

- **Top-left (large messages):** ~1.1–1.8×. Bandwidth-bound — topology is a
  second-order effect; you're paying for bytes either way.
- **Bottom-right (small messages, many nodes):** up to **14.2×**. Latency-bound
  at scale — topology is *everything*, because hop count is what you're paying
  for, and that's exactly where torus and switch differ most.

**The takeaway for system design:** if your collectives are small and frequent
(latency-bound — think small gradients, frequent syncs, large clusters), fabric
topology dominates and a low-diameter mesh pays off enormously. If they're large
and infrequent (bandwidth-bound — think big tensors), you are buying raw link
bandwidth and the topology choice matters far less.

## Validating with the ns-3 backend

The analytical backend is an idealized link model — fast, great for sweeping a
big grid, but it does not model packet-level congestion, PFC, or congestion
control. ASTRA-sim's **ns-3 backend** does. I rebuilt it (`./ns3 configure
--enable-mpi && ./ns3 build AstraSimNetwork`) and ran a matched 8-node slice: a
one-hop **switch** fabric vs a **ring** (= 1-D torus), both pinned to **400 Gbps
/ 500 ns** links so the only difference is fabric structure, driving the *same*
Chakra workloads through ns-3's packet-level RDMA model across 16 KiB → 16 MiB.

![ns-3 vs analytical validation, 8 NPUs]({{ site.baseurl }}/assets/astra/ns3_fig5_validation.png)

The regimes survive the move to packet-level simulation. ns-3 sits **above** the
analytical model everywhere (left panel) — it pays for packet headers and the
congestion-control ramp the idealized model ignores, and that overhead is
*relatively* larger for small messages — but the **shape is the same**: a flat
latency-bound floor, a bandwidth-bound ramp, and ring consistently below switch.
The clincher is the right panel: the **ring-over-switch speedup shrinks from ~2×
(latency-bound) toward ~1.1× (bandwidth-bound)** in *both* backends, tracking
each other closely. The packet-level simulator independently reproduces the
central finding — **topology matters most when you're latency-bound** — which is
exactly the confidence a second, more detailed backend is supposed to buy you.

## Reproducing

The full harness is in the repo — one Docker image, a bytes-based Chakra
workload generator, the topology/system config emitters, the sweep runner, and
the plotting script:

```bash
# build the simulator image + analytical backend (in Docker)
docker build -t astra-sim:latest astra-sim/
docker run --rm -v "$PWD":/app -w /app/astra-sim astra-sim:latest \
  ./build/astra_analytical/build.sh

# run the 220-point sweep and plot
docker run --rm -v "$PWD":/app -w /app astra-sim:latest \
  bash -lc 'PYTHONPATH=/app:/app/astra-sim python experiments/run_sweep.py'
python3 experiments/plot_results.py
```

## What I'd model next

- **3-D torus and fat-tree** at 256–1024 NPUs, where diameter differences widen.
- **Algorithm × topology**: halving-doubling and direct AllReduce, not just ring
  — the latency floor is set by the algorithm's step count, so the regime map
  shifts.
- **ns-3 congestion at scale**: where does PFC/back-pressure make the analytical
  model optimistic?

---

*Built with ASTRA-sim (analytical + ns-3 backends), Chakra execution traces, and
a Python sweep/plot harness. Code and configs:
[github.com/kredd2506/Astro](https://github.com/kredd2506/Astro).*
