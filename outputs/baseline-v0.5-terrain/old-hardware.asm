;--------------------------------------------------------
; File Created by SDCC : free open source ISO C Compiler
; Version 4.6.0 #16555 (MINGW64)
;--------------------------------------------------------
	.module hardware
	
	.optsdcc -mz80 sdcccall(1)
;--------------------------------------------------------
; Public variables in this module
;--------------------------------------------------------
	.globl _span_height
	.globl _span_y
	.globl _gfx_wait
	.globl _gfx_vblank
	.globl _gfx_init
	.globl _hardware_upload
	.globl _gfx_fill
	.globl _gfx_blit
	.globl _gfx_begin_spans
	.globl _gfx_span
	.globl _gfx_flip
	.globl _input_read
	.globl _engine_sound
;--------------------------------------------------------
; special function registers
;--------------------------------------------------------
_hw_vram	=	0x0060
_hw_palette	=	0x0061
_hw_reg_data	=	0x0063
_hw_reg_select	=	0x0064
_hw_status	=	0x0065
_hw_irq_flags	=	0x0066
_hw_system	=	0x0067
_hw_psg_select	=	0x00a0
_hw_psg_write	=	0x00a1
_hw_psg_read	=	0x00a2
_hw_key_data	=	0x00a9
_hw_key_select	=	0x00aa
;--------------------------------------------------------
; ram data
;--------------------------------------------------------
	.area _DATA
_span_y::
	.ds 2
_span_height::
	.ds 1
;--------------------------------------------------------
; ram data
;--------------------------------------------------------
	.area _INITIALIZED
;--------------------------------------------------------
; absolute ram data
;--------------------------------------------------------
	.area _DABS (ABS)
	.area _DABS (ABS)
;--------------------------------------------------------
; global & static initialisations
;--------------------------------------------------------
	.area _HOME
	.area _GSINIT
	.area _GSFINAL
	.area _GSINIT
;--------------------------------------------------------
; Home
;--------------------------------------------------------
	.area _HOME
	.area _HOME
;--------------------------------------------------------
; code
;--------------------------------------------------------
	.area _CODE
;work/candidates/8849a4e19fb9/src/hardware.c:18: static void reg_write(u8 r,u8 v){hw_reg_select=r;hw_reg_data=v;}
;	---------------------------------
; Function reg_write
; ---------------------------------
_reg_write:
	out	(_hw_reg_select), a
	ld	a, l
	out	(_hw_reg_data), a
	ret
_v9990_palette:
	.db #0x00	; 0
	.db #0x00	; 0
	.db #0x00	; 0
	.db #0x0c	; 12
	.db #0x17	; 23
	.db #0x1d	; 29
	.db #0x14	; 20
	.db #0x1b	; 27
	.db #0x1c	; 28
	.db #0x0d	; 13
	.db #0x13	; 19
	.db #0x15	; 21
	.db #0x07	; 7
	.db #0x0d	; 13
	.db #0x0e	; 14
	.db #0x10	; 16
	.db #0x16	; 22
	.db #0x09	; 9
	.db #0x04	; 4
	.db #0x09	; 9
	.db #0x07	; 7
	.db #0x0d	; 13
	.db #0x12	; 18
	.db #0x08	; 8
	.db #0x15	; 21
	.db #0x0a	; 10
	.db #0x06	; 6
	.db #0x16	; 22
	.db #0x13	; 19
	.db #0x0d	; 13
	.db #0x18	; 24
	.db #0x15	; 21
	.db #0x0f	; 15
	.db #0x1b	; 27
	.db #0x19	; 25
	.db #0x13	; 19
	.db #0x04	; 4
	.db #0x05	; 5
	.db #0x05	; 5
	.db #0x1d	; 29
	.db #0x12	; 18
	.db #0x08	; 8
	.db #0x11	; 17
	.db #0x13	; 19
	.db #0x11	; 17
	.db #0x1e	; 30
	.db #0x1d	; 29
	.db #0x19	; 25
;work/candidates/8849a4e19fb9/src/hardware.c:22: void gfx_wait(void){while(hw_status&1){}}
;	---------------------------------
; Function gfx_wait
; ---------------------------------
_gfx_wait::
00101$:
	in	a, (_hw_status)
	rrca
	jr	c, 00101$
	ret
