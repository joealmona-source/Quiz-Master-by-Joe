import streamlit as st
import pandas as pd
import os
import json
import random
import time
import uuid
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

# --- EXAM MODE URL INTERCEPTOR (STAGE 3) ---
if "exam" in st.query_params:
    exam_id_param = st.query_params["exam"]
    
    try:
        df_active = conn.read(worksheet="Active_Exams", ttl="0m")
        exam_data = df_active[df_active["Exam_ID"] == exam_id_param]
    except Exception as e:
        st.error("Could not connect to the database.")
        st.stop()

    if exam_data.empty:
        st.error("❌ This exam link is invalid or the exam has been deleted.")
        st.stop()
        
    exam_info = exam_data.iloc[0]
    
    st.markdown(f"<h1 style='text-align: center; font-size: 3.5rem; font-weight: 900; color: #0f172a; margin-bottom: 0;'>{exam_info['School_Name']}</h1>", unsafe_allow_html=True)
    st.markdown(f"<h2 style='text-align: center; font-size: 1.8rem; font-weight: 500; color: #0284c7; margin-top: 0;'>{exam_info['Exam_Title']}</h2>", unsafe_allow_html=True)
    
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
                
                # --- NEW SECURITY LOCK: Check for Duplicate Entries ---
                try:
                    df_results_check = conn.read(worksheet="Student_Results", ttl="0m")
                    exam_history = df_results_check[df_results_check["Exam_ID"] == exam_info["Exam_ID"]]
                    # Create a lowercase list of all existing names to prevent case-sensitive bypasses
                    taken_names = [str(name).strip().lower() for name in exam_history["Student_Name"].dropna().tolist()]
                except Exception:
                    taken_names = []
                # --------------------------------------------------------

                current_time = datetime.now()
                try:
                    start_dt = datetime.strptime(str(exam_info["Start_DateTime"]), "%Y-%m-%d %H:%M:%S")
                    end_dt = datetime.strptime(str(exam_info["End_DateTime"]), "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    start_dt = pd.to_datetime(exam_info["Start_DateTime"])
                    end_dt = pd.to_datetime(exam_info["End_DateTime"])

                # --- VALIDATION CASCADE ---
                if not student_name or not student_class:
                    st.error("⚠️ Please enter your name and class to begin.")
                elif student_name.strip().lower() in taken_names:
                    st.error(f"🛑 Access Denied: A submission for '{student_name.strip()}' has already been recorded. You cannot retake this exam.")
                elif current_time < start_dt:
                    st.error(f"⏳ **Too Early:** This exam opens on {start_dt.strftime('%B %d, %Y at %I:%M %p')}.")
                elif current_time > end_dt:
                    st.error("🛑 **Exam Closed:** The submission window for this exam has expired.")
                else:
                    st.session_state.student_info = {"name": student_name, "class": student_class, "contact": student_contact}
                    st.session_state.exam_state = "in_progress"
                    st.session_state.exam_start_time = time.time()
                    st.rerun()

                    
        with col2:
            st.subheader("👨‍🏫 Examiner Portal")
            entered_pin = st.text_input("Enter Exam PIN", type="password")
            if st.button("📊 View Scores", use_container_width=True):
                # FIX: Clean decimals and whitespace from Google Sheets numbers for accurate PIN matching
                db_pin = str(exam_info["Exam_PIN"]).split(".")[0].strip()
                if entered_pin.strip() == db_pin:
                    st.session_state.exam_state = "examiner_dashboard"
                    st.rerun()
                else:
                    st.error("Incorrect PIN. Access Denied.")

    # --- IN PROGRESS VIEW (STAGE 4) ---
    elif st.session_state.exam_state == "in_progress":
        
        # AGGRESSIVE CSS: Makes radio buttons, text, and options significantly larger and easier to read
        st.markdown("""
        <style>
        .stRadio label p { font-size: 22px !important; margin-left: 10px; line-height: 1.5; color: #0f172a; }
        .stRadio div[role="radio"] { transform: scale(1.6); margin-top: 2px; }
        .stRadio > div { gap: 1.5rem !important; }
        </style>
        """, unsafe_allow_html=True)
        
        # 1. Initialize Exam State Questions
        if "exam_qs" not in st.session_state:
            df_eq = conn.read(worksheet="Exam_Questions", ttl="0m")
            q_list = df_eq[df_eq["Exam_ID"] == exam_info["Exam_ID"]].to_dict('records')
            st.session_state.exam_qs = q_list
            if "student_answers" not in st.session_state:
                st.session_state.student_answers = {} 
            st.session_state.current_q = 0
            
        qs = st.session_state.exam_qs
        idx = st.session_state.current_q
        
        if not qs:
            st.error("⚠️ No questions were found loaded for this exam ID. Please check your database.")
            if st.button("⬅️ Back to Landing"):
                st.session_state.exam_state = "landing"
                st.rerun()
            st.stop()
            
        current_q_data = qs[idx]
        
        # 2. Timer Calculation
        elapsed_seconds = time.time() - st.session_state.exam_start_time
        try:
            allowed_secs = int(exam_info["Timer_Seconds"])
        except Exception:
            allowed_secs = 1800 # Default fallback 30 mins
        time_left = max(0, allowed_secs - elapsed_seconds)
        
        # 3. Top Header Bar (Timer & Submit)
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

        # 4. Safe Calculator Expander
        calc_allowed = str(exam_info.get("Allow_Calculator", "False")).strip().upper()
        if calc_allowed in ['TRUE', '1', 'YES', 'ON']:
            with st.expander("🧮 Open Scientific Calculator", expanded=False):
                st.components.v1.html("""<iframe width="100%" height="350px" style="border: none;" src="https://www.desmos.com/scientific"></iframe>""", height=360)

        st.markdown("---")
        
        # 5. Question Box Banner
        st.markdown(f"""
        <div style="background-color: #f8fafc; padding: 15px; border-radius: 8px; border-left: 5px solid #0284c7; margin-bottom: 20px;">
            <span style="color: #64748b; font-weight: 600; font-size: 1.1rem;">Question {idx + 1} of {len(qs)}</span>
            <h3 style="color: #0f172a; margin-top: 10px;">{current_q_data.get('Question_Text', '')}</h3>
        </div>
        """, unsafe_allow_html=True)
        
        # 6. Answer Input (Objectives vs Theory)
        saved_ans = st.session_state.student_answers.get(idx, None)
        q_type = str(current_q_data.get('Question_Type', ''))
        
        if "Multiple Choice" in q_type or "Objective" in q_type:
            raw_options = str(current_q_data.get('Options', ''))
            options = [opt.strip() for opt in raw_options.split(",") if opt.strip()]
            
            if options:
                selection = st.radio(
                    "Select your answer:", 
                    options, 
                    index=options.index(saved_ans) if saved_ans in options else None, 
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
        
        # 7. Previous / Next Buttons
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
        
        # 8. Jump to Question Grid Drawer
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

    # --- SUBMISSION AND AUTOGRADING VIEW (STAGE 5) ---
    elif st.session_state.exam_state == "submitted":
        st.success("🎉 Exam Submitted Successfully!")
        
        with st.spinner("Calculating your score and saving results..."):
            auto_score = 0
            detailed_responses = {}
            
            # Safely handle the points variable in case it's blank in the DB
            try:
                points = int(exam_info.get("Points_Per_Question", 0))
            except ValueError:
                points = 0
            
            # Grade Questions
            for i, q in enumerate(st.session_state.exam_qs):
                student_ans = str(st.session_state.student_answers.get(i, "")).strip()
                correct_ans = str(q.get("Correct_Answer", "")).strip()
                q_type = str(q.get("Question_Type", "")).lower()
                is_correct = False
                
                # Robust type checking (looks for the word "multiple" or "objective")
                if "multiple" in q_type or "objective" in q_type:
                    # Strict but clean string comparison
                    if student_ans.lower() == correct_ans.lower() and student_ans != "":
                        auto_score += points
                        is_correct = True
                        
                detailed_responses[f"Q{i+1}"] = {
                    "Question": str(q.get("Question_Text", "")),
                    "Type": str(q.get("Question_Type", "")),
                    "Student_Answer": student_ans,
                    "Is_Correct": is_correct
                }
                
            result_data = {
                "Exam_ID": [exam_info["Exam_ID"]],
                "Student_Name": [st.session_state.student_info["name"].strip()],
                "Class": [st.session_state.student_info["class"].strip()],
                "Contact": [st.session_state.student_info.get("contact", "").strip()],
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
                st.info("✅ Your answers have been securely recorded. You may safely close this window.")
                st.balloons()
            except Exception as e:
                st.error(f"⚠️ Error saving results: {e}")
        
    # --- EXAMINER DASHBOARD VIEW (STAGE 5) ---
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
            st.error("Could not fetch student results from the database.")
            exam_results = pd.DataFrame()

        if exam_results.empty:
            st.info("No students have submitted results for this exam yet.")
        else:
            st.subheader("📊 Class Overview")
            # Display a clean summary table of everyone's scores
            display_df = exam_results[["Student_Name", "Class", "Auto_Score", "Manual_Score", "Total_Score"]]
            st.dataframe(display_df, use_container_width=True, hide_index=True)

            st.write("---")
            st.subheader("📝 Grade Theory & View Responses")
            
            selected_student = st.selectbox("Select a student to review:", exam_results["Student_Name"].tolist())

            if selected_student:
                # Find the exact row index in the master dataframe
                student_idx = exam_results[exam_results["Student_Name"] == selected_student].index[0]
                student_data = exam_results.loc[student_idx]
                
                st.markdown(f"**Reviewing:** {student_data['Student_Name']} ({student_data['Class']})")
                
                # Grading Box
                new_manual_score = st.number_input(
                    "Assign Manual Score (For Theory Questions)", 
                    value=int(student_data["Manual_Score"]),
                    step=1
                )
                
                if st.button("💾 Save Score Update", type="primary"):
                    # Update the specific row
                    df_results.at[student_idx, "Manual_Score"] = new_manual_score
                    df_results.at[student_idx, "Total_Score"] = int(student_data["Auto_Score"]) + new_manual_score
                    
                    with st.spinner("Saving to database..."):
                        conn.update(worksheet="Student_Results", data=df_results)
                    st.success(f"✅ Scores updated for {selected_student}!")
                    time.sleep(1)
                    st.rerun()
                
                st.write("")
                st.markdown("### 📄 Detailed Answer Sheet")
                
                import ast
                try:
                    # Safely convert the stringified dictionary back into a usable Python dictionary
                    responses = ast.literal_eval(student_data["Detailed_Responses"])
                    for q_num, data in responses.items():
                        st.markdown(f"**{q_num}: {data['Question']}**")
                        
                        # Color code: Green for correct MCQ, Red for wrong MCQ, Blue for Theory
                        if data["Type"] == "Multiple Choice (Objectives)":
                            color = "#16a34a" if data["Is_Correct"] else "#dc2626"
                        else:
                            color = "#0284c7" # Blue for theory requiring manual grading
                            
                        st.markdown(f"<div style='background-color: #f8fafc; padding: 10px; border-radius: 5px; border-left: 4px solid {color};'>Student Answer: <b>{data['Student_Answer']}</b></div>", unsafe_allow_html=True)
                        st.write(" ")
                except Exception as e:
                    st.error("Could not parse detailed responses.")
                    st.write(student_data["Detailed_Responses"])
st.stop()

# --- AUTHENTICATION STATE ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.logged_in_school = ""

# ONLY fetch access codes if the user is NOT logged in yet
if not st.session_state.authenticated:
    try:
        # 👈 Changed ttl to 10m so it doesn't spam Google!
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
            
            # 1. THE MASTER ADMIN BYPASS
            if entered_code == "1960":  # Change this to your secret master password
                st.session_state.authenticated = True
                st.session_state.logged_in_school = "Admin"
                st.success("Access Granted! Welcome back, Admin.")
                time.sleep(1)
                st.rerun()
                
            # 2. THE SCHOOL ACCESS CODE CHECK
            elif not df_codes.empty and entered_code in df_codes['Code'].values:
                # Find the row that matches the entered code
                school_row = df_codes[df_codes['Code'] == entered_code].iloc[0]
                school_name = school_row['School Name']
                
                # Update session state to log them in
                st.session_state.authenticated = True
                st.session_state.logged_in_school = school_name
                
                st.success(f"Access Granted! Welcome, {school_name}.")
                time.sleep(1)
                st.rerun()
                
            # 3. FAILED LOGIN
            else:
                st.error("❌ Invalid Access Code. Please contact the administrator.")
    
    # STOP EXECUTION HERE if not logged in
    st.stop() 

# --- LOAD QUESTIONS DATABASE ---
try:
    df_quiz = conn.read(worksheet="Questions", ttl="10m")
    df_quiz = df_quiz.dropna(how="all")
except Exception as e:
    df_quiz = pd.DataFrame(columns=["Subject", "Topic", "Type", "Question", "Options", "Correct Answer"])

for col in ["Subject", "Topic", "Type", "Question", "Options", "Correct Answer"]:
    if col not in df_quiz.columns:
        df_quiz[col] = None

# --- UNIFIED SUBJECT LOADING & AUTO-SYNC ---
DEFAULT_SUBJECTS = ["Mathematics", "English Language", "Physics", "Chemistry", "Biology", "Basic Science", "Agricultural Science"]
loaded_subjects = []

# 1. Read from the 'Subjects' worksheet tab in Google Sheets
try:
    df_subjects = conn.read(worksheet="Subjects", ttl="10m")
    df_subjects = df_subjects.dropna(how="all")
    if not df_subjects.empty and "Subjects" in df_subjects.columns:
        loaded_subjects.extend(df_subjects["Subjects"].dropna().tolist())
except Exception as e:
    pass

# 2. Harvest any subjects dynamically existing inside the 'Questions' database
if not df_quiz.empty and "Subject" in df_quiz.columns:
    loaded_subjects.extend(df_quiz["Subject"].dropna().unique().tolist())

# 3. Fallback to defaults if both sheets are empty
if not loaded_subjects:
    loaded_subjects = DEFAULT_SUBJECTS

# 4. Clean, deduplicate, sort alphabetically, and force into session state
st.session_state.subjects = sorted(list(set([str(s).strip() for s in loaded_subjects if str(s).strip()])))

def save_subjects():
    new_sub_df = pd.DataFrame({"Subjects": st.session_state.subjects})
    try:
        conn.update(worksheet="Subjects", data=new_sub_df)
        st.cache_data.clear()  # 👈 Forces Streamlit to load fresh subjects on refresh!
    except Exception as e:
        st.error(f"Failed to save subjects to Google Sheets: {e}")

# --- SIDEBAR MANAGEMENT ---
st.sidebar.title("🏆 Quiz Control Panel")

if st.sidebar.button("🔄 Sync Google Sheets", use_container_width=True):
    st.cache_data.clear()
    st.sidebar.success("App synced with Google Sheets!")

menu = ["AI Question Generator", "Manual Input", "View Quiz Bank", "Subject Settings", "Live Competition Mode", "Exam Mode Setup"]
choice = st.sidebar.selectbox("Go to Module", menu)

# --- MODULE: SUBJECT SETTINGS ---
if choice == "Subject Settings":
    st.header("⚙️ Subject Management Dashboard")
    st.caption("Customize your school's curriculum fields dynamically.")
    
    # Auto-detect and sync any subjects that exist in the Questions database
    if not df_quiz.empty and "Subject" in df_quiz.columns:
        quiz_subjects = df_quiz["Subject"].dropna().unique().tolist()
        for s in quiz_subjects:
            clean_s = str(s).strip()
            if clean_s and clean_s not in st.session_state.subjects:
                st.session_state.subjects.append(clean_s)
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("➕ Add New Subject")
        new_sub = st.text_input("Enter Subject Name", placeholder="e.g., Further Mathematics, Economics")
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
                            except Exception as e:
                                st.error(f"Failed to update questions in Google Sheets: {e}")
                        save_subjects()
                        st.success("Renamed successfully!")
                        st.rerun()
            with edit_col2:
                st.write("🚨 **Danger Zone:**")
                st.caption("Admin access required to delete.")
                
                # The password input box for the Admin PIN
                admin_pin = st.text_input("Enter Admin PIN to unlock:", type="password", key="del_sub_pin")
                
                # Replace "1960" with whatever secret PIN you want to use!
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
    
    if "GROQ_API_KEY" in st.secrets:
        api_key = st.secrets["GROQ_API_KEY"]
    else:
        api_key = None
    
    if api_key:
        client = Groq(api_key=api_key)
        col1, col2 = st.columns(2)
        with col1:
            # --- DYNAMIC SUBJECT SYNC ---
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
            with st.spinner(f"Drafting standard NERDC curriculum questions for {subject}..."):
                
                if q_type == "Multiple Choice (Objectives)":
                    prompt = f"""
                    Generate {num_q} standard secondary school level Multiple Choice questions for {subject} on topic: '{topic}'.
                    
                    CURRICULUM & EXAM ALIGNMENT: 
                    1. Align the questions strictly with the Nigerian Educational Research and Development Council (NERDC) curriculum.
                    2. For Senior Secondary level subjects, model the style, depth, and structural tone exactly after past WAEC, NECO, and JAMB UTME national examinations.
                    3. For Junior Secondary level subjects, model the style exactly after Basic Education Certificate Examination (B.E.C.E) standards.
                    4. Maintain a realistic and balanced mix of conceptual, theoretical, and calculation-based questions as found in actual national papers. Do not tilt heavily into complex calculations unless explicitly required by the topic, and never generate dubious, unrealistic, or outrageous scenarios.
                    
                    STRICT RANDOMIZATION RULE:
                    - You MUST heavily randomize which option contains the correct answer. It is unacceptable for 'A' to be the correct answer for multiple questions in a row. Shuffle the correct answer evenly across the 1st, 2nd, 3rd, and 4th positions.
                    
                    JSON FORMATTING RULE:
                    - Return a single JSON object with a root key "questions".
                    - Inside "questions", provide a list of objects with exactly these keys: 'Question', 'Options', 'Correct Answer'.
                    - 'Options' must be a JSON array containing EXACTLY 4 strings. Do NOT write 'A)', 'B)', etc. inside the array elements (e.g. ["10 m/s", "20 m/s", "30 m/s", "40 m/s"]).
                    - 'Correct Answer' must explicitly map to the final correct option WITH a letter indicator corresponding to its position in your generated array (e.g., 'C) 30 m/s').
                    """
                else:
                    prompt = f"""
                    Generate {num_q} standard secondary school level Short Answer/Theory questions for {subject} on topic: '{topic}'.
                    
                    CURRICULUM & EXAM ALIGNMENT:
                    1. Align strictly with the NERDC curriculum.
                    2. Model questions after WAEC, NECO, and JAMB standards for Senior Secondary level, and B.E.C.E standards for Junior Secondary level.
                    3. Ensure the questions are clean, clear, and realistic—avoid dubious, overly convoluted, or outrageous framing. Maintain a balanced approach between theoretical concepts and practical core knowledge.
                    4. Give STRAIGHT DIRECT ANSWERS ONLY to the short answer questions. Do not include long explanations, preambles, or extra sentences.
                    5. CALCULATION CONSTRAINT: For any calculation problems, provide ONLY the exact final numerical answer with its proper unit (e.g., "120 cm³", "x = 4"). Do NOT show the working steps.
                    
                    JSON FORMATTING RULE:
                    - Return a single JSON object with a root key "questions".
                    - The "questions" key must hold a list of objects with exactly these keys: 'Question', 'Correct Answer'.
                    - 'Correct Answer' must contain ONLY the short phrase or final numerical answer.
                    - Set 'Options' field as an empty string in your output logic (or omit it entirely).
                    """
                
                try:
                    response = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[
                            {"role": "system", "content": "You are a highly intelligent and meticulous Chief Examiner for Nigerian national exam boards (WAEC, NECO, JAMB, BECE). You produce clear, highly accurate, standard-compliant exam items based on the NERDC curriculum. Always return responses in valid JSON format."},
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
                            raw_opts = raw_opts[:5]
                            opts_str = ", ".join([str(x).strip() for x in raw_opts])
                        else:
                            opts_str = str(raw_opts)
                            
                        new_qs.append({
                            "Subject": subject, "Topic": topic, "Type": q_type,
                            "Question": q.get("Question", ""), "Options": opts_str, "Correct Answer": q.get("Correct Answer", "")
                        })
                    
                    st.session_state["temp_generated"] = pd.DataFrame(new_qs)
                    st.success("Standard-compliant questions generated successfully!")
                except Exception as e:
                    st.error(f"Groq API Error: {e}")
                    
        if "temp_generated" in st.session_state:
            st.info("💡 **Review and edit the generated questions below.** You can click inside any cell to fix typos or modify the formatting before saving. You can also select rows on the left to delete them entirely.")
            
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
        You can format your questions directly in the text boxes below. The app will automatically render the formatting during the Live Quiz!
        
        **Basic Formatting:**
        * **Bold**: Wrap text in double asterisks ➡️ `**Mass**` becomes **Mass**
        * **Italic**: Wrap text in single asterisks ➡️ `*Velocity*` becomes *Velocity*
        * **Underline**: Use HTML tags ➡️ `<u>Define</u>` becomes <u>Define</u>
        
        **Science & Math:**
        * **Subscript (Chemistry)**: Use sub tags ➡️ `H<sub>2</sub>SO<sub>4</sub>` becomes H<sub>2</sub>SO<sub>4</sub>
        * **Superscript (Math)**: Use sup tags ➡️ `x<sup>2</sup> + y<sup>2</sup>` becomes x<sup>2</sup> + y<sup>2</sup>
        * **Complex Equations**: Wrap in dollar signs ➡️ `$\frac{1}{2} mv^2$`
        """)

    q_type = st.radio("Select Category", ["Multiple Choice (Objectives)", "Short Answer / Theory"], horizontal=True)
    
    with st.form("manual_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1: 
            # --- DYNAMIC SUBJECT SYNC ---
            active_subs = list(st.session_state.subjects)
            if not df_quiz.empty and "Subject" in df_quiz.columns:
                active_subs.extend(df_quiz["Subject"].dropna().unique().tolist())
            active_subs = sorted(list(set([str(s).strip() for s in active_subs if str(s).strip()])))
            
            sub = st.selectbox("Subject", active_subs)
        with col2: 
            top = st.text_input("Topic")
            
        q_text = st.text_area("Question Text")
        opts_text = st.text_input("Options (Separated by commas, omitting labels)", placeholder="e.g. 20 Hz, 40 Hz, 60 Hz, 80 Hz") if q_type == "Multiple Choice (Objectives)" else ""
        ans_text = st.text_area("Correct Answer (Include label prefix if objective, e.g., A) 20 Hz)")
        
        if st.form_submit_button("Save Question"):
            new_row = {"Subject": sub, "Topic": top, "Type": q_type, "Question": q_text, "Options": opts_text, "Correct Answer": ans_text}
            df_quiz = pd.concat([df_quiz, pd.DataFrame([new_row])], ignore_index=True)
            try:
                conn.update(worksheet="Questions", data=df_quiz)
                st.cache_data.clear() 
                st.success("Added successfully!")
            except Exception as e:
                st.error(f"Failed to save question to Google Sheets: {e}")

# --- MODULE 3: VIEW QUIZ BANK ---
elif choice == "View Quiz Bank":
    st.header("🗂️ Stored Questions Vault")
    st.caption("You can edit any question text, options, or answers directly in the table below, then click save. You can also check the 'Delete' box to remove records.")
    
    if not df_quiz.empty:
        col1, col2 = st.columns(2)
        with col1: sub_filter = st.multiselect("Filter View by Subject", df_quiz["Subject"].unique())
        with col2: type_filter = st.multiselect("Filter View by Category", df_quiz["Type"].unique())
        
        filtered = df_quiz.copy()
        if sub_filter: filtered = filtered[filtered["Subject"].isin(sub_filter)]
        if type_filter: filtered = filtered[filtered["Type"].isin(type_filter)]
        
        st.subheader("📚 Active Database Records")
        filtered.insert(0, "Delete", False)
        
        # Allow editing across all question fields while keeping the Delete checkbox interactive
        edited_df = st.data_editor(
            filtered,
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
                    st.success("Changes saved successfully to Google Sheets!")
                    st.cache_data.clear()
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
                        st.success("Selected records removed from database successfully!")
                        st.cache_data.clear()
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
            st.subheader("⏱️ Timer Settings")
            timer_mode = st.radio("Select Timer Format:", ["No Timer", "Per Question", "Entire Session"], horizontal=True)
            
            # Default values (in seconds)
            timer_seconds = 60
            session_total_seconds = 600
            
            if timer_mode == "Per Question":
                # Changed minimum to 1 second and step to 1
                timer_seconds = st.number_input("Seconds allocated per question:", min_value=1, max_value=3600, value=60, step=1)
            elif timer_mode == "Entire Session":
                # Changed from minutes to seconds, minimum to 1 second, and step to 1
                session_total_seconds = st.number_input("Total seconds allocated for the whole round:", min_value=1, max_value=10800, value=600, step=1)
            
            st.write("---")
            
            type_filtered_pool = df_quiz[df_quiz["Type"] == chosen_type]
            available_subjects = type_filtered_pool["Subject"].unique()
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
                            # Save the new seconds variable instead of minutes
                            st.session_state.session_total_seconds = session_total_seconds
                            
                        # Trigger the Ready, Set, Go screen
                        st.session_state.quiz_state = "countdown"
                        st.rerun()
                    else:
                        st.error("Please allocate at least 1 question to start.")
            elif len(available_subjects) == 0:
                st.warning(f"There are no questions in the database categorized as '{chosen_type}' yet.")
                
        else:
            # --- COUNTDOWN INTERSTITIAL SCREEN ---
            if st.session_state.quiz_state == "countdown":
                placeholder = st.empty()
                
                # 3, 2, 1 Loop
                for i in [3, 2, 1]:
                    placeholder.markdown(f"""
                        <div style='display: flex; flex-direction: column; align-items: center; justify-content: center; height: 60vh;'>
                            <h1 style='font-size: 4rem; color: #e2e8f0; margin-bottom: 0px;'>GET READY</h1>
                            <h1 style='font-size: 8rem; color: #ff4b4b; margin-top: 10px;'>{i}</h1>
                        </div>
                    """, unsafe_allow_html=True)
                    time.sleep(1)
                
                # GO!
                placeholder.markdown("""
                    <div style='display: flex; flex-direction: column; align-items: center; justify-content: center; height: 60vh;'>
                        <h1 style='font-size: 10rem; color: #38bdf8; margin: 0;'>GO! 🚀</h1>
                    </div>
                """, unsafe_allow_html=True)
                time.sleep(1)
                
                # Move to live state and start the global timer if applicable
                st.session_state.quiz_state = "live"
                if st.session_state.get("timer_mode") == "Entire Session":
                    # Removed the * 60 multiplier so it calculates purely in seconds
                    st.session_state.session_end_time_ms = int(time.time() * 1000) + (st.session_state.session_total_seconds * 1000)
                st.rerun()

            # --- MAIN LIVE VIEW ---
            elif st.session_state.quiz_state == "live":
                q_list = st.session_state.live_questions
                idx = st.session_state.current_q_index
                current_q = q_list[idx]
                
                # 1. TOP CONTROLS (Jump Selector & Restart Button)
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
                    if st.button("🔄 Restart Round", use_container_width=True, help="Repeat this exact quiz session and reset the timer"):
                        st.session_state.current_q_index = 0
                        st.session_state.show_answer = False
                        st.session_state.quiz_state = "countdown" # Triggers the countdown again!
                        st.rerun()
                
                st.write("") # Tiny spacer below dropdown
                
                # 2. BALANCED TIMER INJECTION
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
                
                # 3. BALANCED QUESTION CONTAINER
                st.markdown(f"""
                    <div style='background-color: #1e293b; padding: 12px 15px; border-radius: 8px; margin-bottom: 15px;'>
                        <span style='color: #38bdf8; font-weight: bold; font-size: 1.1rem;'>📍 Q{idx + 1}/{len(q_list)}:</span> 
                        <span style='color: #e2e8f0; font-size: 1rem;'>{current_q['Subject']} | {current_q['Topic']}</span>
                    </div>
                """, unsafe_allow_html=True)
                
                st.markdown(f"<div style='font-size: 1.25rem; font-weight: 500; line-height: 1.5; margin-bottom: 20px;'>{str(current_q['Question'])}</div>", unsafe_allow_html=True)
                
                # 4. SPACED OPTIONS
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
                
                st.write("---") # Visual divider before buttons
                
                # 5. BOTTOM NAVIGATION BAR
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

    # ==========================================
    # TAB 1: EXAM CREATION
    # ==========================================
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

            instructions = st.text_area("Instructions for Students", placeholder="e.g., Attempt all questions. No calculators allowed.")

            st.subheader("Availability Schedule")
            col3, col4 = st.columns(2)
            with col3:
                start_date = st.date_input("Start Date")
                start_time = st.time_input("Start Time")
            with col4:
                end_date = st.date_input("End Date")
                end_time = st.time_input("End Time")

            st.subheader("Question Selection")
            subjects = st.multiselect("Select Subjects", st.session_state.subjects)
            
            # --- NEW: Independent Question Quantities ---
            col_q1, col_q2 = st.columns(2)
            with col_q1:
                num_mcq = st.number_input("Multiple Choice Questions (per subject)", min_value=0, value=20)
            with col_q2:
                num_theory = st.number_input("Short Answer / Theory Questions (per subject)", min_value=0, value=5)
                allow_calc = st.checkbox("Allow Basic Scientific Calculator for this Exam")

            submit_exam = st.form_submit_button("Generate Exam Link")

            if submit_exam:
                if not exam_title or not exam_pin or not subjects:
                    st.error("Please fill in the Exam Title, Examiner PIN, and select at least one Subject.")
                elif num_mcq == 0 and num_theory == 0:
                    st.error("Please allocate at least 1 question to generate the exam.")
                else:
                    start_datetime = f"{start_date} {start_time}"
                    end_datetime = f"{end_date} {end_time}"
                    exam_id = f"EXAM-{str(uuid.uuid4())[:6].upper()}"
                    
                    # 1. Filter the live master database for selected subjects
                    selected_qs = df_quiz[df_quiz["Subject"].isin(subjects)]
                    
                    if selected_qs.empty:
                        st.error("No questions found in the database for the selected subjects.")
                    else:
                        with st.spinner("Compiling exam and saving to database..."):
                            final_exam_qs = []
                            
                    # 2. Independent Extraction Logic
                            for subj in subjects:
                                # Pull Multiple Choice FIRST
                                if num_mcq > 0:
                                    pool_mcq = selected_qs[(selected_qs["Subject"] == subj) & (selected_qs["Type"] == "Multiple Choice (Objectives)")]
                                    if not pool_mcq.empty:
                                        # --- NEW WARNING MESSAGE ---
                                        if len(pool_mcq) < num_mcq:
                                            st.warning(f"⚠️ Only {len(pool_mcq)} Multiple Choice questions available for {subj} (Requested: {num_mcq}).")
                                            
                                        sampled_mcq = pool_mcq.sample(n=min(num_mcq, len(pool_mcq)))
                                        for idx, row in sampled_mcq.iterrows():
                                            final_exam_qs.append({
                                                "Exam_ID": exam_id,
                                                "Question_Number": 0, 
                                                "Question_Type": row["Type"],
                                                "Subject": row["Subject"],
                                                "Question_Text": row["Question"],
                                                "Options": row["Options"],
                                                "Correct_Answer": row["Correct Answer"]
                                            })
                                            
                                # Pull Short Answer Theory SECOND
                                if num_theory > 0:
                                    pool_theory = selected_qs[(selected_qs["Subject"] == subj) & (selected_qs["Type"] == "Short Answer / Theory")]
                                    if not pool_theory.empty:
                                        # --- NEW WARNING MESSAGE ---
                                        if len(pool_theory) < num_theory:
                                            st.warning(f"⚠️ Only {len(pool_theory)} Theory questions available for {subj} (Requested: {num_theory}).")
                                            
                                        sampled_theory = pool_theory.sample(n=min(num_theory, len(pool_theory)))
                                        for idx, row in sampled_theory.iterrows():
                                            final_exam_qs.append({
                                                "Exam_ID": exam_id,
                                                "Question_Number": 0, 
                                                "Question_Type": row["Type"],
                                                "Subject": row["Subject"],
                                                "Question_Text": row["Question"],
                                                "Options": row["Options"],
                                                "Correct_Answer": row["Correct Answer"]
                                            })
                            
                            # 3. Number the questions sequentially
                            for i, q in enumerate(final_exam_qs):
                                q["Question_Number"] = i + 1
                                
                            # 4. Prepare the master exam record
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
                                "Allow_Calculator": [allow_calc] # <--- NEW LINE ADDED HERE
                            }
                            
                            try:
                                # 5. Connect and append to Google Sheets
                                df_new_exam = pd.DataFrame(exam_record)
                                df_new_qs = pd.DataFrame(final_exam_qs)
                                
                                df_active = conn.read(worksheet="Active_Exams")
                                df_active = pd.concat([df_active, df_new_exam], ignore_index=True)
                                conn.update(worksheet="Active_Exams", data=df_active)
                                
                                df_exam_questions = conn.read(worksheet="Exam_Questions")
                                df_exam_questions = pd.concat([df_exam_questions, df_new_qs], ignore_index=True)
                                conn.update(worksheet="Exam_Questions", data=df_exam_questions)
                                
                                st.success("✅ Exam Successfully Created & Saved to Database!")
                                
                                # Replace with your actual Streamlit app domain name below:
                                base_url = "https://quiz-master-by-joe-v8hv3x7blqf35lgjpge6br.streamlit.app"
                                exam_url = f"{base_url}/?exam={exam_id}"
                                
                                st.info(f"**Share this link with students:**\n{exam_url}")
                            except Exception as e:
                                st.error(f"Failed to connect to Google Sheets: {e}")

    # ==========================================
    # TAB 2: EXAM DELETION (Hardcoded Admin Pin)
    # ==========================================
    with manage_tab:
        st.subheader("🗑️ Delete Active Exams")
        st.warning("Deleting an exam will permanently erase it from Active_Exams, Exam_Questions, and Student_Results.")
        
        try:
            # Fetch active exams dynamically
            df_active_view = conn.read(worksheet="Active_Exams", ttl="1m")
            active_exams_list = ["Select an exam..."] + df_active_view["Exam_ID"].dropna().tolist()
        except:
            active_exams_list = ["Select an exam..."]
            
        exam_to_delete = st.selectbox("Select Exam to Delete", active_exams_list) 
        
        # Security Check using your existing master bypass PIN
        admin_pin_input = st.text_input("Enter Master Admin PIN to confirm", type="password", key="delete_exam_pin")
        
        if st.button("🗑️ Delete Exam Record", type="primary"):
            if admin_pin_input == "1960": 
                if exam_to_delete != "Select an exam...":
                    try:
                        with st.spinner("Wiping exam records from all databases..."):
                            # 1. Delete from Active_Exams
                            df_active = conn.read(worksheet="Active_Exams")
                            df_active = df_active[df_active["Exam_ID"] != exam_to_delete]
                            conn.update(worksheet="Active_Exams", data=df_active)
                            
                            # 2. Delete from Exam_Questions
                            df_eq = conn.read(worksheet="Exam_Questions")
                            if not df_eq.empty and "Exam_ID" in df_eq.columns:
                                df_eq = df_eq[df_eq["Exam_ID"] != exam_to_delete]
                                conn.update(worksheet="Exam_Questions", data=df_eq)
                                
                            # 3. Delete from Student_Results
                            try:
                                df_sr = conn.read(worksheet="Student_Results")
                                if not df_sr.empty and "Exam_ID" in df_sr.columns:
                                    df_sr = df_sr[df_sr["Exam_ID"] != exam_to_delete]
                                    conn.update(worksheet="Student_Results", data=df_sr)
                            except:
                                pass # Fails gracefully if Student_Results is empty
                                
                            st.success(f"Successfully deleted {exam_to_delete} and all associated records.")
                            time.sleep(2)
                            st.rerun()
                    except Exception as e:
                        st.error(f"Error during deletion: {e}")
                else:
                    st.error("Please select a valid exam to delete.")
            elif admin_pin_input != "":
                st.error("❌ Incorrect Admin PIN. Deletion unauthorized.")
