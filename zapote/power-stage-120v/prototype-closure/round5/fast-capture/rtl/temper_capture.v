`timescale 1ns/1ps

module temper_capture(input wire clk80, input wire reset_n,
 input wire [3:0] logic_in, input wire cs_n, input wire sclk,
 output wire miso, output wire fault);
 // Asynchronous assertion and synchronous reset release. External reset must
 // remain asserted through configuration/power stabilization; no init assumption.
 (* ASYNC_REG = "TRUE" *) reg [2:0] reset_pipe;
 always @(posedge clk80 or negedge reset_n)
  if(!reset_n) reset_pipe<=0; else reset_pipe<={reset_pipe[1:0],1'b1};
 wire rst=~reset_pipe[2];
 wire valid, capture_fault, transport_fault;
 wire [31:0] counter, epoch;
 wire [511:0] measurements;
 wire [15:0] sample_age;
 edge_capture capture(clk80,rst,logic_in,valid,capture_fault,counter,epoch,measurements,sample_age);
 tfc1_spi link(clk80,rst,cs_n,sclk,miso,valid,capture_fault,counter,sample_age,measurements,transport_fault);
 assign fault=capture_fault | transport_fault;
endmodule
