#!/usr/bin/env python3
"""Repaint flagged sprite records (tiles in CG2.ROM) with Zoinkity's Densha de Go! 64 English.

    repaint_cg2.py <SPRITE.LST> <orig TBL.ROM> <orig CG2.ROM> <PAL.DAT> <out TBL.ROM> <out CG2.ROM> [preview-dir] [--all]

By default only the STABLE records are repainted (tested in game without the HUD glitch); --all repaints every
record in RECORDS, including the ones not yet proven.

This is a PORT (CLAUDE.md section 11): English strings with a number are Zoinkity's, taken from the DDG64
texture whose original Japanese is the same text (`mld82r/Images/<n>.bin.png` -> `007gg4/<n>.bin.png`, same
<n>). Strings marked `operator` are the operator's own curation of a gap (2026-09-29). None = still a gap: the
original Japanese art is left untouched. No wording here is Claude's.

The game draws each label as its own box, sized to the Japanese: English is confined to that box (squeezed to
80% width, then scaled down, if it would run past). Drawn in the record's own palette indices (fill, antialiasing
ramp, and the baked drop shadow where the original has one), so the record's unnamed palette never matters.

Then re-tile and deduplicate. A tile that already exists anywhere in CG2.ROM keeps that id; new tiles take the
ids of tiles only these records used; the file is rebuilt at its original size (recompressing other tiles when
the English needs the room), since the disc is patched in place.
"""
import os, re, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import ddg_assets as A

FONT = "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf"
CAP = 0.716                      # Arial Narrow cap height, in em
SS = 4

# Styles measured from the originals: fill index, antialiasing ramp (strong -> faint), baked shadow.
HEADER = dict(cap=30, ramp=[92, 91, 90, 89], shadow=None, pal=22)          # no shadow: the engine adds it
LEGEND = dict(cap=12, ramp=[7, 78, 77, 4], shadow=None, pal=1)
ITEM   = dict(cap=19, ramp=[92, 91, 90, 89], shadow=(88, 3, 3), pal=22)    # OBJz_font
ITEM_H = dict(cap=19, ramp=[90, 89, 93, 94], shadow=(88, 3, 3), pal=22)    # OBJz_font2 (highlighted)
FOOTER = dict(cap=15, ramp=[6, 4, 5], shadow=(3, 3, 3), pal=1)
# Route select labels: pixel art, no antialiasing. A dithered vertical gradient (each row's two-index pattern is
# copied from the original label) inside a 1-pixel edge of index 62.
ROUTE  = dict(cap=24, kind="gradient", outline=62, shadow=None, pal=1)
# Route select, operator 2026-09-29: keep the Japanese (shrunk, aspect ratio kept) and add a small subtitle under it.
ROUTE_SUB = dict(kind="subtitle", scale=0.6, cap=14, outline=62, shadow=None, pal=1, light=None)

HEADERS = ["Main Menu",          # メインメニュー operator
           "Controls",           # コントロール  1032
           "Difficulty",         # 難易度        1033
           "Vibration",          # 振動          operator
           "Sound",              # サウンド      1034
           "Speedometer",        # 速度メーター  1035
           "Distances",          # 距離メーター  1036
           "Load & Save",        # ロード・セーブ operator
           "Options",            # ゲーム設定    1031
           "Load",               # ロードする    operator
           "Save"]               # セーブする    operator
ITEMS_LEFT = ["Controls",        # コントロール  1038
              "Difficulty",      # 難易度        1039
              "Vibration",       # 振動          operator
              "Sound",           # サウンド      1040
              "Speedometer",     # 速度メーター  1041
              "Distances",       # 距離メーター  1042
              "Easy",            # イージー      1048
              "Normal",          # ノーマル      1049
              "Hard",            # ハード        1050
              "Very Hard",       # ベリーハード  1051
              ("Off", "Weak", "Normal", "Strong"),   # 切 弱 並 強 operator; one box per kanji
              "Stereo",          # ステレオ      1052
              "Mono",            # モノラル      1053
              "Hidden",          # 非表示        1061
              "cm",              # cm 表示       1054
              "m",               # m 表示        1055
              "Digital",         # デカデジ      1057
              "Load",            # ロードする    operator
              "Save"]            # セーブする    operator
ITEMS_RIGHT = {0: "Two-Handed A",            # ツーハンドルA 1044
               1: "Two-Handed B",            # ツーハンドルB 1045
               2: "Two-Handed C",            # ツーハンドルC operator: 1044's words, letter transcribed
               3: "Two-Handed D",            # ツーハンドルD operator
               4: "One-Handed A",            # ワンハンドルA operator: 1046 ワンハンドル One-Handed + letter
               5: "One-Handed B",            # ワンハンドルB operator
               9: "Port A, exp. socket 1",   # ポートA拡張ソケット1 operator
               11: "Port B, exp. socket 1"}  # ポートB拡張ソケット1 operator
               # 専用コントローラ: gap

# --- HUD, pause and controls (2026-09-30). Box styles measured from the originals. ---
BUBBLE = dict(cap=10, bg=7, keep={7, 28, 0}, clear=(0, 0, 224, 64), fill=1, ramp=[1], pal=1)
# tips: black text on white; every pixel but the white, the green border and the transparent corners is text
CLOCK  = dict(cap=11, bg=1, fill=17, ramp=[17, 17], pal=1)   # 現在時刻, 次駅到着時刻; two colours only, so fill down to 35%: stems stay 2 px
CLOCK2 = dict(cap=11, bg=1, fill=74, pal=1)                                          # 次駅通過時刻
ALLOT  = dict(cap=16, bg=0, fill="template", outline=28, pal=1)                      # 持ち時間
LINE   = dict(cap=11, bg=0, fill=63, ramp=[63, 61], pal=1, align="left")             # line + series names
BANNER = dict(cap=18, bg=15, text={10, 1}, fill=10, outline=1, pal=1, margin=(16, 7), lead=1.5)  # the red start banner
PASS   = dict(cap=18, bg=7, text={72}, fill=72, pal=1)                               # 通過駅 box
PAUSE  = dict(cap=18, ramp="auto", pal=1)                                                                  # pause items and prompts
CTRL   = dict(cap=13, ramp="auto", pal=1)                                        # controls diagrams

# --- second HUD round: distance panels, results ledger, banners (2026-09-30) ---
PANEL_T = dict(cap=20, bg="rows", dither=True, text={31}, fill=31, outline=1, pal=1)             # green label straight on the checker
PANEL_B = dict(cap=20, fill="template", pal=1)                           # checker label inside a green/red box
SEC_W   = dict(cap=15, bg="rows", text={7}, fill=7, pal=1)               # 秒 box, white (the line behind is restored)
SEC_Y   = dict(SEC_W, text={10}, fill=10)                                # 秒 box, yellow
JIKO_O  = dict(cap=12, bg=1, text={17}, fill=17, pal=1, align="left")   # 定刻 / 到着時刻 / 通過時刻, orange
JIKO_Y  = dict(JIKO_O, text={10}, fill=10)                               # the same, yellow
LEDGER  = dict(cap=20, bg=0, fill=10, rings=[(15, 1), (1, 2)], pal=1, align="left", baseline=True)   # results lines
LEDGER_C = dict(LEDGER, align="center")
PASS_G  = dict(cap=20, bg=0, fill=28, rings=[(1, 3)], pal=1, baseline=True)             # green 合格!
METAL   = dict(cap=24, bg=0, fill="template", rings=[(7, 1), (28, 1)], pal=1)   # chrome words (運転評価, 合格!!)
REDB    = dict(cap=18, bg=15, text={10, 1}, fill=10, outline=1, pal=1, margin=(4, 0))  # red penalty banners
YELB    = dict(cap=18, bg=10, text={15, 1}, fill=15, outline=1, pal=1, margin=(4, 0))  # yellow banners, red text
GRAD    = dict(cap=20, bg=0, fill="template", rings=[(1, 2)], pal=1)     # gradient words on transparent
GRAD2   = dict(cap=30, bg=0, fill="template", rings=[(1, 2)], pal=1)     # the coupling game's big words
MEISY   = dict(cap=18, bg=7, ramp="auto", pal=1, margin=(3, 0))          # landmark labels: black on white
LVL     = dict(cap=20, fill="template", rings=[(1, 1)], pal=1)           # chrome difficulty badges on their colour
TETU    = dict(cap=16, bg=7, fill=1, ramp=[1, 2, 3, 4], pal=1, lead=1.35)  # conductor's advice: black, grey shading

EKI = [  # DDG64 217-308, verbatim
    'Departing',  # 217
    'Passing',  # 218
    'Stop at',  # 219
    'Station',  # 220
    'Akita',  # 221
    'Yotsugoya',  # 222
    'Wada',  # 223
    'Obarino',  # 224
    'Ugo-Sakai',  # 225
    'Mineyoshikawa',  # 226
    'Kariwano',  # 227
    'Jinguji',  # 228
    'Omagari',  # 229
    'Kita-Omagari',  # 230
    'Ugo-Yotsuya',  # 231
    'Yariminai',  # 232
    'Ugo-Nagano',  # 233
    'Uguisuno',  # 234
    'Kakunodate',  # 235
    'Shoden',  # 236
    'Jindai',  # 237
    'Sashimaki',  # 238
    'Tazawako',  # 239
    'Akabuchi',  # 240
    'Harukiba',  # 241
    'Shizukuishi',  # 242
    'Koiwai',  # 243
    'Okama',  # 244
    'Morioka',  # 245
    'Naoetsu',  # 246
    'Kuroi',  # 247
    'Saigata',  # 248
    'Kubiki',  # 249
    'Oike-Ikoi-no-Mori',  # 250
    'Uragawara',  # 251
    'Mushigawa-Osugi',  # 252
    'Hokuhoku-Oshima',  # 253
    'Matsudai',  # 254
    'Tokamachi',  # 255
    'Shinza',  # 256
    'Misashima',  # 257
    'Uonuma-Kyuryo',  # 258
    'Muikamachi',  # 259
    'Shiozawa',  # 260: Zoinkity's reads "Shizowa", a typo for 塩沢 (shio + sawa); operator-approved fix
    'Osawa',  # 261
    'Ishiuchi',  # 262
    'Echigo-Yuzawa',  # 263
    'Tokyo',  # 264
    'Yurakucho',  # 265
    'Shimbashi',  # 266
    'Hamamatsucho',  # 267
    'Tamachi',  # 268
    'Shinagawa',  # 269
    'Osaki',  # 270
    'Gotanda',  # 271
    'Meguro',  # 272
    'Ebisu',  # 273
    'Shibuya',  # 274
    'Harajuku',  # 275
    'Yoyogi',  # 276
    'Shinjuku',  # 277
    'Yokohama',  # 278
    'Higashi-Kanagawa',  # 279
    'Shin-Koyasu',  # 280
    'Tsurumi',  # 281
    'Kawasaki',  # 282
    'Kamata',  # 283
    'Omori',  # 284
    'Oimachi',  # 285
    'Kanda',  # 286
    'Akihabara',  # 287
    'Okachimachi',  # 288
    'Ueno',  # 289
    'Osaka',  # 290
    'Tsukamoto',  # 291
    'Amagasaki',  # 292
    'Tachibana',  # 293
    'Koshienguchi',  # 294
    'Nishinomiya',  # 295
    'Ashiya',  # 296
    'Konan-Yamate',  # 297
    'Settsu-Motoyama',  # 298
    'Sumiyoshi',  # 299
    'Rokkomichi',  # 300
    'Nada',  # 301
    'Sannomiya',  # 302
    'Motomachi',  # 303
    'Kobe',  # 304
    'Shin-Hanamaki',  # 305
    'Reduced:Depart',  # 306
    'Caution:Depart',  # 307
    'Restricted:Depart',  # 308
]


