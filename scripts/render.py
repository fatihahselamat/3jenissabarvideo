import json, math, random, subprocess, sys, wave, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import imageio_ffmpeg

SRC, TRANS, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
WORK = os.path.dirname(os.path.abspath(OUT))
PREVIEW = [float(x) for x in sys.argv[4].split(",")] if len(sys.argv) > 4 else None
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
W, H, FPS, DUR = 1080, 1920, 30, 30.0

# ---------------- transcript cleanup ----------------
segs = json.load(open(TRANS))
FIX = {"terbagi": "terbahagi", "istikomah": "istiqamah", "redor": "reda"}
for s in segs:
    ws = []
    for w in s["words"]:
        txt = w["w"].strip()
        if txt == "menjauhimang":
            ws.append({"w": "menjauhi", "s": w["s"], "e": 17.75})
            ws.append({"w": "maksiat.", "s": 17.75, "e": 18.38})
            continue
        if txt == "siat.":
            continue
        if txt.startswith("-Asr") and ws and ws[-1]["w"] == "Al":
            ws[-1] = {"w": "Al-'Asr" + txt[4:], "s": ws[-1]["s"], "e": w["e"]}
            continue
        for a, b in FIX.items():
            txt = txt.replace(a, b)
        ws.append({"w": txt, "s": w["s"], "e": w["e"]})
    s["words"] = ws

# ---------------- audio: compress pauses, then speed up ----------------
with wave.open(SRC) as wf:
    SR = wf.getframerate()
    pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32)

allw = [w for s in segs for w in s["words"]]
chunks = []
for w in allw:
    if chunks and w["s"] - chunks[-1][1] < 0.22:
        chunks[-1][1] = w["e"]
    else:
        chunks.append([w["s"], w["e"]])
chunks = [[max(0, a - 0.04), min(len(pcm) / SR, b + 0.07)] for a, b in chunks]
GAP = 0.1
pieces, cmap, pos = [], [], 0.0
fade = int(0.01 * SR)
for a, b in chunks:
    seg = pcm[int(a * SR):int(b * SR)].copy()
    seg[:fade] *= np.linspace(0, 1, fade); seg[-fade:] *= np.linspace(1, 0, fade)
    pieces += [seg, np.zeros(int(GAP * SR), np.float32)]
    cmap.append((a, b, pos))
    pos += (b - a) + GAP
comp = np.concatenate(pieces)
TEMPO = max(1.0, (len(comp) / SR) / 29.3)
comp_path = os.path.join(WORK, "compressed.wav")
with wave.open(comp_path, "wb") as wf:
    wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SR)
    wf.writeframes(np.clip(comp, -32768, 32767).astype(np.int16).tobytes())

def remap(t):
    for a, b, p in cmap:
        if a - 1e-6 <= t <= b + 1e-6:
            return (p + t - a) / TEMPO
    best = min(cmap, key=lambda c: abs(c[0] - t))
    return best[2] / TEMPO

for s in segs:
    for w in s["words"]:
        w["s"], w["e"] = remap(w["s"]), remap(w["e"])
    s["s"], s["e"] = s["words"][0]["s"], s["words"][-1]["e"]
print(f"compressed {len(comp)/SR:.2f}s, tempo {TEMPO:.3f}, speech ends {segs[-1]['e']:.2f}s")

def WT(si, wi):
    return segs[si]["words"][wi]["s"]

# ---------------- design ----------------
GOLD = (242, 193, 78); CREAM = (255, 248, 231); DARK = (22, 20, 18)
FONT = "/System/Library/Fonts/Avenir Next.ttc"
FI = {"bold": 0, "demi": 2, "italic": 4, "medium": 5, "regular": 7, "heavy": 8, "demiit": 3}
_fc = {}
def font(size, wt="bold"):
    k = (size, wt)
    if k not in _fc:
        _fc[k] = ImageFont.truetype(FONT, size, index=FI[wt])
    return _fc[k]

