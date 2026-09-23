; BIRD HUNT: three sequential birds, five shots per round and fixed miss flashes.
; Sprite 0 = cursor, 1 = bird, 2 = miss patch; sprite 3 remains hidden.
; Philips Videopac G7000 / Magnavox Odyssey2, Intel 8048 + 8244/8245 VDC.
;
; Build: make (ASL assembler and p2bin required)
;
; MB0 holds core routines; HUD/extended loop use MB1 with explicit bank returns.
; ASL can insert SEL MB1 before CALL, but RET does not restore that latch.
; BIOS IRQs use RB0; game code uses RB1 and RAM 20h-3bh.
	cpu 8048
	include "include/g7000.h"

cursor_x equ 020h
cursor_y equ 021h
fire_latch equ 022h              ; one shot per press, including empty ammo
ammo equ 023h
bird_ram equ 024h                ; X, Y, state: flying=0, falling=1, absent=2
bird_dx equ 027h
bird_dy equ 028h
turn_time equ 029h
birds_left equ 02ah              ; includes the currently flying/falling bird
flash_time equ 02bh
round_time equ 02ch
anim_clock equ 02dh
game_active equ 02eh              ; bit 0 active, bits 1-4 perfect streak, 6/7 key/pause
sound_event equ 02fh
random_state equ 030h
flash_x equ 031h
flash_y equ 032h
round_hits equ 033h
score_lo equ 034h                ; unsigned 16-bit total, saturated at 65535
score_hi equ 035h
score_pending equ 036h           ; five digits, refreshed one per VBlank
score_digits equ 037h            ; most significant digit first, through 3bh
plus_active equ 03ch             ; retained after the background loader returns
horizon_y equ 150                ; 60% of the 250-line displayed field
x_min equ 008h
x_max equ 098h
y_min equ 014h
y_max equ 0b8h

	org 0400h
	jmp reset                       ; 0400: reset
	jmp irq                         ; 0402: external IRQ -> BIOS
	jmp timer_irq                   ; 0404: timer IRQ
	jmp frame_irq                   ; 0406: sky reset, then full BIOS VSYNC
	jmp reset                       ; 0408: menu launch needs full initialization too
	jmp soundirq                    ; 040a: BIOS sound continuation
reset
	dis tcnti
	stop tcnt
	sel mb0
	sel rb1                         ; BIOS init/gfxoff require the main register bank
	call init                       ; clears all sprites, chars, quads, grid and RAM
	sel rb1
	jmp detect_plus
start
	en i
	dis tcnti
	stop tcnt
	mov r0,#game_active
	mov @r0,#0
	call waitvsync
	call gfxoff
	call prepare_intro
	jnz intro_ready                 ; G7400 title text is already in Plus graphics
	mov r0,#iram_clock
	mov @r0,#080h                   ; do not run the BIOS on-screen clock
	mov r0,#vdc_char0
	mov r3,#02ch
	mov r4,#070h                   ; one text row lower
	mov r2,#9
	mov r1,#title_text & 0ffh
intro_char
	mov a,r1
	movp a,@a
	mov r5,a
	mov a,r1
	add a,#9
	movp a,@a
	mov r6,a
	call printchar
	inc r1
	djnz r2,intro_char
intro_ready
	call gfxon
wait_fire
	call random_byte                ; seed depends on how long the player waits
	call extramenable
	mov r1,#0
	call getjoystick
	jf0 wait_release
	jmp wait_fire
wait_release
	call extramenable
	mov r1,#0
	call getjoystick
	jf0 wait_release
	call waitvsync
	call vdcenable
	call gfxoff
	; Hide the intro chars and all quad records before enabling sprites.
	mov r0,#vdc_char0
	mov r2,#112
	mov a,#0f8h
