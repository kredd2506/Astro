#!/usr/bin/env python3
"""Generate synthetic Chakra ET workloads for a single collective.

Unlike astra-sim's stock generators (which take --coll-size in integer MB and so
cannot reach the small-message *latency-bound* regime), this one takes the size
in **bytes**, letting us sweep from 1 KiB to 1 GiB on a clean log scale.

Run with PYTHONPATH=<astra-sim root> so the chakra protobuf schema is importable.
"""
import argparse
import os

from extern.graph_frontend.chakra.schema.protobuf.et_def_pb2 import (
    GlobalMetadata,
    COMM_COLL_NODE,
    ALL_REDUCE,
    ALL_GATHER,
    REDUCE_SCATTER,
    ALL_TO_ALL,
)
from extern.graph_frontend.chakra.schema.protobuf.et_def_pb2 import AttributeProto as ChakraAttr
from extern.graph_frontend.chakra.schema.protobuf.et_def_pb2 import Node as ChakraNode
from extern.graph_frontend.chakra.src.third_party.utils.protolib import encodeMessage as encode_message

COMM_TYPES = {
    "all_reduce": ALL_REDUCE,
    "all_gather": ALL_GATHER,
    "reduce_scatter": REDUCE_SCATTER,
    "all_to_all": ALL_TO_ALL,
}


def generate(coll_name: str, npus_count: int, coll_size_bytes: int, out_dir: str) -> str:
    """Write one single-node ET per NPU describing a single collective op.

    Returns the workload prefix path that astra-sim's --workload-configuration expects
    (the per-rank file is "<prefix>.<rank>.et").
    """
    comm_type = COMM_TYPES[coll_name]
    os.makedirs(out_dir, exist_ok=True)
    prefix = os.path.join(out_dir, coll_name)

    for npu in range(npus_count):
        with open(f"{prefix}.{npu}.et", "wb") as et:
            encode_message(et, GlobalMetadata(version="0.0.4"))
            node = ChakraNode()
            node.id = 0
            node.name = f"{coll_name}_{npus_count}npus_{coll_size_bytes}B"
            node.type = COMM_COLL_NODE
            node.attr.append(ChakraAttr(name="is_cpu_op", bool_val=False))
            node.attr.append(ChakraAttr(name="comm_type", int64_val=comm_type))
            node.attr.append(ChakraAttr(name="comm_size", int64_val=coll_size_bytes))
            encode_message(et, node)
    return prefix


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--collective", required=True, choices=list(COMM_TYPES))
    p.add_argument("--npus-count", type=int, required=True)
    p.add_argument("--coll-size-bytes", type=int, required=True)
    p.add_argument("--out-dir", default="./")
    a = p.parse_args()
    assert a.npus_count > 0 and a.coll_size_bytes > 0
    prefix = generate(a.collective, a.npus_count, a.coll_size_bytes, a.out_dir)
    print(prefix)


if __name__ == "__main__":
    main()
