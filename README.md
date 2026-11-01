# PH-EXAM-RESULTS

Responsive front-end foundation for a Philippine examination results portal.

## Pages
- **Searching Page:** normal homepage with PRC/CSC tabs, passer-name field, examination selector, year selector, and search action.
- **Preparing Page:** minimal circular preparation indicator, current examination label, preparation status, and top-right search control.

## Run locally
Open `index.html` in a modern browser. No build step or package installation is required.

## Configuration
Edit the constants at the top of `app.js`:
- `SITE_MODE`: `"search"` for the normal homepage or `"preparing"` to activate the preparation page.
- `PREPARATION.percentage` and `PREPARATION.examinationName`: illustrative preparation display values.
- `EXAMS` and `YEARS`: temporary selector options.

## Important limitations
- The sample 75% indicator and selector options are illustrative, not live or official data.
- Search is currently UI-only. It deliberately reports that no official results database is connected.
- No admin dashboard, release-date prediction, automatic activation, or official publication workflow is implemented.
- The public Preparing Page does not show an expected release date, following the previously locked design.
- Connect a verified preparation-progress source and authoritative published-results database before presenting any data as official.

## Design
Teal `#087E83`, midnight blue `#123047`, cool grey `#F1F5F9`, white search panel, responsive mobile/tablet/desktop layout, keyboard focus styles, and reduced-motion support.