def _eki(n, v):
    """Station/call record n: green (28; 22 for the signal calls 90-92) on grey, or yellow (10; 15) on blue (61) for s.
    Two colours and an outline only: fill down to 35% so the squeezed long names keep their strokes."""
    c = (22 if n >= 90 else 28) if not v else (15 if n >= 90 else 10)
    return dict(cap=18, bg=61 if v else 0, fill=c, ramp=[c, c], outline=1, pal=1)


def _sig(c):
    """Signal-window label: colour c straight on the checker, solid dark outline (like the distance panels)."""
    return dict(cap=16, bg="rows", dither=True, text={c}, fill=c, outline=1, pal=1)


def _plate(v):
    """The 場/出 plate behind the label of the j/s signal variants: kept, with the English on top as in Taito's."""
    return [(32, 108, 64, 140, {1, 2, 3, 4, 5})] if v else []



TIPS = {                                   # OBJgreenaNN: Zoinkity's bubble, his line breaks
    1: ("When the train doors\nclose, the cab signal\nlight will turn on.", 583),
    2: ("Abide the speed limit\nuntil it is cancelled.", 584),
    3: ("Act promptly when\nmultiple speed limit\nsignals are given.", 585),
    4: ("Decelerate quickly\nwhen you receive\na limit signal.", 586),
    5: ("Until the next\nsignal, maintain\nthe speed limit.", 587),
    6: ("You failed to\ndecelerate in time.", 588),
    7: ("Don't continue\nto accelerate.", 589),
    8: ("Only apply the\nemergency brake\nin emergencies.", 590),
    9: ("Relay signals repeat\nsignals you can't see\nfurther down the line.", 591),
    11: ("Don't mistakingly set\nboth the brakes and\nthe master control.", 592),
    13: ("Decelerate as soon\nas you see a blinking\nspeed limit warning.", 594),
    14: ("The speed limit\nis in effect once\nit stops blinking.", 595),
    16: ("The coupling\nis too poor.", 597),
    17: ("Enjoy a high-speed\nATC-assisted\nbonus route!", 598),
    18: ("Please follow the\nschedule when\npassing stations.", 599),
    19: ("There's no electricity!\nYou'll be stuck\nif you stop!!!", 600),
    20: ("Please depart\nfrom the station.", 601),
    21: ("Please begin\ndecelerating.", 602),
    22: ("Your operating\nspeed should be\nabout 90 km/h.", 603),
    23: ("Your operating\nspeed should be\nabout 100 km/h.", 604),
    24: ("Your operating\nspeed should be\nabout 110 km/h.", 605),
    25: ("Your operating\nspeed should be\n110 ~ 120 km/h.", 606),
    26: ("Even when passing\nstations you should\nfollow the schedule.", 607),
    27: ("Service will resume\nmomentarily after\ncoupling is complete.", 608),
    28: ("As the ATC updates\nfollow the indicated\nspeed changes.", 609),   # DC ends in 。, his does not
    29: ("Your operating\nspeed should be\nabout 120 km/h.", 610),
    30: ("The next station is\na passing station!", 611),
    31: ("You'll be stopping\nat the next station!", 612),
    32: ("Your operating\nspeed should be\nabout 80 km/h.", 613),
    33: ("You're running late.\nPlease accelerate\na little to catch up.", 614),
    34: ("You're ahead of\nschedule. Please\nslow down a bit.", 615),
}   # gaps: 10 (picture), 12 警笛は足元のペダルです, 15 制限標識は解除されましたが… (DDG64's Japanese differs)
LINES = ["Yamanote Line 205 S.", "Tokaido Line 223 S.", "Tokaido Line 221 S.", "Tokaido Line 207 S.",   # 33-36
         "Tokaido Line 201 S.", "Keihin-Tohoku L. 209 S.", "Akita Shinkansen E3 S.",                    # 37-39
         "Tohoku Shinkansen 200", "Tohoku Shinkansen E2", "Hokuhoku Line HK100 M.",                     # 40-42
         "Hokuhoku Line 485 S.", "Hokuhoku Line 681 S.", "Ou Main Line 701 S.",                         # 43-45
         "Tazawako Line 701 S.", "Shinetsu Line EF63"]                                                   # 46-47

def _pad(lever_top, lever_bot, brake_top, brake_bot):
    """Pad controller diagram (OBJz_2hana-d): DDG64 1027-1029, plus the two BK near-misses (operator, 2026-09-30)."""
    return [((25, 3, 117, 23), "Master Control Shutoff"),   # マスコン切る 1027
            ((25, 24, 117, 45), "Brake Release"),           # ブレーキ解除 operator (DDG64: BK解除)
            ((189, 3, 277, 23), "Pro Mode"),                # PROモード 1027
            ((189, 25, 277, 45), "On/Off"),                 # ON/OFF 1027
            ((256, 75, 341, 94), "Emergency Brake"),        # 非常ブレーキ operator (DDG64: 非常BK)
            ((250, 130, 341, 149), "Horn"),                 # 警笛 1027
            ((4, 244, 61, 272), "M.Control"),               # マスコン 1027
            ((68, 229, 124, 249), lever_top), ((68, 269, 124, 292), lever_bot),
            ((163, 244, 220, 272), "Brake"),                # ブレーキ 1028
            ((227, 229, 284, 249), brake_top), ((227, 270, 284, 292), brake_bot),
            ((256, 74, 341, 75), "")]                       # 非常BK's top row, above its box

def _one(left_top, left_bot, right):
    """One-handle diagram (OBJz_1hana/b): DDG64 1027."""
    return _pad("", "", "", "")[:6] + [_pad("", "", "", "")[-1]] + [((4, 226, 60, 247), left_top), ((4, 270, 60, 291), left_bot),
                                       ((68, 219, 124, 238), right[0]), ((68, 250, 124, 269), right[1]),
                                       ((68, 282, 124, 300), right[2]),
                                       # the Japanese reaches a row past these boxes; the arrows sit right next to them
                                       ((4, 247, 60, 249), ""), ((4, 267, 20, 270), ""), ((68, 300, 124, 301), "")]

CAPTION_T = dict(cap=12, bg=1, fill=7, ramp=[7, 6, 4, 2], pal=1, align="left")   # train caption title
CAPTION_B = dict(cap=11, bg=1, fill=7, ramp=[7, 6, 4, 2], pal=1, align="left", lead=1.5)    # train caption body

CAPTIONS = {   # OBJsp*: DDG64 798-811. Near matches greenlit by the operator (2026-09-30): HK100形 (DDG64 型),
               # and 番代 (DDG64 番台) in the titles of 207/223/485b/681/701b and the body of 701b.
    "OBJsp201": ("201 Series", "These energy-efficient DC commuter EMUs sport a\nthyristor chopper traction system. Air suspension\non its bogies provides a comfortable ride."),              # 798
    "OBJsp205": ("205 Series", "A DC commuter employing a superimposed field\nexcitation control traction system. Yamanote line's\nSaHa 204 has 6 pairs of doors and color LCD screens."),   # 799
    "OBJsp207": ("207 Series 1000 Model", "Notable for their wide stainless steel bodies,\nthese DC commuter trains use a control\nconfiguration with one inverter per electric motor."),   # 800
    "OBJsp209": ("209 Series", "This DC commuter model, designed for mass\nproduction, did not adhere to traditional design\nconcepts and used many innovative techniques."),          # 801
    "OBJsp221": ("221 Series", "A versatile DC commuter train, utilized\nin variations ranging from 2 to 12 cars.\nMaximum operating speed is 120 km/h (~75 mph)."),             # 802
    "OBJsp223": ("223 Series 1000 Model", "A DC commuter boasting high performance, with\na maximum operating speed of 130 km/h (~81 mph).\nIt has a durable stainless steel alloy body."),  # 803
    "OBJsp485a": ("485 Series", "Capable of running on DC power and on\nAC power supplies at both 50Hz and 60Hz;\nthe interior and exterior have been refurbished."),           # 804
    "OBJsp485b": ("485 Series 3000 Model", "This dual AC & DC limited express has been\nremarkably refurbished inside and out,\ngiving the impression of a newly built car."),  # 805
    "OBJsp681": ("681 Series 2000 Model", "A dual AC & DC limited express equipped\nwith ATS-P transponder support,\ncapable of operating at 140 km/h (~87 mph)."),       # 806
    "OBJsp701a": ("701 Series", "These AC suburban models require only a\nsingle operator and serve the Tohoku region.\nThey are remarkably cold and snow-resistant."),       # 807
    "OBJsp701b": ("701 Series 5000 Model", "The 5000 model is lightweight, wearing\nbolsterless bogies fit to standard gauge.\nSingle-arm pantographs are a notable feature."),  # 808
    "OBJspe3": ("E3 Series", "Utilizes aluminum alloy car bodies,\nwith four motorized cars per trailer.\nThe E311 has a coupling device on the Tokyo side."),                   # 809
    "OBJsphk100": ("HK-100 Model", "Inverter-controlled DC train designed for fast transit.\nIts excellent acceleration / deceleration\nperformance correlates to high average speed."),  # 810
}