hide_text
	movx @r0,a
	inc r0
	djnz r2,hide_text
	call start_game_setup           ; reloads the clean Plus landscape when needed
	call begin_round_wait
	call init_score_label
	call reveal_plus
	mov r0,#vdc_color
	mov a,#col_bck_blue
	movx @r0,a
	; Keep the VDC beam counters live for an exact horizon position.
	mov r0,#vdc_control
	mov a,#2
	movx @r0,a
	mov r0,#game_active
	mov @r0,#1
	call draw_scene
	call draw_hud
	call gfxon
	jmp game_loop
title_text
	db _B,_I,_R,_D,00ch,_H,_U,_N,_T
	db col_chr_yellow,col_chr_green,col_chr_red,col_chr_cyan,col_chr_white
	db col_chr_yellow,col_chr_violet,col_chr_white,col_chr_cyan

; BIOS has saved A/P1 and selected RB0 before entering this VSYNC hook.
frame_irq
	mov r0,#game_active
	mov a,@r0
	jz frame_irq_done
	mov r0,#vdc_color
	mov a,#col_bck_blue
	movx @r0,a
	; Arm before the horizon; use the beam counter for the final alignment.
	mov r0,#plus_active
	mov a,@r0
	jnz frame_irq_done
	mov a,#(256-128)
	mov t,a
	strt cnt
	en tcnti
frame_irq_done
	jmp vsyncirq

; Convert the binary total without modifying it. All MOVP data shares page 4.
score_decimal
	mov r0,#score_lo
	mov a,@r0
	mov r4,a
	inc r0
	mov a,@r0
	mov r5,a
	mov r1,#score_digits
	mov r3,#score_divisors & 0ffh
	mov r7,#5
decimal_digit
	mov a,r3
	movp a,@a
	mov r2,a
	inc r3
	mov a,r3
	movp a,@a
	mov r6,a
	inc r3
	mov @r1,#0
decimal_subtract
	mov a,r4
	add a,r2
	mov r0,a
	mov a,r5
	addc a,r6
	jnc decimal_next
	mov r5,a
	mov a,r0
	mov r4,a
	inc @r1
	jmp decimal_subtract
decimal_next
	inc r1
	djnz r7,decimal_digit
	mov r0,#score_pending
	mov @r0,#5
	ret
score_divisors
	db 0f0h,0d8h,018h,0fch,09ch,0ffh,0f6h,0ffh,0ffh,0ffh

; Known G7400 BIOS opcode signatures; unknown/non-Plus BIOS stays G7000-safe.
; MOVP3 reads BIOS page 3 without entering Plus-only routines.
detect_plus
	mov a,#07eh
	movp3 a,@a
	xrl a,#039h
	jnz plain_console
	mov a,#094h
	movp3 a,@a
	xrl a,#0bbh
	jnz plain_console
	mov r0,#plus_active
	mov @r0,#1
	jmp bank02                     ; bank 3 -> bank 2 loader at 0408h
plain_console
	jmp start
	if $ > 0500h
	fatal "Page 4 overflow"
	endif

	org 0500h
game_loop
	sel mb1
	jmp extended_loop

begin_round_wait
	mov r0,#bird_ram+2
	mov @r0,#4                     ; wait for any round melody to finish
	mov r0,#fire_latch
	mov @r0,#1                     ; title/fire cannot spill into a shot
	mov r0,#flash_time
	mov @r0,#0
	ret

move_cursor
	mov r0,#cursor_x
	mov a,@r0
	mov r4,a
	mov a,r2
	jz x_done
	xrl a,#1
	jnz move_left
	mov a,r4
	add a,#2
	mov r4,a
	add a,#(255-x_max)
	jnc x_done
	mov r4,#x_max
	jmp x_done
move_left
	mov a,r4
	add a,#254
	mov r4,a
	add a,#(256-x_min)
	jc x_done
	mov r4,#x_min
