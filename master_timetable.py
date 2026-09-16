"""
master_timetable.py: Advanced School Master Timetable Generator & Substitution Engine
- 6 Days: Monday to Saturday (Mon-Thu: 8 periods, Fri: 5 periods, Sat: 8 periods)
- Class Teacher takes Period 1 daily for all 6 days with their assigned subject
- Teachers with Period 1 on any day are barred from taking Period 8 on that day
- Automatic substitution system allocating the teacher with the minimum daily load
- Whole-school master matrix view with PDF and CSV export
- CSV / Excel File upload for quick workload setup
"""

import copy
import os
import random
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
import streamlit as st

DAYS_SCHEDULE = {
    "Monday": 8,
    "Tuesday": 8,
    "Wednesday": 8,
    "Thursday": 8,
    "Friday": 5,
    "Saturday": 8,
}
TOTAL_WEEKLY_SLOTS = sum(DAYS_SCHEDULE.values())  # 45 slots total


def build_empty_slots(days_config: dict = None) -> list[tuple]:
  if days_config is None:
    days_config = DAYS_SCHEDULE
  slots = []
  for day, num_periods in days_config.items():
    for p in range(1, num_periods + 1):
      slots.append((day, f"Period {p}"))
  return slots


def generate_institutional_timetable(
    teaching_assignments: list[dict],
    class_teachers: dict[str, dict],
    days_config: dict = None,
) -> tuple[dict, dict, list]:
  if days_config is None:
    days_config = DAYS_SCHEDULE

  all_slots = build_empty_slots(days_config)
  grades = list(set([item["grade"] for item in teaching_assignments]))
  all_teachers = list(set([item["teacher"] for item in teaching_assignments]))
  total_slots_allowed = sum(days_config.values())

  errors = []
  grade_totals = {}
  for item in teaching_assignments:
    g = item["grade"]
    grade_totals[g] = grade_totals.get(g, 0) + item["periods_per_week"]

  for g, tot in grade_totals.items():
    if tot > total_slots_allowed:
      errors.append(
          f"⚠️ {g} has {tot} periods assigned, exceeding weekly capacity of"
          f" {total_slots_allowed}."
      )

  if errors:
    return {}, {}, errors

  max_attempts = 250
  for attempt in range(max_attempts):
    timetable_by_grade = {
        g: {slot: ("Free", "-") for slot in all_slots} for g in grades
    }
    teacher_busy_slots = {slot: set() for slot in all_slots}
    teachers_in_p1_per_day = {day: set() for day in days_config.keys()}

    ct_clash = False
    remaining_tasks = copy.deepcopy(teaching_assignments)

    for grade, ct_info in class_teachers.items():
      ct_name = ct_info.get("teacher", "").strip()
      ct_subj = ct_info.get("subject", "").strip()
      if not ct_name or not ct_subj or grade not in timetable_by_grade:
        continue

      for day in days_config.keys():
        slot = (day, "Period 1")
        if ct_name in teacher_busy_slots[slot]:
          ct_clash = True
          break
        timetable_by_grade[grade][slot] = (ct_subj, ct_name)
        teacher_busy_slots[slot].add(ct_name)
        teachers_in_p1_per_day[day].add(ct_name)

      if ct_clash:
        break

      for item in remaining_tasks:
        if (
            item["grade"] == grade
            and item["teacher"] == ct_name
            and item["subject"] == ct_subj
        ):
          item["periods_per_week"] = max(
              0, item["periods_per_week"] - len(days_config)
          )

    if ct_clash:
      continue

    allocation_queue = []
    for item in remaining_tasks:
      for _ in range(item["periods_per_week"]):
        allocation_queue.append({
            "grade": item["grade"],
            "subject": item["subject"],
            "teacher": item["teacher"],
        })

    random.shuffle(allocation_queue)
    t_counts = {}
    for task in allocation_queue:
      t_counts[task["teacher"]] = t_counts.get(task["teacher"], 0) + 1
    allocation_queue.sort(key=lambda x: t_counts[x["teacher"]], reverse=True)

    success = True
    for task in allocation_queue:
      g = task["grade"]
      t = task["teacher"]
      s = task["subject"]

      valid_slots = []
      for slot in all_slots:
        day, period_label = slot
        if timetable_by_grade[g][slot][0] != "Free":
          continue
        if t in teacher_busy_slots[slot]:
          continue

        if period_label == "Period 8" and t in teachers_in_p1_per_day[day]:
          continue
        if period_label == "Period 1":
          p8_slot = (day, "Period 8")
          if (
              p8_slot in timetable_by_grade[g]
              and t in teacher_busy_slots[p8_slot]
          ):
            continue

        valid_slots.append(slot)

      if not valid_slots:
        success = False
        break

      chosen_slot = random.choice(valid_slots)
      timetable_by_grade[g][chosen_slot] = (s, t)
      teacher_busy_slots[chosen_slot].add(t)

      day, period_label = chosen_slot
      if period_label == "Period 1":
        teachers_in_p1_per_day[day].add(t)

    if success:
      timetable_by_teacher = {
          tch: {slot: ("Free", "-") for slot in all_slots} for tch in all_teachers
      }
      for g, sched in timetable_by_grade.items():
        for slot, (subj, tch) in sched.items():
          if tch != "-":
            timetable_by_teacher[tch][slot] = (subj, g)

      return timetable_by_grade, timetable_by_teacher, []

  return {}, {}, [
      "Unable to find a valid clash-free timetable with current constraints."
      " Please verify teacher loads."
  ]


