# Architectural Restructuring of the MyHDL ALU

The previous iteration of the ALU was functional but suffered from several anti-patterns common when software developers first write hardware description code. Below is a detailed breakdown of the architectural changes made to bring the code up to professional digital design standards.

## 1. Magic Numbers vs. Enums
**The Problem:** The old design used raw integers (e.g., `opcode == 8`) to define operations. This is highly error-prone, hard to read, and provides no context to anyone reviewing the code. 
**The Solution:** We introduced the `t_Op` MyHDL `enum`. Instead of `8`, the code now explicitly checks for `t_Op.MUL`. This translates perfectly into Verilog `localparam` or `parameter` definitions during synthesis, keeping the hardware efficient while making the Python source code self-documenting.

## 2. Combinational vs. Sequential Logic Splitting
**The Problem:** The entire ALU was wrapped in a single `@always(clock_signal.posedge)` block. In hardware, this means **every single operation**—even a basic bitwise `AND`—requires a flip-flop register and takes a full clock cycle to complete. Standard ALUs compute basic arithmetic and bitwise logic combinationally (immediately), while only complex operations like Multiply/Divide require synchronous state machines.
**The Solution:** We split the logic into two distinct blocks:
- **`comb_logic` (`@always_comb`)**: Computes single-cycle operations (ADD, SUB, OR, XOR) instantly using standard combinational gates.
- **`seq_logic` (`@always(clock_signal.posedge)`)**: Operates a state machine exclusively for Multi-Cycle operations.

## 3. Explicit State Machines
**The Problem:** The Multi-Cycle operations previously relied on a raw boolean `busy` flag to determine if it should calculate or reset. This scales poorly for complex operations.
**The Solution:** We introduced a `t_State` enum (`IDLE` and `CALC`). This clearly defines the state machine's intent. When a `MUL` or `DIV` opcode is detected while in `IDLE`, the machine transitions to `CALC`, computes over N clock cycles, and returns to `IDLE`.

## 4. Output Multiplexing
**The Problem:** MyHDL (and Verilog) does not allow multiple blocks to drive the same signal (the "Multiple Drivers" error). Because we split the logic into combinational and sequential blocks, they could no longer both write directly to `operation_result`.
**The Solution:** We introduced an `out_mux` block. This block acts as a physical hardware Multiplexer. It checks the current `opcode`:
- If `MUL` or `DIV`, it routes the `seq_result` wire to the `operation_result` output.
- Otherwise, it routes the `comb_result` wire to the output.

## Summary
The resulting code compiles into much cleaner, standard Verilog. The synthesis tool can now infer simple combinational adders and logic gates for single-cycle operations, drastically reducing register usage and allowing the ALU to run at a significantly higher clock frequency.
