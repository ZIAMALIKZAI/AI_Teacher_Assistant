"""
generate_sample_marks.py
Generates realistic sample student marks files (CSV & XLSX)
for testing the AI Teacher Assistant's marks processing and certificate generator.
"""

import random
import pandas as pd

# List of realistic student records
STUDENTS = [
    ("101", "Ahmad Ali", "M. Ali"),
    ("102", "Bilal Khan", "Tariq Khan"),
    ("103", "Ayesha Bibi", "Muhammad Farooq"),
    ("104", "Hamza Javed", "Javed Iqbal"),
    ("105", "Zainab Fatima", "Abdul Rehman"),
    ("106", "Usman Ghani", "Ghani Ur Rehman"),
    ("107", "Maryam Noor", "Noor Muhammad"),
    ("108", "Saad Ullah", "Inam Ullah"),
    ("109", "Fatima Zahra", "Rashid Mehmood"),
    ("110", "Umer Farooq", "Farooq Ahmad"),
    ("111", "Hassan Raza", "Ghulam Raza"),
    ("112", "Sana Tariq", "Tariq Mehmood"),
]

SUBJECTS = [
    ("CS-101", "Computer Science", 100),
    ("ENG-101", "English", 100),
    ("MATH-101", "Mathematics", 100),
    ("PHY-101", "Physics", 100),
    ("ISL-101", "Islamiat", 50),
]


def create_sample_files():
    # 1. Generate Single Subject Award List (CSV)
    award_list_rows = []
    for roll, name, father in STUDENTS:
        award_list_rows.append(
            {
                "Roll Number": roll,
                "Student Name": name,
                "Father Name": father,
                "Class": "Grade 10",
                "Subject Code": "CS-101",
                "Subject": "Computer Science",
                "Total Marks": 100,
                "Obtained Marks": random.randint(52, 97),
            }
        )

    df_award_list = pd.DataFrame(award_list_rows)
    csv_file = "sample_award_list.csv"
    df_award_list.to_csv(csv_file, index=False)
    print(f"Created {csv_file} ({len(df_award_list)} rows)")

    # 2. Generate Multi-Subject Comprehensive Sheet (XLSX)
    xlsx_file = "sample_student_marks.xlsx"
    with pd.ExcelWriter(xlsx_file, engine="openpyxl") as writer:
        # Sheet 1: Single subject award list
        df_award_list.to_excel(
            writer, sheet_name="Subject Award List", index=False
        )

        # Sheet 2: Multi-subject report card table
        comprehensive_rows = []
        for roll, name, father in STUDENTS:
            for code, subj, tot in SUBJECTS:
                obt = (
                    random.randint(50, 98)
                    if tot == 100
                    else random.randint(22, 49)
                )
                comprehensive_rows.append(
                    {
                        "Roll Number": roll,
                        "Student Name": name,
                        "Father Name": father,
                        "Class": "Grade 10",
                        "Subject Code": code,
                        "Subject": subj,
                        "Total Marks": tot,
                        "Obtained Marks": obt,
                    }
                )

        df_comp = pd.DataFrame(comprehensive_rows)
        df_comp.to_excel(writer, sheet_name="Comprehensive Marks", index=False)
        print(f"Created {xlsx_file} with 2 tabs ({len(df_comp)} total rows)")


if __name__ == "__main__":
    create_sample_files()
