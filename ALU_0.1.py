from myhdl import *

@block
def alu(data_in_1, data_in_2, carry_in, operation_result, carry_out,
        clock_signal, opcode, negative_flag, zero_flag, overflow_flag, width=8):

    full_mask = (1 << width) - 1

    # ── multi-cycle state — all width bits wide ───────────────────────────────
    count        = Signal(intbv(0, min=0, max=width + 1))
    busy         = Signal(bool(0))
    accumulate   = Signal(intbv(0)[width:])   # running sum for multiply
    multiplicand = Signal(intbv(0)[width:])   # current shifted copy of data_in_1
    multiplier   = Signal(intbv(0)[width:])   # remaining bits of data_in_2
    remainder    = Signal(intbv(0)[width:])   # working register for divide
    divisor      = Signal(intbv(0)[width:])   # latched copy of data_in_2

    # ── combinational flags ───────────────────────────────────────────────────
    @always_comb
    def flags():
        zero_flag.next     = (operation_result == 0)
        negative_flag.next = operation_result[width - 1]   # MSB = sign bit

    # ── sequential datapath ───────────────────────────────────────────────────
    @always(clock_signal.posedge)
    def logic():

        # ── ADD (with carry) ──────────────────────────────────────────────────
        if opcode == 0:
            total = data_in_1 + data_in_2 + carry_in
            operation_result.next = total & full_mask
            carry_out.next        = (total >> width) & 1
            # Signed overflow: both inputs same sign, result sign differs.
            overflow_flag.next = (
                (data_in_1[width - 1] == data_in_2[width - 1]) and
                (bool((total >> (width - 1)) & 1) != bool(data_in_1[width - 1]))
            )

        # ── SUB ───────────────────────────────────────────────────────────────
        elif opcode == 1:
            diff = (data_in_1 - data_in_2) & ((1 << (width + 1)) - 1)
            operation_result.next = diff & full_mask
            carry_out.next        = (diff >> width) & 1    # borrow flag
            # Signed overflow: inputs differ in sign, result sign mismatches minuend.
            overflow_flag.next = (
                (data_in_1[width - 1] != data_in_2[width - 1]) and
                (bool((diff >> (width - 1)) & 1) != bool(data_in_1[width - 1]))
            )

        # ── Bitwise OR ────────────────────────────────────────────────────────
        elif opcode == 2:
            operation_result.next = (data_in_1 | data_in_2) & full_mask
            overflow_flag.next    = 0

        # ── Bitwise NOR ───────────────────────────────────────────────────────
        elif opcode == 3:
            operation_result.next = (~(data_in_1 | data_in_2)) & full_mask
            overflow_flag.next    = 0

        # ── Bitwise AND ───────────────────────────────────────────────────────
        elif opcode == 4:
            operation_result.next = (data_in_1 & data_in_2) & full_mask
            overflow_flag.next    = 0

        # ── Bitwise NAND ─────────────────────────────────────────────────────
        elif opcode == 5:
            operation_result.next = (~(data_in_1 & data_in_2)) & full_mask
            overflow_flag.next    = 0

        # ── Bitwise XOR ───────────────────────────────────────────────────────
        elif opcode == 6:
            operation_result.next = (data_in_1 ^ data_in_2) & full_mask
            overflow_flag.next    = 0

        # ── Bitwise XNOR ─────────────────────────────────────────────────────
        elif opcode == 7:
            operation_result.next = (~(data_in_1 ^ data_in_2)) & full_mask
            overflow_flag.next    = 0

        # ── Multiply (sequential shift-and-add, width-bit accumulator) ────────
        # accumulate holds only the low `width` bits at each step.
        # If adding multiplicand would push past full_mask, the high bits are
        # dropped and overflow_flag is raised on that final cycle.
        elif opcode == 8:
            if busy == 0:
                accumulate.next   = 0
                multiplicand.next = data_in_1
                multiplier.next   = data_in_2
                count.next        = 0
                busy.next         = 1
                overflow_flag.next = 0
            
            elif count < width:
                accumulate_val  = int(accumulate)
                multiplicand_val = int(multiplicand)
                multiplier_val = int(multiplier)
                partial = accumulate_val  # ← initialize before the if-block
                if multiplier_val & 1:
                 partial = accumulate_val + multiplicand_val
                accumulate.next = partial & full_mask
                multiplicand.next = (int(multiplicand) << 1) & full_mask
                multiplier.next   = int(multiplier) >> 1
                count.next        = count + 1
                if count == width - 1:
                    operation_result.next = partial & full_mask
                    overflow_flag.next    = 1 if (partial > full_mask) else 0
                    busy.next             = 0

        # ── Divide (sequential restoring, width-bit remainder) ────────────────
        # remainder and divisor are both width bits.  Each iteration shifts one
        # bit of the dividend in from the top of `remainder` and trial-subtracts
        # `divisor`; the quotient bit is accumulated in the low end of remainder.
        elif opcode == 9:
            if busy == 0:
                if data_in_2 != 0:
                    remainder.next     = data_in_1
                    divisor.next       = data_in_2
                    count.next         = 0
                    busy.next          = 1
                    overflow_flag.next = 0
                else:
                    # Divide-by-zero: return all-ones and flag it.
                    operation_result.next = full_mask
                    overflow_flag.next    = 1

            elif count < width:
                # Upper half = bits [width-1 : width//2], used as partial remainder.
                # We work entirely within width bits by using the top half as the
                # partial remainder and the bottom half as the accumulating quotient.
                half      = width // 2
                remainder_val=int(remainder)
                divisor_val=int(divisor)

                partial_r = (remainder_val >> half) & full_mask
                quotient  = remainder_val & ((1 << half) - 1)

                # Shift partial remainder left by 1, bring in next quotient bit slot.
                partial_r = ((partial_r << 1) | ((quotient >> (half - 1)) & 1)) & full_mask
                q_bit = 0
                if partial_r >= divisor_val:
                    partial_r -= divisor_val
                    q_bit = 1

                # Pack updated partial remainder back into top half, quotient into bottom.
                remainder.next = (((partial_r & ((1 << half) - 1)) << half) |
                                  ((quotient << 1) & ((1 << half) - 1)) | q_bit) & full_mask
                count.next = count + 1

                if count == width - 1:
                    operation_result.next = int(remainder) & ((1 << half) - 1)
                    overflow_flag.next    = 0
                    busy.next             = 0

    return flags, logic