RECORDS = {
    **{n: dict(style=CAPTION_B, boxes=[((3, 0, 220, 22), t, CAPTION_T), ((3, 22, 318, 63), b)])
       for n, (t, b) in CAPTIONS.items()},
    **{"OBJgreena%02d" % n: dict(style=BUBBLE, boxes=[((12, 6, 212, 58), t)]) for n, (t, _) in TIPS.items()},
    # 17: the scribbled サービス・サービス is a near miss (DDG64 writes サービスサービス): kept as it is, a gap
    "OBJgreena17": dict(style=BUBBLE, boxes=[((10, 6, 136, 58), TIPS[17][0])], protect=[(139, 36, 224, 63), (204, 22, 224, 36)]),
    # 19: the scribbled プンプン is DDG64's "Stinky!" badge (600)
    "OBJgreena19": dict(style=BUBBLE, boxes=[((10, 6, 150, 58), TIPS[19][0]),
                                             ((150, 30, 218, 58), "Stinky!", dict(BUBBLE, clear=None, cap=9))]),
    "OBJjikokua": dict(style=CLOCK, boxes=[((0, 0, 80, 16), "Current Time")]),        # 現在時刻 21
    "OBJjikokub": dict(style=CLOCK, boxes=[((0, 0, 112, 16), "Arrival Time")]),       # 次駅到着時刻 22
    "OBJjikokuc": dict(style=CLOCK2, boxes=[((0, 0, 112, 16), "Next Station")]),      # 次駅通過時刻 23
    "OBJmoti01": dict(style=ALLOT, boxes=[((0, 0, 128, 24), "Allotted Time")]),   # 持ち時間 32; rows 24-31 stay clear, as in Taito's
    **{"OBJmoti%02d" % (i + 2): dict(style=LINE, boxes=[((0, 0, 176 if i else 176, 16), t)])
       for i, t in enumerate(LINES)},                                                  # line names 33-47
    "OBJhyou20": dict(style=BANNER, boxes=[((4, 0, 380, 64),
                      "You are signaled to proceed.\nSet the train in motion.")]),   # 146
    "OBJz_tuuka": dict(style=PASS, boxes=[((0, 0, 160, 30), "Passing")]),             # 通過駅 119; まで: gap
    "OBJz_pause": dict(style=PAUSE, boxes=[
        ((0, 32, 340, 64), "Do you want to quit?"),            # 運転を中止しますか？ 884
        ((0, 64, 340, 96), "Do you want to restart?"),         # 始発駅に戻りますか？ 883
        ((0, 96, 191, 127), "Resume"), ((192, 96, 384, 127), "Resume"),              # 運転再開 878
        ((0, 128, 191, 159), "Quit"), ((192, 128, 384, 159), "Quit"),                # 運転中止 879
        ((0, 160, 191, 190), "Retry Route"), ((192, 160, 384, 190), "Retry Route"),  # 始発駅に戻る 880
        ((0, 226, 96, 255), "Yes"), ((96, 226, 191, 255), "No"),                     # はい いいえ 881 882
        ((192, 226, 288, 255), "Yes"), ((288, 226, 384, 255), "No"),                 # 画面位置調整, 標準に戻す, 調整終了: gaps
        *[((x, y, x + 84, y + 32), t, dict(PAUSE, align="left", margin=(4, 0)))   # 上 下 左 右 next to the arrows: operator
          for y, t in ((256, "Up"), (288, "Down"), (320, "Left"), (352, "Right")) for x in (88, 280)]]),
    "OBJz_2hana": dict(style=CTRL, boxes=_pad("Off", "Full", "Full", "Off")),       # 切る/加速, 非常/解除
    "OBJz_2hanb": dict(style=CTRL, boxes=_pad("Off", "Full", "Off", "Full")),       # 切る/加速, 解除/非常
    "OBJz_2hanc": dict(style=CTRL, boxes=_pad("Full", "Off", "Full", "Off")),       # 加速/切る, 非常/解除
    "OBJz_2hand": dict(style=CTRL, boxes=_pad("Full", "Off", "Off", "Full")),       # 加速/切る, 解除/非常
    "OBJz_1hana": dict(style=CTRL, boxes=_one("Brake", "M.Control", ("Brake", "Off", "Full"))),   # ブレーキ⇕マスコン; 非常 切る 加速
    "OBJz_1hanb": dict(style=CTRL, boxes=_one("M.Control", "Brake", ("Full", "Off", "Brake"))),   # マスコン⇕ブレーキ; 加速 切る 非常
    "OBJz_2han": dict(style=CTRL, boxes=[                                            # train controller: DDG64 1030
        ((2, 20, 62, 50), "Master Control"),
        ((66, 4, 126, 26), "Off"), ((66, 44, 126, 68), "Full"),
        ((153, 20, 213, 50), "Brake"),
        ((217, 4, 277, 26), "Increase"), ((217, 44, 277, 68), "Release"),
        ((26, 218, 118, 236), "Pro Mode"), ((26, 240, 118, 262), "On/Off"),
        ((186, 243, 277, 262), "Horn")]),

    # distance panels (top label only; あと / まで / m / Cm / OVER stay)
    "OBJdist40": dict(style=PANEL_T, boxes=[((0, 3, 128, 30), "Stopping"), ((0, 38, 40, 64), "in")]),   # 停止位置 117, あと 814
    "OBJdist41": dict(style=PASS, boxes=[((1, 1, 127, 31), "Passing")]),         # 通過駅 119
    **{"OBJdist%d" % n: dict(style=PANEL_B, boxes=[((1, 1, 127, 31), "Success")] +   # 合格範囲 116
                                 ([((0, 38, 40, 64), "in", PANEL_T)] if n in (42, 43) else []))  # あと 814
       for n in (42, 43, 44, 45)},
    **{"OBJdist%d" % n: dict(style=PANEL_T, boxes=[((0, 38, 40, 64), "in")]) for n in (47, 48)},   # あと 814; 連結位置: gap
    "OBJdist46": dict(style=PANEL_B, boxes=[((1, 1, 127, 31), "Overrun")]),      # 過走 118
    "OBJz_gover": dict(style=PANEL_B, boxes=[((1, 1, 151, 31), "Success")]),     # 合格範囲 116
    "OBJz_gstop": dict(style=PANEL_T, boxes=[((0, 3, 152, 30), "Stopping"), ((0, 38, 40, 64), "in")]),   # 117, 814
    "OBJtime0c": dict(style=SEC_W, boxes=[((6, 1, 42, 38), "Sec")]),             # 秒 178
    "OBJtime0cy": dict(style=SEC_Y, boxes=[((6, 1, 42, 38), "Sec")]),            # 秒 178
    "OBJjikokuz1": dict(style=JIKO_O, boxes=[((0, 0, 96, 16), "OnTime!"), ((0, 16, 96, 32), "Arrival Time")]),  # 1114 1115
    "OBJjikokuz2": dict(style=JIKO_O, boxes=[((0, 0, 96, 16), "OnTime!"), ((0, 16, 96, 32), "Next Station")]),  # 1114 1116
    "OBJjikokuz3": dict(style=JIKO_O, boxes=[((0, 0, 96, 16), "OnTime!"), ((0, 16, 96, 32), "Arrival Time", JIKO_Y)]),
    "OBJjikokuz4": dict(style=JIKO_O, boxes=[((0, 0, 96, 16), "OnTime!"), ((0, 16, 96, 32), "Next Station", JIKO_Y)]),
    # results ledger (Cm, m, x, the digits and EXCELLENT! stay; 減点 168 is a gap)
    "OBJhyou02": dict(style=METAL, boxes=[((0, 2, 176, 46), "Evaluation")]),     # 運転評価 141
    "OBJhyou03": dict(style=LEDGER, boxes=[((12, 0, 124, 32), "Schedule")]),     # ダイヤ 165
    **{n: dict(style=LEDGER, boxes=[((12, 0, 124, 32), "Schedule"),              # ダイヤ 165
                                    ((316, 0, 358, 32), "Sec", LEDGER_C),         # 秒 178
                                    ((x, 0, 471, 32), "Sec", LEDGER_C)])
       for n, x in (("OBJhyou004", 430), ("OBJhyou004b", 430), ("OBJhyou004c", 430))},
    **{n: dict(style=LEDGER, boxes=[((0, 0, 180, 32), "Overrun"),                # オーバーラン 177
                                    ((429, 0, 471, 32), "Sec", LEDGER_C)])        # 秒 178
       for n in ("OBJhyou005", "OBJhyou005b", "OBJhyou005c", "OBJhyou05", "OBJhyou05b", "OBJhyou05c")},
    "OBJhyou04": dict(style=LEDGER, boxes=[((12, 0, 124, 32), "Schedule"),       # ダイヤ 165
                                           ((236, 0, 312, 32), "Delay", LEDGER_C),   # 遅れ 176
                                           ((429, 0, 472, 32), "Sec", LEDGER_C)]),   # 秒 178
    "OBJhyou06": dict(style=LEDGER, boxes=[((12, 0, 150, 32), "Stop Position"),  # 停止位置 181
                                           ((362, 0, 454, 32), "Pass!", PASS_G)]),   # 合格! 169
    "OBJhyou07": dict(style=PASS_G, boxes=[((0, 0, 80, 32), "On Time!")]),       # 定刻! 180
    "OBJhyou08": dict(style=LEDGER_C, boxes=[((0, 0, 64, 32), "Early")]),        # 早着 179
    "OBJhyou09": dict(style=LEDGER, boxes=[((10, 13, 90, 48), "Total"),          # 合計 170
                                           ((96, 13, 240, 48), "Penalty"),        # マイナス 173
                                           ((429, 13, 472, 48), "Sec", LEDGER_C)]),  # 秒 178
    "OBJhyou21": dict(style=LEDGER_C, boxes=[((0, 0, 48, 32), "Sec")]),          # 秒 178
    "OBJhyou19k": dict(style=PASS_G, boxes=[((0, 0, 48, 32), "Sec")]),          # green, like its digits         # 秒 178
    "OBJhyou22": dict(style=LEDGER, boxes=[((0, 0, 192, 32), "Station Acceleration")]),  # 駅構内再加速 166
    "OBJhyou23": dict(style=LEDGER, boxes=[((0, 0, 224, 32), "Speeding at Station")]),   # 駅進入速度超過 167
    "OBJhyou24": dict(style=PASS_G, boxes=[((0, 0, 80, 32), "Pass!")]),          # 合格! 169
    "OBJhyou25": dict(style=LEDGER_C, boxes=[((0, 0, 64, 32), "None")]),         # なし 175
    "OBJhyou31": dict(style=LEDGER, boxes=[((12, 0, 150, 32), "Stop Position"),  # 停止位置 181
                                           ((386, 0, 478, 32), "Pass!", PASS_G)]),   # 合格! 169
    "OBJhyou32": dict(style=LEDGER, boxes=[((0, 0, 192, 32), "Emergency Brake")]),   # 非常制動停車 171
    "OBJhyou34": dict(style=LEDGER, boxes=[((0, 0, 130, 32), "Stop Position"),   # 停止位置 181
                                           ((372, 0, 476, 32), "Pass!", METAL)]),    # 合格!! 137
    # signal windows (label under the lamps, on the checker). 停止信号, 制限 and 進行 alone: gaps (DDG64 190, 194, 198);
    # the 場/出 plates stay (DDG64 215, 216 keep them). Gradient signs 勾配なし/上り勾配/下り勾配 (85/87/83) wait.
    **{n: dict(style=_sig(15), boxes=[((0, 104, 96, 136), "Warning")])                   # 緊急停止 184-188
       for n in ("OBJwin001", "OBJwin002", "OBJwin003", "OBJwin004", "OBJwin005")},
    **{n + v: dict(style=_sig(31), boxes=[((0, y, 96, y + 26), "Proceed")], protect=_plate(v))   # 進行信号 90/189
       for n, y in (("OBJwin006", 103), ("OBJwin039", 111)) for v in ("", "j", "s")},
    **{n + v: dict(style=_sig(75), boxes=[((0, 96, 96, 120), "Caution"), ((0, 120, 96, 144), "Limit 45km/h")],
                   protect=_plate(v))                                                     # 注意信号 速度45km/h 199
       for n in ("OBJwin007", "OBJwin037") for v in ("", "j", "s")},
    **{"OBJwin036" + v: dict(style=_sig(15), boxes=[((0, 96, 96, 120), "Restricted"), ((0, 120, 96, 144), "Limit 25km/h")],
                             protect=_plate(v)) for v in ("", "j", "s")},                # 警戒信号 速度25km/h 200
    **{"OBJwin038" + v: dict(style=_sig(75), boxes=[((0, 96, 96, 120), "Reduced"), ((0, 120, 96, 144), "Limit 70km/h")],
                             protect=_plate(v)) for v in ("", "j", "s")},                # 減速信号 速度70km/h 201
    "OBJwin040": dict(style=_sig(31), boxes=[((0, 119, 96, 144), "Express")]),            # 高速進行 191
    "OBJwin041": dict(style=_sig(7), boxes=[((0, 96, 96, 120), "Stop", _sig(15)),         # 停止 193
                                            ((0, 120, 96, 144), "Relay")]),               # 中継信号 192
    "OBJwin042": dict(style=_sig(7), boxes=[((0, 120, 96, 144), "Relay")]),               # 制限: gap; 中継信号 192
    "OBJwin042a": dict(style=_sig(7), boxes=[((0, 96, 96, 120), "Limit 25km/h", _sig(15)), ((0, 120, 96, 144), "Relay")]),  # 197
    "OBJwin042b": dict(style=_sig(7), boxes=[((0, 96, 96, 120), "Limit 45km/h", _sig(75)), ((0, 120, 96, 144), "Relay")]),  # 195
    "OBJwin042c": dict(style=_sig(7), boxes=[((0, 96, 96, 120), "Limit 70km/h", _sig(75)), ((0, 120, 96, 144), "Relay")]),  # 196
    "OBJwin043": dict(style=_sig(7), boxes=[((0, 120, 96, 144), "Relay")]),               # 進行: gap; 中継信号 192
    "OBJwin044": dict(style=_sig(7), boxes=[((0, 95, 96, 120), "Express", _sig(31)), ((0, 120, 96, 144), "Relay")]),  # 191 192
    **{"OBJwin%03d" % i: dict(style=_sig(10), boxes=[((0, 63, 96, 96), "Speed Limit")])   # 速度制限 89
       for i in list(range(17, 33)) + list(range(48, 54))},
    "OBJwin033": dict(style=_sig(28), boxes=[((0, 64, 96, 96), "No Limit")]),             # 制限解除 79
    "OBJwin034": dict(style=_sig(10), boxes=[((0, 63, 96, 96), "Horn")]),                 # 警笛鳴せ 81
    # departure calls and station names (OBJeki001-092 = DDG64 217-308, same Japanese in the same order); the plain
    # record is green on grey, the s one yellow on blue. 260 塩沢 fixes Zoinkity's "Shizowa" typo (operator).
    **{"OBJeki%03d" % (i + 1) + v: dict(style=_eki(i + 1, v), boxes=[((0, 0, 999, 32), t)])
       for i, t in enumerate(EKI) for v in ("", "s")},
    # route boards: each station column -> Zoinkity's name (EKI numbers), turned 90 degrees; see board()
    'OBJsouab01': dict(style=dict(pal=1), board=[30, 31, 32, 33, 34, 35, 36, 37, 38, 39]),
    'OBJsouab02': dict(style=dict(pal=1), board=[39, 40, 41, 42, 43]),
    'OBJsouab03': dict(style=dict(pal=1), board=[43, 44, 45, 46, 47]),
    'OBJsoubb01': dict(style=dict(pal=1), board=[30, 31, 32]),
    'OBJsoubb02': dict(style=dict(pal=1), board=[32, 33]),
    'OBJsoubb03': dict(style=dict(pal=1), board=[33, 34, 35]),
    'OBJsoubb03b': dict(style=dict(pal=1), board=[33, 34, 35]),
    'OBJsoubb04': dict(style=dict(pal=1), board=[35, 36, 37]),
    'OBJsoubb05': dict(style=dict(pal=1), board=[37, 38]),
    'OBJsoubb06': dict(style=dict(pal=1), board=[38, 39]),
    'OBJsoubb07': dict(style=dict(pal=1), board=[39, 40, 41, 42, 43]),
    'OBJsoucb01': dict(style=dict(pal=1), board=[5, 6, 7, 8, 9, 10, 11, 12, 13]),
    'OBJsoucb01b': dict(style=dict(pal=1), board=[5, 6, 7, 8, 9, 10, 11, 12, 13]),
    'OBJsoucb02': dict(style=dict(pal=1), board=[13, 14, 15, 16, 17, 18, 19]),
    'OBJsoucb03': dict(style=dict(pal=1), board=[19, 20, 21, 22, 23]),
    'OBJsoucb04': dict(style=dict(pal=1), board=[23, 24, 25, 26]),
    'OBJsoucb05': dict(style=dict(pal=1), board=[26, 27, 28, 29]),
    'OBJsoucb06': dict(style=dict(pal=1), board=[29, 89]),
    'OBJsoucb06b': dict(style=dict(pal=1), board=[29, 89]),
    'OBJsoudb01': dict(style=dict(pal=1), board=[5, 6]),
    'OBJsoudb02': dict(style=dict(pal=1), board=[6, 7]),
    'OBJsoudb03': dict(style=dict(pal=1), board=[7, 8]),
    'OBJsoudb04': dict(style=dict(pal=1), board=[8, 9]),
    'OBJsoudb05': dict(style=dict(pal=1), board=[9, 10]),
    'OBJsoudb06': dict(style=dict(pal=1), board=[10, 11]),
    'OBJsoudb07': dict(style=dict(pal=1), board=[11, 12]),
    'OBJsoudb08': dict(style=dict(pal=1), board=[12, 13]),
    'OBJsoueb01': dict(style=dict(pal=1), board=[13, 14]),
    'OBJsoueb02': dict(style=dict(pal=1), board=[14, 15]),
    'OBJsoueb03': dict(style=dict(pal=1), board=[15, 16]),
    'OBJsoueb04': dict(style=dict(pal=1), board=[16, 17]),
    'OBJsoueb05': dict(style=dict(pal=1), board=[17, 18]),
    'OBJsoueb06': dict(style=dict(pal=1), board=[18, 19]),
    'OBJsoueb07': dict(style=dict(pal=1), board=[19, 20]),
    'OBJsoueb08': dict(style=dict(pal=1), board=[20, 21]),
    'OBJsoueb09': dict(style=dict(pal=1), board=[21, 22]),
    'OBJsoueb10': dict(style=dict(pal=1), board=[22, 23]),
    'OBJsoueb11': dict(style=dict(pal=1), board=[23, 24]),
    'OBJsoueb12': dict(style=dict(pal=1), board=[24, 25]),
    'OBJsoueb13': dict(style=dict(pal=1), board=[25, 26]),
    'OBJsoueb14': dict(style=dict(pal=1), board=[26, 27]),
    'OBJsoueb15': dict(style=dict(pal=1), board=[27, 28]),
    'OBJsoueb16': dict(style=dict(pal=1), board=[28, 29]),
    'OBJsoufb01': dict(style=dict(pal=1), board=[74, 75, 76]),
    'OBJsoufb02': dict(style=dict(pal=1), board=[76, 77, 78, 79, 80]),
    'OBJsoufb03': dict(style=dict(pal=1), board=[80, 81, 82, 83]),
    'OBJsoufb04': dict(style=dict(pal=1), board=[83, 84]),
    'OBJsoufb05': dict(style=dict(pal=1), board=[84, 85, 86]),
    'OBJsoufb06': dict(style=dict(pal=1), board=[86, 87]),
    'OBJsoufb07': dict(style=dict(pal=1), board=[87, 88]),
    'OBJsougb01': dict(style=dict(pal=1), board=[74, 75]),
    'OBJsougb02': dict(style=dict(pal=1), board=[75, 76]),
    'OBJsougb03': dict(style=dict(pal=1), board=[76, 77]),
    'OBJsougb04': dict(style=dict(pal=1), board=[77, 78]),
    'OBJsougb05': dict(style=dict(pal=1), board=[78, 79]),
    'OBJsougb06': dict(style=dict(pal=1), board=[79, 80]),
    'OBJsougb07': dict(style=dict(pal=1), board=[80, 81]),
    'OBJsougb08': dict(style=dict(pal=1), board=[81, 82]),
    'OBJsougb09': dict(style=dict(pal=1), board=[82, 83]),
    'OBJsougb10': dict(style=dict(pal=1), board=[83, 84]),
    'OBJsougb11': dict(style=dict(pal=1), board=[84, 85]),
    'OBJsougb12': dict(style=dict(pal=1), board=[85, 86]),
    'OBJsougb13': dict(style=dict(pal=1), board=[86, 87]),
    'OBJsougb14': dict(style=dict(pal=1), board=[87, 88]),
    'OBJsouhb01': dict(style=dict(pal=1), board=[62, 63]),
    'OBJsouhb02': dict(style=dict(pal=1), board=[63, 64]),
    'OBJsouhb03': dict(style=dict(pal=1), board=[64, 65]),
    'OBJsouhb04': dict(style=dict(pal=1), board=[65, 66]),
    'OBJsouhb05': dict(style=dict(pal=1), board=[66, 67]),
    'OBJsouhb06': dict(style=dict(pal=1), board=[67, 68]),
    'OBJsouhb07': dict(style=dict(pal=1), board=[68, 69]),
    'OBJsouhb08': dict(style=dict(pal=1), board=[69, 53]),
    'OBJsouib01': dict(style=dict(pal=1), board=[62, 63]),
    'OBJsouib02': dict(style=dict(pal=1), board=[63, 64]),
    'OBJsouib03': dict(style=dict(pal=1), board=[64, 65]),
    'OBJsouib04': dict(style=dict(pal=1), board=[65, 66]),
    'OBJsouib05': dict(style=dict(pal=1), board=[66, 67]),
    'OBJsouib06': dict(style=dict(pal=1), board=[67, 68]),
    'OBJsouib07': dict(style=dict(pal=1), board=[68, 69]),
    'OBJsouib08': dict(style=dict(pal=1), board=[69, 53]),
    'OBJsouib09': dict(style=dict(pal=1), board=[53, 52]),
    'OBJsouib09b': dict(style=dict(pal=1), board=[53, 52]),
    'OBJsouib10': dict(style=dict(pal=1), board=[52, 51, 50, 49, 48]),
    'OBJsouib11': dict(style=dict(pal=1), board=[48, 70, 71]),
    'OBJsouib12': dict(style=dict(pal=1), board=[71, 72, 73]),
    'OBJsoujb01': dict(style=dict(pal=1), board=[48, 49]),
    'OBJsoujb02': dict(style=dict(pal=1), board=[49, 50]),
    'OBJsoujb03': dict(style=dict(pal=1), board=[50, 51]),
    'OBJsoujb04': dict(style=dict(pal=1), board=[51, 52]),
    'OBJsoujb05': dict(style=dict(pal=1), board=[52, 53]),
    'OBJsoujb06': dict(style=dict(pal=1), board=[53, 54]),
    'OBJsoujb07': dict(style=dict(pal=1), board=[54, 55]),
    'OBJsoujb07b': dict(style=dict(pal=1), board=[54, 55]),
    'OBJsoujb08': dict(style=dict(pal=1), board=[55, 56]),
    'OBJsoujb09': dict(style=dict(pal=1), board=[56, 57]),
    'OBJsoujb10': dict(style=dict(pal=1), board=[57, 58]),
    'OBJsoujb11': dict(style=dict(pal=1), board=[58, 59]),
    'OBJsoujb12': dict(style=dict(pal=1), board=[59, 60]),
    'OBJsoujb13': dict(style=dict(pal=1), board=[60, 61]),
    'OBJsoulb01': dict(style=dict(pal=1), board=[23, 24, 25, 26, 27, 28, 29]),
    'OBJsoumb01': dict(style=dict(pal=1), board=[23, 24]),
    **{n: dict(style=dict(cap=11, bg=10, text={1}, fill=1, ramp=[1, 1], pal=1), boxes=[((2, 3, 62, 18), "Cab Signal")])
       for n in ("OBJz_syanai0", "OBJz_syanai1")},                                   # 車内信号 345
    # landmark labels (OBJmeisy* = DDG64 309-344, same Japanese in the same order), one line each
    'OBJmeisya01': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Akita Vehicle Yard')]),   # 309
    'OBJmeisya02': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Akita-Kita Bypass')]),   # 310
    'OBJmeisya03': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Akita Expressway')]),   # 311
    'OBJmeisya04': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Iwami River')]),   # 312
    'OBJmeisya05': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'First Tamagawa Bridge')]),   # 313
    'OBJmeisya06': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Sainai River')]),   # 314
    'OBJmeisya07': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Iwasehashi')]),   # 315
    'OBJmeisya08': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Shidonai Signal Station')]),   # 316
    'OBJmeisya09': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Ochizawa Signal Station')]),   # 317
    'OBJmeisya10': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Akita Road')]),   # 318
    'OBJmeisya11': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Tohoku Expressway')]),   # 319
    'OBJmeisyb01': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Seki River')]),   # 320
    'OBJmeisyb02': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Hokuriku Expressway')]),   # 321
    'OBJmeisyb03': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Kata River')]),   # 322
    'OBJmeisyb04': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Shinano River')]),   # 323
    'OBJmeisyb05': dict(style=MEISY, boxes=[((0, 0, 999, 32), "Kan'etsu Expressway")]),   # 324
    'OBJmeisyb06': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Gimyo Signal Station')]),   # 325
    'OBJmeisyb07': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Yakushitoge Signal Station')]),   # 326
    'OBJmeisyb08': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Akakura Signal Station')]),   # 327
    'OBJmeisyc01': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Yodo River')]),   # 328
    'OBJmeisyc02': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Kanzaki River')]),   # 329
    'OBJmeisyc03': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Shouge River')]),   # 330
    'OBJmeisyc04': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Muko River')]),   # 331
    'OBJmeisyc05': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Hankyu Imazu Line')]),   # 332
    'OBJmeisyc06': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Shuku River')]),   # 333
    'OBJmeisyd01': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Yokohama Line')]),   # 334
    'OBJmeisyd02': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Tsurumi Line')]),   # 335
    'OBJmeisyd03': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Tsurumi River')]),   # 336
    'OBJmeisyd04': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Nambu Line')]),   # 337
    'OBJmeisyd05': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Tama River')]),   # 338
    'OBJmeisye01': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Pass')]),   # 339
    'OBJmeisyf01': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Meguro River')]),   # 340
    'OBJmeisyf02': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Meguro Route')]),   # 341
    'OBJmeisyf03': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Shibuya Route')]),   # 342
    'OBJmeisyf04': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Meiji Shrine')]),   # 343
    'OBJmeisyf05': dict(style=MEISY, boxes=[((0, 0, 999, 32), 'Shinjuku Route')]),   # 344
    # E3 coupling HUD (DDG64 813-817); 813's "Tohoka" is a typo for 東北 (operator-approved fix, cf. 319 Tohoku)
    "OBJheigo01": dict(style=dict(cap=18, bg=62, text={7}, fill=7, ramp=[7, 7], pal=1), boxes=[((214, 1, 306, 31), "Tohoku")]),
    "OBJheigo02": dict(style=dict(cap=18, bg=1, text={7}, fill=7, ramp=[7, 7], pal=1), boxes=[((0, 0, 62, 32), "in")]),   # あと 814
    "OBJheigo03": dict(style=dict(cap=20, bg=28, text={1}, fill=1, ramp=[1, 1], pal=1), boxes=[((0, 0, 160, 32), "Ready")]),     # 併合準備完了 815
    "OBJheigo04": dict(style=dict(cap=20, bg=28, text={1}, fill=1, ramp=[1, 1], pal=1), boxes=[((0, 0, 160, 32), "Complete")]),  # 併合完了 816
    "OBJheigo05": dict(style=dict(cap=20, bg=1, text={10}, fill=10, ramp=[10, 10], pal=1), boxes=[((0, 0, 160, 32), "Caution")]),  # 距離注意 817 (his ‖ bars left out)
    # coupling bonus game (DDG64 823-830)
    "OBJrenk01": dict(style=GRAD2, boxes=[((0, 0, 320, 48), "Bonus Game")]),        # ボーナスゲーム 823
    "OBJrenk03": dict(style=dict(cap=24, bg="rows", text={58, 63}, fill=58, outline=63, pal=1), boxes=[
        ((10, 12, 232, 62), "Shock Meter"),                                           # 衝撃メーター 824
        ((236, 14, 340, 44), "Acceptable", dict(cap=14, bg="rows", text={28}, fill=28, ramp=[28, 28], pal=1)),  # 合格範囲 825
        ((396, 14, 462, 44), "Danger", dict(cap=14, bg="rows", text={57}, fill=57, ramp=[57, 57], pal=1))]),     # 危険 825
    'OBJrenk05': dict(style=GRAD2, boxes=[((0, 0, 999, 48), 'Success')]),   # 827
    'OBJrenk06': dict(style=GRAD2, boxes=[((0, 0, 999, 48), 'Failed')]),   # 828
    'OBJrenk07': dict(style=GRAD2, boxes=[((0, 0, 999, 48), 'Ready')]),   # 829
    'OBJrenk08': dict(style=GRAD2, boxes=[((0, 0, 999, 48), 'Start')]),   # 830
    # difficulty (DDG64 525-529)
    "OBJselect08": dict(style=dict(cap=10, bg=0, fill=15, outline=17, pal=1), boxes=[((0, 0, 64, 16), "Difficulty")]),   # 難易度 525
    'OBJselect13': dict(style=LVL, boxes=[((0, 0, 64, 32), 'Lvl.1')]),   # 526
    'OBJselect14': dict(style=LVL, boxes=[((0, 0, 64, 32), 'Lvl.2')]),   # 527
    'OBJselect15': dict(style=LVL, boxes=[((0, 0, 64, 32), 'Lvl.3')]),   # 528
    "OBJselect16": dict(style=dict(LVL, face="/System/Library/Fonts/Supplemental/Arial Unicode.ttf"), boxes=[((0, 0, 64, 32), "Lvl.☆")]),   # 529: ☆ needs Arial Unicode
    # conductor's advice (OBJtetu* = DDG64 565-577 in order; 08 and 09 are near misses, held)
    "OBJtetu01": dict(style=TETU, boxes=[((3, 20, 190, 118), 'Please stop at\nthe station as\ninstructed.')]),   # 565
    "OBJtetu02": dict(style=TETU, boxes=[((3, 20, 190, 118), 'Try not to brake\nso roughly.')]),   # 566
    "OBJtetu03": dict(style=TETU, boxes=[((3, 20, 190, 118), 'Please obey\nthe signals.')]),   # 567
    "OBJtetu04": dict(style=TETU, boxes=[((3, 20, 190, 118), 'The train cannot\nstop suddenly.')]),   # 568
    "OBJtetu05": dict(style=TETU, boxes=[((3, 20, 190, 118), 'Please coast.')]),   # 569
    "OBJtetu06": dict(style=TETU, boxes=[((3, 20, 190, 118), 'Overrunning a\ncrossing is very\ndangerous. Check\nthe driver is safe!')]),   # 570
    "OBJtetu07": dict(style=TETU, boxes=[((3, 20, 190, 118), 'Press Start\nto continue.')]),   # 571
    "OBJtetu10": dict(style=TETU, boxes=[((3, 20, 190, 118), 'Great coasting!')]),   # 574
    "OBJtetu11": dict(style=TETU, boxes=[((3, 20, 190, 118), 'Iron-chan is\nimpressed!')]),   # 575
    "OBJtetu12": dict(style=TETU, boxes=[((3, 20, 190, 118), 'When operating\nthe train, always\nbe punctual.')]),   # 576
    "OBJtetu13": dict(style=TETU, boxes=[((3, 20, 190, 118), 'The train has\nbeen stopped\nwirelessly. Stinky!')]),   # 577
    # あと on the distance panels = DDG64 814 "in"
    # red penalty banners
    "OBJhyou15": dict(style=REDB, boxes=[((0, 0, 128, 32), "Sudden Braking")]),  # 急制動 142
    "OBJhyou16": dict(style=REDB, boxes=[((0, 0, 144, 32), "Signal Ignored")]),  # 標識無視 143
    "OBJhyou17": dict(style=REDB, boxes=[((0, 0, 192, 32), "Speeding")]),        # 制限速度超過 144
    "OBJhyou18": dict(style=REDB, boxes=[((0, 0, 176, 32), "Station Passed")]),  # 停車駅通過 145
    "OBJhyou27": dict(style=REDB, boxes=[((0, 0, 256, 32), "Early Stop")]),      # 停止位置手前です 147
    "OBJhyou28": dict(style=REDB, boxes=[((0, 0, 256, 32), "Check Cab Signal")]),    # 知らせ灯確認ミス 148
    "OBJhyou29": dict(style=REDB, boxes=[((0, 0, 176, 32), "Struck Bollard")]),  # 車止め激突 149
    "OBJhyou30": dict(style=REDB, boxes=[((0, 0, 144, 32), "Excess Horn")]),     # 警笛過剰 150
    "OBJhyou33": dict(style=REDB, boxes=[((0, 0, 176, 32), "Behind Schedule")]), # ダイヤ遅れ 151
    "OBJhyou36": dict(style=REDB, boxes=[((0, 0, 176, 32), "Collision")]),       # 車両激突 152
    # banners
    "OBJkei05": dict(style=dict(REDB, cap=26, margin=(10, 4)), boxes=[((0, 0, 224, 48), "ATS Actuation")]),   # ATS作動 120
    "OBJkei17": dict(style=dict(YELB, cap=26, margin=(10, 4)), boxes=[((0, 0, 224, 48), "ATS Confirmed")]),   # ATS確認 122
    "OBJmes05": dict(style=dict(cap=13, bg=0, fill=10, outline=1, pal=1),        # 運転継続？ CONTINUE -> CONTINUE? 123
                     boxes=[((0, 0, 160, 32), ""), ((0, 32, 160, 48), "CONTINUE?")]),
    "OBJmes06": dict(style=YELB, boxes=[((0, 0, 256, 32), "Use Emergency Brake")]),   # 非常ブレーキ使え 124 (one line fits here)
    "OBJmes07": dict(style=GRAD, boxes=[((0, 0, 224, 32), "Risk Averted!")]),    # 危険回避合格！ 125
    "OBJmes08": dict(style=GRAD, boxes=[((0, 0, 160, 32), "Resuming")]),         # 運転再開 126
    "OBJmes09": dict(style=dict(REDB, cap=40, margin=(10, 6)), boxes=[((0, 0, 192, 64), "ACCIDENT")]),  # 事故 127
    "OBJmes11": dict(style=GRAD, boxes=[((0, 0, 160, 31), "")]),                 # 運転中止 GAME OVER -> GAME OVER 129
    "OBJmes12": dict(style=GRAD, boxes=[((0, 0, 160, 31), "")]),                 # 運転終了 GAME OVER -> GAME OVER 130
    "OBJmes13": dict(style=dict(REDB, cap=22), boxes=[((50, 16, 190, 46), "Time Over")]),  # 時間切れ 131
    "OBJmes18": dict(style=REDB, boxes=[((0, 0, 224, 32), "Speeding at Station")]),        # 駅進入速度超過 167
    "OBJmes21": dict(style=GRAD, boxes=[((0, 0, 256, 32), "Safe Transition")]),  # セクション通過 132
    "OBJmes23": dict(style=GRAD, boxes=[((0, 0, 208, 49), "")]),                 # スタートボタンで運転開始 -> PUSH START BUTTON 134

    "OBJz_submenu":  dict(style=HEADER, band=48, cols=[(0, 288)], labels={(i, 0): t for i, t in enumerate(HEADERS)}),
    "OBJz_submenu2": dict(style=HEADER, band=48, cols=[(0, 288)], labels={(i, 0): t for i, t in enumerate(
        HEADERS + ["Train Select",         # 電車選択 869
                   "Route Select"])}),     # 路線選択 868
    "OBJz_kettei":   dict(style=LEGEND, band=32, cols=[(0, 112)], labels={
        (0, 0): "Select",                  # 選択       870
        (1, 0): "Back",                    # キャンセル 870
        (2, 0): "Choose",                  # 決定       870
        (3, 0): None}),                    # おわり     gap
    "OBJz_font":  dict(style=ITEM, band=32, cols=[(0, 190), (190, 432)], labels=dict(
        [((i, 0), t) for i, t in enumerate(ITEMS_LEFT)] + [((i, 1), t) for i, t in ITEMS_RIGHT.items()])),
    "OBJz_font2": dict(style=ITEM_H, band=32, cols=[(0, 190), (190, 432)], labels=dict(
        [((i, 0), t) for i, t in enumerate(ITEMS_LEFT)] + [((i, 1), t) for i, t in ITEMS_RIGHT.items()])),
    "OBJexsel01": dict(style=ROUTE_SUB, band=48, cols=[(0, 160)], labels={(0, 0): "Kanto"}),     # 関東路線 operator
    "OBJexsel02": dict(style=ROUTE_SUB, band=48, cols=[(0, 160)], labels={(0, 0): "Kansai"}),    # 関西路線 operator
    "OBJexsel03": dict(style=ROUTE_SUB, band=48, cols=[(0, 160)], labels={(0, 0): "Hokuriku"}),  # 北陸路線 operator
    "OBJexsel04": dict(style=ROUTE_SUB, band=48, cols=[(0, 160)], labels={(0, 0): "Tohoku"}),    # 東北路線 operator
    # button icons at x 1-30 and 161-190 stay; only the two text boxes are redrawn
    "OBJz_ranking":  dict(style=FOOTER, band=32, cols=[(33, 158), (193, 384)], labels={
        (0, 0): "Next",                    # 次に進む       738
        (0, 1): "Main Menu"}),             # メニューに戻る 739
    "OBJz_ranking2": dict(style=FOOTER, band=32, cols=[(33, 158), (193, 384)], labels={
        (0, 0): "Next",                    # 次に進む       740
        (0, 1): "Main Menu"}),             # メニューに戻る 741
}


