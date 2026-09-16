"""
teacher_attendance.py: Teacher Attendance System with WhatsApp/SMS Arrival Alerts,
Roster Management (CNIC & Phone), and Monthly/Annual Absence Analytics.
"""

import datetime
import os
import urllib.parse
import pandas as pd
import streamlit as st
from utils import decode_qr_image

ROSTER_FILE = "teacher_roster.csv"
ATTENDANCE_LOG_FILE = "teacher_attendance_log.csv"


def load_roster() -> pd.DataFrame:
  if os.path.exists(ROSTER_FILE):
    return pd.read_csv(ROSTER_FILE)
  return pd.DataFrame([
      {
          "Teacher_ID": "T101",
          "Teacher_Name": "Mr. Ahmad",
          "CNIC": "16202-1234567-1",
          "Phone_WhatsApp": "+923001234567",
          "Designation": "SST Maths",
      },
      {
          "Teacher_ID": "T102",
          "Teacher_Name": "Mr. Tariq",
          "CNIC": "16202-7654321-3",
          "Phone_WhatsApp": "+923009876543",
          "Designation": "SST IT",
      },
      {
          "Teacher_ID": "T103",
          "Teacher_Name": "Ms. Ayesha",
          "CNIC": "16202-9876543-5",
          "Phone_WhatsApp": "+923012345678",
          "Designation": "SST Physics",
      },
      {
          "Teacher_ID": "T104",
          "Teacher_Name": "Mr. Bilal",
          "CNIC": "16202-4567890-7",
          "Phone_WhatsApp": "+923023456789",
          "Designation": "SST English",
      },
  ])


def save_roster(df: pd.DataFrame):
  df.to_csv(ROSTER_FILE, index=False)


def record_teacher_checkin(
    teacher_id_or_name: str, roster_df: pd.DataFrame
) -> tuple[str, str, str]:
  """Logs teacher entry and generates direct WhatsApp notification link."""
  val = str(teacher_id_or_name).strip()
  match = roster_df[
      (roster_df["Teacher_ID"].astype(str) == val)
      | (roster_df["Teacher_Name"].astype(str).str.lower() == val.lower())
  ]

  if match.empty:
    return f"⚠️ Teacher ID or Name '{val}' not found in Roster.", "", ""

  rec = match.iloc[0]
  t_id = rec["Teacher_ID"]
  name = rec["Teacher_Name"]
  phone = str(rec["Phone_WhatsApp"]).replace("-", "").replace(" ", "").strip()

  now = datetime.datetime.now()
  date_str = now.strftime("%Y-%m-%d")
  time_str = now.strftime("%I:%M:%S %p")

  cols = [
      "Date",
      "Year",
      "Month",
      "Time",
      "Teacher_ID",
      "Teacher_Name",
      "Designation",
      "Status",
  ]
  if os.path.exists(ATTENDANCE_LOG_FILE):
    log_df = pd.read_csv(ATTENDANCE_LOG_FILE)
  else:
    log_df = pd.DataFrame(columns=cols)

  if not log_df.empty:
    already = log_df[
        (log_df["Date"] == date_str)
        & (log_df["Teacher_ID"].astype(str) == str(t_id))
    ]
    if not already.empty:
      return (
          f"ℹ️ {name} is already marked Present today at"
          f" {already.iloc[0]['Time']}.",
          "",
          phone,
      )

  new_row = pd.DataFrame([{
      "Date": date_str,
      "Year": now.year,
      "Month": now.strftime("%B"),
      "Time": time_str,
      "Teacher_ID": t_id,
      "Teacher_Name": name,
      "Designation": rec.get("Designation", "Teacher"),
      "Status": "Present",
  }])
  log_df = pd.concat([log_df, new_row], ignore_index=True)
  log_df.to_csv(ATTENDANCE_LOG_FILE, index=False)

  alert_msg = (
      f"Salam {name},\nYour attendance at school has been recorded"
      f" successfully.\n📅 Date: {date_str}\n⏰ Arrival Time: {time_str}\nStatus:"
      " Present ✅\nHave a great teaching day!"
  )
  encoded_msg = urllib.parse.quote(alert_msg)
  clean_phone = phone.replace("+", "")
  whatsapp_url = (
      f"https://api.whatsapp.com/send?phone={clean_phone}&text={encoded_msg}"
  )

  status_msg = f"✅ Attendance Recorded: {name} ({t_id}) at {time_str}"
  return status_msg, whatsapp_url, phone


