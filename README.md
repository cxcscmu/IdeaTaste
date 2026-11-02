# IdeaTaste project page

Static site served by GitHub Pages from this `gh-pages` branch (Settings → Pages → Branch: `gh-pages`, folder `/`).

- `index.html`: the page
- `assets/style.css`, `assets/app.js`: styles and the leaderboard and charts (no dependencies)
- `assets/data/leaderboard.json`: main-table scores, built from the release data's `main_table.json`; all numbers are the paper's
- `assets/img/`: figures from the paper

Preview locally with `python -m http.server` and open http://localhost:8000.

```
python -m http.server 8766 --bind 127.0.0.1 --directory ."
```
