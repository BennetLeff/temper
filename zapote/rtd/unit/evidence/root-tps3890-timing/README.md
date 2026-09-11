# TPS389001 assertion-delay evidence

The retained official TI TPS3890 Rev A datasheet, page 5 section 7.6,
places 18 microseconds (3.3 V supply, CT open) in the NOM column. The
MAX column is blank. This was checked in both extracted text and the
rendered table retained here. The current official TI URL presents the
same revision.

The timing conditions include 5% SENSE overdrive and MR tied to VDD.
The typical delay versus overdrive curves do not establish a guaranteed
maximum. CT controls release delay; it does not provide an independent
maximum assertion bound.

A model may use the nominal delay with its conditions stated. It cannot
claim a guaranteed worst-case local-rail response from this table. Five
percent below the lowest qualified 3.006 V falling trip is about 2.856 V,
already below the ADC 3.0 V operating minimum; the nominal delay therefore
does not establish that shutdown precedes departure from valid ADC supply.

Required physical timing characterization remains NOT RUN. If guaranteed
maximum assertion timing is mandatory for design acceptance, this evidence
alone does not close that requirement.
