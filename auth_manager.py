"""
auth_manager.py: Authentication, Multi-Tenant Isolation, Role-Based Access Control,
Account Deletion, SuperAdmin Credentials Visibility, and Email OTP Password Recovery.
"""

import os
import json
import shutil
import random
import smtplib
import hashlib
import datetime
from email.mime.text import MIMEText
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

    initial_db = {
        "superadmin": {
            "username": "superadmin",
            "plain_password": "admin123",
            "password_hash": hash_password("admin123"),
            "role": "superadmin",
            "school_name": "System Central Administration",
            "school_id": "system_admin",
            "email": "admin@schoolportal.local",
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


def delete_user_account(username: str) -> tuple[bool, str]:
    """Permanently deletes a school account and purges its storage directory."""
    db = load_users_db()
    u = username.strip().lower()

    if u not in db:
        return False, f"User '{u}' not found."
    if db[u].get("role") == "superadmin":
        return False, "SuperAdmin account cannot be deleted."

    school_id = db[u].get("school_id", u)
    del db[u]
    save_users_db(db)

    # Purge isolated school folder
    school_path = os.path.join(BASE_DATA_DIR, school_id)
    if os.path.exists(school_path):
        try:
            shutil.rmtree(school_path)
        except Exception:
            pass

    return True, f"Account '{u}' and all school data deleted successfully."


def send_otp_email(recipient_email: str, otp_code: str) -> tuple[bool, str]:
    """
    Sends an OTP code via SMTP if configured in st.secrets or environment variables.
    Cleans up any hidden spaces from credentials automatically.
    """
    # 1. Safely read credentials and strip any hidden spaces
    raw_server = st.secrets.get("SMTP_SERVER", os.getenv("SMTP_SERVER", "smtp.gmail.com"))
    raw_port = st.secrets.get("SMTP_PORT", os.getenv("SMTP_PORT", 587))
    raw_user = st.secrets.get("SMTP_USER", os.getenv("SMTP_USER", ""))
    raw_pass = st.secrets.get("SMTP_PASS", os.getenv("SMTP_PASS", ""))

    smtp_server = str(raw_server).strip()
    smtp_port = int(raw_port)
    smtp_user = str(raw_user).strip()
    # Removes all accidental spaces in the 16-letter password:
    smtp_pass = str(raw_pass).replace(" ", "").strip()

    # 2. Check if credentials exist
    if smtp_user and smtp_pass:
        try:
            msg = MIMEText(
                f"Hello,\n\nYour OTP for password recovery on AI Teacher Assistant is: {otp_code}\n"
                "This code is valid for 10 minutes.\n\n"
                "Regards,\nAI Teacher Assistant Security Team"
            )
            msg["Subject"] = "🔐 Password Recovery OTP - AI Teacher Assistant"
            msg["From"] = smtp_user
            msg["To"] = recipient_email

            with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
            return True, f"OTP sent to {recipient_email}."
        except Exception as e:
            return False, f"SMTP error: {e}"

    return True, f"Development Mode: OTP for {recipient_email} is [{otp_code}]"

def get_school_workspace_dir(school_id: str) -> str:
    path = os.path.join(BASE_DATA_DIR, school_id)
    os.makedirs(path, exist_ok=True)
    return path


def render_superadmin_dashboard():
    # Top Bar: Title on the left, Logout button on the right
    col_sa1, col_sa2 = st.columns([4, 1])
    with col_sa1:
        st.subheader("🛡️ SuperAdmin Central Management Portal")
        st.caption("Inspect Credentials, Create or Remove Accounts, and Manage School Trial Durations.")
    with col_sa2:
        if st.button("🚪 Sign Out", key="sa_logout_btn", type="secondary", use_container_width=True):
            if "authenticated_user" in st.session_state:
                del st.session_state["authenticated_user"]
            st.query_params.clear()
            st.rerun()

    st.markdown("---")

    db = load_users_db()

    tab_users, tab_create, tab_delete = st.tabs([
        "📋 Registered Schools & Credentials",
        "➕ Create New School Account",
        "🗑️ Delete School Account"
    ])

    # 1. Registered Schools Table with Passwords & School Names
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
                "Password": data.get("plain_password", "********"),
                "School Name": data.get("school_name", "-"),
                "Registered Email": data.get("email", "-"),
                "School ID": data.get("school_id", "-"),
                "Trial Period": f"{trial_days} Days",
                "Expiry Date": expiry.strftime("%Y-%m-%d"),
                "Days Left": max(0, days_left),
                "Status": status
            })

        if rows:
            df_users = pd.DataFrame(rows)
            st.dataframe(df_users, use_container_width=True)

            st.markdown("##### ⚙️ Update Account Settings")
            col_m1, col_m2, col_m3 = st.columns(3)
            with col_m1:
                selected_user = st.selectbox("Select Account", [r["Username"] for r in rows], key="sa_sel_usr")
            with col_m2:
                action = st.selectbox("Action", ["Extend Trial (+30 Days)", "Extend Trial (+365 Days Full License)", "Toggle Active/Deactivate", "Change Password"])
            with col_m3:
                new_pw = st.text_input("New Password (if changing)", type="password", key="sa_new_pw")

            if st.button("Apply Account Modification", type="primary"):
                u_target = db[selected_user]
                if action == "Extend Trial (+30 Days)":
                    u_target["trial_days"] = u_target.get("trial_days", 14) + 30
                    u_target["is_active"] = True
                    st.success(f"Extended {selected_user} by 30 days!")
                elif action == "Extend Trial (+365 Days Full License)":
                    u_target["trial_days"] = u_target.get("trial_days", 14) + 365
                    u_target["is_active"] = True
                    st.success(f"Upgraded {selected_user} to 365 Days Full License!")
                elif action == "Toggle Active/Deactivate":
                    u_target["is_active"] = not u_target.get("is_active", True)
                    st.success(f"Toggled status for {selected_user} to active={u_target['is_active']}!")
                elif action == "Change Password":
                    if new_pw.strip():
                        u_target["plain_password"] = new_pw.strip()
                        u_target["password_hash"] = hash_password(new_pw.strip())
                        st.success(f"Password updated for {selected_user}!")
                    else:
                        st.error("Please enter a new password.")

                save_users_db(db)
                st.rerun()
        else:
            st.info("No school accounts registered yet. Use the next tab to register one.")

    # 2. Add New School Account
    with tab_create:
        st.markdown("##### ➕ Register New School Client")
        with st.form("create_school_form"):
            new_s_name = st.text_input("School Full Name", placeholder="e.g. Government High School Chota Lahore")
            col_u1, col_u2 = st.columns(2)
            with col_u1:
                new_u = st.text_input("Username (Unique, lowercase)", placeholder="e.g. ghs_swabi")
                new_email = st.text_input("Registered Recovery Email", placeholder="e.g. principal@ghs.edu.pk")
            with col_u2:
                new_p = st.text_input("Assigned Password", placeholder="e.g. School@1234")
                trial_option = st.selectbox("Trial Lifespan", [7, 14, 30, 90, 365], index=1)

            submit_btn = st.form_submit_button("Register & Grant Access", type="primary")

            if submit_btn:
                clean_u = new_u.strip().lower()
                clean_s = new_s_name.strip()
                clean_e = new_email.strip().lower()

                if not clean_u or not new_p.strip() or not clean_s or not clean_e:
                    st.error("All fields (School Name, Username, Email, Password) are required.")
                elif clean_u in db:
                    st.error(f"Username '{clean_u}' already exists! Please choose another.")
                else:
                    school_id = clean_u.replace(" ", "_")
                    db[clean_u] = {
                        "username": clean_u,
                        "plain_password": new_p.strip(),
                        "password_hash": hash_password(new_p.strip()),
                        "role": "school_admin",
                        "school_name": clean_s,
                        "school_id": school_id,
                        "email": clean_e,
                        "created_at": datetime.date.today().isoformat(),
                        "trial_days": trial_option,
                        "is_active": True
                    }
                    save_users_db(db)
                    get_school_workspace_dir(school_id)
                    st.success(f"✅ School Account '{clean_s}' registered successfully with a {trial_option}-day trial!")
                    st.rerun()

    # 3. Delete School Account
    with tab_delete:
        st.markdown("##### 🗑️ Permanent School Account Removal")
        st.warning("⚠️ Warning: Deleting a school account permanently erases its credentials, documents, and student marks records from disk.")

        non_admin_users = [u for u, d in db.items() if d.get("role") != "superadmin"]
        if non_admin_users:
            del_user = st.selectbox("Select Account to Permanently Delete", non_admin_users, key="del_user_select")
            confirm_box = st.checkbox(f"Confirm permanent deletion of account '{del_user}' and all its stored data.")

            if st.button("Delete Account Permanently", type="primary"):
                if confirm_box:
                    ok, msg = delete_user_account(del_user)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.error("Please check the confirmation box to proceed.")
        else:
            st.info("No school accounts available to delete.")
