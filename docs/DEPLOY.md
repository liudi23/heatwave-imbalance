# Deploying the presentation app to Streamlit Community Cloud

The app is **self-contained**: it reads the precomputed bundle in `app/data/`
(committed to the repo) and needs **no secrets, API keys, or live data**. So
deploying is just pointing Streamlit Cloud at the repo.

## One-time deploy
1. Make sure the latest commit (incl. `app/`, `app/data/`, and the root
   `requirements.txt`) is pushed to GitHub.
2. Go to **https://share.streamlit.io** and sign in with the GitHub account
   that owns `liudi23/heatwave-imbalance`; authorise access if prompted.
3. **Create app → Deploy a public app from GitHub**, then set:
   - **Repository:** `liudi23/heatwave-imbalance`
   - **Branch:** `mvp` (or `main`, whichever you want public)
   - **Main file path:** `app/streamlit_app.py`
   - **(Advanced settings) Python version:** `3.11`
4. **Deploy.** Cloud installs from the root `requirements.txt` and serves the
   app at `https://<your-app-name>.streamlit.app` — that's the link to share.

## Updating the live app
- Streamlit Cloud **auto-redeploys on every push** to the chosen branch.
- When the analysis changes, refresh the bundle and commit it so the live app
  shows the new numbers:
  ```bash
  python src/analysis/export_app_data.py
  git add app/data && git commit -m "Refresh app data" && git push
  ```

## Notes
- **Dependencies:** Cloud installs the **root** `requirements.txt` (it ignores
  `app/requirements.txt`, which exists only for minimal local installs).
- **Data is committed:** `app/data/*.csv` and `summary.json` are tracked (not
  caught by the `data/` ignore rules), so the deployed app has everything it
  needs. No `data/raw` or sister-repo access is required at runtime.
- **Theme/config:** `.streamlit/config.toml` (light theme) is picked up
  automatically.
- **Public & safe:** the app is read-only and contains no credentials.
