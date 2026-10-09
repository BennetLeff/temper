`timescale 1ns/1ps

// SPI mode 0, MSB first, 10 MHz maximum. CS setup >=200 ns; idle >=2 us.
// SPI inputs are oversampled in the same 80 MHz domain as edge_capture.
module tfc1_spi(input wire clk, input wire rst,
 input wire cs_n, input wire sclk, output wire miso,
 input wire valid, input wire capture_fault,
 input wire [31:0] counter, input wire [15:0] sample_age,
 input wire [511:0] measurements, output reg transport_fault);
 (* ASYNC_REG = "TRUE" *) reg [2:0] cs_sync, sck_sync;
 wire select = cs_sync[2] && !cs_sync[1];
 wire deselect = !cs_sync[2] && cs_sync[1];
 wire rise = !sck_sync[2] && sck_sync[1];
 wire fall = sck_sync[2] && !sck_sync[1];
 reg [31:0] packet_seq;
 reg [0:703] payload;
 reg [31:0] crc;
 reg [6:0] crc_index, fetch_index;
 reg building;
 reg [7:0] crc_data;
 reg data_valid;
 reg [735:0] bank, tx;
 reg bank_ready;
 reg [31:0] build_sequence, bank_sequence;
 reg [15:0] bank_age, build_age;
 reg build_valid;
 reg [9:0] bits_seen;
 reg selected;
 // Dedicated SPI bus: high impedance when physically deselected; deterministic
 // zero on a failed/not-ready transaction, rejected by receiver magic/CRC.
 assign miso = cs_n ? 1'bz : tx[735];
 function [31:0] crc_byte;
  input [31:0] old; input [7:0] data;
  reg [31:0] c; integer k;
  begin c=old ^ data;
   for(k=0;k<8;k=k+1) c=c[0] ? (c>>1)^32'hedb88320 : c>>1;
   crc_byte=c;
  end
 endfunction
 always @(posedge clk) begin
  if(rst) begin
   cs_sync<=3'b111; sck_sync<=0; packet_seq<=0; payload<=0; crc<=32'hffffffff;
   crc_index<=0; fetch_index<=1; building<=0; crc_data<=0; data_valid<=0; bank<=0; tx<=0; bank_ready<=0;
   bank_age<=65535; build_age<=65535; build_sequence<=0; bank_sequence<=0;
   build_valid<=0; bits_seen<=0; selected<=0; transport_fault<=0;
  end else begin
   cs_sync<={cs_sync[1:0],cs_n}; sck_sync<={sck_sync[1:0],sclk};
   // Saturating age propagation avoids wide timestamp subtract/compare on CS.
   if(build_age!=65535) build_age<=build_age+1;
   if(bank_age!=65535) bank_age<=bank_age+1;
   // Build packet in parallel with transmission; publication is atomic.
   if(!building) begin
    payload<={32'h54464331,8'h01,
      ((valid && !capture_fault && !transport_fault) ? 8'h0f : 8'h00),
      16'd92,packet_seq,32'd80000000,counter,32'd40000,measurements};
    build_age<=(sample_age==65535 ? 16'd65535 : sample_age+16'd1); build_sequence<=packet_seq;
    build_valid<=valid && !capture_fault && !transport_fault;
    crc<=32'hffffffff; crc_index<=0; fetch_index<=1; building<=1; data_valid<=0;
   end else if(!data_valid) begin
    crc_data<=payload[0 +:8]; data_valid<=1;
   end else begin
    crc<=crc_byte(crc,crc_data);
    if(crc_index==87) begin
     bank<={payload,~crc_byte(crc,crc_data)};
     bank_age<=(build_age==65535 ? 16'd65535 : build_age+16'd1); bank_sequence<=build_sequence;
     bank_ready<=build_valid; building<=0;
    end else begin
     crc_index<=crc_index+1;
     crc_data<=payload[fetch_index*8 +:8]; fetch_index<=fetch_index+1;
    end
   end
   if(select) begin
    selected<=1; bits_seen<=0;
    if(bank_ready && bank_sequence==packet_seq && valid && !capture_fault &&
       !transport_fault && bank_age<=39990) tx<=bank;
    else tx<=0;
   end else if(selected && !cs_sync[1]) begin
    if(rise) begin
     if(bits_seen<736) begin
      bits_seen<=bits_seen+1;
      if(bits_seen==735) begin
       packet_seq<=packet_seq+1; building<=0; bank_ready<=0;
      end
     end else transport_fault<=1;
    end
    if(fall) tx<={tx[734:0],1'b0};
   end
   if(deselect) begin
    selected<=0;
    if(bits_seen!=736) transport_fault<=1;
   end
  end
 end
endmodule
