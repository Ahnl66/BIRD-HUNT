; Identical MB0 code in cartridge banks 0, 1 and 2. Interrupts stay disabled
; during streaming; bank 3 owns all gameplay. RAM 20h/R2 = data offset/page.
; Plus BIOS busy polling clobbers R0; never retain the stream pointer there.

	org 0400h
	jmp bank3
	jmp irq
	retr
	nop
	jmp vsyncirq
	jmp loader_entry
	jmp soundirq
loader_entry
	dis tcnti
	stop tcnt
	in a,p1
	anl a,#3
	xrl a,#2
	jz load_patterns
	jmp load_screen
load_patterns
	call waitvsync
	call gfxoff
	call plusenable
	clr a
	call plusloadr
	dis i
	call plushide
	mov r7,#plus_cmd_brow
	mov r6,#0
	call pluscmd
	mov r0,#020h
	mov @r0,#0
	mov r2,#0
	mov r3,#0a0h
pattern_loop
	mov r7,#plus_cmd_loadm
	mov r6,#plus_loadm_wrni
	call pluscmd
	mov r6,#088h
	mov a,r3
	mov r7,a
	call plusdata
	mov r7,#plus_cmd_loadm
	mov r6,#plus_loadm_wrsl
	call pluscmd
	mov r4,#10
pattern_slice
	call read_next
	mov r6,a
	mov r7,a
	call plusdata
	djnz r4,pattern_slice
	inc r3
	mov a,r3
	jnz pattern_loop
	; Atomically change external banks; same continuation exists in every bank.
	in a,p1
	anl a,#0fch
	orl a,#1
	outl p1,a
	jmp load_screen
	if $ > 0500h
	fatal "Loader page 4 overflow"
	endif

	org 0500h
load_screen
	dis i
	call plusenable
	mov r7,#plus_cmd_loadm
	mov r6,#plus_loadm_wr
	call pluscmd
	mov r0,#020h
	mov @r0,#0
	mov r2,#0
	mov r3,#0
	in a,p1
	jb0 screen_row
	mov r3,#12
screen_row
	mov r7,#plus_cmd_brow
	mov a,r3
	mov r6,a
	call pluscmd
	mov r4,#40
screen_cell
	call read_next
	mov r5,a
	call read_next
	mov r7,a
	mov a,r5
	mov r6,a
	call plusdata
	djnz r4,screen_cell
	inc r3
	mov a,r2
	xrl a,#4
	jnz screen_row
	in a,p1
	jb0 second_half
	; Clear the service row to blue too; enabling it fills the top ten lines.
	mov r7,#plus_cmd_brow
	mov r6,#31
	call pluscmd
	mov r4,#40
service_cell
	mov r6,#0cch                   ; blue FG and BG, irrespective of pattern
	mov r7,#0a0h
	call plusdata
	djnz r4,service_cell
	mov r7,#plus_cmd_loady0
	mov r6,#0
	call pluscmd
	call maybe_intro
	en i
	call waitvsync
	call plusenable
	mov a,#plus_loadr_dspl+plus_loadr_srow
	call plusloadr
	call vdcenable
	jmp loader_return              ; bypass the public menu entry (full reset)
second_half
	in a,p1
	anl a,#0fch
	outl p1,a
	jmp load_screen
	if $ > 0600h
	fatal "Loader page 5 overflow"
	endif

	org 0600h
; Explicit SEL MB1 opcode plus low CALL alias prevents ASL's inferred bank
; state from leaking into BIOS calls. Every path restores MB0 after RET.
read_next
	mov r0,#020h
	mov a,@r0
	mov r0,a
	mov a,r2
	jz read_page0
	dec a
	jz read_page1
	dec a
	jz read_page2
	mov a,r0
	db 0f5h
	call 03f0h
	sel mb0
	jmp read_advance
read_page2
	mov a,r0
	db 0f5h
	call 02f0h
	sel mb0
	jmp read_advance
read_page1
	mov a,r0
	db 0f5h
	call 01f0h
	sel mb0
	jmp read_advance
read_page0
	mov a,r0
	db 0f5h
	call 00f0h
	sel mb0
read_advance
	mov r6,a
	inc r0
	mov a,r0
	xrl a,#240
	jnz read_return
	mov r0,#0
	inc r2
read_return
	mov a,r0
	mov r1,#020h
	mov @r1,a
	mov a,r6
	ret

; The title is stored as row/column/run-count commands in page 7 of banks
; 2, 1 and 0. Only changed cells are written over the gameplay landscape.
maybe_intro
	mov r0,#03ch                   ; plus_active: 1=title, 2=gameplay restore
	mov a,@r0
	xrl a,#1
	jnz intro_done
	in a,p1                        ; full screen loading ended in bank 0
	orl a,#2
	outl p1,a                      ; continue at this address in bank 2
	mov r0,#020h
	mov @r0,#0
intro_command
	call intro_next
	xrl a,#0ffh
	jz intro_done
	xrl a,#0ffh                    ; restore the row after the sentinel test
	mov r1,#022h
	mov @r1,a                      ; row
	call intro_next
	mov r1,#021h
	mov @r1,a                      ; column survives the first Plus BIOS call
	mov r7,#plus_cmd_brow
	mov r1,#022h
	mov a,@r1
	mov r6,a
	call pluscmd
	mov r7,#plus_cmd_loadx
	mov r1,#021h
	mov a,@r1
	mov r6,a
	call pluscmd
	call intro_next
	mov r2,a                       ; number of RLE runs in this span
intro_run
	call intro_next
	mov r4,a                       ; repeated cell count
	call intro_next
	mov r1,#021h
	mov @r1,a                      ; parallel attribute
	call intro_next
	mov r7,a                       ; character code
	mov r1,#021h
	mov a,@r1
	mov r6,a
intro_repeat
	call plusdata
	djnz r4,intro_repeat
	djnz r2,intro_run
	jmp intro_command
intro_done
	ret

intro_next
	mov r0,#020h
	mov a,@r0
	mov r0,a
	call intro_page_read
	mov r5,a
	inc r0
	mov a,r0
	xrl a,#240
	jnz intro_store_offset
	mov r0,#0
	in a,p1
	jb1 intro_bank1
	anl a,#0fch                    ; bank 1 -> bank 0
	outl p1,a
	jmp intro_store_offset
intro_bank1
	anl a,#0fch                    ; bank 2 -> bank 1
	orl a,#1
	outl p1,a
intro_store_offset
	mov a,r0
	mov r1,#020h
	mov @r1,a
	mov a,r5
	ret
	if $ > 0700h
	fatal "Loader page 6 overflow"
	endif

	org 07f0h
intro_page_read
	movp a,@a
	ret

	org 07f8h
loader_return
	orl p1,#3                      ; next instruction comes from game bank 3
	jmp 0400h                      ; unreachable; bank 3 instead jumps to title