def render_login_gate() -> dict | None:
    """Renders the login gate, registration verification, and preserves session across browser refresh."""
    
    # 1. Check if user is already logged in session_state
    if "authenticated_user" in st.session_state and st.session_state["authenticated_user"]:
        return st.session_state["authenticated_user"]

    # 2. Check if a valid session exists in query params (survives page refresh / F5)
    params = st.query_params
    if "session_user" in params and "session_token" in params:
        q_user = params.get("session_user", "").strip().lower()
        q_token = params.get("session_token", "").strip()
        db = load_users_db()
        if q_user in db and db[q_user].get("is_active", True):
            # Verify session token matches password hash
            if db[q_user]["password_hash"] == q_token:
                st.session_state["authenticated_user"] = db[q_user]
                return db[q_user]

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(
            """
            <div style="text-align: center; margin-bottom: 1.5rem;">
                <h2>🎓 AI Teacher Assistant</h2>
                <p style="color: #64748b; font-weight: 500;">Secure Institutional Portal</p>
            </div>
            """,
            unsafe_allow_html=True
        )

        login_tab, forgot_tab = st.tabs(["🔐 Sign In", "🔑 Forgot Password?"])

        with login_tab:
            login_username = st.text_input("Username", key="gate_user_input")
            login_password = st.text_input("Password", type="password", key="gate_pass_input")

            if st.button("Sign In to Workspace", type="primary", use_container_width=True):
                success, msg, user_data = authenticate_user(login_username, login_password)
                if success:
                    st.session_state["authenticated_user"] = user_data
                    # Store session params in URL so refresh/F5 will NOT log you out
                    st.query_params["session_user"] = user_data["username"]
                    st.query_params["session_token"] = user_data["password_hash"]
                    st.success("Access Granted! Launching workspace...")
                    st.rerun()
                else:
                    st.error(msg)

            st.caption("SuperAdmin default login: `superadmin` / `admin123`")

        with forgot_tab:
            st.markdown("##### 📩 Password Recovery via Email OTP")
            recovery_email = st.text_input("Enter Registered School Email", key="rec_email_in")

            if st.button("Send 6-Digit OTP", key="btn_send_otp"):
                clean_email = recovery_email.strip().lower()
                db = load_users_db()
                matched_user = None

                for u, data in db.items():
                    if data.get("email", "").strip().lower() == clean_email:
                        matched_user = u
                        break

                if not matched_user:
                    st.error("No account found registered with that email address.")
                else:
                    generated_otp = "".join([str(random.randint(0, 9)) for _ in range(6)])
                    st.session_state["active_otp"] = generated_otp
                    st.session_state["otp_target_user"] = matched_user
                    st.session_state["otp_timestamp"] = datetime.datetime.now()

                    ok, send_msg = send_otp_email(clean_email, generated_otp)
                    if ok:
                        st.success(send_msg)
                    else:
                        st.error(send_msg)

            if "active_otp" in st.session_state:
                st.markdown("---")
                st.markdown("##### 🔢 Enter Verification Code")
                entered_otp = st.text_input("6-Digit OTP Code", max_chars=6, key="entered_otp_val")
                new_pass = st.text_input("Set New Password", type="password", key="otp_new_pass")

                if st.button("Verify OTP & Reset Password", type="primary", use_container_width=True):
                    time_diff = (datetime.datetime.now() - st.session_state["otp_timestamp"]).total_seconds()
                    if time_diff > 600:
                        st.error("OTP has expired. Please request a new code.")
                    elif entered_otp.strip() == st.session_state["active_otp"]:
                        if not new_pass.strip():
                            st.error("Password cannot be blank.")
                        else:
                            db = load_users_db()
                            target_u = st.session_state["otp_target_user"]
                            db[target_u]["plain_password"] = new_pass.strip()
                            db[target_u]["password_hash"] = hash_password(new_pass.strip())
                            save_users_db(db)

                            del st.session_state["active_otp"]
                            del st.session_state["otp_target_user"]
                            st.success(f"✅ Password for '{target_u}' reset successfully! You can now sign in.")
                    else:
                        st.error("Invalid OTP code. Please check and try again.")

    return None
