"""Synthetic 2025 source documents for a made-up client (the Holloways: MFJ, Ann Arbor MI).

Seven PDFs to drop on a case (organizer, two W-2s, 1099-INT, composite 1099-DIV/B,
1098, K-1 1065), plus an answer key in OpenTax input.json shape. Every page carries
a SYNTHETIC watermark and a "Fictional document" footer, which intake requires.

    .venv/bin/python scripts/make_source_docs.py [out_dir]     # default: server/tests/fixtures/sources
"""
import json
import sys
from pathlib import Path
from fpdf import FPDF

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "server" / "tests" / "fixtures" / "sources"
KEY = OUT
OUT.mkdir(parents=True, exist_ok=True)

TP = dict(name="DANIEL R HOLLOWAY", ssn="XXX-XX-4417")
SP = dict(name="PRIYA S HOLLOWAY", ssn="XXX-XX-8032")
ADDR = ["2418 Glenwood Ct", "Ann Arbor, MI 48104"]


def money(v):
    return "" if v is None else f"{v:,.2f}"


class Form(FPDF):
    def __init__(self, title, subtitle, form_id):
        super().__init__("P", "pt", "Letter")
        self.set_auto_page_break(False)
        self.title_txt, self.sub, self.form_id = title, subtitle, form_id
        self.add_page()
        self.set_draw_color(40, 40, 40)
        # watermark
        self.set_text_color(225, 225, 225)
        self.set_font("Helvetica", "B", 44)
        with self.rotation(30, 306, 420):
            self.text(60, 470, "SYNTHETIC - PRACTICE ONLY")
        self.set_text_color(0, 0, 0)
        self.set_font("Helvetica", "B", 16)
        self.text(36, 48, title)
        self.set_font("Helvetica", "", 9)
        self.text(36, 62, subtitle)
        self.set_font("Helvetica", "B", 10)
        self.text(470, 48, "Tax Year 2025")
        self.set_font("Helvetica", "", 7)
        self.text(36, 770, f"{form_id}  |  Fictional document generated for software practice. Not issued by any payer. Not for filing.")

    def box(self, x, y, w, h, label, value="", big=False, align="R"):
        self.rect(x, y, w, h)
        self.set_font("Helvetica", "", 6.5)
        self.set_xy(x + 2, y + 2)
        self.multi_cell(w - 4, 7.5, label)
        self.set_font("Courier", "B", 11 if big else 10)
        if isinstance(value, (list, tuple)):
            for i, line in enumerate(value):
                self.text(x + 5, y + h - 6 - 11 * (len(value) - 1 - i), line)
        elif value != "":
            txt = money(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else str(value)
            tw = self.get_string_width(txt)
            self.text(x + w - tw - 5 if align == "R" else x + 5, y + h - 6, txt)

    def check(self, x, y, label, on):
        self.rect(x, y, 8, 8)
        if on:
            self.set_font("Helvetica", "B", 9)
            self.text(x + 1.5, y + 7, "X")
        self.set_font("Helvetica", "", 6.5)
        self.text(x + 11, y + 7, label)


def w2(fn, emp, ee, d):
    p = Form("Form W-2  Wage and Tax Statement", "Copy B - To Be Filed With Employee's FEDERAL Tax Return. Department of the Treasury - IRS", "W-2")
    L, M, R, Y = 36, 306, 576, 90
    h = 40
    p.box(L, Y, 270, h, "a  Employee's social security number", ee["ssn"], align="L")
    p.box(L, Y + h, 270, h, "b  Employer identification number (EIN)", emp["ein"], align="L")
    p.box(L, Y + 2 * h, 270, 80, "c  Employer's name, address, and ZIP code", [emp["name"], *emp["addr"]])
    p.box(L, Y + 2 * h + 80, 270, h, "d  Control number", d.get("control", ""), align="L")
    p.box(L, Y + 3 * h + 80, 270, 80, "e/f  Employee's name, address, and ZIP code", [ee["name"], *ADDR])
    rows = [("1  Wages, tips, other compensation", d["b1"], "2  Federal income tax withheld", d["b2"]),
            ("3  Social security wages", d["b3"], "4  Social security tax withheld", d["b4"]),
            ("5  Medicare wages and tips", d["b5"], "6  Medicare tax withheld", d["b6"]),
            ("7  Social security tips", "", "8  Allocated tips", ""),
            ("9", "", "10  Dependent care benefits", d.get("b10", ""))]
    for i, (l1, v1, l2, v2) in enumerate(rows):
        p.box(M, Y + i * h, 135, h, l1, v1, big=True)
        p.box(M + 135, Y + i * h, 135, h, l2, v2, big=True)
    y2 = Y + 5 * h
    p.box(M, y2, 135, h, "11  Nonqualified plans", "")
    b12 = d.get("b12", [])
    p.box(M + 135, y2, 135, 4 * 22, "12  See instructions for box 12", "")
    for i, (code, amt) in enumerate(b12):
        p.set_font("Courier", "B", 10)
        p.text(M + 145, y2 + 24 + 16 * i, f"12{'abcd'[i]}  {code}")
        s = money(amt)
        p.text(M + 265 - p.get_string_width(s), y2 + 24 + 16 * i, s)
    p.rect(M, y2 + h, 135, 48)
    p.set_font("Helvetica", "", 6.5)
    p.text(M + 3, y2 + h + 9, "13")
    p.check(M + 8, y2 + h + 14, "Statutory employee", False)
    p.check(M + 8, y2 + h + 25, "Retirement plan", d.get("b13_ret", False))
    p.check(M + 8, y2 + h + 36, "Third-party sick pay", False)
    b14 = d.get("b14", [])
    p.box(M, y2 + h + 48, 270, 36, "14  Other", "  ".join(f"{k} {money(v)}" for k, v in b14), align="L")
    ys = Y + 3 * h + 180
    cols = [(L, 50, "15  State", d["st"]), (L + 50, 130, "Employer's state ID number", emp["state_id"]),
            (L + 180, 100, "16  State wages, tips, etc.", d["b16"]), (L + 280, 90, "17  State income tax", d["b17"]),
            (L + 370, 90, "18  Local wages, tips, etc.", ""), (L + 460, 80, "19  Local income tax", "")]
    for x, w, lab, v in cols:
        p.box(x, max(ys, y2 + h + 84) + 10, w, h, lab, v, align="L" if x < L + 180 else "R")
    p.output(OUT / fn)


def i1099(fn, title, form_id, payer, recip, boxes, extra=None):
    p = Form(title, "Copy B - For Recipient. This is important tax information and is being furnished to the IRS.", form_id)
    L, Y = 36, 90
    p.box(L, Y, 270, 90, "PAYER'S name, street address, city, state, ZIP, telephone", [payer["name"], *payer["addr"]])
    p.box(L, Y + 90, 135, 36, "PAYER'S TIN", payer["tin"], align="L")
    p.box(L + 135, Y + 90, 135, 36, "RECIPIENT'S TIN", recip["ssn"], align="L")
    p.box(L, Y + 126, 270, 70, "RECIPIENT'S name, street address, city, state, ZIP", [recip["name"], *ADDR])
    p.box(L, Y + 196, 270, 36, "Account number (see instructions)", payer.get("acct", ""), align="L")
    x0, y = 306, Y
    for i in range(0, len(boxes), 2):
        for j, (lab, v) in enumerate(boxes[i:i + 2]):
            p.box(x0 + j * 135, y, 135, 36, lab, v, big=True)
        y += 36
    if extra:
        extra(p, max(y, Y + 232) + 20)
    p.output(OUT / fn)


# ---------- the client ----------
EMP_D = dict(name="GREAT LAKES MOBILITY SYSTEMS INC", ein="38-7215560",
             addr=["1500 Technology Dr", "Ann Arbor, MI 48108"], state_id="MI 38-7215560")
EMP_P = dict(name="HURON VALLEY HEALTH SYSTEM", ein="38-6410927",
             addr=["5301 E Huron River Dr", "Ypsilanti, MI 48197"], state_id="MI 38-6410927")

d_gross, d_401k = 146_900.00, 18_500.00
p_gross, p_403b = 82_300.00, 6_000.00
W2_D = dict(b1=d_gross - d_401k, b2=16_850.00, b3=d_gross, b4=round(d_gross * .062, 2), b5=d_gross,
            b6=round(d_gross * .0145, 2), b12=[("D", d_401k), ("DD", 14_216.40)], b13_ret=True,
            st="MI", b16=d_gross - d_401k, b17=round((d_gross - d_401k) * .0425, 2), control="0044172")
W2_P = dict(b1=p_gross - p_403b, b2=7_940.00, b3=p_gross, b4=round(p_gross * .062, 2), b5=p_gross,
            b6=round(p_gross * .0145, 2), b12=[("E", p_403b), ("DD", 9_874.20)], b13_ret=True,
            b14=[("UNION", 780.00)], st="MI", b16=p_gross - p_403b, b17=round((p_gross - p_403b) * .0425, 2),
            control="HV-22871")
w2("01-W2-Daniel-GreatLakesMobility.pdf", EMP_D, TP, W2_D)
w2("02-W2-Priya-HuronValleyHealth.pdf", EMP_P, SP, W2_P)

INT = dict(b1=1_184.22, b4=0.0)
i1099("03-1099-INT-LakeshoreCreditUnion.pdf", "Form 1099-INT  Interest Income", "1099-INT",
      dict(name="LAKESHORE COMMUNITY CREDIT UNION", addr=["800 S State St", "Ann Arbor, MI 48104", "(734) 555-0142"],
           tin="38-2093315", acct="****6620 (JOINT)"), TP,
      [("1  Interest income", INT["b1"]), ("2  Early withdrawal penalty", ""),
       ("3  Interest on U.S. Savings Bonds and Treas. obligations", ""), ("4  Federal income tax withheld", ""),
       ("8  Tax-exempt interest", ""), ("9  Specified private activity bond interest", "")])

# 1099 composite: DIV + B
DIV = dict(b1a=3_412.87, b1b=2_905.14, b2a=488.00, b7=41.19, b8="VARIOUS")
LOTS = [  # description, acquired, sold, proceeds, cost, long_term
    ("40 SH NORTHPOINT GROWTH ETF (NPGX)", "02/11/2025", "09/03/2025", 6_420.55, 5_980.00, False),
    ("25 SH CEDARLINE SEMICONDUCTOR (CDLS)", "03/20/2025", "11/14/2025", 2_110.00, 2_655.30, False),
    ("150 SH NORTHPOINT TOTAL MKT IDX (NPTM)", "08/05/2019", "06/18/2025", 18_750.00, 11_204.60, True),
    ("60 SH HARBOR BAY UTILITIES (HBU)", "01/12/2021", "12/08/2025", 9_300.25, 10_120.00, True),
]


def b_table(p, y):
    p.set_font("Helvetica", "B", 10)
    p.text(36, y, "Form 1099-B  Proceeds From Broker and Barter Exchange Transactions (Copy B)")
    y += 10
    cols = [("1a Description", 190), ("1b Acquired", 62), ("1c Sold", 62), ("1d Proceeds", 72), ("1e Cost basis", 72), ("Gain/(loss)", 82)]
    for term, lt in (("SHORT-TERM - Box 2 short-term; basis reported to IRS (Form 8949 Box A)", False),
                     ("LONG-TERM - Box 2 long-term; basis reported to IRS (Form 8949 Box D)", True)):
        y += 12
        p.set_font("Helvetica", "B", 7.5)
        p.text(36, y, term)
        y += 4
        x = 36
        for lab, w in cols:
            p.set_fill_color(235, 235, 235)
            p.rect(x, y, w, 14, "DF")
            p.set_font("Helvetica", "B", 7)
            p.text(x + 3, y + 10, lab)
            x += w
        y += 14
        tot = [0, 0]
        for desc, a, s, pr, c, is_lt in LOTS:
            if is_lt != lt:
                continue
            x = 36
            for (lab, w), v in zip(cols, (desc, a, s, money(pr), money(c), money(pr - c))):
                p.rect(x, y, w, 14)
                p.set_font("Courier", "", 7.5)
                p.text(x + 3 if lab.startswith(("1a", "1b", "1c")) else x + w - 3 - p.get_string_width(v), y + 10, v)
                x += w
            tot[0] += pr; tot[1] += c
            y += 14
        p.set_font("Helvetica", "B", 7.5)
        p.text(36 + 190 + 62 + 5, y + 10, "TOTAL")
        for v, x in ((tot[0], 36 + 314 + 72), (tot[1], 36 + 386 + 72), (tot[0] - tot[1], 36 + 458 + 82)):
            s = money(v)
            p.text(x - 3 - p.get_string_width(s), y + 10, s)
        y += 16
    p.set_font("Helvetica", "", 7)
    p.text(36, y + 8, "Box 4 Federal tax withheld: 0.00   Box 1g Wash sale loss disallowed: 0.00   Box 5 Noncovered security: No   Box 6: Gross proceeds")


i1099("04-1099-Composite-NorthpointBrokerage.pdf", "Composite Form 1099  (DIV / B)  Northpoint Brokerage", "1099-DIV/1099-B",
      dict(name="NORTHPOINT BROKERAGE SERVICES LLC", addr=["200 Market Plaza, Ste 900", "Chicago, IL 60606", "(800) 555-0188"],
           tin="36-4471902", acct="NPB-7719-3350 (JTWROS)"), TP,
      [("1a  Total ordinary dividends", DIV["b1a"]), ("1b  Qualified dividends", DIV["b1b"]),
       ("2a  Total capital gain distr.", DIV["b2a"]), ("3  Nondividend distributions", ""),
       ("4  Federal income tax withheld", ""), ("5  Section 199A dividends", ""),
       ("7  Foreign tax paid", DIV["b7"]), ("8  Foreign country or U.S. possession", DIV["b8"]),
       ("12  Exempt-interest dividends", ""), ("13  Specified private activity bond int. div.", "")],
      extra=b_table)

M = dict(b1=11_862.40, b2=318_450.00, b3="06/14/2021", b5=0.0, b6=0.0, b10_tax=6_214.00)
i1099("05-1098-WolverineHomeLending.pdf", "Form 1098  Mortgage Interest Statement", "1098",
      dict(name="WOLVERINE HOME LENDING NA", addr=["PO Box 30219", "Lansing, MI 48909", "(517) 555-0107"],
           tin="38-3326158", acct="Loan 0082-441937"), TP,
      [("1  Mortgage interest received from payer(s)/borrower(s)", M["b1"]), ("2  Outstanding mortgage principal", M["b2"]),
       ("3  Mortgage origination date", M["b3"]), ("4  Refund of overpaid interest", ""),
       ("5  Mortgage insurance premiums", ""), ("6  Points paid on purchase of principal residence", ""),
       ("7  Address of property same as borrower", "X"), ("9  Number of properties securing mortgage", "1"),
       ("10  Other: Real estate taxes paid from escrow", M["b10_tax"]), ("11  Mortgage acquisition date", "")])

# K-1 (1065)
K1 = dict(name="RIVERBEND GROWTH PARTNERS II LP", ein="47-2281946", b1=4_210.00, b5=86.00, b6a=212.00, b6b=180.00,
          b9a=1_140.00, b14a=None, b19a=2_500.00, b20z=4_210.00)
p = Form("Schedule K-1 (Form 1065)",
         "Partner's Share of Income, Deductions, Credits, etc.   Final K-1 [ ]   Amended K-1 [ ]   Calendar year 2025", "K-1 (1065)")
L, Y = 36, 90
p.set_font("Helvetica", "B", 9); p.text(L, Y - 6, "Part I  Information About the Partnership")
p.box(L, Y, 260, 32, "A  Partnership's EIN", K1["ein"], align="L")
p.box(L, Y + 32, 260, 70, "B  Partnership's name, address, city, state, ZIP", [K1["name"], "410 N Main St, Ste 300", "Ann Arbor, MI 48104"])
p.box(L, Y + 102, 260, 32, "C  IRS center where partnership filed return", "E-FILE", align="L")
p.set_font("Helvetica", "B", 9); p.text(L, Y + 150, "Part II  Information About the Partner")
p.box(L, Y + 156, 260, 32, "E  Partner's SSN or TIN", TP["ssn"], align="L")
p.box(L, Y + 188, 260, 60, "F  Name, address, city, state, ZIP", [TP["name"], *ADDR])
p.box(L, Y + 248, 260, 30, "G  General partner/LLC member-manager [ ]   Limited partner [X]", "")
p.box(L, Y + 278, 260, 30, "I1  What type of entity is this partner?", "INDIVIDUAL", align="L")
p.box(L, Y + 308, 260, 44, "J  Partner's share of profit / loss / capital (ending)", "0.8400% / 0.8400% / 0.8400%", align="L")
p.box(L, Y + 352, 260, 44, "K1  Share of liabilities (ending): Nonrecourse / Qual. nonrecourse / Recourse", "0 / 0 / 0", align="L")
p.box(L, Y + 396, 260, 90, "L  Partner's capital account analysis", ["Beginning capital  48,920.00", "Contributed          0.00",
      "Current yr income   5,648.00", "Withdrawals        (2,500.00)", "Ending capital     52,068.00"])
p.box(L, Y + 486, 260, 30, "M  Did partner contribute property w/ built-in gain? Yes [ ] No [X]", "")
p.box(L, Y + 516, 260, 30, "N  Net unrecognized Sec. 704(c) gain or (loss): Beginning / Ending", "0 / 0", align="L")
X = 306
p.set_font("Helvetica", "B", 9); p.text(X, Y - 6, "Part III  Partner's Share of Current Year Income, Deductions, Credits")
k1rows = [("1  Ordinary business income (loss)", K1["b1"]), ("2  Net rental real estate income (loss)", ""),
          ("3  Other net rental income (loss)", ""), ("4a  Guaranteed payments for services", ""),
          ("5  Interest income", K1["b5"]), ("6a  Ordinary dividends", K1["b6a"]), ("6b  Qualified dividends", K1["b6b"]),
          ("7  Royalties", ""), ("8  Net short-term capital gain (loss)", ""), ("9a  Net long-term capital gain (loss)", K1["b9a"]),
          ("11  Other income (loss)", ""), ("13  Other deductions", ""),
          ("14  Self-employment earnings (loss)", ""),
          ("19  Distributions   Code A", K1["b19a"]),
          ("20  Other information   Code Z  (Sec. 199A info - see statement)", "STMT")]
for i, (lab, v) in enumerate(k1rows):
    p.box(X, Y + i * 34, 270, 34, lab, v, big=True)
p.set_font("Helvetica", "", 7)
p.text(X, Y + len(k1rows) * 34 + 14, "*See attached statement for additional information.")
# statement page
p.add_page()
p.set_font("Helvetica", "B", 13); p.text(36, 50, f"{K1['name']}  -  EIN {K1['ein']}")
p.set_font("Helvetica", "", 10); p.text(36, 66, f"Supplemental statement to 2025 Schedule K-1 for {TP['name']} ({TP['ssn']})")
p.set_font("Helvetica", "B", 11); p.text(36, 100, "Box 20, Code Z - Section 199A Information (Statement A)")
rows = [("Activity", "RIVERBEND GROWTH PARTNERS II LP - Trade or business #1"), ("SSTB?", "No"),
        ("Ordinary business income (QBI)", "4,210.00"), ("W-2 wages", "12,940.00"), ("UBIA of qualified property", "38,500.00"),
        ("Section 199A dividends", "0.00"), ("Aggregated with other activities?", "No")]
y = 116
for a, b in rows:
    p.rect(36, y, 300, 20); p.rect(336, y, 240, 20)
    p.set_font("Helvetica", "", 9); p.text(40, y + 13, a)
    p.set_font("Courier", "B", 10); p.text(572 - p.get_string_width(b), y + 13, b)
    y += 20
p.set_font("Helvetica", "B", 11); p.text(36, y + 30, "Box 6a/6b - Dividends and Box 9a - LTCG are from portfolio investments held by the partnership.")
p.set_font("Helvetica", "", 9); p.text(36, y + 48, "Michigan: partnership is not filing a composite return on this partner's behalf. MI source income = Box 1.")
p.output(OUT / "06-K1-1065-RiverbendGrowthPartners.pdf")

# Client organizer (facts not on any info return)
p = Form("2025 Client Tax Organizer  -  Holloway", "Completed by client; returned 02/09/2026", "Organizer")
lines = [
    ("Filing status", "Married filing jointly"),
    ("Taxpayer", "Daniel R Holloway, DOB 04/22/1986, SSN XXX-XX-4417, Engineering Manager"),
    ("Spouse", "Priya S Holloway, DOB 11/03/1987, SSN XXX-XX-8032, Registered Nurse"),
    ("Address", "2418 Glenwood Ct, Ann Arbor, MI 48104 (lived here all year)"),
    ("Dependent 1", "Maya J Holloway, daughter, DOB 07/15/2016, SSN XXX-XX-2290, lived with you 12 months"),
    ("Dependent 2", "Theo A Holloway, son, DOB 03/02/2021, SSN XXX-XX-6154, lived with you 12 months"),
    ("Child care", "Little Oaks Learning Center, EIN 38-3902217, 1120 Packard St, Ann Arbor MI - $7,800 for Theo"),
    ("Dep. care FSA", "None (W-2 Box 10 is blank for both)"),
    ("Charitable - cash", "Food Gatherers $1,200 (acknowledgment letter); St. Mary Parish $2,400 (annual statement)"),
    ("Charitable - noncash", "Clothing/household to Kiwanis Thrift, FMV $420, 05/17/2025"),
    ("Estimated taxes", "Federal: none.  Michigan: none."),
    ("Prior year", "2024 federal refund $1,318 received by direct deposit; no state refund (MI refund $212 - did NOT itemize in 2024)"),
    ("HSA / IRA", "No HSA. No IRA contributions for 2025."),
    ("Health coverage", "Full-year employer coverage (Daniel's plan). No Form 1095-A."),
    ("Crypto / digital assets", "No"),
    ("Foreign accounts", "No"),
    ("Direct deposit", "Lakeshore Community CU, routing 272480678, checking acct ****6620"),
    ("Anything else?", "Priya paid $780 union dues (W-2 box 14). No other changes this year."),
]
y = 96
for a, b in lines:
    p.set_font("Helvetica", "B", 8.5); p.set_xy(36, y); p.cell(120, 12, a)
    p.set_font("Helvetica", "", 8.5); p.set_xy(156, y); p.multi_cell(420, 12, b)
    y = max(p.get_y(), y + 12) + 8
    p.line(36, y - 4, 576, y - 4)
p.output(OUT / "00-Client-Organizer-Holloway.pdf")

# ---------- answer key in OpenTax input.json shape ----------
key = {"year": 2025, "source": "synthetic", "scenario": "Holloway MFJ: 2 W-2s, 1099-INT, 1099-DIV/B, 1098, K-1 1065, 2 kids, child care",
 "forms": [
  {"node_type": "start", "data": {"general": {"filing_status": "mfj", "taxpayer_first_name": "Daniel", "taxpayer_last_name": "Holloway",
     "spouse_first_name": "Priya", "spouse_last_name": "Holloway", "address_city": "Ann Arbor", "address_state": "MI", "address_zip": "48104"}}},
  {"node_type": "w2", "data": {"employer_name": EMP_D["name"], "employer_ein": EMP_D["ein"], "box1_wages": W2_D["b1"], "box2_fed_withheld": W2_D["b2"],
     "box3_ss_wages": W2_D["b3"], "box4_ss_withheld": W2_D["b4"], "box5_medicare_wages": W2_D["b5"], "box6_medicare_withheld": W2_D["b6"],
     "box12_entries": [{"code": c, "amount": a} for c, a in W2_D["b12"]], "box13_retirement_plan": True,
     "box15_state": "MI", "box16_state_wages": W2_D["b16"], "box17_state_withheld": W2_D["b17"]}},
  {"node_type": "w2", "data": {"employer_name": EMP_P["name"], "employer_ein": EMP_P["ein"], "box1_wages": W2_P["b1"], "box2_fed_withheld": W2_P["b2"],
     "box3_ss_wages": W2_P["b3"], "box4_ss_withheld": W2_P["b4"], "box5_medicare_wages": W2_P["b5"], "box6_medicare_withheld": W2_P["b6"],
     "box12_entries": [{"code": c, "amount": a} for c, a in W2_P["b12"]], "box13_retirement_plan": True,
     "box14_entries": [{"description": "UNION", "amount": 780.0, "is_state_sdi_pfml": False}],
     "box15_state": "MI", "box16_state_wages": W2_P["b16"], "box17_state_withheld": W2_P["b17"]}},
  {"node_type": "f1099int", "data": {"payer_name": "LAKESHORE COMMUNITY CREDIT UNION", "payer_tin": "38-2093315", "box1": INT["b1"]}},
  {"node_type": "f1099div", "data": {"payerName": "NORTHPOINT BROKERAGE SERVICES LLC", "box1a": DIV["b1a"], "box1b": DIV["b1b"], "box2a": DIV["b2a"], "box7": DIV["b7"]}},
  *[{"node_type": "f1099b", "data": {"payer_name": "NORTHPOINT BROKERAGE SERVICES LLC", "description": d, "date_acquired": a, "date_sold": s,
      "proceeds": pr, "cost_basis": c, "is_long_term": lt, "noncovered_security": False}} for d, a, s, pr, c, lt in LOTS],
  {"node_type": "f1098", "data": {"lender_name": "WOLVERINE HOME LENDING NA", "box1_mortgage_interest": M["b1"], "box2_outstanding_principal": M["b2"],
     "box3_origination_date": "2021-06-14", "box10_other": M["b10_tax"]}},
  {"node_type": "k1_partnership", "data": {"partnership_name": K1["name"], "partnership_ein": K1["ein"], "box1_ordinary_business": K1["b1"],
     "box5_interest": K1["b5"], "box6a_ordinary_dividends": K1["b6a"], "box6b_qualified_dividends": K1["b6b"], "box9a_net_lt_cap_gain": K1["b9a"]}},
  {"node_type": "f2441", "data": {"provider": "Little Oaks Learning Center", "provider_ein": "38-3902217", "amount": 7800.0, "qualifying_persons": 1}},
  {"node_type": "schedule_a", "data": {"cash_contributions": 3600.0, "noncash_contributions": 420.0, "real_estate_taxes": 6214.0,
     "state_income_tax": W2_D["b17"] + W2_P["b17"]}},
 ],
 "_notes": "Field names for w2/1099/1098/k1 follow benchmark input.json + node schemas; f2441/schedule_a data keys are approximate - check the node schema before feeding to the CLI.",
}
(KEY / "holloway-opentax-input.json").write_text(json.dumps(key, indent=2))
print(f"wrote {OUT}")
