import os
import discord
from discord.ext import commands
from flask import Flask
from threading import Thread

# إعداد خادم الويب لتجاوز فحص المنافذ في Render
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

keep_alive()

# إعداد البوت مع الـ intents المطلوبة
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# تشغيل البوت باستخدام التوكن المحفوظ في متغيرات البيئة
bot.run(os.environ.get("TOKEN"))
import asyncio
import datetime
import io
import json
import math
import os
import random
import re
import unicodedata

import discord
from discord.ext import commands

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont   # لرسم الصور: pip install pillow
except ImportError:
    Image = None

# ============ الإعدادات ============
TOKEN = "ضع_التوكن_هنا"
PREFIX = "!"

JOIN_TIME = 30      # مدة التسجيل بالثواني
TURN_TIME = 30      # مدة دور اللاعب بالثواني
MIN_PLAYERS = 3     # أقل عدد لاعبين
MAX_PLAYERS = 15    # أكبر عدد لاعبين

QUESTION_TIME = 15         # مدة السؤال بالثواني لكل ألعاب الكتابة السريعة (أعلام، عواصم، ماركات، رياضيات)

FLAG_ROUND_TIME = QUESTION_TIME       # مدة كل علم بالثواني
FLAG_DEFAULT_ROUNDS = 10   # عدد الأعلام بالجولة إذا ما حددت
FLAG_MAX_ROUNDS = 30       # أكبر عدد أعلام بالجولة

BRAND_ROUND_TIME = QUESTION_TIME      # مدة كل ماركة بالثواني
NO_REPEAT_LAST = 7         # ما بتتكرر الماركة إلا بعد ما تنسأل 7 ماركات غيرها على الأقل

CAPITAL_ROUND_TIME = QUESTION_TIME   # مدة كل سؤال عواصم بالثواني
MATH_ROUND_TIME = QUESTION_TIME      # مدة كل معادلة بالثواني
CAPITAL_ROUNDS = 10        # عدد أسئلة العواصم بالجولة

STREAK_STEP = 5            # كل كم إجابة ورا بعض بتطلع رسالة ستريك (5-10-15...)

# مجلد صور الشعارات (بينعمل لحاله جنب main.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BRANDS_DIR = os.path.join(BASE_DIR, "brands")
os.makedirs(BRANDS_DIR, exist_ok=True)

SERVER_NAME = "Bavrians Server"
DAILY_LIMIT = 100          # أقصى نقاط بتنحسب للاعب باليوم
ROULETTE_WIN_POINTS = 5    # نقاط الفوز بالروليت
XO_WIN_POINTS = 3          # نقاط الفوز بلعبة XO (حط 0 إذا ما بدك نقاط)
XO_JOIN_TIME = 30          # مدة انتظار الخصم بلعبة XO
XO_TURN_TIME = 30          # مدة دور اللاعب بلعبة XO (إذا ما لعب بيخسر)
TOP_COUNT = 10             # كم لاعب بيطلعوا بـ !توب (لحد 10، بعمودين متل المثال)
LEVEL_UNIT = 25            # كل مستوى بيحتاج نقاط أكتر (المستوى 2 من 25 نقطة، 3 من 100، 4 من 225...)
POINTS_FILE = os.path.join(BASE_DIR, "points.json")   # هون بتنحفظ النقاط للأبد
GAMES_IMAGE = os.path.join(BASE_DIR, "games.png")     # صورة !العاب (لازم تكون جنب main.py)
# ===================================

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None, case_insensitive=True)

# كل روم فيها لعبة وحدة بنفس الوقت
active_games = {}
active_flags = {}
active_brands = {}
active_xo = {}


def secs(n):
    """بيكتب عدد الثواني بالصيغة الصح: 5 ثوانٍ، 15 ثانية"""
    return f"{n} ثوانٍ" if 3 <= n <= 10 else f"{n} ثانية"


def channel_busy(cid):
    return cid in active_games or cid in active_flags or cid in active_brands or cid in active_xo


def get_game(cid):
    return active_flags.get(cid) or active_brands.get(cid) or active_games.get(cid) or active_xo.get(cid)


# ================= نظام النقاط (بينحفظ للأبد بملف points.json) =================
class PointsDB:
    def __init__(self, path):
        self.path = path
        self.users = {}
        self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self.users = json.load(f).get("users", {})
        except FileNotFoundError:
            pass
        except Exception as e:
            print("points.json مو مقروء، رح ياخد نسخة احتياطية وبيبدأ من جديد:", e)
            try:
                os.replace(self.path, self.path + ".bak")
            except OSError:
                pass
            self.users = {}

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"users": self.users}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    @staticmethod
    def today():
        return datetime.date.today().isoformat()

    def _user(self, uid):
        u = self.users.setdefault(str(uid), {"name": "", "total": 0, "daily": 0, "day": "", "warned": ""})
        if u.get("day") != self.today():
            u["day"] = self.today()
            u["daily"] = 0
        return u

    def award(self, member, amount=1):
        """بيضيف نقاط للاعب مع مراعاة الحد اليومي.
        بيرجّع (النقاط اللي انحسبت فعلًا، رسالة تنبيه أو نص فاضي)"""
        u = self._user(member.id)
        u["name"] = member.display_name
        given = max(0, min(amount, DAILY_LIMIT - u["daily"]))
        u["daily"] += given
        u["total"] += given
        note = ""
        if (given < amount or u["daily"] >= DAILY_LIMIT) and u.get("warned") != self.today():
            u["warned"] = self.today()
            if given > 0:
                note = f"🔒 {member.mention} وصلت لحدك اليومي (**{DAILY_LIMIT}** نقطة)! النقاط الجاية ما رح تنحسب لحد بكرا."
            else:
                note = f"🔒 {member.mention} وصلت لحدك اليومي (**{DAILY_LIMIT}** نقطة)، النقاط ما رح تنحسب لحد بكرا."
        try:
            self._save()
        except Exception as e:
            print("ما قدرت احفظ النقاط:", e)
        return given, note

    def get(self, uid):
        u = self.users.get(str(uid))
        if not u:
            return {"total": 0, "daily": 0}
        daily = u["daily"] if u.get("day") == self.today() else 0
        return {"total": u["total"], "daily": daily}

    def ranking(self):
        rows = [(uid, u) for uid, u in self.users.items() if u.get("total", 0) > 0]
        rows.sort(key=lambda r: (-r[1]["total"], r[1].get("name", "")))
        return rows

    def top(self, n=5):
        return self.ranking()[:n]

    def rank_of(self, uid):
        for i, (u, _) in enumerate(self.ranking(), start=1):
            if u == str(uid):
                return i
        return None


points_db = PointsDB(POINTS_FILE)


def normalize(text):
    """توحيد الهمزات عشان !إنعاش و !انعاش يشتغلوا نفس الشي"""
    for ch in "أإآ":
        text = text.replace(ch, "ا")
    return text.strip()


# ================= رسم عجلة الروليت =================
WHEEL_COLORS = [
    (231, 76, 60), (52, 152, 219), (46, 204, 113), (241, 196, 15),
    (155, 89, 182), (230, 126, 34), (26, 188, 156), (236, 100, 160),
]


def _wheel_font(size):
    for name in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size)
    except Exception:
        return ImageFont.load_default()


def make_wheel_gif(numbers, chosen, size=380, frames_count=46):
    """بيرسم عجلة فيها أرقام اللاعبين الأحياء وبيدورها وبيوقفها على الرقم المختار.
    بيرجّع (ملف GIF بالذاكرة، مدة الدوران بالثواني)"""
    n = len(numbers)
    cx = cy = size // 2
    radius = size // 2 - 16
    seg = 360 / n
    idx = numbers.index(chosen)

    colors = [WHEEL_COLORS[i % len(WHEEL_COLORS)] for i in range(n)]
    if n > 2 and colors[-1] == colors[0]:
        colors[-1] = WHEEL_COLORS[(n + 3) % len(WHEEL_COLORS)]

    # ---- العجلة نفسها (بتنرسم مرة وحدة وبعدين بتتدور) ----
    base = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(base)
    d.ellipse([cx - radius - 6, cy - radius - 6, cx + radius + 6, cy + radius + 6],
              fill=(255, 255, 255))
    for i in range(n):
        d.pieslice([cx - radius, cy - radius, cx + radius, cy + radius],
                   start=i * seg, end=(i + 1) * seg, fill=colors[i],
                   outline=(255, 255, 255), width=2)

    font_size = 30 if n <= 8 else (24 if n <= 16 else 17)
    font = _wheel_font(font_size)
    for i, num in enumerate(numbers):
        c = (i + 0.5) * seg                      # زاوية منتصف القطعة (باتجاه عقارب الساعة من الشرق)
        tmp = Image.new("RGBA", (90, 60), (0, 0, 0, 0))
        ImageDraw.Draw(tmp).text((45, 30), str(num), font=font, fill=(255, 255, 255),
                                 anchor="mm", stroke_width=2, stroke_fill=(0, 0, 0))
        tmp = tmp.rotate(270 - c, expand=True, resample=Image.BICUBIC)
        r = radius * (0.76 if n > 2 else 0.6)
        px = cx + r * math.cos(math.radians(c))
        py = cy + r * math.sin(math.radians(c))
        base.alpha_composite(tmp, (int(px - tmp.width / 2), int(py - tmp.height / 2)))

    d.ellipse([cx - 20, cy - 20, cx + 20, cy + 20], fill=(30, 31, 34), outline=(255, 255, 255), width=3)

    # ---- زاوية الوقوف: القطعة المختارة تحت المؤشر (فوق) ----
    jitter = random.uniform(-0.3, 0.3) * seg
    final_angle = 360 * random.randint(3, 4) + ((((idx + 0.5) * seg + 90) + jitter) % 360)

    bg_color = (43, 45, 49)
    frames, durations = [], []
    for k in range(frames_count):
        t = k / (frames_count - 1)
        angle = final_angle * (1 - (1 - t) ** 3)      # بتبدأ سريعة وبتبطّأ لحد ما توقف
        frame = Image.new("RGB", (size, size), bg_color)
        rot = base.rotate(angle, resample=Image.BICUBIC)
        frame.paste(rot, (0, 0), rot)
        fd = ImageDraw.Draw(frame)
        fd.polygon([(cx - 17, 3), (cx + 17, 3), (cx, 42)], fill=(255, 255, 255), outline=(0, 0, 0))
        fd.polygon([(cx - 11, 6), (cx + 11, 6), (cx, 34)], fill=(220, 30, 30))
        frames.append(frame)
        durations.append(int(45 + 90 * t ** 2))        # الإطارات الأخيرة أبطأ شوي
    spin_seconds = sum(durations) / 1000
    durations[-1] = 4000                               # بتضل واقفة على آخر إطار

    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:],
                   duration=durations, disposal=1)
    buf.seek(0)
    return buf, spin_seconds


