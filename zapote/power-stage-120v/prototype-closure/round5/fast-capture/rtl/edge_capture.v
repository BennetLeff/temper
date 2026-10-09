`timescale 1ns/1ps
// Four coherent logic-input cycles. Absolute age uses unsigned modulo 2^32.
// Local acquisition/fall-age timers saturate; no stale low-bit timestamp aliases.
module edge_capture(input wire clk, input wire rst,
 input wire [3:0] logic_in, output reg valid, output reg fault,
 output reg [31:0] counter, output reg [31:0] epoch,
 output reg [511:0] measurements, output reg [15:0] sample_age);
 (* ASYNC_REG = "TRUE" *) reg [3:0] sync1, sync2;
 reg [3:0] prev, fall_seen;
 wire [3:0] rising = sync2 & ~prev;
 wire [3:0] falling = ~sync2 & prev;
 reg [12:0] fall_age[0:3];
 reg active;
 reg [31:0] origin;
 reg [12:0] ticks, first[0:3], widths[0:3], periods[0:3], gaps[0:3];
 reg [3:0] started, fell, done;
 reg [1:0] check_stage;
 reg [3:0] period_ok, width_ok, gap_ok, phase_ok, same_period;
 integer i;
 always @(posedge clk) begin
  if (rst) begin
   sync1<=0; sync2<=0; prev<=0; fall_seen<=0; valid<=0; fault<=0;
   counter<=0; epoch<=0; sample_age<=65535; measurements<=0; active<=0;
   origin<=0; ticks<=0; started<=0; fell<=0; done<=0; check_stage<=0;
   period_ok<=0; width_ok<=0; gap_ok<=0; phase_ok<=0; same_period<=0;
   for(i=0;i<4;i=i+1) begin
    fall_age[i]<=8191; first[i]<=0; widths[i]<=0; periods[i]<=0; gaps[i]<=0;
   end
  end else begin
   counter<=counter+1;
   if(sample_age!=65535) sample_age<=sample_age+1;
   sync1<=logic_in; sync2<=sync1; prev<=sync2;
   for(i=0;i<4;i=i+1) begin
    if(falling[i]) begin fall_age[i]<=0; fall_seen[i]<=1; end
    else if(fall_age[i]!=8191) fall_age[i]<=fall_age[i]+1;
   end
   if ((sync2[0] && sync2[1]) || (sync2[2] && sync2[3]) ||
       (active && check_stage==0 && (|(rising & started & ~done & ~fell)))) fault<=1;
   if(fault) begin valid<=0; active<=0; end
   else begin
    // Clear validity permanently at expiry, including across absolute counter wrap.
    if(valid && (sample_age > 39990)) valid<=0;
    if(!active && falling[1] && fall_seen==4'hf) begin
     active<=1; origin<=counter; ticks<=1;
     started<=rising; fell<=0; done<=0; check_stage<=0;
     for(i=0;i<4;i=i+1) begin
      first[i]<=0;
      gaps[i]<=(fall_age[i^1]==8191 ? 13'd8191 : fall_age[i^1]+13'd1);
     end
    end else if(active) begin
     ticks<=ticks+1;
     if(check_stage==1) begin
      // Separate registered checks keep comparisons out of the publish-enable path.
      for(i=0;i<4;i=i+1) begin
       period_ok[i]<=periods[i]>=1332 && periods[i]<=2286;
       width_ok[i]<=widths[i]!=0 && widths[i]<periods[i];
       gap_ok[i]<=gaps[i]!=0 && gaps[i]<(periods[i]>>2);
       phase_ok[i]<=first[i]<periods[0];
       same_period[i]<=periods[i]+13'd2>=periods[0] && periods[i]<=periods[0]+13'd2;
      end
      check_stage<=2;
     end else if(check_stage==2) begin
      if((&period_ok) && (&width_ok) && (&gap_ok) && (&phase_ok) && (&same_period)) begin
       for(i=0;i<4;i=i+1) begin
        measurements[511-i*32 -:32]<={19'b0,periods[i]};
        measurements[383-i*32 -:32]<={19'b0,widths[i]};
        measurements[255-i*32 -:32]<={19'b0,first[i]};
        measurements[127-i*32 -:32]<={19'b0,gaps[i]};
       end
       epoch<=origin; sample_age<= {3'b0,ticks}+16'd1; valid<=1;
      end else valid<=0;
      active<=0;
     end else begin
      if(done==4'hf) check_stage<=1;
      for(i=0;i<4;i=i+1) begin
      if(rising[i] && !done[i]) begin
       if(!started[i]) begin
        first[i]<=ticks;
        gaps[i]<=(fall_age[i^1]==8191 ? 13'd8191 : fall_age[i^1]+13'd1);
        started[i]<=1;
       end else begin
        periods[i]<=ticks-first[i]; done[i]<=1;
       end
      end
      if(falling[i] && started[i] && !fell[i]) begin
       widths[i]<=ticks-first[i]; fell[i]<=1;
      end
      end
     end
     if(ticks==7000) begin active<=0; valid<=0; end
    end
   end
  end
 end
endmodule
