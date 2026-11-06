# Label templates

`custom_components/brother_ptouch/ptouch/templates.py` ships 35 ready-made label designs
(version `TEMPLATE_VERSION = 1`). Each is a function of the tape height, so one definition renders
correctly at 3.5 mm (24 dots) up to 24 mm (128 dots). Content uses `{{ variable }}` placeholders
with defaults, so a template previews well straight away.

## Research: what people label

Findings from Brother's own pages, label-maker guides, forums and Home Assistant community threads.
Many sources are marketing or SEO pages; the Reddit/forum hits were short comments, so this shows
habits, not a survey. Typical tape is a judgement for TZe tapes (12 mm is the "all-round" width).

| Use case | Typical tape | Content needed | Source |
|---|---|---|---|
| Pantry jars, canisters, bins | 12 / 18 | name, optional icon | [Brother pantry/kitchen](https://brother-usa.com/ptouch/essentials/diy-projects/kitchen-storage) |
| Spice jars | 12 | name + note | [Brother](https://brother-usa.com/ptouch/essentials/diy-projects/kitchen-storage), [organized-home](https://www.organized-home.com/posts/7-ways-label-spice-jars/) |
| Freezer food with date | 12 / 18 | name, date, portions | [Brother kitchen](https://www.brother-usa.com/ptouch/essentials/diy-projects/kitchen-storage), [kitchen handbook](https://www.momskitchenhandbook.com/why-tape-is-my-new-favorite-kitchen-tool) |
| Leftovers / use-by | 9-12 | date | same |
| Storage bins, drawers, shelves | 12-24 | title, contents, number, QR | [Brother storage](https://www.brother-usa.com/ptouch/essentials/diy-projects/storage), [Brother home](https://www.brother-usa.com/PTouch/Ptouch-Home) |
| Seasonal / moving boxes | 18-24 | title, contents | [Brother P-touch Home](https://www.brother-usa.com/PTouch/Ptouch-Home) |
| Binder / file spines, folders | 12-24 | title, year | [Brother Life Labeled](https://www.brother-usa.com/ptouch/life-labeled) (filing, home office) |
| Cable labels (flag / wrap) | 6-12 | name | [GroupDIY thread](https://groupdiy.com/threads/cable-label-maker-in-2024-brother-p-touch.88653), [eWEEK](https://www.eweek.com/de/reviews/you-ve-got-to-label-label-label-your-cable-cable-cable/) |
| Patch panel / port labels | 9-12 | port no., destination | [Mike Holt forum](https://forums.mikeholt.com/threads/panel-labeling-software.54512/post-54512) |
| Homelab: drives, component drawers, ethernet/HDMI/USB | 9-12 | hostname, IP, part value | Reddit homelab comments via search results (see above) |
| Breaker panel / fuse box / switches | 6-12 | circuit number, what it feeds | [Brother fuse box](https://www.brother-usa.com/ptouch/essentials/diy%20projects/fuse%20box), [Holt forum](https://forums.mikeholt.com/threads/panel-labeling-software.54512/post-54512) |
| Guest Wi-Fi + appliance guides | 18-24 | SSID, password, QR | [Brother-adjacent guide](https://inspiration.brother.ca/how-i-organized-my-home-with-the-brother-p-touch-400-ad-labeller) |
| Workshop, garage, tools, garden | 12-18 | name, "property of" | [Brother Life Labeled](https://www.brother-usa.com/ptouch/life-labeled) |
| Plant / garden markers (laminated tape outdoors) | 12 | plant name, watering | [The Home I Have Made](https://thehomesihavemade.com/best-tools-and-supplies-for-making-labels/) |
| Kids' belongings and name labels | 6-12 | name | [The Organized Mama](https://www.theorganizedmama.com/how-to-make-labels-for-organizing) |
| Mailbox, door, name/return address | 9-18 | name, address | [Dummies: 10 ways to label](https://dummies.com/article/10-ways-to-label-anything-and-everything-267716) |
| Asset tags / UPC barcodes / inventory | 12-18 | Code 128 ID, owner | [Brother Life Labeled](https://www.brother-usa.com/ptouch/life-labeled) (asset tracking, UPC), [HomeBox discussion](https://github.com/hay-kot/homebox/discussions/273) |
| Electronics parts bins, project boxes | 12 | value, part type, version | Reddit homelab comment (drawers), maker practice |
| 3D-printer filament spools | 12-18 | material, colour, temps | maker practice (no strong web source found) |
| Safety / warning / fragile / shut-off valves | 9-18 | text, icon | [Brother Life Labeled](https://www.brother-usa.com/ptouch/life-labeled) (signage) |
| Smart-home devices: name, entity, IEEE, QR | 12 | name, ID, QR | [HA community label printing](https://community.home-assistant.io/t/food-labels-via-a-dymo-label-printer/701986), [HA Label Studio](https://community.home-assistant.io/t/ha-label-studio-print-dymo-labels-directly-from-ha/1026914) |
| Battery type + date installed | 12 | type, date | general practice |
| Key tags, daily reminders (neutral text) | 9-12 | name / when + note | general practice |

Takeaways: (1) 12 mm is the workhorse; 6-9 mm for cables, ports and breakers, 18-24 mm only when a
QR code or a spine needs the height. (2) Most labels are "one big word + one small line"; dates,
numbers and QR/barcodes are the second most common content. (3) HA users repeat the same set:
devices (name/entity/IEEE QR), network gear, Wi-Fi QR, battery dates, breaker and valve labels.

## Design rules used by the templates

* 1-bit output: solid black fills, heavy font weights (Roboto 800, Roboto Condensed 800, Roboto Mono 700,
  Roboto Slab 800, Permanent Marker), no text box shorter than 19 dots per line (letters >= ~14 dots).
* QR modules are at least 3 dots (QR quiet zone 0, the white label margin serves as quiet zone);
  default QR payloads are short so they fit a 12 mm tape. Longer payloads need wider tape.
* Single-line templates support all tapes (3.5 mm included); two-line layouts need >= 12 mm; QR codes
  with long payloads (Wi-Fi, URL) need >= 18 mm (`tapes` says so).
* Only characters in the Latin subset are used (the asset manager downloads Latin glyphs only), so no
  arrows or Greek letters in default text.

## Catalogue

Tape 3.5 is reported by the printer as `4`; the API uses `4`.

| id | Name | Category | Tapes (mm) | Variables |
|---|---|---|---|---|
| `pantry-jar` | Pantry jar | Kitchen & Food | 3.5, 6, 9, 12, 18, 24 | `name` |
| `spice-jar` | Spice jar | Kitchen & Food | 12, 18, 24 | `name`, `note` |
| `freezer-date` | Freezer food | Kitchen & Food | 12, 18, 24 | `name`, `date`, `portions` |
| `use-by` | Use by / leftovers | Kitchen & Food | 9, 12, 18, 24 | `date` |
| `storage-bin-qr` | Storage bin with QR | Home & Storage | 12, 18, 24 | `code`, `title`, `contents` |
| `drawer-shelf` | Drawer / shelf | Home & Storage | 6, 9, 12, 18, 24 | `number`, `name` |
| `storage-box` | Storage box | Home & Storage | 12, 18, 24 | `title`, `sub` |
| `key-tag` | Key tag | Home & Storage | 9, 12, 18, 24 | `name` |
| `plant-marker` | Plant marker | Home & Storage | 12, 18, 24 | `name`, `water` |
| `daily-reminder` | Daily reminder | Home & Storage | 12, 18, 24 | `when`, `note` |
| `cable-flag` | Cable flag | Cables & Network | 6, 9, 12, 18 | `name` |
| `patch-port` | Patch panel port | Cables & Network | 6, 9, 12, 18, 24 | `port`, `dest` |
| `network-device` | Network device | Cables & Network | 12, 18, 24 | `host`, `ip` |
| `wifi-qr` | Wi-Fi guest label | Cables & Network | 18, 24 | `ssid`, `password` |
| `breaker` | Breaker / fuse | Cables & Network | 6, 9, 12, 18, 24 | `no`, `name` |
| `component-bin` | Component bin | Electronics & Maker | 12, 18, 24 | `value`, `kind` |
| `filament-spool` | Filament spool | Electronics & Maker | 12, 18, 24 | `material`, `color`, `temps` |
| `test-tag` | Tested / inspected | Electronics & Maker | 12, 18, 24 | `status`, `date`, `who` |
| `project-tag` | Project / version | Electronics & Maker | 9, 12, 18, 24 | `name`, `version` |
| `file-folder` | File folder / tab | Office & Admin | 9, 12, 18, 24 | `name`, `year` |
| `binder-spine` | Binder spine | Office & Admin | 12, 18, 24 | `title`, `year` |
| `asset-tag` | Asset tag (Code 128) | Office & Admin | 12, 18, 24 | `tag`, `owner` |
| `return-address` | Return address | Office & Admin | 12, 18, 24 | `name`, `address` |
| `name-plate` | Mailbox / door name | People & Names | 9, 12, 18, 24 | `name` |
| `kids-name` | Kid's belongings | People & Names | 6, 9, 12, 18, 24 | `name` |
| `property-of` | Property of | People & Names | 12, 18, 24 | `name` |
| `lost-found-qr` | Lost & found | People & Names | 12, 18, 24 | `name`, `phone` |
| `zigbee-device` | Zigbee / smart device | Smart Home | 12, 18, 24 | `name`, `ieee` |
| `ha-device` | Device & entity | Smart Home | 12, 18, 24 | `name`, `entity` |
| `scan-to-open` | Scan to open | Smart Home | 18, 24 | `url`, `title` |
| `battery-date` | Battery changed | Smart Home | 12, 18, 24 | `type`, `date` |
| `fragile` | Fragile | Safety & Warning | 9, 12, 18, 24 | `text` |
| `warning` | Warning | Safety & Warning | 9, 12, 18, 24 | `text` |
| `do-not-unplug` | Do not unplug | Safety & Warning | 12, 18, 24 | `reason` |
| `shutoff-valve` | Shut-off valve | Safety & Warning | 12, 18, 24 | `what`, `hint` |

Categories: Kitchen & Food, Home & Storage, Cables & Network, Electronics & Maker, Office & Admin,
People & Names, Smart Home, Safety & Warning.

## API

```python
from ptouch.templates import list_templates, build_template, TEMPLATE_VERSION
list_templates()                 # [{id, name, category, description, tape_mm_hint, tapes, variables}]
design = build_template("spice-jar", 12)   # design JSON (contract section 1); raises TemplateError
img = render_design(design, 12, variables={})   # variables={} substitutes the defaults
```

`tapes` holds the printer's tape ints (`4` = 3.5 mm). `build_template` also accepts `3.5`.
The returned design has `id: ""` (storage assigns it), `length_mm: null`, `variables` = defaults.
Pass `variables={}` (not `None`) to `render_design` to substitute `{{ }}` placeholders.

## Adding a template

Add a builder to `templates.py` using the `@_tpl(...)` decorator:

```python
@_tpl("my-label", "My label", "Home & Storage", "One-line description.", 12, T12,
      {"name": _v("Name", "Example")})
def _my(g: Geo, e: Els) -> int:
    (y1, h1), (y2, h2) = g.rows(0.6, 0.4)      # split the inner band into rows
    e.text(0, y1, 300, h1, "{{ name }}", BOLD)
    e.text(0, y2, 300, h2, "static line", COND_SUB)
    return 300                                  # content length in dots
```

`g.H` is the pin count, `g.m` the margin, `g.y0`/`g.ih` the inner band; icons go in `ICONS`,
fonts are the style dicts at the top (`BOLD`, `COND`, `MONO`, `HAND`, `SERIF`). Declare every variable
used and nothing more. Then run `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_templates.py`
(every template x tape: renders, no clipping, variables consistent, text >= 19 dots, QR modules >= 3 dots)
and once `PTOUCH_LIVE=1 ...` to verify the fonts, weights and icons against the real catalogues.
