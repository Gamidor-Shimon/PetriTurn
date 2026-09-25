"""
Writes perfboard/README.md from the checked layout data, so no hole name is copied by hand.
Every multimeter row is checked against the layout before it is written.

Run (from the project root), after changing layout.py:
    .venv\\Scripts\\python perfboard\\make_readme.py
"""
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import layout as L  # noqa: E402

assert not L.check(), L.check()
X, T, M, PN, PW = L.XIAO, L.TMC, L.MOTOR, L.PANEL, L.PWR
rows_of = lambda d, keys: f"{min(int(d[k][1:]) for k in keys)}–{max(int(d[k][1:]) for k in keys)}"

# ---- connectivity for the multimeter table (strips + wires + resistors) ----
parent = {}


def find(x):
    parent.setdefault(x, x)
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def union(a, b):
    parent[find(a)] = find(b)


for r in range(1, L.ROWS + 1):
    for half in ("ABCDE", "FGHIJ"):
        for c in half[1:]:
            union(f"{half[0]}{r}", f"{c}{r}")
for a, b, *_ in L.WIRES:
    union(a, b)
RES = {frozenset((find(L.R1["1"]), find(L.R1["2"]))): "1k",
       frozenset((find(L.R2["1"]), find(L.R2["2"]))): "10k",
       frozenset((find(L.R3["1"]), find(L.R3["2"]))): "330"}


def meas(a, b):
    ra, rb = find(a), find(b)
    return "0" if ra == rb else RES.get(frozenset((ra, rb)), "open")


def free_hole(pin_hole, avoid=()):
    """Another hole on the same strip, not used by a part or a wire (for probing)."""
    col, row = pin_hole[0], int(pin_hole[1:])
    half = "ABCDE" if col in "ABCDE" else "FGHIJ"
    used = {h for pm in L.COMPONENTS.values() for h in pm.values()} | \
           {h for w in L.WIRES for h in w[:2]} | set(avoid)
    for c in reversed(half) if half == "ABCDE" else half:
        h = f"{c}{row}"
        if h not in used:
            return h
    return pin_hole


checks = [  # (a, b, expected, what)
    (PW["+24V"], PW["0V"], "open", "**אין קצר בין 24V ל-GND**"),
    (PW["+24V"], X["3V3"], "open", "**24V לא מגיע ל-3.3V**"),
    (PW["0V"], X["GND"], "0", "GND של הספק = GND של הבקר, הכפתור והלד"),
    (PW["0V"], T["GND_L"], "0", "GND של הלוגיקה בדרייבר"),
    (PW["0V"], T["MS1"], "0", "MS1 ל-GND"),
    (PW["0V"], T["MS2"], "0", "MS2 ל-GND"),
    (X["3V3"], T["VDD"], "0", "3.3V מגיע ל-VDD"),
    (X["3V3"], T["EN"], "10k", "R2: EN ← 3.3V"),
    (X["D1"], T["EN"], "0", "D1 → EN"),
    (X["D2"], T["STEP"], "0", "D2 → STEP"),
    (X["D3"], T["DIR"], "0", "D3 → DIR"),
    (X["D5"], T["USART"], "0", "D5 → USART"),
    (X["D4"], T["USART"], "1k", "D4 → R1 → USART"),
    (X["D10"], PN["LED+"], "330", "D10 → R3 → לד"),
    (M["1"], M["2"], "open", "אין קצר בין חוטי המנוע"),
    (M["2"], M["3"], "open", ""), (M["3"], M["4"], "open", ""),
    (T["PDN"], T["USART"], "open", "PDN לבד"),
    (T["CLK"], T["STEP"], "open", "CLK לבד"),
]
show = {"0": "≈0Ω", "open": "**נתק**", "1k": "≈1kΩ", "10k": "≈10kΩ", "330": "≈330Ω"}
meter = ["| בין | צריך | מה זה בודק |", "|---|---|---|"]
for a, b, want, what in checks:
    got = meas(a, b)
    assert got == want, (a, b, want, got)
    pa, pb = free_hole(a), free_hole(b)          # probe free holes of the same strips
    assert pa != pb, (a, b)
    meter.append(f"| `{pa}` ↔ `{pb}` | {show[want]} | {what} |")