x_done
	mov a,r4
	mov @r0,a
	inc r0
	mov a,@r0
	mov r5,a
	mov a,r3
	jz y_done
	xrl a,#1
	jnz move_up
	mov a,r5
	add a,#2
	mov r5,a
	add a,#(255-y_max)
	jnc y_done
	mov r5,#y_max
	jmp y_done
move_up
	mov a,r5
	add a,#254
	mov r5,a
	add a,#(256-y_min)
	jc y_done
	mov r5,#y_min
y_done
	mov a,r5
	mov @r0,a
	ret

shoot
	mov r0,#fire_latch
	jf0 trigger_down
	mov @r0,#0
	ret
trigger_down
	mov a,@r0
	jz new_shot
	ret
new_shot
	mov @r0,#1
	mov r0,#bird_ram+2
	mov a,@r0
	xrl a,#2
	jz no_shot
	mov r0,#ammo
	mov a,@r0
	jz no_shot
	dec a
	mov @r0,a
	mov r0,#sound_event
	mov @r0,#tune_shoot
	mov r0,#bird_ram+2
	mov a,@r0
	jnz missed
	mov r1,#bird_ram
	mov a,@r1
	cpl a
	add a,#1
	mov r6,a
	mov r0,#cursor_x
	mov a,@r0
	add a,#4
	add a,r6
	add a,#248
	jc missed
	inc r1
	mov a,@r1
	cpl a
	add a,#1
	mov r6,a
	mov r0,#cursor_y
	mov a,@r0
	add a,#8
	add a,r6
	add a,#240
	jc missed
	inc r1
	mov @r1,#1
	mov r0,#round_hits
	inc @r0
	ret
missed
	; Freeze the flash at the shot position, independent of later cursor movement.
	mov r0,#flash_time
	mov @r0,#8
	mov r0,#cursor_x
	mov r1,#flash_x
	mov a,@r0
	mov @r1,a
	inc r0
	inc r1
	mov a,@r0
	mov @r1,a
no_shot
	ret

; At most one BIOS character write per frame, keeping NTSC VBlank safe.
draw_score
	mov r0,#score_pending
	mov a,@r0
	jz score_draw_done
	dec a
	mov @r0,a
	cpl a
	add a,#5                        ; index 0..4
	mov r2,a
	add a,#score_digits
	mov r1,a
	mov a,@r1
	mov r5,a                       ; BIOS digits 0..9 have character codes 0..9
	mov a,r2
	rl a
	rl a
	add a,#vdc_char5
	mov r0,a
	mov a,r2
	rl a
	rl a
	rl a
	add a,#084                      ; space between SCORE and the five digits
	mov r3,a
	mov r4,#220
	mov r6,#col_chr_white
	call printchar
score_draw_done
	ret

prepare_intro
	mov r0,#plus_active
	mov a,@r0
	jnz prepare_plus_intro
	ret                            ; A is zero; BIOS init left the title black
prepare_plus_intro
	mov r0,#vdc_color
	mov a,#col_bck_blue             ; mixer exposes the Plus title through blue
	movx @r0,a
	call reveal_plus
	mov a,#1
	ret

; This routine is entered with a CALL. The loader bridge eventually jumps to
; init_game, whose RET returns to the original caller after the bank round-trip.
start_game_setup
	mov r0,#plus_active
	mov a,@r0
	jz plain_game_setup
	inc @r0                        ; 1 -> 2: restore, do not reapply, the title
	call plusenable
	call plushide
	jmp bank01                      ; bank 3 -> bank 1 screen loader at 0408h
plain_game_setup
	jmp init_game

loader_bridge
	mov r0,#plus_active
	mov a,@r0
	dec a
	jz loader_to_title
	mov @r0,#1
	jmp init_game
loader_to_title
	jmp start
	if $ > 0600h
	fatal "Page 5 overflow"
	endif

	org 0600h
move_birds
	mov r0,#anim_clock
	inc @r0
	mov r0,#round_time
	mov a,@r0
	jz bird_step
	dec a
	mov @r0,a
	jnz bird_return
	call begin_round_wait
	ret
