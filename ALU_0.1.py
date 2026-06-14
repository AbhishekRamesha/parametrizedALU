from myhdl import *

t_Op = enum('ADD', 'SUB', 'OR', 'NOR', 'AND', 'NAND', 'XOR', 'XNOR', 'MUL', 'DIV')
t_State = enum('IDLE', 'CALC')

@block
def alu(data_in_1, data_in_2, carry_in, operation_result, carry_out,
        clock_signal, opcode, negative_flag, zero_flag, overflow_flag, width=8):

    full_mask = (1 << width) - 1

    # ── Internal signals for combinational operations ─────────────────────────
    comb_result   = Signal(intbv(0)[width:])
    comb_carry    = Signal(bool(0))
    comb_overflow = Signal(bool(0))

    # ── Internal signals for sequential operations ────────────────────────────
    seq_result    = Signal(intbv(0)[width:])
    seq_overflow  = Signal(bool(0))

    # ── Multi-cycle state signals ─────────────────────────────────────────────
    state        = Signal(t_State.IDLE)
    count        = Signal(intbv(0, min=0, max=width + 1))
    accumulate   = Signal(intbv(0)[width:])   # running sum for multiply
    multiplicand = Signal(intbv(0)[width:])   # current shifted copy of data_in_1
    multiplier   = Signal(intbv(0)[width:])   # remaining bits of data_in_2
    remainder    = Signal(intbv(0)[width:])   # working register for divide
    divisor      = Signal(intbv(0)[width:])   # latched copy of data_in_2

    # ── Combinational Single-Cycle Logic ──────────────────────────────────────
    @always_comb
    def comb_logic():
        # Default values to prevent latches
        comb_result.next   = 0
        comb_carry.next    = 0
        comb_overflow.next = 0

        # ADD
        if opcode == t_Op.ADD:
            total = data_in_1 + data_in_2 + carry_in
            comb_result.next = total & full_mask
            comb_carry.next  = (total >> width) & 1
            comb_overflow.next = (
                (data_in_1[width - 1] == data_in_2[width - 1]) and
                (bool((total >> (width - 1)) & 1) != bool(data_in_1[width - 1]))
            )

        # SUB
        elif opcode == t_Op.SUB:
            diff = (data_in_1 - data_in_2) & ((1 << (width + 1)) - 1)
            comb_result.next = diff & full_mask
            comb_carry.next  = (diff >> width) & 1    # borrow flag
            comb_overflow.next = (
                (data_in_1[width - 1] != data_in_2[width - 1]) and
                (bool((diff >> (width - 1)) & 1) != bool(data_in_1[width - 1]))
            )

        # Bitwise logic
        elif opcode == t_Op.OR:
            comb_result.next = (data_in_1 | data_in_2) & full_mask
        elif opcode == t_Op.NOR:
            comb_result.next = (~(data_in_1 | data_in_2)) & full_mask
        elif opcode == t_Op.AND:
            comb_result.next = (data_in_1 & data_in_2) & full_mask
        elif opcode == t_Op.NAND:
            comb_result.next = (~(data_in_1 & data_in_2)) & full_mask
        elif opcode == t_Op.XOR:
            comb_result.next = (data_in_1 ^ data_in_2) & full_mask
        elif opcode == t_Op.XNOR:
            comb_result.next = (~(data_in_1 ^ data_in_2)) & full_mask

    # ── Sequential Multi-Cycle Logic (MUL & DIV) ──────────────────────────────
    @always(clock_signal.posedge)
    def seq_logic():
        if state == t_State.IDLE:
            if opcode == t_Op.MUL:
                accumulate.next   = 0
                multiplicand.next = data_in_1
                multiplier.next   = data_in_2
                count.next        = 0
                seq_overflow.next = 0
                state.next        = t_State.CALC

            elif opcode == t_Op.DIV:
                if data_in_2 != 0:
                    remainder.next    = data_in_1
                    divisor.next      = data_in_2
                    count.next        = 0
                    seq_overflow.next = 0
                    state.next        = t_State.CALC
                else:
                    # Divide-by-zero
                    seq_result.next   = full_mask
                    seq_overflow.next = 1

        elif state == t_State.CALC:
            if opcode == t_Op.MUL:
                if count < width:
                    accumulate_val   = int(accumulate)
                    multiplicand_val = int(multiplicand)
                    multiplier_val   = int(multiplier)
                    partial          = accumulate_val
                    
                    if multiplier_val & 1:
                        partial = accumulate_val + multiplicand_val
                    
                    accumulate.next   = partial & full_mask
                    multiplicand.next = (multiplicand_val << 1) & full_mask
                    multiplier.next   = multiplier_val >> 1
                    count.next        = count + 1

                    if count == width - 1:
                        seq_result.next   = partial & full_mask
                        seq_overflow.next = 1 if (partial > full_mask) else 0
                        state.next        = t_State.IDLE

            elif opcode == t_Op.DIV:
                if count < width:
                    half = width // 2
                    remainder_val = int(remainder)
                    divisor_val   = int(divisor)

                    partial_r = (remainder_val >> half) & full_mask
                    quotient  = remainder_val & ((1 << half) - 1)

                    partial_r = ((partial_r << 1) | ((quotient >> (half - 1)) & 1)) & full_mask
                    q_bit = 0
                    if partial_r >= divisor_val:
                        partial_r -= divisor_val
                        q_bit = 1

                    remainder.next = (((partial_r & ((1 << half) - 1)) << half) |
                                      ((quotient << 1) & ((1 << half) - 1)) | q_bit) & full_mask
                    count.next = count + 1

                    if count == width - 1:
                        # MyHDL next assignment cannot be read immediately, use value we are setting
                        res = (((partial_r & ((1 << half) - 1)) << half) |
                               ((quotient << 1) & ((1 << half) - 1)) | q_bit) & full_mask
                        seq_result.next   = res & ((1 << half) - 1)
                        seq_overflow.next = 0
                        state.next        = t_State.IDLE
            else:
                state.next = t_State.IDLE

    # ── Output Multiplexer & Flags ────────────────────────────────────────────
    @always_comb
    def out_mux():
        # Select between combinational or sequential result based on opcode
        if opcode == t_Op.MUL or opcode == t_Op.DIV:
            operation_result.next = seq_result
            overflow_flag.next    = seq_overflow
            carry_out.next        = False
        else:
            operation_result.next = comb_result
            overflow_flag.next    = comb_overflow
            carry_out.next        = comb_carry

    @always_comb
    def flags():
        zero_flag.next     = (operation_result == 0)
        negative_flag.next = operation_result[width - 1]

    return comb_logic, seq_logic, out_mux, flags