def generate_substitution_timetable(
    base_grade_tt: dict,
    base_teacher_tt: dict,
    absent_teacher: str,
    leave_day: str,
    days_config: dict = None,
) -> tuple[dict, pd.DataFrame]:
  if days_config is None:
    days_config = DAYS_SCHEDULE

  sub_grade_tt = copy.deepcopy(base_grade_tt)
  all_teachers = [t for t in base_teacher_tt.keys() if t != absent_teacher]
  num_periods = days_config.get(leave_day, 8)

  daily_loads = {t: 0 for t in all_teachers}
  for t in all_teachers:
    for p in range(1, num_periods + 1):
      slot = (leave_day, f"Period {p}")
      if base_teacher_tt[t].get(slot, ("Free", "-"))[0] != "Free":
        daily_loads[t] += 1

  sub_log = []
  for p in range(1, num_periods + 1):
    slot = (leave_day, f"Period {p}")

    for grade, sched in sub_grade_tt.items():
      subj, assigned_t = sched.get(slot, ("Free", "-"))

      if assigned_t == absent_teacher:
        candidates = []
        for candidate in all_teachers:
          if base_teacher_tt[candidate].get(slot, ("Free", "-"))[0] == "Free":
            if f"Period {p}" == "Period 8":
              p1_slot = (leave_day, "Period 1")
              if (
                  base_teacher_tt[candidate].get(p1_slot, ("Free", "-"))[0]
                  != "Free"
              ):
                continue
            candidates.append(candidate)

        if candidates:
          candidates.sort(key=lambda t: daily_loads[t])
          substitute = candidates[0]
          daily_loads[substitute] += 1

          sub_grade_tt[grade][slot] = (f"{subj} (Sub)", substitute)
          sub_log.append({
              "Day": leave_day,
              "Period": f"Period {p}",
              "Class": grade,
              "Subject": subj,
              "Absent Teacher": absent_teacher,
              "Substitute Assigned": substitute,
              "Sub's Daily Total Load": daily_loads[substitute],
          })
        else:
          sub_grade_tt[grade][slot] = (f"{subj} (No Sub)", "Unassigned")
          sub_log.append({
              "Day": leave_day,
              "Period": f"Period {p}",
              "Class": grade,
              "Subject": subj,
              "Absent Teacher": absent_teacher,
              "Substitute Assigned": "⚠️ None Free",
              "Sub's Daily Total Load": "-",
          })

  return sub_grade_tt, pd.DataFrame(sub_log)


