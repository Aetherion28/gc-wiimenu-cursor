# GameCube controller -> Wii Menu pointer hook, System Menu 4.3U (v513).
#
# Two call sites in the controller manager update (0x81337500) are redirected:
#   0x81337584  bl WPADProbe  ->  bl gc_probe
#   0x813375BC  bl KPADRead   ->  bl gc_kpad
#
# gc_probe: on channel 0, if no real remote is found (-1) and a GC pad is
#   plugged into any port, report "Wii Remote (core) connected" and set OVR.
#   PADRead says err -3 when the pad wasn't polled since the last read, so the
#   last good status (LAST) is reused for up to HOLD frames.
# gc_kpad: on channel 0 with OVR set, replace the KPADStatus with one built
#   from LAST: stick -> pointer, buttons -> Wii Remote buttons.
#
# {NAME} placeholders are filled in by tools/build.py. r31 = data block.
# "@section code" goes in the big cave, "@section code2" right after the data block.
# Labels used across sections are written as {label}.
# Lines between "@if NAME" and "@endif" are kept only when build flag NAME is on.
# Careful: addi/addis with rA = r0 means "li"/"lis", so r0 is never a base here.

@section code2
gc_probe:
    stwu r1, -0x20(r1)
    mflr r0
    stw r0, 0x24(r1)
    stw r31, 0x1c(r1)
    stw r30, 0x18(r1)
    stw r29, 0x14(r1)
    stw r28, 0x10(r1)
    mr r30, r3                  # chan
    mr r29, r4                  # u32 *type
    bl {WPADProbe}
    mr r28, r3                  # real result
    cmpwi r30, 0
    bne probe_out
    lis r31, {DATA_HA}
    addi r31, r31, {DATA_LO}
@if DEBUG
    lwz r3, {PCNT}(r31)         # debug: chan-0 probe calls
    addi r3, r3, 1
    stw r3, {PCNT}(r31)
@endif
    li r0, 0
    stw r0, {OVR}(r31)
    cmpwi r28, -1               # WPAD_ERR_NO_CONTROLLER
    bne probe_led               # a real remote is there (or busy): leave it alone
    addi r3, r31, {PADBUF}
    bl {PADRead}
    li r4, 0                    # PADReset every port that says "no controller",
    lis r5, 0x8000              # so pads plugged in later get detected (the SDK
    li r7, 4                    # expects the caller to do this every frame)
    mtctr r7
    addi r6, r31, {PADBUF}
rst_loop:
    lbz r7, 0xa(r6)
    extsb r7, r7
    cmpwi r7, -1                # PAD_ERR_NO_CONTROLLER
    bne rst_next
    or r4, r4, r5
rst_next:
    srwi r5, r5, 1
    addi r6, r6, 12
    bdnz rst_loop
    cmpwi r4, 0
    beq rst_done
    mr r3, r4
    bl {PADReset}
rst_done:
    li r5, 4                    # first port with err == 0
    mtctr r5
    addi r6, r31, {PADBUF}
port_loop:
    lbz r0, 0xa(r6)
    extsb. r0, r0
    beq port_ok
    addi r6, r6, 12
    bdnz port_loop
    lwz r7, {MISS}(r31)         # no fresh status this frame
    addi r7, r7, 1
    stw r7, {MISS}(r31)
    cmpwi r7, {HOLD}
    bgt probe_led               # gone for too long: unplugged
    lwz r7, {GOOD}(r31)
    cmpwi r7, 0
    beq probe_led               # never seen a pad yet
    b spoof
port_ok:
    li r7, 0
    stw r7, {MISS}(r31)
    li r7, 1
    stw r7, {GOOD}(r31)
    lwz r7, 0(r6)               # LAST = this port's 12-byte PADStatus
    stw r7, {LAST}(r31)
    lwz r7, 4(r6)
    stw r7, {LAST}+4(r31)
    lwz r7, 8(r6)
    stw r7, {LAST}+8(r31)
spoof:
    li r0, 1
    stw r0, {OVR}(r31)
    li r0, 0
    stw r0, 0(r29)              # *type = WPAD_DEV_CORE
    li r28, 0                   # WPAD_ERR_NONE
probe_led:
@if LED
# disc slot LED (HW_GPIOB_OUT bit 0x20): solid = override on, blinking = hook running without a pad
    lis r6, 0xcd00
    lwz r7, 0xc0(r6)
    rlwinm r7, r7, 0, 27, 25
    lwz r0, {OVR}(r31)
    cmpwi r0, 0
    bne led_on
    lwz r0, {PCNT}(r31)
    andi. r0, r0, 16
    beq led_set
led_on:
    ori r7, r7, 0x20
led_set:
    stw r7, 0xc0(r6)
@endif
probe_out:
    mr r3, r28
    lwz r28, 0x10(r1)
    lwz r29, 0x14(r1)
    lwz r30, 0x18(r1)
    lwz r31, 0x1c(r1)
    lwz r0, 0x24(r1)
    mtlr r0
    addi r1, r1, 0x20
    blr

@section code
gc_kpad:
    stwu r1, -0x20(r1)
    mflr r0
    stw r0, 0x24(r1)
    stw r31, 0x1c(r1)
    stw r30, 0x18(r1)
    stw r29, 0x14(r1)
    stw r28, 0x10(r1)
    mr r30, r3                  # chan
    mr r29, r4                  # KPADStatus *buf
    bl {KPADRead}
    mr r28, r3                  # real sample count
    cmpwi r30, 0
    bne kpad_out
    lis r31, {DATA_HA}
    addi r31, r31, {DATA_LO}
    lwz r0, {OVR}(r31)
    cmpwi r0, 0
    beq kpad_out

