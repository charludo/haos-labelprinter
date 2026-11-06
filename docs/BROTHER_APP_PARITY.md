# Parity with the Brother apps (PT-P710BT)

Research date: 2026-11-06. Evidence is from Brother store listings, Brother support FAQs/manuals and the
printer's user's guide. Anything I could not confirm is marked **UNVERIFIED**. Brother's own web pages
were partly unreachable (403/timeouts) and I found **no Reddit threads** through search, so the
"what users miss" section rests on App Store reviews and retailer reviews only.

## 1. Executive summary (straight answer)

**No, not yet, but for a different audience we are ahead.** Brother's phone app (P-touch Design&Print 2)
is a template-driven, tap-and-go designer: templates, fonts, symbols, emoji, patterns, frames, images,
QR, text recognition from the camera and translation, cloud template storage. Our editor (per the
contract) is a free-form canvas editor with Google Fonts, MDI icons, QR, 7 barcode symbologies, images,
rectangles, and above all HA templates, variables and automations, which Brother has no equivalent for.

Gaps that matter for a home/maker user, in order: (1) serial/counter and date/time stamping as a
first-class element (we can fake date/time via `{{ now() }}` templates, but there is no printer-side
counter), (2) CSV/spreadsheet batch print, (3) ready-made templates and frames/patterns, (4) a
camera/OCR/translate path (phone-centric; low value in an HA panel), (5) mirror print, tables and
curved/vertical text. On the printer side the PT-P710BT user's guide only lists **Auto Cut, Chain
Printing, Special tape and Mirror** as print options, so there is no half cut to chase (see section 4).

Caveat: our editor status below is from the contract plus what exists in the repo; the frontend is still
being written, so "Planned in contract but unproven" means designed, not demonstrated.

## 2. Feature inventory and comparison

Status legend: **Have** = works today (driver/service level); **Planned** = in the contract, unproven;
**Not yet**; **N/A**. Effort S/M/L. Value = for an HA home/maker user (H/M/L).