# Records tested in game without the HUD glitch (2026-09-30, split builds): the menus, the first HUD round, the
# departure calls and station names, and the signal windows. The glitch is somewhere in the rest of the second HUD
# round (distance panels, time box, time panels, results, banners); that and the later batches build with --all.
STABLE = re.compile(r"^OBJ(z_submenu|z_font|z_kettei|z_ranking|exsel|greena|sp|jikoku[abc]$|moti|hyou20$|z_tuuka$"
                    r"|z_pause$|z_[12]han|eki|win)")


def coverage(text, cap, w, h):
    """(h, w) coverage of `text` at cap height `cap`, left-aligned and vertically centred, fitted to w."""
    font = ImageFont.truetype(FONT, int(round(cap * SS / CAP)))
    l, t, r, b = font.getbbox(text)
    img = Image.new("L", (r - l + 8, b - t + 8))
    ImageDraw.Draw(img).text((4 - l, 4 - t), text, 255, font=font)
    img = img.crop(img.getbbox())
    tw, th = img.width / SS, img.height / SS
    sx = min(1.0, w / tw)
    sy = 1.0
    if sx < 0.8:                                   # squeeze no further than 80%, then scale evenly
        sy = sx / 0.8; sx = sx
    img = img.resize((max(1, int(tw * sx)), max(1, int(round(th * sy)))), Image.LANCZOS)
    out = np.zeros((h, w))
    y = max(0, (h - img.height) // 2)
    out[y:y + img.height, :img.width] = np.asarray(img)[:h - y, :w] / 255.0
    return out


def fit(text, cap, w, h, align="center", lead=None, baseline=False, face=None):
    """(h, w) coverage of `text` (lines split on \\n), at cap height `cap` or smaller: shrunk evenly to fit the
    height, squeezed to 80% width, then shrunk evenly again. Lines are aligned left or centred. `lead`: line
    pitch in cap heights (tight, for multi-line boxes); without it each line gets the font's full height + a gap."""
    font = ImageFont.truetype(face or FONT, int(round(cap * SS / CAP)))
    lines = text.split("\n")
    gap = int(cap * SS * 0.35)
    imgs = []
    for ln in lines:
        l, t, r, b = font.getbbox(ln)
        im = Image.new("L", (r - l + 8, int(cap * SS / CAP * 1.25) + 8))
        ImageDraw.Draw(im).text((4 - l, 4), ln, 255, font=font)
        bb = im.getbbox() or (0, 0, 1, 1)
        imgs.append(im.crop((bb[0], 0, bb[2], im.height)))
    tw = max(i.width for i in imgs)
    pitch = int(round(lead * cap * SS)) if lead else None
    if pitch:
        stack = np.zeros((pitch * (len(imgs) - 1) + imgs[0].height, tw), np.uint8)
        for k, i in enumerate(imgs):
            x = (tw - i.width) // 2 if align == "center" else 0
            s = stack[k * pitch:k * pitch + i.height, x:x + i.width]
            np.maximum(s, np.asarray(i)[:s.shape[0]], out=s)          # lines may touch: keep both
        body = Image.fromarray(stack)
    else:
        body = Image.new("L", (tw, sum(i.height for i in imgs) + gap * (len(imgs) - 1)))
    y = 0
    for i in ([] if pitch else imgs):
        body.paste(i, ((tw - i.width) // 2 if align == "center" else 0, y)); y += i.height + gap
    bb = body.getbbox() or (0, 0, 1, 1)
    if baseline:                                   # every word on one baseline: crop to the font's own extent
        _, t, _, b = font.getbbox("Hdgjy")
        bb = (bb[0], 4 + t, bb[2], min(body.height, 4 + b))
    body = body.crop(bb)
    bw, bh = body.width / SS, body.height / SS
    k = min(1.0, h / bh)
    sx = min(1.0, w / (bw * k))
    if sx < 0.8:
        k *= sx / 0.8; sx = 0.8
    body = body.resize((max(1, int(bw * k * sx)), max(1, int(round(bh * k)))), Image.LANCZOS)
    out = np.zeros((h, w))
    x = (w - body.width) // 2 if align == "center" else 0
    y = max(0, (h - body.height) // 2)
    out[y:y + body.height, x:x + body.width] = np.asarray(body)[:h - y, :w - x] / 255.0
    return out


def boxtext(a, box, text, st):
    """Redraw one label inside box (x0, y0, x1, y1): its own text pixels (everything that is not the box's
    background, or st["text"] if given) go back to the background, then `text` is drawn fitted to the box.
    Fill: st["fill"] (an index), or the original glyphs' own colour row by row ("template": keeps gradients and
    dithers). st["outline"]: an index drawn as a 1-pixel ring. st["ramp"]: antialiasing indices, strong -> faint.
    st["bg"] = "rows" (needs st["text"]): a background with a checker dither or straight lines; each cleared pixel
    takes its own row's most common non-text value at its checker parity."""
    if st.get("clear"):                            # clear the whole record's text, draw in `box`
        cx0, cy0, cx1, cy1 = st["clear"]
        region = a[cy0:cy1, cx0:cx1]
        region[~np.isin(region, list(st["keep"]))] = st["bg"]
    x0, y0, x1, y1 = box
    sub = a[y0:y1, x0:x1]
    orig = sub.copy()
    vals = [v for v in orig.ravel().tolist()]
    bg = st.get("bg")
    if bg is None:
        bg = max(set(vals), key=vals.count)
    if st.get("keep"):
        textmask = ~np.isin(orig, list(st["keep"]))
    else:
        textmask = np.isin(orig, list(st["text"])) if st.get("text") else (orig != bg)
    edge = st.get("outline")
    rings = st.get("rings") or ([(edge, 1)] if edge is not None else [])   # inner -> outer: (index, width)
    ringset = {i for i, _ in rings}
    tpl = {}
    if st.get("fill") == "template":
        H, W = orig.shape
        for y in range(H):
            for par in (0, 1):
                v = [int(orig[y, x]) for x in range(W) if textmask[y, x] and (x + y) % 2 == par and orig[y, x] not in ringset]
                if v:
                    tpl[(y, par)] = max(set(v), key=v.count)
    if bg == "rows":
        H, W = orig.shape
        near = textmask.copy()                     # sample the background away from the glyphs and their outline
        for _ in range(2):
            n = near.copy()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    n |= np.roll(np.roll(near, dy, 0), dx, 1)
            near = n
        for p in st.get("avoid", ()):              # protected art (a plate) is not background: don't sample it
            near[max(0, p[1] - y0):max(0, p[3] - y0), max(0, p[0] - x0):max(0, p[2] - x0)] = True
        rowbg = orig.copy()
        par_all = (np.arange(W)[None, :] + np.arange(H)[:, None]) % 2
        glob = {}                                  # the box-wide dither, for rows the glyphs almost fill
        for par in (0, 1):
            v = orig[(par_all == par) & ~near].tolist()
            if v:
                glob[par] = max(set(v), key=v.count)
        for y in range(H):
            for par in (0, 1):
                v = [int(orig[y, x]) for x in range(W) if (x + y) % 2 == par and not near[y, x]]
                pick = max(set(v), key=v.count) if len(v) >= 6 else glob.get(par)
                if pick is not None:
                    rowbg[y, (np.arange(W) + y) % 2 == par] = pick
        if st.get("dither"):
            textmask |= orig != rowbg              # the glyphs' solid outline breaks the dither: text too
        sub[textmask] = rowbg[textmask]
        free = np.ones(sub.shape, bool)
    else:
        sub[textmask] = bg
        free = None
    if text == "":                                 # clear only: the English keeps just the Latin line already there
        return
    pad = sum(w for _, w in rings)
    mx, my = st.get("margin", (0, 0))              # cleared across the whole box, drawn inside the margin
    cov = fit(text, st["cap"], sub.shape[1] - 2 * (pad + mx), sub.shape[0] - 2 * (pad + my),
              st.get("align", "center"), st.get("lead"), st.get("baseline", False), st.get("face"))
    cov = np.pad(cov, ((my, my), (mx, mx)))
    m = np.zeros(sub.shape, bool)
    m[pad:pad + cov.shape[0], pad:pad + cov.shape[1]] = cov >= 0.5
    grown, layers = m, []
    for idx, w in rings:
        for _ in range(w):
            g = grown.copy()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    g |= np.roll(np.roll(grown, dy, 0), dx, 1)
            grown = g
        layers.append((idx, grown))
    for idx, g in reversed(layers):                # outermost first, inner rings drawn over it
        sub[g & ~m] = idx
        if free is not None:
            free &= ~(g & ~m)
    if st.get("fill") == "template":
        rows = sorted({y for y, _ in tpl}) or [0]
        for y, x in zip(*np.nonzero(m)):
            par = (x + y) % 2
            v = tpl.get((y, par), tpl.get((y, 1 - par)))
            if v is None:
                near = min(rows, key=lambda r: abs(r - y))
                v = tpl.get((near, par), tpl.get((near, 1 - par), bg))
            sub[y, x] = v
    else:
        ramp = st.get("ramp") or [st["fill"]]
        if ramp == "auto":                         # the label's own antialiasing: its main colour, then the shades
            tv = orig[textmask].tolist()           # that sit next to it, closest first
            core = max(set(tv), key=tv.count)
            score = {}
            H, W = orig.shape
            for y, x in zip(*np.nonzero(textmask)):
                v = int(orig[y, x])
                if v == core:
                    continue
                nb = [int(orig[yy, xx]) for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1))
                      if 0 <= yy < H and 0 <= xx < W]
                sc = score.setdefault(v, [0, 0]); sc[0] += sum(q == core for q in nb); sc[1] += len(nb)
            ramp = [core] + sorted(score, key=lambda v: -score[v][0] / score[v][1])[:3]
        full = np.zeros(sub.shape)
        full[pad:pad + cov.shape[0], pad:pad + cov.shape[1]] = cov
        for lo, idx in zip((0.5, 0.35, 0.22, 0.12), ramp):
            if free is None:
                sub[(full >= lo) & (sub == bg)] = idx
            else:
                sub[(full >= lo) & free] = idx; free &= ~(full >= lo)


def paint(a, cfg):
    if "board" in cfg:
        return board(a, cfg)
    a = a.copy()
    if "boxes" in cfg:
        orig = a.copy()
        for entry in cfg["boxes"]:
            box, text = entry[0], entry[1]
            if text is not None:
                st = entry[2] if len(entry) > 2 else cfg["style"]
                boxtext(a, box, text, dict(st, avoid=cfg.get("protect", ())))
        for p in cfg.get("protect", ()):           # art that must survive the clear (gap decorations)
            x0, y0, x1, y1 = p[:4]
            if len(p) > 4:                         # art under the label (a plate): back wherever the English is not
                keep = np.isin(orig[y0:y1, x0:x1], list(p[4])) & np.isin(a[y0:y1, x0:x1], [0, 1])
                a[y0:y1, x0:x1][keep] = orig[y0:y1, x0:x1][keep]
            else:
                a[y0:y1, x0:x1] = orig[y0:y1, x0:x1]
        return a
    st = cfg["style"]
    shadow = st["shadow"]
    for (row, col), text in cfg["labels"].items():
        if text is None:
            continue                               # gap: original Japanese stays
        y0, y1 = row * cfg["band"], (row + 1) * cfg["band"]
        cx0, cx1 = cfg["cols"][col]
        box = a[y0:y1, cx0:cx1]
        on = np.nonzero((box != 0).any(0))[0]
        if not len(on):
            raise SystemExit("empty label box at %s" % ((row, col),))
        bx0, bx1 = on.min(), on.max() + 1            # the Japanese label's own extent: English stays inside
        if st.get("kind") == "gradient":
            gradient(box, text, bx0, bx1, st)
            continue
        if st.get("kind") == "subtitle":
            subtitle(box, text, st)
            continue
        box[:] = 0
        words = text if isinstance(text, tuple) else (text,)
        step = (bx1 - bx0) / len(words)              # a tuple: one equal box per Japanese character
        for j, word in enumerate(words):
            x0, x1 = bx0 + int(round(j * step)), bx0 + int(round((j + 1) * step))
            draw(box, word, x0, x1, cfg["band"], st)
    return a


def board(a, cfg):
    """Route board (OBJsou?b??, 352x144): each vertical station column becomes Zoinkity's name for that station
    (EKI), turned 90 degrees to read top to bottom, in the column's own ink and antialiasing shades (bold black for
    the ends, grey for the stops between). The line, dots, frame and the blue ATC / BONUS ROUND stay."""
    a = a.copy()
    names = [EKI[i - 1] for i in cfg["board"]]
    reg = a[25:135, 9:344]                         # below the line, inside the frame
    orig = reg.copy()
    m = np.isin(orig, [1, 2, 3, 4, 5, 6])
    segs = []
    for x in np.nonzero(m.any(0))[0]:
        if segs and x - segs[-1][1] <= 3:
            segs[-1][1] = x
        else:
            segs.append([x, x])
    if len(segs) != len(names):
        raise SystemExit("board: %d columns, %d names" % (len(segs), len(names)))
    centres = [(s0 + s1) / 2 for s0, s1 in segs]
    H = reg.shape[0]
    for k, ((s0, s1), name) in enumerate(zip(segs, names)):
        cm = np.zeros(m.shape, bool); cm[:, s0:s1 + 1] = m[:, s0:s1 + 1]
        tv = orig[cm].tolist()
        core = max(set(tv), key=tv.count)
        score = {}
        for y, x in zip(*np.nonzero(cm)):
            v = int(orig[y, x])
            if v != core:
                nb = [int(orig[yy, xx]) for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1))
                      if 0 <= yy < H and 0 <= xx < orig.shape[1]]
                sc = score.setdefault(v, [0, 0]); sc[0] += sum(q == core for q in nb); sc[1] += len(nb)
        ramp = [core] + sorted(score, key=lambda v: -score[v][0] / score[v][1])[:3]
        reg[cm] = 7
        gap = min([abs(centres[k] - c) for j, c in enumerate(centres) if j != k] or [64])
        half = int(min(12, gap / 2 - 1))
        L = H - 4
        rot = np.rot90(fit(name, 16, L, 2 * half, "left"), -1)      # (L, 2*half): top of the name at the top
        cx = int(round(centres[k]))
        sub = reg[2:2 + L, cx - half:cx + half]
        for lo, idx in zip((0.5, 0.35, 0.22, 0.12), ramp):
            sub[(rot[:sub.shape[0], :sub.shape[1]] >= lo) & (sub == 7)] = idx
    return a

