#!/usr/bin/env python3
import argparse
import re

from riscv_trace_csv import RiscvInstructionTraceEntry, RiscvInstructionTraceCsv

# =============================================================================

INSTR_RE = re.compile(r"^\s*(?P<cyc>[0-9]+)\s+:\s+#(?P<inst>[0-9]+)\s+0\s+"
                      r"(?P<pc>[0-9a-f]+)\s+(?P<opc>[0-9a-f]+)\s+"
                      r"((?P<reg>[^=;]+)=(?P<val>[0-9a-f]+))?"
                      r"\s+;\s+(?P<mnemonic>.*)")

NB_RE    = re.compile(r"^\s*(?P<cyc>[0-9]+)\s+:\s+"
                      r"(?P<reg>[^=;]+)=(?P<val>[0-9a-f]+)"
                      r"\s+;\s+(?P<mnemonic>(nbL|nbD))")

# =============================================================================

def parse_log(file_name):
    """
    Parses VeeR-EL2 execution log generated by HDL simulation.

    The core is in-order however, due to pipelined implementation certain
    instructions may have an effect in different clock cycle than they are
    executed. The testbench trace handes this by emitting special "nbL" and
    "nbD" entries which need to be correlated with the actual instruction.

    Most of the logic of this parser does exactly that. Every trace entry is
    put into a temporary queue. Whenever a "nbL"/"nbD" is encountered, the
    queue is searched for a matching counterpart. This happens in the opposite
    way as well eg. when a "div" is encountered the queue is searched for "nbD"
    Once an entry is found, relevant data is filled in.

    Entires are poped of the queue only when they contain all the information
    for the complete trace.
    """

    # Read the log
    with open(file_name, "r") as fp:
        lines = fp.readlines()

    data  = []
    queue = []

    for line in lines:
        line  = line.strip()

        # Instruction
        match = INSTR_RE.match(line)
        if match is not None:
            groups = match.groupdict()

            gpr = None
            if groups["reg"] and groups["val"]:
                gpr = ("{}:{}".format(groups["reg"], groups["val"]))

            fields   = groups["mnemonic"].split()
            mnemonic = fields[0]
            operands = fields[1].split(",") if len(fields) > 1 else []

            entry = None

            # Delayed effect, search the queue
            if gpr is None and mnemonic in ["lw", "div", "divu", "rem", "remu"]:
                for ent in reversed(queue):

                    if (ent.operand == "nbL" and mnemonic in ["lw"]) or \
                       (ent.operand == "nbD" and mnemonic in ["div", "divu", "rem", "remu"]):

                        assert len(operands), line
                        assert len(ent.gpr),  ent.get_trace_string()

                        reg, val = ent.gpr[0].split(":") # FIXME: Assuming single GPR
                        if reg == operands[0]:
                            entry = ent
                            break

            # Enqueue or not
            enqueue = entry is None and (gpr is not None or mnemonic in \
                                         ["div", "divu", "rem", "remu", "lw"])

            # Entry not found in the queue, create it
            if not entry:
                entry = RiscvInstructionTraceEntry()

            # Fill data
            entry.pc        = groups["pc"]
            entry.binary    = groups["opc"]
            entry.operand   = groups["mnemonic"]
            entry.mode      = "0" # TODO

            # Append GPR if any
            if gpr:
                entry.gpr.append(gpr)

            # Enqueue
            if enqueue:
                queue.append(entry)

        # nbL / nbD
        match = NB_RE.match(line)
        if match is not None:
            groups = match.groupdict()

            assert groups["reg"] and groups["val"], line
            gpr = ("{}:{}".format(groups["reg"], groups["val"]))

            # Find an existing nbL/nbD entry in the queue. Match destination GPR
            for entry in reversed(queue):

                fields   = entry.operand.split()
                mnemonic = fields[0]
                operands = fields[1].split(",") if len(fields) > 1 else []

                if (groups["mnemonic"] == "nbL" and mnemonic in ["lw"]) or \
                   (groups["mnemonic"] == "nbD" and mnemonic in ["div", "divu", "rem", "remu"]):
                    assert len(operands), entry
                    if groups["reg"] == operands[0]:
                        entry.gpr.append(gpr)
                        break

            # Add a new entry
            else:
                entry = RiscvInstructionTraceEntry()
                entry.operand = groups["mnemonic"]
                entry.gpr.append(gpr)

                queue.append(entry)

        # Dequeue entries that have all they need. Stop at the first one which
        # is missing something.
        while len(queue):
            entry = queue[0]

            if not entry.pc or not entry.gpr:
                break

            # Pop
            data.append(entry)
            queue = queue[1:]

        # Safeguard
        if len(queue) >= 10:
            print("ERROR: Malformed trace, the queue grew too much")
            for entry in reversed(queue):
                print("", entry.get_trace_string())
            assert False

    return data


def write_csv(file_name, data):
    """
    Writes the trace to CSV
    """

    with open(file_name, "w") as fp:

        writer = RiscvInstructionTraceCsv(fp)
        writer.start_new_trace()

        for entry in data:
            writer.write_trace_entry(entry)

# =============================================================================


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--log",
        type=str,
        required=True,
        help="HDL simulation trace log"
    )
    parser.add_argument(
        "--csv",
        type=str,
        required=True,
        help="Output CSV file"
    )

    args = parser.parse_args()

    # Parse log
    data = parse_log(args.log)

    # Write CSV
    write_csv(args.csv, data)

if __name__ == "__main__":
    main()
