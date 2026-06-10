---
layout: post
title: "Modeling Collective-Communication Scaling in ASTRA-sim"
date: 2026-06-07
tags: [astra-sim, distributed-ml, collectives, overview]
---

When you train a large model across many accelerators, a surprising fraction of
wall-clock time is *not* spent doing math — it is spent in **collective
communication**: `AllReduce` to average gradients, `AllGather` to assemble
sharded tensors. How long those collectives take depends on three things that
interact in non-obvious ways: the **message size**, the **number of nodes**, and
the **interconnect topology**.

This is the first in a short series modeling that interaction directly in
[ASTRA-sim](https://github.com/astra-sim/astra-sim) — Georgia Tech and Intel's
distributed-ML network simulator. The question: *as message size and node count
vary, when is a collective **latency-bound** versus **bandwidth-bound**, and how
does that boundary move between a multi-hop **torus** and a one-hop **switch**
fabric?*

### TL;DR for the series

- I swept **AllReduce** and **AllGather** over **5 node counts (4–64)** × **11
  message sizes (1 KiB–1 GiB)** × **2 topologies** on ASTRA-sim's analytical
  backend (220 runs), holding per-link bandwidth (50 GB/s) and latency (500 ns)
  identical so the *only* variable is fabric structure.
- Every curve shows the same two regimes: a **flat latency-bound floor** for
  small messages (time ≈ algorithm steps × per-link latency) and a **slope-1
  bandwidth-bound ramp** for large messages (time ≈ bytes ÷ link bandwidth).
- **The torus's advantage is a strong function of regime** — up to **14×**
  latency-bound at scale, collapsing to **~1.1–1.5×** bandwidth-bound. ([the
  full size sweep]({{ site.url }}/2026/06/08/latency-bound-vs-bandwidth-bound.html),
  [scaling with nodes]({{ site.url }}/2026/06/09/when-does-topology-matter.html))
- An **ns-3 packet-level** run independently reproduces those regimes. ([ns-3
  validation]({{ site.url }}/2026/06/10/validating-with-ns3.html))

### Why ASTRA-sim makes this clean

ASTRA-sim separates three concerns, which is exactly what lets us isolate
topology:

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
small-message latency-bound regime, so I wrote a **bytes-based** Chakra generator
to sweep cleanly on a log scale from 1 KiB. The analytical runs use the
**congestion-unaware** backend — the model built for multi-dimensional
(hierarchical) topologies — so the *same* backend drives both fabrics. Collective
latency is the **max** `sys[i] finished` cycle across ranks (the collective
finishes when the slowest rank does).

Everything is reproducible from a single Docker image; the harness lives at
[github.com/kredd2506/Astro](https://github.com/kredd2506/Astro). The next post
gets into the first result: the two regimes, and where torus separates from
switch.
