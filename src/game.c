/* MAGICAL HAPPY RALLY v0.4 — original native turbo R / V9990 drive prototype.
 * No host-side simulation. All gameplay, input, sound and drawing run here.
 */
#include "hardware.h"
#include "assets.h"
#include "palette.h"
#include "course.h"
#include "scenery.h"

volatile u8 ready,mode,keys,offroad,section;
volatile u16 frame_counter,distance,speed,course_phase,laps;
volatile s16 player_x,road_center,hill;
volatile s8 course_curve;
u8 old_keys,draw_page,profile[256],distance_fraction;
u16 loaded_phase;
static const char * const names[8]={
    "HIGHLAND TRAIL","PINE RIDGE","THE LONG CLIMB","OPEN SKY",
    "VALLEY RUN","FOREST BEND","LAKESIDE","HOMEWARD"};

static u16 page_y(void){return (u16)draw_page<<8;}
/* R800 unsigned 8x8 multiply, ED C9 = MULUB A,C. SDCC call1 passes
 * half-width in A and returns the signed 16-bit result in DE. Work with
 * the magnitude before shifting to preserve C's division toward zero.
 * This cartridge explicitly targets turbo R in R800 mode.
 */
static s16 camera_shift(u8 halfwidth) __naked{
    halfwidth;
    __asm
    ld c,a
    ld a,(_player_x+1)
    ld b,a
    ld a,(_player_x)
    bit 7,b
    jr z,drive_multiply
    neg
drive_multiply:
    .db 0xed,0xc9
    .rept 6
    srl h
    rr l
    .endm
    bit 7,b
    jr z,drive_positive
    xor a
    sub l
    ld e,a
    sbc a,a
    sub h
    ld d,a
    ret
drive_positive:
    ex de,hl
    ret
    __endasm;
}
static void rect(s16 x,s16 y,s16 w,s16 h,u8 color){
    if(x<0){w+=x;x=0;}if(y<0){h+=y;y=0;}
    if(x+w>256)w=256-x;if(y+h>212)h=212-y;
    if(w>0&&h>0)gfx_fill(x,page_y()+y,w,h,color);
}
static void sprite(const Sprite *s,s16 x,s16 y,s16 bottom){
    s16 sx=s->x,sy=s->y,w=s->w,h=s->h;
    if(x<0){sx-=x;w+=x;x=0;}
    if(y<0){sy-=y;h+=y;y=0;}
    if(x+w>256)w=256-x;if(y+h>bottom)h=bottom-y;
    if(w>0&&h>0)gfx_blit(sx,sy,x,page_y()+y,w,h,1);
}
static void text(s16 x,s16 y,const char *p){
    while(*p){u8 c=*p++;
        if(c>=32&&c<128&&x>=0&&x<251&&y>=0&&y<205){
            const Sprite *s=&font[c-32];
            gfx_blit(s->x,s->y,x,page_y()+y,6,8,1);
        }x+=6;
    }
}
static void number(s16 x,s16 y,u16 v){
    char b[4];b[3]=0;b[2]='0'+v%10;v/=10;
    b[1]='0'+v%10;b[0]='0'+v/10;text(x,y,b);
}
/* SDCC call1 supplies the source pointer in HL. This is exactly the old
 * 256-byte profile copy, with no conversion or geometry changes. */
