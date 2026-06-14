module tb_alu;

reg [7:0] data_in_1;
reg [7:0] data_in_2;
reg carry_in;
wire [7:0] operation_result;
wire carry_out;
reg clock_signal;
reg [3:0] opcode;
wire negative_flag;
wire zero_flag;
wire overflow_flag;

initial begin
    $from_myhdl(
        data_in_1,
        data_in_2,
        carry_in,
        clock_signal,
        opcode
    );
    $to_myhdl(
        operation_result,
        carry_out,
        negative_flag,
        zero_flag,
        overflow_flag
    );
end

alu dut(
    data_in_1,
    data_in_2,
    carry_in,
    operation_result,
    carry_out,
    clock_signal,
    opcode,
    negative_flag,
    zero_flag,
    overflow_flag
);

endmodule