;work/candidates/8849a4e19fb9/src/hardware.c:23: void gfx_vblank(void){while(hw_status&0x40){} while(!(hw_status&0x40)){}}
;	---------------------------------
; Function gfx_vblank
; ---------------------------------
_gfx_vblank::
00101$:
	in	a, (_hw_status)
	bit	6, a
	jr	nz, 00101$
00104$:
	in	a, (_hw_status)
	bit	6, a
	jr	z, 00104$
	ret
;work/candidates/8849a4e19fb9/src/hardware.c:24: void gfx_init(void){
;	---------------------------------
; Function gfx_init
; ---------------------------------
_gfx_init::
;work/candidates/8849a4e19fb9/src/hardware.c:26: __asm di __endasm;
	di	
;work/candidates/8849a4e19fb9/src/hardware.c:27: hw_system=2;hw_system=0;
	ld	a, #0x02
	out	(_hw_system), a
	xor	a, a
	out	(_hw_system), a
;work/candidates/8849a4e19fb9/src/hardware.c:28: hw_reg_select=0;for(i=0;i<29;++i)hw_reg_data=0;
	xor	a, a
	out	(_hw_reg_select), a
	ld	c, #0x00
00103$:
	xor	a, a
	out	(_hw_reg_data), a
	inc	c
	ld	a, c
	sub	a, #0x1d
	jr	c, 00103$
;work/candidates/8849a4e19fb9/src/hardware.c:29: hw_irq_flags=7;
	ld	a, #0x07
	out	(_hw_irq_flags), a
;work/candidates/8849a4e19fb9/src/hardware.c:30: reg_write(6,0x81);reg_write(7,0);reg_write(8,0x42);
	ld	l, #0x81
	ld	a, #0x06
	call	_reg_write
	ld	l, #0x00
	ld	a, #0x07
	call	_reg_write
	ld	l, #0x42
	ld	a, #0x08
	call	_reg_write
;work/candidates/8849a4e19fb9/src/hardware.c:31: reg_write(13,0);reg_write(14,0);
	ld	l, #0x00
	ld	a, #0x0d
	call	_reg_write
	ld	l, #0x00
	ld	a, #0x0e
	call	_reg_write
;work/candidates/8849a4e19fb9/src/hardware.c:32: for(i=0;i<48;++i)hw_palette=v9990_palette[i];
	ld	bc, #_v9990_palette+0
	ld	e, #0x00
00105$:
	ld	l, e
	ld	h, #0x00
	add	hl, bc
	ld	a, (hl)
	out	(_hw_palette), a
	inc	e
	ld	a, e
	sub	a, #0x30
	jr	c, 00105$
;work/candidates/8849a4e19fb9/src/hardware.c:33: gfx_vblank();gfx_fill(0,0,256,512,0);gfx_wait();
	call	_gfx_vblank
	xor	a, a
	push	af
	inc	sp
	ld	hl, #0x0200
	push	hl
	ld	h, #0x01
	push	hl
	ld	de, #0x0000
	ld	h, l
	call	_gfx_fill
;work/candidates/8849a4e19fb9/src/hardware.c:34: }
	jp	_gfx_wait