# ─────────────────────────────────────────────────────────────────────────────
# Testbench
# ─────────────────────────────────────────────────────────────────────────────
import random

@block
def test_alu(width=4):

    data_in_1        = Signal(intbv(0)[width:])
    data_in_2        = Signal(intbv(0)[width:])
    operation_result = Signal(intbv(0)[width:])
    opcode           = Signal(t_Op.ADD)
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
        ops = [t_Op.ADD, t_Op.SUB, t_Op.OR, t_Op.NOR, t_Op.AND, t_Op.NAND, t_Op.XOR, t_Op.XNOR, t_Op.MUL, t_Op.DIV]

        header = (f"{'Op':>4} | {'A':>{width}} | {'B':>{width}} | "
                  f"{'Ci':>2} | {'Result':>{width}} | Co | N | Z | OV")
        print(header)
        print("-" * len(header))

        for i in range(10):
            a  = random.randrange(1, 2 ** width)
            b  = random.randrange(1, 2 ** width)
            ci = random.choice([0, 1])

            op = ops[i]
            opcode.next    = op
            data_in_1.next = a
            data_in_2.next = b
            carry_in.next  = ci

            yield clock_signal.posedge
            yield delay(1)

            # Wait enough clock edges for multi-cycle result to settle
            if op == t_Op.MUL or op == t_Op.DIV:
                for _ in range(width + 2):
                    yield clock_signal.posedge
                yield delay(1)

            print(f"{str(op):>4} | {int(data_in_1):>{width}} | "
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

    # Generate Verilog
    # Note: Enums are supported in MyHDL convert but we need to pass a signal initialized with an enum
    data_in_1        = Signal(intbv(0)[8:])
    data_in_2        = Signal(intbv(0)[8:])
    operation_result = Signal(intbv(0)[8:])
    opcode           = Signal(t_Op.ADD)
    carry_in         = Signal(bool(0))
    carry_out        = Signal(bool(0))
    clock_signal     = Signal(bool(1))
    negative_flag    = Signal(bool(0))
    zero_flag        = Signal(bool(0))
    overflow_flag    = Signal(bool(0))

    alu_inst = alu(data_in_1, data_in_2, carry_in, operation_result, carry_out,
                   clock_signal, opcode, negative_flag, zero_flag, overflow_flag, width=8)
    alu_inst.convert(hdl='Verilog')