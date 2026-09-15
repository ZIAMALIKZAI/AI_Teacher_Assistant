"""
master_timetable.py: Advanced Institutional Master Timetable Scheduler.
Features:
- 6 Days a Week (Mon-Thu: 8 periods, Fri: 5 periods, Sat: 8 periods = 45 slots/week)
- Class Teacher assigned to Period 1 every day (Mon-Sat)
- Strict Rule: Teachers assigned to Period 1 do not take Period 8 on that day
- Zero-clash bipartite multi-grade scheduling
- Dynamic Leave / Substitute Teacher reallocation based on minimum daily load
- Full Whole-School Combined Master Matrix view + A4 PDF Export
"""

import os
import random
import copy
import pandas as pd
import streamlit as st
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# Weekly periods distribution
DAYS_SCHEDULE = {
    "Monday": 8,
    "Tuesday": 8,
    "Wednesday": 8,
    "Thursday": 8,
    "Friday": 5,
    "Saturday": 8
}
TOTAL_WEEKLY_SLOTS = sum(DAYS_SCHEDULE.values())  # 45 periods


def build_empty_slots():
    """Generates ordered list of (Day, Period) tuples across all 6 days."""
    slots = []
    for day, count in DAYS_SCHEDULE.items():
        for p in range(1, count + 1):
            slots.append((day, f"Period {p}"))
    return slots


def generate_institutional_timetable(
    teaching_assignments: list[dict],
    class_teachers: dict[str, dict]
) -> tuple[dict, dict, list]:
    """
    Generates a collision-free schedule across all grades.
    
    class_teachers format:
    {"Grade 9": {"teacher": "Mr. Ahmad", "subject": "Mathematics"}}
    """
    all_slots = build_empty_slots()
    grades = list(set([item["grade"] for item in teaching_assignments]))
    all_teachers = list(set([item["teacher"] for item in teaching_assignments]))

    # Validate weekly quotas
    errors = []
    grade_totals = {}
    for item in teaching_assignments:
        g = item["grade"]
        grade_totals[g] = grade_totals.get(g, 0) + item["periods_per_week"]

    for g, tot in grade_totals.items():
        if tot > TOTAL_WEEKLY_SLOTS:
            errors.append(f"⚠️ Error in {g}: Assigned {tot} periods exceeds weekly limit of {TOTAL_WEEKLY_SLOTS}.")

    if errors:
        return {}, {}, errors

    max_attempts = 200
    for attempt in range(max_attempts):
        timetable_by_grade = {g: {slot: ("Free", "-") for slot in all_slots} for g in grades}
        teacher_busy_slots = {slot: set() for slot in all_slots}
        
        # Track which teacher is in Period 1 on which day
        teachers_in_period1 = {day: set() for day in DAYS_SCHEDULE.keys()}

        # -------------------------------------------------------------
        # STEP 1: Fix Class Teacher in Period 1 for all 6 days
        # -------------------------------------------------------------
        class_teacher_clash = False
        remaining_assignments = copy.deepcopy(teaching_assignments)

        for grade, ct_info in class_teachers.items():
            ct_name = ct_info.get("teacher")
            ct_subj = ct_info.get("subject")
            if not ct_name or not ct_subj:
                continue

            for day in DAYS_SCHEDULE.keys():
                slot = (day, "Period 1")
                if ct_name in teacher_busy_slots[slot]:
                    class_teacher_clash = True
                    break
                timetable_by_grade[grade][slot] = (ct_subj, ct_name)
                teacher_busy_slots[slot].add(ct_name)
                teachers_in_period1[day].add(ct_name)

            if class_teacher_clash:
                break

            # Deduct the 6 periods from the assigned teacher quota
            for item in remaining_assignments:
                if item["grade"] == grade and item["teacher"] == ct_name and item["subject"] == ct_subj:
                    item["periods_per_week"] = max(0, item["periods_per_week"] - 6)

        if class_teacher_clash:
            continue

        # -------------------------------------------------------------
        # STEP 2: Allocate all remaining periods with strict rules
        # -------------------------------------------------------------
        allocation_queue = []
        for item in remaining_assignments:
            for _ in range(item["periods_per_week"]):
                allocation_queue.append({
                    "grade": item["grade"],
                    "subject": item["subject"],
                    "teacher": item["teacher"]
                })

        random.shuffle(allocation_queue)
        # Prioritize teachers with higher remaining load
        t_counts = {}
        for x in allocation_queue:
            t_counts[x["teacher"]] = t_counts.get(x["teacher"], 0) + 1
        allocation_queue.sort(key=lambda x: t_counts[x["teacher"]], reverse=True)

        success = True
        for task in allocation_queue:
            grade = task["grade"]
            teacher = task["teacher"]
            subj = task["subject"]

            valid_slots = []
            for slot in all_slots:
                day, period_str = slot
                
                # Check if slot is already occupied
                if timetable_by_grade[grade][slot][0] != "Free":
                    continue
                if teacher in teacher_busy_slots[slot]:
                    continue

                # RULE: If this slot is Period 8, teacher must NOT have been in Period 1 on this day
                if period_str == "Period 8" and teacher in teachers_in_period1[day]:
                    continue

                # RULE: If allocating Period 1 to a regular teacher, ensure they are not already in Period 8 on that day
                if period_str == "Period 1":
                    p8_slot = (day, "Period 8")
                    if p8_slot in timetable_by_grade[grade] and teacher in teacher_busy_slots[p8_slot]:
                        continue

                valid_slots.append(slot)

            if not valid_slots:
                success = False
                break

            chosen_slot = random.choice(valid_slots)
            timetable_by_grade[grade][chosen_slot] = (subj, teacher)
            teacher_busy_slots[chosen_slot].add(teacher)

            day, period_str = chosen_slot
            if period_str == "Period 1":
                teachers_in_period1[day].add(teacher)

        if success:
            # Build teacher-centric schedule
            timetable_by_teacher = {t: {slot: ("Free", "-") for slot in all_slots} for t in all_teachers}
            for grade, schedule in timetable_by_grade.items():
                for slot, (subj, teacher) in schedule.items():
                    if teacher != "-":
                        timetable_by_teacher[teacher][slot] = (subj, grade)

            return timetable_by_grade, timetable_by_teacher, []

    return {}, {}, ["Unable to find a clash-free combination with the given rules. Try adjusting subject loads."]


