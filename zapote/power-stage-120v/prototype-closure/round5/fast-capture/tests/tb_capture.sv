`timescale 1ns/1ps
module tb_capture;
 reg clock_enable=1;
 reg clk=0, reset_n=0, cs_n=1, sclk=0;
 wire miso, fault;
 reg [3:0] logic_in=0;
 reg pwm_enable=1;
 integer tick=0, phase=400, period=1600, dead=32;
 integer i, j, fd, frames=0, spi_half=50;
 reg save_vectors=1;
 reg [735:0] packet;
 temper_capture dut(clk,reset_n,logic_in,cs_n,sclk,miso,fault);
 always #6.25 if(clock_enable) clk=~clk;
 // Pin changes halfway between capture clocks; channel skew tested separately.
 always @(negedge clk) begin
  tick=(tick+1)%period;
  if(pwm_enable) begin
   logic_in[0]=((tick+period-dead)%period < period/2-dead);
   logic_in[1]=((tick+period-(period/2+dead))%period < period/2-dead);
   logic_in[2]=((tick+2*period-((phase+dead)%period))%period < period/2-dead);
   logic_in[3]=((tick+2*period-((phase+period/2+dead)%period))%period < period/2-dead);
  end else logic_in=0;
 end
 function [31:0] word;
  input [735:0] p; input integer byte_offset;
  word=p[735-byte_offset*8 -:32];
 endfunction
 function [31:0] crc88;
  input [735:0] p;
  reg [31:0] c; integer a,b;
  begin c=32'hffffffff;
   for(a=0;a<88;a=a+1) begin
    c=c ^ p[735-a*8 -:8];
    for(b=0;b<8;b=b+1) c=c[0] ? (c>>1)^32'hedb88320 : c>>1;
   end
   crc88=~c;
  end
 endfunction
 `include "age_monitor.inc"
 task read_packet;
  input integer phase_delay;
  begin
   #(phase_delay); cs_n=0; #200;
   for(j=0;j<736;j=j+1) begin
    sclk=1; #1; packet[735-j]=miso; #(spi_half-1); sclk=0; #(spi_half);
   end
   cs_n=1; #2000;
  end
 endtask
 task expect_valid;
  input integer expected_phase;
  begin
   if(word(packet,0)!==32'h54464331 || packet[695 -:8]!==8'h0f ||
      word(packet,88)!==crc88(packet)) $fatal(1,"bad valid frame");
   for(i=0;i<4;i=i+1) begin
    if(word(packet,24+4*i)!=period || word(packet,40+4*i)!=period/2-dead ||
       word(packet,72+4*i)!=dead) $fatal(1,"measurement mismatch channel %d",i);
   end
   if(word(packet,56)!=dead || word(packet,60)!=period/2+dead ||
      word(packet,64)!=(expected_phase+dead)%period ||
      word(packet,68)!=(expected_phase+period/2+dead)%period)
     $fatal(1,"phase mismatch %d %d %d %d",word(packet,56),word(packet,60),word(packet,64),word(packet,68));
   if(save_vectors) begin $fwrite(fd,"%0184h\n",packet); frames=frames+1; end
  end
 endtask
 task reset_device;
  begin cs_n=1; sclk=0; reset_n=0; #100; reset_n=1; #2000; end
 endtask
 initial begin
  fd=$fopen("frames.hex","w");
  reset_device;
  read_packet(0); if(word(packet,0)==32'h54464331) $fatal(1,"startup accepted");
  // Startup read consumes seq0, independent C receiver starts at first valid seq.
  #100000; read_packet(0); expect_valid(400);
  // Sweep all relative 80 MHz/SPI phase positions with 200ns CS setup.
  for(integer p=0;p<13;p=p+1) begin #170000; read_packet(p); expect_valid(400); end
  // Endpoints and near-wrap edge (BL rises one tick before AH).
  phase=0; #150000; read_packet(0); expect_valid(0);
  phase=800; #150000; read_packet(0); expect_valid(800);
  phase=799; #150000; read_packet(0); expect_valid(799);
  // Counter rollover must preserve timestamps and measured intervals.
  @(negedge clk); dut.capture.counter=32'hfffff000;
  #150000; read_packet(0); expect_valid(799);
  // Physical-interface target is 5 MHz: sweep phase offsets and both frequency limits.
  save_vectors=0; spi_half=100;
  for(integer p=0;p<13;p=p+1) begin #100000; read_packet(p); expect_valid(799); end
  phase=768; #150000; read_packet(0); expect_valid(768);
  period=1334; phase=333; #150000; read_packet(0); expect_valid(333);
  period=2284; phase=571; #150000; read_packet(0); expect_valid(571);
  period=1600; phase=799; #150000;
  // Sequence rollover is accepted unsigned; not proof of reset discrimination.
  @(negedge clk); dut.link.packet_seq=32'hffffffff;
  #4000; read_packet(0);
  if(word(packet,8)!==32'hffffffff || word(packet,88)!==crc88(packet)) $fatal(1,"packet_seq max");
  #100000; read_packet(0);
  if(word(packet,8)!==0 || word(packet,88)!==crc88(packet)) $fatal(1,"packet_seq wrap");
  // Stopped inputs cannot make a cached waveform fresh.
  pwm_enable=0; #600000; read_packet(0);
  if(word(packet,0)==32'h54464331) $fatal(1,"stale accepted");
  // No stale validity resurrection after common counter wraps.
  @(negedge clk); dut.capture.counter=dut.capture.epoch+10;
  #4000; read_packet(0); if(word(packet,0)==32'h54464331) $fatal(1,"stale wrap accepted");
  // Aborted SPI permanently invalidates subsequent packets until external reset.
  pwm_enable=1; reset_device; #150000;
  cs_n=0; #200; repeat(10) begin sclk=1; #50; sclk=0; #50; end
  cs_n=1; #5000; read_packet(0);
  if(!fault || word(packet,0)==32'h54464331) $fatal(1,"abort not latched");
  // Overlap is latched, independent of previously published valid bank.
  reset_device; #150000;
  force logic_in=4'b0011; #100; release logic_in; #5000; read_packet(0);
  if(!fault || word(packet,0)==32'h54464331) $fatal(1,"overlap not latched");
  // Out-of-range and acquisition-timer overflow must never alias into valid cycles.
  reset_device; period=3000; phase=750; #300000; read_packet(0);
  if(word(packet,0)==32'h54464331) $fatal(1,"slow period accepted");
  period=1000; phase=250; #200000; read_packet(0);
  if(word(packet,0)==32'h54464331) $fatal(1,"fast period accepted");
  period=9000; phase=2250; #700000; read_packet(0);
  if(word(packet,0)==32'h54464331) $fatal(1,"timer overflow accepted");
  period=1600; phase=400; reset_device; #150000;
  // Freeze one packet while incoming waveform changes during transmission.
  fork
   read_packet(0);
   begin #20000; phase=0; end
  join
  expect_valid(400);
  reset_device; #150000;
  // An extra737th clock edge invalidates all subsequent transactions.
  cs_n=0; #200; repeat(737) begin sclk=1; #100; sclk=0; #100; end
  cs_n=1; #5000; read_packet(0);
  if(!fault || word(packet,0)==32'h54464331) $fatal(1,"overlong SPI accepted");
  reset_device; #150000; @(negedge clk); clock_enable=0;
  read_packet(0); if(word(packet,0)==32'h54464331) $fatal(1,"stopped clock accepted");
  clock_enable=1; reset_device;
  if(age_checks<30) $fatal(1,"age monitor coverage");
  $fclose(fd); $display("PASS RTL: %0d receiver vectors; %0d independent age checks; SPI5MHz/10MHz phase sweeps; period bounds/overflow; frozen packets; phase endpoints/near-wrap; counter/sequence wrap; startup/stale/abort/overlong/overlap/clock-stop",frames,age_checks);
  $finish;
 end
 initial begin #50000000; $fatal(1,"timeout"); end
endmodule