def ease_out(x): x = min(max(x, 0), 1); return 1 - (1 - x) ** 3
def ease_back(x):
    x = min(max(x, 0), 1); c1 = 1.70158; c3 = c1 + 1
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2
def ease_io(x): x = min(max(x, 0), 1); return x * x * (3 - 2 * x)

def text_el(txt, size, wt="bold", color=CREAM, glow=None, track=0, shadow=True):
    f = font(size, wt)
    if track:
        widths = [f.getlength(c) for c in txt]
        tw = int(sum(widths) + track * (len(txt) - 1))
    else:
        tw = int(f.getlength(txt))
    asc, desc = f.getmetrics()
    pad = 60
    im = Image.new("RGBA", (tw + pad * 2, asc + desc + pad * 2), (0, 0, 0, 0))
    def draw_on(d, fill):
        if track:
            x = pad
            for c, cw in zip(txt, widths):
                d.text((x, pad), c, font=f, fill=fill); x += cw + track
        else:
            d.text((pad, pad), txt, font=f, fill=fill)
    if glow or shadow:
        g = Image.new("RGBA", im.size, (0, 0, 0, 0))
        draw_on(ImageDraw.Draw(g), (glow + (200,)) if glow else (0, 0, 0, 150))
        g = g.filter(ImageFilter.GaussianBlur(size * (0.16 if glow else 0.06)))
        if not glow:
            g = Image.alpha_composite(Image.new("RGBA", im.size, (0, 0, 0, 0)), g)
            g2 = Image.new("RGBA", im.size, (0, 0, 0, 0)); g2.paste(g, (0, 8)); g = g2
        im = Image.alpha_composite(im, g)
    draw_on(ImageDraw.Draw(im), color + (255,))
    return im