def format_schedule_to_dataframe(
    schedule_dict: dict, days_config: dict = None, mode: str = "grade"
) -> pd.DataFrame:
  if days_config is None:
    days_config = DAYS_SCHEDULE
  rows = []
  for day, count in days_config.items():
    row = {"Day": day}
    for p in range(1, 9):
      if p <= count:
        slot = (day, f"Period {p}")
        subj, secondary = schedule_dict.get(slot, ("Free", "-"))
        if subj == "Free":
          row[f"P{p}"] = "—"
        else:
          row[f"P{p}"] = (
              f"{subj}\n({secondary})"
              if mode == "grade"
              else f"{subj}\n[{secondary}]"
          )
      else:
        row[f"P{p}"] = "Closed"
    rows.append(row)
  return pd.DataFrame(rows)


def build_whole_school_dataframe(
    grade_tt: dict, selected_day: str, days_config: dict = None
) -> pd.DataFrame:
  if days_config is None:
    days_config = DAYS_SCHEDULE
  num_periods = days_config.get(selected_day, 8)
  rows = []
  for grade, schedule in grade_tt.items():
    row = {"Class / Grade": grade}
    for p in range(1, num_periods + 1):
      slot = (selected_day, f"Period {p}")
      val, tch = schedule.get(slot, ("Free", "-"))
      row[f"Period {p}"] = f"{val} ({tch})" if val != "Free" else "—"
    rows.append(row)
  return pd.DataFrame(rows)


def export_timetable_pdf(
    df: pd.DataFrame, header: str, subtitle: str, output_path: str
) -> str:
  doc = SimpleDocTemplate(
      output_path,
      pagesize=landscape(A4),
      rightMargin=18,
      leftMargin=18,
      topMargin=18,
      bottomMargin=18,
  )
  styles = getSampleStyleSheet()
  h_style = ParagraphStyle(
      "Hdr",
      parent=styles["Heading1"],
      fontSize=13,
      alignment=1,
      textColor=colors.HexColor("#1e3a8a"),
  )
  sub_style = ParagraphStyle(
      "Sub",
      parent=styles["Heading2"],
      fontSize=9,
      alignment=1,
      textColor=colors.HexColor("#475569"),
  )
  cell_style = ParagraphStyle(
      "Cell", parent=styles["Normal"], fontSize=7, leading=9, alignment=1
  )
  cell_bold = ParagraphStyle(
      "CellB",
      parent=styles["Normal"],
      fontSize=8,
      leading=10,
      alignment=1,
      fontName="Helvetica-Bold",
  )

  elements = [
      Paragraph(header.upper(), h_style),
      Paragraph(subtitle, sub_style),
      Spacer(1, 8),
  ]

  cols = list(df.columns)
  table_data = [[Paragraph(f"<b>{c}</b>", cell_bold) for c in cols]]
  for _, r in df.iterrows():
    r_cells = []
    for c in cols:
      text = str(r[c]).replace("\n", "<br/>")
      r_cells.append(Paragraph(text, cell_style))
    table_data.append(r_cells)

  page_w = landscape(A4)[0] - 36
  col_w = page_w / len(cols)
  t = Table(table_data, colWidths=[col_w] * len(cols))
  t.setStyle(
      TableStyle([
          ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
          ("ALIGN", (0, 0), (-1, -1), "CENTER"),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#94a3b8")),
          ("TOPPADDING", (0, 0), (-1, -1), 4),
          ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
      ])
  )
  elements.append(t)
  doc.build(elements)
  return output_path


