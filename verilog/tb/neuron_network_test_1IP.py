import re
import numpy as np
import cocotb
from cocotb.triggers import RisingEdge, ClockCycles, Timer
from cocotb.clock import Clock

PERIOD       = 20
RD_DLY       = 44
WR_DLY       = 200
MODE_PROGRAM = 0xC0000000
MODE_READ    = 0x40000000
N_SAMPLES    = 50

PHASE_ADDR   = 0x30004000

W2_FILE     = "W2_binary.npy"
LABELS_FILE = "label_classes.npy"

def load_classifier():
    try:
        W2     = np.load(W2_FILE).astype(np.int32)
        labels = np.load(LABELS_FILE, allow_pickle=True)
        print(f"  Classifier loaded: {W2.shape[0]} classes, W2 shape {W2.shape}")
        return W2, labels
    except FileNotFoundError:
        print(f"  NOTE: {W2_FILE} / {LABELS_FILE} not found.")
        return None, None

def decode_spikes(spike_int, W2, labels):
    spikes = np.array([(spike_int >> i) & 1 for i in range(64)], dtype=np.int32)
    return str(labels[(W2 @ spikes).argmax()])

def parse_expected_output(filename):
    result = {}; current = None
    with open(filename) as f:
        for line in f:
            line = line.strip()
            m = re.search(r'SAMPLE_START\s+(\d+)\s+label=(\S+)', line)
            if m:
                current = int(m.group(1))
                result[current] = {'label': m.group(2), 'data': []}
                continue
            if 'SAMPLE_END' in line: current = None; continue
            if current is not None and not line.startswith('//'):
                parts = line.split()
                if len(parts) >= 2:
                    result[current]['data'].append(
                        (int(parts[0], 16), int(parts[1], 16)))
    return result

def parse_weights_by_phase(filename):
    """Parse weights grouped by phase (0-63)"""
    phases = {}; current_phase = None
    with open(filename) as f:
        for line in f:
            ls = line.strip()
            if ls.startswith('//') or not ls: continue
            parts = ls.split()
            if len(parts) < 2: continue
            try:
                addr = int(parts[0], 16)
                data = int(parts[1], 16)
                if addr == PHASE_ADDR:
                    current_phase = data & 0x3F
                    if current_phase not in phases:
                        phases[current_phase] = []
                elif current_phase is not None:
                    phases[current_phase].append((addr, data))
            except: pass
    return phases

def parse_stimuli_and_ctrl(filename):
    """Parse stimuli by sample and phase"""
    stimuli = {}; ctrl = {}
    current_sample = None; current_phase = None
    with open(filename) as f:
        for line in f:
            raw = line; ls = line.strip()
            if 'Sample' in raw and re.search(r'Sample\s+\d+', raw):
                m = re.search(r'Sample\s+(\d+)', raw)
                if m:
                    current_sample = int(m.group(1))
                    stimuli[current_sample] = {}
                    ctrl[current_sample] = []
                    current_phase = None
                continue
            if ls.startswith('//') or not ls: continue
            if current_sample is None: continue
            parts = ls.split()
            if len(parts) < 2: continue
            try:
                addr = int(parts[0], 16)
                if parts[1].upper() == 'READ': continue
                data   = int(parts[1], 16)
                region = (addr >> 12) & 0xF
                if addr == PHASE_ADDR:
                    current_phase = data & 0x3F
                    if current_phase not in stimuli[current_sample]:
                        stimuli[current_sample][current_phase] = []
                elif region == 0 and current_phase is not None:
                    stimuli[current_sample][current_phase].append((addr, data))
                elif region in [2, 3]:
                    ctrl[current_sample].append((addr, data))
            except: pass
    return stimuli, ctrl

async def wishbone_write(dut, addr, data):
    dut.wbs_cyc_i.value = 1; dut.wbs_stb_i.value = 1
    dut.wbs_we_i.value  = 1; dut.wbs_sel_i.value = 0xF
    dut.wbs_adr_i.value = addr; dut.wbs_dat_i.value = data
    await RisingEdge(dut.wb_clk_i)
    dut.wbs_cyc_i.value = 0; dut.wbs_stb_i.value = 0
    dut.wbs_we_i.value  = 0; dut.wbs_sel_i.value = 0
    dut.wbs_dat_i.value = 0

async def wishbone_read(dut, addr):
    dut.wbs_cyc_i.value = 1; dut.wbs_stb_i.value = 1
    dut.wbs_we_i.value  = 0; dut.wbs_sel_i.value = 0xF
    dut.wbs_adr_i.value = addr; dut.wbs_dat_i.value = 0
    await RisingEdge(dut.wb_clk_i)
    await RisingEdge(dut.wb_clk_i)
    data = dut.wbs_dat_o.value.integer
    dut.wbs_cyc_i.value = 0; dut.wbs_stb_i.value = 0
    dut.wbs_sel_i.value = 0
    return data

async def nvm_write(dut, addr, data):
    await wishbone_write(dut, addr, (data & 0x3FFFFFFF) | MODE_PROGRAM)
    await ClockCycles(dut.wb_clk_i, WR_DLY + 5)

