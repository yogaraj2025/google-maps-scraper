# Google Maps Lead Scraper

A Streamlit web app that scrapes business leads from Google Maps by keyword +
city, with a free tier (10-row sample, rest masked) and a premium tier (full
Excel download). Includes an admin panel to manage users.

## Features

- Email/password login (bcrypt-hashed, SQLite)
- Keyword + city search — auto-expands into neighbourhood queries for major
  Indian cities (Chennai, Bangalore, Mumbai, Delhi, Hyderabad, Pune, Kolkata)
- Free tier: sample of 10 rows unmasked, the rest of the rows replaced with
  "🔒 Upgrade to Premium to unlock"
- Premium / Admin: full unmasked Excel with three sheets (with-phone,
  no-phone, all), sorted by rating
- Admin Panel: list users, toggle premium / admin, reset passwords,
  delete accounts, view scrape activity
- **Auto-bootstrapped admin account** on first launch (created from
  `ADMIN_EMAIL` / `ADMIN_PASSWORD` secrets)
- API key never exposed to users — read only from environment / Streamlit
  secrets

## Deploying to Streamlit Community Cloud (the fast, free path)

1. **Push this folder to a NEW GitHub repository.** From this folder:

   ```powershell
   cd "<path-to-this-folder>"
   git init
   git add .
   git commit -m "Initial commit"
   gh repo create google-maps-scraper --private --source=. --push
   ```

   If you don't have the GitHub CLI (`gh`), create an empty private repo on
   github.com, then run:

   ```powershell
   git remote add origin https://github.com/YOUR_USERNAME/google-maps-scraper.git
   git branch -M main
   git push -u origin main
   ```

2. Go to <https://share.streamlit.io>, click **New app**, and pick your repo.
   - Branch: `main`
   - Main file path: `app.py`
   - Python version: 3.11

3. Click **Advanced settings → Secrets** and paste (with your real values):

   ```toml
   GOOGLE_MAPS_API_KEY = "your_google_maps_api_key_here"
   ADMIN_EMAIL         = "you@example.com"
   ADMIN_PASSWORD      = "a_strong_password"
   ```

4. Click **Deploy**. First deploy takes 2–3 minutes.

5. When it opens, sign in with the admin email + password from step 3.
   The admin user is created automatically on the first launch.

Your app URL will look like `https://YOUR-APP-NAME.streamlit.app`.

### ⚠️ Persistence caveat on Streamlit Community Cloud

Streamlit Cloud storage is ephemeral: **whenever you push new code, the
container is rebuilt and the SQLite database is wiped**. All registered users
disappear, except the admin (which is bootstrapped again on launch).

This is fine for testing and demos. Before paying customers rely on the app,
migrate the user table to a managed Postgres (Neon or Supabase both have free
tiers — ~30 lines of code change in `auth.py`), or move to a host with
persistent disk (Render Starter, $7/mo).

## Running locally

```powershell
pip install -r requirements.txt
copy .env.example .env
notepad .env   # fill GOOGLE_MAPS_API_KEY, ADMIN_EMAIL, ADMIN_PASSWORD
streamlit run app.py
```

Browser opens at <http://localhost:8501>. Sign in with the admin credentials
you set in `.env`.

## Making a user premium

1. Sign in as admin.
2. Open **Admin Panel** in the left sidebar.
3. Find the user and toggle the **Premium** switch on.

The user gets the full unmasked download from their next scrape onward.

## File layout

```
.
├── app.py                       Main Streamlit app (login + scraper)
├── pages/
│   └── 1_Admin_Panel.py         Admin UI (auto-listed by Streamlit)
├── auth.py                      SQLite + bcrypt user management
├── scraper.py                   Google Maps scrape + masking + Excel export
├── requirements.txt
├── .env.example                 Template for local .env
├── .streamlit/
│   └── secrets.toml.example     Template for Streamlit Cloud secrets
├── .gitignore
└── data/                        Created at runtime; holds users.db
```

## Security notes

- The original `music_scraper.py` had a Google Maps API key hard-coded in it.
  Rotate that key immediately in the Google Cloud Console — once a key is
  committed to a file, treat it as compromised.
- **Never commit `.env` or `.streamlit/secrets.toml`.** Both are in
  `.gitignore` already; don't remove those lines.
- Each Places Text Search and Place Details call is billed by Google. Set a
  budget alert in the Google Cloud billing dashboard before going live with
  paying users.