;work/candidates/8849a4e19fb9/src/hardware.c:35: static void upload_bank(void) __naked{
;	---------------------------------
; Function upload_bank
; ---------------------------------
_upload_bank:
;work/candidates/8849a4e19fb9/src/hardware.c:46: __endasm;
	ld hl,#0x6000
	ld c,#0x60
	ld e,#32
drive_upload_loop:
	ld b,#0
	otir
	dec e
	jr nz,drive_upload_loop
	ret
;work/candidates/8849a4e19fb9/src/hardware.c:47: }
;work/candidates/8849a4e19fb9/src/hardware.c:48: void hardware_upload(void){
;	---------------------------------
; Function hardware_upload
; ---------------------------------
_hardware_upload::
;work/candidates/8849a4e19fb9/src/hardware.c:50: gfx_wait();hw_reg_select=0;hw_reg_data=0;hw_reg_data=0;hw_reg_data=1;
	call	_gfx_wait
	xor	a, a
	out	(_hw_reg_select), a
	xor	a, a
	out	(_hw_reg_data), a
	xor	a, a
	out	(_hw_reg_data), a
	ld	a, #0x01
	out	(_hw_reg_data), a
;work/candidates/8849a4e19fb9/src/hardware.c:51: for(bank=4;bank<12;++bank){*((volatile u8*)0x6800)=bank;upload_bank();}
	ld	c, #0x04
00103$:
	ld	hl, #0x6800
	ld	(hl), c
	push	bc
	call	_upload_bank
	pop	bc
	inc	c
	ld	a, c
	sub	a, #0x0c
	jr	c, 00103$
;work/candidates/8849a4e19fb9/src/hardware.c:53: hw_reg_select=0;hw_reg_data=0;hw_reg_data=0;hw_reg_data=3;
	xor	a, a
	out	(_hw_reg_select), a
	xor	a, a
	out	(_hw_reg_data), a
	xor	a, a
	out	(_hw_reg_data), a
	ld	a, #0x03
	out	(_hw_reg_data), a
;work/candidates/8849a4e19fb9/src/hardware.c:54: for(bank=44;bank<60;++bank){*((volatile u8*)0x6800)=bank;upload_bank();}
	ld	c, #0x2c
00105$:
	ld	hl, #0x6800
	ld	(hl), c
	push	bc
	call	_upload_bank
	pop	bc
	inc	c
	ld	a, c
	sub	a, #0x3c
	jr	c, 00105$
;work/candidates/8849a4e19fb9/src/hardware.c:55: reg_write(8,0xc2);gfx_vblank();
	ld	l, #0xc2
	ld	a, #0x08
	call	_reg_write
;work/candidates/8849a4e19fb9/src/hardware.c:56: }
	jp	_gfx_vblank
;work/candidates/8849a4e19fb9/src/hardware.c:60: void gfx_fill(u16 x,u16 y,u16 w,u16 h,u8 color){
;	---------------------------------
; Function gfx_fill
; ---------------------------------
_gfx_fill::
	push	ix
	ld	ix,	#0
	add	ix, sp
;work/candidates/8849a4e19fb9/src/hardware.c:61: if(!w||!h)return;
	ld	a, 5 (ix)
	or	a, 4 (ix)
	jr	z, 00116$
	ld	a, 7 (ix)
	or	a, 6 (ix)
	jr	z, 00116$
;work/candidates/8849a4e19fb9/src/hardware.c:62: color|=color<<4;
	ld	a, 8 (ix)
	add	a, a
	add	a, a
	add	a, a
	add	a, a
	or	a, 8 (ix)
	ld	8 (ix), a
;work/candidates/8849a4e19fb9/src/hardware.c:63: gfx_wait();hw_reg_select=36;
	push	hl
	push	de
	call	_gfx_wait
	pop	de
	pop	hl
	ld	a, #0x24
	out	(_hw_reg_select), a
;work/candidates/8849a4e19fb9/src/hardware.c:64: WORD(x);WORD(y);WORD(w);WORD(h);
	ld	a, l
	out	(_hw_reg_data), a
	ld	a, h
	out	(_hw_reg_data), a
	ld	a, e
	out	(_hw_reg_data), a
	ld	a, d
	out	(_hw_reg_data), a
	ld	a, 4 (ix)
	out	(_hw_reg_data), a
	ld	a, 5 (ix)
	out	(_hw_reg_data), a
	ld	a, 6 (ix)
	out	(_hw_reg_data), a
	ld	a, 7 (ix)
	out	(_hw_reg_data), a
;work/candidates/8849a4e19fb9/src/hardware.c:65: hw_reg_data=0;hw_reg_data=0x0c;hw_reg_data=0xff;hw_reg_data=0xff;
	xor	a, a
	out	(_hw_reg_data), a
	ld	a, #0x0c
	out	(_hw_reg_data), a
	ld	a, #0xff
	out	(_hw_reg_data), a
	ld	a, #0xff
	out	(_hw_reg_data), a
;work/candidates/8849a4e19fb9/src/hardware.c:66: hw_reg_data=color;hw_reg_data=color;reg_write(52,0x20);
	ld	a, 8 (ix)
	out	(_hw_reg_data), a
	out	(_hw_reg_data), a
	ld	l, #0x20
	ld	a, #0x34
	call	_reg_write
00116$:
;work/candidates/8849a4e19fb9/src/hardware.c:67: }
	pop	ix
	pop	hl
	pop	af
	pop	af
	inc	sp
	jp	(hl)
