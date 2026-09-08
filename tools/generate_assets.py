"""Deterministic 16-colour pixel assets for the first V9990 rally drive.

No downloaded artwork or fonts.  The atlas is uploaded at VRAM y=512 and
packed as V9990 4bpp (left pixel in the high nibble).  Run from any directory.
"""

from pathlib import Path
import hashlib
import math
import random

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SRC = ROOT / "src"
ATLAS_W, ATLAS_H = 256, 512
VRAM_Y = 512

# Index zero is transparent when sprites are copied with transparent logic.
# Quantise first, so the preview shows the actual 5-bit V9990 palette.
PALETTE_RGB = [
    (0, 0, 0),        # 0 transparent
    (102, 193, 235),  # 1 clean sky
    (168, 220, 230),  # 2 cloud shadow / lake highlight
    (111, 156, 172),  # 3 distant mountains / water
    (58, 108, 118),   # 4 mountain shadow
    (130, 177, 78),   # 5 meadow
    (35, 78, 56),     # 6 pine foliage
    (107, 151, 69),   # 7 softly shaded grass
    (176, 80, 48),    # 8 rusty paint
    (181, 158, 111),  # 9 dirt road
    (195, 171, 120),  # 10 sunlit road
    (222, 206, 155),  # 11 dry roadside grass
    (29, 43, 43),     # 12 tires / deep shadow
    (237, 145, 66),   # 13 sunlit old paint
    (137, 155, 143),  # 14 metal / windscreen reflection
    (247, 239, 207),  # 15 warm white
]
PALETTE_5 = [tuple(round(c * 31 / 255) for c in rgb) for rgb in PALETTE_RGB]
PALETTE = [tuple(round(c * 255 / 31) for c in rgb) for rgb in PALETTE_5]
PAL_FLAT = [c for rgb in PALETTE for c in rgb] + [0] * (768 - 48)


def canvas(w, h, fill=0):
    im = Image.new("P", (w, h), fill)
    im.putpalette(PAL_FLAT)
    return im