def render_master_timetable_page(school_name: str = "Government High School"):
  st.subheader("🗓️ Complete School Master Timetable & Substitution Engine")
  st.caption(
      "6 Days (Mon–Thu: 8 Periods | Fri: 5 Periods | Sat: 8 Periods = 45"
      " Periods Total). Class Teacher Period 1 Rule."
  )

  temp_dir = "temp_output"
  os.makedirs(temp_dir, exist_ok=True)

  tab1, tab2, tab3 = st.tabs([
      "⚙️ Configuration & Master Generator",
      "🏫 Whole School & Class Schedules",
      "🔄 Leave & Substitution Engine",
  ])

  with tab1:
    st.markdown(
        "##### 📁 1. Load Teaching Load from CSV / Excel (or Edit Below)"
    )

    template_csv = (
        "Grade,Subject,Teacher,Periods_Per_Week,Is_Class_Teacher\n"
        "Grade 9,Mathematics,Mr. Ahmad,8,Yes\n"
        "Grade 9,Computer Science,Mr. Tariq,7,No\n"
        "Grade 9,Physics,Ms. Ayesha,7,No\n"
        "Grade 9,English,Mr. Bilal,7,No\n"
        "Grade 9,Islamiat,Mr. Hamza,5,No\n"
        "Grade 9,Pak Studies,Ms. Fatima,5,No\n"
        "Grade 9,Chemistry,Mr. Usama,6,No\n"
        "Grade 10,Computer Science,Mr. Tariq,8,Yes\n"
        "Grade 10,Mathematics,Mr. Ahmad,7,No\n"
        "Grade 10,Physics,Ms. Ayesha,7,No\n"
        "Grade 10,English,Mr. Bilal,7,No\n"
        "Grade 10,Islamiat,Mr. Hamza,5,No\n"
        "Grade 10,Pak Studies,Ms. Fatima,5,No\n"
        "Grade 10,Chemistry,Mr. Usama,6,No\n"
    )
    st.download_button(
        "📥 Download Timetable CSV Template",
        data=template_csv,
        file_name="timetable_workload_template.csv",
        mime="text/csv",
    )

    uploaded_tt_file = st.file_uploader(
        "Upload Workload Sheet (.csv, .xlsx)",
        type=["csv", "xlsx", "xls"],
        key="tt_file_up",
    )

    default_workload = pd.DataFrame([
        {
            "Grade": "Grade 9",
            "Subject": "Mathematics",
            "Teacher": "Mr. Ahmad",
            "Periods_Per_Week": 8,
            "Is_Class_Teacher": "Yes",
        },
        {
            "Grade": "Grade 9",
            "Subject": "Computer Science",
            "Teacher": "Mr. Tariq",
            "Periods_Per_Week": 7,
            "Is_Class_Teacher": "No",
        },
        {
            "Grade": "Grade 9",
            "Subject": "Physics",
            "Teacher": "Ms. Ayesha",
            "Periods_Per_Week": 7,
            "Is_Class_Teacher": "No",
        },
        {
            "Grade": "Grade 9",
            "Subject": "English",
            "Teacher": "Mr. Bilal",
            "Periods_Per_Week": 7,
            "Is_Class_Teacher": "No",
        },
        {
            "Grade": "Grade 9",
            "Subject": "Islamiat",
            "Teacher": "Mr. Hamza",
            "Periods_Per_Week": 5,
            "Is_Class_Teacher": "No",
        },
        {
            "Grade": "Grade 9",
            "Subject": "Pak Studies",
            "Teacher": "Ms. Fatima",
            "Periods_Per_Week": 5,
            "Is_Class_Teacher": "No",
        },
        {
            "Grade": "Grade 9",
            "Subject": "Chemistry",
            "Teacher": "Mr. Usama",
            "Periods_Per_Week": 6,
            "Is_Class_Teacher": "No",
        },
        {
            "Grade": "Grade 10",
            "Subject": "Computer Science",
            "Teacher": "Mr. Tariq",
            "Periods_Per_Week": 8,
            "Is_Class_Teacher": "Yes",
        },
        {
            "Grade": "Grade 10",
            "Subject": "Mathematics",
            "Teacher": "Mr. Ahmad",
            "Periods_Per_Week": 7,
            "Is_Class_Teacher": "No",
        },
        {
            "Grade": "Grade 10",
            "Subject": "Physics",
            "Teacher": "Ms. Ayesha",
            "Periods_Per_Week": 7,
            "Is_Class_Teacher": "No",
        },
        {
            "Grade": "Grade 10",
            "Subject": "English",
            "Teacher": "Mr. Bilal",
            "Periods_Per_Week": 7,
            "Is_Class_Teacher": "No",
        },
        {
            "Grade": "Grade 10",
            "Subject": "Islamiat",
            "Teacher": "Mr. Hamza",
            "Periods_Per_Week": 5,
            "Is_Class_Teacher": "No",
        },
        {
            "Grade": "Grade 10",
            "Subject": "Pak Studies",
            "Teacher": "Ms. Fatima",
            "Periods_Per_Week": 5,
            "Is_Class_Teacher": "No",
        },
        {
            "Grade": "Grade 10",
            "Subject": "Chemistry",
            "Teacher": "Mr. Usama",
            "Periods_Per_Week": 6,
            "Is_Class_Teacher": "No",
        },
    ])

    if uploaded_tt_file is not None:
      try:
        if uploaded_tt_file.name.endswith(".csv"):
          df_loaded = pd.read_csv(uploaded_tt_file)
        else:
          df_loaded = pd.read_excel(uploaded_tt_file)

        rename_map = {}
        for c in df_loaded.columns:
          cl = str(c).strip().lower().replace(" ", "_")
          if "grade" in cl or "class" in cl:
            rename_map[c] = "Grade"
          elif "subject" in cl:
            rename_map[c] = "Subject"
          elif "teacher" in cl:
            rename_map[c] = "Teacher"
          elif "period" in cl:
            rename_map[c] = "Periods_Per_Week"
          elif "class_teacher" in cl or "role" in cl:
            rename_map[c] = "Is_Class_Teacher"
        df_loaded = df_loaded.rename(columns=rename_map)
        if all(
            col in df_loaded.columns
            for col in ["Grade", "Subject", "Teacher", "Periods_Per_Week"]
        ):
          default_workload = df_loaded
          st.success("✅ File loaded successfully!")
      except Exception as e:
        st.error(f"Error parsing file: {e}")

    workload_df = st.data_editor(
        default_workload, num_rows="dynamic", use_container_width=True
    )

    if st.button("⚡ Generate Master Timetable", type="primary"):
      assignments = []
      auto_class_teachers = {}
      for _, r in workload_df.iterrows():
        if (
            pd.notna(r["Grade"])
            and pd.notna(r["Subject"])
            and pd.notna(r["Teacher"])
        ):
          grade_val = str(r["Grade"]).strip()
          subj_val = str(r["Subject"]).strip()
          teacher_val = str(r["Teacher"]).strip()
          periods_val = int(r["Periods_Per_Week"])
          is_ct = str(r.get("Is_Class_Teacher", "No")).strip().lower() in [
              "yes",
              "true",
              "1",
              "y",
          ]

          assignments.append({
              "grade": grade_val,
              "subject": subj_val,
              "teacher": teacher_val,
              "periods_per_week": periods_val,
          })
          if is_ct:
            auto_class_teachers[grade_val] = {
                "teacher": teacher_val,
                "subject": subj_val,
            }

      with st.spinner(
          "Generating 6-day timetable with Period 1 Class Teacher & Period 8"
          " rules..."
      ):
        grade_tt, teacher_tt, errs = generate_institutional_timetable(
            assignments, auto_class_teachers
        )

      if errs:
        for e in errs:
          st.error(e)
      else:
        st.session_state["grade_tt"] = grade_tt
        st.session_state["teacher_tt"] = teacher_tt
        st.session_state["grades_list"] = list(grade_tt.keys())
        st.session_state["teachers_list"] = list(teacher_tt.keys())
        st.success(
            "✅ Master Timetable generated successfully for"
            f" {len(grade_tt)} grades and {len(teacher_tt)} teachers!"
        )

  with tab2:
    if "grade_tt" in st.session_state:
      view_opt = st.radio(
          "Select Schedule View:",
          [
              "🏫 Whole School Master View (Daily Matrix)",
              "📚 Individual Class Timetable",
              "👨‍🏫 Individual Teacher Workload",
          ],
          horizontal=True,
      )

      if view_opt == "🏫 Whole School Master View (Daily Matrix)":
        sel_day = st.selectbox("Day of Week", list(DAYS_SCHEDULE.keys()))
        master_df = build_whole_school_dataframe(
            st.session_state["grade_tt"], sel_day
        )
        st.markdown(f"#### Whole School Master Matrix — {sel_day.upper()}")
        st.dataframe(master_df, use_container_width=True)

        pdf_path = os.path.join(temp_dir, f"School_Master_{sel_day}.pdf")
        export_timetable_pdf(
            master_df,
            school_name,
            f"WHOLE SCHOOL MASTER MATRIX — {sel_day.upper()}",
            pdf_path,
        )
        with open(pdf_path, "rb") as f:
          st.download_button(
              f"📥 Download {sel_day} Master PDF",
              data=f,
              file_name=f"School_Master_{sel_day}.pdf",
              mime="application/pdf",
          )

      elif view_opt == "📚 Individual Class Timetable":
        sel_g = st.selectbox(
            "Select Class/Grade", st.session_state["grades_list"]
        )
        c_df = format_schedule_to_dataframe(
            st.session_state["grade_tt"][sel_g], mode="grade"
        )
        st.dataframe(c_df, use_container_width=True)

        pdf_path = os.path.join(temp_dir, f"{sel_g}_Timetable.pdf")
        export_timetable_pdf(
            c_df, school_name, f"CLASS SCHEDULE — {sel_g.upper()}", pdf_path
        )
        with open(pdf_path, "rb") as f:
          st.download_button(
              f"📥 Download {sel_g} PDF",
              data=f,
              file_name=f"{sel_g}_Timetable.pdf",
              mime="application/pdf",
          )

      else:
        sel_t = st.selectbox(
            "Select Teacher", st.session_state["teachers_list"]
        )
        t_df = format_schedule_to_dataframe(
            st.session_state["teacher_tt"][sel_t], mode="teacher"
        )
        st.dataframe(t_df, use_container_width=True)

        pdf_path = os.path.join(temp_dir, f"{sel_t}_Workload.pdf")
        export_timetable_pdf(
            t_df, school_name, f"TEACHER WORKLOAD — {sel_t.upper()}", pdf_path
        )
        with open(pdf_path, "rb") as f:
          st.download_button(
              f"📥 Download {sel_t} PDF",
              data=f,
              file_name=f"{sel_t}_Workload.pdf",
              mime="application/pdf",
          )
    else:
      st.info("Please generate the timetable in Tab 1 first.")

  with tab3:
    st.markdown("##### 🔄 Dynamic Teacher Leave & Smart Substitution")
    st.caption(
        "Automatically allocates available teachers with lowest daily teaching"
        " load when an educator is absent."
    )

    if "grade_tt" in st.session_state:
      s_c1, s_c2 = st.columns(2)
      with s_c1:
        abs_tch = st.selectbox(
            "Teacher on Leave", st.session_state["teachers_list"]
        )
      with s_c2:
        abs_day = st.selectbox("Leave Day", list(DAYS_SCHEDULE.keys()))

      if st.button("⚡ Generate Substitute Schedule", type="primary"):
        sub_grade_tt, sub_log = generate_substitution_timetable(
            st.session_state["grade_tt"],
            st.session_state["teacher_tt"],
            abs_tch,
            abs_day,
        )

        st.markdown(f"#### Substitute Assignment Log: {abs_tch} ({abs_day})")
        if not sub_log.empty:
          st.dataframe(sub_log, use_container_width=True)

          st.markdown(f"#### Adjusted Whole School Timetable for {abs_day}")
          sub_master = build_whole_school_dataframe(sub_grade_tt, abs_day)
          st.dataframe(sub_master, use_container_width=True)

          pdf_path = os.path.join(temp_dir, f"Adjusted_Timetable_{abs_day}.pdf")
          export_timetable_pdf(
              sub_master,
              school_name,
              f"SUBSTITUTION TIMETABLE — {abs_day.upper()}",
              pdf_path,
          )
          with open(pdf_path, "rb") as f:
            st.download_button(
                "📥 Download Adjusted Schedule PDF",
                data=f,
                file_name=f"Adjusted_{abs_day}.pdf",
                mime="application/pdf",
            )
        else:
          st.success(f"{abs_tch} has no classes scheduled on {abs_day}.")
    else:
      st.info("Please generate the master timetable in Tab 1 first.")


if __name__ == "__main__":
  st.set_page_config(
      page_title="Master Timetable Scheduler", page_icon="🗓️", layout="wide"
  )
  render_master_timetable_page()