bird_step
	mov r0,#bird_ram+2
	mov a,@r0
	jnz falling
	mov r0,#bird_dx
	mov a,@r0
	mov r1,#bird_ram
	add a,@r1
	mov @r1,a
	xrl a,#(x_max+1)
	jz bird_finished
	mov a,@r1
	xrl a,#(x_min-1)
	jz bird_finished
	mov r0,#turn_time
	mov a,@r0
	dec a
	mov @r0,a
	jnz vertical_step
	call choose_turn
vertical_step
	mov r0,#anim_clock
	mov a,@r0
	anl a,#1
	jnz bird_return
	mov r0,#bird_dy
	mov a,@r0
	mov r1,#bird_ram+1
	add a,@r1
	mov @r1,a
	xrl a,#31
	jz bounce_down
	mov a,@r1
	xrl a,#129
	jnz bird_return
	mov @r1,#128
	mov @r0,#0ffh
	ret
bounce_down
	mov @r1,#32
	mov @r0,#1
bird_return
	ret
falling
	mov r0,#bird_ram+1
	mov a,@r0
	add a,#4
	mov @r0,a
	add a,#(256-216)
	jnc bird_return
bird_finished
	mov r0,#birds_left
	mov a,@r0
	dec a
	mov @r0,a
	jz round_finished
	call spawn_bird
	ret
round_finished
	sel mb1
	call settle_score
	sel mb0
	mov r0,#bird_ram+2
	mov @r0,#2
	mov r0,#round_time
	mov @r0,#30                    ; short round-sound pause (0.5-0.6 seconds)
	mov r0,#sound_event
	mov @r0,#tune_select2
	ret

; Position updates are confined to VBlank with foreground disabled.
draw_scene
	mov r0,#vdc_spr0_ctrl
	mov r1,#cursor_y
	mov a,@r1
	movx @r0,a
	inc r0
	dec r1
	mov a,@r1
	movx @r0,a
	inc r0
	mov a,#col_spr_yellow
	movx @r0,a
	mov r0,#vdc_spr1_ctrl
	mov r1,#bird_ram+2
	mov a,@r1
	anl a,#0feh                   ; hide absent, game-over and waiting states
	jnz hide_bird
	dec r1
	mov a,@r1
	movx @r0,a
	inc r0
	dec r1
	mov a,@r1
	movx @r0,a
	inc r0
	mov r1,#bird_ram+2
	mov a,@r1
	jz white_bird
	mov a,#col_spr_red
	jmp bird_color
white_bird
	mov a,#col_spr_white
bird_color
	movx @r0,a
	jmp draw_flash
hide_bird
	mov a,#0f8h
	movx @r0,a
draw_flash
	mov r0,#vdc_spr2_ctrl
	mov r1,#flash_time
	mov a,@r1
	jz hide_flash
	mov r1,#flash_y
	mov a,@r1
	movx @r0,a
	inc r0
	dec r1
	mov a,@r1
	movx @r0,a
	inc r0
	mov a,#col_spr_white
	movx @r0,a
	jmp animate_birds
hide_flash
	mov a,#0f8h
	movx @r0,a
	jmp animate_birds

; One mid-frame interrupt; preserve mainline registers and BIOS sound R3/R4.
timer_irq
	sel rb0
	mov r5,a
	stop tcnt
	in a,p1
	mov r6,a
	call vdcenable
	mov r0,#vdc_scanline
wait_horizon
	movx a,@r0
	add a,#(257-horizon_y)          ; align during the line preceding the horizon
	jnc wait_horizon
	; T1 is the real HBLANK/VBLANK input. VDC status bit 0 is NOT HBLANK.
	mov r0,#vdc_color
	mov a,#col_bck_green
wait_active_line
	jt1 wait_active_line
wait_hblank
	jnt1 wait_hblank
	movx @r0,a
	jmp irqend                      ; restores P1/A and RETR restores the PSW

