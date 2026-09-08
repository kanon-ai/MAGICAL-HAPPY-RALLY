# Only configures the dedicated process launched by emulator_host.mjs.
# -control starts with power off; startup scripts precede media initialization.
namespace eval alpine_launcher {
    proc select_video {remaining} {
        # Wait for the cartridge to enable V9990 display (R#8 bit 7).
        # Selecting earlier can be undone by the MSX BIOS startup screen.
        if {![catch {debug read {Sunrise GFX9000 regs} 8} control]} {
            if {$control & 0x80} {
                set ::videosource GFX9000
                return
            }
        }
        if {$remaining > 0} {
            after realtime 0.1 [list alpine_launcher::select_video [expr {$remaining - 1}]]
        } else {
            puts stderr "MAGICAL HAPPY RALLY: V9990 display did not become ready within 30 seconds."
        }
    }
}
after realtime 0.2 {
    set power on
    set renderer SDLGL-PP
    set scale_factor 3
    set pause off
    set speed 100
    alpine_launcher::select_video 300
}