# ---- row table ----
nice = {"PWR.+24V": "**+24V**", "PWR.0V": "**0V**", "C1.+": "C1 +", "C1.-": "C1 −",
        "PANEL.LED+": "**LED+ (לפאנל)**", "PANEL.LED-": "**LED− (לפאנל)**",
        "PANEL.BTN": "**RESET (לפאנל)**"}
occ = defaultdict(list)
for comp, pm in L.COMPONENTS.items():
    for pin, h in pm.items():
        key = f"{comp}.{pin}"
        name = nice.get(key) or (f"מנוע {pin}" if comp == "MOTOR" else
                                 comp if comp in ("R1", "R2", "R3") else
                                 key.replace("GND_P", "GND").replace("GND_L", "GND"))
        occ[("L" if h[0] in "ABCDE" else "R", int(h[1:]))].append(name)
for i, (a, b, *_r) in enumerate(L.WIRES, 1):
    for h in (a, b):
        occ[("L" if h[0] in "ABCDE" else "R", int(h[1:]))].append(f"W{i}")
bus_row = int(L.WIRES[0][0][1:])
lone = {("R", int(T["PDN"][1:])): "TMC.PDN — **לבד**", ("R", int(T["CLK"][1:])): "TMC.CLK — **לבד**"}
first = min(int(h[1:]) for pm in L.COMPONENTS.values() for h in pm.values())
last = max(int(h[1:]) for pm in L.COMPONENTS.values() for h in pm.values())
rows = ["| שורה | A–E (שמאל) | F–J (ימין) |", "|---|---|---|",
        f"| 1–{first - 1} | — (**פנוי: מקום למתאם ה-USB**) | — |"]
for r in range(first, last + 1):
    left = ", ".join(occ[("L", r)]) or "—"
    right = lone.get(("R", r)) or ", ".join(occ[("R", r)]) or "—"
    if r == bus_row:
        left, right = "**פס 3.3V**: " + left, "**פס 3.3V**: " + right
    rows.append(f"| {r} | {left} | {right} |")
rows.append(f"| {last + 1}–{L.ROWS} | — | — |")

# ---- wires ----
he = {"3.3V bus: join both halves of row 15": f"פס 3.3V — מחבר את שני חצאי שורה {bus_row}",
      "XIAO 3V3 -> 3.3V bus": "3V3 של ה-XIAO ← פס 3.3V", "3.3V bus -> VDD": "פס 3.3V ← VDD של הדרייבר",
      "D1 -> EN": "D1 ← EN", "D2 -> STEP": "D2 ← STEP", "D3 -> DIR": "D3 ← DIR",
      "D5 -> USART": "D5 ← USART", "MS1 -> GND (across the channel)": "MS1 ← GND (מעל התעלה)",
      "MS2 -> MS1 / GND": "MS2 ← MS1 / GND", "power GND <-> logic GND": "GND של המתח ↔ GND של הלוגיקה",
      "XIAO GND -> GND": "GND של ה-XIAO ← GND"}
colour = {"#7b3fb8": "סגול", "#1f6fd1": "כחול", "#e08a00": "כתום", "#222222": "שחור", "#7a7a7a": "אפור"}
side = {"top": "למעלה (קצר)", "bottom": "למטה"}
wires = ["| חוט | מה | מ- | אל | צד | צבע |", "|---|---|---|---|---|---|"]
for i, (a, b, c, what, sd, via) in enumerate(L.WIRES, 1):
    wires.append(f"| W{i} | {he[what]} | `{a}` | `{b}` | {side[sd]} | {colour[c]} |")
top_wires = ", ".join(f"W{i}" for i, w in enumerate(L.WIRES, 1) if w[4] == "top")
bottom_wires = ", ".join(f"W{i}" for i, w in enumerate(L.WIRES, 1) if w[4] == "bottom")

