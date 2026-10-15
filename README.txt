PRIME Sports Analytics 1.0 — frontend PWA

1. Upload ALL files and folders to a GitHub Pages repository (index.html at repository root).
2. In repository Settings > Pages enable deployment from main branch / root.
3. Open your published GitHub Pages URL on iPhone Safari > Share > Add to Home Screen, or Android Chrome > Install app.
4. Initially the feed is empty on purpose. There are NO fabricated forecasts.
5. To export predictions from your existing bot's state file, run:
   python export_predictions.py /path/to/data/state.json
   Then upload/commit updated data/predictions.json to the repository.
6. Automated synchronization, Telegram-free bot publishing, and more detailed NHL data are NOT connected yet. They require the next integration stage.
7. Do not publish your bot token, secrets, or private data/state.json in GitHub Pages.
8. The frontend displays model edge (percentage-point difference), NOT probability of winning.
