# Filing downloads: `uni.json`, `sort`, the launcher

Once a semester, edit `~/.config/assignmentvibe/uni.json`: which semester is
running, which courses it has, and what their files are called.

```jsonc
{
  "active": "m1",
  "uni_root": "~/Uni",
  "downloads": "~/Downloads",
  "pdf_viewer": "firefox",
  "alte_skripte_im_launcher": true,

  "semesters": {
    "m1": {
      "optimierung": {
        "name": "Optimierung",
        "skript":   ["VO*_Optimierung*.pdf"],
        "folien":   ["*Folien*.pdf"],
        "blaetter": ["*-Blatt-PS-Optimierung.pdf"]
      }
    }
  }
}
```

Patterns are globs (`*`, `?`, `[0-9]`), case-insensitive. Keys starting with
`_` are notes and ignored (JSON has no comments). The keys are German -
`skript` (lecture notes), `folien` (slides), `blaetter` (problem sheets) -
since that is what the tool was built for.

**The one rule:** a file is filed if it matches a pattern here, and not
otherwise. A downloads folder is full of things that have nothing to do with
university; all of that stays where it is. No heuristics, no guessing.

The three categories do **not** decide where a file goes - everything lands
flat in `<uni_root>/<semester>/<course>/`. They say what a file *is*, and that
decides what happens when a new version is downloaded:

| Category | How many | On a new download |
|---|---|---|
| `skript` | one **per pattern** | replaces the old one, **even under another name** (`VO3_…` → `VO4_…`) |
| `folien` | one per chapter | replaces only under the **same name**, else is added |
| `blaetter` | many | replaces only under the **same name**, else is added |

For `skript`, **one pattern is one slot**: `["VO*_Optimierung.pdf"]` lets
`VO4_…` replace `VO3_…`. Two patterns are two slots, so
`lecture-notes.pdf` and `lecture-notes-annotated.pdf` live side by side.

"Same name" is compared without the browser's counter (Firefox appends `-1`,
Chrome ` (1)`): `Folien-1.pdf` is a new version of `Folien.pdf` and is filed
under the clean name - but **only if the name without counter exists**, filed
or in downloads, so that `04x1-1.pdf` (a real slide set) is not taken for a
copy of `04x1.pdf`. `_1` is never stripped: `Blatt_1.pdf` and `Blatt_2.pdf`
are different sheets. Several downloads competing for one name: the newest
wins. Nothing is ever deleted - replaced files and leftover downloads go to
the trash (`gio trash`).

## Subfolders

By default everything goes flat into the course folder. If a course folder is
divided by hand, `unterordner` says where each category goes:

```jsonc
"parallele_programmierung": {
  "name": "Parallele Programmierung",
  "folien": ["[0-9][0-9]_*.pdf", "part?_*.pdf"],
  "unterordner": { "folien": "vo" }
}
```

Files are searched for below it **recursively**: if a file of the same name
already lies deeper (`vo/Kapitel 5 - …/SE Kapitel 5 Teil 1.pdf`), the download
replaces exactly that one.

## The launcher

Super+Space finds: the script, **every** slide set on its own, the **newest**
sheet, and the course folder. PDFs open with `pdf_viewer`, the folder in the
file manager. With `alte_skripte_im_launcher`, scripts of past semesters stay
findable ("Analysis Skript (s4)") - their slides, sheets and folders do not,
or the search would drown.

```bash
assignmentvibe config show     # what the config means right now
assignmentvibe sort            # preview: what would go where
assignmentvibe sort --apply    # move, and update the launcher entries
assignmentvibe launcher        # only rebuild the Super+Space entries
```

`bin/uni-sort` (bound to Super+Shift+U here) opens a terminal with the
preview and asks before moving anything.

The generated entries are `assignmentvibe-*.desktop` and carry
`X-AssignmentVibe=true`; only those are cleaned up on a re-sync, hand-written
entries are left alone.