def gradient(box, text, x0, x1, st):
    """Pixel-art label: take each row's dither pattern (index by x parity) from the original glyphs, then redraw
    the English with that fill inside a 1-pixel edge of the outline index."""
    orig = box.copy()
    edge = st["outline"]
    H = box.shape[0]
    tpl = {}
    for y in range(H):
        for par in (0, 1):
            v = [int(orig[y, x]) for x in range(x0, x1) if (x + y) % 2 == par and orig[y, x] not in (0, edge)]
            if v:
                tpl[(y, par)] = max(set(v), key=v.count)
    rows = sorted({y for y, _ in tpl})
    def pick(y, par):
        if (y, par) in tpl:
            return tpl[(y, par)]
        if (y, 1 - par) in tpl:
            return tpl[(y, 1 - par)]
        near = min(rows, key=lambda r: abs(r - y))
        return tpl.get((near, par), tpl.get((near, 1 - par)))
    box[:] = 0
    cov = coverage(text, st["cap"], x1 - x0 - 2, H - 2)
    m = np.zeros(box.shape, bool)
    h, w = cov.shape
    m[1:1 + h, x0 + 1:x0 + 1 + w] = cov >= 0.5
    grown = m.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            grown |= np.roll(np.roll(m, dy, 0), dx, 1)
    box[grown & ~m] = edge
    ys, xs = np.nonzero(m)
    for y, x in zip(ys, xs):
        box[y, x] = pick(y, (x + y) % 2)