| Feature | Brother app (source) | Our editor | Effort | Value |
|---|---|---|---|---|
| Layout templates / ready-made labels (home, office, ribbons, decorative tape) | D&P2: "variety of templates" for labels, decorative tapes, satin ribbons [A1]; FAQs distinguish "Create your own label" vs "Template" [S4] | Not yet (only saved designs + `print_template` service) | M | H |
| Text: fonts, size, styles | D&P2: "wide variety of fonts" [A1]; reviewers: frames shrink text, can't enlarge [A1]; no text rotation in custom labels (June 2025 review) [R1] | Planned: Google Fonts (1000+), weight, italic, auto-fit, align, line spacing, rotation, invert | already contract | H |
| Text auto-fit | Implicit; frames auto-shrink text (negative review) [A1] | Planned (`size: "auto"`) | - | H |
| Vertical / rotated text | Only in prebuilt templates (review) [R1]; **UNVERIFIED** in editing UI | Planned: rotation 0/90/180/270 on any element. Stacked-letter vertical text: Not yet | S | L |
| Curved/arched text, text on tables | P-touch Editor 5.x has tables [S6]; app: **UNVERIFIED** | Not yet | M-L | L |
| Symbols, emoji, patterns | D&P2 [A1] | Planned: MDI icon glyphs (7000+, monochrome). No emoji, no patterns | M | M |
| Frames / borders | D&P2 frames [A1]; Brother FAQ lists "cannot use Frame function" problems [S5] | Planned partly: `rect` element can draw a border by hand; no frame presets/decorative borders | S-M | M |
| Barcodes | D&P2 listing does not mention barcodes (**UNVERIFIED** in D&P2); iPrint&Label: Code39/Code128/EAN13/GS1-128 added in 5.3.1 [S7]; user's guide says iPrint&Label creates barcodes [S2] | Planned: code128, code39, ean13, ean8, upca, itf, codabar (more symbologies than the app evidence shows). GS1-128 not planned | - | H |
| QR codes | D&P2: QR via "Share label" to share links, "PT-P910BT/P710BT only" [A1]; review: cannot add QR outside prebuilt templates [R1] | Planned (`qr`, ecc l/m/q/h, data from variables) | - | H |
| Images / logos / photos | D&P2: insert images and logos [A1]; review says could not import an image [R1] (conflicting, UNVERIFIED) | Planned (`image`, PNG/JPEG data URI, dither). No camera capture, no crop tool, no threshold slider | M | M |
| Text recognition (OCR) from camera | D&P2 2.x "What's new": scan and insert text, PT-P910BT/P710BT only [A1]; Android listing wording differs (CUBE XP/Plus) [A2, per search snippet] | Not yet | M-L | L (phone workflow; could use browser camera + server OCR) |
| Translation of text | D&P2: translate scanned or typed text, P910BT/P710BT only [A1] | Not yet | M | L |
| Serial numbering / auto-increment | **UNVERIFIED** for D&P2 and iPrint&Label (nothing found). Brother points other models to "Pro Label Tool" [S7]; P-touch Editor 5.x Windows: **UNVERIFIED** | Not yet (no counter). Workaround: HA `counter` helper in a template | S-M | M |
| Date/time stamp | iPrint&Label 5.0: auto date/time at print and calculated future dates ("use by") [S7]; D&P2: **UNVERIFIED** | Have via templates (`{{ now().strftime(...) }}`, with offsets via `timedelta`), resolved at print time | S (UI helper) | H |
| Database / CSV / Excel merge | P-touch Editor 5.x: Excel/Access/SQL database connect and print [S6]; phone apps: **UNVERIFIED** (not seen) | Not yet (can loop in an automation calling `print_template`) | M | M-H |
| Print from contacts / address book | **UNVERIFIED** for P710BT apps | Not applicable (not HA's domain) | - | L |
| Multiple pages / multi-label jobs | D&P2: multiple labels per job, Cut Options apply across them [S3]; exact UI **UNVERIFIED** | Have in driver (strips: several labels in one job, `copies`, `cut_each`); editor itself is one design = one label. Not yet: multi-page documents in the editor | M | M |
| Tape length: auto / fixed | D&P2 has a [Tape length] setting, min 25 mm [S3] | Planned (`length_mm` null=auto or fixed) | - | H |
| Margins | D&P2 Cut Options, "Cut the last label" and margin tricks [S3]; user's guide: margin adjustment reduces leading blank [S2] | Have (`margin_mm`, ESC i d) | - | H |
| Auto cut | Yes; PT-P710BT guide lists Auto Cut [S2] | Have (`auto_cut`, `cut_each`) | - | H |
| Full cut vs chain printing (don't cut last label) | "Chain Printing: save tape by not cutting the last label" [S2]; D&P2 "Cut the last label" toggle [S3] | **Deliberately not offered**: our hardware tests showed chain printing leaves the last page in the printer. We instead merge jobs into one strip ("Saving tape" in README) | - | - |
| Half cut | iPrint&Label cut-options table has a half-cut column with footnote "models that do not support half cut", PT-P710BT check mark ambiguous [S8]; the PT-P710BT user's guide lists only Auto Cut, Chain, Special tape, Mirror [S2]; ESC i K bit 2 = half cut in a third-party protocol reference [S9]. **Treat as UNVERIFIED / probably unsupported on the P710BT** | Not yet | S to probe | L |
| Cut mark / cut line / "pause to cut" | iPrint&Label table mentions "Pause to cut" and cut marks for some models [S8]; which models: **UNVERIFIED** (page text garbled). Brother user's guide: "Special tape" = feed for manual cutting [S2] | Not yet. Doable in our renderer as a printed dotted line/tick at label edges regardless of the printer (no protocol needed) | S | M |
| Special tape (fabric, extra-strength: no cut) | Special tape option [S2] | Not yet (ESC i K bit 4, per official PT-P700 raster doc [S9a]) | S | L-M |
| Mirror print | Printer option "Mirror Printing" [S2]; App Store reviewer asks to mirror images/clipart [R1] | Not yet in UI (driver has orientation flip for calibration; ESC i M bit 7 is the protocol mirror [S9a]). Needed for window/iron-on/heat-shrink use | S | M |
| Print preview | D&P2: "preview the final design before printing" [A1] | Planned: server-rendered 1:1 preview PNG (truthful to the printer) | - | H |
| Copies | Yes (standard); D&P2 exact UI **UNVERIFIED** | Have (`copies` 1..20) | - | H |
| Tape auto-detection | Phone apps read tape from printer (**UNVERIFIED** in text, standard Brother behaviour) | Have (status polling; "from printer" tape default) | - | H |
| Tape colour / media type awareness (laminated, heat-shrink etc.) | D&P2: colour options limited to Brother's official ones (review) [R1]; half cut unavailable on heat-shrink/non-laminated on other models [S8b] | Have as sensors (tape type and colour). Editor does not yet warn on heat-shrink length/ratio or colour mismatch | S | M |
| Saved label history / local storage | Yes in app (**UNVERIFIED** detail) | Planned (HA `Store`, list/open/duplicate/delete) | - | H |
| Cloud storage and sharing templates | D&P2 "Cloud Storage: upload, reuse and share templates" [A1] | Partly: HA backups cover designs. Export/import design JSON: Not yet | S | M |
| Share label QR (share a label as link) | D&P2 [A1] | Not applicable | - | L |
| Siri/Shortcuts / widgets | **UNVERIFIED**, not found | Better: HA services work with any automation, Siri via HA | - | - |
| Bluetooth to phone | App prints over Bluetooth [A1]; users report re-pairing, disconnects [R2] | Different (USB/BT/bridge from HA host) | - | - |
| Tables, drawing, shapes | P-touch Editor 5.x: tables [S6]; app shapes: **UNVERIFIED** | Planned: rect/line only | M | L |
| Undo/redo, alignment, snapping | Review: moving elements with a finger is "imprecise" [R3] | Planned: arrow-key nudge, snapping, undo/redo | - | M |
| Desktop editor features (P-touch Editor 5.x: layouts Express/Professional/Snap, screen capture, drag-and-drop, cable labelling wizard) | PT-P710BT guide: USB only for computers, no Bluetooth to PC [S2] | Not applicable except Cable/flag labels, see backlog | M | M |

## 3. Where we are ahead

* **HA state in labels**: `{{ states('sensor.x') }}`, `now()`, attributes, any HA template, resolved server-side before rendering. Brother has nothing comparable.
* **Automations and scripts**: print on a trigger (shopping list item added, battery low, expiry reminders, door left open) via `print_text`, `print_qr`, `print_image`, `print_template` services.
* **Reusable templates with variables**: one saved design plus `variables` per call; no per-label retyping.
* **Google Fonts and MDI icons**: ~1000+ families with weights/italics, 7000+ icons, versus Brother's fixed font and symbol sets. Fonts are fetched once and cached.
* **Tape saving by batching**: requests within a window merge into one strip, one leader, one cut (the printer wastes ~25 mm of leading blank tape [S2]).
* **Server-side single renderer**: preview and print share the same Python renderer, so what you see is what prints; the Brother apps can differ between preview and output (frames shrinking text, truncated labels [A1]).
* **Dynamic barcode/QR**: data from automations (URLs, IDs, entity values); more barcode symbologies than the app evidence shows.
* **Works on a desktop browser with keyboard, precise numeric x/y/w/h**, versus a finger-driven phone UI that reviewers call imprecise [R3].
* **No account, no cloud, no re-pairing on each use**, versus App Store complaints [A1].

## 4. Prioritized backlog (top 10)

Printer capability baseline for the PT-P710BT: the user's guide lists exactly four print options (Auto Cut, Chain Printing, Special tape, Mirror) [S2]. The official PT-P700 raster reference defines ESC i M bit 6 auto cut, bit 7 mirror, ESC i K bit 3 no-chain, bit 4 special tape (no cutting) [S9a]; a third-party reference also lists bit 2 as half cut with no model limits stated [S9]. **Half cut on the PT-P710BT is UNVERIFIED and not recommended** without a hardware test (and Brother notes half cut is unavailable on heat-shrink/non-laminated tapes on other models [S8b]). Chain-based features are risky: our tests showed the last page stays in the printer.

1. **Date/time and counter helpers (S-M, value H).** Add a "dynamic text" inserter in the inspector that writes template snippets (`{{ now().strftime('%d.%m.%Y') }}`, `{{ (now()+timedelta(days=7)) }}`) and a counter variable backed by an HA `input_number`/`counter` entity or a design-stored `counter` that the backend increments on each print (new key in design JSON `variables`, increment in `editor_api` after a successful print). No printer feature needed.
2. **Batch print from CSV / list (M, value M-H).** New WS command `print_batch` and service `print_template_batch` taking `rows: [{var: value}]` (or pasted CSV in the panel); backend renders each row, passes all images to `build_job` so they land in one strip (cut_each optional). Uses the existing batching so tape waste stays low. Panel: a "Data" tab with a paste/upload table and preview of row N.
3. **Template gallery (M, value H).** Ship 10-20 built-in designs (spice jar, cable flag, box label with QR, shelf/bin, name tag, battery date, wifi QR, asset tag with barcode, plant tag) as JSON in the frontend/backend, with a "New from template" flow; add per-tape-width scaling (dots depend on tape pins). No protocol work.
4. **Mirror print and flip options (S, value M).** Add `mirror` design flag applied in the renderer (flip x) so it works regardless of firmware, with the protocol ESC i M bit 7 as an alternative; needed for window and iron-on or reversed-adhesive uses. Add a warning when used with non-reversible content.
5. **Frames, borders and cut lines (S-M, value M).** Add `frame` presets (rounded rect, double, dashed, decorative corner via MDI glyphs) as a new element or a design-level option, plus an optional printed "cut line/tick" at both ends (a thin dashed bar drawn in the margin). This gives cut-mark behaviour without chain printing or half cut, so it is safe with our single-job strategy.
6. **Design import/export and sharing (S, value M).** `designs/export` and `designs/import` WS commands (JSON file download/upload in the panel), plus a "copy as YAML for service call" button producing a ready `print_template` snippet with variables. Covers Brother's cloud sharing for a self-hosted audience.
7. **Mirror/special tape and tape-aware warnings (S, value M).** Expose `special_tape` (no cut, ESC i K bit 4) for fabric/strong adhesive tapes, and add preview warnings from tape status: heat-shrink needs minimum length and ratio, text colour, laminate vs non-laminate, minimum 25 mm label length [S3] (the Brother FAQ shows users hit this).
8. **Images: crop, threshold, invert and clip-art search (M, value M).** Extend `image` with `threshold`, `invert`, a crop box, and Iconify/Openclipart-style search through the allow-listed hosts only (requires host-list change in the contract). Server-side dithering already planned.
9. **Camera/OCR text input (M-L, value L-M).** Browser `<input capture>` to upload a photo, backend OCR (optional dependency, e.g. Tesseract, behind a config switch) returning text to insert; mirrors Brother's text recognition for the P710BT [A1]. Add translation only if a local engine is acceptable; otherwise skip.
10. **Multi-label documents and tables (M-L, value M).** Let one design hold several "pages" (labels) printed in one strip with a per-page cut, and a simple table/grid element for spec labels (cell text, row/column rules). The driver already composes strips, so the work is in JSON schema, renderer and UI.

Spike worth doing before backlog item 5/7: one hardware test of ESC i K bit 2 (half cut) and bit 4 (special tape) on the real P710BT; ignore half cut if no visible half-cut occurs.

## 5. Sources

* [A1] App Store, P-touch Design&Print 2: https://apps.apple.com/gb/app/brother-p-touch-design-print-2/id1468451451 (v2.8.1, 4.7 of 5 from 746 ratings; reviews quoted)
* [A2] Google Play and APKMirror release notes (Android feature wording; not fetched in full, from search snippets): https://www.apkmirror.com/apk/brother-industries-ltd/p-touch-designprint-2/
* [S2] PT-P710BT User's Guide: https://download.brother.com/welcome/docp100362/pt-p710bt_eng_ug_03.pdf (print options, 25 mm leading blank, apps, no BT to PC)
* [S3] Brother FAQ, "I want my printer to use less tape for each label (Design&Print / Design&Print 2)": https://support.brother.com/g/b/faqend.aspx?c=us&lang=en&prod=p710bteus&faqid=faqp00100302_000 ; "The printer stops while printing, or the tape is cut in the middle of the text": https://support.brother.com/g/b/faqend.aspx?c=sg&lang=en&prod=p710bteas&faqid=faqp00010402_003 ; "The printer feeds more tape than required (Design&Print 2)": https://support.brother.com/g/b/faqend.aspx?c=gb&lang=en&prod=p710bteuk&faqid=faqp00100539_000 (all read via search summaries, not fetched in full)
* [S4] Brother FAQs on templates (PT-P710BT): https://www.brother.co.za/en/support/pt-p710bt/faqs?cate=10036
* [S5] Brother FAQ, cannot select printer / Frame function issues: https://support.brother.com/g/b/faqend.aspx?c=us&lang=en&prod=p710bteus&ftype3=100125&faqid=faqp00100353_000&pfs=1
* [S6] P-touch Editor 5.x FAQs (database, Excel, tables, barcode): https://www.brother.com.au/en/support/pt-p710bt/faqs?cate=10033 (read via search summary)
* [S7] iPrint&Label 5.0 news (date/time, calculated dates): https://www.brother.co.uk/about-brother/news/2017/improved-app-means-business-for-customers ; app listing: https://apptopia.com/ios/app/523047493/about
* [S8] iPrint&Label cut options: https://help.brother-usa.com/app/answers/detail/a_id/183293/~/cut-options---iprint&label (table text garbled; PT-P710BT column UNVERIFIED)
* [S8b] Cut options table for PT-E310BT (half cut unavailable on iron-on, heat-shrink, non-laminated): https://support.brother.com/g/s/es/htmldoc/ptouch/e310bt/usen/html/GUID-AF5EC619-F03F-4892-8B10-282282A658B3_1.html
* [S9] Third-party PT raster protocol (ESC i K bit table): https://thermal-label.github.io/brother-ql/protocol/pt
* [S9a] Official PT-P700 raster command reference (mirror, chain, special tape bits; no half-cut bit on the page read): https://www.manualsdir.com/manuals/374153/brother-pt-p700.html?page=37 ; Brother PDF https://download.brother.com/welcome/docp000771/cv_ptp700_jpn_raster_101.pdf (Japanese; not read)
* [R1] App Store review "June 2025" (templates fixed, no text rotation, no QR/images outside templates) and "Please add an option to mirror images/clipart" (2022): quoted on [A1] and via search summary of https://apps.apple.com/us/app/brother-p-touch-design-print-2/id1468451451
* [R2] App Store review "Very lazily done" (2024), on [A1]
* [R3] Sam's Club customer reviews of the PT-P710BT: https://www.samsclub.com/reviews/product/13850822360?page=2
* PT-P710BT product pages: https://www.brother.ca/p/PTP710BT ; brochure https://cdn.shopify.com/s/files/1/0648/4354/6883/files/PT-P710BT_Brochure.pdf (UNVERIFIED, not read)

Not found or not verifiable: Reddit/forum threads; Design&Print 2 serial numbering, date/time and barcode support; Siri/Shortcuts; whether the P710BT supports half cut or "pause to cut".
