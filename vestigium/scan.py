"""Scanned documents (PDFs and photos) -> text with confidence -> the same intake pipeline.

Stage 1 (vision model): transcribe every page, record by record, and say how sure it is. It transcribes; it never judges.
Stage 2: the transcript goes through intake.analyze (reader -> graph -> rule engine). The engine still decides.
Confidence is carried through to the verdict: if a finding (or a clean verdict) rests on a record that was read with low
confidence, the answer says which record and page to check against the original instead of guessing silently.

render_scan() makes synthetic test scans (stamps, handwriting-style notes, blur, rotation, JPEG damage) from our dossiers.
"""
import io, os, random, re, textwrap
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .extract import split_records

W, H, M = 1240, 1754, 110                      # A4 at 150 dpi
URW = "/usr/share/fonts/opentype/urw-base35/"
FONTS = dict(body=URW + "C059-Roman.otf", bold=URW + "C059-Bold.otf", hand=URW + "Z003-MediumItalic.otf", stamp=URW + "NimbusMonoPS-Bold.otf")
DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
TIERS = ("pdf", "phone", "poor")


def _font(kind, size):
    try: return ImageFont.truetype(FONTS[kind] if os.path.exists(FONTS[kind]) else DEJAVU, size)
    except Exception: return ImageFont.load_default()


def _wrap(draw, text, font, width):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= width: cur = t
        else: lines.append(cur); cur = w
    return lines + ([cur] if cur else [])


def _annotation(img, xy, iso, style, rng):
    """A clerk's stamp or a handwritten 'Recd' note carrying the recording date, drawn on its own layer and rotated."""
    y, m, d = iso.split("-")
    layer = Image.new("RGBA", (420, 150), (0, 0, 0, 0)); g = ImageDraw.Draw(layer)
    if style == "stamp":
        f = _font("stamp", 30); col = (190, 30, 40, 200)
        g.rectangle([4, 4, 300, 100], outline=col, width=4); g.text((22, 12), "RECORDED", font=f, fill=col); g.text((22, 54), iso, font=f, fill=col)
    else:
        f = _font("hand", 46); col = (25, 50, 150, 230)
        g.text((6, 30), f"Recd {int(d)} {MONTHS[int(m)-1]} {y}", font=f, fill=col)
    layer = layer.rotate(rng.uniform(-9, 9), expand=True, resample=Image.BICUBIC)
    img.paste(layer, xy, layer)


def render_pages(records, seed=0):
    """records: [(id, body, recorded_iso|None)] -> list of page images. The recording date appears ONLY as a stamp or handwriting."""
    rng = random.Random(seed)
    pages, img, draw, y = [], None, None, M

    def new_page():
        nonlocal img, draw, y
        img = Image.new("RGB", (W, H), (246, 244, 238)); draw = ImageDraw.Draw(img); y = M
        draw.text((M, 50), "OFFICE OF THE RECORDER · FICTIONAL COUNTY · SYNTHETIC DOCUMENT", font=_font("bold", 20), fill=(90, 90, 90))
        pages.append(img)

    new_page(); body_f, bold_f = _font("body", 27), _font("bold", 27)
    for rid, body, rec in records:
        lines = _wrap(draw, body, body_f, W - 2 * M - 250)
        need = 44 + len(lines) * 38 + 70
        if y + need > H - M: new_page()
        draw.text((M, y), f"Ref. {rid}", font=bold_f, fill=(20, 20, 20)); y += 44
        for ln in lines:
            draw.text((M, y), ln, font=body_f, fill=(25, 25, 25)); y += 38
        if rec: _annotation(img, (W - M - 330 + rng.randint(-20, 20), y - 120 + rng.randint(-10, 20)), rec, rng.choice(["stamp", "hand"]), rng)
        draw.line([M, y + 22, W - M, y + 22], fill=(190, 190, 190), width=1); y += 60
    for i, p in enumerate(pages, 1):
        ImageDraw.Draw(p).text((W // 2 - 60, H - 70), f"Page {i} of {len(pages)}", font=_font("body", 22), fill=(110, 110, 110))
    return pages


def degrade(img, tier, rng):
    a = img
    if tier == "pdf":
        sigma, blur, ang, scale, q = 4, 0.0, rng.uniform(-0.4, 0.4), 1.0, None
    elif tier == "phone":
        sigma, blur, ang, scale, q = 8, 1.1, rng.uniform(-3.5, 3.5), 0.7, 55
    else:
        sigma, blur, ang, scale, q = 16, 2.0, rng.uniform(-5.5, 5.5), 0.5, 30
    a = a.rotate(ang, expand=True, fillcolor=(120, 118, 112) if tier != "pdf" else (246, 244, 238), resample=Image.BICUBIC)
    if blur: a = a.filter(ImageFilter.GaussianBlur(blur))
    if scale < 1: a = a.resize((int(a.width * scale), int(a.height * scale)), Image.BILINEAR)
    arr = np.asarray(a).astype(np.float32)
    if tier != "pdf":                                              # uneven lighting, like a shadow across a phone photo
        grad = np.linspace(rng.uniform(.72, .9), 1.0, arr.shape[1])[None, :, None]
        arr = arr * (grad if rng.random() < .5 else grad[:, ::-1])
    arr += np.random.default_rng(rng.randint(0, 10**6)).normal(0, sigma, arr.shape)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)), q


