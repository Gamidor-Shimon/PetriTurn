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

# ---- connectivity (strips + wires); resistors are looked up separately ----
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


USED = {h for pm in L.COMPONENTS.values() for h in pm.values()} | {h for w in L.WIRES for h in w[:2]}


def free_hole(pin_hole):
    """Another hole on the same strip, not used by a part or a wire (for probing)."""
    col, row = pin_hole[0], int(pin_hole[1:])
    half = "ABCDE" if col in "ABCDE" else "FGHIJ"
    for c in (reversed(half) if half == "ABCDE" else half):
        if f"{c}{row}" not in USED:
            return f"{c}{row}"
    return pin_hole


# ---- names ----
PIN_HE = {
    "XIAO": "XIAO", "TMC": "דרייבר", "R1": "R1 1kΩ", "R2": "R2 10kΩ", "R3": "R3 330Ω",
    "C1": "C1 100µF", "MOTOR": "מהדק מנוע", "PWR": "מהדק מתח", "PANEL": "מהדק פאנל",
    "ENPAD": "חוט דק ממשטח EN בגב ה-XIAO",
}
PIN_NAME = {("TMC", "GND_P"): "GND (ליד VM)", ("TMC", "GND_L"): "GND (האחרון)",
            ("MOTOR", "1"): "1 · A2 · חוט שחור", ("MOTOR", "2"): "2 · A1 · חוט ירוק",
            ("MOTOR", "3"): "3 · B1 · חוט אדום", ("MOTOR", "4"): "4 · B2 · חוט כחול",
            ("C1", "+"): "+ (רגל ארוכה)", ("C1", "-"): "− (פס לבן)",
            ("R1", "1"): "רגל 1", ("R1", "2"): "רגל 2", ("R2", "1"): "רגל 1", ("R2", "2"): "רגל 2",
            ("R3", "1"): "רגל 1", ("R3", "2"): "רגל 2", ("ENPAD", "wire"): "קצה"}
NET_HE = {"VM +24V": "+24V (מתח המנוע)", "GND": "GND (אדמה)", "3V3": "3.3V",
          "EN": "EN — הפעלת המנוע", "STEP": "STEP", "DIR": "DIR", "TX": "TX (D4, לפני R1)",
          "USART": "USART (תקשורת עם הדרייבר)", "A2": "מנוע A2", "A1": "מנוע A1",
          "B1": "מנוע B1", "B2": "מנוע B2", "LED": "לד (D10, לפני R3)",
          "LED anode": "לד + (אחרי R3)", "RESET": "RESET"}
WIRE_HE = {
    "3.3V bus: join both halves of row 18": "פס 3.3V — מחבר את שני חצאי שורה 18",
    "XIAO 3V3 -> 3.3V bus": "3V3 של ה-XIAO ← פס 3.3V", "3.3V bus -> VDD": "פס 3.3V ← VDD של הדרייבר",
    "D1 -> EN": "D1 ← EN", "D2 -> STEP": "D2 ← STEP", "D3 -> DIR": "D3 ← DIR",
    "D5 -> USART": "D5 ← USART", "MS1 -> GND (across the channel)": "MS1 ← GND (מעל התעלה)",
    "MS2 -> MS1 / GND": "MS2 ← MS1 / GND", "power GND <-> logic GND": "GND ↔ GND של הדרייבר",
    "XIAO GND -> GND": "GND של ה-XIAO ← GND",
    "+24V: terminal -> VM": "+24V: מהדק מתח ← VM", "0V: terminal -> GND": "0V: מהדק מתח ← GND",
    "GND -> panel terminal": "GND ← מהדק פאנל", "LED+ -> panel terminal": "לד + ← מהדק פאנל",
}
COLOUR = {"#7b3fb8": "סגול", "#1f6fd1": "כחול", "#e08a00": "כתום", "#222222": "שחור",
          "#7a7a7a": "אפור", "#2e7d32": "ירוק", "#d62d20": "אדום", "#2a9d3a": "ירוק"}
WNUM = {w[:2]: i for i, w in enumerate(L.WIRES, 1)}


def pin_label(comp, pin):
    return f"{PIN_HE[comp]} · {PIN_NAME.get((comp, pin), pin)}"


# ---- 1. connection list: every net, every pin and wire end, with its hole ----
pins = {f"{c}.{p}": h for c, pm in L.COMPONENTS.items() for p, h in pm.items()}
net_list = []
for net, members in L.EXPECTED.items():
    root = find(pins[members[0]])
    items = []
    for c, pm in L.COMPONENTS.items():
        for p, h in pm.items():
            if find(h) == root:
                items.append((h, pin_label(c, p)))
    for (a, b), i in WNUM.items():
        for h in (a, b):
            if find(h) == root:
                items.append((h, f"קצה של חוט W{i}"))
    items.sort(key=lambda t: (int(t[0][1:]), t[0][0]))
    net_list.append(f"#### {NET_HE[net]}\n")
    net_list.append("| חור | מה מחובר |\n|---|---|")
    net_list += [f"| `{h}` | {what} |" for h, what in items]
    net_list.append("")