;work/candidates/8849a4e19fb9/src/hardware.c:68: void gfx_blit(u16 sx,u16 sy,u16 dx,u16 dy,u16 w,u16 h,u8 transparent){
;	---------------------------------
; Function gfx_blit
; ---------------------------------
_gfx_blit::
	push	ix
	ld	ix,	#0
	add	ix, sp
;work/candidates/8849a4e19fb9/src/hardware.c:69: if(!w||!h)return;
	ld	a, 9 (ix)
	or	a, 8 (ix)
	jr	z, 00122$
	ld	a, 11 (ix)
	or	a, 10 (ix)
	jr	z, 00122$
;work/candidates/8849a4e19fb9/src/hardware.c:70: gfx_wait();hw_reg_select=32;
	push	hl
	push	de
	call	_gfx_wait
	pop	de
	pop	hl
	ld	a, #0x20
	out	(_hw_reg_select), a
;work/candidates/8849a4e19fb9/src/hardware.c:71: WORD(sx);WORD(sy);WORD(dx);WORD(dy);WORD(w);WORD(h);
	ld	a, l
	out	(_hw_reg_data), a
	ld	a, h
	out	(_hw_reg_data), a
	ld	a, e
	out	(_hw_reg_data), a
	ld	a, d
	out	(_hw_reg_data), a
	ld	a, 4 (ix)
	out	(_hw_reg_data), a
	ld	a, 5 (ix)
	out	(_hw_reg_data), a
	ld	a, 6 (ix)
	out	(_hw_reg_data), a
	ld	a, 7 (ix)
	out	(_hw_reg_data), a
	ld	a, 8 (ix)
	out	(_hw_reg_data), a
	ld	a, 9 (ix)
	out	(_hw_reg_data), a
	ld	a, 10 (ix)
	out	(_hw_reg_data), a
	ld	a, 11 (ix)
	out	(_hw_reg_data), a
;work/candidates/8849a4e19fb9/src/hardware.c:72: hw_reg_data=0;hw_reg_data=transparent?0x1c:0x0c;
	xor	a, a
	out	(_hw_reg_data), a
	ld	a, 12 (ix)
	or	a, a
	ld	a, #0x1c
	jr	nz, 00125$
	ld	a, #0x0c
00125$:
	out	(_hw_reg_data), a
;work/candidates/8849a4e19fb9/src/hardware.c:73: hw_reg_data=0xff;hw_reg_data=0xff;reg_write(52,0x40);
	ld	a, #0xff
	out	(_hw_reg_data), a
	ld	a, #0xff
	out	(_hw_reg_data), a
	ld	l, #0x40
	ld	a, #0x34
	call	_reg_write
00122$:
;work/candidates/8849a4e19fb9/src/hardware.c:74: }
	pop	ix
	pop	hl
	ld	iy, #9
	add	iy, sp
	ld	sp, iy
	jp	(hl)
;work/candidates/8849a4e19fb9/src/hardware.c:78: void gfx_begin_spans(void){
;	---------------------------------
; Function gfx_begin_spans
; ---------------------------------
_gfx_begin_spans::
;work/candidates/8849a4e19fb9/src/hardware.c:79: gfx_wait();hw_reg_select=44;
	call	_gfx_wait
	ld	a, #0x2c
	out	(_hw_reg_select), a
;work/candidates/8849a4e19fb9/src/hardware.c:80: hw_reg_data=0;hw_reg_data=0x0c;hw_reg_data=0xff;hw_reg_data=0xff;
	xor	a, a
	out	(_hw_reg_data), a
	ld	a, #0x0c
	out	(_hw_reg_data), a
	ld	a, #0xff
	out	(_hw_reg_data), a
	ld	a, #0xff
	out	(_hw_reg_data), a
;work/candidates/8849a4e19fb9/src/hardware.c:81: }
	ret
