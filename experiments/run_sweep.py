#!/usr/bin/env python3
"""Sweep AllReduce / AllGather across torus vs switch topologies on the
ASTRA-sim analytical backend, over message size x node count.

Runs *inside* the astra-sim Docker container (paths are /app/...).
Writes one CSV row per (collective, topology, nodes, size) to results/analytical.csv.

Latency-bound vs bandwidth-bound is not configured here -- it *emerges* from the
size sweep: small messages are dominated by per-step link latency (flat region),
large messages by data volume / link bandwidth (linear region). The crossover and
its dependence on node count and topology is the whole point.
"""
import csv
import json
import os
import re
import subprocess
import sys

ASTRA = "/app/astra-sim"
# congestion-*unaware* is the analytical model that supports multi-dimensional
# (hierarchical) topologies; the congestion-aware binary is 1-D only. Using one
# backend for both topologies keeps the comparison apples-to-apples.
BIN = f"{ASTRA}/build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware"
REMOTE = f"{ASTRA}/examples/remote_memory/analytical/no_memory_expansion.json"
WORK = "/app/experiments/work"
RESULTS = "/app/experiments/results"

sys.path.insert(0, ASTRA)
from experiments.gen_workload import generate as gen_workload  # noqa: E402

# ---- sweep grid -------------------------------------------------------------
NODE_COUNTS = [4, 8, 16, 32, 64]
# 1 KiB .. 1 GiB on a log4 grid -> spans deep latency-bound to deep bandwidth-bound
SIZES = [1 << e for e in range(10, 31, 2)]
COLLECTIVES = ["all_reduce", "all_gather"]
TOPOLOGIES = ["switch", "torus2d"]

# Per-link physical parameters held identical across topologies so the only thing
# that changes is the *interconnect structure* (one-hop switch vs multi-hop ring mesh).
BW = 50.0    # GB/s per link
LAT = 500.0  # ns per link


def torus_factors(n):
    """Near-square 2-D factorisation (a <= b, a*b == n)."""
    a = int(n ** 0.5)
    while n % a != 0:
        a -= 1
    return a, n // a


def make_network(topo, n, path):
    if topo == "switch":
        cfg = {"topology": ["Switch"], "npus_count": [n],
               "bandwidth": [BW], "latency": [LAT]}
        dims = 1
    elif topo == "torus2d":
        a, b = torus_factors(n)
        cfg = {"topology": ["Ring", "Ring"], "npus_count": [a, b],
               "bandwidth": [BW, BW], "latency": [LAT, LAT]}
        dims = 2
    else:
        raise ValueError(topo)
    # astra-network-analytical reads YAML; emit it by hand (lists inline)
    with open(path, "w") as f:
        f.write(f"topology: [ {', '.join(cfg['topology'])} ]\n")
        f.write(f"npus_count: [ {', '.join(map(str, cfg['npus_count']))} ]\n")
        f.write(f"bandwidth: [ {', '.join(map(str, cfg['bandwidth']))} ]\n")
        f.write(f"latency: [ {', '.join(map(str, cfg['latency']))} ]\n")
    return dims


def make_system(dims, path):
    impl = ["ring"] * dims
    cfg = {
        "scheduling-policy": "LIFO",
        "endpoint-delay": 10,
        "active-chunks-per-dimension": 1,
        "preferred-dataset-splits": 4,
        "all-reduce-implementation": impl,
        "all-gather-implementation": impl,
        "reduce-scatter-implementation": impl,
        "all-to-all-implementation": impl,
        "collective-optimization": "localBWAware",
        "local-mem-bw": 1600,
        "boost-mode": 0,
    }
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)


FIN_RE = re.compile(r"sys\[\d+\] finished, (\d+) cycles")


def run_one(workload_prefix, system_cfg, network_cfg):
    out = subprocess.run(
        [BIN,
         f"--workload-configuration={workload_prefix}",
         f"--system-configuration={system_cfg}",
         f"--remote-memory-configuration={REMOTE}",
         f"--network-configuration={network_cfg}"],
        capture_output=True, text=True)
    cycles = [int(m) for m in FIN_RE.findall(out.stdout + out.stderr)]
    if not cycles:
        sys.stderr.write(out.stdout[-2000:] + out.stderr[-2000:])
        raise RuntimeError("no 'finished' line parsed")
    return max(cycles)  # collective completes when the slowest rank finishes


def main():
    os.makedirs(RESULTS, exist_ok=True)
    out_csv = os.path.join(RESULTS, "analytical.csv")
    rows = []
    total = len(COLLECTIVES) * len(TOPOLOGIES) * len(NODE_COUNTS) * len(SIZES)
    i = 0
    for coll in COLLECTIVES:
        for n in NODE_COUNTS:
            # workloads depend only on (collective, nodes, size); reuse across topologies
            wl_prefixes = {}
            for size in SIZES:
                wdir = f"{WORK}/wl/{coll}/{n}npus_{size}B"
                wl_prefixes[size] = gen_workload(coll, n, size, wdir)
            for topo in TOPOLOGIES:
                net = f"{WORK}/net_{topo}_{n}.yml"
                dims = make_network(topo, n, net)
                sysc = f"{WORK}/sys_{dims}d.json"
                make_system(dims, sysc)
                a, b = (torus_factors(n) if topo == "torus2d" else (n, 1))
                for size in SIZES:
                    lat = run_one(wl_prefixes[size], sysc, net)
                    rows.append({
                        "backend": "analytical",
                        "collective": coll,
                        "topology": topo,
                        "nodes": n,
                        "shape": f"{a}x{b}" if topo == "torus2d" else f"{n}",
                        "dims": dims,
                        "size_bytes": size,
                        "link_bw_GBps": BW,
                        "link_lat_ns": LAT,
                        "latency_ns": lat,
                    })
                    i += 1
                    print(f"[{i:3d}/{total}] {coll:11s} {topo:8s} N={n:3d} "
                          f"size={size:>10d}B -> {lat} ns", flush=True)
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {len(rows)} rows to {out_csv}")


if __name__ == "__main__":
    main()
