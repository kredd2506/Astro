#!/usr/bin/env python3
"""Plot the ASTRA-sim sweep: latency-bound vs bandwidth-bound behaviour of
AllReduce/AllGather on torus vs switch, as a function of message size and node count.

Runs natively on the host (matplotlib/pandas). Reads results/<backend>.csv,
writes PNGs to results/plots/.
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
PLOTS = os.path.join(RES, "plots")
os.makedirs(PLOTS, exist_ok=True)

TOPO_STYLE = {
    "switch":  dict(color="#c0392b", marker="o", label="Switch (1 hop, shared BW)"),
    "torus2d": dict(color="#2471a3", marker="s", label="2-D Torus (multi-hop ring mesh)"),
}
COLL_TITLE = {"all_reduce": "AllReduce", "all_gather": "AllGather"}


def human_bytes(n):
    for u in ["B", "KB", "MB", "GB"]:
        if n < 1024 or u == "GB":
            return f"{int(n)}{u}" if u == "B" else f"{n/1:.0f}{u}" if n % 1 == 0 else f"{n}{u}"
        n /= 1024
    return f"{n}"


def size_label(n):
    units = [(1 << 30, "GB"), (1 << 20, "MB"), (1 << 10, "KB")]
    for v, u in units:
        if n >= v:
            return f"{n // v}{u}"
    return f"{n}B"


def load(backend="analytical"):
    df = pd.read_csv(os.path.join(RES, f"{backend}.csv"))
    # algorithmic (bus) bandwidth actually delivered = bytes moved / time
    df["eff_bw_GBps"] = df["size_bytes"] / (df["latency_ns"] * 1e-9) / 1e9
    df["latency_us"] = df["latency_ns"] / 1e3
    return df


# ---------------------------------------------------------------------------
def fig_latency_vs_size(df, nodes=16, backend="analytical"):
    """Headline: latency vs message size, torus vs switch, both collectives.
    Annotate the latency-bound (flat) and bandwidth-bound (slope-1) regimes."""
    colls = ["all_reduce", "all_gather"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.2), sharex=True, sharey=True)
    for ax, coll in zip(axes, colls):
        sub = df[(df.collective == coll) & (df.nodes == nodes)]
        for topo, st in TOPO_STYLE.items():
            d = sub[sub.topology == topo].sort_values("size_bytes")
            ax.loglog(d.size_bytes, d.latency_us, **st, lw=2, ms=6)
            # latency floor (small-message asymptote)
            floor = d.latency_us.iloc[0]
            ax.axhline(floor, color=st["color"], ls=":", lw=1, alpha=0.5)
            # crossover: first size where latency >= 2x floor
            over = d[d.latency_us >= 2 * floor]
            if len(over):
                xc = over.size_bytes.iloc[0]
                ax.axvline(xc, color=st["color"], ls="--", lw=1, alpha=0.45)
        ax.set_title(f"{COLL_TITLE[coll]}  ({nodes} NPUs)")
        ax.set_xlabel("Message size (bytes)")
        ax.grid(True, which="both", ls=":", alpha=0.4)
    axes[0].set_ylabel("Collective latency (µs)")
    # regime annotations on the first panel
    axes[0].text(0.04, 0.93, "latency-bound\n(flat: ~hops × link latency)",
                 transform=axes[0].transAxes, fontsize=9, va="top",
                 bbox=dict(boxstyle="round", fc="#fdf2e9", ec="#e67e22", alpha=0.9))
    axes[0].text(0.62, 0.30, "bandwidth-bound\n(slope 1: bytes / link BW)",
                 transform=axes[0].transAxes, fontsize=9, va="top",
                 bbox=dict(boxstyle="round", fc="#eaf2f8", ec="#2471a3", alpha=0.9))
    axes[1].legend(loc="upper left", fontsize=9)
    fig.suptitle(f"Latency-bound → bandwidth-bound transition vs message size "
                 f"({backend} backend)", fontsize=13, y=1.0)
    fig.tight_layout()
    p = os.path.join(PLOTS, f"{backend}_fig1_latency_vs_size_{nodes}npus.png")
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return p


def fig_effective_bw(df, nodes=16, backend="analytical"):
    """Effective (bus) bandwidth vs size: rises from ~0 (latency-bound) toward a
    topology-dependent roofline (bandwidth-bound saturation)."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.2), sharex=True, sharey=True)
    for ax, coll in zip(axes, ["all_reduce", "all_gather"]):
        sub = df[(df.collective == coll) & (df.nodes == nodes)]
        for topo, st in TOPO_STYLE.items():
            d = sub[sub.topology == topo].sort_values("size_bytes")
            ax.semilogx(d.size_bytes, d.eff_bw_GBps, **st, lw=2, ms=6)
            asy = d.eff_bw_GBps.iloc[-1]
            ax.axhline(asy, color=st["color"], ls=":", lw=1, alpha=0.5)
        ax.set_title(f"{COLL_TITLE[coll]}  ({nodes} NPUs)")
        ax.set_xlabel("Message size (bytes)")
        ax.grid(True, which="both", ls=":", alpha=0.4)
    axes[0].set_ylabel("Effective bus bandwidth (GB/s)")
    axes[1].legend(loc="upper left", fontsize=9)
    fig.suptitle("Effective bandwidth saturates toward the topology roofline as "
                 "messages grow", fontsize=13, y=1.0)
    fig.tight_layout()
    p = os.path.join(PLOTS, f"{backend}_fig2_effbw_vs_size_{nodes}npus.png")
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return p