;work/candidates/8849a4e19fb9/src/hardware.c:82: void gfx_span(s16 left,s16 right,u8 color){
;	---------------------------------
; Function gfx_span
; ---------------------------------
_gfx_span::
	push	ix
	ld	ix,	#0
	add	ix, sp
;work/candidates/8849a4e19fb9/src/hardware.c:84: if(left<0)left=0;if(right>256)right=256;
	bit	7, h
	jr	z, 00102$
	ld	hl, #0x0000
00102$:
	xor	a, a
	cp	a, e
	ld	a, #0x01
	sbc	a, d
	jp	po, 00142$
	xor	a, #0x80
00142$:
	jp	p, 00104$
	ld	de, #0x0100
00104$:
;work/candidates/8849a4e19fb9/src/hardware.c:85: if(right<=left)return;
	ld	a, l
	sub	a, e
	ld	a, h
	sbc	a, d
	jp	po, 00143$
	xor	a, #0x80
00143$:
	jp	m, 00106$
	jp	00116$
00106$:
;work/candidates/8849a4e19fb9/src/hardware.c:86: width=right-left;color|=color<<4;
	ld	a, e
	sub	a, l
	ld	c, a
	ld	a, d
	sbc	a, h
	ld	b, a
	ld	a, 4 (ix)
	add	a, a
	add	a, a
	add	a, a
	add	a, a
	or	a, 4 (ix)
	ld	4 (ix), a
;work/candidates/8849a4e19fb9/src/hardware.c:87: gfx_wait();hw_reg_select=36;
	push	hl
	push	bc
	call	_gfx_wait
	pop	bc
	pop	hl
	ld	a, #0x24
	out	(_hw_reg_select), a
;work/candidates/8849a4e19fb9/src/hardware.c:88: WORD(left);WORD(span_y);WORD(width);
	ld	a, l
	out	(_hw_reg_data), a
	ld	a, h
	out	(_hw_reg_data), a
	ld	a, (_span_y+0)
	out	(_hw_reg_data), a
	ld	a, (_span_y+1)
	out	(_hw_reg_data), a
	ld	a, c
	out	(_hw_reg_data), a
	ld	a, b
	out	(_hw_reg_data), a
;work/candidates/8849a4e19fb9/src/hardware.c:89: hw_reg_data=span_height;hw_reg_data=0;
	ld	a, (_span_height+0)
	out	(_hw_reg_data), a
	xor	a, a
	out	(_hw_reg_data), a
;work/candidates/8849a4e19fb9/src/hardware.c:90: hw_reg_select=48;hw_reg_data=color;hw_reg_data=color;
	ld	a, #0x30
	out	(_hw_reg_select), a
	ld	a, 4 (ix)
	out	(_hw_reg_data), a
	out	(_hw_reg_data), a
;work/candidates/8849a4e19fb9/src/hardware.c:91: reg_write(52,0x20);
	ld	l, #0x20
	ld	a, #0x34
	call	_reg_write
00116$:
;work/candidates/8849a4e19fb9/src/hardware.c:92: }
	pop	ix
	pop	hl
	inc	sp
	jp	(hl)
;work/candidates/8849a4e19fb9/src/hardware.c:93: void gfx_flip(u8 page){
;	---------------------------------
; Function gfx_flip
; ---------------------------------
_gfx_flip::
	ld	c, a
;work/candidates/8849a4e19fb9/src/hardware.c:94: gfx_wait();gfx_vblank();reg_write(18,page&1);
	push	bc
	call	_gfx_wait
	call	_gfx_vblank
	pop	bc
	ld	a, c
	and	a, #0x01
	ld	l, a
	ld	a, #0x12
	call	_reg_write
;work/candidates/8849a4e19fb9/src/hardware.c:95: while(hw_status&0x40){}
00101$:
	in	a, (_hw_status)
	bit	6, a
	jr	nz, 00101$
;work/candidates/8849a4e19fb9/src/hardware.c:96: }
	ret
