"""
Google Maps Lead Scraper — Streamlit app.

• Free tier  → can scrape, sees a 10-row preview, downloads an Excel where the
  first 10 rows are visible and the rest are masked.
• Premium    → full preview and full unmasked Excel download.
• Admin      → access to the Admin Panel page to manage users.

Deployment: works locally (`streamlit run app.py`) and on Streamlit Community
Cloud. Configure GOOGLE_MAPS_API_KEY, ADMIN_EMAIL, ADMIN_PASSWORD in
.streamlit/secrets.toml (or the Cloud dashboard). The admin account is created
automatically on first launch.
"""
from __future__ import annotations

import os
from datetime import datetime

import pandas as pd
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import auth
import scraper

FREE_SAMPLE_SIZE = 10

st.set_page_config(
    page_title="Google Maps Lead Scraper",
    page_icon="🗺️",
    layout="wide",
)

# Initialise DB + bootstrap admin account on first launch. Idempotent.
auth.init_db()
auth.bootstrap_admin_from_env()


def current_user():
    uid = st.session_state.get("user_id")
    return auth.get_user(uid) if uid else None


def login_view():
    st.title("🗺️ Google Maps Lead Scraper")
    st.caption("Sign in to start scraping local business leads from Google Maps.")

    tab_login, tab_register = st.tabs(["Sign in", "Create account"])

    with tab_login:
        with st.form("login_form", clear_on_submit=False):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Sign in", use_container_width=True, type="primary")
        if submitted:
            user = auth.authenticate(email, password)
            if user:
                st.session_state["user_id"] = user["id"]
                st.rerun()
            else:
                st.error("Invalid email or password.")

    with tab_register:
        with st.form("register_form", clear_on_submit=True):
            email = st.text_input("Email", key="reg_email")
            password = st.text_input("Password (min 6 chars)", type="password", key="reg_password")
            confirm = st.text_input("Confirm password", type="password", key="reg_confirm")
            submitted = st.form_submit_button("Create free account", use_container_width=True)
        if submitted:
            if password != confirm:
                st.error("Passwords do not match.")
            else:
                ok, msg = auth.register_user(email, password, is_premium=False, is_admin=False)
                (st.success if ok else st.error)(msg)


def sidebar(user):
    with st.sidebar:
        st.markdown(f"**Signed in as**\n\n`{user['email']}`")
        badges = []
        if user.get("is_admin"):
            badges.append("👑 Admin")
        badges.append("⭐ Premium" if user.get("is_premium") else "🆓 Free")
        st.markdown(" • ".join(badges))
        st.divider()
        if user.get("is_admin"):
            st.info("Use the **Admin Panel** page in the sidebar to manage users.")
        else:
            st.markdown(
                "**Free plan**\n\n"
                f"Downloads include a sample of the first **{FREE_SAMPLE_SIZE}** results; "
                "the remaining rows are masked. Upgrade to unlock the full export."
            )
        st.divider()
        if st.button("Sign out", use_container_width=True):
            st.session_state.clear()
            st.rerun()


def scraper_view(user):
    st.title("🗺️ Google Maps Lead Scraper")
    st.caption("Find businesses by keyword and city. Results include name, phone, address, rating, website, and Google Maps URL.")

    with st.form("search_form"):
        col1, col2 = st.columns(2)
        with col1:
            keyword = st.text_input(
                "Keyword",
                placeholder="e.g. singing classes, dental clinic, gym",
            )
        with col2:
            city = st.text_input("City", placeholder="e.g. Chennai, Bangalore, Mumbai")
        include_areas = st.checkbox(
            "Also search popular neighbourhoods of this city (recommended for more results)",
            value=True,
        )
        run = st.form_submit_button("🔍 Start scraping", type="primary", use_container_width=True)

    if run:
        if not keyword or not city:
            st.warning("Please enter both a keyword and a city.")
            return
        try:
            scraper.get_api_key()
        except RuntimeError as e:
            st.error(str(e))
            return

        progress_bar = st.progress(0.0)
        status = st.empty()

        def cb(frac, msg):
            progress_bar.progress(min(max(frac, 0.0), 1.0))
            status.write(msg)

        with st.spinner("Scraping… this can take a few minutes for popular keywords."):
            try:
                df = scraper.scrape(keyword=keyword, city=city,
                                    include_areas=include_areas, progress=cb)
            except Exception as e:
                st.error(f"Scrape failed: {e}")
                return

        progress_bar.empty()
        status.empty()

        if df.empty:
            st.warning("No results found. Try a different keyword or city.")
            return

        st.session_state["last_df"] = df
        st.session_state["last_meta"] = {
            "keyword": keyword,
            "city": city,
            "ts": datetime.utcnow().isoformat(),
        }
        auth.log_scrape(user["id"], keyword, city, len(df))

    df = st.session_state.get("last_df")
    meta = st.session_state.get("last_meta")
    if df is None or meta is None:
        return

    is_premium = bool(user.get("is_premium") or user.get("is_admin"))
    total = len(df)
    with_phone = int((df["Phone"].astype(str).str.strip() != "").sum())

    st.divider()
    st.subheader(f"Results — {meta['keyword']} in {meta['city']}")

    c1, c2, c3 = st.columns(3)
    c1.metric("Total places", total)
    c2.metric("With phone numbers", with_phone)
    c3.metric("Without phone", total - with_phone)

    if is_premium:
        st.success("⭐ Premium account — showing full results.")
        st.dataframe(df, use_container_width=True, hide_index=True)
        excel_bytes = scraper.to_excel_bytes(df)
        filename = f"{meta['keyword'].replace(' ', '_')}_{meta['city'].replace(' ', '_')}_FULL.xlsx"
        st.download_button(
            "⬇️ Download full Excel",
            data=excel_bytes,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
        )
    else:
        st.info(
            f"🆓 Free account — showing first **{FREE_SAMPLE_SIZE}** of **{total}** results. "
            "The downloadable Excel will include the same sample with the rest masked. "
            "Contact the admin to upgrade and unlock the full export."
        )
        st.dataframe(df.head(FREE_SAMPLE_SIZE), use_container_width=True, hide_index=True)
        masked_df = scraper.mask_for_free(df, sample_size=FREE_SAMPLE_SIZE)
        excel_bytes = scraper.to_excel_bytes(masked_df)
        filename = f"{meta['keyword'].replace(' ', '_')}_{meta['city'].replace(' ', '_')}_SAMPLE.xlsx"
        st.download_button(
            "⬇️ Download sample Excel (10 rows visible, rest masked)",
            data=excel_bytes,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )


def main():
    user = current_user()
    if not user:
        login_view()
        return
    sidebar(user)
    scraper_view(user)


if __name__ == "__main__":
    main()