init_score_label
	mov r0,#vdc_char0
	mov r1,#score_label & 0ffh
	mov r2,#5
	mov r3,#036
	mov r4,#220
score_label_char
	mov a,r1
	movp a,@a
	mov r5,a
	mov r6,#col_chr_white
	call printchar
	inc r1
	djnz r2,score_label_char
	ret
score_label
	db _S,_C,_O,_R,_E

reveal_plus
	mov r0,#plus_active
	mov a,@r0
	jz no_plus_reveal
	mov r7,#0ebh                   ; mixer wiring: blue=bit4, green=bit2
	mov a,#0ffh                    ; dark Plus colors, no external collisions
	call plusmode
no_plus_reveal
	ret
	if $ > 0700h
	fatal "Page 6 overflow"
	endif


	org 0700h
init_game
	call score_decimal              ; BIOS init has zeroed the total
	mov r0,#cursor_x
	mov @r0,#060h
	inc r0
	mov @r0,#060h
	inc r0
	mov @r0,#0
	mov r0,#flash_time
	mov @r0,#0
	mov r0,#round_time
	mov @r0,#0
	mov r0,#vdc_spr0_shape
	mov r3,#cursor_shape & 0ffh
	call copy_shape
	mov r0,#vdc_spr2_shape
	mov r3,#miss_shape & 0ffh
	call copy_shape
new_round
	mov r0,#round_hits
	mov @r0,#0
	mov r0,#birds_left
	mov @r0,#3
	mov r0,#ammo
	mov @r0,#5
spawn_bird
	call random_byte
	anl a,#63
	add a,#32
	mov r0,#bird_ram+1
	mov @r0,a
	inc r0
	mov @r0,#0
	call random_byte
	anl a,#1
	jz from_left
	mov r0,#bird_ram
	mov @r0,#x_max
	mov r0,#bird_dx
	mov @r0,#0ffh
	jmp choose_turn
from_left
	mov r0,#bird_ram
	mov @r0,#x_min
	mov r0,#bird_dx
	mov @r0,#1
choose_turn
	; Change vertical slope periodically; reflections keep the whole bird in the sky.
	call random_byte
	anl a,#1
	jnz downward
	mov a,#0ffh
	jmp store_dy
downward
	mov a,#1
store_dy
	mov r0,#bird_dy
	mov @r0,a
	call random_byte
	anl a,#31
	add a,#16
	mov r0,#turn_time
	mov @r0,a
	ret

; Nonzero 8-bit LFSR; intro wait time supplies a changing initial seed.
random_byte
	mov r0,#random_state
	mov a,@r0
	jnz random_shift
	mov a,#0a7h
random_shift
	clr c
	rrc a
	jnc random_store
	xrl a,#0b8h
random_store
	mov @r0,a
	ret

animate_birds
	mov r0,#vdc_spr1_shape
	mov r3,#bird_fall & 0ffh
	mov r1,#bird_ram+2
	mov a,@r1
	jnz copy_shape
	mov r1,#anim_clock
	mov a,@r1
	anl a,#8
	add a,#bird_wings & 0ffh
	mov r3,a
copy_shape
	mov r2,#8
copy_row
	mov a,r3
	movp a,@a
	movx @r0,a
	inc r0
	inc r3
	djnz r2,copy_row
	ret
cursor_shape
	db 018h,018h,000h,0c3h,0c3h,000h,018h,018h
bird_wings
	db 081h,042h,024h,018h,03ch,018h,000h,000h
	db 000h,000h,018h,03ch,05ah,099h,000h,000h
bird_fall
	db 018h,03ch,018h,018h,03ch,05ah,099h,000h
miss_shape
	db 000h,018h,03ch,07eh,07eh,03ch,018h,000h