;work/candidates/8849a4e19fb9/src/hardware.c:97: u8 input_read(void){
;	---------------------------------
; Function input_read
; ---------------------------------
_input_read::
;work/candidates/8849a4e19fb9/src/hardware.c:98: u8 k,result=0,ppi=hw_key_select,joy;
	ld	c, #0x00
	in	a, (_hw_key_select)
;work/candidates/8849a4e19fb9/src/hardware.c:99: hw_key_select=(ppi&0xf0)|8;k=(u8)~hw_key_data;
	ld	b, a
	and	a, #0xf0
	ld	e, a
	or	a, #0x08
	out	(_hw_key_select), a
	in	a, (_hw_key_data)
	cpl
;work/candidates/8849a4e19fb9/src/hardware.c:100: if(k&0x10)result|=INPUT_LEFT;if(k&0x80)result|=INPUT_RIGHT;
	bit	4, a
	jr	z, 00102$
	ld	c, #0x01
00102$:
	bit	7, a
	jr	z, 00104$
	set	1, c
00104$:
;work/candidates/8849a4e19fb9/src/hardware.c:101: if(k&0x20)result|=INPUT_UP;if(k&0x40)result|=INPUT_DOWN;
	bit	5, a
	jr	z, 00106$
	set	2, c
00106$:
	bit	6, a
	jr	z, 00108$
	set	3, c
00108$:
;work/candidates/8849a4e19fb9/src/hardware.c:102: if(k&1)result|=INPUT_FIRE;
	rrca
	jr	nc, 00110$
	set	4, c
00110$:
;work/candidates/8849a4e19fb9/src/hardware.c:103: hw_key_select=(ppi&0xf0)|5;
	ld	a, e
	or	a, #0x05
	out	(_hw_key_select), a
;work/candidates/8849a4e19fb9/src/hardware.c:104: if(!(hw_key_data&0x20))result|=INPUT_BRAKE;
	in	a, (_hw_key_data)
	bit	5, a
	jr	nz, 00112$
	set	5, c
00112$:
;work/candidates/8849a4e19fb9/src/hardware.c:105: hw_key_select=(ppi&0xf0)|7;
	ld	a, e
	or	a, #0x07
	out	(_hw_key_select), a
;work/candidates/8849a4e19fb9/src/hardware.c:106: if(!(hw_key_data&4))result|=INPUT_PAUSE;
	in	a, (_hw_key_data)
	bit	2, a
	jr	nz, 00114$
	set	6, c
00114$:
;work/candidates/8849a4e19fb9/src/hardware.c:107: hw_key_select=ppi;
	ld	a, b
	out	(_hw_key_select), a
;work/candidates/8849a4e19fb9/src/hardware.c:108: hw_psg_select=7;hw_psg_write=(hw_psg_read&0x3f)|0x80;
	ld	a, #0x07
	out	(_hw_psg_select), a
	in	a, (_hw_psg_read)
	and	a, #0x3f
	or	a, #0x80
	out	(_hw_psg_write), a
;work/candidates/8849a4e19fb9/src/hardware.c:109: hw_psg_select=15;joy=hw_psg_read;hw_psg_write=(joy&0xaf)|3;
	ld	a, #0x0f
	out	(_hw_psg_select), a
	in	a, (_hw_psg_read)
	ld	b, a
	and	a, #0xaf
	or	a, #0x03
	out	(_hw_psg_write), a
;work/candidates/8849a4e19fb9/src/hardware.c:110: hw_psg_select=14;k=(u8)~hw_psg_read;
	ld	a, #0x0e
	out	(_hw_psg_select), a
	in	a, (_hw_psg_read)
	cpl
;work/candidates/8849a4e19fb9/src/hardware.c:111: if(k&4)result|=INPUT_LEFT;if(k&8)result|=INPUT_RIGHT;
	bit	2, a
	jr	z, 00116$
	set	0, c
00116$:
	bit	3, a
	jr	z, 00118$
	set	1, c
00118$:
;work/candidates/8849a4e19fb9/src/hardware.c:112: if(k&1)result|=INPUT_UP;if(k&2)result|=INPUT_DOWN;
	bit	0, a
	jr	z, 00120$
	set	2, c
00120$:
	bit	1, a
	jr	z, 00122$
	set	3, c
00122$:
;work/candidates/8849a4e19fb9/src/hardware.c:113: if(k&0x10)result|=INPUT_FIRE;if(k&0x20)result|=INPUT_BRAKE;
	bit	4, a
	jr	z, 00124$
	set	4, c
00124$:
	bit	5, a
	jr	z, 00126$
	set	5, c
00126$:
;work/candidates/8849a4e19fb9/src/hardware.c:114: hw_psg_select=15;hw_psg_write=joy;return result;
	ld	a, #0x0f
	out	(_hw_psg_select), a
	ld	a, b
	out	(_hw_psg_write), a
	ld	a, c
;work/candidates/8849a4e19fb9/src/hardware.c:115: }
	ret
