/* Time attack is an optional record, never a deadline or a game-over rule.
 * Included after the shared state and drawing helpers in game.c.
 *
 * The turbo R E6 timer runs at 3579545 / 14 Hz. E6/E7 reads are not
 * latched (openMSX MSXE6Timer::peekIO); high-low-high retry avoids a torn
 * read at low-byte rollover. We never reset the shared hardware timer.
 * A 16-bit delta is unambiguous when sampled at least every 256 ms.
 */
#ifndef ALPINE_LAP_CLOCK_H
#define ALPINE_LAP_CLOCK_H

__sfr __at(0xe6) lap_timer_low;
__sfr __at(0xe7) lap_timer_high;

/* Unsigned 32-bit deciseconds: neither a stopped car nor a slow lap times
 * out. Last and best are session records; restarting the ROM clears them.
 */
volatile unsigned long lap_current_tenths,lap_last_tenths,lap_best_tenths;
volatile u8 lap_last_valid,lap_best_valid;
unsigned long lap_tick_fraction,lap_cached_current,lap_cached_best;
u16 lap_previous_timer,lap_previous_laps;
u8 lap_previous_mode,lap_cache_ready,lap_cached_best_valid;
char lap_current_text[13],lap_best_text[13];

static u16 read_lap_timer(void){
    u8 high,low;
    do{high=lap_timer_high;low=lap_timer_low;}while(high!=lap_timer_high);
    return ((u16)high<<8)|low;
}

static void init_lap_clock(void){
    u8 i;
    lap_current_tenths=0;lap_last_tenths=0;lap_best_tenths=0;
    lap_last_valid=0;lap_best_valid=0;lap_tick_fraction=0;
    lap_previous_timer=read_lap_timer();lap_previous_laps=laps;
    lap_previous_mode=mode;lap_cache_ready=0;
    lap_cached_current=0;lap_cached_best=0;lap_cached_best_valid=0;
    for(i=0;i<13;++i){lap_current_text[i]=0;lap_best_text[i]=0;}
}

static void step_lap_clock(void){
    u16 now=read_lap_timer(),delta=now-lap_previous_timer;
    lap_previous_timer=now;
    /* Account for the mode during the interval just elapsed: the frame
     * entering pause still counts, while the frame leaving it does not.
     * Sampling in title/pause prevents their timer wraps from leaking in.
     */
    if(lap_previous_mode==1){
        /* Exact rational conversion, with no frame-count assumption and
         * no division per frame. delta * 140 / 3579545 yields deciseconds.
         */
        lap_tick_fraction+=(unsigned long)delta*140UL;
        while(lap_tick_fraction>=3579545UL){
            lap_tick_fraction-=3579545UL;++lap_current_tenths;
        }
        if(laps!=lap_previous_laps){
            lap_last_tenths=lap_current_tenths;lap_last_valid=1;
            if(!lap_best_valid||lap_last_tenths<lap_best_tenths){
                lap_best_tenths=lap_last_tenths;lap_best_valid=1;
            }
            lap_current_tenths=0;lap_tick_fraction=0;
        }
    }
    lap_previous_laps=laps;lap_previous_mode=mode;
}

static void format_lap_time(char *out,unsigned long tenths){
    char reverse[10];
    u8 n=0;
    u16 tail,short_minutes;
    unsigned long minutes;
    /* Seeding and lap completion are infrequent. Still use 16-bit math
     * for ordinary laps; long-session records retain the full u32 range.
     */
    if(tenths<65536UL){
        tail=(u16)tenths%600;short_minutes=(u16)tenths/600;
        do{reverse[n++]='0'+short_minutes%10;short_minutes/=10;}while(short_minutes);
    }else{
        tail=(u16)(tenths%600UL);minutes=tenths/600UL;
        do{reverse[n++]='0'+(u8)(minutes%10UL);minutes/=10UL;}while(minutes);
    }
    if(n<2)reverse[n++]='0';
    while(n)*out++=reverse[--n];
    *out++=':';*out++='0'+tail/100;*out++='0'+(tail/10)%10;
    *out++='.';*out++='0'+tail%10;*out=0;
}

static void increment_lap_text(char *value){
    u8 length=0;
    s8 i;
    while(value[length])++length;
    /* Ordinary 0.1-second ticks need no division or full reformatting. */
    for(i=(s8)length-1;i>=0;--i){
        if(value[i]==':'||value[i]=='.')continue;
        ++value[i];
        if(value[i]<(i==(s8)length-4?'6':':'))return;
        value[i]='0';
    }
    /* 99:59.9 -> 100:00.0 (and subsequent minute-column expansion). */
    for(i=(s8)length;i>=0;--i)value[i+1]=value[i];
    value[0]='1';
}

static void copy_lap_text(u16 x,char *cached,const char *value){
    u8 old_length=0,new_length=0,i,c,glyph;
    while(cached[old_length])++old_length;
    while(value[new_length])++new_length;
    for(i=0;i<old_length||i<new_length;++i){
        c=i<new_length?value[i]:' ';
        if(i>=old_length||c!=cached[i]){
            if(c>='0'&&c<='9')glyph=c-'0';
            else if(c==':')glyph=10;
            else if(c=='.')glyph=11;
            else if(c=='-')glyph=12;
            else glyph=13;
            /* Cached glyph already includes its dark background. One
             * opaque copy replaces a digit without a separate clear.
             */
            gfx_blit((u16)glyph*6,1424,x+(u16)i*6,1040,6,8,0);
        }
        cached[i]=i<new_length?c:0;
    }
    cached[new_length]=0;
}

static void draw_lap_clock(void){
    u8 saved_page,i;
    char value[13];
    if(!mode)return;
    if(lap_cache_ready&&lap_cached_current==lap_current_tenths
       &&lap_cached_best_valid==lap_best_valid&&lap_cached_best==lap_best_tenths)return;
    saved_page=draw_page;draw_page=4;
    /* Replace only the instruction row in the existing HUD cache, VRAM
     * y1038..1049. The caller's regular HUD copy also draws this clock:
     * no additional per-frame blit. Title keeps the original instructions.
     * Only actual changed characters are copied. A normal tenth is one
     * 6 x 8 opaque blit; no seven-character redraw and no long division.
     */
    if(!lap_cache_ready){
        /* Spare VRAM y1424..1431 is disjoint from encounter panels and
         * the landscape atlas. Digits, punctuation and blank are cached.
         */
        draw_page=5;rect(0,144,84,8,COL_DARK);text(0,144,"0123456789:.- ");
        draw_page=4;
        rect(0,14,256,12,COL_DARK);
        text(6,16,"TIME");text(132,16,"BEST");
    }
    if(!lap_cache_ready||lap_cached_current!=lap_current_tenths){
        if(lap_cache_ready&&lap_current_tenths&&lap_current_tenths==lap_cached_current+1UL){
            for(i=0;i<13;++i)value[i]=lap_current_text[i];
            increment_lap_text(value);
        }else format_lap_time(value,lap_current_tenths);
        copy_lap_text(38,lap_current_text,value);
        lap_cached_current=lap_current_tenths;
    }
    if(!lap_cache_ready||lap_cached_best_valid!=lap_best_valid
       ||lap_cached_best!=lap_best_tenths){
        if(lap_best_valid){format_lap_time(value,lap_best_tenths);copy_lap_text(164,lap_best_text,value);}
        else copy_lap_text(164,lap_best_text,"--:--.-");
        lap_cached_best=lap_best_tenths;lap_cached_best_valid=lap_best_valid;
    }
    lap_cache_ready=1;draw_page=saved_page;
}

#endif
