import asyncio
import os
import random
import re

import discord
from discord.ext import commands

# ============ الإعدادات ============
TOKEN = "ضع_التوكن_هنا"
PREFIX = "!"

JOIN_TIME = 30      # مدة التسجيل بالثواني
TURN_TIME = 30      # مدة دور اللاعب بالثواني
MIN_PLAYERS = 3     # أقل عدد لاعبين
MAX_PLAYERS = 30    # أكبر عدد لاعبين

FLAG_ROUND_TIME = 20       # مدة كل علم بالثواني
FLAG_DEFAULT_ROUNDS = 10   # عدد الأعلام بالجولة إذا ما حددت
FLAG_MAX_ROUNDS = 30       # أكبر عدد أعلام بالجولة

BRAND_ROUND_TIME = 15      # مدة كل ماركة بالثواني

STREAK_STEP = 5            # كل كم إجابة ورا بعض بتطلع رسالة ستريك (5-10-15...)

# مجلد صور الشعارات (بينعمل لحاله جنب main.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BRANDS_DIR = os.path.join(BASE_DIR, "brands")
os.makedirs(BRANDS_DIR, exist_ok=True)
# ===================================

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None, case_insensitive=True)

# كل روم فيها لعبة وحدة بنفس الوقت
active_games = {}
active_flags = {}
active_brands = {}


def normalize(text):
    """توحيد الهمزات عشان !إنعاش و !انعاش يشتغلوا نفس الشي"""
    for ch in "أإآ":
        text = text.replace(ch, "ا")
    return text.strip()


class RouletteGame:
    def __init__(self, channel, host):
        self.channel = channel
        self.players = {}   # الرقم -> العضو
        self.status = {}    # الرقم -> alive / dead / out
        self.joining = True
        self.starter = host
        self.task = None
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

    async def run(self):
        ch = self.channel

        # ---------- التسجيل ----------
        await ch.send(
            "🎡 **روليت!**\n"
            f"اكتبوا `!دخول` للمشاركة. التسجيل ينتهي بعد {JOIN_TIME} ثانية.\n"
            f"صاحب اللعبة دخل تلقائيًا برقم **1**."
        )
        await asyncio.sleep(JOIN_TIME)
        self.joining = False

        if len(self.players) < MIN_PLAYERS:
            await ch.send(
                f"❌ ما كفى لاعبين. لازم على الأقل {MIN_PLAYERS} لاعبين. انلغت اللعبة."
            )
            return

        await ch.send(
            "✅ انتهى التسجيل! هذي الأرقام:\n" + self.format_list(self.nums("alive"))
        )
        await asyncio.sleep(4)

        # ---------- الأدوار ----------
        while len(self.nums("alive")) > 1:
            await self.play_turn()
            await asyncio.sleep(3)

        winner = self.nums("alive")[0]
        await ch.send(
            f"🏆 الفائز هو {self.players[winner].mention} (رقم **{winner}**)! مبروك 🎉"
        )

    async def play_turn(self):
        ch = self.channel
        alive = self.nums("alive")

        # العجلة: اختيار عشوائي بحت، كل لاعب حي إلو نفس الفرصة
        msg = await ch.send("🎡 العجلة عم تدور...")
        await asyncio.sleep(3)
        chosen = random.choice(alive)
        player = self.players[chosen]
        await msg.edit(
            content=f"🎡 العجلة وقفت على رقم **{chosen}** ← {player.mention}!"
        )

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
        return entry[1]

    def streak_message(self, member):
        if self.streak >= STREAK_STEP and self.streak % STREAK_STEP == 0:
            fire = "🔥" * min(self.streak // STREAK_STEP, 3)
            return f"{fire} **ستريك {self.streak}!** {member.mention} جاب {self.streak} ورا بعض!"
        return None

    def reset_streak(self):
        self.streak_id = None
        self.streak = 0

    async def run(self):
        ch = self.channel
        await ch.send(
            "🏳️ **لعبة الأعلام!**\n"
            f"{self.rounds} علم، وأسرع واحد بيكتب اسم الدولة بياخد نقطة.\n"
            "بتقدروا تكتبوا بالعربي أو بالإنجليزي.\n"
            f"عندكم **{FLAG_ROUND_TIME} ثانية** لكل علم. جاهزين؟ 🚀"
        )
        await asyncio.sleep(4)

        picked = random.sample(FLAGS, self.rounds)
        for i, (code, ar, en, answers) in enumerate(picked, start=1):
            embed = discord.Embed(
                title=f"🏳️ العلم {i} من {self.rounds}",
                description="شو اسم هالدولة؟ اكتبه بسرعة!",
                color=discord.Color.blurple(),
            )
            embed.set_image(url=f"https://flagcdn.com/w640/{code}.png")
            await ch.send(embed=embed)

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
                text = (
                    f"✅ برافو {m.author.mention}! العلم هو **{ar}** ({en})\n"
                    f"نقاطك: **{pts}**"
                )
                bonus = self.streak_message(m.author)
                if bonus:
                    text += "\n" + bonus
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
    ["facebook", "فيسبوك", "فيس بوك"],
    ["instagram", "انستغرام", "انستجرام", "انستقرام", "انستا"],
    ["youtube", "يوتيوب", "يوتوب"],
    ["twitter", "تويتر", "x", "اكس"],
    ["whatsapp", "واتساب", "واتس اب", "واتس"],
    ["telegram", "تيليجرام", "تيليغرام", "تلغرام", "تلجرام"],
    ["snapchat", "سناب شات", "سناب", "سنابشات"],
    ["tiktok", "تيك توك", "تيكتوك"],
    ["netflix", "نتفلكس", "نتفليكس", "نيتفليكس"],
    ["spotify", "سبوتيفاي", "سبوتفاي"],
    ["discord", "ديسكورد", "دسكورد"],
    ["playstation", "بلايستيشن", "بلاي ستيشن"],
    ["xbox", "اكس بوكس"],
    ["nintendo", "نينتندو"],
    ["lego", "ليغو", "ليجو"],
    ["mcdonalds", "mcdonald's", "ماكدونالدز", "ماكدونالد", "ماك دونالدز", "ماكدونالز", "ماك"],
    ["kfc", "كنتاكي", "كي اف سي"],
    ["burger king", "برجر كنج", "برغر كنغ", "برجر كينج"],
    ["starbucks", "ستاربكس"],
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
            "اللعبة بتضل شغالة لحد ما تيجي ماركة ما حدا بيعرفها 😉\n"
            "وبتقدروا توقفوها بـ `!stop`. جاهزين؟ 🚀"
        )
        await asyncio.sleep(4)

        deck = []
        last = None
        while True:
            if not deck:
                # خلصت الماركات؟ منخلطها من جديد (بدون ما نكرر آخر وحدة)
                deck = random.sample(self.brands, len(self.brands))
                if len(deck) > 1 and deck[-1] is last:
                    deck[0], deck[-1] = deck[-1], deck[0]
            brand = deck.pop()
            last = brand
            path, name, ext, answers = brand

            embed = discord.Embed(
                title="🛍️ ما اسم هذه الماركة؟",
                description=f"لديك {BRAND_ROUND_TIME} ثانية للإجابة",
                color=discord.Color.orange(),
            )
            embed.set_image(url=f"attachment://logo{ext}")
            embed.set_footer(
                text=f"تم الطلب بواسطة {self.starter.display_name}",
                icon_url=self.starter.display_avatar.url,
            )
            await ch.send(embed=embed, file=discord.File(path, filename=f"logo{ext}"))

            def check(m):
                if m.channel != ch or m.author.bot:
                    return False
                t = normalize_answer(m.content)
                return t in answers or t.replace(" ", "") in answers

            try:
                m = await bot.wait_for("message", check=check, timeout=BRAND_ROUND_TIME)
            except asyncio.TimeoutError:
                await ch.send(f"⏰ انتهى الوقت وما حدا عرفها! الماركة هي **{name}**")
                break

            pts = self.add_point(m.author)
            text = (
                f"✅ برافو {m.author.mention}! الماركة هي **{name}**\n"
                f"نقاطك: **{pts}**"
            )
            bonus = self.streak_message(m.author)
            if bonus:
                text += "\n" + bonus
            await ch.send(text)
            await asyncio.sleep(3)

        await ch.send("🏁 **انتهت اللعبة!** جات ماركة ما حدا عرفها.")
        await self.show_scores()


