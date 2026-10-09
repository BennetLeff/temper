 integer simulation_ticks=0, acquisition_origin=0, published_origin=0;
 integer build_origin=0, bank_origin=0, age_checks=0;
 always @(posedge clk) begin
  simulation_ticks<=simulation_ticks+1;
  if(reset_n && !dut.rst) begin
   if(!dut.capture.active && dut.capture.falling[1] && dut.capture.fall_seen==15)
    acquisition_origin<=simulation_ticks;
   if(dut.capture.active && dut.capture.check_stage==2 &&
      (&dut.capture.period_ok) && (&dut.capture.width_ok) &&
      (&dut.capture.gap_ok) && (&dut.capture.phase_ok) && (&dut.capture.same_period))
    published_origin<=acquisition_origin;
   if(!dut.link.building) build_origin<=published_origin;
   if(dut.link.building && dut.link.data_valid && dut.link.crc_index==87) bank_origin<=build_origin;
   if(dut.link.select && dut.link.bank_ready &&
      dut.link.bank_sequence==dut.link.packet_seq && dut.valid &&
      !dut.capture_fault && !dut.transport_fault && dut.link.bank_age<=39990) begin
    if(simulation_ticks-bank_origin>40000) $fatal(1,"age bound violated across pipeline");
    if(dut.link.bank_age<simulation_ticks-bank_origin) $fatal(1,"bank age underestimated");
    age_checks<=age_checks+1;
   end
  end
 end