;work/candidates/8849a4e19fb9/src/hardware.c:116: static void psg(u8 r,u8 v){hw_psg_select=r;hw_psg_write=v;}
;	---------------------------------
; Function psg
; ---------------------------------
_psg:
	out	(_hw_psg_select), a
	ld	a, l
	out	(_hw_psg_write), a
	ret
;work/candidates/8849a4e19fb9/src/hardware.c:117: void engine_sound(u16 speed,u8 offroad,u8 muted){
;	---------------------------------
; Function engine_sound
; ---------------------------------
_engine_sound::
	push	ix
	ld	ix,	#0
	add	ix, sp
;work/candidates/8849a4e19fb9/src/hardware.c:118: u16 tone=820-speed*4;
	ld	c,l
	ld	b,h
	add	hl, hl
	add	hl, hl
	ld	a, #0x34
	sub	a, l
	ld	e, a
	ld	a, #0x03
	sbc	a, h
	ld	d, a
;work/candidates/8849a4e19fb9/src/hardware.c:119: psg(0,(u8)tone);psg(1,(u8)(tone>>8));
	ld	l, e
	push	hl
	push	bc
	push	de
	xor	a, a
	call	_psg
	pop	de
	ld	a, d
	push	de
	ld	l, a
	ld	a, #0x01
	call	_psg
	pop	de
	pop	bc
	pop	hl
;work/candidates/8849a4e19fb9/src/hardware.c:120: psg(2,(u8)(tone+9));psg(3,(u8)((tone+9)>>8));
	ld	a, l
	add	a, #0x09
	push	bc
	push	de
	ld	l, a
	ld	a, #0x02
	call	_psg
	pop	de
	pop	bc
	ld	hl, #0x0009
	add	hl, de
	ld	l, h
	push	bc
	ld	a, #0x03
	call	_psg
	pop	bc
;work/candidates/8849a4e19fb9/src/hardware.c:121: psg(6,offroad?12:4);
	ld	a, 4 (ix)
	or	a, a
	ld	l, #0x0c
	jr	nz, 00104$
	ld	l, #0x04
00104$:
	push	bc
	ld	a, #0x06
	call	_psg
;work/candidates/8849a4e19fb9/src/hardware.c:122: psg(7,0x9c); /* A+B tone, C noise; keep joystick port directions. */
	ld	l, #0x9c
	ld	a, #0x07
	call	_psg
	pop	bc
;work/candidates/8849a4e19fb9/src/hardware.c:123: psg(8,muted?0:7);psg(9,muted?0:5);
	ld	a, 5 (ix)
	or	a, a
	ld	l, #0x00
	jr	nz, 00106$
	ld	l, #0x07
00106$:
	push	bc
	ld	a, #0x08
	call	_psg
	pop	bc
	ld	a, 5 (ix)
	or	a, a
	ld	l, #0x00
	jr	nz, 00108$
	ld	l, #0x05
00108$:
	push	bc
	ld	a, #0x09
	call	_psg
	pop	bc
;work/candidates/8849a4e19fb9/src/hardware.c:124: psg(10,(!muted&&speed>12)?(offroad?6:3):0);
	ld	a, 5 (ix)
	or	a, a
	jr	nz, 00109$
	ld	a, #0x0c
	cp	a, c
	ld	a, #0x00
	sbc	a, b
	jr	nc, 00109$
	ld	a, 4 (ix)
	or	a, a
	jr	z, 00114$
	ld	l, #0x06
	jp	00110$
00114$:
	ld	l, #0x03
	jp	00110$
00109$:
	ld	l, #0x00
00110$:
	ld	a, #0x0a
	call	_psg
;work/candidates/8849a4e19fb9/src/hardware.c:125: }
	pop	ix
	pop	hl
	pop	af
	jp	(hl)
	.area _CODE
	.area _INITIALIZER
	.area _CABS (ABS)