; The HUD helper makes no BIOS calls and restores the MB0 latch explicitly.
draw_hud
	db 0f5h                        ; SEL MB1, hidden from ASL bank inference
	call 000h                      ; 0800h while MB1 is selected
	sel mb0
	jnz hud_return                 ; do not refresh score on an ammo-update frame
	jmp draw_score
hud_return
	ret
rom_end
	if rom_end > 0800h
	fatal "BIRD HUNT exceeded MB0; review every CALL/JMP before using MB1"
	endif
	if $ > 07f8h
	fatal "Game overlaps loader return bridge"
	endif
	org 07f8h
	orl p1,#3                      ; shared address with loader bank-switch bridge
	jmp loader_bridge              ; select title startup or post-title game setup

	org 0800h
; Char A is the fifth cartridge; quad 0 contains the first four. Char B stays
; hidden, with its unused pointer byte caching the last ammo count. VDC reads
; and writes here occur only with graphics disabled in VBlank.
ammo_hud
	mov r1,#ammo
	mov a,@r1
	mov r6,a
	mov r0,#vdc_charb+2
	movx a,@r0
	mov r5,a
	xrl a,r6
	jnz ammo_changed
	clr a
	ret
ammo_changed
	mov a,r6
	movx @r0,a
	mov a,r5
	xrl a,#0f8h
	jnz ammo_pointers
	; tune_shoot only changes AA (control), unlike tune_select2 which loads
	; A7-A9. Seed a nonzero waveform before the first shot, output still muted.
	mov r0,#vdc_sound0
	clr a
	movx @r0,a
	inc r0
	mov a,#00fh
	movx @r0,a
	inc r0
	mov a,#0ffh
	movx @r0,a
	mov r0,#vdc_quad0
	mov r3,#ammo_positions & 0ffh
	mov r2,#16
ammo_init_quad
	mov a,r3
	movp a,@a
	movx @r0,a
	inc r0
	inc r3
	djnz r2,ammo_init_quad
	mov r0,#vdc_chara
	mov r2,#4
ammo_init_fifth
	mov a,r3
	movp a,@a
	movx @r0,a
	inc r0
	inc r3
	djnz r2,ammo_init_fifth
ammo_pointers
	mov a,r6
	rl a
	rl a
	add a,r6                       ; five pointer bytes per ammo count
	add a,#ammo_shapes & 0ffh
	mov r3,a
	mov r0,#vdc_quad0+2
	mov r2,#4
ammo_quad_pointer
	mov a,r3
	movp a,@a
	movx @r0,a
	inc r3
	mov a,r0
	add a,#4
	mov r0,a
	djnz r2,ammo_quad_pointer
	mov r0,#vdc_chara+2
	mov a,r3
	movp a,@a
	movx @r0,a
	mov a,#1
	ret
ammo_positions
	db 16,88,88,6,16,88,88,6,16,88,88,6,16,88,88,6
	db 16,152,88,6
; ROM glyph I resembles a narrow cartridge. Space and I both have 7 rows,
; preserving the quad's shared height when its rightmost cartridge vanishes.
ammo_shapes
	db 88,88,88,88,88
	db 168,88,88,88,88
	db 168,168,88,88,88
	db 168,168,168,88,88
	db 168,168,168,168,88
	db 168,168,168,168,168
	if $ > 0900h
	fatal "Ammo HUD crossed MOVP page"
	endif

; Calls from MB1 must restore the bank latch after returning from MB0/BIOS.
call_base macro target
	sel mb0
	call target
	sel mb1
	endm

	org 0900h
extended_loop
	call_base extramenable
	call poll_pause
	mov r1,#0
	call_base getjoystick
	mov r0,#game_active
	mov a,@r0
	jb7 paused_frame
	mov r0,#bird_ram+2
	mov a,@r0
	jb2 waiting_frame
	xrl a,#3
	jz game_over_tick
	mov r0,#flash_time
	mov a,@r0
	jz extended_input
	dec a
	mov @r0,a
extended_input
	call_base move_cursor
	call_base shoot
	call_base move_birds
	call round_events
	jmp extended_render
