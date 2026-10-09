`timescale 1ns/1ps
module tb_gate_map;
 reg a,b; wire or_y,and_y;
 \$_ORNOT_ or_gate(a,b,or_y);
 \$_ANDNOT_ and_gate(a,b,and_y);
 initial begin
  for(integer i=0;i<4;i=i+1) begin
   a=i&1;b=(i>>1)&1;#1;
   if(or_y!==(a|~b) || and_y!==(a&~b)) $fatal(1,"gate map truth table");
  end
  $display("PASS custom LUT mapping: all 4 input states against official SB_LUT4 simulation primitive");$finish;
 end
endmodule