# ================= الأوامر =================
@bot.command(name="روليت")
async def roulette(ctx):
    if ctx.channel.id in active_games:
        await ctx.send("⚠️ في لعبة روليت شغالة بهالروم.")
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


@bot.command(name="دخول")
async def join(ctx):
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


@bot.command(name="اعلام", aliases=["أعلام"])
async def flags(ctx, rounds: int = FLAG_DEFAULT_ROUNDS):
    if ctx.channel.id in active_flags or ctx.channel.id in active_brands:
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
    game = (
        active_flags.get(ctx.channel.id)
        or active_brands.get(ctx.channel.id)
        or active_games.get(ctx.channel.id)
    )
    if game is None:
        await ctx.send("ما في لعبة شغالة بهالروم.")
        return
    if ctx.author.id != game.starter.id and not ctx.author.guild_permissions.manage_messages:
        await ctx.send("بس صاحب اللعبة أو الأدمن بيقدر يوقفها.")
        return
    game.task.cancel()


@bot.command(name="ماركات", aliases=["ماركة", "ماركه"])
async def brands_game(ctx):
    if ctx.channel.id in active_flags or ctx.channel.id in active_brands:
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


@bot.event
async def on_ready():
    print("Bot is ready:", bot.user)


@bot.event
async def on_command_error(ctx, error):
    # أوامر اللعبة (!طرد / !انعاش / !انسحاب) بتنقرا داخل الدور، فنتجاهل CommandNotFound
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.BadArgument):
        await ctx.send("اكتب عدد الأعلام كرقم، مثلًا: `!اعلام 10`")
        return
    print("Error:", error)


bot.run("MTU1Njc5NDIwMDcwMjQ1NTg4NA.GOVcpb.AS_p1m_EiaVRrArd4sSDNG7L7T5UksQR4H0BHk")