waiting_frame
	call_base move_cursor
	call wait_round
	jmp extended_render
paused_frame
	jf0 resume_game
	jmp extended_render
resume_game
	mov a,@r0
	anl a,#07fh
	mov @r0,a
	mov r0,#fire_latch
	mov @r0,#1                    ; resume consumes the press, not ammunition
	jmp extended_render
game_over_tick
	mov r0,#round_time
	mov a,@r0
	dec a
	mov @r0,a
	jnz extended_render
	sel mb0
	jmp reset
extended_render
	call_base waitvsync
	call_base vdcenable
	call_base gfxoff
	call_base draw_scene
	call_base draw_hud
	call_base gfxon
	mov r0,#sound_event
	mov a,@r0
	jz extended_next
	mov @r0,#0
	call_base playsound
extended_next
	jmp extended_loop

; Scan all six console keyboard rows. Bit 4 low means a key is pressed.
; game_active bits 7/6 hold pause/key-edge state without consuming more RAM.
poll_pause
	anl p1,#0fbh                   ; enable the keyboard encoder (active-low P1.2)
	mov r0,#0f0h
	mov r2,#6
keyboard_row
	mov a,r0
	outl p2,a
	in a,p2
	jb4 keyboard_next
	mov r0,#game_active
	mov a,@r0
	jb6 keyboard_done
	orl a,#0c0h
	mov @r0,a
	jmp keyboard_done
keyboard_next
	inc r0
	djnz r2,keyboard_row
	mov r0,#game_active
	mov a,@r0
	anl a,#0bfh
	mov @r0,a
keyboard_done
	orl p1,#4
	ret
	if $ > 0a00h
	fatal "Extended loop crossed page"
	endif

	org 0a00h
round_events
	mov r0,#bird_ram+2
	mov a,@r0
	xrl a,#2
	jnz event_done
	mov r0,#round_time
	mov a,@r0
	xrl a,#30
	jz round_boundary
	mov a,@r0
	xrl a,#60
	jnz event_done
	jmp happy_event
round_boundary
	mov r0,#round_hits
	mov a,@r0
	jz no_hits_end
	xrl a,#3
	jnz event_done
	mov r0,#ammo
	mov a,@r0
	xrl a,#2
	jnz happy_event
	; Initial round completion has a pending default tune. Later repetitions
	; have none, so the final 30-frame segment cannot restart the 90-frame gap.
	mov r0,#sound_event
	mov a,@r0
	jz happy_event
	mov r0,#round_time
	mov @r0,#90
happy_event
	mov r0,#sound_event
	mov @r0,#tune_select
event_done
	ret
no_hits_end
	mov r0,#sound_event
	mov @r0,#tune_alarm             ; every zero-hit round announces the halving
	mov r0,#score_lo
	mov a,@r0
	inc r0
	orl a,@r0
	jnz event_done
	mov r0,#bird_ram+2
	mov @r0,#3
	call two_second_timer
	ret
two_second_timer
	; Measure VBlank before starting the alarm: PAL ~D6, NTSC ~34.
	; The next VSYNC re-arms the horizon hook. Its interrupt occurs after
	; VBlank, so measurement does not need to blank the G7000 grass for a frame.
	call_base waitvsync
	clr a
measure_blank
	inc a
	jz blank_measured
	nop
	nop
	nop
	jt1 measure_blank
blank_measured
	mov r2,#120
	jb7 pal_gameover
	jmp set_gameover_time
pal_gameover
	mov r2,#100
set_gameover_time
	mov r0,#round_time
	mov a,r2
	mov @r0,a
	mov r0,#game_active
	mov a,@r0
	anl a,#01eh                    ; preserve only the perfect-run streak
	orl a,#1
	mov @r0,a
	ret