# -------------------------------------------------------------
# Leave & Substitution Engine
# -------------------------------------------------------------
def generate_substitution_timetable(
    base_grade_tt: dict,
    base_teacher_tt: dict,
    absent_teacher: str,
    leave_day: str
) -> tuple[dict, pd.DataFrame]:
    """
    Creates a temporary daily adjustment when a teacher is on leave:
    Finds teachers who are FREE during the absent teacher's periods on that day,
    and assigns the substitute who currently has the MINIMUM teaching load that day.
    """
    sub_grade_tt = copy.deepcopy(base_grade_tt)
    all_teachers = list(base_teacher_tt.keys())
    day_periods_count = DAYS_SCHEDULE[leave_day]

    # Calculate base teaching load of each teacher on the absent day
    daily_load = {t: 0 for t in all_teachers if t != absent_teacher}
    for t in daily_load.keys():
        for p in range(1, day_periods_count + 1):
            slot = (leave_day, f"Period {p}")
            if base_teacher_tt[t].get(slot, ("Free", "-"))[0] != "Free":
                daily_load[t] += 1

    substitution_log = []

    for p in range(1, day_periods_count + 1):
        slot = (leave_day, f"Period {p}")

        for grade, g_sched in sub_grade_tt.items():
            subj, t_assigned = g_sched.get(slot, ("Free", "-"))

            if t_assigned == absent_teacher:
                # Find available teachers at this exact period
                available_teachers = []
                for candidate in daily_load.keys():
                    # Candidate must be free at this period
                    if base_teacher_tt[candidate].get(slot, ("Free", "-"))[0] == "Free":
                        # Check rule: If substitute is assigned to Period 8, ensure not in Period 1
                        if f"Period {p}" == "Period 8":
                            p1_slot = (leave_day, "Period 1")
                            if base_teacher_tt[candidate].get(p1_slot, ("Free", "-"))[0] != "Free":
                                continue
                        available_teachers.append(candidate)

                if available_teachers:
                    # Select teacher with minimum daily load
                    available_teachers.sort(key=lambda t: daily_load[t])
                    selected_sub = available_teachers[0]

                    # Assign substitution
                    sub_grade_tt[grade][slot] = (f"{subj} (Sub)", selected_sub)
                    daily_load[selected_sub] += 1

                    substitution_log.append({
                        "Day": leave_day,
                        "Period": f"Period {p}",
                        "Class": grade,
                        "Subject": subj,
                        "Absent Teacher": absent_teacher,
                        "Substitute Assigned": selected_sub,
                        "Sub's Total Load Today": daily_load[selected_sub]
                    })
                else:
                    sub_grade_tt[grade][slot] = (f"{subj} (No Sub Avail)", "Unassigned")
                    substitution_log.append({
                        "Day": leave_day,
                        "Period": f"Period {p}",
                        "Class": grade,
                        "Subject": subj,
                        "Absent Teacher": absent_teacher,
                        "Substitute Assigned": "⚠️ No Free Teacher",
                        "Sub's Total Load Today": "-"
                    })

    return sub_grade_tt, pd.DataFrame(substitution_log)


