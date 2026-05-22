`default_nettype none
module user_project_wrapper #(
    parameter BITS = 32
) (
`ifdef USE_POWER_PINS
    inout vdda1, inout vdda2,
    inout vssa1, inout vssa2,
    inout vccd1, inout vccd2,
    inout vssd1, inout vssd2,
`endif

    // Wishbone
    input         wb_clk_i,
    input         wb_rst_i,
    input         wbs_stb_i,
    input         wbs_cyc_i,
    input         wbs_we_i,
    input  [3:0]  wbs_sel_i,
    input  [31:0] wbs_dat_i,
    input  [31:0] wbs_adr_i,
    output        wbs_ack_o,
    output [31:0] wbs_dat_o,

    // Logic Analyzer
    input  [127:0] la_data_in,
    output [127:0] la_data_out,
    input  [127:0] la_oenb,

    // Digital IOs
    input  [`MPRJ_IO_PADS-1:0] io_in,
    output [`MPRJ_IO_PADS-1:0] io_out,
    output [`MPRJ_IO_PADS-1:0] io_oeb,

    // Analog IOs (analog_io[k] <-> GPIO pad k+7)
    inout  [`MPRJ_IO_PADS-10:0] analog_io,

    // Extra user clock
    input   user_clock2,

    // IRQs
    output [2:0] user_irq
);

    // -------------------------------------------------------------------------
    // Tie off unused outputs - using direct constant assignment pattern
    // from known-good tape-out wrapper. No (* keep *) attributes - let
    // synthesis handle constant outputs naturally.
    // -------------------------------------------------------------------------

    // Logic Analyzer: not used, drive low
    assign la_data_out = 128'b0;

    // IRQs: not used, drive low
    assign user_irq = 3'b0;

    // io_oeb: all high (input mode / Hi-Z) except bit [23] which is driven
    // low because that bit is the output for ScanOutCC
    assign io_oeb[`MPRJ_IO_PADS-1:24] = {(`MPRJ_IO_PADS-24){1'b1}};
    assign io_oeb[23]                 = 1'b0;
    assign io_oeb[22:0]               = {23{1'b1}};

    // io_out: drive low for all bits except bit [23] (ScanOutCC from mprj)
    assign io_out[`MPRJ_IO_PADS-1:24] = {(`MPRJ_IO_PADS-24){1'b0}};
    assign io_out[22:0]               = 23'b0;
    // io_out[23] is driven by mprj.ScanOutCC below

    // -------------------------------------------------------------------------
    // Instantiate the neuromorphic core
    // -------------------------------------------------------------------------
    nvm_neuron_core_256x64 mprj (
`ifdef USE_POWER_PINS
        .VDDC1 (vccd1),
        .VDDC2 (vccd2),
        .VDDA1 (vdda1),
        .VDDA2 (vdda2),
        .VSS   (vssd1),
`endif

        // Clocks / resets
        .user_clk (wb_clk_i),
        .user_rst (wb_rst_i),
        .wb_clk_i (wb_clk_i),
        .wb_rst_i (wb_rst_i),

        // Wishbone
        .wbs_stb_i (wbs_stb_i),
        .wbs_cyc_i (wbs_cyc_i),
        .wbs_we_i  (wbs_we_i),
        .wbs_sel_i (wbs_sel_i),
        .wbs_dat_i (wbs_dat_i),
        .wbs_adr_i (wbs_adr_i),
        .wbs_dat_o (wbs_dat_o),
        .wbs_ack_o (wbs_ack_o),

        // Scan/Test
        .ScanInCC  (io_in[35]),
        .ScanInDL  (io_in[22]),
        .ScanInDR  (io_in[21]),
        .TM        (io_in[36]),
        .ScanOutCC (io_out[23]),

        // Analog / bias pins
        .Iref          (analog_io[27]),
        .Vcc_read      (analog_io[26]),
        .Vcomp         (analog_io[25]),
        .Bias_comp2    (analog_io[24]),
        .Vcc_wl_read   (analog_io[19]),
        .Vcc_wl_set    (analog_io[23]),
        .Vbias         (analog_io[22]),
        .Vcc_wl_reset  (analog_io[21]),
        .Vcc_set       (analog_io[20]),
        .dc_bias       (analog_io[18])
    );

endmodule
`default_nettype wire