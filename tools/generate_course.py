"""Deterministic projected road profiles, not pre-rendered movie frames.

1024 route samples x 256 bytes. Runtime changes the camera's lateral offset
and paints spans with the V9990 command engine. Height visibility is solved
near-to-far, so a crest correctly hides road and objects behind it.
Each sample holds 128 road bytes, 64 scenery bytes and 64 event-anchor bytes.
"""
from pathlib import Path
import math
import json
import hashlib

ROOT = Path(__file__).resolve().parents[1]
COUNT = 1024
LENGTH = 102400.0
FOCAL = 120.0
CAMERA_HEIGHT = 850.0
ROAD_WIDTH = 1450.0
HORIZON = 91.0
BANDS = list(range(64, 106, 2)) + list(range(106, 186, 4))
HEIGHTS = [2] * 21 + [4] * 20
LARGE_HEIGHTS = [10,14,20,28,38,50,66,86,110,138,166,196]
ROCK_SIZES = [(3,2),(5,3),(9,5),(15,9),(24,14),(38,23)]
BUSH_SIZES = [(3,2),(5,3),(8,5),(14,8),(24,13),(36,19)]
EVENT_PROJECT_OFFSET = 192
# One distance unit is 25 world units. Near records are denser so traffic
# can grow smoothly as it reaches the player; far records cover its approach.
EVENT_DEPTHS = [28,32,36,42,50,60,72,86,102,124,150,184,230,292,380,512]

def scenery_at(index):
    """Route-anchored scenery only; road geometry and vehicle rules are fixed.

    Sparse meadow / enclosing firs / rock cut / open crest / valley / firs /
    lakeside crags / open homeward trail. No runtime scene-load or teleport.
    """
    tile = index % 128
    zone = tile // 16
    side = -1 if (tile + (tile >> 2)) & 1 else 1
    # Fixed world spacing preserves a quiet opening between giant forms;
    # it also lets distant scenery appear while it is still small, rather
    # than popping a large rock in when a per-frame object budget frees up.
    if zone in (1,2,5,6) and tile & 1:
        return None
    if zone in (1,5):
        return 0, 2400+(tile%3)*170, 1.20+(tile%3)*.10, side
    if zone in (2,6):
        if tile%3==0:
            return 0, 2100, 1.23, side
        return 2, 2350+(tile%4)*160, 1.90+(tile%3)*.06, side
    if tile%4==0:
        return 0, 2100, 1.19, side
    if tile%4==1:
        return 3, 330, 1.12, side
    if tile%4==2 and zone==4:
        return 1, 380, 1.25, side
    return None

def object_dimensions(kind,size):
    if kind in (0,2):
        h=LARGE_HEIGHTS[size]
        return round(h*(.55 if kind==0 else .90)),h
    return (ROCK_SIZES if kind==1 else BUSH_SIZES)[size]

def height(z):
    t = z * math.tau / LENGTH
    return 2600 * math.sin(t - .7) + 800 * math.sin(2*t + .3)

def center(z):
    t = z * math.tau / LENGTH
    return 5200 * math.sin(t) + 1600 * math.sin(2*t - .5)

def slope(fun, z):
    return (fun(z + 1) - fun(z - 1)) / 2

def event_projection(z, camera_y, tangent_x, pitch, points, distance):
    """Road-relative event anchor with the same near-hill mask as scenery.

    x is signed and relative to screen center; width is the projected road
    half-width. An actor's foot is y, but only rows above clip may be drawn.
    y > clip is therefore valid for both hill-hidden and near-screen actors.
    """
    depth = distance * 25
    world_z = z + depth
    x = FOCAL * (center(world_z) - center(z) - tangent_x*depth) / depth
    y = HORIZON + FOCAL*(camera_y-height(world_z)+pitch*depth)/depth
    width = FOCAL*ROAD_WIDTH/depth
    front = [p[1] for p in points if p[3] < world_z]
    clip = min(186, round(min(front))) if front else 186
    return (max(-127,min(127,round(x))) & 255,
            max(0,min(255,round(y))),
            max(1,min(250,round(width))),
            max(0,min(186,clip)))

