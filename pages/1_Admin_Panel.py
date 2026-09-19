"""
Admin Panel — visible only to users with is_admin = 1.
Manage user accounts, toggle premium status, view scrape activity.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import auth

st.set_page_config(page_title="Admin Panel", page_icon="👑", layout="wide")
auth.init_db()


def current_user():
    uid = st.session_state.get("user_id")
    return auth.get_user(uid) if uid else None


user = current_user()
if not user:
    st.error("Please sign in on the main page first.")
    st.stop()
if not user.get("is_admin"):
    st.error("Admin access only.")
    st.stop()

st.title("👑 Admin Panel")
st.caption(f"Signed in as `{user['email']}`")

tab_users, tab_create, tab_log = st.tabs(["Users", "Create user", "Recent scrapes"])

with tab_users:
    users = auth.list_users()
    st.subheader(f"All users ({len(users)})")

    if not users:
        st.info("No users yet.")
    else:
        for u in users:
            with st.container(border=True):
                c1, c2, c3, c4, c5 = st.columns([3, 1, 1, 2, 2])
                c1.markdown(
                    f"**{u['email']}**  \n"
                    f"<small>Created {u['created_at'][:19].replace('T',' ')} · "
                    f"Last login {(u['last_login'] or '—')[:19].replace('T',' ')}</small>",
                    unsafe_allow_html=True,
                )
                c2.write("⭐ Premium" if u["is_premium"] else "🆓 Free")
                c3.write("👑 Admin" if u["is_admin"] else "User")

                with c4:
                    new_premium = st.toggle(
                        "Premium",
                        value=bool(u["is_premium"]),
                        key=f"prem_{u['id']}",
                    )
                    if new_premium != bool(u["is_premium"]):
                        auth.set_premium(u["id"], new_premium)
                        st.rerun()

                with c5:
                    if u["id"] == user["id"]:
                        st.caption("(this is you)")
                    else:
                        with st.popover("Manage"):
                            st.write(f"Manage **{u['email']}**")
                            new_admin = st.checkbox(
                                "Admin access",
                                value=bool(u["is_admin"]),
                                key=f"admin_{u['id']}",
                            )
                            if new_admin != bool(u["is_admin"]):
                                auth.set_admin(u["id"], new_admin)
                                st.rerun()

                            new_pw = st.text_input(
                                "Reset password to",
                                type="password",
                                key=f"pw_{u['id']}",
                            )
                            if st.button("Apply password reset", key=f"pwbtn_{u['id']}"):
                                if new_pw:
                                    ok, msg = auth.change_password(u["id"], new_pw)
                                    (st.success if ok else st.error)(msg)
                                else:
                                    st.warning("Enter a password first.")

                            st.divider()
                            confirm = st.checkbox(
                                "I understand this is permanent",
                                key=f"delconf_{u['id']}",
                            )
                            if st.button("🗑️ Delete user", key=f"del_{u['id']}", disabled=not confirm):
                                auth.delete_user(u["id"])
                                st.rerun()

with tab_create:
    st.subheader("Create a new user")
    with st.form("create_user_form", clear_on_submit=True):
        email = st.text_input("Email")
        password = st.text_input("Password (min 6 chars)", type="password")
        c1, c2 = st.columns(2)
        is_premium = c1.checkbox("Grant premium access")
        is_admin = c2.checkbox("Grant admin access")
        submitted = st.form_submit_button("Create user", type="primary")
    if submitted:
        ok, msg = auth.register_user(email, password, is_premium=is_premium, is_admin=is_admin)
        (st.success if ok else st.error)(msg)

with tab_log:
    st.subheader("Recent scrape activity")
    log = auth.list_scrape_log(limit=200)
    if not log:
        st.info("No scrapes recorded yet.")
    else:
        df = pd.DataFrame(log)
        df["created_at"] = df["created_at"].str[:19].str.replace("T", " ")
        df = df.rename(columns={
            "id": "ID", "email": "User", "keyword": "Keyword",
            "city": "City", "rows_found": "Rows", "created_at": "When (UTC)",
        })
        st.dataframe(df, use_container_width=True, hide_index=True)
