

# 1) Global power/ground pin connects (if available in your tree)
if {[info exists ::env(SCRIPTS_DIR)]} {
  set _gg "$::env(SCRIPTS_DIR)/openroad/common/set_global_connections.tcl"
  if {[file exists $_gg]} {
    source $_gg
    set_global_connections
  }
}

# 2) Ensure primary nets exist (defaults if envs missing)
if {![info exists ::env(VDD_NET)]} { set ::env(VDD_NET) vccd1 }
if {![info exists ::env(GND_NET)]} { set ::env(GND_NET) vssd1 }


set secondary {}
if {![catch {ord::get_db_block}]} {
  foreach n {vdda1 vdda2 vssa1 vssa2 vccd2 vssd2} {
    set db_net [[ord::get_db_block] findNet $n]
    if {$db_net ne "NULL"} { lappend secondary $n }
  }
}

# 3) Voltage domain

set_voltage_domain -name CORE -power $::env(VDD_NET) -ground $::env(GND_NET) \
  -secondary_power $secondary

# 4) Core PDN grid & ring

define_pdn_grid -name core -starts_with POWER -voltage_domains {CORE}



add_pdn_stripe -grid core -layer met1 -width 0.48 -offset 80.0 -followpins -starts_with POWER

# Minimal MET2: narrow width positioned near boundaries
add_pdn_stripe -grid core -layer met2 -width 6.0 -pitch 800.0 -offset 100.0 -starts_with POWER

# 5) Power distribution on upper metals
add_pdn_stripe -grid core -layer met3 -width 8.0 -pitch 180.0 -offset 20.0 -starts_with POWER
add_pdn_stripe -grid core -layer met4 -width 8.0 -pitch 180.0 -offset 20.0 -starts_with POWER 
add_pdn_stripe -grid core -layer met5 -width 8.0 -pitch 180.0 -offset 46.0 -starts_with POWER -extend_to_core_ring

# 6) Macro grid

define_pdn_grid -macro -default -name macro -starts_with POWER -halo {10.0 10.0} -voltage_domains {CORE}

# 7) Sequential layer connections

add_pdn_connect -grid core  -layers {met1 met2}
add_pdn_connect -grid core  -layers {met2 met3}
add_pdn_connect -grid core  -layers {met3 met4}
add_pdn_connect -grid core  -layers {met4 met5}
add_pdn_connect -grid macro -layers {met3 met4}