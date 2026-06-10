#!/usr/bin/env python3
"""ns-3 packet-level validation slice: AllReduce on an 8-node SWITCH vs an 8-node
RING (= 1-D torus), matched at 400 Gbps / 500 ns links, swept over message size.

Confirms the analytical regimes survive packet-level congestion/protocol modeling.
Runs inside the container from the ns-3 build/scratch dir. Writes results/ns3.csv.
"""
import csv
import os
import re
import subprocess
import sys

ASTRA = "/app/astra-sim"
NS3 = f"{ASTRA}/extern/network_backend/ns-3"
SCRATCH = f"{NS3}/scratch"
BIN_DIR = f"{NS3}/build/scratch"
BIN = "./ns3.42-AstraSimNetwork-default"
SYSTEM = f"{ASTRA}/examples/system/native_collectives/Ring_4chunks.json"
REMOTE = f"{ASTRA}/examples/remote_memory/analytical/no_memory_expansion.json"
LOGICAL = "/app/experiments/work/logical_8_1d.json"
RESULTS = "/app/experiments/results"

sys.path.insert(0, "/app")
from experiments.gen_workload import generate as gen_workload  # noqa: E402

NODES = 8
SIZES = [1 << e for e in range(14, 25, 2)]   # 16 KiB .. 16 MiB
TOPOS = {
    "switch": f"{SCRATCH}/config/config_switch8.txt",
    "ring1d": f"{SCRATCH}/config/config_ring8.txt",
}
BW = 50.0    # GB/s (= 400 Gbps)
LAT = 500.0  # ns  (= 0.0005 ms)

FIN_RE = re.compile(r"sys\[\d+\] finished, (\d+) cycles")


def run_one(workload_prefix, network_cfg):
    out = subprocess.run(
        [BIN,
         f"--workload-configuration={workload_prefix}",
         f"--system-configuration={SYSTEM}",
         f"--network-configuration={network_cfg}",
         f"--remote-memory-configuration={REMOTE}",
         f"--logical-topology-configuration={LOGICAL}",
         "--comm-group-configuration=empty"],
        capture_output=True, text=True, cwd=BIN_DIR)
    cycles = [int(m) for m in FIN_RE.findall(out.stdout + out.stderr)]
    if not cycles:
        sys.stderr.write((out.stdout + out.stderr)[-2000:])
        raise RuntimeError("no 'finished' line parsed")
    return max(cycles)


def main():
    os.makedirs(RESULTS, exist_ok=True)
    rows = []
    total = len(TOPOS) * len(SIZES)
    i = 0
    for size in SIZES:
        wl = gen_workload("all_reduce", NODES, size,
                          f"/app/experiments/work/ns3wl/{size}B")
        for topo, cfg in TOPOS.items():
            lat = run_one(wl, cfg)
            rows.append({
                "backend": "ns3",
                "collective": "all_reduce",
                "topology": topo,
                "nodes": NODES,
                "shape": "8" if topo == "ring1d" else "8",
                "dims": 1,
                "size_bytes": size,
                "link_bw_GBps": BW,
                "link_lat_ns": LAT,
                "latency_ns": lat,
            })
            i += 1
            print(f"[{i:2d}/{total}] ns3 all_reduce {topo:7s} N=8 "
                  f"size={size:>9d}B -> {lat} ns", flush=True)
    out_csv = os.path.join(RESULTS, "ns3.csv")
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {len(rows)} rows to {out_csv}")


if __name__ == "__main__":
    main()
