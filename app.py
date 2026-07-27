import streamlit as st
import pandas as pd
import os
import json
import random
import time
import uuid
import base64
import ast
from datetime import datetime
import streamlit.components.v1 as components
from groq import Groq
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="School Quiz Champion Pro", layout="wide", initial_sidebar_state="expanded")

# --- SYSTEM INITIALIZATION & SESSION STATE ---

if "live_questions" not in st.session_state:
    st.session_state.live_questions = []

if "current_q_index" not in st.session_state:
    st.session_state.current_q_index = 0

if "show_answer" not in st.session_state:
    st.session_state.show_answer = False

if "quiz_state" not in st.session_state:
    st.session_state.quiz_state = "setup"

# --- CUSTOM BALANCED CSS ---
st.markdown("""
    <style>
    /* Safe top padding so the sidebar and page titles don't get cut off */
    .block-container {
        padding-top: 3rem !important; 
        padding-bottom: 2rem !important;
    }
    /* Relaxed gap so elements have breathing room but remain compact */
    div[data-testid="stVerticalBlock"] {
        gap: 0.8rem !important;
    }
    /* Balanced button sizes */
    .stButton > button {
        padding: 0.4rem 0.8rem !important;
        min-height: 2.5rem !important;
        border-radius: 6px !important;
    }
    /* Compact the dropdown selector without squashing it */
    div[data-testid="stSelectbox"] div[role="combobox"] {
        min-height: 2.5rem !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- GOOGLE SHEETS CONNECTION ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- HELPER FUNCTIONS FOR IMAGES ---
def process_image_upload(uploaded_file):
    """Validates file size (max 100 KB) and returns base64 string or error message."""
    if uploaded_file is not None:
        if uploaded_file.size > 100 * 1024:
            return None, "⚠️ File size exceeds the 100 KB limit! Please choose a smaller image."
        bytes_data = uploaded_file.read()
        encoded = base64.b64encode(bytes_data).decode("utf-8")
        mime_type = uploaded_file.type
        return f"data:{mime_type};base64,{encoded}", None
    return "", None

# --- EXAM MODE URL INTERCEPTOR (STAGE 3) ---
if "exam" in st.query_params:
    exam_id_param = st.query_params["exam"]
    
    try:
        df_active = conn.read(worksheet="Active_Exams", ttl="10m")
        exam_data = df_active[df_active["Exam_ID"] == exam_id_param]
    except Exception as e:
        st.error("Could not connect to the database.")
        st.stop()

    if exam_data.empty:
        st.error("❌ This exam link is invalid or the exam has been deleted.")
        st.stop()
        
    exam_info = exam_data.iloc[0]
    
    # Render Header
    st.markdown(f"<h1 style='text-align: center; color: var(--text-color);'>{exam_info.get('School_Name', '')}</h1>", unsafe_allow_html=True)
    st.markdown(f"<h3 style='text-align: center; color: #38bdf8;'>{exam_info.get('Exam_Title', '')}</h3>", unsafe_allow_html=True)
    
    examiner_name = str(exam_info.get('Examiner_Name', '')).strip()
    if examiner_name and examiner_name.lower() != "nan":
        st.markdown(f"<p style='text-align: center; color: var(--text-color); opacity: 0.8; font-size: 1.1rem;'><b>Examiner:</b> {examiner_name}</p>", unsafe_allow_html=True)
    
    if "exam_state" not in st.session_state:
        st.session_state.exam_state = "landing"
        
    # --- LANDING PAGE VIEW ---
    if st.session_state.exam_state == "landing":
        st.write("---")
        st.markdown(f"<div style='text-align: center; font-style: italic; font-size: 1.1rem; color: #475569;'><b>Instructions:</b><br>{exam_info['Instructions']}</div>", unsafe_allow_html=True)
        st.write("---")
        
        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader("📝 Student Registration")
            student_name = st.text_input("Full Name (Surname First)")
            student_class = st.text_input("Class")
            student_contact = st.text_input("Contact / Phone Number (Optional)")
            
            if st.button("🚀 Start Exam", type="primary", use_container_width=True):
                try:
                    df_results_check = conn.read(worksheet="Student_Results", ttl="0m")
                    exam_history = df_results_check[df_results_check["Exam_ID"] == exam_info["Exam_ID"]]
                    taken_names = [str(name).strip().lower() for name in exam_history["Student_Name"].dropna().tolist()]
                except Exception:
                    taken_names = []

                current_time = datetime.now()
                try:
                    start_dt = datetime.strptime(str(exam_info["Start_DateTime"]), "%Y-%m-%d %H:%M:%S")
                    end_dt = datetime.strptime(str(exam_info["End_DateTime"]), "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    start_dt = pd.to_datetime(exam_info["Start_DateTime"])
                    end_dt = pd.to_datetime(exam_info["End_DateTime"])

                if not student_name or not student_class:
                    st.error("⚠️ Please enter your name and class to begin.")
                elif student_name.strip().lower() in taken_names:
                    st.error(f"🛑 Access Denied: A submission for '{student_name.strip()}' has already been recorded.")
                elif current_time < start_dt:
                    st.error(f"⏳ **Too Early:** This exam opens on {start_dt.strftime('%B %d, %Y at %I:%M %p')}.")
                elif current_time > end_dt:
                    st.error("🛑 **Exam Closed:** The submission window for this exam has expired.")
                else:
                    st.session_state.student_info = {"name": student_name, "class": student_class, "contact": student_contact}
                    st.session_state.exam_state = "in_progress"
                    st.session_state.exam_start_time = time.time()
                    st.session_state.result_saved = False
                    st.rerun()

        with col2:
            st.subheader("👨‍🏫 Examiner Portal")
            entered_pin = st.text_input("Enter Exam PIN", type="password")
            if st.button("📊 View Scores", use_container_width=True):
                db_pin = str(exam_info["Exam_PIN"]).split(".")[0].strip()
                if entered_pin.strip() == db_pin:
                    st.session_state.exam_state = "examiner_dashboard"
                    st.rerun()
                else:
                    st.error("Incorrect PIN. Access Denied.")

    # --- IN PROGRESS VIEW (STAGE 4) ---
    elif st.session_state.exam_state == "in_progress":
        st.markdown("""
        <style>
        .stRadio label p { font-size: 22px !important; margin-left: 10px; line-height: 1.5; color: var(--text-color) !important; }
        .stRadio div[role="radio"] { transform: scale(1.6); margin-top: 2px; }
        .stRadio > div { gap: 1.5rem !important; }
        </style>
        """, unsafe_allow_html=True)
        
        if "exam_qs" not in st.session_state:
            df_eq = conn.read(worksheet="Exam_Questions", ttl="10m")
            q_list = df_eq[df_eq["Exam_ID"] == exam_info["Exam_ID"]].to_dict('records')
            st.session_state.exam_qs = q_list
            if "student_answers" not in st.session_state:
                st.session_state.student_answers = {} 
            st.session_state.current_q = 0
            
        qs = st.session_state.exam_qs
        idx = st.session_state.current_q
        
        if not qs:
            st.error("⚠️ No questions were found loaded for this exam ID.")
            st.stop()
            
        current_q_data = qs[idx]
        
        elapsed_seconds = time.time() - st.session_state.exam_start_time
        try:
            allowed_secs = int(exam_info["Timer_Seconds"])
        except Exception:
            allowed_secs = 1800 
        time_left = max(0, allowed_secs - elapsed_seconds)
        
        top1, top2 = st.columns(2)
        with top1:
            timer_html = f"""
            <div id="exam_timer" style="font-size: 1.8rem; font-weight: bold; color: #16a34a; font-family: monospace;"></div>
            <script>
            var timeLeft = {time_left};
            var elem = document.getElementById('exam_timer');
            var timerId = setInterval(function() {{
                if (timeLeft <= 0) {{ 
                    clearInterval(timerId); elem.innerHTML = "00:00"; elem.style.color = "red";
                    var btns = window.parent.document.querySelectorAll('button');
                    for(var i=0; i<btns.length; i++) {{
                        if(btns[i].innerText.includes('Submit Exam')) {{ btns[i].click(); }}
                    }}
                }} else {{
                    var m = Math.floor(timeLeft / 60); var s = Math.floor(timeLeft % 60);
                    elem.innerHTML = "⏱️ " + (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s;
                    if(timeLeft < 120) {{ elem.style.color = "#dc2626"; }}
                    timeLeft--;
                }}
            }}, 1000);
            </script>
            """
            st.components.v1.html(timer_html, height=45)
            
        with top2:
             if st.button("Submit Exam 🏁", type="primary", use_container_width=True):
                st.session_state.exam_state = "submitted"
                st.rerun()

        if str(exam_info.get("Allow_Calculator", "False")).lower() in ["true", "1", "yes"]:
            with st.expander("🧮 Open Scientific Calculator", expanded=False):
                st.components.v1.html("""<iframe width="100%" height="350px" style="border: none;" src="https://www.desmos.com/scientific"></iframe>""", height=360)

        st.markdown("---")
        
        # Display Image ABOVE/BEFORE question text if present
        img_data = current_q_data.get('Image', '')
        if pd.notna(img_data) and str(img_data).strip() and str(img_data) != "nan":
            st.image(img_data, caption=f"Question {idx + 1} Image", width=480)

        st.markdown(f"""
        <div style="background-color: var(--secondary-background-color); padding: 15px; border-radius: 8px; border-left: 5px solid #0284c7; margin-bottom: 20px;">
            <span style="color: var(--text-color); opacity: 0.7; font-weight: 600; font-size: 1.1rem;">Question {idx + 1} of {len(qs)}</span>
            <h3 style="color: var(--text-color); margin-top: 10px;">{current_q_data.get('Question_Text', '')}</h3>
        </div>
        """, unsafe_allow_html=True)
        
        saved_ans = st.session_state.student_answers.get(idx, None)
        q_type = str(current_q_data.get('Question_Type', ''))
        
        if "Multiple Choice" in q_type or "Objective" in q_type:
            raw_options = str(current_q_data.get('Options', ''))
            options_list = [opt.strip() for opt in raw_options.split(",") if opt.strip()]
            
            if options_list:
                letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
                formatted_options = []
                for i, opt in enumerate(options_list):
                    prefix = f"{letters[i]}) " if i < len(letters) else ""
                    if opt.startswith(tuple(f"{l})" for l in letters)):
                        formatted_options.append(opt)
                    else:
                        formatted_options.append(f"{prefix}{opt}")
                
                selection = st.radio(
                    "Select your answer:", 
                    formatted_options, 
                    index=formatted_options.index(saved_ans) if saved_ans in formatted_options else None, 
                    key=f"q_radio_{idx}"
                )
                if selection:
                    st.session_state.student_answers[idx] = selection
            else:
                st.warning("⚠️ No options found for this question.")
        else:
            theory_ans = st.text_area(
                "Type your answer here:", 
                value=saved_ans if saved_ans else "", 
                key=f"q_text_{idx}", 
                height=150
            )
            if theory_ans:
                st.session_state.student_answers[idx] = theory_ans
                
        st.write("")
        
        c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
        with c2:
            if st.button("⬅️ Previous", use_container_width=True, disabled=(idx == 0)):
                st.session_state.current_q -= 1
                st.rerun()
        with c3:
            if st.button("Next ➡️", use_container_width=True, disabled=(idx == len(qs) - 1)):
                st.session_state.current_q += 1
                st.rerun()
                
        st.markdown("---")
        
        with st.expander("🔢 View / Jump to Questions", expanded=False):
            cols_per_row = 10 
            for i in range(0, len(qs), cols_per_row):
                grid_cols = st.columns(cols_per_row)
                for j in range(cols_per_row):
                    if i + j < len(qs):
                        q_index = i + j
                        is_answered = pd.notna(st.session_state.student_answers.get(q_index)) and str(st.session_state.student_answers.get(q_index)).strip() != ""
                        btn_label = f"✅ {q_index + 1}" if is_answered else f"⚪ {q_index + 1}"
                        
                        if grid_cols[j].button(btn_label, key=f"nav_grid_{q_index}", use_container_width=True):
                            st.session_state.current_q = q_index
                            st.rerun()

    # --- SUBMISSION VIEW ---
    elif st.session_state.exam_state == "submitted":
        st.success("🎉 Exam Submitted Successfully!")
        
        if not st.session_state.get("result_saved", False):
            with st.spinner("Saving results..."):
                auto_score = 0
                detailed_responses = {}
                try:
                    points = int(exam_info.get("Points_Per_Question", 2))
                except Exception:
                    points = 2
                
                for i, q in enumerate(st.session_state.exam_qs):
                    student_ans = str(st.session_state.student_answers.get(i, "")).strip()
                    is_correct = False
                    q_type = str(q.get("Question_Type", "")).lower()
                    correct_ans = str(q.get("Correct_Answer", "")).strip()
                    
                    if "multiple choice" in q_type or "objective" in q_type:
                        db_correct_ans = correct_ans.lower()
                        clean_student_text = student_ans.lower()
                        student_letter = ""
                        
                        if ")" in student_ans:
                            parts = student_ans.split(")", 1)
                            student_letter = parts[0].strip().lower()
                            clean_student_text = parts[1].strip().lower()
                            
                        clean_db_text = db_correct_ans
                        if ")" in db_correct_ans:
                            clean_db_text = db_correct_ans.split(")", 1)[1].strip().lower()
                            
                        if clean_student_text != "":
                            if (clean_student_text == clean_db_text) or (student_letter == db_correct_ans) or (student_ans.lower() == db_correct_ans):
                                auto_score += points
                                is_correct = True
                            
                    detailed_responses[f"Q{i+1}"] = {
                        "Question": q.get("Question_Text", ""),
                        "Type": q.get("Question_Type", ""),
                        "Student_Answer": student_ans,
                        "Is_Correct": is_correct,
                        "Correct_Answer": correct_ans
                    }
                    
                result_data = {
                    "Exam_ID": [exam_info["Exam_ID"]],
                    "Student_Name": [st.session_state.student_info["name"]],
                    "Class": [st.session_state.student_info["class"]],
                    "Contact": [st.session_state.student_info.get("contact", "")],
                    "Auto_Score": [auto_score],
                    "Manual_Score": [0],
                    "Total_Score": [auto_score],
                    "Detailed_Responses": [str(detailed_responses)]
                }
                
                try:
                    df_results = conn.read(worksheet="Student_Results", ttl="0m") 
                    df_new_result = pd.DataFrame(result_data)
                    
                    if df_results.empty:
                        df_updated = df_new_result
                    else:
                        df_updated = pd.concat([df_results, df_new_result], ignore_index=True)
                        
                    conn.update(worksheet="Student_Results", data=df_updated)
                    st.cache_data.clear()
                    st.session_state.result_saved = True
                    st.info("✅ Your answers have been securely recorded. You may safely close this window.")
                    st.balloons()
                except Exception as e:
                    st.error(f"⚠️ Error saving results: {e}") 
        else:
            st.info("✅ Your answers have been securely recorded. You may safely close this window.")

    # --- EXAMINER DASHBOARD VIEW ---
    elif st.session_state.exam_state == "examiner_dashboard":
        st.markdown("<h2 style='text-align: center;'>👨‍🏫 Examiner Dashboard</h2>", unsafe_allow_html=True)
        
        c1, c2, c3 = st.columns([1, 2, 1])
        with c1:
            if st.button("⬅️ Back to Start"):
                st.session_state.exam_state = "landing"
                st.rerun()
                
        st.write("---")
        
        try:
            df_results = conn.read(worksheet="Student_Results", ttl="0m")
            exam_results = df_results[df_results["Exam_ID"] == exam_info["Exam_ID"]]
        except Exception as e:
            st.error("Could not fetch student results from database.")
            exam_results = pd.DataFrame()

        if exam_results.empty:
            st.info("No students have submitted results for this exam yet.")
        else:
            st.subheader("📊 Class Overview")
            display_df = exam_results[["Student_Name", "Class", "Auto_Score", "Manual_Score", "Total_Score"]]
            st.dataframe(display_df, use_container_width=True, hide_index=True)

            st.write("---")
            st.subheader("📝 Granular Question-by-Question Grading")
            
            selected_student = st.selectbox("Select a student to review and grade:", exam_results["Student_Name"].tolist())

            if selected_student:
                student_idx = exam_results[exam_results["Student_Name"] == selected_student].index[0]
                student_data = exam_results.loc[student_idx]
                
                st.markdown(f"**Reviewing Student:** {student_data['Student_Name']} ({student_data['Class']})")
                
                # Persist grading state across widget interactions
                if "grading_student" not in st.session_state or st.session_state.grading_student != selected_student:
                    st.session_state.grading_student = selected_student
                    try:
                        st.session_state.grading_responses = ast.literal_eval(student_data["Detailed_Responses"])
                    except Exception:
                        st.session_state.grading_responses = {}

                responses = st.session_state.grading_responses

                try:
                    points_per_q = int(exam_info.get("Points_Per_Question", 1))
                except Exception:
                    points_per_q = 1

                total_auto_calc = 0
                total_manual_calc = 0

                for q_key, data in responses.items():
                    st.markdown("---")
                    q_type = str(data.get("Type", ""))
                    is_mcq = "multiple" in q_type.lower() or "objective" in q_type.lower()
                    
                    col_q, col_score_box = st.columns([3, 1])
                    
                    with col_q:
                        st.markdown(f"**{q_key}: {data['Question']}**")
                        color = "#16a34a" if (is_mcq and data.get("Is_Correct", False)) else ("#dc2626" if is_mcq else "#0284c7")
                        
                        st.markdown(f"""
                        <div style='background-color: var(--secondary-background-color); padding: 8px; border-radius: 5px; border-left: 4px solid {color}; margin-bottom: 4px;'>
                            <span style='color: var(--text-color);'>Student Answer: <b>{data.get('Student_Answer', '')}</b></span>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        correct_ans = data.get("Correct_Answer", "Check master question list")
                        st.markdown(f"""
                        <div style='padding-left: 10px; margin-bottom: 15px;'>
                            <span style='color: #10b981; font-size: 0.9em; font-weight: 600;'>✅ Correct Answer: {correct_ans}</span>
                        </div>
                        """, unsafe_allow_html=True)
                                            
                    with col_score_box:
                        if is_mcq:
                            awarded = points_per_q if data.get("Is_Correct", False) else 0
                            total_auto_calc += awarded
                            st.markdown(f"<br><b>Score: {awarded}/{points_per_q}</b>", unsafe_allow_html=True)
                        else:
                            existing_q_score = int(data.get("Manual_Score_Given", 0))
                            q_score_input = st.number_input(
                                f"Score ({q_key})", 
                                min_value=0, 
                                max_value=20, 
                                value=existing_q_score, 
                                key=f"manual_{student_idx}_{q_key}"
                            )
                            data["Manual_Score_Given"] = q_score_input
                            total_manual_calc += q_score_input

                sum_theory_manual = sum(int(d.get("Manual_Score_Given", 0)) for d in responses.values() if not ("multiple" in str(d.get("Type", "")).lower() or "objective" in str(d.get("Type", "")).lower()))
                final_calculated_total = total_auto_calc + sum_theory_manual

                st.write("")
                st.markdown(f"### 🧮 Live Score Summary: Auto ({total_auto_calc}) + Manual ({sum_theory_manual}) = **Total: {final_calculated_total}**")

                if st.button("💾 Save All Grades & Update Total Score", type="primary"):
                    df_results.at[student_idx, "Auto_Score"] = total_auto_calc
                    df_results.at[student_idx, "Manual_Score"] = sum_theory_manual
                    df_results.at[student_idx, "Total_Score"] = final_calculated_total
                    df_results.at[student_idx, "Detailed_Responses"] = str(responses)
                    
                    with st.spinner("Saving grades to database..."):
                        conn.update(worksheet="Student_Results", data=df_results)
                        st.cache_data.clear()
                    st.success(f"✅ Successfully updated grades for {selected_student}!")
                    time.sleep(1)
                    st.rerun()

    st.stop()
    
# --- AUTHENTICATION STATE ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.logged_in_school = ""

if not st.session_state.authenticated:
    try:
        df_codes = conn.read(worksheet="AccessCodes", ttl="10m") 
        df_codes['Code'] = df_codes['Code'].astype(str).str.strip()
    except Exception as e:
        df_codes = pd.DataFrame() 

# --- LOGIN SCREEN ---
if not st.session_state.authenticated:
    st.markdown("<style>.block-container { padding-top: 3rem !important; }</style>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h2 style='text-align: center;'>🔒 System Locked</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center;'>Enter your School Access Code</p>", unsafe_allow_html=True)
        
        entered_code = st.text_input("Access Code", type="password").strip()
        
        if st.button("Unlock System", use_container_width=True):
            if entered_code == "1960":
                st.session_state.authenticated = True
                st.session_state.logged_in_school = "Admin"
                st.success("Access Granted! Welcome back, Admin.")
                time.sleep(1)
                st.rerun()
            elif not df_codes.empty and entered_code in df_codes['Code'].values:
                school_row = df_codes[df_codes['Code'] == entered_code].iloc[0]
                school_name = school_row['School Name']
                st.session_state.authenticated = True
                st.session_state.logged_in_school = school_name
                st.success(f"Access Granted! Welcome, {school_name}.")
                time.sleep(1)
                st.rerun()
            else:
                st.error("❌ Invalid Access Code. Please contact the administrator.")
    st.stop() 

# --- LOAD QUESTIONS DATABASE ---
try:
    df_quiz = conn.read(worksheet="Questions", ttl="10m")
    df_quiz = df_quiz.dropna(how="all")
except Exception as e:
    df_quiz = pd.DataFrame(columns=["Class", "Subject", "Topic", "Type", "Question", "Options", "Correct Answer", "Image"])

for col in ["Class", "Subject", "Topic", "Type", "Question", "Options", "Correct Answer", "Image"]:
    if col not in df_quiz.columns:
        df_quiz[col] = None

# --- UNIFIED CLASS & SUBJECT LOADING & AUTO-SYNC ---
DEFAULT_CLASSES = ["JSS 1", "JSS 2", "JSS 3", "SSS 1", "SSS 2", "SSS 3"]
DEFAULT_SUBJECTS = ["Mathematics", "English Language", "Physics", "Chemistry", "Biology", "Basic Science", "Agricultural Science"]

loaded_classes = []
loaded_subjects = []

# 1. Read 'Classes' worksheet tab from Google Sheets
try:
    df_classes = conn.read(worksheet="Classes", ttl="10m")
    df_classes = df_classes.dropna(how="all")
    if not df_classes.empty and "Classes" in df_classes.columns:
        loaded_classes.extend(df_classes["Classes"].dropna().tolist())
except Exception:
    pass

# Harvest dynamic classes from Questions sheet
if not df_quiz.empty and "Class" in df_quiz.columns:
    loaded_classes.extend(df_quiz["Class"].dropna().unique().tolist())

if not loaded_classes:
    loaded_classes = DEFAULT_CLASSES

st.session_state.classes = sorted(list(set([str(c).strip() for c in loaded_classes if str(c).strip()])))

def save_classes():
    new_cls_df = pd.DataFrame({"Classes": st.session_state.classes})
    try:
        conn.update(worksheet="Classes", data=new_cls_df)
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Failed to save classes to Google Sheets: {e}")

# 2. Read 'Subjects' worksheet tab from Google Sheets
try:
    df_subjects = conn.read(worksheet="Subjects", ttl="10m")
    df_subjects = df_subjects.dropna(how="all")
    if not df_subjects.empty and "Subjects" in df_subjects.columns:
        loaded_subjects.extend(df_subjects["Subjects"].dropna().tolist())
except Exception:
    pass

if not df_quiz.empty and "Subject" in df_quiz.columns:
    loaded_subjects.extend(df_quiz["Subject"].dropna().unique().tolist())

if not loaded_subjects:
    loaded_subjects = DEFAULT_SUBJECTS

st.session_state.subjects = sorted(list(set([str(s).strip() for s in loaded_subjects if str(s).strip()])))

def save_subjects():
    new_sub_df = pd.DataFrame({"Subjects": st.session_state.subjects})
    try:
        conn.update(worksheet="Subjects", data=new_sub_df)
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Failed to save subjects to Google Sheets: {e}")

# --- SIDEBAR MANAGEMENT ---
st.sidebar.title("🏆 Quiz Control Panel")

if st.sidebar.button("🔄 Sync Google Sheets", use_container_width=True):
    st.cache_data.clear()
    st.sidebar.success("App synced with Google Sheets!")

menu = ["AI Question Generator", "Manual Input", "View Quiz Bank", "Class & Subjects Setting", "Live Competition Mode", "Exam Mode Setup"]
choice = st.sidebar.selectbox("Go to Module", menu)

# --- MODULE: CLASS & SUBJECTS SETTING ---
if choice == "Class & Subjects Setting":
    st.header("⚙️ Class & Subjects Management Dashboard")
    st.caption("Customize your school's classes and curriculum fields dynamically.")
    
    tab_class, tab_sub = st.tabs(["🏫 Class Settings", "📚 Subject Settings"])
    
    # --- TAB 1: CLASS SETTINGS ---
    with tab_class:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("➕ Add New Class")
            new_cls = st.text_input("Enter Class Name", placeholder="e.g. Grade 10, JSS 1 Gold", key="add_cls_in")
            if st.button("Add Class") and new_cls:
                clean_cls = new_cls.strip()
                if clean_cls not in st.session_state.classes:
                    st.session_state.classes.append(clean_cls)
                    save_classes()
                    st.success(f"Class '{clean_cls}' added successfully!")
                    st.rerun()
                else:
                    st.warning("Class already exists.")
                    
        with col2:
            st.subheader("📝 Edit / Remove Existing Classes")
            if st.session_state.classes:
                cls_to_edit = st.selectbox("Select Class to Modify", sorted(st.session_state.classes), key="sel_cls_mod")
                
                edit_c1, edit_c2 = st.columns(2)
                with edit_c1:
                    rename_cls_val = st.text_input("Rename Class to:", value=cls_to_edit, key="ren_cls_in")
                    if st.button("Rename Class"):
                        new_cls_name = rename_cls_val.strip()
                        if new_cls_name:
                            idx = st.session_state.classes.index(cls_to_edit)
                            st.session_state.classes[idx] = new_cls_name
                            if not df_quiz.empty and "Class" in df_quiz.columns:
                                df_quiz.loc[df_quiz["Class"] == cls_to_edit, "Class"] = new_cls_name
                                try:
                                    conn.update(worksheet="Questions", data=df_quiz)
                                    st.cache_data.clear()
                                except Exception as e:
                                    st.error(f"Failed to update questions database: {e}")
                            save_classes()
                            st.success("Renamed successfully!")
                            st.rerun()
                with edit_c2:
                    st.write("🚨 **Danger Zone:**")
                    st.caption("Admin access required to delete classes.")
                    
                    admin_pin_cls = st.text_input("Enter Admin PIN to unlock:", type="password", key="del_cls_pin")
                    if admin_pin_cls == "1960":
                        if st.button("🗑️ Delete Class", type="primary"):
                            st.session_state.classes.remove(cls_to_edit)
                            save_classes()
                            st.warning(f"Class '{cls_to_edit}' removed from list configuration.")
                            st.rerun()
                    elif admin_pin_cls != "":
                        st.error("Incorrect PIN.")

    # --- TAB 2: SUBJECT SETTINGS ---
    with tab_sub:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("➕ Add New Subject")
            new_sub = st.text_input("Enter Subject Name", placeholder="e.g. Further Mathematics, Economics")
            if st.button("Add Subject") and new_sub:
                clean_sub = new_sub.strip()
                if clean_sub not in st.session_state.subjects:
                    st.session_state.subjects.append(clean_sub)
                    save_subjects()
                    st.success(f"'{clean_sub}' added successfully!")
                    st.rerun()
                else:
                    st.warning("Subject already exists.")
                    
        with col2:
            st.subheader("📝 Edit / Remove Existing Subjects")
            if st.session_state.subjects:
                sub_to_edit = st.selectbox("Select Subject to Modify", sorted(st.session_state.subjects))
                
                edit_col1, edit_col2 = st.columns(2)
                with edit_col1:
                    rename_val = st.text_input("Rename to:", value=sub_to_edit)
                    if st.button("Rename Subject"):
                        new_name = rename_val.strip()
                        if new_name:
                            idx = st.session_state.subjects.index(sub_to_edit)
                            st.session_state.subjects[idx] = new_name
                            if not df_quiz.empty and "Subject" in df_quiz.columns:
                                df_quiz.loc[df_quiz["Subject"] == sub_to_edit, "Subject"] = new_name
                                try:
                                    conn.update(worksheet="Questions", data=df_quiz)
                                    st.cache_data.clear()
                                except Exception as e:
                                    st.error(f"Failed to update questions in Google Sheets: {e}")
                            save_subjects()
                            st.success("Renamed successfully!")
                            st.rerun()
                with edit_col2:
                    st.write("🚨 **Danger Zone:**")
                    st.caption("Admin access required to delete subjects.")
                    
                    admin_pin = st.text_input("Enter Admin PIN to unlock:", type="password", key="del_sub_pin")
                    if admin_pin == "1960": 
                        if st.button("🗑️ Delete Subject", type="primary"):
                            st.session_state.subjects.remove(sub_to_edit)
                            save_subjects()
                            st.warning(f"'{sub_to_edit}' removed from list configuration.")
                            st.rerun()
                    elif admin_pin != "":
                        st.error("Incorrect PIN.")

# --- MODULE 1: AI QUESTION GENERATOR ---
elif choice == "AI Question Generator":
    st.header("🤖 AI-Assisted Question Generator")
    st.caption("Powered by Groq Llama 3.3 (Standard Exam Specification Mode)")
    
    api_key = st.secrets.get("GROQ_API_KEY", None)
    
    if api_key:
        client = Groq(api_key=api_key)
        col1, col2 = st.columns(2)
        with col1:
            selected_class = st.selectbox("Class Designation", st.session_state.classes)
            
            active_subs = list(st.session_state.subjects)
            if not df_quiz.empty and "Subject" in df_quiz.columns:
                active_subs.extend(df_quiz["Subject"].dropna().unique().tolist())
            active_subs = sorted(list(set([str(s).strip() for s in active_subs if str(s).strip()])))
            
            subject = st.selectbox("Subject", active_subs)
            q_type = st.radio("Select Question Category", ["Multiple Choice (Objectives)", "Short Answer / Theory"])
        with col2:
            topic = st.text_input("Topic / Area")
            num_q = st.slider("Number of Questions", 1, 10, 3)
            
        if st.button("✨ Auto-Generate Questions", type="primary"):
            with st.spinner(f"Drafting standard NERDC curriculum questions for {selected_class} - {subject}..."):
                if q_type == "Multiple Choice (Objectives)":
                    prompt = f"""
                    Generate {num_q} standard secondary school level Multiple Choice questions for Class: '{selected_class}' and Subject: '{subject}' on topic: '{topic}'.
                    
                    CURRICULUM & EXAM ALIGNMENT: 
                    1. Align the questions strictly with the Nigerian Educational Research and Development Council (NERDC) curriculum for {selected_class}.
                    2. Maintain a realistic and balanced mix of conceptual, theoretical, and calculation-based questions.
                    
                    STRICT RANDOMIZATION RULE:
                    - Heavily randomize which option contains the correct answer.
                    
                    JSON FORMATTING RULE:
                    - Return a single JSON object with a root key "questions".
                    - Inside "questions", provide a list of objects with keys: 'Question', 'Options', 'Correct Answer'.
                    - 'Options' must be a JSON array containing EXACTLY 4 strings.
                    """
                else:
                    prompt = f"""
                    Generate {num_q} standard secondary school level Short Answer/Theory questions for Class: '{selected_class}' and Subject: '{subject}' on topic: '{topic}'.
                    
                    JSON FORMATTING RULE:
                    - Return a single JSON object with a root key "questions".
                    - Inside "questions", provide a list of objects with keys: 'Question', 'Correct Answer'.
                    """
                
                try:
                    response = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[
                            {"role": "system", "content": "You are a Chief Examiner producing standard exam items. Return valid JSON only."},
                            {"role": "user", "content": prompt}
                        ],
                        response_format={"type": "json_object"},
                        temperature=0.65
                    )
                    
                    generated_text = response.choices[0].message.content
                    generated_data = json.loads(generated_text)
                    
                    new_qs = []
                    for q in generated_data.get("questions", []):
                        raw_opts = q.get("Options", "")
                        if isinstance(raw_opts, list):
                            opts_str = ", ".join([str(x).strip() for x in raw_opts[:5]])
                        else:
                            opts_str = str(raw_opts)
                            
                        new_qs.append({
                            "Class": selected_class, "Subject": subject, "Topic": topic, "Type": q_type,
                            "Question": q.get("Question", ""), "Options": opts_str, "Correct Answer": q.get("Correct Answer", ""),
                            "Image": ""
                        })
                    
                    st.session_state["temp_generated"] = pd.DataFrame(new_qs)
                    st.success("Standard-compliant questions generated successfully!")
                except Exception as e:
                    st.error(f"Groq API Error: {e}")
                    
        if "temp_generated" in st.session_state:
            st.info("💡 **Review and edit the generated questions below.** Click inside any cell to modify before saving.")
            
            edited_df = st.data_editor(
                st.session_state["temp_generated"], 
                use_container_width=True,
                num_rows="dynamic" 
            )
            
            if st.button("💾 Save Edited Questions to Database"):
                df_quiz = pd.concat([df_quiz, edited_df], ignore_index=True)
                try:
                    conn.update(worksheet="Questions", data=df_quiz)
                    st.success("Committed to database!")
                    st.cache_data.clear() 
                    del st.session_state["temp_generated"]
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to save questions to Google Sheets: {e}")
    else:
        st.warning("Please configure your GROQ_API_KEY inside your Streamlit Secrets Panel.")

# --- MODULE 2: MANUAL INPUT ---
elif choice == "Manual Input":
    st.header("📝 Manual Question Entry")
    
    with st.expander("💡 Formatting & Math Cheat Sheet (Click to view)"):
        st.markdown(r"""
        **Basic Formatting:**
        * **Bold**: `**Mass**` ➡️ **Mass**
        * **Italic**: `*Velocity*` ➡️ *Velocity*
        * **Science & Math**: Subscripts `H<sub>2</sub>O` | Superscripts `x<sup>2</sup>` | Math `$\frac{1}{2} mv^2$`
        """)

    q_type = st.radio("Select Category", ["Multiple Choice (Objectives)", "Short Answer / Theory"], horizontal=True)
    
    col_cls, col_sub = st.columns(2)
    with col_cls:
        selected_class = st.selectbox("Designated Class", st.session_state.classes)
    with col_sub:
        active_subs = list(st.session_state.subjects)
        if not df_quiz.empty and "Subject" in df_quiz.columns:
            active_subs.extend(df_quiz["Subject"].dropna().unique().tolist())
        active_subs = sorted(list(set([str(s).strip() for s in active_subs if str(s).strip()])))
        sub = st.selectbox("Subject", active_subs)

    top = st.text_input("Topic")
    q_text = st.text_area("Question Text")
    opts_text = st.text_input("Options (Comma separated)", placeholder="e.g. 20 Hz, 40 Hz, 60 Hz, 80 Hz") if q_type == "Multiple Choice (Objectives)" else ""
    ans_text = st.text_area("Correct Answer (e.g. A) 20 Hz)")
    
    # --- IMAGE UPLOAD SECTION ---
    st.write("---")
    st.subheader("🖼️ Question Image (Optional)")
    col_img_up, col_img_note = st.columns([1.5, 1])
    
    with col_img_up:
        uploaded_img = st.file_uploader("Upload Image (Max: 100 KB)", type=["png", "jpg", "jpeg", "webp"], help="Cap limit: 100 Kilobytes")
    
    with col_img_note:
        st.info("ℹ️ **Notice:** Any uploaded image will automatically appear **above or before** the question text during Live Competitions and Exam Mode sessions.")

    if st.button("💾 Save Question to Database", type="primary"):
        img_str = ""
        if uploaded_img is not None:
            img_b64, err_msg = process_image_upload(uploaded_img)
            if err_msg:
                st.error(err_msg)
                st.stop()
            else:
                img_str = img_b64
                
        new_row = {
            "Class": selected_class, 
            "Subject": sub, 
            "Topic": top, 
            "Type": q_type, 
            "Question": q_text, 
            "Options": opts_text, 
            "Correct Answer": ans_text,
            "Image": img_str
        }
        df_quiz = pd.concat([df_quiz, pd.DataFrame([new_row])], ignore_index=True)
        try:
            conn.update(worksheet="Questions", data=df_quiz)
            st.cache_data.clear() 
            st.success("Question and Image added successfully!")
            time.sleep(1)
            st.rerun()
        except Exception as e:
            st.error(f"Failed to save question to Google Sheets: {e}")

# --- MODULE 3: VIEW QUIZ BANK ---
elif choice == "View Quiz Bank":
    st.header("🗂️ Stored Questions Vault")
    st.caption("View, sort, edit, and reference questions based on Class, Subject, and Category.")
    
    if not df_quiz.empty:
        c_filter1, c_filter2, c_filter3 = st.columns(3)
        with c_filter1: 
            cls_filter = st.multiselect("Filter View by Class", df_quiz["Class"].dropna().unique())
        with c_filter2: 
            sub_filter = st.multiselect("Filter View by Subject", df_quiz["Subject"].dropna().unique())
        with c_filter3: 
            type_filter = st.multiselect("Filter View by Category", df_quiz["Type"].dropna().unique())
        
        filtered = df_quiz.copy()
        if cls_filter: filtered = filtered[filtered["Class"].isin(cls_filter)]
        if sub_filter: filtered = filtered[filtered["Subject"].isin(sub_filter)]
        if type_filter: filtered = filtered[filtered["Type"].isin(type_filter)]
        
        st.subheader("📚 Active Database Records")
        filtered.insert(0, "Delete", False)
        
        # Configure image thumbnail formatting
        column_config = {
            "Image": st.column_config.ImageColumn("Image Box", help="Thumbnail preview of attached image")
        }
        
        edited_df = st.data_editor(
            filtered,
            column_config=column_config,
            hide_index=False,
            use_container_width=True
        )
        
        col_save, col_del = st.columns(2)
        
        with col_save:
            if st.button("💾 Save Changes to Database", type="primary", use_container_width=True):
                updated_subset = edited_df.drop(columns=["Delete"])
                df_quiz.update(updated_subset)
                try:
                    conn.update(worksheet="Questions", data=df_quiz)
                    st.cache_data.clear()
                    st.success("Changes saved successfully to Google Sheets!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to update database: {e}")
        
        indices_to_delete = edited_df[edited_df["Delete"] == True].index
        
        with col_del:
            if len(indices_to_delete) > 0:
                if st.button(f"🗑️ Delete Selected Records ({len(indices_to_delete)})", use_container_width=True):
                    df_quiz = df_quiz.drop(indices_to_delete).reset_index(drop=True)
                    try:
                        conn.update(worksheet="Questions", data=df_quiz)
                        st.cache_data.clear()
                        st.success("Selected records removed successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to delete records in Google Sheets: {e}")
    else:
        st.info("The saved question vault is currently empty.")

# --- MODULE 4: LIVE COMPETITION MODE ---
elif choice == "Live Competition Mode":
    if not df_quiz.empty:
        if len(st.session_state.live_questions) == 0:
            st.header("🎬 Grand Arena - Setup")
            st.subheader("Setup Inter-Subject Competition Round")
            
            chosen_type = st.radio("Select Competition Format for this Session", ["Multiple Choice (Objectives)", "Short Answer / Theory"], horizontal=True)
            
            st.write("---")
            st.subheader("🏫 Class Selector")
            class_options = ["All Classes"] + sorted(list(set(df_quiz["Class"].dropna().unique())))
            selected_quiz_class = st.selectbox("Select Class filter:", class_options)
            
            # Filter pool by Class and Category
            type_filtered_pool = df_quiz[df_quiz["Type"] == chosen_type]
            if selected_quiz_class != "All Classes":
                type_filtered_pool = type_filtered_pool[type_filtered_pool["Class"] == selected_quiz_class]

            st.write("---")
            st.subheader("⏱️ Timer Settings")
            timer_mode = st.radio("Select Timer Format:", ["No Timer", "Per Question", "Entire Session"], horizontal=True)
            
            timer_seconds = 60
            session_total_seconds = 600
            
            if timer_mode == "Per Question":
                timer_seconds = st.number_input("Seconds allocated per question:", min_value=1, max_value=3600, value=60, step=1)
            elif timer_mode == "Entire Session":
                session_total_seconds = st.number_input("Total seconds allocated for the whole round:", min_value=1, max_value=10800, value=600, step=1)
            
            st.write("---")
            
            available_subjects = type_filtered_pool["Subject"].dropna().unique()
            chosen_subjects = st.multiselect("Select Subjects to include in this round", available_subjects)
            
            if chosen_subjects:
                st.write(f"🔧 Set Question Quantities per Subject:")
                config_counts = {}
                
                for s in chosen_subjects:
                    max_avail = len(type_filtered_pool[type_filtered_pool["Subject"] == s])
                    config_counts[s] = st.number_input(f"Number of questions from '{s}' (Max: {max_avail})", min_value=0, max_value=max_avail, value=min(2, max_avail))
                
                if st.button("🚀 Compile and Randomize Game Show Pool", type="primary"):
                    round_pool = []
                    for s, count in config_counts.items():
                        if count > 0:
                            sub_pool = type_filtered_pool[type_filtered_pool["Subject"] == s].sample(n=int(count)).to_dict(orient="records")
                            round_pool.extend(sub_pool)
                    
                    if round_pool:
                        random.shuffle(round_pool)
                        st.session_state.live_questions = round_pool
                        st.session_state.current_q_index = 0
                        st.session_state.show_answer = False
                        st.session_state.timer_mode = timer_mode
                        
                        if timer_mode == "Per Question":
                            st.session_state.timer_seconds = timer_seconds
                        elif timer_mode == "Entire Session":
                            st.session_state.session_total_seconds = session_total_seconds
                            
                        st.session_state.quiz_state = "countdown"
                        st.rerun()
                    else:
                        st.error("Please allocate at least 1 question to start.")
            elif len(available_subjects) == 0:
                st.warning("No questions found matching your selected Class and Category combination.")
                
        else:
            # --- COUNTDOWN INTERSTITIAL SCREEN ---
            if st.session_state.quiz_state == "countdown":
                placeholder = st.empty()
                for i in [3, 2, 1]:
                    placeholder.markdown(f"""
                        <div style='display: flex; flex-direction: column; align-items: center; justify-content: center; height: 60vh;'>
                            <h1 style='font-size: 4rem; color: #e2e8f0; margin-bottom: 0px;'>GET READY</h1>
                            <h1 style='font-size: 8rem; color: #ff4b4b; margin-top: 10px;'>{i}</h1>
                        </div>
                    """, unsafe_allow_html=True)
                    time.sleep(1)
                
                placeholder.markdown("""
                    <div style='display: flex; flex-direction: column; align-items: center; justify-content: center; height: 60vh;'>
                        <h1 style='font-size: 10rem; color: #38bdf8; margin: 0;'>GO! 🚀</h1>
                    </div>
                """, unsafe_allow_html=True)
                time.sleep(1)
                
                st.session_state.quiz_state = "live"
                if st.session_state.get("timer_mode") == "Entire Session":
                    st.session_state.session_end_time_ms = int(time.time() * 1000) + (st.session_state.session_total_seconds * 1000)
                st.rerun()

            # --- MAIN LIVE VIEW ---
            elif st.session_state.quiz_state == "live":
                q_list = st.session_state.live_questions
                idx = st.session_state.current_q_index
                current_q = q_list[idx]
                
                top_c1, top_c2 = st.columns([4, 1])
                with top_c1:
                    q_labels = [f"Question {i+1} {'⭐ (Current)' if i == idx else ''}" for i in range(len(q_list))]
                    chosen_q_label = st.selectbox("Jump to:", q_labels, index=idx, label_visibility="collapsed")
                    new_idx = q_labels.index(chosen_q_label)
                    
                    if new_idx != idx:
                        st.session_state.current_q_index = new_idx
                        st.session_state.show_answer = False
                        st.rerun()
                with top_c2:
                    if st.button("🔄 Restart Round", use_container_width=True):
                        st.session_state.current_q_index = 0
                        st.session_state.show_answer = False
                        st.session_state.quiz_state = "countdown"
                        st.rerun()
                
                st.write("")
                
                current_mode = st.session_state.get("timer_mode", "No Timer")
                if current_mode == "Per Question":
                    timer_html = f"""
                    <div style="font-size: 22px; font-family: monospace; font-weight: bold; color: #ff4b4b; text-align: center; border: 2px solid #ff4b4b; border-radius: 8px; padding: 6px; margin-bottom: 15px; background-color: #fff1f0; line-height: 1;">
                        <span id="timer_display_{idx}"></span>
                    </div>
                    <script>
                    var timeLeft = {st.session_state.get('timer_seconds', 60)};
                    var elem = document.getElementById('timer_display_{idx}');
                    var timerId = setInterval(countdown, 1000);
                    function countdown() {{
                        if (timeLeft <= 0) {{ clearInterval(timerId); elem.innerHTML = "🚨 TIME UP!"; }}
                        else {{ elem.innerHTML = "⏱️ " + timeLeft + "s"; timeLeft--; }}
                    }}
                    countdown();
                    </script>
                    """
                    components.html(timer_html, height=45)
                    
                elif current_mode == "Entire Session":
                    end_time_ms = st.session_state.get("session_end_time_ms", 0)
                    timer_html = f"""
                    <div style="font-size: 22px; font-family: monospace; font-weight: bold; color: #ff4b4b; text-align: center; border: 2px solid #ff4b4b; border-radius: 8px; padding: 6px; margin-bottom: 15px; background-color: #fff1f0; line-height: 1;">
                        <span id="global_timer_display"></span>
                    </div>
                    <script>
                    var endTime = {end_time_ms};
                    var elem = document.getElementById('global_timer_display');
                    function updateTimer() {{
                        var timeLeft = Math.floor((endTime - Date.now()) / 1000);
                        if (timeLeft <= 0) {{ elem.innerHTML = "🚨 TIME UP!"; }} 
                        else {{
                            var m = Math.floor(timeLeft / 60); var s = timeLeft % 60;
                            elem.innerHTML = "⏱️ " + m + "m " + (s < 10 ? "0" : "") + s + "s";
                        }}
                    }}
                    updateTimer(); setInterval(updateTimer, 1000);
                    </script>
                    """
                    components.html(timer_html, height=45)
                
                # QUESTION CONTAINER
                st.markdown(f"""
                    <div style='background-color: #1e293b; padding: 12px 15px; border-radius: 8px; margin-bottom: 15px;'>
                        <span style='color: #38bdf8; font-weight: bold; font-size: 1.1rem;'>📍 Q{idx + 1}/{len(q_list)}:</span> 
                        <span style='color: #e2e8f0; font-size: 1rem;'>Class: {current_q.get('Class', 'N/A')} | {current_q['Subject']} | {current_q['Topic']}</span>
                    </div>
                """, unsafe_allow_html=True)
                
                # Display image ABOVE question text
                if pd.notna(current_q.get("Image")) and str(current_q.get("Image")).strip() and str(current_q.get("Image")) != "nan":
                    st.image(current_q["Image"], caption=f"Q{idx + 1} Image", width=500)

                st.markdown(f"<div style='font-size: 1.25rem; font-weight: 500; line-height: 1.5; margin-bottom: 20px;'>{str(current_q['Question'])}</div>", unsafe_allow_html=True)
                
                if current_q['Type'] == "Multiple Choice (Objectives)" and pd.notna(current_q['Options']) and str(current_q['Options']).strip() != "":
                    options_split = str(current_q['Options']).split(",")
                    prefixes = ["A)", "B)", "C)", "D)", "E)"]
                    
                    for index, option in enumerate(options_split):
                        if index >= len(prefixes): break
                        clean_opt = option.strip()
                        if any(clean_opt.startswith(p) for p in prefixes):
                            st.markdown(f"**🔹 {clean_opt}**")
                        else:
                            pref = prefixes[index]
                            st.markdown(f"**🔹 {pref} {clean_opt}**")
                
                st.write("---")
                
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    if st.button("👁️ Show Ans", use_container_width=True):
                        st.session_state.show_answer = not st.session_state.show_answer
                with c2:
                    if st.button("⬅️ Prev", use_container_width=True) and idx > 0:
                        st.session_state.current_q_index -= 1
                        st.session_state.show_answer = False
                        st.rerun()
                with c3:
                    if st.button("Next ➡️", use_container_width=True) and idx < len(q_list) - 1:
                        st.session_state.current_q_index += 1
                        st.session_state.show_answer = False
                        st.rerun()
                with c4:
                    if st.button("❌ End Game", use_container_width=True):
                        st.session_state.live_questions = []
                        st.session_state.current_q_index = 0
                        st.session_state.show_answer = False
                        st.session_state.quiz_state = "setup"
                        st.rerun()
                
                if st.session_state.show_answer:
                    st.success(f"**Ans:** {current_q['Correct Answer']}")
    else:
        st.info("The database is currently empty.")

# --- MODULE 5: EXAM MODE SETUP ---
elif choice == "Exam Mode Setup":
    st.header("⚙️ Exam Mode Setup")
    
    setup_tab, manage_tab = st.tabs(["📝 Create New Exam", "🗑️ Manage/Delete Exams"])

    with setup_tab:
        with st.form("exam_setup_form", clear_on_submit=False):
            st.subheader("Exam Details")
            col1, col2 = st.columns(2)
            with col1:
                exam_title = st.text_input("Exam Title", placeholder="e.g., Senior Sec. Physics Mock Exam")
                school_name = st.text_input("School Name", value=st.session_state.get("logged_in_school", ""))
                examiner_name = st.text_input("Examiner Name")
            with col2:
                exam_pin = st.text_input("Examiner PIN (To view scores later)", type="password")
                timer_seconds = st.number_input("Timer (in seconds)", min_value=60, value=3600, step=60)
                points_per_q = st.number_input("Points Per Question", min_value=1, value=1)

            instructions = st.text_area("Instructions for Students", placeholder="e.g., Attempt all questions.")

            st.subheader("Availability Schedule")
            col3, col4 = st.columns(2)
            with col3:
                start_date = st.date_input("Start Date")
                start_time = st.time_input("Start Time")
            with col4:
                end_date = st.date_input("End Date")
                end_time = st.time_input("End Time")

            st.subheader("Question Selection")
            col_cls_ex, col_sub_ex = st.columns(2)
            with col_cls_ex:
                selected_exam_classes = st.multiselect("Select Class Filter(s)", ["All Classes"] + st.session_state.classes, default=["All Classes"])
            with col_sub_ex:
                subjects = st.multiselect("Select Subjects", st.session_state.subjects)
            
            col_q1, col_q2 = st.columns(2)
            with col_q1:
                num_mcq = st.number_input("Multiple Choice Questions (per subject)", min_value=0, value=20)
            with col_q2:
                num_theory = st.number_input("Short Answer / Theory Questions (per subject)", min_value=0, value=5)
                allow_calc = st.checkbox("Allow Basic Scientific Calculator for this Exam")

            submit_exam = st.form_submit_button("Generate Exam Link")

            if submit_exam:
                if not exam_title or not exam_pin or not subjects:
                    st.error("Please fill in Exam Title, Examiner PIN, and select at least one Subject.")
                elif num_mcq == 0 and num_theory == 0:
                    st.error("Please allocate at least 1 question.")
                else:
                    start_datetime = f"{start_date} {start_time}"
                    end_datetime = f"{end_date} {end_time}"
                    exam_id = f"EXAM-{str(uuid.uuid4())[:6].upper()}"
                    
                    # Filter questions based on selected Class & Subjects
                    selected_qs = df_quiz[df_quiz["Subject"].isin(subjects)]
                    if "All Classes" not in selected_exam_classes:
                        selected_qs = selected_qs[selected_qs["Class"].isin(selected_exam_classes)]
                    
                    if selected_qs.empty:
                        st.error("No matching questions found in the database for your Class/Subject criteria.")
                    else:
                        with st.spinner("Compiling exam and saving to database..."):
                            final_exam_qs = []
                            for subj in subjects:
                                if num_mcq > 0:
                                    pool_mcq = selected_qs[(selected_qs["Subject"] == subj) & (selected_qs["Type"] == "Multiple Choice (Objectives)")]
                                    if not pool_mcq.empty:
                                        sampled_mcq = pool_mcq.sample(n=min(num_mcq, len(pool_mcq)))
                                        for idx, row in sampled_mcq.iterrows():
                                            final_exam_qs.append({
                                                "Exam_ID": exam_id,
                                                "Question_Number": 0, 
                                                "Question_Type": row["Type"],
                                                "Subject": row["Subject"],
                                                "Question_Text": row["Question"],
                                                "Options": row["Options"],
                                                "Correct_Answer": row["Correct Answer"],
                                                "Image": row.get("Image", "")
                                            })
                                            
                                if num_theory > 0:
                                    pool_theory = selected_qs[(selected_qs["Subject"] == subj) & (selected_qs["Type"] == "Short Answer / Theory")]
                                    if not pool_theory.empty:
                                        sampled_theory = pool_theory.sample(n=min(num_theory, len(pool_theory)))
                                        for idx, row in sampled_theory.iterrows():
                                            final_exam_qs.append({
                                                "Exam_ID": exam_id,
                                                "Question_Number": 0, 
                                                "Question_Type": row["Type"],
                                                "Subject": row["Subject"],
                                                "Question_Text": row["Question"],
                                                "Options": row["Options"],
                                                "Correct_Answer": row["Correct Answer"],
                                                "Image": row.get("Image", "")
                                            })
                            
                            for i, q in enumerate(final_exam_qs):
                                q["Question_Number"] = i + 1
                                
                            exam_record = {
                                "Exam_ID": [exam_id],
                                "Exam_Title": [exam_title],
                                "School_Name": [school_name],
                                "Examiner_Name": [examiner_name],
                                "Instructions": [instructions],
                                "Exam_PIN": [exam_pin],
                                "Start_DateTime": [start_datetime],
                                "End_DateTime": [end_datetime],
                                "Timer_Seconds": [timer_seconds],
                                "Points_Per_Question": [points_per_q],
                                "Status": ["Active"],
                                "Allow_Calculator": [allow_calc]
                            }
                            
                            try:
                                df_new_exam = pd.DataFrame(exam_record)
                                df_new_qs = pd.DataFrame(final_exam_qs)
                                
                                df_active = conn.read(worksheet="Active_Exams")
                                df_active = pd.concat([df_active, df_new_exam], ignore_index=True)
                                conn.update(worksheet="Active_Exams", data=df_active)
                                
                                df_exam_questions = conn.read(worksheet="Exam_Questions")
                                df_exam_questions = pd.concat([df_exam_questions, df_new_qs], ignore_index=True)
                                conn.update(worksheet="Exam_Questions", data=df_exam_questions)
                                st.cache_data.clear()
                                
                                st.success("✅ Exam Successfully Created & Saved to Database!")
                                base_url = "https://quiz-master-by-joe-v8hv3x7blqf35lgjpge6br.streamlit.app"
                                exam_url = f"{base_url}/?exam={exam_id}"
                                st.info(f"**Share this link with students:**\n{exam_url}")
                            except Exception as e:
                                st.error(f"Failed to connect to Google Sheets: {e}")

    with manage_tab:
        st.subheader("🗑️ Delete Active Exams")
        st.warning("Deleting an exam will permanently erase it from Active_Exams, Exam_Questions, and Student_Results.")
        
        try:
            df_active_view = conn.read(worksheet="Active_Exams", ttl="1m")
            active_exams_list = ["Select an exam..."] + df_active_view["Exam_ID"].dropna().tolist()
        except Exception:
            active_exams_list = ["Select an exam..."]
            
        exam_to_delete = st.selectbox("Select Exam to Delete", active_exams_list) 
        admin_pin_input = st.text_input("Enter Master Admin PIN to confirm", type="password", key="delete_exam_pin")
        
        if st.button("🗑️ Delete Exam Record", type="primary"):
            if admin_pin_input == "1960": 
                if exam_to_delete != "Select an exam...":
                    try:
                        with st.spinner("Wiping exam records from all databases..."):
                            df_active = conn.read(worksheet="Active_Exams")
                            df_active = df_active[df_active["Exam_ID"] != exam_to_delete]
                            conn.update(worksheet="Active_Exams", data=df_active)
                            
                            df_eq = conn.read(worksheet="Exam_Questions")
                            if not df_eq.empty and "Exam_ID" in df_eq.columns:
                                df_eq = df_eq[df_eq["Exam_ID"] != exam_to_delete]
                                conn.update(worksheet="Exam_Questions", data=df_eq)
                                
                            try:
                                df_sr = conn.read(worksheet="Student_Results")
                                if not df_sr.empty and "Exam_ID" in df_sr.columns:
                                    df_sr = df_sr[df_sr["Exam_ID"] != exam_to_delete]
                                    conn.update(worksheet="Student_Results", data=df_sr)
                            except Exception:
                                pass
                                
                            st.cache_data.clear()
                            st.success(f"Successfully deleted {exam_to_delete} and all associated records.")
                            time.sleep(2)
                            st.rerun()
                    except Exception as e:
                        st.error(f"Error during deletion: {e}")
                else:
                    st.error("Please select a valid exam to delete.")
            elif admin_pin_input != "":
                st.error("❌ Incorrect Admin PIN. Deletion unauthorized.")