def make_profile(phase):
    z = phase * LENGTH / COUNT
    camera_y = height(z) + CAMERA_HEIGHT
    tangent_x = slope(center, z)
    # Partial pitch following lets climbs fill the view and descents open it.
    pitch = slope(height, z) * .58
    points = []
    for depth in range(650, 24801, 150):
        world_z = z + depth
        x = FOCAL * (center(world_z) - center(z) - tangent_x*depth) / depth
        y = HORIZON + FOCAL*(camera_y-height(world_z)+pitch*depth)/depth
        points.append((x, y, FOCAL*ROAD_WIDTH/depth, world_z))
    horizon = max(64, min(126, round(min(p[1] for p in points))))
    data = []
    for top, rows in zip(BANDS, HEIGHTS):
        sample_y = top + rows/2
        hit = None
        for a, b in zip(points, points[1:]):
            if a[1] >= sample_y > b[1]:
                f = (a[1]-sample_y)/(a[1]-b[1])
                hit = tuple(a[i]+(b[i]-a[i])*f for i in range(4))
                break
        if hit is None:
            data.extend((0, 0, 0))
        else:
            x, _, width, world_z = hit
            # Ground bands and gravel dashes advance by distance, not time.
            color = int(world_z / 800) & 1
            depth_bucket = max(0, min(5, round((width-8)/30)))
            data.extend((max(-127,min(127,round(x))) & 255,
                         max(1,min(250,round(width))),
                         color | (depth_bucket << 1)))
    curvature = max(-100,min(100, round((slope(center,z+1800)-tangent_x)*450)))
    grade = max(-100,min(100,round(slope(height,z)*220)))
    # Eight softly changing route sectors; no scenery load between them.
    section = (phase % COUNT) // 128
    heading = max(-127,min(127,round(tangent_x*150)))
    data.extend((horizon, curvature & 255, grade & 255, section, heading & 255))
    assert len(data) == 128
    objects = []
    # Larger, much taller masses pass within the view instead of escaping
    # outside the viewport while still tiny. Their positions remain fixed
    # in world coordinates and their height is occluded by the same hills.
    start = math.floor((z+650)/800)
    for index in range(start, start+28):
        definition = scenery_at(index)
        if definition is None:
            continue
        kind,world_height,offset_factor,side=definition
        world_z = index*800.0
        depth = world_z-z
        if depth < 650 or depth > 22000:
            continue
        offset = ROAD_WIDTH*offset_factor*side
        x = 128+FOCAL*(center(world_z)-center(z)-tangent_x*depth+offset)/depth
        y = HORIZON+FOCAL*(camera_y-height(world_z)+pitch*depth)/depth
        width = FOCAL*ROAD_WIDTH/depth
        sizes=LARGE_HEIGHTS if kind in (0,2) else [h for _,h in (ROCK_SIZES if kind==1 else BUSH_SIZES)]
        size=min(range(len(sizes)),key=lambda n:abs(sizes[n]-FOCAL*world_height/depth))
        sprite_w,sprite_h=object_dimensions(kind,size)
        front = [p[1] for p in points if p[3] < world_z]
        clip = min(186,round(min(front))) if front else 186
        if y-sprite_h >= clip:
            continue
        steering_margin=min(250,width)*144/128
        if x+sprite_w/2+steering_margin>0 and x-sprite_w/2-steering_margin<256 and y>0:
            objects.append((depth,round(x),round(y),size,kind,max(0,clip),min(250,round(width))))
    # Spend the transfer budget on the nearer forms. Distant forests already
    # have their silhouette in the panorama, so fewer separate far trees help.
    objects = sorted(objects)[:8]
    objects.reverse()  # painter order, far-to-near
    for _,x,y,size,kind,clip,width in objects:
        data.extend((x&255,(x>>8)&255,y&255,(y>>8)&255,size,kind,clip,width))
    # Preserve the existing eight scenery slots exactly. The previously
    # unused final 64 bytes now describe independent moving-event anchors.
    assert len(data) <= EVENT_PROJECT_OFFSET
    data.extend([0]*(EVENT_PROJECT_OFFSET-len(data)))
    for distance in EVENT_DEPTHS:
        data.extend(event_projection(z,camera_y,tangent_x,pitch,points,distance))
    assert len(data)==256
    return bytes(data)