def subtitle(box, text, st):
    """Keep the Japanese label, shrunk (aspect ratio kept) to the top-left of its box, and write `text` small
    underneath: the shrunk art keeps its own indices (nearest-neighbour); the subtitle takes the label's own
    dithered gradient (squeezed to its height) inside a 1-pixel edge of the outline index; `light` (the brightest
    fill, set in main) is only the fallback for a row with no gradient sample."""
    orig = box.copy()
    edge = st["outline"]
    ys, xs = np.nonzero(orig)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    art = orig[y0:y1, x0:x1]
    h, w = max(1, int(round(art.shape[0] * st["scale"]))), max(1, int(round(art.shape[1] * st["scale"])))
    yi = (np.arange(h) * art.shape[0] / h).astype(int)
    xi = (np.arange(w) * art.shape[1] / w).astype(int)
    small = art[yi][:, xi]
    light = st["light"]
    box[:] = 0
    box[y0 - 3:y0 - 3 + h, x0:x0 + w] = small
    sy = y0 - 3 + h + 2
    cov = coverage(text, st["cap"], box.shape[1] - x0 - 2, box.shape[0] - sy - 1)
    m = np.zeros(box.shape, bool)
    ch, cw = cov.shape
    m[sy:sy + ch, x0 + 1:x0 + 1 + cw] = cov >= 0.5
    grown = m.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            grown |= np.roll(np.roll(m, dy, 0), dx, 1)
    box[grown & ~m & (box == 0)] = edge
    # the kanji's own gradient: each subtitle row takes the dither pair of the proportional original row
    grad = {}
    for y in range(y0, y1):
        for par in (0, 1):
            v = [int(orig[y, x]) for x in range(x0, x1) if (x + y) % 2 == par and orig[y, x] not in (0, edge)]
            if v:
                grad[(y, par)] = max(set(v), key=v.count)
    my, mx = np.nonzero(m)
    top, bot = my.min(), my.max() + 1
    for y, x in zip(my, mx):
        oy = y0 + int((y - top) * (y1 - y0) / max(1, bot - top))
        par = (x + y) % 2
        box[y, x] = grad.get((oy, par), grad.get((oy, 1 - par), light))