@if DEBUG
    lwz r3, {KCNT}(r31)         # debug: frames overridden
    addi r3, r3, 1
    stw r3, {KCNT}(r31)
@endif
    mr r3, r29                  # memset(buf, 0, 0x84)
    li r4, 0
    li r5, 0x84
    bl {memset}

# ---- buttons: GC bit i -> BTNTAB[i] ----
    lhz r3, {LAST}(r31)
    li r4, 0
    addi r5, r31, {BTNTAB}-2
    li r6, 13
    mtctr r6
btn_loop:
    lhzu r7, 2(r5)
    andi. r0, r3, 1
    beq btn_skip
    or r4, r4, r7
btn_skip:
    srwi r3, r3, 1
    bdnz btn_loop
    lwz r5, {PREV}(r31)         # r4 = now, r5 = prev
    andc r6, r4, r5             # trig
    andc r7, r5, r4             # release
    stw r4, {PREV}(r31)
    stw r6, 4(r29)
    stw r7, 8(r29)
# KPAD repeat bit (0x80000000): on press, after 30 frames, then every 6
    lwz r8, {RPT}(r31)
    li r9, 0
    cmpw r4, r5
    beq rpt_same
    li r8, 30
    cmpwi r6, 0
    beq rpt_done
    li r9, 1
    b rpt_done
rpt_same:
    cmpwi r4, 0
    beq rpt_done
    addic. r8, r8, -1
    bne rpt_done
    li r9, 1
    li r8, 6
rpt_done:
    stw r8, {RPT}(r31)
    cmpwi r9, 0
    beq no_rpt
    oris r4, r4, 0x8000
no_rpt:
    stw r4, 0(r29)

# ---- stick -> cursor ----
    lfs f1, {CX}(r31)
    lfs f2, {CY}(r31)
    fmr f3, f1
    fmr f4, f2
    lbz r3, {LAST}+2(r31)       # stick X
    extsb r3, r3
    bl {stick_delta}
    fadds f1, f1, f5
    lbz r3, {LAST}+3(r31)       # stick Y (up = +), pointer Y (up = -)
    extsb r3, r3
    neg r3, r3
    bl {stick_delta}
    fadds f2, f2, f5
    lfs f6, {LIMX}(r31)         # clamp x to [-LIMX, LIMX]
    fneg f8, f6
    fsubs f7, f1, f6
    fsel f1, f7, f6, f1
    fadds f7, f1, f6
    fsel f1, f7, f1, f8
    lfs f6, {LIMY}(r31)         # clamp y to [-LIMY, LIMY]
    fneg f8, f6
    fsubs f7, f2, f6
    fsel f2, f7, f6, f2
    fadds f7, f2, f6
    fsel f2, f7, f2, f8
    stfs f1, {CX}(r31)
    stfs f2, {CY}(r31)
    stfs f1, 0x20(r29)          # pos
    stfs f2, 0x24(r29)
    fsubs f3, f1, f3
    fsubs f4, f2, f4
    stfs f3, 0x28(r29)          # vec
    stfs f4, 0x2c(r29)
    fmuls f5, f3, f3
    fmadds f5, f4, f4, f5
    lfs f6, {ZERO}(r31)
    fcmpu cr0, f5, f6
    beq no_speed
    frsqrte f7, f5              # speed = s2 * rsqrt(s2), one Newton step
    lfs f8, {HALF}(r31)
    lfs f9, {THREEHALF}(r31)
    fmul f10, f7, f7
    fmul f10, f10, f5
    fnmsub f10, f10, f8, f9
    fmul f7, f7, f10
    fmul f7, f7, f5
    frsp f7, f7
    stfs f7, 0x30(r29)          # speed
no_speed:

# ---- fixed fields (values copied from a real remote at rest) ----
    lis r0, 0xbf80
    stw r0, 0x10(r29)           # acc.y = -1.0
    lis r0, 0x3f80
    stw r0, 0x18(r29)           # acc_value = 1.0
    stw r0, 0x34(r29)           # horizon.x = 1.0
    stw r0, 0x54(r29)           # acc_vertical.x = 1.0
    lis r0, 0x3ff9
    ori r0, r0, 0x3ae6
    stw r0, 0x48(r29)           # dist = 1.95
    li r0, 0x0202
    stw r0, 0x5c(r29)           # dev_type 0, wpad_err 0, dpd_valid 2, data_format 2
    li r28, 1                   # 1 sample
kpad_out:
    mr r3, r28
    lwz r28, 0x10(r1)
    lwz r29, 0x14(r1)
    lwz r30, 0x18(r1)
    lwz r31, 0x1c(r1)
    lwz r0, 0x24(r1)
    mtlr r0
    addi r1, r1, 0x20
    blr

@section code
# r3 = signed stick value -> f5 = cursor delta (quadratic past the deadzone).
# Leaf; keeps f1-f4. Needs r31 = data block.
stick_delta:
    srawi r4, r3, 31
    xor r5, r3, r4
    subf r5, r4, r5             # |s|  (not r0: addi with rA=r0 means "li")
    cmpwi r5, {DEADZONE}
    bge sd_go
    lfs f5, {ZERO}(r31)
    blr
sd_go:
    addi r5, r5, -{DEADZONE}
    mullw r5, r5, r5
    cmpwi r3, 0
    bge sd_pos
    neg r5, r5
sd_pos:
    xoris r5, r5, 0x8000        # int -> double via 0x43300000_80000000 trick
    stw r5, {TMP}+4(r31)
    lis r4, 0x4330
    stw r4, {TMP}(r31)
    lfd f5, {TMP}(r31)
    lfd f13, {MAGIC}(r31)
    fsub f5, f5, f13
    lfs f12, {SPEED}(r31)
    fmul f5, f5, f12
    frsp f5, f5
    blr
