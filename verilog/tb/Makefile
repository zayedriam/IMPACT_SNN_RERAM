TOPLEVEL_LANG ?= verilog
SIM ?= icarus
TOPLEVEL := nvm_neuron_core_256x64
PWD=$(shell pwd)
COCOTB?=$(PWD)
MODULE = neuron_network_test_1IP

ifeq ($(TOPLEVEL_LANG),verilog)
    VERILOG_SOURCES = $(COCOTB)/nvm_neuron_core_256x64.v \
                      $(COCOTB)/nvm_core_decoder.v \
                      $(COCOTB)/nvm_neuron_block.v \
                      $(COCOTB)/nvm_synapse_matrix.v \
                      $(COCOTB)/nvm_neuron_spike_out.v \
                      $(COCOTB)/Neuromorphic_X1_Beh.v
    ifneq ($(filter $(SIM),riviera activehdl),)
        COMPILE_ARGS += -sv2k12
    endif
else
    $(error A valid value (verilog or vhdl) was not provided for TOPLEVEL_LANG=$(TOPLEVEL_LANG))
endif

include $(shell cocotb-config --makefiles)/Makefile.sim