async def nvm_inference_read(dut, addr, data):
    await wishbone_write(dut, addr, (data & 0x3FFFFFFF) | MODE_READ)
    await ClockCycles(dut.wb_clk_i, RD_DLY + 2)
    dut.wbs_cyc_i.value = 1; dut.wbs_stb_i.value = 1
    dut.wbs_we_i.value  = 0; dut.wbs_sel_i.value = 0xF
    dut.wbs_adr_i.value = addr; dut.wbs_dat_i.value = data
    await RisingEdge(dut.wb_clk_i)
    await RisingEdge(dut.wb_clk_i)
    dut.wbs_cyc_i.value = 0; dut.wbs_stb_i.value = 0
    dut.wbs_we_i.value  = 0; dut.wbs_sel_i.value = 0
    dut.wbs_dat_i.value = 0

@cocotb.test(timeout_time=17000000000, timeout_unit='ns')
async def neuron_network_hex_test(dut):
    print("\n" + "=" * 70)
    print("SNN HARDWARE TEST — nvm_neuron_core_256x64 (1 IP version)")
    print("64 phases per sample: reprogram X1 + 512 inference reads per phase")
    print("=" * 70 + "\n")

    W2, class_labels = load_classifier()
    print()

    clock = Clock(dut.wb_clk_i, PERIOD, units="ns")
    cocotb.start_soon(clock.start())
    dut.wb_rst_i.value = 1
    for sig in [dut.wbs_cyc_i, dut.wbs_stb_i, dut.wbs_we_i,
                dut.wbs_sel_i, dut.wbs_adr_i, dut.wbs_dat_i]:
        sig.value = 0
    await RisingEdge(dut.wb_clk_i)
    await Timer(100, units="ns")
    dut.wb_rst_i.value = 0
    await RisingEdge(dut.wb_clk_i)

    weights_by_phase          = parse_weights_by_phase("weights_wishbone.hex")
    stimuli_by_phase, ctrl_by = parse_stimuli_and_ctrl("input_stimuli.hex")
    expected                  = parse_expected_output("expected_output.hex")

    print(f"Phases loaded   : {len(weights_by_phase)}")
    print(f"Weight entries  : {sum(len(v) for v in weights_by_phase.values())}")
    print(f"Samples loaded  : {len(stimuli_by_phase)}")
    sample_ids = sorted(stimuli_by_phase.keys())[:N_SAMPLES]
    print(f"Running {len(sample_ids)} samples (0 – {sample_ids[-1]})\n")

    if W2 is not None:
        print(f"  {'#':>4}  {'True Label':<14}  {'Predicted':<14}  "
              f"{'Cls':^5}  {'RTL':^4}")
        print(f"  {'-'*4}  {'-'*14}  {'-'*14}  {'-'*5}  {'-'*4}")
    else:
        print(f"  {'#':>4}  {'True Label':<14}  {'RTL':^4}")

    total_rtl = 0; total_cls = 0; results = []

    for sample in sample_ids:
        if sample not in expected: continue
        true_label = expected[sample]['label']

        # Reset neurons
        await ClockCycles(dut.wb_clk_i, 10)
        await wishbone_write(dut, 0x30002000, 0x00000000)
        await ClockCycles(dut.wb_clk_i, 10)

        # 64 phases: reprogram X1 + inference per neuron
        for phase in range(64):
            # Set phase/target neuron
            await wishbone_write(dut, PHASE_ADDR, phase)
            
            # Program weights for this phase
            for addr, data in weights_by_phase.get(phase, []):
                await nvm_write(dut, addr, data)
            
            # Read X1 in inference mode (triggers neuron accumulation)
            for addr, data in stimuli_by_phase.get(sample, {}).get(phase, []):
                await nvm_inference_read(dut, addr, data)

        # Execute control signals
        for addr, data in ctrl_by.get(sample, []):
            await ClockCycles(dut.wb_clk_i, 5)
            await wishbone_write(dut, addr, data)

        await ClockCycles(dut.wb_clk_i, 20)

        # Read spike outputs
        rtl_ok = True; spike_int = 0
        for addr, exp_val in expected[sample]['data']:
            act_val = await wishbone_read(dut, addr)
            if act_val != exp_val: rtl_ok = False
            if addr == 0x30001000: spike_int |= act_val
            elif addr == 0x30001004: spike_int |= (act_val << 32)

        if rtl_ok: total_rtl += 1

        if W2 is not None:
            pred = decode_spikes(spike_int, W2, class_labels)
            ok   = (pred == true_label)
            if ok: total_cls += 1
            print(f"  {sample:>4}   {true_label:<14}  {pred:<14}  "
                  f"{'✓' if ok else '✗':^5}  {'PASS' if rtl_ok else 'FAIL'}")
        else:
            print(f"  {sample:>4}   {true_label:<14}  "
                  f"{'PASS' if rtl_ok else 'FAIL'}")

        results.append((sample, true_label, rtl_ok))

    n = len(results)
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Samples tested         : {n}")
    print(f"  RTL correct (hw match) : {total_rtl}/{n}  "
          f"({100*total_rtl//n if n else 0}%)")
    if W2 is not None:
        print(f"  Gesture classification : {total_cls}/{n}  "
              f"({100*total_cls//n if n else 0}%)")
    print("=" * 70 + "\n")