def pill_el(txt, size, fg=DARK, bg=GOLD, wt="heavy", padx=34, pady=14, track=4, outline=False):
    f = font(size, wt)
    widths = [f.getlength(c) for c in txt]
    tw = int(sum(widths) + track * (len(txt) - 1))
    asc, desc = f.getmetrics()
    th = asc + int(desc * 0.4)
    im = Image.new("RGBA", (tw + padx * 2, th + pady * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if outline:
        d.rounded_rectangle([1, 1, im.width - 2, im.height - 2], radius=im.height // 2, outline=bg + (255,), width=3)
    else:
        d.rounded_rectangle([0, 0, im.width - 1, im.height - 1], radius=im.height // 2, fill=bg + (255,))
    x = padx
    for c, cw in zip(txt, widths):
        d.text((x, pady - int(asc * 0.08)), c, font=f, fill=fg + (255,)); x += cw + track
    return im

def badge_el(num, r=105):
    s = r * 2 + 80
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    g = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(g).ellipse([40, 40, s - 40, s - 40], fill=GOLD + (170,))
    im = Image.alpha_composite(im, g.filter(ImageFilter.GaussianBlur(22)))
    d = ImageDraw.Draw(im)
    d.ellipse([40, 40, s - 40, s - 40], fill=GOLD + (255,))
    d.ellipse([56, 56, s - 56, s - 56], outline=DARK + (90,), width=3)
    f = font(110, "heavy")
    tw = f.getlength(num); asc, desc = f.getmetrics()
    d.text(((s - tw) / 2, (s - asc - desc) / 2 + 4), num, font=f, fill=DARK + (255,))
    return im

def card_el(lines, hl, width=900):
    f = font(54, "demi")
    lh = 78
    h = 70 + lh * len(lines) + 20
    im = Image.new("RGBA", (width + 40, h + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([20, 20, width + 20, h + 20], radius=36, fill=(255, 255, 255, 30), outline=GOLD + (150,), width=3)
    d.rounded_rectangle([20, 20, 34, h + 20], radius=7, fill=GOLD + (255,))
    y = 20 + 45
    for ln in lines:
        words = ln.split(" ")
        total = sum(f.getlength(w) for w in words) + (f.getlength(" ") + 14) * (len(words) - 1)
        x = 20 + (width - total) / 2 + 8
        for w in words:
            ww = f.getlength(w)
            key = w.strip(",.&").lower() in hl
            if key:
                d.rounded_rectangle([x - 12, y - 4, x + ww + 12, y + 66], radius=14, fill=GOLD + (255,))
                d.text((x, y), w, font=f, fill=DARK + (255,))
            else:
                d.text((x, y), w, font=f, fill=CREAM + (255,))
            x += ww + f.getlength(" ") + 14
        y += lh
    return im

def steps_el(cur):
    im = Image.new("RGBA", (420, 60), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for i in range(3):
        x = 20 + i * 135
        if i + 1 == cur:
            d.rounded_rectangle([x, 22, x + 110, 38], radius=8, fill=GOLD + (255,))
        elif i + 1 < cur:
            d.rounded_rectangle([x, 22, x + 110, 38], radius=8, fill=GOLD + (120,))
        else:
            d.rounded_rectangle([x, 22, x + 110, 38], radius=8, fill=(255, 255, 255, 50))
    return im

def key_el():
    s = 300
    im = Image.new("RGBA", (s + 80, s + 80), (0, 0, 0, 0))
    def draw(d, fill):
        cx, cy = 150, 190
        d.ellipse([cx - 80, cy - 80, cx + 80, cy + 80], outline=fill, width=34)
        d.rounded_rectangle([cx + 70, cy - 17, cx + 300, cy + 17], radius=8, fill=fill)
        d.rectangle([cx + 230, cy + 10, cx + 262, cy + 70], fill=fill)
        d.rectangle([cx + 180, cy + 10, cx + 208, cy + 52], fill=fill)
    im = Image.new("RGBA", (420, 380), (0, 0, 0, 0))
    g = Image.new("RGBA", im.size, (0, 0, 0, 0)); draw(ImageDraw.Draw(g), GOLD + (200,))
    im = Image.alpha_composite(im, g.filter(ImageFilter.GaussianBlur(18)))
    draw(ImageDraw.Draw(im), GOLD + (255,))
    return im

# ---------------- scenes ----------------
scene_segs = [[0], [1], [2, 3], [4, 5], [6, 7], [8], [9]]
S = [0.0] + [segs[g[0]]["s"] - 0.22 for g in scene_segs[1:]] + [DUR]
BGS = [((10, 34, 46), (3, 10, 18)), ((6, 52, 42), (2, 16, 16)), ((8, 62, 58), (2, 20, 24)),
       ((30, 30, 82), (8, 8, 30)), ((76, 22, 40), (22, 5, 14)), ((6, 52, 42), (2, 16, 16)),
       ((16, 26, 48), (3, 5, 12))]

# element: (image, cx, cy, t_in, anim)
scenes = [[] for _ in scene_segs]
def add(si, im, cy, t_in, anim="up", cx=W // 2):
    scenes[si].append((im, cx, cy, t_in, anim))

# 0 hook
add(0, pill_el("SURAH AL-'ASR", 40, track=6), 400, 0.15)
add(0, text_el("Pernahkah kita", 86, "demi"), 600, WT(0, 0))
add(0, text_el("terfikir...", 86, "demi"), 710, WT(0, 2))
add(0, text_el("mengapa Allah menekankan", 62, "medium", color=(220, 230, 225)), 850, WT(0, 3))
add(0, text_el("SABAR", 250, "heavy", GOLD, glow=GOLD), 1040, WT(0, 7), "pop")
add(0, text_el("dalam Surah Al-'Asr?", 72, "demi"), 1230, WT(0, 9))
# 1 three types
add(1, text_el("3", 560, "heavy", GOLD, glow=GOLD), 760, segs[1]["s"] - 0.1, "zoom")
add(1, text_el("JENIS SABAR", 128, "heavy", track=6), 1140, WT(1, 0), "up")
add(1, text_el("yang perlu kita tahu", 58, "medium", color=(210, 225, 220)), 1270, WT(1, 3))
# 2-4 types
TYPES = [
    ("01", "PERTAMA", "Sabar dalam", "KETAATAN", ["Tetap istiqamah beribadah", "walaupun terasa berat"], {"istiqamah", "beribadah"}, 2),
    ("02", "KEDUA", "Sabar menjauhi", "MAKSIAT", ["Menahan diri daripada perkara", "yang dilarang Allah"], {"menahan", "diri", "dilarang"}, 4),
    ("03", "KETIGA", "Sabar menghadapi", "UJIAN", ["Tetap reda & tidak berputus asa", "ketika ditimpa kesusahan"], {"reda", "berputus", "asa"}, 6),
]
for k, (num, lab, l1, l2, card, hl, sg) in enumerate(TYPES):
    si = 2 + k
    add(si, badge_el(num), 400, segs[sg]["s"] - 0.05, "pop")
    add(si, text_el(lab, 46, "bold", GOLD, track=14, shadow=False), 585, segs[sg]["s"] + 0.1)
    add(si, text_el(l1, 84, "demi"), 700, WT(sg, 1))
    add(si, text_el(l2, 150, "heavy", GOLD, glow=GOLD), 840, segs[sg]["words"][-1]["s"] - 0.05, "pop")
    add(si, card_el(card, hl), 1120, segs[sg + 1]["s"] - 0.05, "left")
    add(si, steps_el(k + 1), 1325, segs[sg]["s"] + 0.2)
# 5 ingatlah
add(5, pill_el("INGATLAH", 44, track=8), 380, segs[8]["s"])
add(5, text_el("Surah Al-'Asr · Ayat 3", 66, "demi"), 540, WT(8, 1))
add(5, text_el("“...wa tawāsau bis-sabr”", 70, "demiit", GOLD, shadow=False), 670, WT(8, 4))
add(5, text_el("saling berpesan dengan", 76, "demi"), 860, WT(8, 8))
add(5, text_el("KESABARAN", 136, "heavy", GOLD, glow=GOLD), 1010, WT(8, 11) - 0.05, "pop")
# 6 ending
add(6, key_el(), 470, segs[9]["s"] - 0.1, "zoom")
add(6, text_el("SABAR", 190, "heavy", GOLD, glow=GOLD), 740, WT(9, 1), "pop")
add(6, text_el("adalah kunci menuju", 64, "medium"), 890, WT(9, 2))
add(6, text_el("KEJAYAAN", 150, "heavy", CREAM, glow=GOLD), 1030, WT(9, 5), "pop")
add(6, pill_el("DUNIA & AKHIRAT", 52, track=6), 1190, WT(9, 6), "up")

# ---------------- background ----------------
def grad(top, bot):
    a = np.linspace(0, 1, H)[:, None, None]
    arr = (np.array(top)[None, None] * (1 - a) + np.array(bot)[None, None] * a)
    yy, xx = np.mgrid[0:H, 0:W]
    glow = np.exp(-(((xx - W / 2) / 650) ** 2 + ((yy - 820) / 750) ** 2))[..., None]
    arr = arr + glow * 38
    return np.clip(np.repeat(arr, W, axis=1) if arr.shape[1] == 1 else arr, 0, 255).astype(np.uint8)
BG = [Image.fromarray(grad(t, b)).convert("RGB") for t, b in BGS]

PW, PH = W + 400, H + 400
pattern = Image.new("RGBA", (PW, PH), (0, 0, 0, 0))
pd = ImageDraw.Draw(pattern)
sp = 200
for gy in range(0, PH + sp, sp):
    for gx in range(0, PW + sp, sp):
        cx, cy = gx + (sp // 2 if (gy // sp) % 2 else 0), gy
        for rot in (0, 45):
            pts = [(cx + 62 * math.cos(math.radians(rot + 45 + 90 * i)), cy + 62 * math.sin(math.radians(rot + 45 + 90 * i))) for i in range(4)]
            pd.polygon(pts, outline=GOLD + (22,))
        pd.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], outline=GOLD + (18,))

yy, xx = np.mgrid[0:H, 0:W]
vig = np.clip(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H / 2) / (H * 0.62)) ** 2, 0, 1)
vignette = Image.fromarray(np.dstack([np.zeros((H, W, 3), np.uint8), (vig ** 1.6 * 190).astype(np.uint8)]))

random.seed(7)
parts = [(random.uniform(0, W), random.uniform(0, H), random.uniform(1.5, 5), random.uniform(15, 50), random.uniform(0, 6.28)) for _ in range(55)]

# ---------------- captions ----------------
KEY = {"sabar", "al-'asr", "3", "jenis", "ketaatan", "istiqamah", "maksiat", "dilarang", "ujian", "reda",
       "berputus", "asa", "kesabaran", "kunci", "kejayaan", "dunia", "akhirat", "allah"}
CF = font(58, "demi")
SPC = CF.getlength(" ") + 18
def norm(w): return w.strip(",.?!").lower()
cap_layout = []
for s in segs:
    lines, cur, cw = [], [], 0
    for w in s["words"]:
        ww = CF.getlength(w["w"])
        if cur and cw + ww > 900:
            lines.append(cur); cur, cw = [], 0
        cur.append((w, ww)); cw += ww + SPC
    lines.append(cur)
    items = []
    y0 = 1560 - (len(lines) * 88) / 2
    for li, ln in enumerate(lines):
        tot = sum(ww for _, ww in ln) + SPC * (len(ln) - 1)
        x = (W - tot) / 2
        for w, ww in ln:
            items.append((w, x, y0 + li * 88, ww)); x += ww + SPC
    cap_layout.append((items, len(lines)))

def draw_caption(frame, t):
    for i, s in enumerate(segs):
        end = segs[i + 1]["s"] - 0.05 if i + 1 < len(segs) else DUR
        if s["s"] - 0.12 <= t < end:
            items, nl = cap_layout[i]
            a = ease_out((t - s["s"] + 0.12) / 0.2)
            ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(ov)
            ph = nl * 88 + 50
            d.rounded_rectangle([60, 1560 - ph / 2 - 6, W - 60, 1560 + ph / 2 + 6], radius=32, fill=(0, 0, 0, int(105 * a)))
            last = max([w["s"] for w, *_ in items if w["s"] <= t], default=-1)
            for w, x, y, ww in items:
                spoken = t >= w["s"]
                active = w["s"] == last and t < w["e"] + 0.25
                if norm(w["w"]) in KEY and spoken:
                    k = ease_back((t - w["s"]) / 0.18)
                    grow = 10 * k
                    d.rounded_rectangle([x - grow, y - 2 - grow * 0.4, x + ww + grow, y + 72 + grow * 0.4], radius=16, fill=GOLD + (int(255 * a),))
                    d.text((x, y), w["w"], font=CF, fill=DARK + (int(255 * a),))
                elif active:
                    d.text((x, y), w["w"], font=CF, fill=GOLD + (int(255 * a),))
                else:
                    d.text((x, y), w["w"], font=CF, fill=CREAM + (int((255 if spoken else 95) * a),))
            frame.alpha_composite(ov)
            return

# ---------------- frame ----------------
def scene_at(t):
    for i in range(len(S) - 1):
        if S[i] <= t < S[i + 1]:
            return i
    return len(S) - 2

def place(frame, im, cx, cy, alpha, scale=1.0, dx=0, dy=0):
    if alpha <= 0.01: return
    if abs(scale - 1) > 0.005:
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.BICUBIC)
    if alpha < 0.99:
        r, g, b, a = im.split()
        a = a.point(lambda v: int(v * alpha))
        im = Image.merge("RGBA", (r, g, b, a))
    x, y = int(cx - im.width / 2 + dx), int(cy - im.height / 2 + dy)
    frame.alpha_composite(im, (max(0, x), max(0, y)), (max(0, -x), max(0, -y)))

def render(t):
    si = scene_at(t)
    # background crossfade around boundary
    bg = BG[si]
    if si + 1 < len(BG) and t > S[si + 1] - 0.3:
        bg = Image.blend(BG[si], BG[si + 1], ease_io((t - (S[si + 1] - 0.3)) / 0.3))
    elif si > 0 and t < S[si] + 0.25:
        bg = Image.blend(BG[si - 1], BG[si], 0.5 + 0.5 * ease_io((t - S[si]) / 0.25))
    frame = bg.convert("RGBA")
    ox = int(200 + 140 * math.sin(t * 0.25)); oy = int(200 - t * 9) % sp + 100
    frame.alpha_composite(pattern.crop((ox, oy, ox + W, oy + H)))
    # particles
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    for x, y, r, v, ph in parts:
        yy_ = (y - v * t) % H; a = int(90 + 80 * math.sin(t * 2 + ph))
        d.ellipse([x - r, yy_ - r, x + r, yy_ + r], fill=GOLD + (a,))
    frame.alpha_composite(ov)
    frame.alpha_composite(vignette)
    # elements
    end = S[si + 1]
    out = 1 - ease_io((t - (end - 0.22)) / 0.22) if si + 1 < len(S) - 1 else 1
    for im, cx, cy, tin, anim in scenes[si]:
        if t < tin: continue
        p = (t - tin) / 0.45
        a = ease_out(p * 1.6) * out
        dy = -40 * ease_io((t - (end - 0.22)) / 0.22) if out < 1 else 0
        breathe = 1 + 0.012 * math.sin((t - tin) * 3)
        if anim == "pop":
            place(frame, im, cx, cy, a, (0.6 + 0.4 * ease_back(p)) * breathe, 0, dy)
        elif anim == "zoom":
            place(frame, im, cx, cy, a, (1.8 - 0.8 * ease_out(p)) * breathe, 0, dy)
        elif anim == "left":
            place(frame, im, cx, cy, a, 1, -260 * (1 - ease_out(p)), dy)
        else:
            place(frame, im, cx, cy, a, 1, 0, 50 * (1 - ease_out(p)) + dy)
    draw_caption(frame, t)
    # transition wipe
    ov = None
    for b in S[1:-1]:
        q = (t - (b - 0.3)) / 0.55
        if 0 <= q <= 1:
            ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
            x = -1100 + q * (W + 2200)
            for off, wdt, al in ((0, 220, 235), (-300, 60, 150), (260, 30, 120)):
                xx0 = x + off
                d.polygon([(xx0, 0), (xx0 + wdt, 0), (xx0 + wdt - 700, H), (xx0 - 700, H)], fill=GOLD + (al,))
            fl = max(0, 1 - abs(t - b) / 0.12)
            if fl > 0:
                d.rectangle([0, 0, W, H], fill=(255, 245, 220, int(60 * fl)))
            frame.alpha_composite(ov)
    # progress bar
    d = ImageDraw.Draw(frame)
    d.rounded_rectangle([60, 70, W - 60, 78], radius=4, fill=(255, 255, 255, 50))
    d.rounded_rectangle([60, 70, 60 + (W - 120) * min(t / DUR, 1), 78], radius=4, fill=GOLD + (255,))
    f = font(30, "bold")
    d.text((60, 98), "3 JENIS SABAR", font=f, fill=CREAM + (170,))
    return frame.convert("RGB")

if PREVIEW:
    for t in PREVIEW:
        render(t).save(os.path.join(WORK, f"prev_{t:05.2f}.jpg"), quality=85)
    sys.exit()

cmd = [FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
       "-i", comp_path, "-filter_complex", f"[1:a]atempo={TEMPO:.5f},apad,atrim=0:{DUR},afade=t=out:st={DUR-0.4}:d=0.4,aresample=48000[a]",
       "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", str(DUR), OUT]
p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
N = int(DUR * FPS)
for i in range(N):
    p.stdin.write(render(i / FPS).tobytes())
    if i % 90 == 0: print(f"frame {i}/{N}", flush=True)
p.stdin.close(); p.wait()
print("done", OUT)