alone = [f"`{pins['TMC.' + p]}` {p}" for p in ("PDN", "CLK")] + \
        [f"`{pins['XIAO.' + p]}` {p}" for p in ("D0", "D6", "5V", "D9", "D8", "D7")]
net_list.append("**רגליים שלא מחוברות לשום דבר** (לבד בפס שלהן): " + ", ".join(alone))

# ---- 2. wires ----
wires = ["| חוט | מה | מ- | אל | צד | צבע |", "|---|---|---|---|---|---|"]
for i, (a, b, c, what, sd, via) in enumerate(L.WIRES, 1):
    wires.append(f"| W{i} | {WIRE_HE[what]} | `{a}` | `{b}` | "
                 f"{'למעלה (קצר)' if sd == 'top' else 'למטה'} | {COLOUR[c]} |")

# ---- 3. multimeter ----
checks = [  # (a, b, expected, what)
    (PW["+24V"], PW["0V"], "open", "**אין קצר בין 24V ל-GND**"),
    (PW["+24V"], X["3V3"], "open", "**24V לא מגיע ל-3.3V**"),
    (PW["+24V"], T["VM"], "0", "מהדק המתח מגיע ל-VM"),
    (PW["0V"], X["GND"], "0", "GND של הספק = GND של הבקר"),
    (PW["0V"], T["GND_L"], "0", "GND של הלוגיקה בדרייבר"),
    (PW["0V"], T["MS1"], "0", "MS1 ל-GND"),
    (PW["0V"], T["MS2"], "0", "MS2 ל-GND"),
    (PW["0V"], PN["GND"], "0", "GND במהדק הפאנל"),
    (X["3V3"], T["VDD"], "0", "3.3V מגיע ל-VDD"),
    (X["3V3"], T["EN"], "10k", "R2: EN ← 3.3V"),
    (X["D1"], T["EN"], "0", "D1 → EN"),
    (X["D2"], T["STEP"], "0", "D2 → STEP"),
    (X["D3"], T["DIR"], "0", "D3 → DIR"),
    (X["D5"], T["USART"], "0", "D5 → USART"),
    (X["D4"], T["USART"], "1k", "D4 → R1 → USART"),
    (X["D10"], PN["LED+"], "330", "D10 → R3 → מהדק הלד"),
    (M["1"], M["2"], "open", "אין קצר בין חוטי המנוע"),
    (M["2"], M["3"], "open", ""), (M["3"], M["4"], "open", ""),
    (PN["RST"], PN["GND"], "open", "RESET לא מקוצר ל-GND"),
    (T["PDN"], T["USART"], "open", "PDN לבד"),
    (T["CLK"], T["STEP"], "open", "CLK לבד"),
]
show = {"0": "צפצוף", "open": "**אין צפצוף**", "1k": "≈1kΩ", "10k": "≈10kΩ", "330": "≈330Ω"}
meter = ["| בין | צריך | מה זה בודק |", "|---|---|---|"]
for a, b, want, what in checks:
    got = meas(a, b)
    assert got == want, (a, b, want, got)
    pa, pb = free_hole(a), free_hole(b)          # probe free holes of the same strips
    assert pa != pb, (a, b)
    meter.append(f"| `{pa}` ↔ `{pb}` | {show[want]} | {what} |")