# ================= رسم الصور (معادلات الرياضيات + ترتيب النقاط) =================
# ---- تشكيل الحروف العربية (بدون أي مكتبة إضافية) ----
_AR_RIGHT_ONLY = set("آأإاٱدذرزوؤةژ")     # حروف ما بتتصل بالحرف اللي بعدها
_FORMS = {}   # (الحرف الأساسي، الشكل) -> الحرف المشكّل
_LIGS = {}    # (ل، ألف) -> {الشكل: الحرف}


def _build_forms():
    for cp in list(range(0xFE70, 0xFF00)) + list(range(0xFB50, 0xFE00)):
        ch = chr(cp)
        dec = unicodedata.decomposition(ch)
        if not dec.startswith("<"):
            continue
        tag, _, rest = dec.partition(" ")
        tag = tag.strip("<>")
        if tag not in ("isolated", "initial", "medial", "final"):
            continue
        base = [chr(int(x, 16)) for x in rest.split()]
        if len(base) == 1:
            _FORMS.setdefault((base[0], tag), ch)
        elif len(base) == 2 and base[0] == "ل":
            _LIGS.setdefault((base[0], base[1]), {})[tag] = ch


_build_forms()


def _is_ar_block(c):
    return ("؀" <= c <= "ۿ") or ("ݐ" <= c <= "ݿ") or ("ﭐ" <= c <= "﷿") or ("ﹰ" <= c <= "﻿")


def _is_ar_letter(c):
    return ("ؠ" <= c <= "ي") or ("ٱ" <= c <= "ۓ")


def _can_join_prev(c):
    return _is_ar_letter(c) and c != "ء"


def _can_join_next(c):
    return _is_ar_letter(c) and c != "ء" and c not in _AR_RIGHT_ONLY


def _shape_ar(s):
    toks, i = [], 0
    while i < len(s):
        if s[i] == "ل" and i + 1 < len(s) and s[i + 1] in "اأإآ":
            toks.append(("lig", "ل", s[i + 1]))
            i += 2
        else:
            toks.append(("one", s[i]))
            i += 1
    out = []
    for k, t in enumerate(toks):
        first, last = t[1], t[-1]
        pj = k > 0 and _can_join_next(toks[k - 1][-1]) and _can_join_prev(first)
        nj = k < len(toks) - 1 and _can_join_next(last) and _can_join_prev(toks[k + 1][1])
        form = "medial" if (pj and nj) else "final" if pj else "initial" if nj else "isolated"
        if t[0] == "lig":
            ch = _LIGS.get(("ل", t[2]), {}).get("final" if pj else "isolated")
            if ch:
                out.append(ch)
            else:
                out.append(_FORMS.get(("ل", "medial" if pj else "initial"), "ل"))
                out.append(_FORMS.get((t[2], "final"), t[2]))
        else:
            out.append(_FORMS.get((first, form), first))
    return "".join(out)


def _char_dir(c):
    if "٠" <= c <= "٩" or "۰" <= c <= "۹":
        return "L"
    if _is_ar_block(c):
        return "R"
    return "L" if c.isalnum() else "N"


def to_visual(text):
    """بيرتّب النص العربي (مع الأرقام والإنجليزي) بالشكل اللي بدو ياه Pillow لما ما يكون عنده raqm"""
    if not text:
        return text
    dirs = [_char_dir(c) for c in text]
    n = len(text)
    base = next((d for d in dirs if d != "N"), "R")      # اتجاه الفقرة = اتجاه أول حرف واضح
    res = []
    for i, d in enumerate(dirs):
        if d != "N":
            res.append(d)
            continue
        j = i - 1
        while j >= 0 and dirs[j] == "N":
            j -= 1
        k = i + 1
        while k < n and dirs[k] == "N":
            k += 1
        res.append(dirs[j] if (j >= 0 and k < n and dirs[j] == dirs[k]) else base)
    runs, cur, buf = [], res[0], text[0]
    for c, d in zip(text[1:], res[1:]):
        if d == cur:
            buf += c
        else:
            runs.append((cur, buf))
            cur, buf = d, c
    runs.append((cur, buf))
    ordered = runs if base == "L" else list(reversed(runs))
    return "".join(seg if d == "L" else _shape_ar(seg)[::-1] for d, seg in ordered)


def ar_text(text):
    """بيجهّز النص العربي للرسم (تشكيل الحروف + ترتيب الاتجاه) بنفس الطريقة على أي جهاز"""
    return to_visual(text)


_NAME_BAD = re.compile(r"[^ء-يٱ-ۓ٠-٩A-Za-z0-9À-ɏ _.\-]")


def clean_name(name, fallback="لاعب"):
    """بيشيل الإيموجي والرموز الغريبة اللي الخط ما بيعرف يرسمها"""
    name = _NAME_BAD.sub("", name or "").strip()
    return name or fallback


AR_FONTS = ["arialbd.ttf", "tahomabd.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf"]
NUM_FONTS = ["arialbd.ttf", "segoeuib.ttf", "tahomabd.ttf", "DejaVuSans-Bold.ttf"]
_FONT_CACHE = {}


def _font_ok(font):
    """بيتأكد إن الخط فيه حروف عربية (شكل البداية والنهاية) عشان ما يطلع مربعات"""
    try:
        missing = font.getmask("\U0010FFFF").tobytes()
        for ch in "\ufe91\ufe9a\ufee0":
            m = font.getmask(ch)
            if m.getbbox() is None or m.tobytes() == missing:
                return False
        return True
    except Exception:
        return True


def _font(size, names):
    key = (int(size), tuple(names))
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    found = None
    for name in names:
        try:
            f = ImageFont.truetype(name, int(size), layout_engine=0)   # 0 = Basic (بدون raqm)
        except Exception:
            continue
        if names is NUM_FONTS or _font_ok(f):
            found = f
            break
    if found is None:
        try:
            found = ImageFont.load_default(int(size))
        except Exception:
            found = ImageFont.load_default()
    _FONT_CACHE[key] = found
    return found


def make_math_image(expr):
    """بيرسم المعادلة بخط كبير أبيض على خلفية غامقة (والأس بيطلع صغير فوق)"""
    S, W, H = 2, 900, 260
    white = (255, 255, 255)
    img = Image.new("RGB", (W * S, H * S), (15, 16, 18))
    d = ImageDraw.Draw(img)
    size = 150
    while True:
        f = _font(size * S, NUM_FONTS)
        if "^" in expr:
            base, exp = expr.split("^", 1)
            fe = _font(size * 0.55 * S, NUM_FONTS)
            gap = 6 * S
            total = d.textlength(base, font=f) + gap + d.textlength(exp, font=fe)
        else:
            total = d.textlength(expr, font=f)
        if total / S <= W * 0.9 or size <= 40:
            break
        size -= 6
    cx, cy = W * S / 2, H * S / 2
    if "^" in expr:
        x = cx - total / 2
        base_y = cy + size * S * 0.36
        d.text((x, base_y), base, font=f, fill=white, anchor="ls")
        d.text((x + d.textlength(base, font=f) + gap, base_y - size * S * 0.52), exp, font=fe, fill=white, anchor="ls")
    else:
        d.text((cx, cy), expr, font=f, fill=white, anchor="mm")
    buf = io.BytesIO()
    img.resize((W, H), Image.LANCZOS).save(buf, "PNG")
    buf.seek(0)
    return buf


