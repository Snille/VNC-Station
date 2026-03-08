# Manual Assets Starter Pack

This folder contains reusable graphical elements and screenshot assets used by the current manuals:

- `docs/user-guide.md`
- `docs/advanced-user-guide.md`
- `docs/admin-guide.md`

## Contents

- `images/`
  - captured screenshots used by the manuals
- `elements/number-badges-png/`
  - `badge-01-40x40.png` to `badge-20-40x40.png`
  - `badge-01-84x84.png` to `badge-20-84x84.png`
- `checklists/`
  - `screenshot-shot-list.md` (master shot list, now completed)
  - `manual-missing-screenshots.md` (coverage map and captured filenames)
  - `source-screenshots.md` (legacy source screenshot references)

## How To Use

1. Open a screenshot in GIMP.
2. Add number badges from `elements/number-badges-png/` on separate layers.
3. Save layered source as `.xcf` and export final image as PNG.

## Notes

- The workflow is PNG-only for compatibility with GIMP.
- Use `40x40` badges for dense UI screenshots and `84x84` for larger images.
- Keep checklist files updated whenever new UI/features require additional screenshots.