N = "\n"
text = f"""# לוח ההלחמה — PetriTurn

הלוח: **לוח הלחמה בסגנון מטריצה, 89 × 52 מ"מ, בשלמותו.** 30 שורות, עמודות A–J.
בכל שורה **A–E מחוברים** ו-**F–J מחוברים**, ואין חיבור בין E ל-F (התעלה באמצע). פסי המתח שבצדדים לא בשימוש.

**כל המיקומים הם לפי המספרים והאותיות שמודפסים על הלוח.** במבט מלמעלה (הצד של הרכיבים): שורה 1 למעלה, A משמאל —
בדיוק כמו בציור `top.png`.
הסידור מוגדר ב-`layout.py` ונבדק אוטומטית: כל חיבור קיים, אין קצרים, רגליים שלא בשימוש לבד בפס שלהן.

| מלמעלה — רכיבים | מלמטה — חוטים (שורה 1 למעלה, **A מימין**) |
|---|---|
| ![top](top.png) | ![bottom](bottom.png) |

> **כמו שהרכיבים הונחו על הלוח (לפי התמונה):** XIAO בשורות 9–15, `D9` = D0, `H9` = 5V (VUSB).
> דרייבר בשורות 19–26, `D19` = EN, `G19` = VM.

---

## 1. הרכיבים

| רכיב | מיקום | הערה |
|---|---|---|
| **XIAO ESP32-C3** על 2 × 7 שקעים נקבה | עמודה `D` שורות 9–15: D0, D1, D2, D3, D4, D5, D6 · עמודה `H` שורות 9–15: 5V, GND, 3V3, D10, D9, D8, D7 | **הרכיבים למעלה, USB-C לכיוון שורה 1** |
| **TMC2209** על 2 × 8 שקעים נקבה | עמודה `D` שורות 19–26: EN, MS1, MS2, PDN, USART, CLK, STEP, DIR · עמודה `G` שורות 19–26: VM, GND, A2, A1, B1, B2, VDD, GND | **הפוטנציומטר לכיוון ה-XIAO** |
| **R1** 1kΩ | `{L.R1['1']}` – `{L.R1['2']}` | עומד |
| **R2** 10kΩ | `{L.R2['1']}` – `{L.R2['2']}` | עומד |
| **R3** 330Ω | `{L.R3['1']}` – `{L.R3['2']}` | שוכב לאורך עמודה I |
| **C1** 100µF / 35V | **+** `{L.C1['+']}`, **−** `{L.C1['-']}` | **שוכב** לאורך עמודה H, הגוף לכיוון שורה 30 (לא על בורג ההרכבה). **קוטביות!** |
| **מהדק מנוע** — 4 ברגים | `{M['1']}` A2, `{M['2']}` A1, `{M['3']}` B1, `{M['4']}` B2 | שחור, ירוק, אדום, כחול. יושב ישר על השורות של הדרייבר. פתחי החוטים החוצה |
| **מהדק מתח** — 2 ברגים | 0V `{PW['0V']}`, +24V `{PW['+24V']}` | פתחי החוטים החוצה |
| **מהדק פאנל** — 3 ברגים | RST `{PN['RST']}`, GND `{PN['GND']}`, LED+ `{PN['LED+']}` | פתחי החוטים החוצה |
| **חוט מ-EN** | משטח `EN` בגב ה-XIAO ← `{L.ENPAD['wire']}` | חוט דק, ראו סעיף 4 |

**המהדקים בפסיעה 2.5 מ"מ:** כל רגל בשורה משלה, בשורות צמודות. כל המהדקים בעמודה J, פתחי החוטים החוצה מהלוח.

**בפאנל:**
- לד STATUS: רגל ארוכה (+) ← **LED+**, רגל קצרה (−) ← **GND**.
- כפתור RESET: רגל אחת ← **RST**, רגל שנייה ← **GND** (שני חוטים באותו בורג GND).
- שקע המתח: + ← **+24V**, − ← **0V**.

---

## 2. רשימת כל החיבורים

לכל חיבור — כל החורים שחייבים להיות מחוברים זה לזה (דרך הפס או דרך חוט).
**שורה אחת בטבלה = חור אחד.** חורים באותה שורה ובאותו חצי (A–E או F–J) מחוברים כבר דרך הפס.

{N.join(net_list)}

---

## 3. חוטים

{N.join(wires)}

- W1, W8 **מעל הלוח**, קצרים (לפני שמכניסים את הדרייבר). כל השאר **מתחת ללוח** — לפי `bottom.png` (שם A מימין).
- חוטים מבודדים בלבד. כל קצה מולחם רק לחור שלו.
- **חוטי המתח** (W12, W13): חוט עבה יותר, 0.35–0.5 מ"מ².
- הקצה `I27` (W13) נמצא ליד מהדק המתח — מלחימים אותו **מלמטה**.

---

## 4. חוט האיפוס — משטח EN בגב ה-XIAO

כפתור RESET עושה **איפוס אמיתי**: מחבר את EN של ה-XIAO ל-GND.
EN הוא **משטח קטן בגב ה-XIAO** (מסומן `EN`), לא רגל.

1. להלחים חוט דק (wire-wrap) למשטח `EN` — מלחם נקי, נגיעה קצרה.
2. להעביר אותו מתחת ל-XIAO, בין שתי שורות השקעים, אל `{L.ENPAD['wire']}`, ולהלחים שם.
3. מ-`{L.ENPAD['wire']}` הפס מגיע לבורג **RST** במהדק הפאנל.
4. **בהחלפת XIAO** — להעביר את החוט ל-XIAO החדש.

---

## 5. בדיקה במולטימטר — בלי XIAO, בלי דרייבר, בלי מתח

מודדים על **חורים פנויים** באותם פסים.

{N.join(meter)}

**אחרי שה-XIAO והדרייבר בשקעים** (עדיין בלי מתח):
- המתכת של שקע ה-USB-C ↔ `{free_hole(X['GND'])}` — **צפצוף**.
- `{free_hole(T['GND_L'])}` ↔ `{free_hole(PW['0V'])}` — **צפצוף**.
"""
(HERE / "README.md").write_text(text, encoding="utf-8")
print("README written;", len(checks), "multimeter rows verified;", len(L.EXPECTED), "nets listed")