; Called exactly once when the third bird has left or finished falling.
; The perfect streak is encoded as twice its count in game_active bits 1-4.
settle_score
	mov r0,#round_hits
	mov a,@r0
	jz break_streak_halve
	mov r2,#1
	mov r3,#0
	dec a
	jz break_streak_add
	mov r2,#5
	dec a
	jz break_streak_add
	mov r0,#ammo
	mov a,@r0
	mov r2,a
	xrl a,#2
	jz perfect_score
	; Three hits without two bullets left keeps the ordinary 10/15-point rule.
	mov a,r2
	rl a
	rl a
	add a,r2
	add a,#10
	mov r2,a
	mov r3,#0
break_streak_add
	call clear_perfect_streak
	jmp add_round_score
break_streak_halve
	call clear_perfect_streak
	mov r0,#score_hi
	mov a,@r0
	clr c
	rrc a
	mov @r0,a
	dec r0
	mov a,@r0
	rrc a                          ; carry transfers the high byte's lowest bit
	mov @r0,a
	call_base score_decimal
	ret
perfect_score
	mov r0,#game_active
	mov a,@r0
	mov r5,a
	anl a,#01eh
	mov r4,a                       ; old streak, also the shift count times two
	xrl a,#01ah                    ; 13+ rounds all exceed the 16-bit score range
	jz perfect_streak_stored
	mov a,r4
	add a,#2
	mov r4,a
perfect_streak_stored
	mov a,r5
	anl a,#0e1h                    ; retain active and keyboard/pause flags
	orl a,r4
	mov @r0,a
	mov a,r4
	add a,#0feh                    ; divide the updated encoded count by two
	rr a                           ; award uses the previous count: 20 << (n-1)
	anl a,#00fh
	mov r4,a
	mov r2,#20
	mov r3,#0
	mov a,r4
	jz add_round_score
perfect_shift
	mov a,r2
	clr c
	rlc a
	mov r2,a
	mov a,r3
	rlc a
	mov r3,a
	jc max_round_award
	djnz r4,perfect_shift
	jmp add_round_score
max_round_award
	mov r2,#0ffh
	mov r3,#0ffh
add_round_score
	mov r0,#score_lo
	mov a,@r0
	add a,r2
	mov @r0,a
	inc r0
	mov a,@r0
	addc a,r3
	jnc store_round_score
score_overflow
	mov a,#0ffh                    ; saturate instead of wrapping the total
	mov @r0,a
	dec r0
	mov @r0,a
	jmp round_score_changed
store_round_score
	mov @r0,a
round_score_changed
	call_base score_decimal
	ret
clear_perfect_streak
	mov r0,#game_active
	mov a,@r0
	anl a,#0e1h
	mov @r0,a
	ret
	if $ > 0b00h
	fatal "Round events crossed page"
	endif

	org 0b00h
; Waiting states are kept separate from the melody/repetition timer. Countdown
; begins only once BIOS sound playback has stopped, including triple cheers.
wait_round
	mov r0,#fire_latch
	mov @r0,#1
	mov r0,#bird_ram+2
	mov a,@r0
	xrl a,#4
	jnz round_countdown
	mov r0,#iram_irqctrl
	mov a,@r0
	jb6 wait_round_done
	call two_second_timer
	mov r0,#bird_ram+2
	mov @r0,#5
	ret
round_countdown
	mov r0,#round_time
	mov a,@r0
	dec a
	mov @r0,a
	jnz wait_round_done
	mov r0,#bird_ram+2
	mov a,@r0
	xrl a,#6
	jz start_waited_round
	call two_second_timer
	mov r0,#round_time
	mov a,@r0
	rr a                         ; 100/120 frames becomes one second
	mov @r0,a
	mov r0,#bird_ram+2
	mov @r0,#6
	mov r0,#sound_event
	mov @r0,#tune_buzz
	ret
start_waited_round
	call_base new_round
wait_round_done
	ret
	if $ > 0c00h
	fatal "Cartridge exceeds standard 2K bank"
	endif