# -------------------------------------------------------------
# Matrix Formatting & Whole-School View
# -------------------------------------------------------------
def format_schedule_to_dataframe(schedule_dict: dict, mode: str = "grade") -> pd.DataFrame:
    rows = []
    for day, num_periods in DAYS_SCHEDULE.items():
        row = {"Day": day}
        for p in range(1, 9):
            if p <= num_periods:
                slot = (day, f"Period {p}")
                val, secondary = schedule_dict.get(slot, ("Free", "-"))
                if val == "Free":
                    row[f"P{p}"] = "—"
                else:
                    if mode == "grade":
                        row[f"P{p}"] = f"{val}\n({secondary})"
                    else:
                        row[f"P{p}"] = f"{val}\n[{secondary}]"
            else:
                row[f"P{p}"] = "Closed"
        rows.append(row)
    return pd.DataFrame(rows)


def build_whole_school_dataframe(grade_tt: dict, selected_day: str) -> pd.DataFrame:
    """Creates a master school matrix showing all classes side-by-side for a specific day."""
    num_periods = DAYS_SCHEDULE[selected_day]
    rows = []

    for grade, schedule in grade_tt.items():
        row = {"Class / Grade": grade}
        for p in range(1, num_periods + 1):
            slot = (selected_day, f"Period {p}")
            val, secondary = schedule.get(slot, ("Free", "-"))
            row[f"Period {p}"] = f"{val} ({secondary})" if val != "Free" else "—"
        rows.append(row)

    return pd.DataFrame(rows)


def export_timetable_pdf(df: pd.DataFrame, title_header: str, subtitle: str, output_path: str) -> str:
    """Renders high-resolution A4 landscape printable grid."""
    doc = SimpleDocTemplate(
        output_path,
        pagesize=landscape(A4),
        rightMargin=20,
        leftMargin=20,
        topMargin=20,
        bottomMargin=20
    )
    styles = getSampleStyleSheet()
    h_style = ParagraphStyle("Hdr", parent=styles["Heading1"], fontSize=14, alignment=1, textColor=colors.HexColor("#1e3a8a"))
    sub_style = ParagraphStyle("Sub", parent=styles["Heading2"], fontSize=10, alignment=1, textColor=colors.HexColor("#475569"))
    cell_style = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=7, leading=9, alignment=1)
    cell_bold = ParagraphStyle("CellB", parent=styles["Normal"], fontSize=8, leading=10, alignment=1, fontName="Helvetica-Bold")

    elements = [
        Paragraph(title_header.upper(), h_style),
        Paragraph(subtitle, sub_style),
        Spacer(1, 10)
    ]

    cols = list(df.columns)
    table_data = [[Paragraph(f"<b>{c}</b>", cell_bold) for c in cols]]

    for _, r in df.iterrows():
        r_cells = []
        for c in cols:
            text = str(r[c]).replace("\n", "<br/>")
            r_cells.append(Paragraph(text, cell_style))
        table_data.append(r_cells)

    page_w = landscape(A4)[0] - 40
    col_w = page_w / len(cols)

    t = Table(table_data, colWidths=[col_w] * len(cols))
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#94a3b8")),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(t)
    doc.build(elements)
    return output_path