def _strip_recorded(text):
    """', recorded 2016-11-18' moves out of the typed body and onto the stamp."""
    m = re.search(r",? recorded (\d{4}-\d{2}-\d{2})", text)
    return (text.replace(m.group(0), "", 1), m.group(1)) if m else (text, None)


def render_scan(dossier_text, tier="phone", seed=0):
    """Dossier text -> [(filename, mime, bytes)]: one PDF for tier 'pdf', one JPEG per page for 'phone' / 'poor'."""
    recs = []
    for rid, s in split_records(dossier_text):
        body, rec = _strip_recorded(s)
        recs.append((rid, body, rec))
    rng = random.Random(f"{seed}-{tier}")
    pages = []
    for p in render_pages(recs, seed):
        im, q = degrade(p, tier, rng); pages.append((im, q))
    if tier == "pdf":
        buf = io.BytesIO(); pages[0][0].save(buf, "PDF", save_all=True, append_images=[p for p, _ in pages[1:]], resolution=150)
        return [("dossier.pdf", "application/pdf", buf.getvalue())], recs
    out = []
    for i, (im, q) in enumerate(pages, 1):
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=q); out.append((f"page{i}.jpg", "image/jpeg", buf.getvalue()))
    return out, recs


# ---------------------------------------------------------------- stage 1: vision transcription with confidence
PROMPT = """You are transcribing scanned legal records (PDF pages or photos). Copy what is printed, stamped or handwritten. Do NOT judge validity, and do NOT fix or guess unclear text.

Return ONE JSON object: {"pages": [{"page": 1, "records": [ ... ]}]}. Each record is one block headed "Ref. <id>":
{"id": "<the id after Ref.>", "text": "<the typed text of the record, verbatim>", "annotation": "<text of any stamp or handwritten note on or next to it, verbatim, or null>",
 "annotation_date": "<the date in the annotation as ISO yyyy-mm-dd, or null>", "confidence": "high" | "medium" | "low",
 "unsure": [{"what": "<which date, name or number>", "why": "<e.g. blurred digit, stamp overlaps text, smudge>"}]}
Confidence is "low" if any DATE, NAME, AMOUNT or NUMBER in the record is hard to read or you had to guess a character; "medium" if you are fairly sure but something is faint;
"high" only if every character is clear. When unsure about a character write what you think it is AND list it in "unsure". Never silently correct a typo you can see.
Dates in typed text keep the form printed. Reply with the JSON object only."""


def transcribe(files):
    from . import llm
    ans, st = llm.ask_vision("You transcribe documents faithfully and report how sure you are. You never judge legality.", PROMPT, files)
    return ans, st


# ---------------------------------------------------------------- stage 1b: an independent second read
# A model's own confidence turned out to be unreliable on poor photos (it was confidently wrong). So we read every scan twice,
# the second time asking only for the facts that matter (dates and names), and flag any record where the two reads disagree.
# The check is deterministic; it does not depend on the model knowing it is wrong.
CHECK_PROMPT = """Read these scanned legal records again. For each record headed "Ref. <id>", list:
- "dates": every date that appears anywhere in that record, including in stamps and handwritten notes, each as ISO yyyy-mm-dd;
- "names": every person or company name in it, copied exactly as printed.
Do not judge anything. Return ONE JSON object: {"records": [{"id": "<id>", "dates": ["yyyy-mm-dd", ...], "names": ["...", ...]}]}"""
ISO = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def second_read(files):
    from . import llm
    return llm.ask_vision("You list the dates and names in documents exactly as they appear. You never judge legality.", CHECK_PROMPT, files, temperature=0.4)


def _norm(n):
    return re.sub(r"[^a-z]", "", str(n).lower())


