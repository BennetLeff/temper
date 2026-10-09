`timescale 1ns/1ps

// Yosys 0.69 -noabc leaves these two combinational internal gates unmapped.
// LUT index = I0 + 2*I1; truth tables ORNOT=[1,1,0,1], ANDNOT=[0,1,0,0].
module \$_ORNOT_ (input A, B, output Y);
 SB_LUT4 #(.LUT_INIT(16'hbbbb)) _TECHMAP_REPLACE_ (.I0(A),.I1(B),.I2(1'b0),.I3(1'b0),.O(Y));
endmodule
module \$_ANDNOT_ (input A, B, output Y);
 SB_LUT4 #(.LUT_INIT(16'h2222)) _TECHMAP_REPLACE_ (.I0(A),.I1(B),.I2(1'b0),.I3(1'b0),.O(Y));
endmodule