# =========================================================================
# Streamlit Interface
# =========================================================================
def render_master_timetable_page(school_name: str = "Government High School"):
    st.subheader("🗓️ Complete School Master Timetable & Substitution Engine")
    st.caption("6 Days (Mon-Thu: 8 Periods | Fri: 5 Periods | Sat: 8 Periods = 45 Periods/Week). Class Teacher 1st Period Rule Enforced.")

    temp_dir = "temp_output"
    os.makedirs(temp_dir, exist_ok=True)

    tt_tab1, tt_tab2, tt_tab3 = st.tabs([
        "⚙️ Configuration & Master Generator",
        "🏫 Whole School & Class Views",
        "🔄 Teacher Leave & Substitute Engine"
    ])

    with tt_tab1:
        st.markdown("##### 1. Assign Class Teachers (1st Period Every Day: Mon–Sat)")
        c_col1, c_col2, c_col3, c_col4 = st.columns(4)
        with c_col1:
            g9_ct = st.text_input("Grade 9 Class Teacher", value="Mr. Ahmad")
            g9_subj = st.text_input("Grade 9 CT Subject", value="Mathematics")
        with c_col2:
            g10_ct = st.text_input("Grade 10 Class Teacher", value="Mr. Tariq")
            g10_subj = st.text_input("Grade 10 CT Subject", value="Computer Science")
        with c_col3:
            g7_ct = st.text_input("Grade 7 Class Teacher (Optional)", value="")
            g7_subj = st.text_input("Grade 7 CT Subject", value="")
        with c_col4:
            g8_ct = st.text_input("Grade 8 Class Teacher (Optional)", value="")
            g8_subj = st.text_input("Grade 8 CT Subject", value="")

        class_teachers = {}
        if g9_ct and g9_subj:
            class_teachers["Grade 9"] = {"teacher": g9_ct.strip(), "subject": g9_subj.strip()}
        if g10_ct and g10_subj:
            class_teachers["Grade 10"] = {"teacher": g10_ct.strip(), "subject": g10_subj.strip()}
        if g7_ct and g7_subj:
            class_teachers["Grade 7"] = {"teacher": g7_ct.strip(), "subject": g7_subj.strip()}
        if g8_ct and g8_subj:
            class_teachers["Grade 8"] = {"teacher": g8_ct.strip(), "subject": g8_subj.strip()}

        st.markdown("##### 2. Define Subjects & Weekly Teaching Loads (Total 45 Periods / Grade)")
        default_data = pd.DataFrame([
            {"Grade": "Grade 9", "Subject": "Mathematics", "Teacher": "Mr. Ahmad", "Periods/Week": 8},
            {"Grade": "Grade 9", "Subject": "Computer Science", "Teacher": "Mr. Tariq", "Periods/Week": 7},
            {"Grade": "Grade 9", "Subject": "Physics", "Teacher": "Ms. Ayesha", "Periods/Week": 7},
            {"Grade": "Grade 9", "Subject": "English", "Teacher": "Mr. Bilal", "Periods/Week": 7},
            {"Grade": "Grade 9", "Subject": "Islamiat", "Teacher": "Mr. Hamza", "Periods/Week": 5},
            {"Grade": "Grade 9", "Subject": "Pak Studies", "Teacher": "Ms. Fatima", "Periods/Week": 5},
            {"Grade": "Grade 9", "Subject": "Chemistry", "Teacher": "Mr. Usama", "Periods/Week": 6},

            {"Grade": "Grade 10", "Subject": "Computer Science", "Teacher": "Mr. Tariq", "Periods/Week": 8},
            {"Grade": "Grade 10", "Subject": "Mathematics", "Teacher": "Mr. Ahmad", "Periods/Week": 7},
            {"Grade": "Grade 10", "Subject": "Physics", "Teacher": "Ms. Ayesha", "Periods/Week": 7},
            {"Grade": "Grade 10", "Subject": "English", "Teacher": "Mr. Bilal", "Periods/Week": 7},
            {"Grade": "Grade 10", "Subject": "Islamiat", "Teacher": "Mr. Hamza", "Periods/Week": 5},
            {"Grade": "Grade 10", "Subject": "Pak Studies", "Teacher": "Ms. Fatima", "Periods/Week": 5},
            {"Grade": "Grade 10", "Subject": "Chemistry", "Teacher": "Mr. Usama", "Periods/Week": 6},
        ])

        edited_df = st.data_editor(default_data, num_rows="dynamic", use_container_width=True)

        if st.button("⚡ Generate Complete Collision-Free Timetable", type="primary"):
            assignments = []
            for _, r in edited_df.iterrows():
                if pd.notna(r["Grade"]) and pd.notna(r["Subject"]) and pd.notna(r["Teacher"]):
                    assignments.append({
                        "grade": str(r["Grade"]).strip(),
                        "subject": str(r["Subject"]).strip(),
                        "teacher": str(r["Teacher"]).strip(),
                        "periods_per_week": int(r["Periods/Week"])
                    })

            with st.spinner("Calculating optimal timetable (enforcing Period 1 CT & Period 8 rules)..."):
                grade_tt, teacher_tt, errs = generate_institutional_timetable(assignments, class_teachers)

            if errs:
                for e in errs:
                    st.error(e)
            else:
                st.session_state["grade_tt"] = grade_tt
                st.session_state["teacher_tt"] = teacher_tt
                st.session_state["grades_list"] = list(grade_tt.keys())
                st.session_state["teachers_list"] = list(teacher_tt.keys())
                st.success("✅ Timetable successfully generated with zero clashes! Class teachers are placed in Period 1 daily, and Period 1 teachers are excluded from Period 8.")

    with tt_tab2:
        if "grade_tt" in st.session_state:
            view_choice = st.radio("Choose Timetable View:", ["🏫 Complete School Master View (Daily Matrix)", "📚 Individual Class View", "👨‍🏫 Individual Teacher View"], horizontal=True)

            if view_choice == "🏫 Complete School Master View (Daily Matrix)":
                sel_day = st.selectbox("Select Day to View All Classes", list(DAYS_SCHEDULE.keys()))
                master_df = build_whole_school_dataframe(st.session_state["grade_tt"], sel_day)
                st.markdown(f"#### Master Schedule: {sel_day.upper()} (All Grades)")
                st.dataframe(master_df, use_container_width=True)

                pdf_path = os.path.join(temp_dir, f"Whole_School_{sel_day}.pdf")
                export_timetable_pdf(master_df, school_name, f"WHOLE SCHOOL MASTER SCHEDULE — {sel_day.upper()}", pdf_path)
                with open(pdf_path, "rb") as f:
                    st.download_button(f"📥 Download {sel_day} Master PDF", data=f, file_name=f"Whole_School_{sel_day}.pdf", mime="application/pdf")

            elif view_choice == "📚 Individual Class View":
                sel_g = st.selectbox("Select Class / Grade", st.session_state["grades_list"])
                c_df = format_schedule_to_dataframe(st.session_state["grade_tt"][sel_g], mode="grade")
                st.dataframe(c_df, use_container_width=True)

                pdf_path = os.path.join(temp_dir, f"{sel_g}_Schedule.pdf")
                export_timetable_pdf(c_df, school_name, f"CLASS TIMETABLE — {sel_g.upper()}", pdf_path)
                with open(pdf_path, "rb") as f:
                    st.download_button(f"📥 Download {sel_g} PDF", data=f, file_name=f"{sel_g}_Schedule.pdf", mime="application/pdf")

            else:
                sel_t = st.selectbox("Select Teacher", st.session_state["teachers_list"])
                t_df = format_schedule_to_dataframe(st.session_state["teacher_tt"][sel_t], mode="teacher")
                st.dataframe(t_df, use_container_width=True)

                pdf_path = os.path.join(temp_dir, f"{sel_t}_Schedule.pdf")
                export_timetable_pdf(t_df, school_name, f"TEACHER WORKLOAD — {sel_t.upper()}", pdf_path)
                with open(pdf_path, "rb") as f:
                    st.download_button(f"📥 Download {sel_t} PDF", data=f, file_name=f"{sel_t}_Schedule.pdf", mime="application/pdf")
        else:
            st.info("Please generate the timetable in Tab 1 first.")

    with tt_tab3:
        st.markdown("##### 🔄 Automatic Teacher Leave & Substitution System")
        st.caption("When a teacher is absent, the system finds free teachers at those periods and assigns the teacher with the minimum daily load.")

        if "grade_tt" in st.session_state:
            sub_col1, sub_col2 = st.columns(2)
            with sub_col1:
                abs_teacher = st.selectbox("Teacher on Leave", st.session_state["teachers_list"])
            with sub_col2:
                abs_day = st.selectbox("Leave Day", list(DAYS_SCHEDULE.keys()))

            if st.button("⚡ Generate Daily Substitution Schedule", type="primary"):
                sub_grade_tt, log_df = generate_substitution_timetable(
                    st.session_state["grade_tt"],
                    st.session_state["teacher_tt"],
                    abs_teacher,
                    abs_day
                )

                st.markdown(f"#### Substitution Log for {abs_teacher} on {abs_day}")
                if not log_df.empty:
                    st.dataframe(log_df, use_container_width=True)

                    st.markdown(f"#### Adjusted School Schedule for {abs_day}")
                    sub_master_df = build_whole_school_dataframe(sub_grade_tt, abs_day)
                    st.dataframe(sub_master_df, use_container_width=True)

                    sub_pdf = os.path.join(temp_dir, f"Substitute_Schedule_{abs_day}.pdf")
                    export_timetable_pdf(sub_master_df, school_name, f"SUBSTITUTION ADJUSTED SCHEDULE — {abs_day.upper()}", sub_pdf)
                    with open(sub_pdf, "rb") as f:
                        st.download_button("📥 Download Adjusted Timetable PDF", data=f, file_name=f"Adjusted_{abs_day}.pdf", mime="application/pdf")
                else:
                    st.success(f"{abs_teacher} has no classes scheduled on {abs_day}.")
        else:
            st.info("Generate the master timetable in Tab 1 first.")


if __name__ == "__main__":
    st.set_page_config(page_title="Master Timetable Scheduler", page_icon="🗓️", layout="wide")
    render_master_timetable_page()