def panorama():
    im = canvas(256, 128, 1)
    d = ImageDraw.Draw(im)
    # Rows 0..43 are an independent, slowly scrolling cloud layer. Broad
    # banks with shaded undersides read as volumes, even at native resolution.
    for x, y, w in [(13, 9, 73), (125, 3, 94), (217, 28, 25)]:
        h = 24 if w > 30 else 12
        d.ellipse((x, y+h//2, x+w, y+h), fill=2)
        for ax, ay, bw, bh in [(0.08, .42, .32, .42), (.20, .11, .34, .74),
                              (.43, .00, .30, .89), (.62, .27, .31, .64)]:
            d.ellipse((x+int(ax*w), y+int(ay*h),
                       x+int((ax+bw)*w), y+int((ay+bh)*h)), fill=15)
        d.rectangle((x+7, y+int(h*.73), x+w-7, y+int(h*.83)), fill=15)
        if w > 30:
            d.line((x+int(w*.26), y+h-2, x+int(w*.52), y+h-2), fill=2)
    # Atmospheric ridge behind the two main massifs, then lit and shaded rock
    # faces. Snow fields follow ridges/gullies rather than triangle caps.
    d.polygon([(0, 79), (15, 72), (26, 65), (33, 69), (43, 58), (55, 65),
               (63, 56), (77, 70), (89, 67), (106, 76), (119, 63),
               (129, 69), (146, 60), (153, 64), (164, 53), (179, 68),
               (192, 63), (207, 75), (219, 68), (233, 71), (248, 76),
               (255, 79), (255, 117), (0, 117)], fill=3)
    d.polygon([(0, 89), (12, 80), (18, 82), (32, 70), (39, 74),
               (56, 52), (62, 56), (67, 48), (73, 60), (81, 59),
               (92, 78), (106, 87), (114, 110), (0, 120)], fill=14)
    d.polygon([(67, 48), (73, 60), (81, 59), (92, 78), (106, 87),
               (114, 110), (74, 104), (60, 89), (65, 73)], fill=4)
    d.polygon([(37, 80), (56, 52), (54, 65), (47, 71), (42, 86),
               (32, 96), (27, 101)], fill=3)
    d.polygon([(67, 48), (64, 60), (62, 65), (64, 70), (58, 78),
               (60, 88), (70, 99), (72, 93), (64, 81), (67, 73),
               (69, 70), (68, 58), (74, 67)], fill=3)
    d.polygon([(56, 52), (48, 61), (51, 61), (49, 66), (54, 65),
               (56, 72), (60, 64), (63, 66), (64, 58), (67, 48),
               (70, 59), (75, 66), (73, 59), (72, 59), (67, 48),
               (61, 56)], fill=15)
    d.polygon([(57, 55), (58, 61), (55, 67), (56, 72), (60, 64),
               (63, 66), (62, 61), (65, 55), (61, 58)], fill=2)
    d.line([(53, 72), (49, 81), (46, 84)], fill=11)
    d.line([(41, 81), (37, 89), (32, 93)], fill=4)
    d.line([(57, 88), (51, 94), (41, 97)], fill=4)
    d.polygon([(24, 89), (40, 79), (35, 89), (19, 99)], fill=7)
    # Taller right massif has a wide sunlit shoulder and a deep blue ravine.
    d.polygon([(98, 102), (116, 84), (132, 72), (140, 75), (155, 58),
               (164, 61), (180, 44), (188, 53), (194, 52), (204, 68),
               (212, 70), (226, 84), (244, 93), (255, 92),
               (255, 122), (108, 124)], fill=14)
    d.polygon([(180, 44), (188, 53), (194, 52), (204, 68), (212, 70),
               (226, 84), (244, 93), (255, 92), (255, 117),
               (218, 110), (197, 93), (187, 71)], fill=4)
    d.polygon([(155, 58), (164, 61), (169, 57), (164, 73), (161, 83),
               (145, 103), (132, 113), (138, 98), (151, 76)], fill=3)
    d.polygon([(180, 44), (181, 58), (178, 63), (181, 67), (177, 75),
               (180, 84), (177, 91), (185, 107), (187, 103),
               (181, 88), (185, 80), (182, 73), (187, 68),
               (185, 59), (192, 64)], fill=3)
    d.polygon([(180, 44), (172, 52), (173, 55), (168, 57), (165, 64),
               (172, 61), (174, 66), (178, 58), (184, 62),
               (186, 60), (192, 66), (190, 58), (194, 56),
               (194, 52), (188, 53)], fill=15)
    d.polygon([(180, 46), (178, 55), (183, 55), (184, 62), (186, 60),
               (192, 66), (190, 58), (185, 55)], fill=2)
    d.polygon([(155, 58), (149, 65), (151, 65), (149, 69),
               (155, 66), (158, 69), (158, 63), (164, 63)], fill=15)
    d.polygon([(170, 75), (161, 86), (158, 94), (163, 91),
               (164, 85), (171, 78)], fill=11)
    d.polygon([(196, 72), (201, 83), (211, 92), (208, 85)], fill=3)
    d.line([(150, 85), (146, 93), (140, 98)], fill=4)
    d.line([(174, 95), (165, 101), (157, 103)], fill=4)
    d.line([(218, 98), (207, 94), (203, 88)], fill=12)
    # Overlapping foothills, forested slopes and a long lake give the bottom
    # layer a readable depth cue when crests reveal more of the panorama.
    d.polygon([(0, 102), (16, 99), (30, 93), (46, 98), (59, 96),
               (81, 106), (100, 114), (133, 116), (152, 106),
               (169, 102), (193, 98), (213, 102), (235, 98), (255, 102),
               (255, 128), (0, 128)], fill=7)
    d.polygon([(0, 110), (25, 103), (31, 100), (42, 101), (54, 102),
               (73, 109), (87, 119), (55, 118), (0, 124)], fill=6)
    d.polygon([(0, 118), (27, 107), (38, 108), (53, 113), (72, 120),
               (109, 124), (148, 124), (165, 117), (175, 107),
               (194, 103), (215, 109), (230, 111), (255, 118),
               (255, 127), (0, 127)], fill=5)
    d.polygon([(167, 117), (175, 107), (194, 103), (212, 108),
               (207, 112), (185, 113)], fill=6)
    for x, y, h in [(3, 108, 4), (10, 106, 3), (16, 105, 5),
                     (24, 103, 4), (32, 103, 4), (46, 106, 3),
                     (59, 109, 4), (177, 108, 4), (181, 106, 5),
                     (188, 105, 4), (199, 106, 3), (205, 108, 4)]:
        d.polygon([(x, y-h), (x-2, y+1), (x+2, y+1)], fill=6)
    d.polygon([(72, 101), (91, 105), (113, 107), (145, 106), (166, 102),
               (177, 107), (158, 113), (143, 123), (95, 124), (73, 116)], fill=7)
    d.polygon([(82, 110), (103, 113), (123, 113), (145, 110),
               (154, 114), (136, 121), (101, 122), (79, 116)], fill=5)
    d.polygon([(93, 106), (135, 104), (159, 106), (150, 109),
               (137, 110), (133, 113), (152, 115), (111, 116),
               (85, 113), (102, 110)], fill=3)
    d.line([(105, 107), (128, 106), (145, 107)], fill=2)
    d.line([(96, 112), (112, 113), (123, 113)], fill=2)
    d.line([(130, 110), (139, 109)], fill=15)
    d.line([(92, 113), (102, 114)], fill=11)
    # Exact wrap is needed for independent cloud and mountain scrolls.
    for y in range(128):
        im.putpixel((255, y), im.getpixel((0, y)))
    d.rectangle((0, 126, 255, 127), fill=5)
    assert all(im.getpixel((x, 0)) == 1 for x in range(256))
    assert set(im.crop((0, 0, 256, 44)).tobytes()) <= {1, 2, 15}
    assert all(im.getpixel((0, y)) == im.getpixel((255, y)) for y in range(128))
    assert all(0 < index <= 15 for index in im.tobytes())
    return im


def old_car(direction):
    """A squat, upright hatchback: same baseline in all three views."""
    im = canvas(44, 30)
    d = ImageDraw.Draw(im)
    s = direction * 2
    d.ellipse((3, 25, 40, 29), fill=12)
    d.rectangle((5, 18, 10, 28), fill=12)
    d.rectangle((33, 18, 38, 28), fill=12)
    # Roof/cabin shifts a little to show yaw, without vehicle roll or shake.
    d.polygon([(12+s, 1), (29+s, 1), (34+s, 12), (9+s, 12)], fill=12)
    d.polygon([(13+s, 2), (28+s, 2), (31+s, 8), (10+s, 8)], fill=13)
    d.polygon([(12+s, 6), (29+s, 6), (32+s, 14), (10+s, 14)], fill=8)
    d.polygon([(13+s, 7), (28+s, 7), (30+s, 12), (12+s, 12)], fill=12)
    d.line((14+s, 8, 27+s, 8), fill=14)
    d.line((15+s, 9, 20+s, 9), fill=2)
    # Tiny crooked roof rack and a rear-window wiper tell the old-car story.
    d.line((13+s, 0, 28+s, 0), fill=14)
    d.line((17+s, 12, 25+s, 11), fill=14)
    d.polygon([(8, 12), (35, 12), (39, 18), (38, 25), (5, 25), (4, 18)], fill=12)
    d.polygon([(9, 13), (34, 13), (37, 18), (36, 23), (7, 23), (6, 18)], fill=8)
    d.line((10, 13, 33, 13), fill=13)
    d.rectangle((8, 15, 35, 18), fill=13)
    d.line((11, 18, 32, 18), fill=8)
    # Rust patches are irregular and sparse, not a tiled texture.
    d.rectangle((11, 16, 14, 17), fill=9)
    d.point((15, 15), fill=9)
    d.line((28, 19, 31, 20), fill=9)
    d.point((32, 19), fill=9)
    d.rectangle((7, 19, 12, 21), fill=12)
    d.rectangle((31, 19, 36, 21), fill=12)
    d.line((8, 19, 11, 19), fill=13)
    d.line((32, 19, 35, 19), fill=13)
    d.rectangle((18, 20, 26, 22), fill=15)
    d.line((20, 21, 24, 21), fill=12)
    d.line((6, 24, 37, 24), fill=14)
    d.line((8, 25, 35, 25), fill=12)
    d.point((30, 14), fill=15)
    # Small black mirrors are visually attached to the cabin.
    d.rectangle((7+s, 11, 9+s, 12), fill=12)
    d.rectangle((33+s, 11, 35+s, 12), fill=12)
    return im


def traffic_van():
    """Friendly cream/blue compact van, viewed from behind, unlike our rusty car."""
    im = canvas(72, 47)
    d = ImageDraw.Draw(im)
    d.ellipse((5, 40, 66, 46), fill=12)
    d.rectangle((9, 29, 17, 44), fill=12)
    d.rectangle((55, 29, 63, 44), fill=12)
    # Upright pale roof, a taller cabin and divided rear glass identify traffic
    # even when it is only a few pixels wide in the distance.
    d.polygon([(21, 1), (50, 1), (58, 12), (61, 35), (10, 35),
               (13, 12)], fill=12)
    d.polygon([(22, 2), (49, 2), (54, 8), (17, 8)], fill=15)
    d.line((22, 3, 48, 3), fill=11)
    d.polygon([(17, 9), (54, 9), (58, 26), (13, 26)], fill=15)
    d.polygon([(19, 11), (52, 11), (55, 22), (16, 22)], fill=12)
    d.polygon([(20, 12), (33, 12), (33, 20), (18, 20)], fill=4)
    d.polygon([(36, 12), (51, 12), (53, 20), (36, 20)], fill=4)
    d.line((20, 13, 30, 13), fill=2)
    d.line((38, 13, 49, 13), fill=3)
    d.line((21, 19, 28, 18), fill=14)
    d.rectangle((9, 17, 13, 20), fill=12)
    d.rectangle((58, 17, 62, 20), fill=12)
    # Light blue body is surrounded by a deep outline; the lower shading
    # grounds the vehicle on the road instead of looking like a floating card.
    d.polygon([(11, 24), (60, 24), (66, 30), (64, 41), (7, 41),
               (5, 30)], fill=12)
    d.polygon([(12, 25), (59, 25), (63, 30), (61, 38), (10, 38),
               (8, 30)], fill=2)
    d.line((14, 25, 57, 25), fill=15)
    d.polygon([(57, 27), (63, 30), (61, 38), (54, 38)], fill=3)
    d.rectangle((14, 33, 56, 37), fill=3)
    d.line((35, 25, 35, 34), fill=14)
    d.line((32, 28, 33, 28), fill=12)
    d.line((38, 28, 39, 28), fill=12)
    d.rectangle((10, 31, 18, 35), fill=12)
    d.rectangle((54, 31, 61, 35), fill=12)
    d.rectangle((11, 31, 17, 33), fill=8)
    d.rectangle((55, 31, 60, 33), fill=8)
    d.line((12, 32, 16, 32), fill=13)
    d.line((56, 32, 59, 32), fill=13)
    d.rectangle((29, 34, 43, 37), fill=15)
    d.line((32, 35, 40, 35), fill=12)
    d.line((9, 39, 62, 39), fill=14)
    d.line((15, 40, 57, 40), fill=4)
    return im


def flying_saucer():
    """A clearly outlined disk, cool dome and warm lamps; no extra palette."""
    im = canvas(52, 20)
    d = ImageDraw.Draw(im)
    d.ellipse((14, 0, 37, 16), fill=12)
    d.ellipse((16, 1, 35, 14), fill=3)
    d.ellipse((18, 2, 31, 11), fill=2)
    d.line((21, 3, 26, 3), fill=15)
    d.ellipse((0, 8, 51, 19), fill=12)
    d.ellipse((2, 8, 49, 16), fill=14)
    d.ellipse((5, 8, 46, 13), fill=15)
    d.ellipse((13, 8, 38, 12), fill=3)
    d.line((4, 14, 47, 14), fill=4)
    d.line((8, 16, 43, 16), fill=3)
    for x in [9, 19, 29, 39]:
        d.rectangle((x, 15, x+3, 16), fill=13)
        d.point((x+1, 15), fill=15)
    d.line((20, 18, 31, 18), fill=2)
    return im


def floating_cow():
    """Small, intact cartoon cow with dangling legs for the pasture warning."""
    im = canvas(20, 14)
    d = ImageDraw.Draw(im)
    d.line([(2, 5), (0, 3), (0, 8)], fill=12)
    d.polygon([(3, 4), (11, 3), (15, 5), (14, 10), (3, 10),
               (2, 8)], fill=12)
    d.polygon([(4, 4), (10, 4), (14, 6), (13, 9), (3, 9),
               (3, 6)], fill=15)
    d.polygon([(5, 4), (8, 4), (7, 7), (4, 6)], fill=12)
    d.polygon([(10, 7), (13, 7), (12, 9), (10, 9)], fill=12)
    d.line((4, 10, 4, 12), fill=15)
    d.line((11, 10, 11, 12), fill=15)
    d.line((3, 13, 5, 13), fill=12)
    d.line((10, 13, 12, 13), fill=12)
    d.line((13, 2, 12, 0), fill=11)
    d.line((17, 2, 18, 0), fill=11)
    d.polygon([(13, 1), (17, 1), (18, 3), (19, 5), (18, 7),
               (14, 7), (12, 4)], fill=12)
    d.rectangle((14, 2, 16, 4), fill=15)
    d.point((16, 3), fill=12)
    d.rectangle((15, 5, 18, 6), fill=13)
    d.point((18, 5), fill=8)
    return im


def car_shadow():
    im = canvas(56, 6)
    ImageDraw.Draw(im).ellipse((2, 0, 53, 5), fill=12)
    return im


def pine():
    im = canvas(48, 76)
    d = ImageDraw.Draw(im)
    d.polygon([(21, 54), (27, 53), (27, 75), (21, 75)], fill=12)
    d.rectangle((22, 53, 24, 73), fill=9)
    for top, left, right, bottom in [(0, 13, 34, 29), (13, 8, 39, 42),
                                      (28, 3, 44, 56), (42, 0, 47, 68)]:
        d.polygon([(24, top), (left+3, bottom-6), (left, bottom),
                   (15, bottom-2), (21, bottom+1), (32, bottom-2),
                   (right, bottom), (right-4, bottom-8)], fill=6)
        d.polygon([(23, top+4), (left+6, bottom-7), (18, bottom-9),
                   (14, bottom-3), (25, bottom-7), (29, bottom-4),
                   (26, bottom-16)], fill=7)
        d.line((23, top+5, left+9, bottom-10), fill=5)
    rng = random.Random(714)
    for _ in range(55):
        x, y = rng.randrange(5, 43), rng.randrange(9, 65)
        if im.getpixel((x, y)) in (6, 7):
            d.line((x, y, x+1, y), fill=7 if x > 25 else 5)
    return im


def rock():
    im = canvas(38, 23)
    d = ImageDraw.Draw(im)
    d.polygon([(1, 18), (7, 8), (14, 2), (26, 0), (34, 8), (37, 19),
               (27, 22), (9, 22), (0, 20)], fill=12)
    d.polygon([(3, 18), (9, 8), (15, 3), (25, 2), (31, 8), (29, 15),
               (17, 18)], fill=14)
    d.polygon([(25, 2), (34, 9), (35, 18), (25, 20), (20, 17), (29, 14)], fill=4)
    d.polygon([(9, 8), (15, 3), (25, 2), (22, 6), (12, 10)], fill=11)
    d.line((12, 12, 17, 9), fill=4)
    d.line((6, 20, 13, 21), fill=7)
    return im


def post():
    im = canvas(8, 34)
    d = ImageDraw.Draw(im)
    d.rectangle((2, 1, 6, 33), fill=12)
    d.rectangle((2, 2, 5, 31), fill=11)
    d.rectangle((2, 2, 3, 29), fill=15)
    d.rectangle((2, 5, 5, 11), fill=8)
    d.rectangle((2, 6, 3, 9), fill=13)
    d.line((2, 26, 4, 28), fill=9)
    d.line((0, 33, 7, 33), fill=7)
    return im


def bush():
    im = canvas(36, 19)
    d = ImageDraw.Draw(im)
    d.ellipse((0, 7, 15, 18), fill=6)
    d.ellipse((8, 1, 27, 18), fill=6)
    d.ellipse((23, 6, 35, 18), fill=6)
    d.ellipse((2, 6, 16, 14), fill=7)
    d.ellipse((10, 2, 23, 14), fill=7)
    d.ellipse((23, 6, 32, 13), fill=7)
    d.line((12, 4, 18, 3), fill=5)
    d.line((4, 9, 9, 7), fill=5)
    d.point((27, 8), fill=11)
    d.point((15, 7), fill=11)
    return im


SCENERY_HEIGHTS = [10, 14, 20, 28, 38, 50, 66, 86, 110, 138, 166, 196]
SCENERY_VRAM_Y = 1536


def grand_pine():
    """Tall roadside conifer, with overlapping bough masses and lit needles."""
    im = canvas(108, 196)
    d = ImageDraw.Draw(im)
    # Trunk/root system makes this read as a tree rooted in the grass, not a
    # flat triangular sign. The large lower branches partly hide the trunk.
    d.polygon([(49, 89), (59, 83), (62, 184), (74, 191), (67, 194),
               (57, 191), (50, 195), (33, 195), (47, 186)], fill=12)
    d.polygon([(51, 97), (55, 96), (57, 183), (61, 190), (52, 188)], fill=9)
    d.line([(52, 145), (52, 174), (50, 185)], fill=11, width=2)
    d.line([(57, 153), (58, 176), (59, 185)], fill=8)
    # Every bough has its own width and tilt; they overlap vertically. Large
    # colour planes, broken tips and a few connected needle strokes replace
    # point noise or repetitive checkerboard dither.
    layers = [(1, 7, 23, 1), (13, 12, 29, -1), (30, 18, 34, 2),
              (47, 25, 37, -1), (63, 31, 43, 2), (81, 37, 45, -2),
              (98, 44, 46, 1), (116, 49, 48, -2), (134, 53, 47, 0)]
    for index, (top, half, depth, lean) in enumerate(layers):
        cx = 54 + lean
        left, right, bottom = max(0, cx-half), min(107, cx+half), top+depth
        outline = [(cx, top), (cx-5, top+depth//3),
                   (left+half//3, bottom-13), (left+2, bottom-8),
                   (left+6, bottom-7), (left, bottom-1),
                   (left+half//3, bottom-4), (left+half//4, bottom+2),
                   (cx-7, bottom-3), (cx-2, bottom),
                   (cx+7, bottom-4), (right-8, bottom),
                   (right-12, bottom-6), (right, bottom-2),
                   (right-7, bottom-10), (right-2, bottom-8),
                   (cx+half//2, top+depth//2), (cx+4, top+depth//4)]
        d.polygon(outline, fill=12)
        canopy = [(cx, top+1), (cx-3, top+depth//3),
                  (left+half//3, bottom-12), (left+5, bottom-7),
                  (left+10, bottom-7), (left+4, bottom-2),
                  (cx-12, bottom-7), (cx-5, bottom-3),
                  (cx+5, bottom-7), (right-7, bottom-4),
                  (right-14, bottom-12), (cx+half//2, top+depth//2),
                  (cx+3, top+depth//4)]
        d.polygon(canopy, fill=6)
        lit = [(cx-1, top+3), (cx-4, top+depth//2),
               (left+half//3+1, bottom-11), (left+7, bottom-6),
               (cx-half//2, bottom-10), (cx-half//3, bottom-8),
               (cx-8, bottom-12), (cx-2, bottom-7),
               (cx+2, bottom-12), (cx-1, top+depth//2)]
        d.polygon(lit, fill=7)
        if half >= 18:
            d.polygon([(cx-4, top+depth//2), (cx-half//2, bottom-14),
                       (left+half//3+3, bottom-11), (cx-half//2+3, bottom-10),
                       (cx-10, bottom-16)], fill=5)
            d.polygon([(cx+5, top+depth//2), (cx+half//2, bottom-14),
                       (right-11, bottom-7), (cx+half//2-3, bottom-10),
                       (cx+10, bottom-13)], fill=7)
            d.line([(cx-3, bottom-9), (cx-half//2, bottom-5),
                    (left+6, bottom-1)], fill=6, width=2)
            d.line([(cx+7, bottom-8), (right-10, bottom-4)], fill=12)
        # Connected two-pixel highlights are tips of particular branches.
        if index > 3:
            for shift in [0, half//3]:
                ax = cx-half//2+shift
                ay = bottom-13-shift//3
                d.line([(ax-4, ay+1), (ax, ay-1), (ax+2, ay)], fill=5)
    # Finer crown remains identifiable at the larger 12 scale steps.
    d.line([(54, 0), (54, 7), (52, 12)], fill=7)
    d.line([(55, 2), (57, 11)], fill=6)
    d.polygon([(36, 194), (45, 189), (44, 193), (50, 191),
               (48, 195), (35, 195)], fill=7)
    return im


def crag():
    """A towering, layered rock buttress with distinct top/front/side planes."""
    im = canvas(176, 196)
    d = ImageDraw.Draw(im)
    outline = [(3, 189), (10, 160), (7, 134), (17, 111), (13, 85),
               (26, 57), (25, 29), (41, 11), (71, 10), (88, 0),
               (124, 3), (136, 20), (151, 31), (149, 63),
               (157, 88), (155, 115), (165, 143), (168, 168),
               (175, 185), (166, 195), (17, 195), (0, 191)]
    d.polygon(outline, fill=12)
    # Visible upper ledge and a sun-facing broad front. The right wall falls
    # away into cool shadow, with a broken vertical ridge defining the corner.
    d.polygon([(27, 29), (42, 13), (74, 13), (88, 2), (123, 5),
               (135, 23), (112, 34), (77, 34), (55, 42)], fill=11)
    d.polygon([(44, 17), (77, 16), (89, 6), (112, 8), (98, 16),
               (99, 24), (74, 30), (52, 30)], fill=10)
    d.line([(46, 15), (74, 15), (88, 4), (114, 7)], fill=15, width=2)
    d.polygon([(27, 31), (54, 44), (77, 36), (113, 35),
               (113, 68), (104, 85), (112, 110), (107, 139),
               (116, 167), (112, 191), (21, 192), (6, 189),
               (14, 160), (11, 134), (22, 111), (18, 84), (30, 56)], fill=9)
    d.polygon([(113, 35), (138, 22), (148, 33), (146, 64), (154, 88),
               (151, 115), (162, 145), (165, 170), (172, 185),
               (164, 191), (114, 191), (119, 167), (109, 138),
               (115, 110), (108, 85), (117, 68)], fill=4)
    # Large sunlit facets taper and fracture instead of using repeated blocks.
    d.polygon([(30, 33), (53, 45), (48, 74), (39, 86),
               (40, 119), (32, 142), (34, 171), (25, 185),
               (13, 183), (18, 161), (16, 138), (26, 111),
               (23, 82), (33, 56)], fill=10)
    d.polygon([(57, 44), (74, 38), (79, 63), (68, 83),
               (73, 107), (65, 126), (70, 148), (57, 165),
               (59, 186), (43, 188), (47, 161), (43, 142),
               (51, 117), (48, 95), (55, 70)], fill=14)
    d.polygon([(81, 38), (110, 37), (109, 65), (97, 80),
               (106, 108), (99, 136), (106, 166), (104, 190),
               (80, 189), (84, 161), (76, 143), (84, 119),
               (80, 91), (89, 66)], fill=10)
    d.polygon([(81, 40), (92, 39), (90, 60), (83, 77),
               (88, 98), (85, 115), (78, 98), (76, 83),
               (84, 66)], fill=11)
    d.polygon([(98, 118), (96, 136), (103, 160), (99, 179),
               (92, 184), (92, 158), (87, 138), (92, 121)], fill=11)
    # A handful of offset strata/ledges connect across facets. Their spacing
    # and direction change so the rock remains a geological mass, not a grid.
    ledges = [([(29, 58), (43, 63), (59, 60), (72, 54), (110, 53)], 3),
              ([(23, 83), (38, 89), (57, 85), (69, 88), (101, 78)], 2),
              ([(21, 113), (42, 117), (60, 109), (79, 113), (108, 106)], 3),
              ([(15, 139), (33, 143), (56, 137), (75, 142), (101, 133)], 2),
              ([(20, 166), (34, 171), (49, 163), (69, 166), (111, 159)], 3)]
    for points, width in ledges:
        d.line(points, fill=4, width=width)
        d.line([(x, y-width) for x, y in points], fill=11)
    # Narrow deep faults are shaded crevices, with a lit lip on just one side.
    d.line([(58, 47), (60, 60), (55, 74), (58, 84), (54, 93)], fill=12)
    d.line([(76, 117), (72, 128), (75, 140), (70, 151), (73, 165)], fill=4, width=2)
    d.line([(43, 148), (41, 161), (45, 171), (41, 184)], fill=4)
    d.line([(116, 37), (114, 65), (104, 84), (112, 109),
            (106, 138), (116, 166), (113, 188)], fill=11, width=2)
    # Side wall: fewer highlights, long blue facets and two deep clefts.
    d.polygon([(139, 29), (144, 36), (140, 63), (145, 81),
               (138, 95), (142, 113), (135, 133), (143, 160),
               (138, 184), (126, 189), (129, 163), (122, 142),
               (129, 119), (124, 99), (132, 79), (129, 61)], fill=3)
    d.polygon([(149, 88), (149, 113), (159, 145), (155, 166),
               (165, 185), (147, 190), (151, 166), (144, 147),
               (147, 127), (141, 113)], fill=12)
    d.line([(119, 58), (131, 53), (145, 48)], fill=12, width=3)
    d.line([(114, 109), (126, 103), (139, 104), (149, 97)], fill=12, width=3)
    d.line([(115, 161), (130, 153), (139, 156), (158, 148)], fill=12, width=2)
    # Turf on sheltered ledges and at the base integrates the rock with grass.
    for points in [[(29, 58), (39, 59), (43, 63), (31, 63), (25, 61)],
                   [(22, 112), (34, 113), (40, 115), (29, 118), (21, 116)],
                   [(80, 111), (94, 107), (105, 108), (96, 112), (84, 114)],
                   [(121, 157), (134, 154), (139, 157), (128, 161)]]:
        d.polygon(points, fill=6)
        d.line(points[:3], fill=7)
    for x, y, w, h in [(3, 175, 30, 19), (39, 181, 24, 15),
                       (139, 176, 34, 19), (114, 186, 21, 10)]:
        shrub = bush().resize((w, h), Image.Resampling.NEAREST)
        paste_transparent(im, shrub, (x, y))
    d.line([(23, 193), (32, 190), (47, 193), (65, 191)], fill=7, width=2)
    return im


# Hand-drawn 5x7 ASCII bitmap; lower case deliberately uses the compact capitals.
GLYPHS = {
    ' ': '00000/00000/00000/00000/00000/00000/00000',
    '!': '00100/00100/00100/00100/00100/00000/00100',
    '"': '01010/01010/01010/00000/00000/00000/00000',
    '#': '01010/11111/01010/01010/11111/01010/00000',
    '$': '00100/01111/10100/01110/00101/11110/00100',
    '%': '11001/11010/00100/01000/10110/00110/00000',
    '&': '01100/10010/10100/01000/10101/10010/01101',
    "'": '00100/00100/01000/00000/00000/00000/00000',
    '(': '00010/00100/01000/01000/01000/00100/00010',
    ')': '01000/00100/00010/00010/00010/00100/01000',
    '*': '00000/10101/01110/11111/01110/10101/00000',
    '+': '00000/00100/00100/11111/00100/00100/00000',
    ',': '00000/00000/00000/00000/00110/00100/01000',
    '-': '00000/00000/00000/11111/00000/00000/00000',
    '.': '00000/00000/00000/00000/00000/00110/00110',
    '/': '00001/00010/00100/00100/01000/10000/00000',
    '0': '01110/10001/10011/10101/11001/10001/01110',
    '1': '00100/01100/00100/00100/00100/00100/01110',
    '2': '01110/10001/00001/00010/00100/01000/11111',
    '3': '11110/00001/00001/01110/00001/00001/11110',
    '4': '00010/00110/01010/10010/11111/00010/00010',
    '5': '11111/10000/10000/11110/00001/00001/11110',
    '6': '01110/10000/10000/11110/10001/10001/01110',
    '7': '11111/00001/00010/00100/01000/01000/01000',
    '8': '01110/10001/10001/01110/10001/10001/01110',
    '9': '01110/10001/10001/01111/00001/00001/01110',
    ':': '00000/00110/00110/00000/00110/00110/00000',
    ';': '00000/00110/00110/00000/00110/00100/01000',
    '<': '00010/00100/01000/10000/01000/00100/00010',
    '=': '00000/00000/11111/00000/11111/00000/00000',
    '>': '01000/00100/00010/00001/00010/00100/01000',
    '?': '01110/10001/00001/00010/00100/00000/00100',
    '@': '01110/10001/10111/10101/10111/10000/01110',
    'A': '01110/10001/10001/11111/10001/10001/10001',
    'B': '11110/10001/10001/11110/10001/10001/11110',
    'C': '01110/10001/10000/10000/10000/10001/01110',
    'D': '11110/10001/10001/10001/10001/10001/11110',
    'E': '11111/10000/10000/11110/10000/10000/11111',
    'F': '11111/10000/10000/11110/10000/10000/10000',
    'G': '01110/10001/10000/10111/10001/10001/01110',
    'H': '10001/10001/10001/11111/10001/10001/10001',
    'I': '01110/00100/00100/00100/00100/00100/01110',
    'J': '00111/00010/00010/00010/10010/10010/01100',
    'K': '10001/10010/10100/11000/10100/10010/10001',
    'L': '10000/10000/10000/10000/10000/10000/11111',
    'M': '10001/11011/10101/10101/10001/10001/10001',
    'N': '10001/11001/10101/10011/10001/10001/10001',
    'O': '01110/10001/10001/10001/10001/10001/01110',
    'P': '11110/10001/10001/11110/10000/10000/10000',
    'Q': '01110/10001/10001/10001/10101/10010/01101',
    'R': '11110/10001/10001/11110/10100/10010/10001',
    'S': '01111/10000/10000/01110/00001/00001/11110',
    'T': '11111/00100/00100/00100/00100/00100/00100',
    'U': '10001/10001/10001/10001/10001/10001/01110',
    'V': '10001/10001/10001/10001/10001/01010/00100',
    'W': '10001/10001/10001/10101/10101/10101/01010',
    'X': '10001/10001/01010/00100/01010/10001/10001',
    'Y': '10001/10001/01010/00100/00100/00100/00100',
    'Z': '11111/00001/00010/00100/01000/10000/11111',
    '[': '01110/01000/01000/01000/01000/01000/01110',
    '\\': '10000/01000/00100/00100/00010/00001/00000',
    ']': '01110/00010/00010/00010/00010/00010/01110',
    '^': '00100/01010/10001/00000/00000/00000/00000',
    '_': '00000/00000/00000/00000/00000/00000/11111',
    '`': '01000/00100/00000/00000/00000/00000/00000',
    '{': '00011/00100/00100/01000/00100/00100/00011',
    '|': '00100/00100/00100/00100/00100/00100/00100',
    '}': '11000/00100/00100/00010/00100/00100/11000',
    '~': '00000/00000/01001/10110/00000/00000/00000',
    '\x7f': '11111/10001/10101/10001/10101/10001/11111',
}


def glyph(char):
    im = canvas(6, 8)
    rows = GLYPHS[char.upper() if char.islower() else char].split('/')
    assert len(rows) == 7 and all(len(row) == 5 for row in rows)
    for y, row in enumerate(rows):
        for x, bit in enumerate(row):
            if bit == '1':
                im.putpixel((x, y), 15)
    return im


class Atlas:
    def __init__(self):
        self.image = canvas(ATLAS_W, ATLAS_H)
        self.image.paste(panorama(), (0, 0))
        self.occupied = [("sky", 0, 0, 256, 128)]
        self.x, self.y, self.row_h = 0, 130, 0

    def add(self, name, im):
        w, h = im.size
        if self.x + w > ATLAS_W:
            self.x = 0
            self.y += self.row_h + 2
            self.row_h = 0
        x, y = self.x, self.y
        assert 0 < w <= 255 and 0 < h <= 255
        assert x + w <= ATLAS_W and y + h <= ATLAS_H, name
        for other, ox, oy, ow, oh in self.occupied:
            assert x + w <= ox or ox + ow <= x or y + h <= oy or oy + oh <= y, (name, other)
        assert all(0 <= index <= 15 for index in im.tobytes()), name
        self.occupied.append((name, x, y, w, h))
        self.image.paste(im, (x, y))
        self.x += w + 2
        self.row_h = max(self.row_h, h)
        return x, y + VRAM_Y, w, h


class SceneryAtlas:
    """Deterministic max-rectangles packing, with a transparent pixel gutter."""
    def __init__(self):
        self.image = canvas(256, 1024)
        self.occupied = []
        self.free = [(0, 0, 256, 1024)]

    def add(self, name, im):
        w, h = im.size
        pw, ph = w+1, h+1
        choices = [(min(fw-pw, fh-ph), max(fw-pw, fh-ph), fy, fx)
                   for fx, fy, fw, fh in self.free if pw <= fw and ph <= fh]
        assert choices, f'No atlas room for {name} {im.size}'
        _, _, y, x = min(choices)
        assert 0 < w < 256 and 0 < h < 212
        assert x+w <= 256 and y+h <= 1024
        for other, ox, oy, ow, oh in self.occupied:
            assert x+w <= ox or ox+ow <= x or y+h <= oy or oy+oh <= y, (name, other)
        assert all(0 <= index <= 15 for index in im.tobytes()), name
        self.occupied.append((name, x, y, w, h))
        self.image.paste(im, (x, y))
        fragments = []
        for fx, fy, fw, fh in self.free:
            if x+pw <= fx or fx+fw <= x or y+ph <= fy or fy+fh <= y:
                fragments.append((fx, fy, fw, fh))
                continue
            if x > fx:
                fragments.append((fx, fy, x-fx, fh))
            if x+pw < fx+fw:
                fragments.append((x+pw, fy, fx+fw-x-pw, fh))
            if y > fy:
                fragments.append((fx, fy, fw, y-fy))
            if y+ph < fy+fh:
                fragments.append((fx, y+ph, fw, fy+fh-y-ph))
        # Overlapping free rectangles are intentional. Remove only contained
        # ones; every later placement splits all intersections consistently.
        fragments = list(dict.fromkeys(fragments))
        self.free = [r for r in fragments if not any(
            r != q and r[0] >= q[0] and r[1] >= q[1]
            and r[0]+r[2] <= q[0]+q[2] and r[1]+r[3] <= q[1]+q[3]
            for q in fragments)]
        return x, y+SCENERY_VRAM_Y, w, h


def pack_4bpp(im):
    pixels = im.tobytes()
    assert im.mode == 'P' and im.width % 2 == 0
    assert len(pixels) == im.width*im.height and max(pixels) <= 15
    packed = bytes((pixels[i] << 4) | pixels[i+1] for i in range(0, len(pixels), 2))
    assert len(packed) == im.width*im.height//2
    unpacked = bytes(v for pair in packed for v in (pair >> 4, pair & 15))
    assert pixels == unpacked, '4bpp roundtrip'
    return packed


def generate_scenery():
    masters = {'grand_pines': (grand_pine(), .55), 'crags': (crag(), .90)}
    art = {name: [master.resize((round(h*ratio), h), Image.Resampling.NEAREST)
                  for h in SCENERY_HEIGHTS]
           for name, (master, ratio) in masters.items()}
    atlas = SceneryAtlas()
    # Large rectangles first; retain ascending scale order in the C arrays.
    entries = sorted([(name, index, im) for name, images in art.items()
                      for index, im in enumerate(images)],
                     key=lambda e: (-e[2].width*e[2].height, -e[2].height, e[0], e[1]))
    groups = {name: [None]*12 for name in art}
    for name, index, im in entries:
        groups[name][index] = atlas.add(f'{name}[{index}]', im)
    for name, rects in groups.items():
        assert [r[3] for r in rects] == SCENERY_HEIGHTS
        assert all(1536 <= r[1] and r[1]+r[3] <= 2560 for r in rects)
    lines = ["/* Generated by tools/generate_assets.py. Do not edit. */",
             "#ifndef RALLY_SCENERY_H", "#define RALLY_SCENERY_H", "",
             '#include "assets.h"', "#define SCENERY_Y 1536",
             "#define SCENERY_H 1024", "#define SCENERY_LEVELS 12", ""]
    for name, rects in groups.items():
        lines.append(f"static const Sprite {name}[12] = {{")
        lines.extend("    { %d, %d, %d, %d }," % r for r in rects)
        lines.append("};\n")
    lines.extend(["#endif", ""])
    (SRC / "scenery.h").write_text('\n'.join(lines), encoding="ascii")
    packed = pack_4bpp(atlas.image)
    assert len(packed) == 131072
    (ASSETS / 'scenery.bin').write_bytes(packed)
    print(f"Scenery: 256x1024, {len(packed)} bytes, 24 non-overlapping rectangles, "
          f"last local row {max(y+h for _, x, y, w, h in atlas.occupied)}")
    print(f"SCENERY SHA256: {hashlib.sha256(packed).hexdigest()}")
    return atlas, art


def emit_header(groups):
    lines = ["/* Generated by tools/generate_assets.py. Do not edit. */",
             "#ifndef RALLY_ASSETS_H", "#define RALLY_ASSETS_H", "",
             "typedef struct { unsigned int x, y; unsigned char w, h; } Sprite;",
             "#define SKY_Y 512", "#define SKY_H 128", ""]
    for name, rectangles in groups.items():
        lines.append(f"static const Sprite {name}[{len(rectangles)}] = {{")
        lines.extend("    { %d, %d, %d, %d }," % r for r in rectangles)
        lines.append("};\n")
    lines.extend(["#endif", ""])
    (SRC / "assets.h").write_text('\n'.join(lines), encoding="ascii")


def emit_palette():
    names = ["TRANSPARENT", "SKY", "SKY_LIGHT", "DISTANT", "MOUNTAIN", "GRASS",
             "TREE", "GRASS_DARK", "RUST", "ROAD", "ROAD_LIGHT", "VERGE",
             "DARK", "ORANGE", "METAL", "WHITE"]
    lines = ["/* Generated by tools/generate_assets.py. RGB components are 0..31. */",
             "#ifndef RALLY_PALETTE_H", "#define RALLY_PALETTE_H", ""]
    lines.extend(f"#define COL_{name} {i}" for i, name in enumerate(names))
    lines.append("#define COL_GRASS_ALT COL_GRASS_DARK")
    lines.extend(["", "static const unsigned char v9990_palette[48] = {"])
    lines.extend("    %2d, %2d, %2d, /* %2d %s */" % (*rgb, i, names[i])
                 for i, rgb in enumerate(PALETTE_5))
    lines.extend(["};", "", "#endif", ""])
    (SRC / "palette.h").write_text('\n'.join(lines), encoding="ascii")


def paste_transparent(target, im, pos):
    mask = im.point(lambda index: 0 if index == 0 else 255, mode="L")
    target.paste(im, pos, mask)


def preview(atlas, art, scenery_atlas, scenery_art):
    scene = canvas(256, 212, 5)
    scene.paste(panorama(), (0, 0))
    d = ImageDraw.Draw(scene)
    # Illustration only: the native ROM independently draws the road.
    for y in range(106, 212):
        t = (y - 106) / 105
        center = 143 - 23 * t + 20 * math.sin(t * math.pi)
        width = 3 + 102 * t ** 1.2
        d.line((int(center - width - 4 * t), y, int(center + width + 4 * t), y), fill=11)
        d.line((int(center - width), y, int(center + width), y), fill=10 if int(t * 22) % 2 == 0 else 9)
    for index, x, y in [(0, 118, 109), (0, 156, 108), (2, 171, 115),
                         (3, 189, 131), (4, 61, 141), (5, 210, 149), (7, 11, 165)]:
        tree_im = scenery_art['grand_pines'][index]
        paste_transparent(scene, tree_im, (x, y - tree_im.height))
    for index, x, y in [(1, 112, 112), (2, 94, 129), (3, 71, 158), (4, 37, 196),
                         (1, 166, 113), (2, 183, 130), (3, 219, 159)]:
        im = art['posts'][index]
        paste_transparent(scene, im, (x, y - im.height))
    paste_transparent(scene, art['rocks'][4], (216, 188))
    paste_transparent(scene, art['bushes'][4], (11, 181))
    paste_transparent(scene, scenery_art['crags'][10], (221, 10))
    paste_transparent(scene, scenery_art['grand_pines'][11], (-66, 13))
    # Same fixed bottom anchor as native draw_ui; the larger car grows upward.
    paste_transparent(scene, art['driving_car'][1], (100, 146))
    d.rectangle((0, 0, 255, 14), fill=12)
    for i, char in enumerate("ASSET PREVIEW V04 / NOT ROM"):
        paste_transparent(scene, glyph(char), (7 + i * 6, 6))
    # One inspectable sheet: composition, enlarged vehicle, both full atlases,
    # and the two large scenery masters on a sky/grass swatch.
    sheet = Image.new("RGB", (1320, 1072), PALETTE[12])
    sheet.paste(scene.convert("RGB").resize((768, 636), Image.Resampling.NEAREST), (8, 8))
    sheet.paste(atlas.image.convert("RGB"), (792, 8))
    sheet.paste(scenery_atlas.image.convert('RGB'), (1056, 8))
    for index in range(3):
        # Use the meadow behind the three transparent vehicle views.
        swatch = canvas(56, 38, 5)
        paste_transparent(swatch, art['driving_car'][index], (0, 0))
        sheet.paste(swatch.convert('RGB').resize((224, 152), Image.Resampling.NEAREST),
                    (8 + index * 232, 656))
    for i, color in enumerate(PALETTE):
        ImageDraw.Draw(sheet).rectangle((8+i*48, 828, 51+i*48, 853), fill=color)
    masters = canvas(512, 200, 1)
    ImageDraw.Draw(masters).rectangle((0, 180, 511, 199), fill=5)
    paste_transparent(masters, scenery_art['grand_pines'][11], (14, 2))
    paste_transparent(masters, scenery_art['crags'][11], (166, 2))
    paste_transparent(masters, art['driving_car'][1], (386, 160))
    sheet.paste(masters.convert('RGB'), (8, 864))
    # The event strip is artwork QA, not a claim of native runtime behavior.
    events = canvas(256, 96, 5)
    paste_transparent(events, art['traffic_car'][0], (9, 44))
    paste_transparent(events, art['traffic_car'][4], (88, 65))
    paste_transparent(events, art['ufo'][0], (156, 7))
    paste_transparent(events, art['cow'][0], (172, 38))
    paste_transparent(events, art['car_shadow'][0], (154, 79))
    sheet.paste(events.convert('RGB').resize((256, 96), Image.Resampling.NEAREST),
                (528, 968))
    sheet.save(ASSETS / "preview.png")


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    SRC.mkdir(parents=True, exist_ok=True)
    atlas = Atlas()
    art = {'car': [old_car(-1), old_car(0), old_car(1)]}
    specs = {
        'trees': (pine(), [(4, 8), (8, 14), (14, 24), (22, 37), (32, 52), (48, 76)]),
        'rocks': (rock(), [(3, 2), (5, 3), (9, 5), (15, 9), (24, 14), (38, 23)]),
        'posts': (post(), [(2, 3), (2, 5), (3, 9), (4, 15), (6, 23), (8, 34)]),
        'bushes': (bush(), [(3, 2), (5, 3), (8, 5), (14, 8), (24, 13), (36, 19)]),
    }
    for name, (master, sizes) in specs.items():
        art[name] = [master.resize(size, Image.Resampling.NEAREST) for size in sizes]
    art['font'] = [glyph(chr(code)) for code in range(32, 128)]
    # Append rather than repack: preserve every v0.2 atlas coordinate and pixel.
    # Nearest-neighbour scaling retains the battered car's 16-colour identity.
    art['driving_car'] = [im.resize((56, 38), Image.Resampling.NEAREST)
                          for im in art['car']]
    # Append v0.4 events after every existing group, so all old coordinates and
    # pixels remain identical. Near-to-far ordering matches event depth bins.
    van = traffic_van()
    traffic_widths = [72, 64, 56, 48, 40, 34, 28, 24,
                      20, 16, 14, 12, 10, 8, 6, 4]
    art['traffic_car'] = [van.resize((w, round(w*47/72)), Image.Resampling.NEAREST)
                          for w in traffic_widths]
    art['ufo'] = [flying_saucer()]
    art['cow'] = [floating_cow()]
    art['car_shadow'] = [car_shadow()]
    groups = {name: [atlas.add(f'{name}[{i}]', im) for i, im in enumerate(images)]
              for name, images in art.items()}
    packed = pack_4bpp(atlas.image)
    assert len(packed) == 65536
    (ASSETS / "vram.bin").write_bytes(packed)
    emit_header(groups)
    emit_palette()
    scenery_atlas, scenery_art = generate_scenery()
    preview(atlas, art, scenery_atlas, scenery_art)
    print(f"Atlas: 256x512, 16 colours, {len(packed)} bytes, "
          f"{len(atlas.occupied)} non-overlapping rectangles, last local row "
          f"{max(y+h for _, x, y, w, h in atlas.occupied)}")
    print(f"VRAM SHA256: {hashlib.sha256(packed).hexdigest()}")
    print(f"Preview: {ASSETS / 'preview.png'}")


if __name__ == '__main__':
    main()
