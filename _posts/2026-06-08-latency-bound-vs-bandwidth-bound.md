---
layout: post
title: "Latency-Bound vs Bandwidth-Bound: The Two Regimes"
date: 2026-06-08
tags: [astra-sim, allreduce, allgather, roofline, results]
---

In the [overview]({{ site.url }}/2026/06/07/modeling-collective-scaling-in-astra-sim.html)
I set up a sweep of `AllReduce` / `AllGather` across a switch and a 2-D torus,
holding per-link physics identical. Here's the first result: every collective
lives in one of two regimes, and the message size decides which.

### The two regimes, and where torus separates from switch

![Latency vs message size, AllReduce and AllGather, 16 NPUs]({{ site.url }}/assets/astra/analytical_fig1_latency_vs_size_16npus.png)

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

### The same data as effective bandwidth

![Effective bus bandwidth vs message size, 16 NPUs]({{ site.url }}/assets/astra/analytical_fig2_effbw_vs_size_16npus.png)

Plotting *delivered* bandwidth (bytes ÷ time) makes the transition tangible.
Small messages **waste** the fabric — almost all the time is latency, so
effective bandwidth is near zero. As messages grow, each curve climbs and
**saturates toward a topology-dependent roofline**. The torus's roofline is
higher; the switch saturates lower. The knee of this curve *is* the
latency→bandwidth crossover from the first figure.

The practical reading: there is a minimum message size below which you simply
cannot use your fabric efficiently, and that threshold is **higher on the
switch**. If your collectives are smaller than the knee, you're paying for
latency and buying more bandwidth won't help.

Next: what happens as you scale the **node count** — where the two regimes
diverge most, and a single picture of when topology actually matters.