def fig_scaling_vs_nodes(df, backend="analytical"):
    """Latency vs node count at a small (latency-bound) and large (bandwidth-bound)
    message size, for AllReduce. Shows how each regime scales with system size."""
    small = 1 << 12   # 4 KB
    large = 1 << 28   # 256 MB
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.2))
    for ax, size, regime in zip(axes, [small, large],
                                ["small message — latency-bound",
                                 "large message — bandwidth-bound"]):
        sub = df[(df.collective == "all_reduce") & (df.size_bytes == size)]
        for topo, st in TOPO_STYLE.items():
            d = sub[sub.topology == topo].sort_values("nodes")
            ax.loglog(d.nodes, d.latency_us, **st, lw=2, ms=7, base=2)
        ax.set_title(f"AllReduce, {size_label(size)}\n({regime})")
        ax.set_xlabel("NPU count")
        ax.grid(True, which="both", ls=":", alpha=0.4)
        ax.set_xticks(sorted(sub.nodes.unique()))
        ax.set_xticklabels(sorted(sub.nodes.unique()))
    axes[0].set_ylabel("Collective latency (µs)")
    axes[0].legend(loc="upper left", fontsize=9)
    fig.suptitle("Scaling with node count differs by regime and topology",
                 fontsize=13, y=1.0)
    fig.tight_layout()
    p = os.path.join(PLOTS, f"{backend}_fig3_scaling_vs_nodes.png")
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return p


def fig_speedup_heatmap(df, backend="analytical"):
    """Torus speedup over switch (switch_latency / torus_latency) across the full
    size x node grid, for AllReduce."""
    sub = df[df.collective == "all_reduce"]
    piv = sub.pivot_table(index="size_bytes", columns="nodes",
                          values="latency_ns", aggfunc="first")
    sw = sub[sub.topology == "switch"].pivot_table(index="size_bytes", columns="nodes", values="latency_ns")
    to = sub[sub.topology == "torus2d"].pivot_table(index="size_bytes", columns="nodes", values="latency_ns")
    ratio = sw / to
    fig, ax = plt.subplots(figsize=(7.5, 6))
    im = ax.imshow(ratio.values, aspect="auto", origin="lower", cmap="RdBu_r",
                   vmin=0.5, vmax=max(2.0, np.nanmax(ratio.values)))
    ax.set_xticks(range(len(ratio.columns)))
    ax.set_xticklabels(ratio.columns)
    ax.set_yticks(range(len(ratio.index)))
    ax.set_yticklabels([size_label(s) for s in ratio.index])
    ax.set_xlabel("NPU count")
    ax.set_ylabel("Message size")
    ax.set_title("AllReduce: Torus speedup over Switch\n(latency_switch / latency_torus)")
    for i in range(ratio.shape[0]):
        for j in range(ratio.shape[1]):
            v = ratio.values[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                    fontsize=8, color="black")
    fig.colorbar(im, ax=ax, label="speedup (×)")
    fig.tight_layout()
    p = os.path.join(PLOTS, f"{backend}_fig4_torus_speedup.png")
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return p


