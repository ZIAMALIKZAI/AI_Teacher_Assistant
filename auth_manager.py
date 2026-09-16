"""
auth_manager.py: Authentication, Multi-Tenant Isolation, Role-Based Access Control,
and Trial Expiration Management for AI Teacher Assistant.
"""

import os
import json
import hashlib
import datetime
import streamlit as st
import pandas as pd

DB_FILE = "users_db.json"
BASE_DATA_DIR = "school_data"
os.makedirs(BASE_DATA_DIR, exist_ok=True)


def hash_password(password: str) -> str:
    """Generates SHA-256 hash for secure storage."""
    return hashlib.sha256(password.strip().encode("utf-8")).hexdigest()


def load_users_db() -> dict:
    """Loads users database with a default superadmin account."""
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # Initial database containing default SuperAdmin account
    initial_db = {
        "superadmin": {
            "username": "superadmin",
            "password_hash": hash_password("admin123"),
            "role": "superadmin",
            "school_name": "System Central Administration",
            "school_id": "system_admin",
            "created_at": datetime.date.today().isoformat(),
            "trial_days": 9999,
            "is_active": True
        }
    }
    save_users_db(initial_db)
    return initial_db


def save_users_db(db: dict):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=4)


def authenticate_user(username: str, password: str) -> tuple[bool, str, dict]:
    """Validates login credentials, account status, and trial period."""
    db = load_users_db()
    u = username.strip().lower()

    if u not in db:
        return False, "❌ Username not found.", {}

    user_info = db[u]

    if not user_info.get("is_active", True):
        return False, "⚠️ This account has been deactivated by SuperAdmin.", {}

    if hash_password(password) != user_info["password_hash"]:
        return False, "❌ Incorrect password.", {}

    # Check trial expiration (SuperAdmin is exempt)
    if user_info["role"] != "superadmin":
        created = datetime.date.fromisoformat(user_info["created_at"])
        trial_days = user_info.get("trial_days", 14)
        expiry_date = created + datetime.timedelta(days=trial_days)
        today = datetime.date.today()

        if today > expiry_date:
            return False, f"🔒 Trial period expired on {expiry_date.strftime('%d-%b-%Y')}. Please contact SuperAdmin to renew your license.", {}

    return True, "Login successful.", user_info


def get_school_workspace_dir(school_id: str) -> str:
    """Provides isolated storage paths per school."""
    path = os.path.join(BASE_DATA_DIR, school_id)
    os.makedirs(path, exist_ok=True)
    return path