xl = lambda keys: ", ".join(keys)
text = f"""# לוח ההלחמה — SBS PetriPlater

הלוח: **לוח הלחמה בסגנון מטריצה, 89 × 52 מ"מ, בשלמותו — בלי חיתוך.** 30 שורות.
בכל שורה **A–E מחוברים** ו-**F–J מחוברים**, ואין חיבור בין E ל-F — בדיוק כמו במטריצה שעליה המערכת עבדה.
הבקר והדרייבר יושבים **מעל התעלה שבאמצע**, וכל פין מקבל פס משלו. **פסי המתח שבצדדים לא בשימוש.**

הסידור מוגדר ב-`layout.py` **ונבדק אוטומטית מול [WIRING.md](../WIRING.md)**, כולל הפסים שבכל שורה:
כל חיבור קיים, אין קצר, ו-PDN, CLK ופיני ה-XIAO שלא בשימוש לבד בפס שלהם.
כל מיקומי החורים במסמך הזה נוצרו מאותם נתונים, וטבלת המולטימטר נבדקה מולם.

```bash
.venv\\Scripts\\python perfboard\\layout.py
```

| מלמעלה — רכיבים | מלמטה — חוטים (**הפוך כמו מראה**) |
|---|---|
| ![top](top.png) | ![bottom](bottom.png) |

---

## 1. הלוח בקופסה

- הלוח שוכב בצד **השמאלי** של הקופסה (ליד חריצי האוורור), המנוע באמצע, פאנל החיבורים מימין.
- **שורה 1 לכיוון הדופן הארוכה הקדמית.** העמודות A–J לרוחב.
- מוחזק ב-**2 ברגי M3** בחורי ההרכבה שבמרכז הקצוות הקצרים (על קו התעלה), ועוד 4 רגליות תמיכה בפינות.
- **שורות 1–{first - 1} נשארות פנויות:** שקע ה-USB-C של ה-XIAO פונה אליהן, ושם יושב **מתאם USB-C בזווית 90°**
  (זכר-נקבה, בצורת L, זווית למעלה). הכבל לפאנל יוצא ממנו כלפי מעלה.

**לבדוק לפני שמתחילים:** המרחק בין מרכז החור E1 למרכז החור F1 — צריך להיות **כ-7.6 מ"מ**.

---

## 2. הרכיבים

| רכיב | ערך | מיקום | הערה |
|---|---|---|---|
| **XIAO ESP32-C3** | על 2 × 7 שקעים נקבה | עמודה `D`, שורות {rows_of(X, ['5V', 'D7'])}: 5V, GND, 3V3, D10, D9, D8, D7 · עמודה `H`, שורות {rows_of(X, ['D0', 'D6'])}: D0 … D6 | **שקע ה-USB-C לכיוון שורה 1** |
| **TMC2209** (V985) | על 2 × 8 שקעים נקבה | עמודה `D`, שורות {rows_of(T, ['VM', 'GND_L'])}: VM, GND, A2, A1, B1, B2, VDD, GND · עמודה `G`, שורות {rows_of(T, ['EN', 'DIR'])}: EN, MS1, MS2, PDN, USART, CLK, STEP, DIR | **הפוטנציומטר לכיוון ה-XIAO** (שורה {T['EN'][1:]}), צלע קירור למעלה |
| **R1** | 1kΩ | `{L.R1['1']}` – `{L.R1['2']}` | שוכב לאורך עמודה J |
| **R2** | 10kΩ | `{L.R2['1']}` – `{L.R2['2']}` | **עומד** |
| **R3** | 330Ω | `{L.R3['1']}` – `{L.R3['2']}` | שוכב לאורך עמודה B — נגד ללד |
| **C1** | 100µF / 35V | **+** ב-`{L.C1['+']}`, **−** ב-`{L.C1['-']}` | **שוכב** מעל אזור פסי המתח (שלא בשימוש). **קוטביות!** |
| **מחבר מנוע** | JST-XH 4 פינים | `{M['1']}` (1), `{M['2']}` (2), `{M['3']}` (3), `{M['4']}` (4) | 1 = שחור, 2 = ירוק, 3 = אדום, 4 = כחול |
| **כניסת 24V** | חוטים משקע המתח | **+24V** ל-`{PW['+24V']}`, **0V** ל-`{PW['0V']}` | |
| **לד STATUS** (בפאנל) | לד 5 מ"מ בבית 8 מ"מ | רגל ארוכה (+) ← `{PN['LED+']}`, רגל קצרה (−) ← `{PN['LED-']}` | חוטים לפאנל |
| **כפתור RESET** (בפאנל) | לחצן רגעי (NO), חור 7 מ"מ | רגל אחת ← `{PN['BTN']}` (GND), רגל שנייה ← **משטח EN בגב ה-XIAO** | ראו סעיף 4 |

- השקעים הנקבה מאפשרים להחליף את הבקר והדרייבר בלי הלחמה. מלחימים את השקעים, לא את הרכיבים.

### מה עובר בכל שורה

{chr(10).join(rows)}

---

## 3. חוטים

רוב החיבורים נעשים **דרך הפסים**. החוטים רק מחברים בין פסים שצריכים להיפגש.

{chr(10).join(wires)}

- **D4 ← USART** עובר דרך R1, ו-**D10 ← לד** עובר דרך R3 — בלי חוט נוסף.
- {top_wires} קצרים, **מעל הלוח** (לפני שמכניסים את הדרייבר). {bottom_wires} **מתחת ללוח** — לעבוד לפי `bottom.png` (הפוך כמו מראה).

---

## 4. חוט האיפוס — משטח EN בגב ה-XIAO

כפתור RESET עושה **איפוס אמיתי** (כמו כפתור RST שעל ה-XIAO): הוא מחבר את פין האיפוס EN ל-GND.
EN של ה-XIAO הוא **משטח קטן בגב הלוח שלו** (מסומן `EN`, ליד `MTDI` / `MTMS`), לא רגל.

1. להלחים חוט דק (0.1–0.2 מ"מ², או wire-wrap) למשטח `EN` — מלחם נקי, נגיעה קצרה.
2. להעביר אותו **בין שתי שורות השקעים**, מתחת ל-XIAO, ולצאת בצד — ה-XIAO עדיין נכנס לשקעים.
3. הקצה השני — לרגל של כפתור ה-RESET. הרגל השנייה של הכפתור ← `{PN['BTN']}` (GND).
4. **בהחלפת XIAO** — להעביר את החוט ל-XIAO החדש.

---

## 5. סדר עבודה

1. לבדוק E1–F1 ≈ 7.6 מ"מ. לסמן שורה 1 בטוש.
2. **שקעים נקבה:** 2×7 ל-XIAO (עמודות D, H), 2×8 לדרייבר (עמודות D, G), בשורות שבטבלה.
3. {top_wires} (הקצרים, מלמעלה).
4. R1, R2 (עומד), R3, C1 (**קוטביות**), מחבר JST.
5. {bottom_wires} מלמטה.
6. חוטים לפאנל (~25 ס"מ): LED+ מ-`{PN['LED+']}`, LED− מ-`{PN['LED-']}`, RESET מ-`{PN['BTN']}`.
7. **בדיקה במולטימטר — בלי רכיבים ובלי מתח** (למטה).
8. חוטי 24V: אדום ל-`{PW['+24V']}`, שחור ל-`{PW['0V']}`. חוט האיפוס מגב ה-XIAO לכפתור.
9. להכניס את ה-XIAO (USB-C לשורה 1) ואת הדרייבר (פוטנציומטר לכיוון ה-XIAO). מתאם 90° על ה-USB-C.
10. USB בלבד → `STATUS`. אחר כך 24V → `DIAG` צריך להחזיר `A0=12/0x21`.

---

## 6. בדיקה במולטימטר — בלי רכיבים, בלי מתח

מודדים על **חורים פנויים** באותם פסים (לא על השקעים).

{chr(10).join(meter)}
"""
(HERE / "README.md").write_text(text, encoding="utf-8")
print("README written;", len(checks), "multimeter rows verified; rows", first, "-", last)
