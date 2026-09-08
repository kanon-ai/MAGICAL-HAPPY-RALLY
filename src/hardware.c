/* B1/ASCII8 foundation adapted from the user's NEON REVENANT hardware layer.
 * New drive renderer uses palette indices directly; all code runs in RAM.
 */
#include "hardware.h"
#include "palette.h"
__sfr __at(0x60) hw_vram;
__sfr __at(0x61) hw_palette;
__sfr __at(0x63) hw_reg_data;
__sfr __at(0x64) hw_reg_select;
__sfr __at(0x65) hw_status;
__sfr __at(0x66) hw_irq_flags;
__sfr __at(0x67) hw_system;
__sfr __at(0xa0) hw_psg_select;
__sfr __at(0xa1) hw_psg_write;
__sfr __at(0xa2) hw_psg_read;
__sfr __at(0xa9) hw_key_data;
__sfr __at(0xaa) hw_key_select;
static void reg_write(u8 r,u8 v){hw_reg_select=r;hw_reg_data=v;}
#define WORD(v) do{hw_reg_data=(u8)(v);hw_reg_data=(u8)((v)>>8);}while(0)
u16 span_y;
u8 span_height;
void gfx_wait(void){while(hw_status&1){}}
void gfx_vblank(void){while(hw_status&0x40){} while(!(hw_status&0x40)){}}
void gfx_init(void){
    u8 i;
    __asm di __endasm;
    hw_system=2;hw_system=0;
    hw_reg_select=0;for(i=0;i<29;++i)hw_reg_data=0;
    hw_irq_flags=7;
    reg_write(6,0x81);reg_write(7,0);reg_write(8,0x42);
    reg_write(13,0);reg_write(14,0);
    for(i=0;i<48;++i)hw_palette=v9990_palette[i];
    gfx_vblank();gfx_fill(0,0,256,512,0);gfx_wait();
}
static void upload_bank(void) __naked{
    __asm
    ld hl,#0x6000
    ld c,#0x60
    ld e,#32
drive_upload_loop:
    ld b,#0
    otir
    dec e
    jr nz,drive_upload_loop
    ret
    __endasm;
}
void hardware_upload(void){
    u8 bank;
    gfx_wait();hw_reg_select=0;hw_reg_data=0;hw_reg_data=0;hw_reg_data=1;
    for(bank=4;bank<12;++bank){*((volatile u8*)0x6800)=bank;upload_bank();}
    /* Extra landscape atlas, beyond the existing static UI cache. */
    hw_reg_select=0;hw_reg_data=0;hw_reg_data=0;hw_reg_data=3;
    for(bank=44;bank<60;++bank){*((volatile u8*)0x6800)=bank;upload_bank();}
    reg_write(8,0xc2);gfx_vblank();
}
/* Fast paths. Caller clips all rectangles to 256x212; zero size is rejected
 * because zero has a special large-area meaning to the V9990 command engine.
 */
void gfx_fill(u16 x,u16 y,u16 w,u16 h,u8 color){
    if(!w||!h)return;
    color|=color<<4;
    gfx_wait();hw_reg_select=36;
    WORD(x);WORD(y);WORD(w);WORD(h);
    hw_reg_data=0;hw_reg_data=0x0c;hw_reg_data=0xff;hw_reg_data=0xff;
    hw_reg_data=color;hw_reg_data=color;reg_write(52,0x20);
}
void gfx_blit(u16 sx,u16 sy,u16 dx,u16 dy,u16 w,u16 h,u8 transparent){
    if(!w||!h)return;
    gfx_wait();hw_reg_select=32;
    WORD(sx);WORD(sy);WORD(dx);WORD(dy);WORD(w);WORD(h);
    hw_reg_data=0;hw_reg_data=transparent?0x1c:0x0c;
    hw_reg_data=0xff;hw_reg_data=0xff;reg_write(52,0x40);
}
/* All road spans share a known Y/height and COPY mode. Setting these outside
 * the pixel-span calculation avoids repeated general rectangle clipping.
 */
void gfx_begin_spans(void){
    gfx_wait();hw_reg_select=44;
    hw_reg_data=0;hw_reg_data=0x0c;hw_reg_data=0xff;hw_reg_data=0xff;
}
void gfx_span(s16 left,s16 right,u8 color){
    u16 width;
    if(left<0)left=0;if(right>256)right=256;
    if(right<=left)return;
    width=right-left;color|=color<<4;
    gfx_wait();hw_reg_select=36;
    WORD(left);WORD(span_y);WORD(width);
    hw_reg_data=span_height;hw_reg_data=0;
    hw_reg_select=48;hw_reg_data=color;hw_reg_data=color;
    reg_write(52,0x20);
}
void gfx_flip(u8 page){
    gfx_wait();gfx_vblank();reg_write(18,page&1);
    while(hw_status&0x40){}
}
u8 input_read(void){
    u8 k,result=0,ppi=hw_key_select,joy;
    hw_key_select=(ppi&0xf0)|8;k=(u8)~hw_key_data;
    if(k&0x10)result|=INPUT_LEFT;if(k&0x80)result|=INPUT_RIGHT;
    if(k&0x20)result|=INPUT_UP;if(k&0x40)result|=INPUT_DOWN;
    if(k&1)result|=INPUT_FIRE;
    hw_key_select=(ppi&0xf0)|5;
    if(!(hw_key_data&0x20))result|=INPUT_BRAKE;
    hw_key_select=(ppi&0xf0)|7;
    if(!(hw_key_data&4))result|=INPUT_PAUSE;
    hw_key_select=ppi;
    hw_psg_select=7;hw_psg_write=(hw_psg_read&0x3f)|0x80;
    hw_psg_select=15;joy=hw_psg_read;hw_psg_write=(joy&0xaf)|3;
    hw_psg_select=14;k=(u8)~hw_psg_read;
    if(k&4)result|=INPUT_LEFT;if(k&8)result|=INPUT_RIGHT;
    if(k&1)result|=INPUT_UP;if(k&2)result|=INPUT_DOWN;
    if(k&0x10)result|=INPUT_FIRE;if(k&0x20)result|=INPUT_BRAKE;
    hw_psg_select=15;hw_psg_write=joy;return result;
}
static void psg(u8 r,u8 v){hw_psg_select=r;hw_psg_write=v;}
void engine_sound(u16 speed,u8 offroad,u8 muted){
    u16 tone=820-speed*4;
    psg(0,(u8)tone);psg(1,(u8)(tone>>8));
    psg(2,(u8)(tone+9));psg(3,(u8)((tone+9)>>8));
    psg(6,offroad?12:4);
    psg(7,0x9c); /* A+B tone, C noise; keep joystick port directions. */
    psg(8,muted?0:7);psg(9,muted?0:5);
    psg(10,(!muted&&speed>12)?(offroad?6:3):0);
}