def draw(box, text, x0, x1, band, st):
    """Draw `text` left-aligned at x0 in box columns [x0, x1), with the style's shadow and ramp."""
    shadow = st["shadow"]
    room = x1 - x0 - (shadow[1] if shadow else 0)
    cov = coverage(text, st["cap"], room, band - (shadow[2] if shadow else 0))
    h, w = cov.shape
    sub = box[:, x0:x0 + w + (shadow[1] if shadow else 0)]
    if shadow:
        idx, dx, dy = shadow
        sub[dy:dy + h, dx:dx + w][cov >= 0.5] = idx
    for lo, idx in zip((0.8, 0.55, 0.3, 0.1), st["ramp"]):
        part = sub[:h, :w]
        part[(cov >= lo) & ((part == 0) | (part == (shadow[0] if shadow else -1)))] = idx


MAX_BLANK = 261        # largest blank tile blank_tile makes; Taito's largest tile is 278 bytes


def blank_tile(size):
    """A type-1 tile of exactly `size` bytes (5..261) that decodes to 256 transparent pixels: literal runs of
    zeros (no more than 84, Taito's longest) plus 2-byte runs, split finer to add bytes."""
    body = size - 1
    for m in range(0, 257):
        lit = m + (-(-m // 84) if m else 0)
        r = 256 - m
        for rc in range(-(-r // 128) if r else 0, r + 1):
            if lit + 2 * rc == body:
                out = bytearray()
                left = m
                while left:
                    k = min(84, left); out += bytes([0x80 | (k - 1)]) + bytes(k); left -= k
                parts = [r // rc + (1 if i < r % rc else 0) for i in range(rc)] if rc else []
                for k in parts:
                    out += bytes([k - 1, 0])
                assert A.cg2_decode(1, bytes(out)) == [0] * 256 and len(out) == body
                return (1, bytes(out))
    return None                                    # not every size can be made (e.g. 6)


BLANK_SIZES = None


def _reencode(tile):
    kind, body = tile
    px = A.cg2_decode(kind, body)
    e = A.cg2_encode(px)
    return (e[0], e[1:]) if len(e) < 1 + len(body) and A.cg2_decode(e[0], e[1:]) == px else tile


def reclaim(tiles, need, skip):
    """Recompress other tiles, largest first, until `need` bytes are saved. Their pictures do not change
    (each re-encoding is decoded and compared), only their bytes. The last tile is left alone: it is cut
    short in the original file."""
    from multiprocessing import Pool
    order = sorted((t for t in range(len(tiles) - 1) if t not in skip), key=lambda t: -len(tiles[t][1]))
    saved, pos = 0, 0
    with Pool() as pool:
        while saved < need and pos < len(order):
            batch = order[pos:pos + 256]; pos += 256
            for t, e in zip(batch, pool.map(_reencode, [tiles[t] for t in batch])):
                saved += len(tiles[t][1]) - len(e[1]); tiles[t] = e
    print("recompressed %d other tiles, %d bytes reclaimed" % (pos, saved))


def main(lst_p, tbl_p, cg2_p, pal_p, out_tbl, out_cg2, preview=None):
    names = {a: o for a, o, s in A.lst(open(lst_p, encoding="latin-1").read())}
    tbl = bytearray(open(tbl_p, "rb").read())
    cg2 = open(cg2_p, "rb").read()
    tiles = A.cg2_tiles(cg2)
    sp = A.Sprites(lst_p, tbl_p, None, cg2_p, pal_p)

    users = {}
    for n in names:
        if sp.flagged(n):
            for t in sp.tilemap(n)[2]:
                users.setdefault(t, set()).add(n)
    freeable = sorted(t for t, u in users.items() if u <= set(RECORDS))
    existing = {}
    for t, (k, b) in enumerate(tiles):
        existing.setdefault(bytes(A.cg2_decode(k, b)), t)

    for name, cfg in RECORDS.items():             # subtitle colour: the label's brightest fill, in its palette
        if cfg["style"].get("kind") == "subtitle" and cfg["style"]["light"] is None:
            a = sp.indices(name)
            pal = sp.palette(cfg["style"]["pal"]).astype(int)
            used = [v for v in set(a.ravel().tolist()) if v not in (0, cfg["style"]["outline"])]
            cfg["style"]["light"] = max(used, key=lambda v: pal[v, :3].sum())
    new = {}
    for name, cfg in RECORDS.items():
        new[name] = paint(sp.indices(name), cfg)
        if preview:
            os.makedirs(preview, exist_ok=True)
            pal = sp.palette(cfg["style"]["pal"])
            Image.fromarray(pal[new[name]], "RGBA").save(os.path.join(preview, name + ".png"))

    def cut(a, w, k):
        return bytes(a[(k // w) * 16:(k // w) * 16 + 16, (k % w) * 16:(k % w) * 16 + 16].ravel())

    kept = set()                                   # freeable ids whose picture is still wanted as it is
    for name, a in new.items():
        w, h, _ = sp.tilemap(name)
        for k in range(w * h):
            px = cut(a, w, k)
            if px in existing and existing[px] in freeable:
                kept.add(existing[px])
    pool = [t for t in freeable if t not in kept]
    out_tiles = list(tiles)
    placed, ids_for = {}, {}
    for name, a in new.items():
        w, h, _ = sp.tilemap(name)
        ids = []
        for k in range(w * h):
            px = cut(a, w, k)
            if px not in placed:
                if px in existing:
                    placed[px] = existing[px]
                else:
                    if not pool:
                        raise SystemExit("out of tile ids")
                    t = pool.pop(0); placed[px] = t
                    e = A.cg2_encode(px)
                    out_tiles[t] = (e[0], e[1:])
            ids.append(placed[px])
        ids_for[name] = ids
    for t in pool:                                 # freed and unused: smallest valid tile
        out_tiles[t] = (1, bytes([0x7F, 0, 0x7F, 0]))

    over = len(A.cg2_build(out_tiles)) - len(cg2)
    if over > 0:
        reclaim(out_tiles, over, set(t for ids in ids_for.values() for t in ids))
    data = A.cg2_build(out_tiles)
    if len(data) > len(cg2):
        raise SystemExit("CG2.ROM would grow by %d bytes" % (len(data) - len(cg2)))
    spare = len(cg2) - len(data)
    # The file must keep its size, but padding at the end would make the last tile tens of KB long: the game
    # sizes a tile by the gap to the next one, and a 67 KB last tile broke it in game (2026-09-30). So the spare
    # bytes go into the freed, unreferenced slots as longer (still valid, 256-pixel) blank tiles, none over
    # Taito's own largest tile.
    extras = [n - 5 for n in range(5, MAX_BLANK + 1) if blank_tile(n)]      # reachable extra bytes per slot
    need = spare
    for t in pool:
        if need <= 0:
            break
        e = max(x for x in extras if x <= need and (need - x == 0 or need - x in extras or need - x > extras[-1]))
        out_tiles[t] = blank_tile(5 + e)
        need -= e
    if need > 0:
        raise SystemExit("%d spare bytes and no freed slot left to hold them" % need)
    data = A.cg2_build(out_tiles)
    assert len(data) == len(cg2)
    for name, ids in ids_for.items():
        struct.pack_into("<%dH" % len(ids), tbl, names[name] + 2, *ids)
    open(out_tbl, "wb").write(tbl); open(out_cg2, "wb").write(data)
    print("%d tiles freed, %d kept, %d new, %d ids spare; CG2.ROM %d bytes to spare" % (
        len(freeable), len(kept), len(freeable) - len(kept) - len(pool), len(pool), spare))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--all"]
    if len(args) not in (6, 7):
        sys.exit(__doc__)
    if "--all" not in sys.argv:
        RECORDS = {k: v for k, v in RECORDS.items() if STABLE.match(k)}
    main(*args)