width = 8
data_in_1        = Signal(intbv(0)[width:])
data_in_2        = Signal(intbv(0)[width:])
operation_result = Signal(intbv(0)[width:])
opcode           = Signal(intbv(0)[4:])
carry_in         = Signal(bool(0))
carry_out        = Signal(bool(0))
clock_signal     = Signal(bool(1))
negative_flag    = Signal(bool(0))
zero_flag        = Signal(bool(0))
overflow_flag    = Signal(bool(0))
# ─────────────────────────────────────────────────────────────────────────────
# Testbench
# ─────────────────────────────────────────────────────────────────────────────
import random

@block
def test_alu(width=4):

    data_in_1        = Signal(intbv(0)[width:])
    data_in_2        = Signal(intbv(0)[width:])
    operation_result = Signal(intbv(0)[width:])
    opcode           = Signal(intbv(0)[4:])
    carry_in         = Signal(bool(0))
    carry_out        = Signal(bool(0))
    clock_signal     = Signal(bool(1))
    negative_flag    = Signal(bool(0))
    zero_flag        = Signal(bool(0))
    overflow_flag    = Signal(bool(0))

    alu_inst = alu(data_in_1, data_in_2, carry_in, operation_result, carry_out,
                   clock_signal, opcode, negative_flag, zero_flag, overflow_flag,
                   width)

    @always(delay(5))
    def clkgen():
        clock_signal.next = not clock_signal

    @instance
    def stimulus():
        op_names = ["ADD", "SUB", "OR ", "NOR", "AND", "NAND","XOR", "XNOR",
                    "MUL", "DIV"]

        header = (f"{'Op':>4} | {'A':>{width}} | {'B':>{width}} | "
                  f"{'Ci':>2} | {'Result':>{width}} | Co | N | Z | OV")
        print(header)
        print("-" * len(header))

        for i in range(10):
            a  = random.randrange(1, 2 ** width)
            b  = random.randrange(1, 2 ** width)
            ci = random.choice([0, 1])

            opcode.next    = i
            data_in_1.next = a
            data_in_2.next = b
            carry_in.next  = ci

            yield clock_signal.posedge
            yield delay(1)

            # Multi-cycle ops: wait enough clock edges for the result to settle.
            if i in (8, 9):
                for _ in range(width + 2):
                    yield clock_signal.posedge
                yield delay(1)

            print(f"{op_names[i]:>4} | {int(data_in_1):>{width}} | "
                  f"{int(data_in_2):>{width}} | {int(carry_in):>2} | "
                  f"{int(operation_result):>{width}} | "
                  f" {int(carry_out)} |"
                  f" {int(negative_flag)} |"
                  f" {int(zero_flag)} |"
                  f"  {int(overflow_flag)}")

        raise StopSimulation()

    return alu_inst, clkgen, stimulus


if __name__ == "__main__":
    tb = test_alu(width=4)
    tb.config_sim(trace=True)
    tb.run_sim()

alu_inst = alu(data_in_1, data_in_2, carry_in, operation_result, carry_out,
               clock_signal, opcode, negative_flag, zero_flag, overflow_flag, width=8)
alu_inst.convert(hdl='Verilog')