def cross_check(text, ans2):
    """Compare the first read (transcript text) with the second read. Returns {record id: [what disagrees]}."""
    from collections import Counter
    from .extract import split_records
    first = dict(split_records(text))
    out = {}
    for r in (ans2 or {}).get("records", []):
        rid = str(r.get("id") or "")
        if rid not in first: continue
        t = first[rid]
        d1 = Counter(ISO.findall(t)); d2 = Counter(x for x in (r.get("dates") or []) if ISO.fullmatch(str(x)))
        diffs = []
        for d in sorted((d1 - d2).keys() | (d2 - d1).keys()):
            other = [x for x in (d2 - d1) if x != d] if d in d1 else [x for x in (d1 - d2) if x != d]
            diffs.append(dict(what=f"date {d}", why="the two independent reads disagree" + (f" ({' / '.join(sorted({d, *other}))})" if other else "")))
        flat = _norm(t)
        for n in r.get("names") or []:
            if len(_norm(n)) >= 4 and _norm(n) not in flat:
                diffs.append(dict(what=f"name {n}", why="the second read saw a name the first read did not"))
        if diffs: out[rid] = diffs
    return out


def transcript_text(ans):
    """Stage 1 JSON -> dossier text for stage 2 (the recording stamp becomes ', recorded <date>' after the first date)."""
    out, low, flags = [], {}, []
    for pg in (ans or {}).get("pages", []):
        for r in pg.get("records", []):
            t = " ".join(str(r.get("text") or "").split())
            ad = r.get("annotation_date")
            if ad and re.match(r"^\d{4}-\d{2}-\d{2}$", str(ad)):
                t2 = re.sub(r"((?:dated|died on) \d{4}-\d{2}-\d{2})", rf"\1, recorded {ad}", t, count=1)
                t = t2 if t2 != t else f"{t} Recorded {ad}."
            out.append(f"[{r.get('id')}] {t}")
            conf = r.get("confidence", "low")
            if conf in ("low", "medium") or r.get("unsure"):
                flags.append(dict(id=r.get("id"), page=pg.get("page"), confidence=conf, unsure=r.get("unsure") or []))
            if conf == "low": low[r.get("id")] = pg.get("page")
    return "\n\n".join(out), low, flags


def scan_analyze(files, as_of=None, transcriber=None, checker=None):
    """Full pipeline for an upload. Carries read-confidence, and disagreement between two reads, through to the verdict.
    checker: the second reader; defaults to a real second read when the first read is real (tests pass their own or none)."""
    from .intake import analyze
    ans, st = (transcriber or transcribe)(files)
    if not ans or not ans.get("pages"):
        return dict(error="The scanner could not read those pages. Try a clearer photo or a PDF.")
    text, low, flags = transcript_text(ans)
    checker = checker if checker is not None else (None if transcriber else second_read)
    disagree, st2 = {}, {}
    if checker:
        try:
            ans2, st2 = checker(files)
            disagree = cross_check(text, ans2)
        except Exception as e:                                   # no second read: say so, never pretend it agreed
            disagree, st2 = {}, dict(error=str(e)[:80])
    page_of = {r.get("id"): pg.get("page") for pg in ans.get("pages", []) for r in pg.get("records", [])}
    for rid, diffs in disagree.items():                          # a disagreement counts as LOW confidence, whatever the model said
        low[rid] = page_of.get(rid)
        f = next((f for f in flags if f["id"] == rid), None)
        if f: f.update(confidence="low", unsure=f["unsure"] + diffs, disagree=True)
        else: flags.append(dict(id=rid, page=page_of.get(rid), confidence="low", unsure=diffs, disagree=True))
    out = analyze(text, reader="auto", as_of=as_of)
    if out.get("error"): return out
    cited = {p for pr in out.get("proof", []) for p in pr.get("passages", [])}
    notes = []
    for rid, pg in low.items():
        if rid in cited:
            notes.append(f"The verdict rests on record {rid} (page {pg}), which was read with LOW confidence" + (" (two independent reads disagree)" if rid in disagree else "") + ": check it against the original.")
        elif not cited:
            pass
    if not cited and low:
        notes.append("The verdict is CLEAN, but " + ", ".join(f"{r} (page {p})" for r, p in low.items()) + " were read with low confidence: check them against the originals before relying on it.")
    for f in flags:
        if f["confidence"] == "medium" and f["id"] in cited:
            notes.append(f"Record {f['id']} (page {f['page']}) was read with medium confidence and the verdict rests on it.")
    if checker and st2.get("error"):
        notes.append("The second, independent read failed, so this scan was read only once: check the key dates against the original.")
    t2 = st2.get("tokens", 0)
    out.update(scan=dict(pages=len(ans["pages"]), transcript=text, flags=flags, low_confidence=low, disagree=sorted(disagree), double_read=bool(checker) and not st2.get("error"),
                         tokens=st.get("tokens", 0) + t2),
               warnings=out.get("warnings", []) + notes, tokens=out.get("tokens", 0) + st.get("tokens", 0) + t2)
    return out