def render_teacher_attendance_page():
  st.subheader("👨‍🏫 Teacher Attendance, WhatsApp Alerts & Absence Analytics")
  roster_df = load_roster()

  t_tab1, t_tab2, t_tab3 = st.tabs([
      "📷 Check-In & WhatsApp Alert",
      "📋 Teacher Roster & File Upload",
      "📊 Monthly & Annual Absence Reports",
  ])

  with t_tab1:
    c1, c2 = st.columns(2)
    with c1:
      st.markdown("##### Scan Teacher QR / Badge")
      cam_shot = st.camera_input("Scan Teacher Badge / QR")
      up_img = st.file_uploader(
          "Or Upload QR Image", type=["jpg", "png", "jpeg"], key="tch_qr_file"
      )

      img_bytes = None
      if cam_shot:
        img_bytes = cam_shot.getvalue()
      elif up_img:
        img_bytes = up_img.getvalue()

      if img_bytes:
        decoded = decode_qr_image(img_bytes)
        tch_key = (
            decoded.get("roll_no")
            or decoded.get("teacher_id")
            or decoded.get("raw_data")
        )
        if tch_key:
          msg, wa_url, phone = record_teacher_checkin(tch_key, roster_df)
          st.success(msg)
          if wa_url:
            st.markdown(
                f"[📲 **Send WhatsApp Arrival Status to {phone}**]({wa_url})",
                unsafe_allow_html=True,
            )
        else:
          st.warning("No recognizable teacher code found in image.")

    with c2:
      st.markdown("##### Manual Teacher Check-In")
      manual_teacher = st.selectbox(
          "Select Teacher", roster_df["Teacher_Name"].tolist()
      )
      if st.button("Mark Present & Generate Alert", type="primary"):
        msg, wa_url, phone = record_teacher_checkin(manual_teacher, roster_df)
        if "already" in msg:
          st.info(msg)
        else:
          st.success(msg)
        if wa_url:
          st.markdown(
              f"""
                    <a href="{wa_url}" target="_blank">
                        <button style="background-color:#25D366;color:white;border:none;border-radius:8px;padding:8px 16px;cursor:pointer;font-weight:bold;">
                            💬 Send Instant WhatsApp Confirmation
                        </button>
                    </a>
                """,
              unsafe_allow_html=True,
          )

    st.markdown("---")
    if os.path.exists(ATTENDANCE_LOG_FILE):
      st.markdown("###### Today's Teacher Attendance Sheet")
      st.dataframe(
          pd.read_csv(ATTENDANCE_LOG_FILE).tail(10), use_container_width=True
      )

  with t_tab2:
    st.markdown("##### Upload Teacher Roster (CSV / Excel)")
    sample_roster = (
        "Teacher_ID,Teacher_Name,CNIC,Phone_WhatsApp,Designation\n"
        "T101,Mr. Ahmad,16202-1234567-1,+923001234567,SST Maths\n"
        "T102,Mr. Tariq,16202-7654321-3,+923009876543,SST IT\n"
        "T103,Ms. Ayesha,16202-9876543-5,+923012345678,SST Physics\n"
        "T104,Mr. Bilal,16202-4567890-7,+923023456789,SST English\n"
    )
    st.download_button(
        "📥 Download Roster CSV Template",
        data=sample_roster,
        file_name="teachers_roster_template.csv",
        mime="text/csv",
    )

    up_roster = st.file_uploader(
        "Upload Roster Sheet", type=["csv", "xlsx"], key="up_roster_key"
    )
    if up_roster:
      if up_roster.name.endswith(".csv"):
        new_roster = pd.read_csv(up_roster)
      else:
        new_roster = pd.read_excel(up_roster)
      save_roster(new_roster)
      roster_df = new_roster
      st.success("✅ Teacher Roster uploaded and saved successfully!")

    st.markdown("###### Current Teacher Database")
    edited_roster = st.data_editor(
        roster_df, num_rows="dynamic", use_container_width=True
    )
    if st.button("Save Roster Changes"):
      save_roster(edited_roster)
      st.success("Changes saved!")

  with t_tab3:
    st.markdown("##### 📈 Absence, Attendance & Analytics Reports")
    if not os.path.exists(ATTENDANCE_LOG_FILE):
      st.info("No attendance logged yet.")
    else:
      log_df = pd.read_csv(ATTENDANCE_LOG_FILE)
      c_y, c_m, c_work = st.columns(3)
      with c_y:
        available_years = log_df["Year"].dropna().unique().tolist()
        sel_year = st.selectbox(
            "Select Year",
            available_years
            if available_years
            else [datetime.datetime.now().year],
        )
      with c_m:
        available_months = ["All Months"] + list(
            log_df["Month"].dropna().unique()
        )
        sel_month = st.selectbox("Select Month", available_months)
      with c_work:
        expected_days = st.number_input(
            "Working Days in Period", min_value=1, max_value=365, value=24
        )

      filtered = log_df[log_df["Year"] == sel_year]
      if sel_month != "All Months":
        filtered = filtered[filtered["Month"] == sel_month]

      present_counts = (
          filtered[filtered["Status"] == "Present"]["Teacher_Name"]
          .value_counts()
          .to_dict()
      )

      summary = []
      for _, r in roster_df.iterrows():
        tname = r["Teacher_Name"]
        tid = r["Teacher_ID"]
        pres = present_counts.get(tname, 0)
        absent = max(0, expected_days - pres)
        pct = round((pres / expected_days) * 100, 1)
        summary.append({
            "Teacher ID": tid,
            "Teacher Name": tname,
            "Designation": r.get("Designation", "-"),
            "Total Working Days": expected_days,
            "Days Present": pres,
            "Days Absent": absent,
            "Attendance %": f"{pct}%",
        })

      summary_df = pd.DataFrame(summary)
      st.markdown(f"#### Attendance Summary Report — {sel_month} {sel_year}")
      st.dataframe(summary_df, use_container_width=True)

      csv_data = summary_df.to_csv(index=False)
      st.download_button(
          "📥 Download Absence Report (.CSV)",
          data=csv_data,
          file_name=f"Teacher_Absence_Report_{sel_month}_{sel_year}.csv",
          mime="text/csv",
      )