def _round_avatar(data, size):
    im = Image.open(io.BytesIO(data)).convert("RGBA").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size * 4 - 1, size * 4 - 1], fill=255)
    mask = mask.resize((size, size), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    return out


# صورة السيرفر (الدببة) اللي بتظهر فوق يسار صورة !توب. إذا حطيت ملف اسمه server_icon.png جنب main.py بيستخدمه بدالها
SERVER_ICON_B64 = (
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAQDAwMDAgQDAwMEBAQFBgoGBgUFBgwICQcKDgwPDg4MDQ0PERYTDxAVEQ0NExoTFRcY"
    "GRkZDxIbHRsYHRYYGRj/2wBDAQQEBAYFBgsGBgsYEA0QGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgYGBgY"
    "GBgYGBgYGBj/wAARCAEAAQADASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUF"
    "BAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVW"
    "V1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi"
    "4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAEC"
    "AxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVm"
    "Z2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq"
    "8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD1/wCEvwp0L4UeDYdO0+BH1CRAbm6IwzHrj8K77jrTc7m5PPrSgAniuFu5tYdnNKTwKac5"
    "4ozkYNAFNz/xMJU/vR1R05v3MoHaQirx51bjuoWsrTW+e6TPInaiwGoW6Uxm5ppbnoeKYzqeh59KVgHluKA/FQlj070bvekBIXBp"
    "Cxxx0qHdzQz4GadwJN1JvFRGTHvSbienWkBNvpkz/uqiMgGcnBHXNQzy4hznIpgXRJjH0qQSCqQc4UnoRTxJxzSAtGTmo5WJx9ai"
    "8w547013PHPegC2re9Sb+KqByBmn7xgc0ATluacjHBqsX4zUit1ANICfcdrfSq1m/wC6NSlso2Dng1Ss2PkEikNF/dSZ75qLfx7+"
    "lBfj5e/SqQDyxNMJ7Um/r6CmM3PFArFO9lZHVs4I7181/Hj9n608WaVdeL/ClssOpQKZLi2jH+sA6t7kntX0ZqDZkxjjFS6AxF67"
    "4BwOh70Qk4u6G1odIGFKCRUeeMU4NVDHgmlVS7AAcnvTNwBwacrYcMD070Iajd2R5H4k+MC6R4y+wQWSukbBWk3Y571pWPjayfdd"
    "KFCy/MRu7mvN/EeiWWt/GW10WyOJby5CSPn7oJ617OvwB0e1sPLs9U23OMFjk5aqp05tvax+gY2jkeFjSpVotSaTb9e5xc/xYmXx"
    "DBYQWSmBpBGx3e/WvSBJ5iJIgwrLkfSvmvWY5dE+Ih026YBrSbcXz1VT1rsbn9obwTpm20uJRvjGwsCTzXLCbUmpHlcTYXB05Uo4"
    "JLa7t17HsJbGTnJppbuK8ltfjd4Z1gCOx1MW5Y4DFCRXV21j411OyS9sLgT2zjKSJt5FbKSex8pOnKHxKx1hfFNLjHvXKHRvH4OG"
    "DZ+gqJrL4gxHAt2b8qCDr/M5xnJ9KAw3npwMms7T01UWatqVsyT9xTdRgvLzTLiytHMU8i4EmPu0WA8p8c/ETVNX1x/DHhPUPsRU"
    "4kvAAd3tg+lZXhL4keKND1s+HvF8i6jbvgJdlwNme+BXO6r8Mtd0a78vXPEQtInkZmcRhiQTntzU03hrwObJYobhpruT5XvSzDZj"
    "viu5U4uNrGPM0z6Bj8S+Hn1BdOXUkF35avs7YPTmpLjxLoNncRWlzqyJNM2yNBzuPpmvFI9O8GE2+6KSVXAia8ErDoPSn6h4I0Wa"
    "bz9N1dpXRd0K5Pyn8aj6vHuP2h72HBAORg9DSM4OBjofzrzvRj4zutFSC1vQ1zENixkDJA6c1csX+JseqxR6npjSW+4BnDKMD1rn"
    "lTkjRSud2GG3Kn3qTdwDVfeV5YYPQ0qyHGOue9ZDLG7ipEbDGqhfGM8UrTCPl2Vc88sKV0tx2ZZmnSK1d3k2Iilm49qwdC8V6Bq1"
    "sfsN/HIQSMHjFLqmq6ddaXc2b3qIZEKBhzjIxXjHhv4U/wDCM3E+q33iXzLfDsowVwTnHevJxuNtpSmk/vPXwOCjJN14vyPejqlk"
    "Mu86Aj0INcwnxQ8JyeLovDovx9ulbao2nk14j4N0zxjqviozzawYrZGYANg7hz71NpXwZ8Sw/HCy8QXNzv0+GTeZcjnI+tRha+Il"
    "UUalRW8jbEYXDwg3GLufTW7Kgk8fzqMuAc4phYKqqTwqgDmmGRiK9u+x4bWpn37kzdan0InMh+orN1CXE5xV/QW/cOSepNIZ02c0"
    "hdQMscAdzVK+1K306zaaeQA44B7155rHiu4vZWSEskXYZrVK57WU5HXx75lpFdTu9Q8TWNgSqSCZ/QcYrl9Q8bXEgIh+Ra4ue+Z2"
    "+ZyfxqsZJJZNiIzu3AUd62iorRH32C4bwuHV3G77syNXsNXt/FEfijw/eiLUI23DK7v51Uvfi98YbJmEl5uYtlcRDk16Jpfw58Z6"
    "wqyQ6ZPDG3R2HGK7BPg1NpfhnUNV1yWKRobdnRNuCGFPkkryTsTmtbJ1edfllNK2mr8kfH3inxJHea15usXRfULpc3DqSNpPVcV1"
    "Vl8L/hBdeEo9UufiHaWl88e9opY3YxnHQ1laBD4BHiq+1DxM/mzQagzKN5AAB6YryjxvZ2GqfEPU76xv2i06admjjViAAegrgU4O"
    "bbZ+e1J1fs7/ANaHpPiFvB3hPwymgaffJrEt+RcJfQAoFHTGOtd3+zl8R9X0nxDc+FH1Ay2UuZEWQZKYHA5ryb4batoGi+LtOuNa"
    "tjf2lviPBb7q56nNekXQ8K3/AO0jBrPhC9iitLpjJIEPyocjimnC3NF6mcoVHL2dTW63Pqg+KtUQkDaPqopp8V6nt6Ln/dFZ1wn7"
    "xniKshxhgetVmI6Dv1re55aNg+KNQfhlTnr8orkfE3xAj01HgtSj3Z+8QB8lZHi3xLFpdubK0cG6YYY/3K8wkuXkzJI+7PPPWuin"
    "SvrIylLoibU72a9uZLy8lMkr8/MePyrl9Yu5DZSrG2Noydq12vhjwhqPjLU/3eYrFD88pHBFev23w58MW2gyaStpvEq7WkY5P51p"
    "KSvoSo6XZ43JY6BofwZguo9WiN/cM3yEEk8Zx7VjaZezwxxrdQyxswBDHPIpdL+F3ipvi8mm3mk3baRFP5nnM3ybCT2r6i/4R3RZ"
    "tOisrmwiKIgQYUA8D1p8yDlPAbO/mjlWW3uHV1+YYY16DoXxL1K1RIdUQXMQ4yABgU3xV8MPsEEmqaE5aNcs9vyWA9c1wUEm1yjc"
    "NnBB7H0ptKQrtHtA1O01Q/bLPBjbkgdjTlcEEk8Vx/g64IsZ4G5G8kVt6nfrZ6VJcOhKD5SQcba8vEyVJtvod2GpSrzjTju9DrdG"
    "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"
)
SERVER_ICON_FILE = os.path.join(BASE_DIR, "server_icon.png")


def load_server_icon():
    try:
        if os.path.exists(SERVER_ICON_FILE):
            with open(SERVER_ICON_FILE, "rb") as f:
                return f.read()
        import base64
        return base64.b64decode("".join(SERVER_ICON_B64))
    except Exception:
        return None


def level_of(points):
    """المستوى من النقاط: 1 من الصفر، 2 من 25، 3 من 100، 4 من 225، 5 من 400... (بتغيّر LEVEL_UNIT)"""
    return 1 + math.isqrt(max(0, points) // LEVEL_UNIT)


def _draw_medal(d, cx, cy, rank, S):
    cols = {1: ((255, 200, 61), (190, 135, 20)), 2: ((205, 213, 222), (130, 140, 152)), 3: ((222, 143, 78), (150, 88, 38))}
    face, edge = cols[rank]

    def poly(pts, fill):
        d.polygon([((cx + x) * S, (cy + y) * S) for x, y in pts], fill=fill)

    poly([(-20, -34), (-8, -34), (5, -2), (-8, -2)], (64, 120, 214))     # الشريط الأزرق
    poly([(8, -34), (20, -34), (8, -2), (-5, -2)], (222, 72, 72))        # الشريط الأحمر
    r = 21
    d.ellipse([(cx - r) * S, (cy + 4 - r) * S, (cx + r) * S, (cy + 4 + r) * S], fill=face, outline=edge, width=3 * S)
    d.ellipse([(cx - r + 6) * S, (cy + 4 - r + 6) * S, (cx + r - 6) * S, (cy + 4 + r - 6) * S], outline=edge, width=2 * S)
    d.text((cx * S, (cy + 4) * S), str(rank), font=_font(20 * S, NUM_FONTS), fill=edge, anchor="mm")


def make_top_image(entries, server_name=SERVER_NAME, viewer_avatar=None, footer_extra=""):
    """صورة المتصدرين. entries = [(الاسم، النقاط، بايتات الصورة أو None), ...] من الأول للأخير.
    لحد 5 لاعبين بعمود وحدة، ولحد 10 بعمودين (متل المثال)."""
    S = 2
    entries = entries[:10]
    n = len(entries)
    two = True   # دايمًا عمودين (5 + 5) والخانات الفاضية بتظهر فاضية متل المثال
    W = 1240
    M, COLGAP, ROW_H, GAP, HEAD = 44, 32, 100, 16, 160
    rows = 5
    H = HEAD + rows * (ROW_H + GAP) + 78
    col_w = (W - 2 * M - (COLGAP if two else 0)) / (2 if two else 1)
    BG1, BG2 = (6, 13, 23), (11, 29, 45)
    TEAL, AMBER = (46, 230, 197), (255, 181, 71)
    WHITE, MUTED = (244, 248, 251), (150, 175, 192)

    img = Image.new("RGB", (W * S, H * S), BG1)
    d = ImageDraw.Draw(img)
    for y in range(H * S):
        t = y / (H * S - 1)
        d.line([(0, y), (W * S, y)], fill=tuple(int(BG1[i] + (BG2[i] - BG1[i]) * t) for i in range(3)))
    gw, gh = max(W // 4, 1), max(H // 4, 1)
    glow = Image.new("RGB", (gw, gh), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([gw * 0.55, -gh * 0.20, gw * 1.15, gh * 0.30], fill=(12, 84, 74))
    gd.ellipse([-gw * 0.20, -gh * 0.15, gw * 0.40, gh * 0.25], fill=(96, 64, 18))
    glow = glow.filter(ImageFilter.GaussianBlur(24)).resize((W * S, H * S), Image.BICUBIC)
    img = ImageChops.add(img, glow)
    d = ImageDraw.Draw(img)

    def text(xy, s, size, fill, anchor="mm", fonts=AR_FONTS):
        d.text((xy[0] * S, xy[1] * S), ar_text(s), font=_font(size * S, fonts), fill=fill, anchor=anchor)

    def width(s, size, fonts=AR_FONTS):
        return d.textlength(ar_text(s), font=_font(size * S, fonts)) / S

    def circle_image(data, r, ring, cx, cy, fallback):
        d.ellipse([(cx - r - 3) * S, (cy - r - 3) * S, (cx + r + 3) * S, (cy + r + 3) * S], fill=ring)
        if data:
            try:
                av = _round_avatar(data, 2 * r * S)
                img.paste(av, (int((cx - r) * S), int((cy - r) * S)), av)
                return
            except Exception:
                pass
        d.ellipse([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S], fill=(24, 64, 86))
        text((cx, cy), (fallback[:1] or "?").upper(), int(r * 0.9), WHITE)

    # ---- الهيدر: صورة صاحب الأمر + عنوان ----
    circle_image(load_server_icon() or viewer_avatar, 38, TEAL, M + 40, 76, server_name)
    title = f"قائمة المتصدرين في {server_name}"
    px0, px1 = M + 100, W - M
    size = 36
    while width(title, size) > (px1 - px0) - 70 and size > 20:
        size -= 2
    d.rounded_rectangle([px0 * S, 38 * S, px1 * S, 114 * S], radius=34 * S, fill=(12, 23, 36), outline=(34, 96, 104), width=2 * S)
    text(((px0 + px1) / 2, 76), title, size, WHITE)

    # ---- الخانات الفاضية ----
    for i in range(n, 10):
        col, row = i // 5, i % 5
        x0 = M + col * (col_w + COLGAP)
        y0 = HEAD + row * (ROW_H + GAP)
        d.rounded_rectangle([x0 * S, y0 * S, (x0 + col_w) * S, (y0 + ROW_H) * S], radius=24 * S,
                            fill=(11, 22, 34), outline=(26, 44, 62), width=2 * S)

    # ---- الصفوف ----
    ring = {1: (255, 200, 61), 2: (205, 213, 222), 3: (222, 143, 78)}
    for i, (name, pts, avatar) in enumerate(entries):
        rank = i + 1
        col, row = i // 5, i % 5
        x0 = M + col * (col_w + COLGAP)
        x1 = x0 + col_w
        y0 = HEAD + row * (ROW_H + GAP)
        ym = y0 + ROW_H / 2
        accent = ring.get(rank)
        d.rounded_rectangle([x0 * S, y0 * S, x1 * S, (y0 + ROW_H) * S], radius=24 * S,
                            fill=(18, 31, 46) if rank == 1 else (13, 25, 39),
                            outline=accent if rank == 1 else (30, 50, 70), width=(3 if rank == 1 else 2) * S)
        ax = x0 + 26 + 36
        circle_image(avatar, 36, accent or (44, 80, 104), ax, ym, name)
        tx = ax + 36 + 20
        max_w = (x1 - (76 if rank <= 3 else 24)) - tx
        label = f"{rank}. {name}"
        if width(label, 30) > max_w:
            while len(name) > 1 and width(f"{rank}. {name.rstrip()}…", 30) > max_w:
                name = name[:-1]
            label = f"{rank}. {name.rstrip()}…"
        text((tx, ym - 17), label, 30, WHITE, anchor="lm")
        text((tx, ym + 22), f"المستوى {level_of(pts)} | النقاط: {pts:,}", 22, MUTED, anchor="lm")
        if rank <= 3:
            _draw_medal(d, x1 - 44, ym - 2, rank, S)

    foot = "النقاط من الألعاب • الحد الأقصى 100 نقطة باليوم"
    if footer_extra:
        foot = footer_extra + "  •  " + foot
    text((W / 2, H - 38), foot, 21, MUTED)
    buf = io.BytesIO()
    img.resize((W, H), Image.LANCZOS).save(buf, "PNG")
    buf.seek(0)
    return buf


ROULETTE_RULES = (
    "1- اكتب `!دخول` للمشاركة وسيُعطى لك رقم حسب ترتيب دخولك (صاحب اللعبة يدخل تلقائيًا)\n"
    "2- ستبدأ الجولة الأولى وسيتم تدوير العجلة واختيار لاعب عشوائي\n"
    "3- إذا كنت اللاعب المختار، فستختار لاعبًا من اختيارك ليتم طرده من اللعبة أو إنعاش لاعب\n"
    "4- يُطرد اللاعب وتبدأ جولة جديدة\n"
    "5- إذا تبقى لاعبان فقط، تدور العجلة مجددًا ويُعلن الفائز مباشرة"
)


class RouletteGame:
    def __init__(self, channel, host):
        self.channel = channel
        self.players = {}   # الرقم -> العضو
        self.status = {}    # الرقم -> alive / dead / out
        self.joining = True
        self.starter = host
        self.task = None
        self.winner = None   # بيتحدد لما يضل لاعبين وتوقف العجلة على واحد منهم
        self.intro_msg = None
        self.add_player(host)

    def add_player(self, member):
        num = len(self.players) + 1
        self.players[num] = member
        self.status[num] = "alive"
        return num

    def has_joined(self, member):
        return any(m.id == member.id for m in self.players.values())

    def nums(self, state):
        return [n for n, s in self.status.items() if s == state]

    def format_list(self, numbers):
        return "\n".join(
            f"**{n}** ← {self.players[n].display_name}" for n in numbers
        )

    def build_intro(self, failed=False):
        embed = discord.Embed(title="🎯 روليت", color=discord.Color.red())
        embed.add_field(name="📜 طريقة اللعب:", value=ROULETTE_RULES, inline=False)
        names = "\n".join(f"**{n}** ← {m.mention}" for n, m in self.players.items()) or "لا أحد بعد"
        embed.add_field(
            name=f"👥 اللاعبين المشاركين: ({len(self.players)}/{MAX_PLAYERS})",
            value=names,
            inline=False,
        )
        if failed:
            embed.set_footer(text=f"❌ لم ينضم عدد كافٍ من اللاعبين لبدء اللعبة. (الحد الأدنى: {MIN_PLAYERS})")
        else:
            embed.set_footer(text=f"التسجيل ينتهي بعد {JOIN_TIME} ثانية  •  الحد الأدنى للاعبين: {MIN_PLAYERS}")
        return embed

    async def refresh_intro(self):
        if self.intro_msg is not None:
            try:
                await self.intro_msg.edit(embed=self.build_intro())
            except Exception:
                pass

    async def run(self):
        ch = self.channel

        # ---------- التسجيل ----------
        self.intro_msg = await ch.send(embed=self.build_intro())
        await asyncio.sleep(JOIN_TIME)
        self.joining = False

        if len(self.players) < MIN_PLAYERS:
            try:
                await self.intro_msg.edit(embed=self.build_intro(failed=True))
            except Exception:
                await ch.send(f"❌ لم ينضم عدد كافٍ من اللاعبين لبدء اللعبة. (الحد الأدنى: {MIN_PLAYERS})")
            return

        await ch.send(
            "✅ انتهى التسجيل! هذي الأرقام:\n" + self.format_list(self.nums("alive"))
        )
        await asyncio.sleep(4)

        # ---------- الأدوار ----------
        while self.winner is None and len(self.nums("alive")) > 1:
            await self.play_turn()
            await asyncio.sleep(3)

        winner = self.winner if self.winner is not None else self.nums("alive")[0]
        member = self.players[winner]
        given, note = points_db.award(member, ROULETTE_WIN_POINTS)
        text = f"🏆 الفائز هو {member.mention} (رقم **{winner}**)! مبروك 🎉\n💰 **+{given}** نقاط"
        if note:
            text += "\n" + note
        await ch.send(text)

    async def spin_wheel(self, alive, chosen, final_two=False):
        ch = self.channel
        title = "🎡 العجلة عم تدور..."
        if final_two:
            title = "⚔️ باقي لاعبين اثنين! العجلة هلق بتحدد الفايز..."

        wheel = None
        if Image is not None:
            try:
                loop = asyncio.get_running_loop()
                wheel = await loop.run_in_executor(None, make_wheel_gif, alive, chosen)
            except Exception as e:
                print("Wheel error:", e)

        if wheel is None:
            # ما في Pillow أو صار خطأ بالرسم: دوران نصي بس
            await ch.send(title)
            await asyncio.sleep(3)
            return

        gif, spin_seconds = wheel
        embed = discord.Embed(title=title, color=discord.Color.gold())
        embed.set_image(url="attachment://wheel.gif")
        await ch.send(embed=embed, file=discord.File(gif, filename="wheel.gif"))
        await asyncio.sleep(spin_seconds + 0.5)

    async def play_turn(self):
        ch = self.channel
        alive = self.nums("alive")

        # العجلة: اختيار عشوائي بحت، كل لاعب حي إلو نفس الفرصة
        chosen = random.choice(alive)
        player = self.players[chosen]
        final_two = len(alive) == 2
        await self.spin_wheel(alive, chosen, final_two)
        await ch.send(f"🎡 العجلة وقفت على رقم **{chosen}** ← {player.mention}!")

        if final_two:
            # باقي لاعبين بس: اللي بتوقف عليه العجلة هو الفايز، وما بينعش حدا
            self.winner = chosen
            return

        targets = [n for n in alive if n != chosen]
        options = [
            "• اكتب **رقم** اللاعب لطرده",
            "• `!انسحاب` للانسحاب من اللعبة",
        ]
        if self.nums("dead"):
            options.insert(1, "• `!انعاش` لإنعاش لاعب ميت")
        else:
            options.append("(ما في حدا ميت، فلازم تطرد حدا أو تنسحب)")

        await ch.send(
            f"عندك **{TURN_TIME} ثانية** لتختار:\n"
            + "\n".join(options)
            + "\n\n**الأحياء:**\n"
            + self.format_list(targets)
        )

        mode = "kick"
        loop = asyncio.get_running_loop()
        deadline = loop.time() + TURN_TIME

        def check(m):
            return m.channel == ch and m.author.id == player.id

        while True:
            remaining = deadline - loop.time()
            try:
                if remaining <= 0:
                    raise asyncio.TimeoutError()
                m = await bot.wait_for("message", check=check, timeout=remaining)
            except asyncio.TimeoutError:
                self.status[chosen] = "dead"
                await ch.send(
                    f"⏰ انتهى الوقت! تم طرد {player.mention} (رقم **{chosen}**)."
                )
                return

            content = normalize(m.content)

            # ----- انسحاب -----
            if content == "!انسحاب":
                self.status[chosen] = "out"
                await ch.send(
                    f"🏳️ {player.display_name} (رقم **{chosen}**) انسحب من اللعبة."
                )
                return

            # ----- التحويل لوضع الطرد -----
            if content == "!طرد":
                mode = "kick"
                await ch.send(
                    "🔪 وضع الطرد. اكتب رقم اللاعب اللي بدك تطرده:\n"
                    + self.format_list(targets)
                )
                continue

            # ----- وضع الإنعاش -----
            if content == "!انعاش":
                dead = self.nums("dead")
                if not dead:
                    await ch.send("ما في حدا ميت لتنعشه، لازم تطرد حدا (اكتب رقمه).")
                    continue
                mode = "revive"
                await ch.send(
                    "💉 اكتب رقم اللاعب اللي بدك تنعشه، أو `!طرد` إذا غيرت رأيك:\n"
                    + self.format_list(dead)
                )
                continue

            # ----- رقم -----
            if content.isdecimal():
                n = int(content)

                if mode == "kick":
                    if n == chosen:
                        await ch.send("ما بتقدر تطرد حالك!")
                        continue
                    if self.status.get(n) != "alive":
                        await ch.send("هذا الرقم مو من الأحياء، اختار رقم تاني.")
                        continue
                    self.status[n] = "dead"
                    await ch.send(
                        f"🔪 {player.display_name} طرد {self.players[n].mention} (رقم **{n}**)!"
                    )
                    return

                else:  # revive
                    if self.status.get(n) != "dead":
                        await ch.send("هذا الرقم مو من الأموات، اختار رقم تاني.")
                        continue
                    self.status[n] = "alive"
                    await ch.send(
                        f"💉 {player.display_name} أنعش {self.players[n].mention} (رقم **{n}**) ورجع للعبة!"
                    )
                    return


# ================= لعبة الأعلام =================
def normalize_answer(text):
    """توحيد الإجابة: يشيل الهمزات والتشكيل وال التعريف وحالة الأحرف الإنجليزية"""
    text = text.lower().replace("ـ", "").replace("-", " ")
    for a in "أإآ":
        text = text.replace(a, "ا")
    text = (
        text.replace("ى", "ي")
        .replace("ة", "ه")
        .replace("ؤ", "و")
        .replace("ئ", "ي")
    )
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"(^|\s)ال", r"\1", text)
    text = re.sub(r"(^|\s)the\s", r"\1", text)
    return " ".join(text.split())


# ===== بيانات الأعلام =====
# الشكل: رمز الدولة|الأسماء العربية|الأسماء الإنجليزية (الفاصل بين أكثر من اسم هو /)
# أول اسم هو اللي بيظهر بالإجابة. لحذف دولة امسح سطرها، ولإضافة دولة زيد سطر جديد.
COUNTRIES_RAW = """
af|أفغانستان|Afghanistan
dz|الجزائر|Algeria
ar|الأرجنتين|Argentina
au|أستراليا|Australia
at|النمسا|Austria
bh|البحرين|Bahrain
bd|بنغلاديش/بنجلاديش|Bangladesh
be|بلجيكا|Belgium
br|البرازيل|Brazil
ca|كندا|Canada
cl|تشيلي|Chile
cn|الصين|China
co|كولومبيا|Colombia
hr|كرواتيا|Croatia
cu|كوبا|Cuba
cz|التشيك/تشيكيا|Czech Republic/Czechia
dk|الدنمارك|Denmark
eg|مصر|Egypt
et|إثيوبيا|Ethiopia
fi|فنلندا|Finland
fr|فرنسا|France
de|ألمانيا|Germany
gr|اليونان|Greece
hu|المجر/هنغاريا|Hungary
is|آيسلندا|Iceland
in|الهند|India
id|إندونيسيا|Indonesia
ir|إيران|Iran
iq|العراق|Iraq
ie|أيرلندا|Ireland
it|إيطاليا|Italy
jp|اليابان|Japan
jo|الأردن|Jordan
ke|كينيا|Kenya
kp|كوريا الشمالية|North Korea
kr|كوريا الجنوبية/كوريا|South Korea/Korea
kw|الكويت|Kuwait
lb|لبنان|Lebanon
ly|ليبيا|Libya
my|ماليزيا|Malaysia
mr|موريتانيا|Mauritania
mx|المكسيك|Mexico
ma|المغرب|Morocco
nl|هولندا|Netherlands/Holland
nz|نيوزيلندا|New Zealand
ng|نيجيريا|Nigeria
no|النرويج|Norway
om|عمان/سلطنة عمان|Oman
pk|باكستان|Pakistan
ps|فلسطين|Palestine
pe|بيرو|Peru
ph|الفلبين|Philippines
pl|بولندا|Poland
pt|البرتغال|Portugal
qa|قطر|Qatar
ro|رومانيا|Romania
ru|روسيا|Russia
sa|السعودية/المملكة العربية السعودية|Saudi Arabia
rs|صربيا|Serbia
sg|سنغافورة|Singapore
so|الصومال|Somalia
za|جنوب أفريقيا|South Africa
es|إسبانيا|Spain
sd|السودان|Sudan
se|السويد|Sweden
ch|سويسرا|Switzerland
sy|سوريا|Syria
th|تايلاند|Thailand
tn|تونس|Tunisia
tr|تركيا|Turkey
ua|أوكرانيا|Ukraine
ae|الإمارات/الإمارات العربية المتحدة|United Arab Emirates/UAE
gb|بريطانيا/المملكة المتحدة|United Kingdom/UK/Britain
us|أمريكا/الولايات المتحدة/الولايات المتحدة الأمريكية|United States/USA/US/America
uy|الأوروغواي/أوروغواي|Uruguay
ve|فنزويلا|Venezuela
vn|فيتنام|Vietnam
ye|اليمن|Yemen
"""

FLAGS = []  # (الرمز, الاسم العربي, الاسم الإنجليزي, الإجابات المقبولة)
for _line in COUNTRIES_RAW.strip().splitlines():
    _code, _ar, _en = _line.strip().split("|")
    _ar_names = [x.strip() for x in _ar.split("/")]
    _en_names = [x.strip() for x in _en.split("/")]
    _answers = {normalize_answer(x) for x in _ar_names + _en_names}
    FLAGS.append((_code, _ar_names[0], _en_names[0], _answers))


class FlagsGame:
    def __init__(self, channel, starter, rounds):
        self.channel = channel
        self.starter = starter
        self.rounds = rounds
        self.scores = {}   # id اللاعب -> [العضو، النقاط]
        self.task = None
        self.streak_id = None      # مين عنده ستريك حاليًا
        self.streak = 0
        self.best_streak = 0
        self.best_member = None
        self.last_note = ""

    MILESTONES = None   # الألعاب الثانية بتبلش الستريك من STREAK_STEP وبتزيد كل STREAK_STEP

    def add_point(self, member):
        """بيزيد نقطة وبيحدّث الستريك، وبيرجّع نقاط اللاعب"""
        entry = self.scores.setdefault(member.id, [member, 0])
        entry[1] += 1
        if self.streak_id == member.id:
            self.streak += 1
        else:
            self.streak_id = member.id
            self.streak = 1
        if self.streak > self.best_streak:
            self.best_streak = self.streak
            self.best_member = member
        _given, self.last_note = points_db.award(member, 1)   # نقاط السيرفر (مع الحد اليومي)
        return entry[1]

    def streak_message(self, member):
        n = self.streak
        if self.MILESTONES:
            hit = n in self.MILESTONES or (n > max(self.MILESTONES) and n % STREAK_STEP == 0)
        else:
            hit = n >= STREAK_STEP and n % STREAK_STEP == 0
        if hit:
            fire = "🔥" * min(max(n // STREAK_STEP, 1), 3)
            return f"{fire} **ستريك {n}!** {member.mention} جاب {n} ورا بعض!"
        return None

    def extra_lines(self, member):
        """سطور إضافية بعد الإجابة الصح: رسالة الستريك + تنبيه الحد اليومي"""
        out = ""
        bonus = self.streak_message(member)
        if bonus:
            out += "\n" + bonus
        if self.last_note:
            out += "\n" + self.last_note
        return out

    def reset_streak(self):
        self.streak_id = None
        self.streak = 0

    async def run(self):
        ch = self.channel
        await ch.send(
            "🏳️ **لعبة الأعلام!**\n"
            f"{self.rounds} علم، وأسرع واحد بيكتب اسم الدولة بياخد نقطة.\n"
            "بتقدروا تكتبوا بالعربي أو بالإنجليزي.\n"
            f"عندكم **{secs(FLAG_ROUND_TIME)}** لكل علم. جاهزين؟ 🚀"
        )
        await asyncio.sleep(4)

        picked = random.sample(FLAGS, self.rounds)
        for i, (code, ar, en, answers) in enumerate(picked, start=1):
            embed = discord.Embed(
                title=f"🏳️ العلم {i} من {self.rounds}",
                description=f"شو اسم هالدولة؟ لديك {secs(FLAG_ROUND_TIME)}",
                color=discord.Color.blurple(),
            )
            embed.set_image(url=f"https://flagcdn.com/w640/{code}.png")
            sent = await ch.send(embed=embed)

            def check(m):
                return (
                    m.channel == ch
                    and not m.author.bot
                    and normalize_answer(m.content) in answers
                )

            try:
                m = await bot.wait_for("message", check=check, timeout=FLAG_ROUND_TIME)
            except asyncio.TimeoutError:
                self.reset_streak()
                await ch.send(f"⏰ انتهى الوقت! العلم هو **{ar}** ({en})")
            else:
                pts = self.add_point(m.author)
                elapsed = max((m.created_at - sent.created_at).total_seconds(), 0)
                text = (
                    f"✅ برافو {m.author.mention}! العلم هو **{ar}** ({en})\n"
                    f"⏱️ جاوب خلال **{elapsed:.2f}** ثانية\n"
                    f"نقاطك: **{pts}**"
                )
                text += self.extra_lines(m.author)
                await ch.send(text)
            await asyncio.sleep(3)

        await ch.send("🏁 **انتهت اللعبة!**")
        await self.show_scores()

    async def show_scores(self):
        if not self.scores:
            await self.channel.send("ما حدا جاوب ولا سؤال 😅")
            return
        ranking = sorted(self.scores.values(), key=lambda e: -e[1])
        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, (member, pts) in enumerate(ranking):
            prefix = medals[i] if i < 3 else f"{i + 1}."
            lines.append(f"{prefix} {member.mention} — **{pts}** نقطة")
        text = "📊 **النتائج:**\n" + "\n".join(lines)
        if self.best_streak >= 3:
            text += (
                f"\n\n🔥 أطول ستريك: {self.best_member.mention} "
                f"(**{self.best_streak}** ورا بعض)"
            )
        await self.channel.send(text)


# ================= لعبة الماركات =================
# اسم ملف الصورة (بدون الامتداد) هو الإجابة الصحيحة، مثلًا: nike.png أو نايك.png
# المجموعات هون هي أسماء بديلة: إذا اسم ملفك طابق أي اسم بالمجموعة،
# كل أسماء المجموعة بتنقبل كإجابة. ضيف مجموعات جديدة متل ما بدك.
BRAND_GROUPS = [
    ["apple", "ابل", "آبل"],
    ["nike", "نايك", "نايكي"],
    ["adidas", "اديداس", "أديداس"],
    ["puma", "بوما"],
    ["reebok", "ريبوك"],
    ["lacoste", "لاكوست"],
    ["gucci", "غوتشي", "جوتشي", "قوتشي"],
    ["chanel", "شانيل"],
    ["rolex", "رولكس"],
    ["samsung", "سامسونج", "سامسونغ"],
    ["huawei", "هواوي"],
    ["xiaomi", "شاومي"],
    ["sony", "سوني"],
    ["intel", "انتل"],
    ["nvidia", "انفيديا"],
    ["google", "جوجل", "غوغل"],
    ["microsoft", "مايكروسوفت", "ميكروسوفت"],
    ["amazon", "امازون"],
    ["facebook", "فيسبوك", "فيس بوك", "فيس", "فايسبوك"],
    ["instagram", "انستغرام", "انستجرام", "انستقرام", "انستا"],
    ["youtube", "يوتيوب", "يوتوب"],
    ["twitter", "تويتر", "x", "اكس"],
    ["whatsapp", "واتساب", "واتس اب", "واتس"],
    ["telegram", "تيليجرام", "تيليغرام", "تلغرام", "تلجرام"],
    ["snapchat", "سناب شات", "سناب", "سنابشات", "سنابتشات"],
    ["tiktok", "تيك توك", "تيكتوك"],
    ["netflix", "نتفلكس", "نتفليكس", "نيتفليكس"],
    ["spotify", "سبوتيفاي", "سبوتفاي", "سبوتيفاى"],
    ["discord", "ديسكورد", "دسكورد"],
    ["playstation", "بلايستيشن", "بلاي ستيشن"],
    ["xbox", "اكس بوكس"],
    ["nintendo", "نينتندو"],
    ["lego", "ليغو", "ليجو"],
    ["mcdonalds", "mcdonald's", "ماكدونالدز", "ماكدونالد", "ماك دونالدز", "ماكدونالز", "ماك"],
    ["kfc", "كنتاكي", "كي اف سي"],
    ["burger king", "برجر كنج", "برغر كنغ", "برجر كينج"],
    ["starbucks", "ستاربكس", "ستاربوكس", "ستار بكس"],
    ["pizza hut", "بيتزا هت"],
    ["dominos", "domino's", "دومينوز", "دومينوس", "دومينو"],
    ["subway", "صب واي", "صبواي"],
    ["pepsi", "بيبسي"],
    ["coca cola", "coca-cola", "cocacola", "كوكاكولا", "كوكا كولا", "كوكا"],
    ["red bull", "ريد بول"],
    ["oreo", "اوريو"],
    ["nestle", "نستله", "نيستله"],
    ["toyota", "تويوتا"],
    ["honda", "هوندا"],
    ["hyundai", "هيونداي"],
    ["ford", "فورد"],
    ["bmw", "بي ام دبليو", "بي ام"],
    ["mercedes", "مرسيدس", "mercedes-benz"],
    ["ferrari", "فيراري"],
    ["lamborghini", "لامبورغيني", "لامبورجيني"],
    ["ikea", "ايكيا"],
    ["visa", "فيزا"],
    ["paypal", "باي بال", "بايبال"],
    ["uber", "اوبر"],
    ["pringles", "برينجلز", "برنجلز", "برينغلز"],
    ["target", "تارجت", "تارغت"],
    ["taco bell", "تاكو بيل", "تاكوبيل"],
    ["tesla", "تسلا", "تيسلا"],
    ["steam", "ستيم", "ستييم"],
]
BRAND_GROUPS_NORM = [{normalize_answer(x) for x in g} for g in BRAND_GROUPS]
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")


def load_brands():
    """بيقرا صور مجلد brands كل مرة بتبدأ لعبة، فبتقدر تضيف صور بدون ما توقف البوت"""
    brands = []
    for fname in sorted(os.listdir(BRANDS_DIR)):
        stem, ext = os.path.splitext(fname)
        if ext.lower() not in IMAGE_EXTS:
            continue
        answers = {normalize_answer(stem)}
        display = stem
        for group, norm in zip(BRAND_GROUPS, BRAND_GROUPS_NORM):
            if answers & norm:
                answers |= norm
                ar = next((x for x in group if re.search(r"[\u0600-\u06FF]", x)), None)
                if ar and normalize_answer(ar) != normalize_answer(stem):
                    display = f"{stem} ({ar})"
        # نقبل كمان الإجابة بدون مسافات (pizzahut / cocacola / بيتزاهت)
        answers |= {a.replace(" ", "") for a in answers}
        brands.append((os.path.join(BRANDS_DIR, fname), display, ext.lower(), answers))
    return brands


class BrandsGame(FlagsGame):
    def __init__(self, channel, starter, brands):
        super().__init__(channel, starter, 0)
        self.brands = brands

    async def run(self):
        ch = self.channel
        await ch.send(
            "🛍️ **لعبة الماركات!**\n"
            "أسرع واحد بيكتب اسم الماركة بياخد نقطة، وبتقدروا تكتبوا بالعربي أو بالإنجليزي.\n"
            f"عندكم **{secs(BRAND_ROUND_TIME)}** لكل ماركة، واللعبة بتضل شغالة لحد ما توقفوها بـ `!stop` 😉\n"
            "جاهزين؟ 🚀"
        )
        await asyncio.sleep(4)

        recent = []   # آخر الماركات اللي انسألت
        while True:
            # اختيار عشوائي بحت من الماركات اللي ما انسألت مؤخرًا
            pool = [b for b in self.brands if b not in recent]
            brand = random.choice(pool)
            recent.append(brand)
            if len(recent) > min(NO_REPEAT_LAST, len(self.brands) // 2):
                recent.pop(0)
            path, name, ext, answers = brand

            embed = discord.Embed(
                title="🛍️ ما اسم هذه الماركة؟",
                description=f"لديك {secs(BRAND_ROUND_TIME)} للإجابة",
                color=discord.Color.orange(),
            )
            embed.set_image(url=f"attachment://logo{ext}")
            embed.set_footer(
                text=f"تم الطلب بواسطة {self.starter.display_name}",
                icon_url=self.starter.display_avatar.url,
            )
            sent = await ch.send(embed=embed, file=discord.File(path, filename=f"logo{ext}"))

            def check(m):
                if m.channel != ch or m.author.bot:
                    return False
                t = normalize_answer(m.content)
                return t in answers or t.replace(" ", "") in answers

            try:
                m = await bot.wait_for("message", check=check, timeout=BRAND_ROUND_TIME)
            except asyncio.TimeoutError:
                self.reset_streak()
                await ch.send(f"⏰ انتهى الوقت وما حدا عرفها! الماركة هي **{name}**")
                await asyncio.sleep(3)
                continue

            pts = self.add_point(m.author)
            elapsed = max((m.created_at - sent.created_at).total_seconds(), 0)
            text = (
                f"✅ برافو {m.author.mention}! الماركة هي **{name}**\n"
                f"⏱️ جاوب خلال **{elapsed:.2f}** ثانية\n"
                f"نقاطك: **{pts}**"
            )
            text += self.extra_lines(m.author)
            await ch.send(text)
            await asyncio.sleep(3)



# ================= لعبة العواصم =================
# الشكل: اسم الدولة|العاصمة بالعربي|العاصمة بالإنجليزي (الفاصل بين أكثر من اسم هو /)
# أول اسم هو اللي بيظهر بالإجابة، والباقي أسماء بديلة بتنقبل كإجابة.
# الدول: أوروبا + أفريقيا العربية + أمريكا الشمالية والجنوبية + آسيا (المشهورة بس، وبدون الجزر الصغيرة).
# لحذف دولة امسح سطرها، ولإضافة دولة زيد سطر جديد.
CAPITALS_RAW = """
النمسا|فيينا|Vienna
بلجيكا|بروكسل|Brussels
البوسنة والهرسك|سراييفو/سرايفو|Sarajevo
بلغاريا|صوفيا|Sofia
كرواتيا|زغرب|Zagreb
التشيك|براغ|Prague
الدنمارك|كوبنهاغن/كوبنهاجن|Copenhagen
فنلندا|هلسنكي|Helsinki
فرنسا|باريس|Paris
ألمانيا|برلين|Berlin
اليونان|أثينا|Athens
المجر|بودابست|Budapest
أيرلندا|دبلن|Dublin
إيطاليا|روما|Rome
هولندا|أمستردام|Amsterdam
النرويج|أوسلو|Oslo
بولندا|وارسو|Warsaw
البرتغال|لشبونة|Lisbon
رومانيا|بوخارست|Bucharest
روسيا|موسكو|Moscow
صربيا|بلغراد|Belgrade
إسبانيا|مدريد|Madrid
السويد|ستوكهولم|Stockholm
سويسرا|برن|Bern/Berne
أوكرانيا|كييف|Kyiv/Kiev
المملكة المتحدة|لندن|London
مصر|القاهرة|Cairo
ليبيا|طرابلس|Tripoli
تونس|تونس|Tunis
الجزائر|الجزائر/الجزائر العاصمة|Algiers
المغرب|الرباط|Rabat
السودان|الخرطوم|Khartoum
موريتانيا|نواكشوط|Nouakchott
الصومال|مقديشو|Mogadishu
جيبوتي|جيبوتي/مدينة جيبوتي|Djibouti
كندا|أوتاوا|Ottawa
الولايات المتحدة الأمريكية|واشنطن/واشنطن العاصمة|Washington/Washington DC/Washington D.C.
المكسيك|مكسيكو سيتي/مكسيكو/مدينة المكسيك|Mexico City
بنما|مدينة بنما/بنما|Panama City/Panama
كوبا|هافانا|Havana
الأرجنتين|بوينس آيرس/بوينس ايرس|Buenos Aires
البرازيل|برازيليا|Brasilia
تشيلي|سانتياغو/سانتياجو|Santiago
كولومبيا|بوغوتا/بوجوتا|Bogota
الإكوادور|كيتو|Quito
بيرو|ليما|Lima
الأوروغواي|مونتيفيديو|Montevideo
فنزويلا|كاراكاس|Caracas
السعودية|الرياض|Riyadh
الإمارات العربية المتحدة|أبو ظبي|Abu Dhabi
قطر|الدوحة|Doha
الكويت|مدينة الكويت/الكويت|Kuwait City/Kuwait
البحرين|المنامة|Manama
سلطنة عمان|مسقط|Muscat
اليمن|صنعاء|Sanaa/Sana'a
العراق|بغداد|Baghdad
سوريا|دمشق|Damascus
لبنان|بيروت|Beirut
الأردن|عمّان|Amman
فلسطين|القدس/القدس الشرقية|Jerusalem
إيران|طهران|Tehran
تركيا|أنقرة|Ankara
أفغانستان|كابول|Kabul
باكستان|إسلام آباد|Islamabad
الهند|نيودلهي/دلهي|New Delhi/Delhi
نيبال|كاتماندو|Kathmandu
بنغلاديش|دكا|Dhaka
تايلاند|بانكوك|Bangkok
فيتنام|هانوي|Hanoi
ماليزيا|كوالالمبور|Kuala Lumpur
إندونيسيا|جاكرتا|Jakarta
الفلبين|مانيلا|Manila
الصين|بكين|Beijing/Peking
اليابان|طوكيو|Tokyo
كوريا الجنوبية|سيول|Seoul
كوريا الشمالية|بيونغ يانغ/بيونغيانغ|Pyongyang
"""

CAPITALS = []  # (الدولة, العاصمة بالعربي, العاصمة بالإنجليزي, الإجابات المقبولة)
for _line in CAPITALS_RAW.strip().splitlines():
    _country, _ar, _en = _line.strip().split("|")
    _ar_names = [x.strip() for x in _ar.split("/")]
    _en_names = [x.strip() for x in _en.split("/")]
    _answers = {normalize_answer(x) for x in _ar_names + _en_names}
    _answers |= {a.replace(" ", "") for a in _answers}   # نقبل الإجابة بدون مسافات كمان
    CAPITALS.append((_country, _ar_names[0], _en_names[0], _answers))

# أسماء دول بتبدأ بكلمة منها، فما منحط قبلها كلمة "دولة"
_NO_DAWLA = ("جمهورية", "جزر", "الولايات", "المملكة", "سلطنة")


class CapitalsGame(FlagsGame):
    async def run(self):
        ch = self.channel
        await ch.send(
            "🏙️ **لعبة العواصم!**\n"
            f"{self.rounds} أسئلة، وأسرع واحد بيكتب عاصمة الدولة بياخد نقطة.\n"
            "بتقدروا تكتبوا بالعربي أو بالإنجليزي. جاهزين؟ 🚀"
        )
        await asyncio.sleep(4)

        picked = random.sample(CAPITALS, self.rounds)
        for i, (country, cap_ar, cap_en, answers) in enumerate(picked, start=1):
            name = country if country.startswith(_NO_DAWLA) else f"دولة {country}"
            embed = discord.Embed(
                description=(
                    f"# 🏙️ ما هي عاصمة {name}؟\n\n"
                    f"⏳ لديك {secs(CAPITAL_ROUND_TIME)}  •  السؤال {i} من {self.rounds}"
                ),
                color=discord.Color.teal(),
            )
            embed.set_footer(
                text=f"تم الطلب بواسطة {self.starter.display_name}",
                icon_url=self.starter.display_avatar.url,
            )
            sent = await ch.send(embed=embed)

            def check(m):
                if m.channel != ch or m.author.bot:
                    return False
                t = normalize_answer(m.content)
                return t in answers or t.replace(" ", "") in answers

            try:
                m = await bot.wait_for("message", check=check, timeout=CAPITAL_ROUND_TIME)
            except asyncio.TimeoutError:
                self.reset_streak()
                await ch.send(f"⏰ انتهى الوقت! عاصمة {country} هي **{cap_ar}** ({cap_en})")
            else:
                pts = self.add_point(m.author)
                elapsed = max((m.created_at - sent.created_at).total_seconds(), 0)
                text = (
                    f"✅ برافو {m.author.mention}! عاصمة {country} هي **{cap_ar}** ({cap_en})\n"
                    f"⏱️ جاوب خلال **{elapsed:.2f}** ثانية\n"
                    f"نقاطك: **{pts}**"
                )
                text += self.extra_lines(m.author)
                await ch.send(text)
            await asyncio.sleep(3)

        await ch.send("🏁 **انتهت اللعبة!**")
        await self.show_scores()


# ================= لعبة الرياضيات =================
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def parse_int_answer(text):
    """بيقبل الأرقام العربية والإنجليزية، والسالب"""
    t = text.strip().translate(_AR_DIGITS).replace("−", "-").replace("–", "-").replace(" ", "")
    return int(t) if re.fullmatch(r"-?\d{1,12}", t) else None


def _num():
    """أرقام صغيرة وسهلة"""
    r = random.random()
    if r < 0.6:
        return random.randint(2, 20)
    return random.randint(15, 60)


def make_math_question():
    """بيرجّع (نص المعادلة، الجواب الصحيح): أسئلة سهلة بأرقام صغيرة (جمع، طرح، ضرب، قسمة، أس)"""
    kind = random.choices(["add", "sub", "mul", "div", "pow"], weights=[22, 22, 22, 20, 14])[0]
    if kind == "add":
        a, b = _num(), _num()
        return f"{a} + {b}", a + b
    if kind == "sub":
        a, b = _num(), _num()
        if a < b:
            a, b = b, a
        if a == b:
            a += random.randint(1, 9)
        return f"{a} - {b}", a - b
    if kind == "mul":
        a, b = random.randint(2, 9), random.randint(2, 9)
        if random.random() < 0.15:
            a = random.randint(10, 12)
        return f"{a} × {b}", a * b
    if kind == "div":
        b, q = random.randint(2, 9), random.randint(2, 10)
        return f"{b * q} / {b}", q
    r = random.random()
    if r < 0.65:
        base, e = random.randint(2, 10), 2
    elif r < 0.85:
        base, e = random.randint(2, 4), 3
    else:
        base, e = 2, random.randint(4, 6)
    return f"{base}^{e}", base ** e


class MathGame(FlagsGame):
    MILESTONES = (3, 5, 10, 15)             # الستريك: 3 - 5 - 10 - 15 وبعدها كل 5

    def __init__(self, channel, starter):
        super().__init__(channel, starter, 0)

    async def run(self):
        ch = self.channel
        await ch.send(
            "🧮 **لعبة الرياضيات!**\n"
            f"حلوا المعادلة بأسرع وقت، وأول واحد بيكتب الجواب الصح بياخد نقطة. عندكم **{secs(MATH_ROUND_TIME)}** لكل سؤال.\n"
            "الأسئلة ما بتخلص لحد ما توقفوها بـ `!stop`. جاهزين؟ 🚀"
        )
        await asyncio.sleep(4)

        while True:
            expr, answer = make_math_question()
            embed = discord.Embed(
                title="حل المعادلة التالية",
                description=f"لديك {secs(MATH_ROUND_TIME)}",
                color=discord.Color.green(),
            )
            file = None
            if Image is not None:
                try:
                    file = discord.File(make_math_image(expr), filename="math.png")
                    embed.set_image(url="attachment://math.png")
                except Exception as e:
                    print("Math image error:", e)
            if file is None:
                embed.description += f"\n# {expr}"
            embed.set_footer(
                text=f"تم الطلب بواسطة {self.starter.display_name}",
                icon_url=self.starter.display_avatar.url,
            )
            sent = await ch.send(embed=embed, file=file) if file else await ch.send(embed=embed)

            def check(m):
                return m.channel == ch and not m.author.bot and parse_int_answer(m.content) == answer

            try:
                m = await bot.wait_for("message", check=check, timeout=MATH_ROUND_TIME)
            except asyncio.TimeoutError:
                self.reset_streak()
                await ch.send(f"⏰ انتهى الوقت! الجواب هو **{answer}**")
            else:
                pts = self.add_point(m.author)
                elapsed = max((m.created_at - sent.created_at).total_seconds(), 0)
                text = (
                    f"✅ برافو {m.author.mention}! الجواب هو **{answer}**\n"
                    f"⏱️ جاوب خلال **{elapsed:.2f}** ثانية\n"
                    f"نقاطك: **{pts}**"
                )
                text += self.extra_lines(m.author)
                await ch.send(text)
            await asyncio.sleep(2)


# ================= لعبة XO (بالأزرار: كبّس على الخانة اللي بدك ياها) =================
XO_LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]
XO_EMOJI = {"X": "❌", "O": "⭕"}


def xo_winner(board):
    """بيرجّع (X أو O، الخط الفايز) أو (None, None)"""
    for line in XO_LINES:
        a, b, c = line
        if board[a] and board[a] == board[b] == board[c]:
            return board[a], line
    return None, None


class XOGame:
    def __init__(self, channel, starter, challenged=None):
        self.channel = channel
        self.starter = starter
        self.challenged = challenged     # إذا حدا تحدّى عضو معيّن
        self.opponent = None
        self.joining = True
        self.board = [None] * 9
        self.task = None
        self.players = {}                # "X"/"O" -> العضو
        self.turn = "X"
        self.playing = False
        self.move = None                 # آخر حركة: رقم الخانة أو "forfeit"
        self.mover = None
        self.joined_event = asyncio.Event()
        self.move_event = asyncio.Event()
        self.msg = None
        self.view = None

    # ---------- الدخول ----------
    async def _try_join(self, who):
        """بيرجّع نص خطأ إذا ما قدر يدخل، أو None إذا انضاف"""
        if not self.joining:
            return "ما في تسجيل مفتوح حاليًا."
        if who.id == self.starter.id:
            return "ما بتقدر تلعب ضد حالك! استنى حدا يقبل التحدي."
        if getattr(who, "bot", False):
            return "البوتات ما بتلعب XO 🤖"
        if self.challenged is not None and who.id != self.challenged.id:
            return f"هالتحدي مو إلك، بس {self.challenged.display_name} بيقدر يقبله."
        self.opponent = who
        self.joining = False
        self.joined_event.set()
        return None

    async def join(self, ctx):
        """بينندهي من !دخول و !قبول"""
        err = await self._try_join(ctx.author)
        if err:
            if getattr(ctx.author, "bot", False):
                return
            await ctx.send(err)
            return
        await ctx.send(f"✅ {ctx.author.mention} قبل التحدي!")

    def _lobby_view(self):
        view = discord.ui.View(timeout=None)
        btn = discord.ui.Button(style=discord.ButtonStyle.success, label="قبول التحدي", emoji="⚔️")

        async def cb(interaction):
            err = await self._try_join(interaction.user)
            if err:
                await interaction.response.send_message(err, ephemeral=True)
                return
            await interaction.response.defer()
            await self.channel.send(f"✅ {interaction.user.mention} قبل التحدي!")

        btn.callback = cb
        view.add_item(btn)
        return view

    # ---------- اللوحة ----------
    def _build_view(self, win_line=None, finished=False):
        view = discord.ui.View(timeout=None)
        for i in range(9):
            mark = self.board[i]
            if mark:
                style = discord.ButtonStyle.success if (win_line and i in win_line) else (
                    discord.ButtonStyle.danger if mark == "X" else discord.ButtonStyle.primary)
                btn = discord.ui.Button(style=style, emoji=XO_EMOJI[mark], row=i // 3, disabled=True)
            else:
                btn = discord.ui.Button(style=discord.ButtonStyle.secondary, label="​", row=i // 3,
                                        disabled=finished)
            btn.callback = self._make_cell_cb(i)
            view.add_item(btn)
        ff = discord.ui.Button(style=discord.ButtonStyle.secondary, label="انسحاب", emoji="🏳️", row=3, disabled=finished)
        ff.callback = self._forfeit_cb
        view.add_item(ff)
        return view

    def _make_cell_cb(self, i):
        async def cb(interaction):
            await self.handle_click(interaction, i)
        return cb

    async def _forfeit_cb(self, interaction):
        await self.handle_click(interaction, "forfeit")

    async def handle_click(self, interaction, cell):
        who = interaction.user
        if not self.playing:
            await interaction.response.send_message("اللعبة خلصت.", ephemeral=True)
            return
        if who.id not in (p.id for p in self.players.values()):
            await interaction.response.send_message("إنت مو من اللاعبين بهالجولة 🙂", ephemeral=True)
            return
        if cell == "forfeit":
            self.mover, self.move = who, "forfeit"
            await interaction.response.defer()
            self.move_event.set()
            return
        if who.id != self.players[self.turn].id:
            await interaction.response.send_message("مو دورك! استنى خصمك.", ephemeral=True)
            return
        if self.board[cell] is not None:
            await interaction.response.send_message("هالخانة مشغولة.", ephemeral=True)
            return
        if self.move is not None:
            await interaction.response.send_message("استنى لحظة...", ephemeral=True)
            return
        self.mover, self.move = who, cell
        await interaction.response.defer()
        self.move_event.set()

    def _turn_text(self):
        cur = self.players[self.turn]
        return f"{XO_EMOJI[self.turn]} دور {cur.mention} — كبّس على الخانة اللي بدك ياها ({secs(XO_TURN_TIME)})"

    async def _show(self, text, win_line=None, finished=False):
        self.view = self._build_view(win_line, finished)
        try:
            if self.msg is None:
                self.msg = await self.channel.send(text, view=self.view)
            else:
                await self.msg.edit(content=text, view=self.view)
        except Exception as e:
            print("XO board error:", e)

    # ---------- اللعبة ----------
    async def run(self):
        ch = self.channel
        if self.challenged is not None:
            text = (f"❌⭕ **XO!** {self.starter.mention} تحدّى {self.challenged.mention}\n"
                    f"كبّس **قبول التحدي** أو اكتب `!قبول` خلال {secs(XO_JOIN_TIME)}.")
        else:
            text = (f"❌⭕ **XO!** {self.starter.mention} بدو حدا يلعب معه\n"
                    f"كبّس **قبول التحدي** أو اكتب `!دخول` خلال {secs(XO_JOIN_TIME)}.")
        lobby = await ch.send(text, view=self._lobby_view())
        try:
            await asyncio.wait_for(self.joined_event.wait(), XO_JOIN_TIME)
        except asyncio.TimeoutError:
            pass
        self.joining = False
        try:
            await lobby.edit(view=None)
        except Exception:
            pass
        if self.opponent is None:
            await ch.send("❌ ما حدا قبل التحدي، انلغت اللعبة.")
            return

        order = [self.starter, self.opponent]
        random.shuffle(order)
        self.players = {"X": order[0], "O": order[1]}
        self.playing = True
        winner = None
        reason = ""
        try:
            await ch.send(f"🎮 بلشت اللعبة!  ❌ {self.players['X'].mention}   ضد   ⭕ {self.players['O'].mention}")
            await self._show(self._turn_text())
            while True:
                cur = self.players[self.turn]
                other = self.players["O" if self.turn == "X" else "X"]
                self.move, self.mover = None, None
                self.move_event.clear()
                try:
                    await asyncio.wait_for(self.move_event.wait(), XO_TURN_TIME)
                except asyncio.TimeoutError:
                    winner, reason = other, f"⏰ انتهى وقت {cur.mention}!"
                    break
                if self.move == "forfeit":
                    loser = self.mover
                    winner = self.players["O"] if loser.id == self.players["X"].id else self.players["X"]
                    reason = f"🏳️ {loser.display_name} انسحب!"
                    break
                self.board[self.move] = self.turn
                mark, line = xo_winner(self.board)
                if mark:
                    winner, reason = cur, ""
                    await self._show(f"🏆 {XO_EMOJI[mark]} خلصت!", win_line=line, finished=True)
                    break
                if all(self.board):
                    self.playing = False
                    await self._show("🤝 تعادل! ما حدا فاز.", finished=True)
                    return
                self.turn = "O" if self.turn == "X" else "X"
                await self._show(self._turn_text())
        finally:
            self.playing = False

        if not (self.board and xo_winner(self.board)[0]):
            await self._show(reason or "انتهت اللعبة", finished=True)
        text = (reason + "\n" if reason else "") + f"🎉 الفايز هو {winner.mention}! مبروك"
        if XO_WIN_POINTS > 0:
            given, note = points_db.award(winner, XO_WIN_POINTS)
            text += f"\n💰 **+{given}** نقاط"
            if note:
                text += "\n" + note
        await ch.send(text)


# ================= الأوامر =================
@bot.command(name="روليت")
async def roulette(ctx):
    if channel_busy(ctx.channel.id):
        await ctx.send("⚠️ في لعبة شغالة بهالروم.")
        return

    game = RouletteGame(ctx.channel, ctx.author)
    game.task = asyncio.current_task()
    active_games[ctx.channel.id] = game
    try:
        await game.run()
    except asyncio.CancelledError:
        await ctx.send("🛑 تم إيقاف الروليت.")
    finally:
        active_games.pop(ctx.channel.id, None)


@bot.command(name="دخول", aliases=["قبول"])
async def join(ctx):
    game = active_xo.get(ctx.channel.id)
    if game is not None:
        await game.join(ctx)
        return
    game = active_games.get(ctx.channel.id)
    if game is None or not game.joining:
        await ctx.send("ما في تسجيل مفتوح حاليًا.")
        return
    if game.has_joined(ctx.author):
        await ctx.send("إنت مسجل أصلًا!")
        return
    if len(game.players) >= MAX_PLAYERS:
        await ctx.send("اللعبة امتلت.")
        return

    num = game.add_player(ctx.author)
    await ctx.send(f"✅ {ctx.author.mention} دخل برقم **{num}**")
    await game.refresh_intro()


@bot.command(name="اعلام", aliases=["أعلام"])
async def flags(ctx, rounds: int = FLAG_DEFAULT_ROUNDS):
    if channel_busy(ctx.channel.id):
        await ctx.send("⚠️ في لعبة شغالة بهالروم.")
        return

    rounds = max(1, min(rounds, FLAG_MAX_ROUNDS))
    game = FlagsGame(ctx.channel, ctx.author, rounds)
    game.task = asyncio.current_task()
    active_flags[ctx.channel.id] = game
    try:
        await game.run()
    except asyncio.CancelledError:
        await ctx.send("🛑 تم إيقاف لعبة الأعلام.")
        await game.show_scores()
    finally:
        active_flags.pop(ctx.channel.id, None)


@bot.command(name="stop", aliases=["ايقاف", "إيقاف"])
@commands.guild_only()
async def stop_flags(ctx):
    game = get_game(ctx.channel.id)
    if game is None:
        await ctx.send("ما في لعبة شغالة بهالروم.")
        return
    opp = getattr(game, "opponent", None)
    if ctx.author.id != game.starter.id and not (opp and ctx.author.id == opp.id) \
            and not ctx.author.guild_permissions.manage_messages:
        await ctx.send("بس صاحب اللعبة أو الأدمن بيقدر يوقفها.")
        return
    game.task.cancel()


@bot.command(name="ماركات", aliases=["ماركة", "ماركه"])
async def brands_game(ctx):
    if channel_busy(ctx.channel.id):
        await ctx.send("⚠️ في لعبة شغالة بهالروم.")
        return

    brands = load_brands()
    if not brands:
        await ctx.send(
            "❌ ما لقيت صور بمجلد `brands`.\n"
            f"حط صور الشعارات هون: `{BRANDS_DIR}`\n"
            "واسم كل ملف هو اسم الماركة، مثال: `nike.png`"
        )
        return

    game = BrandsGame(ctx.channel, ctx.author, brands)
    game.task = asyncio.current_task()
    active_brands[ctx.channel.id] = game
    try:
        await game.run()
    except asyncio.CancelledError:
        await ctx.send("🛑 تم إيقاف لعبة الماركات.")
        await game.show_scores()
    finally:
        active_brands.pop(ctx.channel.id, None)


@bot.command(name="عواصم", aliases=["عاصمة", "عاصمه"])
async def capitals_game(ctx):
    if channel_busy(ctx.channel.id):
        await ctx.send("⚠️ في لعبة شغالة بهالروم.")
        return

    game = CapitalsGame(ctx.channel, ctx.author, CAPITAL_ROUNDS)
    game.task = asyncio.current_task()
    active_flags[ctx.channel.id] = game   # الأعلام والعواصم بيشاركوا نفس القائمة (لعبة وحدة بالروم)
    try:
        await game.run()
    except asyncio.CancelledError:
        await ctx.send("🛑 تم إيقاف لعبة العواصم.")
        await game.show_scores()
    finally:
        active_flags.pop(ctx.channel.id, None)


@bot.command(name="رياضيات", aliases=["حساب", "math"])
async def math_game(ctx):
    if channel_busy(ctx.channel.id):
        await ctx.send("⚠️ في لعبة شغالة بهالروم.")
        return

    game = MathGame(ctx.channel, ctx.author)
    game.task = asyncio.current_task()
    active_flags[ctx.channel.id] = game   # كل ألعاب الأسئلة بتشارك نفس القائمة (لعبة وحدة بالروم)
    try:
        await game.run()
    except asyncio.CancelledError:
        await ctx.send("🛑 تم إيقاف لعبة الرياضيات.")
        await game.show_scores()
    finally:
        active_flags.pop(ctx.channel.id, None)


@bot.command(name="xo", aliases=["اكسو", "اكس_او", "tictactoe"])
async def xo_cmd(ctx, opponent: discord.Member = None):
    if channel_busy(ctx.channel.id):
        await ctx.send("⚠️ في لعبة شغالة بهالروم.")
        return
    if opponent is not None:
        if opponent.id == ctx.author.id:
            await ctx.send("ما بتقدر تتحدى حالك 😅")
            return
        if getattr(opponent, "bot", False):
            await ctx.send("البوتات ما بتلعب XO 🤖")
            return

    game = XOGame(ctx.channel, ctx.author, opponent)
    game.task = asyncio.current_task()
    active_xo[ctx.channel.id] = game
    try:
        await game.run()
    except asyncio.CancelledError:
        await ctx.send("🛑 تم إيقاف لعبة XO.")
    finally:
        active_xo.pop(ctx.channel.id, None)


@bot.command(name="العاب", aliases=["ألعاب", "الألعاب", "الالعاب", "games", "game"])
async def games_list(ctx):
    if os.path.exists(GAMES_IMAGE):
        await ctx.send(file=discord.File(GAMES_IMAGE, filename="games.png"))
        return
    embed = discord.Embed(title=f"🎮 ألعاب {SERVER_NAME}", color=discord.Color.teal())
    embed.description = (
        "1- روليت: `!روليت`\n"
        "2- أعلام: `!اعلام`\n"
        "3- عواصم: `!عواصم`\n"
        "4- ماركات: `!ماركات`\n"
        "5- رياضيات: `!رياضيات`\n"
        "6- XO: `!xo` أو `!xo @صديقك`\n\n"
        "🏆 أفضل 10 لاعبين: `!توب`  •  نقاطك: `!نقاطي`\n"
        "🛑 لإيقاف اللعبة: `!stop`"
    )
    embed.set_footer(text="لعرض صورة الألعاب حط games.png جنب main.py")
    await ctx.send(embed=embed)


async def _display_info(ctx, uid, stored):
    """بيرجّع (الاسم، بايتات الصورة) للاعب، من السيرفر إذا أمكن وإلا من المحفوظ"""
    member = None
    if ctx.guild:
        member = ctx.guild.get_member(int(uid))
        if member is None:
            try:
                member = await ctx.guild.fetch_member(int(uid))
            except Exception:
                member = None
    name = member.display_name if member else stored.get("name") or "لاعب"
    avatar = None
    if member:
        try:
            avatar = await member.display_avatar.replace(size=128, format="png").read()
        except Exception:
            avatar = None
    return name, avatar


@bot.command(name="توب", aliases=["top"])
async def top_cmd(ctx):
    count = max(1, min(TOP_COUNT, 10))
    rows = points_db.top(count)
    if not rows:
        await ctx.send("ما حدا جمع نقاط لسا! العبوا وجمعوا نقاط 🎮")
        return

    entries = []
    for uid, data in rows:
        name, avatar = await _display_info(ctx, uid, data)
        entries.append((clean_name(name), data["total"], avatar))

    viewer_avatar = None
    try:
        viewer_avatar = await ctx.author.display_avatar.replace(size=128, format="png").read()
    except Exception:
        pass
    footer_extra = ""
    rank = points_db.rank_of(ctx.author.id)
    if rank and rank > count:
        footer_extra = f"ترتيبك: {rank} • {points_db.get(ctx.author.id)['total']} نقطة"

    err_note = "" if Image is not None else "\n⚠️ (مكتبة Pillow مو منصّبة، نزّلها: pip install pillow)"
    if Image is not None:
        try:
            loop = asyncio.get_running_loop()
            buf = await loop.run_in_executor(None, make_top_image, entries, SERVER_NAME, viewer_avatar, footer_extra)
            await ctx.send(file=discord.File(buf, filename="top.png"))
            return
        except Exception as e:
            import traceback
            traceback.print_exc()
            print("Top image error:", repr(e))
            err_note = f"\n⚠️ (ما انرسمت الصورة: {type(e).__name__}: {str(e)[:120]})"

    medals = ["🥇", "🥈", "🥉"] + [f"{i}." for i in range(4, 11)]
    lines = [f"{medals[i]} **{n}** — المستوى {level_of(p)} | {p} نقطة" for i, (n, p, _) in enumerate(entries)]
    await ctx.send(f"🏆 **قائمة المتصدرين في {SERVER_NAME}:**\n" + "\n".join(lines) + err_note)


@bot.command(name="نقاطي", aliases=["نقاط", "points"])
async def my_points(ctx):
    info = points_db.get(ctx.author.id)
    rank = points_db.rank_of(ctx.author.id)
    text = (
        f"💰 {ctx.author.mention} مجموع نقاطك: **{info['total']}**  •  المستوى **{level_of(info['total'])}**\n"
        f"📅 اليوم: **{info['daily']}/{DAILY_LIMIT}**"
    )
    if rank:
        text += f"\n🏆 ترتيبك بالسيرفر: **{rank}**"
    await ctx.send(text)


@bot.event
async def on_ready():
    print("Bot is ready:", bot.user)


@bot.event
async def on_command_error(ctx, error):
    # أوامر اللعبة (!طرد / !انعاش / !انسحاب) بتنقرا داخل الدور، فنتجاهل CommandNotFound
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.BadArgument):
        cmd = getattr(ctx, "command", None)
        if getattr(cmd, "name", "") == "xo":
            await ctx.send("منشن العضو اللي بدك تتحداه، مثلًا: `!xo @صديقك`")
        else:
            await ctx.send("اكتب عدد الأعلام كرقم، مثلًا: `!اعلام 10`")
        return
    print("Error:", error)



bot.run(os.getenv("DISCORD_TOKEN"))