static void copy_course_profile(const u8 *src) __naked{
    src;
    __asm
    ld de,#_profile
    ld bc,#256
    ldir
    ret
    __endasm;
}
static void load_course(void){
    const u8 *src;
    course_phase=(distance>>2)&1023;
    if(loaded_phase!=course_phase){
        *((volatile u8*)0x6800)=COURSE_BANK+(u8)(course_phase>>5);
        src=(const u8*)(0x6000+((course_phase&31)<<8));
        copy_course_profile(src);
        loaded_phase=course_phase;
    }
    hill=(s16)profile[123]-91;course_curve=(s8)profile[124];section=profile[126];
}
static void update(void){
    u8 edge=keys&(u8)~old_keys;
    s16 steering;
    u16 advance;
    if(mode==0){
        if(keys&(INPUT_FIRE|INPUT_UP)){mode=1;speed=0;}
        else return;
    }
    if(edge&INPUT_PAUSE){mode=mode==2?1:2;}
    if(mode!=1)return;
    if(keys&(INPUT_DOWN|INPUT_BRAKE))speed=speed>5?speed-5:0;
    else if(keys&(INPUT_UP|INPUT_FIRE)){if(speed<126)speed+=2;else speed=128;}
    else if(speed)--speed;

    steering=0;
    if(speed){
        if(keys&INPUT_LEFT)steering-=1+(speed>>6);
        if(keys&INPUT_RIGHT)steering+=1+(speed>>6);
        player_x+=steering;
        /* Gentle outward drift, without binary lane changes or auto-steering. */
        if(speed>64&&!(frame_counter&7))player_x-=course_curve/16;
    }
    if(player_x>144)player_x=144;if(player_x< -144)player_x=-144;
    offroad=player_x>104||player_x< -104;
    if(offroad&&speed>64)speed-=3;
    advance=(u16)distance_fraction+speed+(speed>>1);
    distance_fraction=(u8)(advance&31);
    distance+=advance>>5;
    if(distance>=4096){distance-=4096;++laps;}
}
static void draw_sky(void){
    s16 h=profile[123],heading=(s8)profile[127]+player_x/12;
    u16 sy=SKY_Y+(112-h)/2;
    u16 clouds=44-(112-h)/2;
    u16 pan=(heading/4)&255;
    /* The sky and mountain ranges turn at different rates. Keep mountain
     * volume at native height instead of squeezing it into a short strip. */
    if(pan){
        gfx_blit(pan,sy,0,page_y(),256-pan,clouds,0);
        gfx_blit(0,sy,256-pan,page_y(),pan,clouds,0);
    }else gfx_blit(0,sy,0,page_y(),256,clouds,0);
    pan=(heading/2)&255;
    if(pan){
        gfx_blit(pan,SKY_Y+44,0,page_y()+clouds,256-pan,h-clouds,0);
        gfx_blit(0,SKY_Y+44,256-pan,page_y()+clouds,pan,h-clouds,0);
    }else gfx_blit(0,SKY_Y+44,0,page_y()+clouds,256,h-clouds,0);
    gfx_fill(0,page_y()+h,256,186-h,COL_GRASS);
}
static void draw_road(void){
    u8 i,*p=profile;
    s16 c,edge,shift;
    u8 flag,w;
    gfx_begin_spans();
    for(i=0;i<COURSE_BANDS;++i,p+=3){
        w=p[1];if(!w)continue;
        span_y=page_y()+band_y[i];span_height=band_h[i];flag=p[2]&1;
        /* Halve first to keep products in signed 16-bit range at road edges. */
        shift=camera_shift(w>>1);
        c=128+(s8)p[0]-shift;
        if(i==COURSE_BANDS-1)road_center=c-128;
        if(flag){
            /* Ground shade follows the shoulders, not full-screen bars. */
            /* Road paint immediately covers the middle: one transfer has
             * the same visible shoulders with less command setup overhead. */
            gfx_span(c-3*w,c+3*w,COL_GRASS_ALT);
        }
        edge=1+(w>>4);
        gfx_span(c-w-edge,c+w+edge,COL_VERGE);
        gfx_span(c-w,c+w,flag?COL_ROAD_LIGHT:COL_ROAD);
        /* Two sparse gravel tracks, anchored in the projected road surface. */
        if(flag&&i>36){
            gfx_span(c-(w>>2),c-(w>>2)+1+(w>>6),COL_ROAD);
            gfx_span(c+(w>>2),c+(w>>2)+1+(w>>6),COL_ROAD);
        }
    }
}
#include "encounters.h"
#include "lap_clock.h"
static void draw_objects(void){
    u8 i,*p=profile+128,size,kind,ti=0,car_id;
    s16 x,y,clip;
    const Sprite *s;
    for(i=0;i<8;++i,p+=8){
        if(!p[7])continue;
        while(ti<3){
            car_id=traffic_order[ti];
            if(traffic_visible[car_id]&&traffic_width[car_id]>p[7])break;
            draw_one_traffic(car_id);++ti;
        }
        x=(s16)((u16)p[0]|((u16)p[1]<<8));
        y=(s16)((u16)p[2]|((u16)p[3]<<8));
        size=p[4];kind=p[5];clip=p[6];
        x-=camera_shift(p[7]>>1);
        if(kind==0)s=&grand_pines[size];
        else if(kind==2)s=&crags[size];
        else if(kind==3)s=&bushes[size];
        else s=&rocks[size];
        sprite(s,x-s->w/2,y-s->h,clip);
    }
    while(ti<3){draw_one_traffic(traffic_order[ti]);++ti;}
}
static void build_ui(void){
    u8 i;
    /* Runtime-generated static panels live outside the uploaded atlas. */
    draw_page=4;
    rect(0,0,256,212,COL_DARK);
    text(29,5,"KM/H");text(82,5,"TRAIL");text(216,5,"ROAD");
    text(8,16,"ARROWS / SPACE  X:BRAKE  ESC:PAUSE");
    for(i=0;i<8;++i)text(4,34+i*12,names[i]);
    text(59,137,"MAGICAL HAPPY RALLY 0.4");
    text(43,150,"A LITTLE CAR. A BIG SKY.");
    text(67,163,"SPACE TO DRIVE");
    text(109,180,"PAUSE");text(82,191,"ESC TO CONTINUE");
    gfx_wait();draw_page=1;
}
static void draw_ui(void){
    const Sprite *s;
    u8 pose=1;
    s16 cx=128+player_x/4;
    if(speed&&keys&INPUT_LEFT)pose=0;
    if(speed&&keys&INPUT_RIGHT)pose=2;
    if(lift_timer)sprite(&car_shadow[0],cx-28,178,186);
    s=&driving_car[pose];sprite(s,cx-s->w/2,184-s->h-car_lift(),186);
    draw_lap_clock();
    gfx_blit(0,1024,0,page_y()+186,256,26,0);
    number(8,191,(speed*5)>>2);
    rect(118,192,84,5,COL_GRASS);
    rect(118,192,(distance*5)>>8,5,COL_WHITE);
    if(offroad){rect(216,191,24,8,COL_DARK);text(216,191,"EDGE");}
    gfx_blit(0,1056+(u16)section*12,5,page_y()+4,112,12,0);
    draw_encounter_ui();
    if(mode==0){
        gfx_blit(30,1156,30,page_y()+29,196,44,0);
    }else if(mode==2){
        gfx_blit(72,1200,72,page_y()+46,112,26,0);
    }
}
/* Debug breakpoint hook: front VRAM page is complete and visible here. */
void frame_done(void){++frame_counter;}
void main(void){
    ready=0;mode=0;frame_counter=0;distance=0;speed=0;player_x=0;
    distance_fraction=0;laps=0;keys=0;old_keys=0;draw_page=1;
    loaded_phase=65535;offroad=0;
    init_encounters();
    init_lap_clock();
    gfx_init();hardware_upload();build_ui();build_encounter_ui();load_course();
    ready=0xa5;
    for(;;){
        keys=input_read();update();load_course();
        step_encounters();
        step_lap_clock();
        engine_sound(speed,offroad,mode!=1);
        draw_sky();draw_road();draw_objects();draw_encounter_world();draw_ui();
        gfx_flip(draw_page);frame_done();draw_page^=1;old_keys=keys;
    }
}