def fig_ns3_validation():
    """Overlay the ns-3 packet-level slice against the analytical model for the
    *same* 8-node switch and ring (1-D torus) fabrics. Validates that the regimes
    (latency floor, bandwidth ramp, shrinking switch/ring gap) survive congestion."""
    ns3 = pd.read_csv(os.path.join(RES, "ns3.csv"))
    an = pd.read_csv(os.path.join(RES, "analytical_ref8.csv"))
    for d in (ns3, an):
        d["latency_us"] = d["latency_ns"] / 1e3
    fab = {"switch": "#c0392b", "ring1d": "#2471a3"}
    fab_lbl = {"switch": "Switch", "ring1d": "Ring (1-D torus)"}

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.2))
    ax = axes[0]
    for topo, c in fab.items():
        a = an[an.topology == topo].sort_values("size_bytes")
        n = ns3[ns3.topology == topo].sort_values("size_bytes")
        ax.loglog(a.size_bytes, a.latency_us, color=c, ls="--", marker="o", ms=5,
                  lw=1.8, label=f"{fab_lbl[topo]} — analytical")
        ax.loglog(n.size_bytes, n.latency_us, color=c, ls="-", marker="s", ms=6,
                  lw=2.2, label=f"{fab_lbl[topo]} — ns-3 (packet-level)")
    ax.set_title("AllReduce, 8 NPUs — analytical vs ns-3")
    ax.set_xlabel("Message size (bytes)")
    ax.set_ylabel("Collective latency (µs)")
    ax.grid(True, which="both", ls=":", alpha=0.4)
    ax.legend(fontsize=8.5, loc="upper left")

    # right: switch/ring speedup vs size, both backends -> both shrink toward 1
    ax = axes[1]
    for name, d, ls, mk in [("analytical", an, "--", "o"), ("ns-3", ns3, "-", "s")]:
        sw = d[d.topology == "switch"].sort_values("size_bytes").set_index("size_bytes").latency_ns
        rg = d[d.topology == "ring1d"].sort_values("size_bytes").set_index("size_bytes").latency_ns
        ratio = (sw / rg)
        ax.semilogx(ratio.index, ratio.values, ls=ls, marker=mk, lw=2,
                    color="#6c3483", label=f"{name}")
    ax.axhline(1.0, color="grey", ls=":", lw=1)
    ax.set_title("Ring speedup over Switch shrinks with size\n(latency-bound → bandwidth-bound)")
    ax.set_xlabel("Message size (bytes)")
    ax.set_ylabel("switch latency / ring latency  (×)")
    ax.grid(True, which="both", ls=":", alpha=0.4)
    ax.legend(fontsize=9)
    fig.suptitle("ns-3 validation: packet-level simulation reproduces the analytical regimes",
                 fontsize=13, y=1.0)
    fig.tight_layout()
    p = os.path.join(PLOTS, "ns3_fig5_validation.png")
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return p


def main():
    df = load("analytical")
    made = [
        fig_latency_vs_size(df, nodes=16),
        fig_effective_bw(df, nodes=16),
        fig_scaling_vs_nodes(df),
        fig_speedup_heatmap(df),
    ]
    if os.path.exists(os.path.join(RES, "ns3.csv")):
        made.append(fig_ns3_validation())
    for p in made:
        print("wrote", p)


if __name__ == "__main__":
    main()
