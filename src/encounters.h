/* v0.4: ordinary traffic and one clearly announced pasture UFO encounter.
 * Included after the shared drawing helpers; no extra input or camera shake.
 */
#ifndef ALPINE_ENCOUNTERS_H
#define ALPINE_ENCOUNTERS_H
#define TRAFFIC_COUNT 3

volatile u16 traffic_z[3],passes,hits,ufo_dodges,ufo_catches,event_tick,ufo_lap;
volatile s8 traffic_lane[3],ufo_lane;
volatile u8 traffic_tag[3],ufo_state,ufo_timer,ufo_caught,recovery_timer,lift_timer;
u16 traffic_gap[3],traffic_previous_gap[3];
s16 traffic_screen_x[3],traffic_screen_y[3];
u8 traffic_size[3],traffic_clip[3],traffic_width[3],traffic_visible[3],traffic_order[3];
u8 notice,notice_timer;
u16 cached_passes;
u8 traffic_scale_lut[513];

static void init_encounters(void){
    u8 i;
    u16 gap;
    /* The same nearest-depth choice, calculated once instead of searching
     * sixteen 16-bit depth values for each visible car on every frame. */
    i=0;
    for(gap=0;gap<=512;++gap){
        if(i<15&&gap>((event_depth[i]+event_depth[i+1])>>1))++i;
        traffic_scale_lut[gap]=i;
    }
    traffic_z[0]=220;traffic_z[1]=720;traffic_z[2]=1250;
    for(i=0;i<3;++i){
        traffic_lane[i]=(i&1)?1:-1;traffic_tag[i]=0;
        traffic_previous_gap[i]=traffic_z[i];traffic_visible[i]=0;
    }
    passes=0;hits=0;ufo_dodges=0;ufo_catches=0;event_tick=0;
    ufo_lap=65535;ufo_state=0;ufo_timer=0;ufo_lane=1;ufo_caught=0;
    recovery_timer=0;lift_timer=0;notice=0;notice_timer=0;
    cached_passes=65535;
}
static s16 beam_screen_x(void){
    u8 w=profile[121];
    s16 c=128+(s8)profile[120]-camera_shift(w>>1);
    return c+(ufo_lane>0?(s16)(w>>1):-(s16)(w>>1));
}
static void prepare_traffic(void){
    u8 i,j,k,t,*p,visible=0;
    u16 gap;
    for(i=0;i<3;++i){
        traffic_order[i]=i;traffic_visible[i]=0;
        gap=(traffic_z[i]-distance)&4095;traffic_gap[i]=gap;
        if(!mode||!gap||gap>512)continue;
        k=traffic_scale_lut[gap];
        p=profile+EVENT_PROJECT_OFFSET+((u16)k<<2);
        traffic_size[i]=k;traffic_width[i]=p[2];traffic_clip[i]=p[3];
        traffic_screen_x[i]=128+(s8)p[0]-camera_shift(p[2]>>1)
            +(traffic_lane[i]>0?(s16)(p[2]>>1):-(s16)(p[2]>>1));
        traffic_screen_y[i]=p[1];
        /* Continue out through the bottom of the view, not a near-plane pop. */
        if(gap<28)traffic_screen_y[i]+=(28-gap)<<2;
        traffic_visible[i]=1;++visible;
    }
    if(!visible)return;
    for(i=0;i<2;++i)for(j=i+1;j<3;++j){
        if(traffic_gap[traffic_order[i]]<traffic_gap[traffic_order[j]]){
            t=traffic_order[i];traffic_order[i]=traffic_order[j];traffic_order[j]=t;
        }
    }
}
static void draw_one_traffic(u8 i){
    const Sprite *s;
    if(!traffic_visible[i])return;
    s=&traffic_car[traffic_size[i]];
    sprite(s,traffic_screen_x[i]-s->w/2,traffic_screen_y[i]-s->h,traffic_clip[i]);
}
static void step_encounters(void){
    u8 i;
    s16 dx;
    u16 gap;
    if(mode==1){
        ++event_tick;
        if(notice_timer)--notice_timer;
        if(lift_timer)--lift_timer;
        if(recovery_timer){--recovery_timer;if(speed>80)speed=80;}
        for(i=0;i<3;++i){
            traffic_previous_gap[i]=(traffic_z[i]-distance)&4095;
            traffic_z[i]=(traffic_z[i]+3)&4095;
            gap=(traffic_z[i]-distance)&4095;
            if(gap<=12){
                /* A vehicle coming from behind is not an earned overtake. */
                if(!traffic_tag[i]&&traffic_previous_gap[i]<128){
                    if(passes<999)++passes;notice=1;notice_timer=36;
                }
                traffic_z[i]=(distance+1400+(u16)i*240)&4095;
                traffic_lane[i]=-traffic_lane[i];traffic_tag[i]=0;
            }
        }
        if(ufo_state){
            if(ufo_timer)--ufo_timer;
            if(!ufo_timer){
                if(ufo_state==1){ufo_state=2;ufo_timer=45;}
                else if(ufo_state==2){ufo_state=3;ufo_timer=60;}
                else if(ufo_state==3){
                    ufo_state=4;ufo_timer=30;
                    if(!ufo_caught){++ufo_dodges;notice=6;notice_timer=45;}
                }else ufo_state=0;
            }
        }else if(ufo_lap!=laps&&distance>=1550&&distance<1750){
            ufo_lap=laps;ufo_state=1;ufo_timer=30;ufo_caught=0;
            ufo_lane=(laps&1)?-1:1;
        }
    }
    prepare_traffic();
    if(mode!=1)return;
    for(i=0;i<3;++i){
        if(traffic_tag[i]||!traffic_visible[i]||traffic_gap[i]>72
           ||traffic_gap[i]<28||traffic_clip[i]<165)continue;
        if(traffic_screen_y[i]<165||traffic_screen_y[i]-traffic_car[traffic_size[i]].h>=184)continue;
        dx=traffic_screen_x[i]-(128+player_x/4);if(dx<0)dx=-dx;
        if(dx<15+(traffic_car[traffic_size[i]].w>>1)){
            traffic_tag[i]=1;++hits;if(speed>72)speed=72;
            recovery_timer=20;notice=2;notice_timer=30;
        }
    }
    if(ufo_state==3&&!ufo_caught){
        dx=beam_screen_x()-(128+player_x/4);if(dx<0)dx=-dx;
        if(dx<42){
            ufo_caught=1;++ufo_catches;if(speed>56)speed=56;
            lift_timer=30;recovery_timer=24;notice=5;notice_timer=40;
        }
    }
}
static u8 car_lift(void){
    u8 t;
    if(!lift_timer)return 0;
    t=30-lift_timer;
    if(t<10)return t*2;
    if(t<20)return 20;
    return (30-t)*2;
}
static void draw_encounter_world(void){
    s16 bx,cx,cy,sy,beam_c,step;
    u8 i,half;
    if(!mode||!ufo_state)return;
    bx=beam_screen_x();cx=bx;if(cx<28)cx=28;if(cx>228)cx=228;
    cy=35;
    if(ufo_state==1)cy-=ufo_timer;
    if(ufo_state==4)cy-=(30-ufo_timer)*3;
    if(ufo_state==1){
        sy=133-(30-ufo_timer)*2;
        sprite(&cow[0],cx-10,sy,186);
        rect(cx,cy+20,1,sy-cy-20,COL_SKY_LIGHT);
    }else if(ufo_state==2){
        if(ufo_timer>35)sprite(&cow[0],cx-10,68-(45-ufo_timer)*2,186);
        /* A visible footprint precedes the damaging light by 45 frames. */
        rect(bx-28,178,56,2,COL_WHITE);
        rect(bx-28,168,2,10,COL_SKY_LIGHT);rect(bx+26,168,2,10,COL_SKY_LIGHT);
    }else if(ufo_state==3){
        /* Open scan-lines keep the road and the safe side readable. */
        beam_c=cx;step=(bx-cx)/8;
        for(i=0;i<8;++i){
            half=6+i*3;
            rect(beam_c-half,64+(u16)i*16,half*2,2,((i+(event_tick>>2))&1)?COL_SKY_LIGHT:COL_WHITE);
            beam_c+=step;
        }
        rect(bx-28,178,56,4,COL_SKY_LIGHT);
    }
    sprite(&ufo[0],cx-26,cy,186);
}
static void build_encounter_ui(void){
    draw_page=5;rect(0,0,256,128,COL_DARK);
    text(4,2,"PASS");
    text(4,18,"CLEAN PASS!");text(4,34,"EASY! KEEP GOING");
    text(4,50,"LOOK UP!");text(4,66,"UFO: KEEP LEFT");
    text(4,82,"BACK ON THE ROAD");text(4,98,"UFO CLEAR!");
    text(4,114,"UFO: KEEP RIGHT");
    gfx_wait();draw_page=1;
}
static void draw_encounter_ui(void){
    u8 msg=notice_timer?notice:0;
    u8 saved_page;
    if(!mode)return;
    if(passes!=cached_passes){
        saved_page=draw_page;draw_page=5;
        rect(53,2,18,8,COL_DARK);number(53,2,passes);
        draw_page=saved_page;cached_passes=passes;
    }
    gfx_blit(0,1280,166,page_y()+4,90,12,0);
    if(ufo_state==1)msg=3;
    if(ufo_state==2||ufo_state==3)msg=ufo_caught?5:(ufo_lane>0?4:7);
    if(msg)gfx_blit(0,1280+(u16)msg*16,76,page_y()+19,104,12,0);
}
#endif