def render_superadmin_dashboard():
    """Administrative management view to create and control school accounts."""
    st.subheader("🛡️ SuperAdmin Control Panel")
    st.caption("Manage School Accounts, Issue Usernames/Passwords, and Configure Trial Lifespans.")

    db = load_users_db()

    tab_users, tab_create = st.tabs(["📋 Registered Schools & License Status", "➕ Create New School Account"])

    with tab_users:
        rows = []
        today = datetime.date.today()

        for u, data in db.items():
            if data["role"] == "superadmin":
                continue

            created = datetime.date.fromisoformat(data["created_at"])
            trial_days = data.get("trial_days", 14)
            expiry = created + datetime.timedelta(days=trial_days)
            days_left = (expiry - today).days

            status = "Active ✅" if days_left >= 0 and data.get("is_active", True) else "Expired 🔒"
            if not data.get("is_active", True):
                status = "Deactivated ⛔"

            rows.append({
                "Username": u,
                "School Name": data.get("school_name"),
                "School ID": data.get("school_id"),
                "Created Date": data.get("created_at"),
                "Trial Period": f"{trial_days} Days",
                "Expiry Date": expiry.strftime("%Y-%m-%d"),
                "Days Left": max(0, days_left),
                "Status": status
            })

        if rows:
            df_users = pd.DataFrame(rows)
            st.dataframe(df_users, use_container_width=True)

            st.markdown("##### ⚙️ Manage Existing School Account")
            col_m1, col_m2, col_m3 = st.columns(3)
            with col_m1:
                selected_user = st.selectbox("Select School Account", [r["Username"] for r in rows])
            with col_m2:
                action = st.selectbox("Action", ["Extend Trial (+30 Days)", "Extend Trial (+365 Days Full License)", "Toggle Active/Deactivate", "Reset Password"])
            with col_m3:
                new_pw = st.text_input("New Password (if resetting)", type="password")

            if st.button("Apply Account Update", type="primary"):
                u_target = db[selected_user]
                if action == "Extend Trial (+30 Days)":
                    u_target["trial_days"] = u_target.get("trial_days", 14) + 30
                    u_target["is_active"] = True
                    st.success(f"Extended {selected_user} by 30 days!")
                elif action == "Extend Trial (+365 Days Full License)":
                    u_target["trial_days"] = u_target.get("trial_days", 14) + 365
                    u_target["is_active"] = True
                    st.success(f"Upgraded {selected_user} to Full License (365 days)!")
                elif action == "Toggle Active/Deactivate":
                    u_target["is_active"] = not u_target.get("is_active", True)
                    st.success(f"Toggled active state for {selected_user} to {u_target['is_active']}!")
                elif action == "Reset Password":
                    if new_pw.strip():
                        u_target["password_hash"] = hash_password(new_pw.strip())
                        st.success(f"Password reset for {selected_user}!")
                    else:
                        st.error("Please enter a new password.")

                save_users_db(db)
                st.rerun()
        else:
            st.info("No school accounts registered yet. Create one below.")

    with tab_create:
        st.markdown("##### ➕ Register New School Client")
        with st.form("create_school_form"):
            new_s_name = st.text_input("School Full Name", placeholder="e.g. Army Public School Peshawar")
            col_u1, col_u2 = st.columns(2)
            with col_u1:
                new_u = st.text_input("Username (Unique)", placeholder="e.g. aps_peshawar")
            with col_u2:
                new_p = st.text_input("Assigned Password", type="password")

            trial_option = st.selectbox("Trial Lifespan", [7, 14, 30, 90, 365], index=1)
            submit_btn = st.form_submit_button("Register & Grant Access", type="primary")

            if submit_btn:
                clean_u = new_u.strip().lower()
                clean_s = new_s_name.strip()

                if not clean_u or not new_p.strip() or not clean_s:
                    st.error("All fields are required.")
                elif clean_u in db:
                    st.error(f"Username '{clean_u}' already exists! Choose another.")
                else:
                    school_id = clean_u.replace(" ", "_")
                    db[clean_u] = {
                        "username": clean_u,
                        "password_hash": hash_password(new_p.strip()),
                        "role": "school_admin",
                        "school_name": clean_s,
                        "school_id": school_id,
                        "created_at": datetime.date.today().isoformat(),
                        "trial_days": trial_option,
                        "is_active": True
                    }
                    save_users_db(db)
                    get_school_workspace_dir(school_id)
                    st.success(f"✅ School Account '{clean_s}' registered successfully with a {trial_option}-day trial!")
                    st.rerun()


def render_login_gate() -> dict | None:
    """Displays login gate and returns active user credentials session dict upon authentication."""
    if "authenticated_user" in st.session_state and st.session_state["authenticated_user"]:
        return st.session_state["authenticated_user"]

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(
            """
            <div style="text-align: center; margin-bottom: 2rem;">
                <h2>🎓 AI Teacher Assistant</h2>
                <p style="color: #64748b;">Enterprise Multi-Tenant Educational Portal</p>
            </div>
            """,
            unsafe_allow_html=True
        )

        with st.container():
            st.markdown("#### 🔐 Portal Sign In")
            login_username = st.text_input("Username", key="login_user_input")
            login_password = st.text_input("Password", type="password", key="login_pass_input")

            if st.button("Sign In to Portal", type="primary", use_container_width=True):
                success, msg, user_data = authenticate_user(login_username, login_password)
                if success:
                    st.session_state["authenticated_user"] = user_data
                    st.success("Access Granted! Loading your dashboard...")
                    st.rerun()
                else:
                    st.error(msg)

            st.caption("Default SuperAdmin login: `superadmin` / `admin123`")
    return None