def main():
    (ROOT/'assets').mkdir(exist_ok=True)
    (ROOT/'src').mkdir(exist_ok=True)
    (ROOT/'outputs').mkdir(exist_ok=True)
    frames = [make_profile(i) for i in range(COUNT)]
    assert make_profile(COUNT) == frames[0], 'Course geometry must close exactly'
    raw = b''.join(frames)
    assert len(raw) == 262144
    assert len(BANDS) == 41 and BANDS[-1]+HEIGHTS[-1] == 186
    assert any(f[124] < 128 and f[124] > 3 for f in frames)
    assert any(f[124] >= 128 for f in frames)
    assert max(f[123] for f in frames)-min(f[123] for f in frames) >= 10
    (ROOT/'assets/course.bin').write_bytes(raw)
    header = '/* Generated by generate_course.py. */\n'
    header += '#define COURSE_BANDS 41\n#define COURSE_BANK 12\n'
    header += '#define EVENT_PROJECT_OFFSET 192\n#define EVENT_PROJECT_COUNT 16\n'
    header += '/* Records: signed center x, ground y, road half-width, hill clip bottom. */\n'
    header += 'static const u16 event_depth[16]={' + ','.join(map(str,EVENT_DEPTHS)) + '};\n'
    header += 'static const unsigned char band_y[41]={' + ','.join(map(str,BANDS)) + '};\n'
    header += 'static const unsigned char band_h[41]={' + ','.join(map(str,HEIGHTS)) + '};\n'
    (ROOT/'src/course.h').write_text(header)
    report = {'phases':COUNT,'bytes':len(raw),'bytes_per_phase':256,
              'sha256':hashlib.sha256(raw).hexdigest(),'exact_geometry_loop':True,
              'horizon_range':[min(f[123] for f in frames),max(f[123] for f in frames)],
              'signed_curve_range':[min(int.from_bytes(f[124:125],signed=True) for f in frames),max(int.from_bytes(f[124:125],signed=True) for f in frames)],
              'method':'Height-aware near-to-far road intersections, 41 variable-height spans',
              'validation':'Generated geometry only, not native runtime performance'}
    baseline=ROOT/'outputs/baseline-v0.1/source-v0.1.zip'
    if baseline.exists():
        import zipfile
        with zipfile.ZipFile(baseline) as archive:
            old=archive.read('assets/course.bin')
        assert len(old)==len(raw)
        assert all(raw[i:i+128]==old[i:i+128] for i in range(0,len(raw),256)), 'Road or handling metadata changed'
        report['road_and_handling_metadata_identical_to_v01']=True
    baseline=ROOT/'outputs/baseline-v0.3/source-v0.3.zip'
    if baseline.exists():
        import zipfile
        with zipfile.ZipFile(baseline) as archive:
            old=archive.read('assets/course.bin')
        assert len(old)==len(raw)
        assert all(raw[i:i+EVENT_PROJECT_OFFSET]==old[i:i+EVENT_PROJECT_OFFSET]
                   for i in range(0,len(raw),256)), 'Existing road, handling or scenery changed'
        assert all(not any(old[i+EVENT_PROJECT_OFFSET:i+256])
                   for i in range(0,len(old),256)), 'Event projection space was not unused'
        report['road_handling_and_scenery_identical_to_v03']=True
        report['event_projection_uses_previously_zero_padding']=True
    projections=[f[at:at+4] for f in frames for at in range(EVENT_PROJECT_OFFSET,256,4)]
    assert len(EVENT_DEPTHS)*4 == 256-EVENT_PROJECT_OFFSET
    assert EVENT_DEPTHS == sorted(set(EVENT_DEPTHS))
    assert all(1 <= p[2] <= 250 and 0 <= p[3] <= 186 for p in projections)
    assert all(f[EVENT_PROJECT_OFFSET+4*n+2] == min(250,round(6960/depth))
               for f in frames for n,depth in enumerate(EVENT_DEPTHS))
    assert all(list(f[EVENT_PROJECT_OFFSET+3:256:4]) ==
               sorted(f[EVENT_PROJECT_OFFSET+3:256:4],reverse=True) for f in frames), \
        'A farther event cannot see below a nearer hill mask'
    report['event_projection']={
        'offset':EVENT_PROJECT_OFFSET,'records_per_phase':len(EVENT_DEPTHS),
        'record_bytes':4,'depth_distance_units':EVENT_DEPTHS,'world_units_per_distance':25,
        'signed_x_range':[min(int.from_bytes(p[:1],signed=True) for p in projections),
                          max(int.from_bytes(p[:1],signed=True) for p in projections)],
        'ground_y_range':[min(p[1] for p in projections),max(p[1] for p in projections)],
        'clip_bottom_range':[min(p[3] for p in projections),max(p[3] for p in projections)],
        'width_matches_road_projection':True,'record_count':len(projections),
        'hill_clip_nonincreasing_with_depth':True,
        'hill_mask':'Minimum projected ground y in nearer road samples, capped at 186'}
    areas=[];large_visible=0
    for frame in frames:
        total=0
        for at in range(128,EVENT_PROJECT_OFFSET,8):
            p=frame[at:at+8]
            if not p[7]:continue
            x=int.from_bytes(p[:2],'little',signed=True);y=int.from_bytes(p[2:4],'little',signed=True)
            w,h=object_dimensions(p[5],p[4])
            area=max(0,min(256,x+w//2)-max(0,x-w//2))*max(0,min(y,p[6],186)-max(0,y-h))
            total+=area
            if area and h>=86:large_visible+=1
        areas.append(total)
    report['scenery']={'max_records':8,'large_visible_records':large_visible,'mean_visible_bbox_pixels':round(sum(areas)/len(areas),1),'max_visible_bbox_pixels':max(areas)}
    (ROOT/'outputs/course-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__ == '__main__':
    main()
