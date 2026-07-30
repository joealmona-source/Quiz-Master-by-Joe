import streamlit as st
import pandas as pd
import os
import json
import random
import time
import uuid
import base64
from io import BytesIO
from PIL import Image
from datetime import datetime
import streamlit.components.v1 as components
from groq import Groq
from streamlit_gsheets import GSheetsConnection

# --- REPORTLAB PDF IMPORTS ---
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors

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

# --- CUSTOM BALANCED & THEME-ADAPTIVE CSS ---
st.markdown("""
    <style>
    /* Main Layout & Typography */
    .block-container {
        padding-top: 2.5rem !important; 
        padding-bottom: 2.5rem !important;
        max-width: 1200px !important;
    }
    div[data-testid="stVerticalBlock"] {
        gap: 1rem !important;
    }

    /* Professional Button Styling */
    .stButton > button {
        padding: 0.5rem 1rem !important;
        min-height: 2.6rem !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        transition: all 0.2s ease-in-out !important;
        border: 1px solid rgba(128, 128, 128, 0.2) !important;
        box-shadow: 0 2px 5px rgba(0,0,0,0.02) !important;
    }
    .stButton > button:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08) !important;
    }

    /* Primary Buttons Styling */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #2563eb, #1d4ed8) !important;
        color: #ffffff !important;
        border: none !important;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3) !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #1d4ed8, #1e40af) !important;
        box-shadow: 0 6px 16px rgba(37, 99, 235, 0.4) !important;
    }

    /* Container Cards & Forms */
    div[data-testid="stForm"] {
        background-color: var(--secondary-background-color) !important;
        border-radius: 12px !important;
        border: 1px solid rgba(128, 128, 128, 0.18) !important;
        padding: 1.5rem !important;
        box-shadow: 0 4px 18px rgba(0, 0, 0, 0.03) !important;
    }

    /* Form Inputs & Selectboxes */
    .stTextInput input, .stSelectbox div[role="combobox"], .stNumberInput input, .stTextArea textarea {
        border-radius: 8px !important;
        border: 1px solid rgba(128, 128, 128, 0.25) !important;
        transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
    }
    .stTextInput input:focus, .stSelectbox div[role="combobox"]:focus, .stTextArea textarea:focus {
        border-color: #2563eb !important;
        box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.18) !important;
    }

    /* Tabs Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px !important;
        border-bottom: 2px solid rgba(128, 128, 128, 0.15) !important;
    }
    .stTabs [data-baseweb="tab"] {
        height: 42px !important;
        border-radius: 8px 8px 0px 0px !important;
        padding: 0px 18px !important;
        font-weight: 600 !important;
    }
    .stTabs [aria-selected="true"] {
        background-color: rgba(37, 99, 235, 0.08) !important;
        border-bottom: 3px solid #2563eb !important;
    }

    /* Metrics Styling */
    div[data-testid="stMetric"] {
        background-color: var(--secondary-background-color) !important;
        padding: 16px 20px !important;
        border-radius: 12px !important;
        border: 1px solid rgba(128, 128, 128, 0.15) !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.02) !important;
    }

    /* Expander Styling */
    div[data-testid="stExpander"] {
        border-radius: 10px !important;
        border: 1px solid rgba(128, 128, 128, 0.18) !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.02) !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- GOOGLE SHEETS CONNECTION ---
conn = st.connection("gsheets", type=GSheetsConnection)

# ==============================================================================
# PDF HELPER FUNCTION
# ==============================================================================
def generate_class_overview_pdf(dataframe):
    df_export = dataframe.copy()
    columns_to_exclude = ["grading_corrections", "Detailed_Responses"]
    df_export = df_export.drop(columns=[col for col in columns_to_exclude if col in df_export.columns])
    
    buffer = BytesIO()
    pdf = SimpleDocTemplate(buffer, pagesize=letter)
    data = [df_export.columns.to_list()] + df_export.values.tolist()
    
    table = Table(data)
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.dimgrey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ])
    table.setStyle(style)
    pdf.build([table])
    buffer.seek(0)
    return buffer.getvalue()

# ==============================================================================
# SECURITY & CONFIRMATION MODALS
# ==============================================================================
@st.dialog("⚠️ Confirm Submission")
def confirm_submit_modal():
    st.write("Are you sure you want to submit your exam now?")
    st.caption("Once submitted, you will not be able to modify your answers.")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Yes, Submit", type="primary", use_container_width=True):
            st.session_state.exam_state = "submitted"
            st.rerun()
    with col2:
        if st.button("Cancel", use_container_width=True):
            st.rerun()

@st.dialog("🚪 Confirm Exit")
def confirm_quit_modal():
    st.write("Are you sure you want to quit the exam?")
    st.caption("Your session will end and unsubmitted answers may be lost.")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Yes, Quit", type="primary", use_container_width=True):
            for k in ["exam_state", "exam_qs", "student_answers", "current_q", "exam_end_timestamp_ms", "student_info"]:
                st.session_state.pop(k, None)
            st.rerun()
    with col2:
        if st.button("Cancel", use_container_width=True):
            st.rerun()

def inject_exam_security():
    st.markdown(
        """
        <style>
        * { -webkit-user-select: none !important; -moz-user-select: none !important; -ms-user-select: none !important; user-select: none !important; }
        @media print { html, body { display: none !important; } }
        </style>
        """, unsafe_allow_html=True
    )
    components.html(
        """
        <script>
        (function() {
            let targetWin = window; let targetDoc = document;
            try { if (window.parent && window.parent.document) { targetWin = window.parent; targetDoc = window.parent.document; } } catch (e) {}
            try { sessionStorage.setItem("exam_active", "true"); } catch(e) {}
            if (targetWin.__examSecurityInitialized) return;
            targetWin.__examSecurityInitialized = true;
            function isActive() { try { return sessionStorage.getItem("exam_active") === "true"; } catch(e) { return false; } }
            function getStrikes() { try { return parseInt(sessionStorage.getItem("exam_strikes") || "0"); } catch(e) { return 0; } }
            function setStrikes(val) { try { sessionStorage.setItem("exam_strikes", val.toString()); } catch(e) {} }
            function handleViolation(reason) {
                if (!isActive()) return;
                let lastStr = sessionStorage.getItem("exam_last_violation") || "0";
                let lastViolationTime = parseInt(lastStr, 10);
                let now = Date.now();
                if (now - lastViolationTime < 1500) return;
                sessionStorage.setItem("exam_last_violation", now.toString());
                let strikes = getStrikes() + 1;
                setStrikes(strikes);
                if (strikes <= 3) {
                    alert(`⚠️ SECURITY WARNING (${strikes}/3 Attempts Used)\\n\\nYou ${reason}. Leaving or minimizing the exam window 4 times will automatically submit your exam!`);
                    sessionStorage.setItem("exam_last_violation", Date.now().toString());
                } else {
                    const buttons = Array.from(targetWin.document.querySelectorAll('button'));
                    const autoSubmitBtn = buttons.find(btn => btn.innerText.includes('AUTO_SUBMIT_HIDDEN'));
                    if (autoSubmitBtn) { autoSubmitBtn.click(); } else {
                        try { const url = new URL(targetWin.location.href); url.searchParams.set("autosubmit", "1"); targetWin.location.href = url.href; } 
                        catch(e) { targetWin.location.search = targetWin.location.search + (targetWin.location.search.includes('?') ? '&' : '?') + "autosubmit=1"; }
                    }
                }
            }
            targetDoc.addEventListener("visibilitychange", function() { if (targetDoc.hidden || targetDoc.visibilityState === "hidden") { handleViolation("switched tabs or minimized the browser"); } });
            targetWin.addEventListener("blur", function() { setTimeout(function() { if (targetDoc.activeElement && (targetDoc.activeElement.tagName === "IFRAME" || targetDoc.activeElement.tagName === "iframe")) { return; } handleViolation("left or minimized the exam window"); }, 100); });
            targetDoc.addEventListener('contextmenu', e => { if(isActive()) e.preventDefault(); });
            targetDoc.addEventListener('keydown', e => { if (isActive() && e.ctrlKey && (e.key === 'c' || e.key === 'u' || e.key === 's' || e.key === 'p')) { e.preventDefault(); } });
        })();
        </script>
        """, height=0, width=0
    )

def process_image_for_db(uploaded_file):
    if uploaded_file is None: return ""
    file_bytes = uploaded_file.read()
    if len(file_bytes) > 100 * 1024:
        st.error("⚠️ File exceeds the 100KB limit. Please upload a smaller image.")
        st.stop()
    try:
        img = Image.open(BytesIO(file_bytes))
        if img.mode != 'RGB': img = img.convert('RGB')
        img.thumbnail((600, 600)) 
        buffered = BytesIO()
        img.save(buffered, format="JPEG", quality=70)
        b64_string = base64.b64encode(buffered.getvalue()).decode()
        if len(b64_string) > 48000:
            buffered = BytesIO()
            img.save(buffered, format="JPEG", quality=40)
            b64_string = base64.b64encode(buffered.getvalue()).decode()
        return f"data:image/jpeg;base64,{b64_string}"
    except Exception as e:
        st.error(f"Image processing failed: {e}")
        return ""

# --- EXAM MODE URL INTERCEPTOR ---
if "exam" in st.query_params:
    exam_id_param = st.query_params["exam"]
    if st.query_params.get("autosubmit") == "1":
        st.session_state.exam_state = "submitted"
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
    st.markdown(f"<h1 style='text-align: center; color: var(--text-color); margin-bottom: 0.2rem;'>{exam_info.get('School_Name', '')}</h1>", unsafe_allow_html=True)
    st.markdown(f"<h3 style='text-align: center; color: #38bdf8; margin-top: 0;'>{exam_info.get('Exam_Title', '')}</h3>", unsafe_allow_html=True)
    
    examiner_name = str(exam_info.get('Examiner_Name', '')).strip()
    if examiner_name and examiner_name.lower() != "nan":
        st.markdown(f"<p style='text-align: center; color: var(--text-color); opacity: 0.8; font-size: 1.1rem;'><b>Examiner:</b> {examiner_name}</p>", unsafe_allow_html=True)
    
    if "exam_state" not in st.session_state: st.session_state.exam_state = "landing"
        
    if st.session_state.exam_state == "landing":
        components.html('<script>try { sessionStorage.removeItem("exam_strikes"); sessionStorage.removeItem("exam_last_violation"); sessionStorage.setItem("exam_active", "false"); } catch(e) {}</script>', height=0, width=0)
        st.write("---")
        st.markdown(f"<div style='text-align: center; font-style: italic; font-size: 1.1rem; color: var(--text-color); opacity: 0.85; background-color: var(--secondary-background-color); padding: 12px 20px; border-radius: 10px; border: 1px solid rgba(128,128,128,0.15);'><b>Instructions:</b><br>{exam_info['Instructions']}</div>", unsafe_allow_html=True)
        st.write("---")
        st.warning("**🔒 STRICT EXAM SECURITY RULES & WARNING:**\n* **No Copying or Text Selection:** Copying question text or using inspect tools is strictly disabled.\n* **No Screenshots or Screen Recording:** Capturing exam content is monitored and prohibited.\n* **Tab Switching / Window Minimizing:** You are **NOT** allowed to switch tabs or minimize this browser window. \n  * **3-Strike Policy:** You are allowed a maximum of **3 warnings**.\n  * **Automatic Submission:** On your **4th attempt/violation**, your exam will be **automatically submitted** immediately without notice.", icon="⚠️")
        
        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader("📝 Student Registration")
            student_name = st.text_input("Full Name (Surname First)")
            student_class = st.text_input("Class")
            student_contact = st.text_input("Contact / Phone Number (Optional)")
            if st.button("🚀 Start Exam", type="primary", use_container_width=True):
                try:
                    df_results_check = conn.read(worksheet="Student_Results", ttl=0)
                    exam_history = df_results_check[df_results_check["Exam_ID"] == exam_info["Exam_ID"]]
                    taken_names = [str(name).strip().lower() for name in exam_history["Student_Name"].dropna().tolist()]
                except: taken_names = []
                current_time = datetime.now()
                try:
                    start_dt = datetime.strptime(str(exam_info["Start_DateTime"]), "%Y-%m-%d %H:%M:%S")
                    end_dt = datetime.strptime(str(exam_info["End_DateTime"]), "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    start_dt = pd.to_datetime(exam_info["Start_DateTime"])
                    end_dt = pd.to_datetime(exam_info["End_DateTime"])
                if not student_name or not student_class: st.error("⚠️ Please enter your name and class to begin.")
                elif student_name.strip().lower() in taken_names: st.error(f"🛑 Access Denied: A submission for '{student_name.strip()}' has already been recorded.")
                elif current_time < start_dt: st.error(f"⏳ **Too Early:** This exam opens on {start_dt.strftime('%B %d, %Y at %I:%M %p')}.")
                elif current_time > end_dt: st.error("🛑 **Exam Closed:** The submission window for this exam has expired.")
                else:
                    st.session_state.student_info = {"name": student_name, "class": student_class, "contact": student_contact}
                    st.session_state.exam_state = "in_progress"
                    try: allowed_secs = int(exam_info["Timer_Seconds"])
                    except: allowed_secs = 1800
                    st.session_state.exam_end_timestamp_ms = int(time.time() * 1000) + (allowed_secs * 1000)
                    st.rerun()
        with col2:
            st.subheader("👨‍🏫 Examiner Portal")
            entered_pin = st.text_input("Enter Exam PIN", type="password")
            if st.button("📊 View Scores", use_container_width=True):
                db_pin = str(exam_info["Exam_PIN"]).split(".")[0].strip()
                if entered_pin.strip() == db_pin:
                    st.session_state.exam_state = "examiner_dashboard"
                    st.rerun()
                else: st.error("Incorrect PIN. Access Denied.")

    elif st.session_state.exam_state == "in_progress":
        st.markdown("<style>.stRadio label p { font-size: 20px !important; margin-left: 10px; line-height: 1.5; color: var(--text-color) !important; } .stRadio div[role='radio'] { transform: scale(1.4); margin-top: 2px; } .stRadio > div { gap: 1.2rem !important; }</style>", unsafe_allow_html=True)
        inject_exam_security()
        if "exam_qs" not in st.session_state:
            df_eq = conn.read(worksheet="Exam_Questions", ttl="10m")
            st.session_state.exam_qs = df_eq[df_eq["Exam_ID"] == exam_info["Exam_ID"]].to_dict('records')
            if "student_answers" not in st.session_state: st.session_state.student_answers = {} 
            st.session_state.current_q = 0
        if "exam_end_timestamp_ms" not in st.session_state:
            try: allowed_secs = int(exam_info["Timer_Seconds"])
            except: allowed_secs = 1800 
            st.session_state.exam_end_timestamp_ms = int(time.time() * 1000) + (allowed_secs * 1000)
            
        qs = st.session_state.exam_qs
        idx = st.session_state.current_q
        if not qs: st.error("⚠️ No questions were found loaded for this exam ID."); st.stop()
        current_q_data = qs[idx]
        
        top1, top2 = st.columns([1.5, 1.2])
        with top1:
            timer_html = f"""
            <div id="exam_timer" style="font-size: 1.5rem; font-weight: bold; color: #16a34a; font-family: monospace; padding-top: 5px;"></div>
            <script>
            var endTime = {st.session_state.exam_end_timestamp_ms};
            var elem = document.getElementById('exam_timer');
            var timerId = setInterval(function() {{
                var timeLeft = Math.floor((endTime - Date.now()) / 1000);
                if (timeLeft <= 0) {{ clearInterval(timerId); elem.innerHTML = "00:00"; elem.style.color = "red"; let targetWin = window.parent || window; const buttons = Array.from(targetWin.document.querySelectorAll('button')); const autoSubmitBtn = buttons.find(btn => btn.innerText.includes('AUTO_SUBMIT_HIDDEN')); if (autoSubmitBtn) {{ autoSubmitBtn.click(); }} else {{ try {{ const url = new URL(targetWin.location.href); url.searchParams.set("autosubmit", "1"); targetWin.location.href = url.href; }} catch(e) {{ targetWin.location.search = "?autosubmit=1"; }} }} }} 
                else {{ var h = Math.floor(timeLeft / 3600); var m = Math.floor((timeLeft % 3600) / 60); var s = Math.floor(timeLeft % 60); if (h > 0) {{ elem.innerHTML = "⏱️ " + (h < 10 ? "0" : "") + h + ":" + (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s; }} else {{ elem.innerHTML = "⏱️ " + (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s; }} if(timeLeft < 120) {{ elem.style.color = "#dc2626"; }} }}
            }}, 1000);
            </script>
            """
            st.components.v1.html(timer_html, height=45)
            
        with top2:
            b_col1, b_col2 = st.columns(2)
            with b_col1:
                if st.button("Submit 🏁", type="primary", use_container_width=True): confirm_submit_modal()
            with b_col2:
                if st.button("Quit ❌", use_container_width=True): confirm_quit_modal()

        if exam_info.get("Allow_Calculator") == True:
            with st.expander("🧮 Open Scientific Calculator", expanded=False): st.components.v1.html("""<iframe width="100%" height="350px" style="border: none;" src="https://www.desmos.com/scientific"></iframe>""", height=360)
        st.markdown("---")
        img_data = current_q_data.get('Image', '')
        if pd.notna(img_data) and str(img_data).startswith('data:image'): st.image(img_data, use_container_width=False, width=600)
            
        st.markdown(f"<div style='background-color: var(--secondary-background-color); padding: 18px 20px; border-radius: 10px; border-left: 5px solid #2563eb; border-right: 1px solid rgba(128,128,128,0.15); border-top: 1px solid rgba(128,128,128,0.15); border-bottom: 1px solid rgba(128,128,128,0.15); margin-bottom: 20px;'><span style='color: var(--text-color); opacity: 0.7; font-weight: 600; font-size: 1.05rem;'>Question {idx + 1} of {len(qs)}</span><h3 style='color: var(--text-color); margin-top: 8px;'>{current_q_data.get('Question_Text', '')}</h3></div>", unsafe_allow_html=True)
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
                    if opt.startswith(tuple(f"{l})" for l in letters)): formatted_options.append(opt)
                    else: formatted_options.append(f"{prefix}{opt}")
                selection = st.radio("Select your answer:", formatted_options, index=formatted_options.index(saved_ans) if saved_ans in formatted_options else None, key=f"q_radio_{idx}")
                if selection: st.session_state.student_answers[idx] = selection
            else: st.warning("⚠️ No options found for this question.")
        else:
            theory_ans = st.text_area("Type your answer here:", value=saved_ans if saved_ans else "", key=f"q_text_{idx}", height=150)
            if theory_ans: st.session_state.student_answers[idx] = theory_ans
                
        st.write("")
        c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
        with c2:
            if st.button("⬅️ Previous", use_container_width=True, disabled=(idx == 0)): st.session_state.current_q -= 1; st.rerun()
        with c3:
            if st.button("Next ➡️", use_container_width=True, disabled=(idx == len(qs) - 1)): st.session_state.current_q += 1; st.rerun()
                
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
                        if grid_cols[j].button(btn_label, key=f"nav_grid_{q_index}", use_container_width=True): st.session_state.current_q = q_index; st.rerun()
        if st.button("AUTO_SUBMIT_HIDDEN", key="auto_submit_hidden"): st.session_state.exam_state = "submitted"; st.rerun()
        components.html("<script>let targetWin = window.parent || window; let buttons = Array.from(targetWin.document.querySelectorAll('button')); let autoSubmitBtn = buttons.find(btn => btn.innerText.includes('AUTO_SUBMIT_HIDDEN')); if (autoSubmitBtn) { let container = autoSubmitBtn.closest('div[data-testid=\"stButton\"]'); if (container) { container.style.display = 'none'; } else { autoSubmitBtn.style.display = 'none'; } }</script>", height=0, width=0)

    elif st.session_state.exam_state == "submitted":
        components.html('<script>try { sessionStorage.setItem("exam_active", "false"); } catch(e){}</script>', height=0, width=0)
        if "student_info" not in st.session_state: st.error("Session information was lost."); st.stop()
        st.success("🎉 Exam Submitted Successfully!")
        if not st.session_state.get("results_saved", False):
            with st.spinner("Calculating your score and saving results..."):
                auto_score = 0; detailed_responses = {}
                try: points = int(exam_info.get("Points_Per_Question", 2))
                except: points = 2
                for i, q in enumerate(st.session_state.exam_qs):
                    student_ans = str(st.session_state.student_answers.get(i, "")).strip()
                    is_correct = False; q_type = str(q.get("Question_Type", "")).lower()
                    correct_ans = str(q.get("Correct_Answer", "")).strip()
                    if "multiple choice" in q_type or "objective" in q_type:
                        db_correct_ans = correct_ans.lower(); clean_student_text = student_ans.lower(); student_letter = ""
                        if ")" in student_ans:
                            parts = student_ans.split(")", 1); student_letter = parts[0].strip().lower(); clean_student_text = parts[1].strip().lower()
                        clean_db_text = db_correct_ans
                        if ")" in db_correct_ans: clean_db_text = db_correct_ans.split(")", 1)[1].strip().lower()
                        if clean_student_text != "":
                            if (clean_student_text == clean_db_text) or (student_letter == db_correct_ans) or (student_ans.lower() == db_correct_ans):
                                auto_score += points; is_correct = True
                    detailed_responses[f"Q{i+1}"] = { "Question": q.get("Question_Text", ""), "Type": q.get("Question_Type", ""), "Student_Answer": student_ans, "Is_Correct": is_correct, "Correct_Answer": correct_ans }
                result_data = {
                    "Exam_ID": [exam_info["Exam_ID"]], "Student_Name": [st.session_state.student_info["name"]], "Class": [st.session_state.student_info["class"]],
                    "Contact": [st.session_state.student_info.get("contact", "")], "Auto_Score": [auto_score], "Manual_Score": [0], "Total_Score": [auto_score], "Detailed_Responses": [str(detailed_responses)]
                }
                try:
                    df_results = conn.read(worksheet="Student_Results", ttl=0) 
                    df_new_result = pd.DataFrame(result_data)
                    df_updated = df_new_result if df_results.empty else pd.concat([df_results, df_new_result], ignore_index=True)
                    conn.update(worksheet="Student_Results", data=df_updated)
                    st.cache_data.clear(); st.session_state.results_saved = True; st.info("✅ Your answers have been securely recorded. You may safely close this window."); st.balloons()
                except Exception as e: st.error(f"⚠️ Error saving results: {e}") 
        else: st.info("✅ Your answers have already been securely recorded. You may safely close this window.")
  
    elif st.session_state.exam_state == "examiner_dashboard":
        st.markdown("<h2 style='text-align: center;'>👨‍🏫 Examiner Dashboard</h2>", unsafe_allow_html=True)
        if st.button("⬅️ Back to Start"): st.session_state.exam_state = "landing"; st.rerun()
        st.write("---")
        try:
            df_results = conn.read(worksheet="Student_Results", ttl=0)
            exam_results = df_results[df_results["Exam_ID"] == exam_info["Exam_ID"]]
        except Exception as e: st.error("Could not fetch student results from the database."); exam_results = pd.DataFrame()

        if exam_results.empty: st.info("No students have submitted results for this exam yet.")
        else:
            st.subheader("📊 Class Overview")
            display_df = exam_results[["Student_Name", "Class", "Auto_Score", "Manual_Score", "Total_Score"]]
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            pdf_bytes = generate_class_overview_pdf(display_df)
            st.download_button(label="📥 Download Class Overview as PDF", data=pdf_bytes, file_name=f"{exam_info.get('Exam_Title', 'Exam')}_Class_Overview.pdf", mime="application/pdf", type="primary")

            st.write("---")
            st.subheader("📝 Granular Question-by-Question Grading")
            selected_student = st.selectbox("Select a student to review and grade:", exam_results["Student_Name"].tolist())

            if selected_student:
                student_idx = exam_results[exam_results["Student_Name"] == selected_student].index[0]
                student_data = exam_results.loc[student_idx]
                st.markdown(f"**Reviewing Student:** {student_data['Student_Name']} ({student_data['Class']})")
                import ast
                try: responses = ast.literal_eval(student_data["Detailed_Responses"])
                except: responses = {}
                try: points_per_q = int(exam_info.get("Points_Per_Question", 1))
                except: points_per_q = 1

                total_auto_calc = 0; total_manual_calc = 0

                for q_key, data in responses.items():
                    st.markdown("---")
                    q_type = str(data.get("Type", "")); is_mcq = "multiple" in q_type.lower() or "objective" in q_type.lower()
                    col_q, col_score_box = st.columns([3, 1])
                    with col_q:
                        st.markdown(f"**{q_key}: {data['Question']}**")
                        color = "#16a34a" if (is_mcq and data.get("Is_Correct", False)) else ("#dc2626" if is_mcq else "#0284c7")
                        st.markdown(f"<div style='background-color: var(--secondary-background-color); padding: 10px 14px; border-radius: 8px; border-left: 4px solid {color}; border-right: 1px solid rgba(128,128,128,0.15); border-top: 1px solid rgba(128,128,128,0.15); border-bottom: 1px solid rgba(128,128,128,0.15); margin-bottom: 6px;'><span style='color: var(--text-color);'>Student Answer: <b>{data.get('Student_Answer', '')}</b></span></div>", unsafe_allow_html=True)
                        correct_ans = data.get("Correct_Answer", "Check master question list")
                        st.markdown(f"<div style='padding-left: 10px; margin-bottom: 15px;'><span style='color: #10b981; font-size: 0.9em; font-weight: 600;'>✅ Correct Answer: {correct_ans}</span></div>", unsafe_allow_html=True)
                    with col_score_box:
                        if is_mcq:
                            awarded = points_per_q if data.get("Is_Correct", False) else 0
                            total_auto_calc += awarded; st.markdown(f"<br><b>Score: {awarded}/{points_per_q}</b>", unsafe_allow_html=True)
                        else:
                            existing_q_score = int(data.get("Manual_Score_Given", 0))
                            q_score_input = st.number_input(f"Score ({q_key})", min_value=0, max_value=20, value=existing_q_score, key=f"manual_{student_idx}_{q_key}")
                            data["Manual_Score_Given"] = q_score_input; total_manual_calc += q_score_input

                sum_theory_manual = sum(int(d.get("Manual_Score_Given", 0)) for d in responses.values() if not ("multiple" in str(d.get("Type", "")).lower() or "objective" in str(d.get("Type", "")).lower()))
                final_calculated_total = total_auto_calc + sum_theory_manual
                st.write(""); st.markdown(f"### 🧮 Live Score Summary: Auto ({total_auto_calc}) + Manual ({sum_theory_manual}) = **Total: {final_calculated_total}**")

                if st.button("💾 Save All Grades & Update Total Score", type="primary"):
                    df_results.at[student_idx, "Auto_Score"] = total_auto_calc; df_results.at[student_idx, "Manual_Score"] = sum_theory_manual
                    df_results.at[student_idx, "Total_Score"] = final_calculated_total; df_results.at[student_idx, "Detailed_Responses"] = str(responses)
                    with st.spinner("Saving grades to database..."): conn.update(worksheet="Student_Results", data=df_results)
                    st.success(f"✅ Successfully updated grades for {selected_student}!"); time.sleep(1); st.rerun()
    st.stop()
    
# --- GLOBAL AUTHENTICATION & DATA LOADING ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.logged_in_school = ""

try:
    df_codes = conn.read(worksheet="AccessCodes", ttl="10m") 
    df_codes['Code'] = df_codes['Code'].astype(str).str.strip()
except Exception as e:
    df_codes = pd.DataFrame(columns=["School Name", "Code"]) 

# --- LOGIN SCREEN ---
if not st.session_state.authenticated:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
            <div style='text-align: center; padding: 1.8rem 1rem 1rem 1rem;'>
                <div style='font-size: 3.2rem; margin-bottom: 0.2rem;'>🔒</div>
                <h2 style='margin: 0; font-weight: 700; color: var(--text-color);'>System Locked</h2>
                <p style='color: var(--text-color); opacity: 0.75; font-size: 0.95rem; margin-top: 0.4rem;'>Enter your School Access Code to unlock</p>
            </div>
        """, unsafe_allow_html=True)
        entered_code = st.text_input("Access Code", type="password", placeholder="••••••••").strip()
        
        if st.button("Unlock System", type="primary", use_container_width=True):
            if entered_code == "1960": 
                st.session_state.authenticated = True; st.session_state.logged_in_school = "Admin"
                st.success("Access Granted! Welcome back, Admin."); time.sleep(1); st.rerun()
            elif not df_codes.empty and entered_code in df_codes['Code'].values:
                school_row = df_codes[df_codes['Code'] == entered_code].iloc[0]
                school_name = school_row['School Name']
                st.session_state.authenticated = True; st.session_state.logged_in_school = school_name
                st.success(f"Access Granted! Welcome, {school_name}."); time.sleep(1); st.rerun()
            else: st.error("❌ Invalid Access Code. Please contact the administrator.")
    st.stop() 

# --- MULTI-TENANT GLOBAL DATABASE LOADING ---
try: df_quiz_global = conn.read(worksheet="Questions", ttl="10m").dropna(how="all")
except Exception: df_quiz_global = pd.DataFrame(columns=["School", "Class", "Subject", "Topic", "Type", "Question", "Image", "Options", "Correct Answer"])
if "School" not in df_quiz_global.columns: df_quiz_global.insert(0, "School", "Unassigned")

try: df_subjects_global = conn.read(worksheet="Subjects", ttl="10m").dropna(how="all")
except Exception: df_subjects_global = pd.DataFrame(columns=["School", "Subjects"])
if "School" not in df_subjects_global.columns: df_subjects_global.insert(0, "School", "Unassigned")

try: df_classes_global = conn.read(worksheet="Classes", ttl="10m").dropna(how="all")
except Exception: df_classes_global = pd.DataFrame(columns=["School", "Classes"])
if "School" not in df_classes_global.columns: df_classes_global.insert(0, "School", "Unassigned")

# --- ADMIN CONTEXT SWITCHING & SIDEBAR MENU ---
st.sidebar.title("🏆 Quiz Control Panel")

if st.sidebar.button("🔄 Sync Google Sheets", use_container_width=True):
    st.cache_data.clear(); st.sidebar.success("App synced with Google Sheets!")

if st.session_state.logged_in_school == "Admin":
    menu = ["School Management", "AI Question Generator", "Manual Input", "View Quiz Bank", "Class Settings", "Subject Settings", "Live Competition Mode", "Exam Mode Setup"]
    choice = st.sidebar.selectbox("Go to Module", menu)
    if choice != "School Management":
        st.sidebar.markdown("---")
        school_list = df_codes["School Name"].dropna().unique().tolist()
        active_school = st.sidebar.selectbox("🛠️ Working As (Select School context):", school_list)
        if not active_school:
            st.sidebar.warning("⚠️ No client schools found. Please add a school in 'School Management' first.")
            st.stop()
    else:
        active_school = "Admin"
else:
    menu = ["AI Question Generator", "Manual Input", "View Quiz Bank", "Class Settings", "Subject Settings", "Live Competition Mode", "Exam Mode Setup"]
    choice = st.sidebar.selectbox("Go to Module", menu)
    active_school = st.session_state.logged_in_school

# --- FILTER LOCAL DATAFRAMES BY ACTIVE SCHOOL CONTEXT ---
if active_school and active_school != "Admin":
    df_quiz = df_quiz_global[df_quiz_global["School"] == active_school].copy()
    df_subjects = df_subjects_global[df_subjects_global["School"] == active_school].copy()
    df_classes = df_classes_global[df_classes_global["School"] == active_school].copy()
else:
    df_quiz = pd.DataFrame(columns=df_quiz_global.columns)
    df_subjects = pd.DataFrame(columns=df_subjects_global.columns)
    df_classes = pd.DataFrame(columns=df_classes_global.columns)

# Load Classes (Filtered Scope)
DEFAULT_CLASSES = ["JSS 1", "JSS 2", "JSS 3", "SSS 1", "SSS 2", "SSS 3"]
loaded_classes = df_classes["Classes"].dropna().tolist() if not df_classes.empty else []
if not df_quiz.empty and "Class" in df_quiz.columns: loaded_classes.extend(df_quiz["Class"].dropna().unique().tolist())
if not loaded_classes: loaded_classes = DEFAULT_CLASSES
if "classes" not in st.session_state or st.session_state.get("last_school") != active_school:
    st.session_state.classes = sorted(list(set([str(c).strip() for c in loaded_classes if str(c).strip()])))
    st.session_state.last_school = active_school

def save_classes():
    global df_classes_global
    new_class_df = pd.DataFrame({"School": [active_school] * len(st.session_state.classes), "Classes": st.session_state.classes})
    df_other = df_classes_global[df_classes_global["School"] != active_school]
    df_updated = pd.concat([df_other, new_class_df], ignore_index=True)
    try: conn.update(worksheet="Classes", data=df_updated); st.cache_data.clear()
    except Exception as e: st.error(f"Failed to save classes to Google Sheets: {e}")

# Load Subjects (Filtered Scope)
DEFAULT_SUBJECTS = ["Mathematics", "English Language", "Physics", "Chemistry", "Biology", "Basic Science", "Agricultural Science"]
loaded_subjects = df_subjects["Subjects"].dropna().tolist() if not df_subjects.empty else []
if not df_quiz.empty and "Subject" in df_quiz.columns: loaded_subjects.extend(df_quiz["Subject"].dropna().unique().tolist())
if not loaded_subjects: loaded_subjects = DEFAULT_SUBJECTS
st.session_state.subjects = sorted(list(set([str(s).strip() for s in loaded_subjects if str(s).strip()])))

def save_subjects():
    global df_subjects_global
    new_sub_df = pd.DataFrame({"School": [active_school] * len(st.session_state.subjects), "Subjects": st.session_state.subjects})
    df_other = df_subjects_global[df_subjects_global["School"] != active_school]
    df_updated = pd.concat([df_other, new_sub_df], ignore_index=True)
    try: conn.update(worksheet="Subjects", data=df_updated); st.cache_data.clear()
    except Exception as e: st.error(f"Failed to save subjects to Google Sheets: {e}")

# ==============================================================================
# MODULE 0: SCHOOL MANAGEMENT (ADMIN ONLY)
# ==============================================================================
if choice == "School Management":
    st.header("🏫 School Management & Configuration")
    st.caption("Admin control panel for managing client schools and their access credentials.")

    tab_manage, tab_view = st.tabs(["⚙️ Manage Schools", "👁️ View School Data"])

    with tab_manage:
        col_add, col_edit = st.columns(2)
        with col_add:
            st.subheader("➕ Add New School")
            with st.form("add_school_form", clear_on_submit=True):
                new_school_name = st.text_input("School Name")
                new_school_pass = st.text_input("Assign Password (Access Code)")
                if st.form_submit_button("Add School", type="primary"):
                    if new_school_name and new_school_pass:
                        if not df_codes.empty and new_school_name in df_codes["School Name"].values:
                            st.error("School Name already exists!")
                        else:
                            new_row = pd.DataFrame([{"School Name": new_school_name, "Code": str(new_school_pass)}])
                            df_codes_updated = pd.concat([df_codes, new_row], ignore_index=True)
                            try:
                                conn.update(worksheet="AccessCodes", data=df_codes_updated)
                                st.success(f"Added {new_school_name} successfully!")
                                st.cache_data.clear(); time.sleep(1); st.rerun()
                            except Exception as e: st.error(f"Error saving to database: {e}")
                    else: st.warning("Please fill in both fields.")

        with col_edit:
            st.subheader("📝 Edit or Delete School")
            if not df_codes.empty:
                school_list_edit = df_codes["School Name"].dropna().tolist()
                if school_list_edit:
                    selected_school_edit = st.selectbox("Select School to Modify", school_list_edit)
                    current_code = df_codes.loc[df_codes["School Name"] == selected_school_edit, "Code"].values[0]
                    new_code = st.text_input("Edit Password", value=str(current_code))

                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("Update Password", use_container_width=True):
                            df_codes.loc[df_codes["School Name"] == selected_school_edit, "Code"] = str(new_code)
                            conn.update(worksheet="AccessCodes", data=df_codes)
                            st.success("Password updated!"); st.cache_data.clear(); time.sleep(1); st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete Data", type="primary", use_container_width=True):
                            df_codes = df_codes[df_codes["School Name"] != selected_school_edit]
                            conn.update(worksheet="AccessCodes", data=df_codes)
                            
                            df_quiz_global = df_quiz_global[df_quiz_global["School"] != selected_school_edit]
                            df_subjects_global = df_subjects_global[df_subjects_global["School"] != selected_school_edit]
                            df_classes_global = df_classes_global[df_classes_global["School"] != selected_school_edit]
                            conn.update(worksheet="Questions", data=df_quiz_global)
                            conn.update(worksheet="Subjects", data=df_subjects_global)
                            conn.update(worksheet="Classes", data=df_classes_global)
                            
                            st.warning(f"Deleted {selected_school_edit} and all associated data."); st.cache_data.clear(); time.sleep(1.5); st.rerun()

    with tab_view:
        st.subheader("📊 School Data Viewer")
        if not df_codes.empty:
            school_list_view = df_codes["School Name"].dropna().tolist()
            if school_list_view:
                view_school = st.selectbox("Select a school to view their database:", school_list_view, key="view_sch_select")
                sch_qs = df_quiz_global[df_quiz_global["School"] == view_school]
                sch_subs = df_subjects_global[df_subjects_global["School"] == view_school]
                sch_cls = df_classes_global[df_classes_global["School"] == view_school]

                st.markdown("---")
                c1, c2, c3 = st.columns(3)
                c1.metric("Total Questions", len(sch_qs))
                c2.metric("Configured Subjects", len(sch_subs))
                c3.metric("Configured Classes", len(sch_cls))
                st.write("")
                with st.expander(f"📚 View Subjects for {view_school}"):
                    if not sch_subs.empty: st.write(", ".join(sch_subs["Subjects"].dropna().tolist()))
                    else: st.info("No subjects configured yet.")
                with st.expander(f"🏫 View Classes for {view_school}"):
                    if not sch_cls.empty: st.write(", ".join(sch_cls["Classes"].dropna().tolist()))
                    else: st.info("No classes configured yet.")
                with st.expander(f"❓ View Questions for {view_school}"):
                    if not sch_qs.empty: st.dataframe(sch_qs[["Class", "Subject", "Topic", "Type", "Question"]], use_container_width=True, hide_index=True)
                    else: st.info("No questions configured yet.")

# --- MODULE: CLASS SETTINGS ---
elif choice == "Class Settings":
    st.header(f"🏫 Class Management Dashboard ({active_school})")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("➕ Add New Class")
        new_class = st.text_input("Enter Class Name", placeholder="e.g., JSS 1A, SSS 2 Science")
        if st.button("Add Class", type="primary") and new_class:
            clean_class = new_class.strip()
            if clean_class not in st.session_state.classes:
                st.session_state.classes.append(clean_class); save_classes()
                st.success(f"'{clean_class}' added successfully!"); st.rerun()
            else: st.warning("Class already exists.")
                
    with col2:
        st.subheader("📝 Edit / Remove Existing Classes")
        if st.session_state.classes:
            class_to_edit = st.selectbox("Select Class to Modify", sorted(st.session_state.classes))
            edit_col1, edit_col2 = st.columns(2)
            with edit_col1:
                rename_val = st.text_input("Rename to:", value=class_to_edit)
                if st.button("Rename Class"):
                    new_name = rename_val.strip()
                    if new_name:
                        idx = st.session_state.classes.index(class_to_edit)
                        st.session_state.classes[idx] = new_name
                        if not df_quiz.empty and "Class" in df_quiz.columns:
                            df_quiz_global.loc[(df_quiz_global["School"] == active_school) & (df_quiz_global["Class"] == class_to_edit), "Class"] = new_name
                            try: conn.update(worksheet="Questions", data=df_quiz_global)
                            except: pass
                        save_classes(); st.success("Renamed successfully!"); st.rerun()
            with edit_col2:
                st.write("🚨 **Danger Zone:**")
                st.caption("Admin access required to delete a class.")
                admin_pin = st.text_input("Enter Admin PIN to unlock:", type="password", key="del_class_pin")
                if admin_pin == "1960": 
                    if st.button("🗑️ Delete Class", type="primary"):
                        st.session_state.classes.remove(class_to_edit); save_classes()
                        st.warning(f"'{class_to_edit}' removed from configuration."); st.rerun()
                elif admin_pin != "": st.error("Incorrect PIN.")

# --- MODULE: SUBJECT SETTINGS ---
elif choice == "Subject Settings":
    st.header(f"⚙️ Subject Management Dashboard ({active_school})")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("➕ Add New Subject")
        new_sub = st.text_input("Enter Subject Name", placeholder="e.g., Further Mathematics")
        if st.button("Add Subject", type="primary") and new_sub:
            clean_sub = new_sub.strip()
            if clean_sub not in st.session_state.subjects:
                st.session_state.subjects.append(clean_sub); save_subjects()
                st.success(f"'{clean_sub}' added successfully!"); st.rerun()
            else: st.warning("Subject already exists.")
                
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
                            df_quiz_global.loc[(df_quiz_global["School"] == active_school) & (df_quiz_global["Subject"] == sub_to_edit), "Subject"] = new_name
                            try: conn.update(worksheet="Questions", data=df_quiz_global)
                            except: pass
                        save_subjects(); st.success("Renamed successfully!"); st.rerun()
            with edit_col2:
                st.write("🚨 **Danger Zone:**")
                st.caption("Admin access required to delete.")
                admin_pin = st.text_input("Enter Admin PIN to unlock:", type="password", key="del_sub_pin")
                if admin_pin == "1960": 
                    if st.button("🗑️ Delete Subject", type="primary"):
                        st.session_state.subjects.remove(sub_to_edit); save_subjects()
                        st.warning(f"'{sub_to_edit}' removed."); st.rerun()
                elif admin_pin != "": st.error("Incorrect PIN.")

# --- MODULE 1: AI QUESTION GENERATOR ---
elif choice == "AI Question Generator":
    st.header("🤖 AI-Assisted Question Generator")
    if "GROQ_API_KEY" in st.secrets: api_key = st.secrets["GROQ_API_KEY"]
    else: api_key = None
    
    if api_key:
        client = Groq(api_key=api_key)
        col1, col2 = st.columns(2)
        with col1:
            q_class = st.selectbox("Designate to Class", sorted(st.session_state.classes))
            subject = st.selectbox("Subject", sorted(st.session_state.subjects))
            q_type = st.radio("Select Question Category", ["Multiple Choice (Objectives)", "Short Answer / Theory"])
        with col2:
            topic = st.text_input("Topic / Area")
            num_q = st.slider("Number of Questions", 1, 10, 3)
            
        if st.button("✨ Auto-Generate Questions", type="primary"):
            with st.spinner(f"Drafting standard NERDC curriculum questions for {q_class} {subject}..."):
                if q_type == "Multiple Choice (Objectives)":
                    prompt = f"Generate {num_q} standard secondary school level Multiple Choice questions for {subject} on topic: '{topic}'. Target Audience Level: {q_class}. Adapt the difficulty accordingly. CURRICULUM & EXAM ALIGNMENT: 1. Align the questions strictly with the Nigerian Educational Research and Development Council (NERDC) curriculum. 2. Maintain a realistic and balanced mix of conceptual, theoretical, and calculation-based questions. STRICT RANDOMIZATION RULE: - Shuffle the correct answer evenly across the 1st, 2nd, 3rd, and 4th positions. JSON FORMATTING RULE: - Return a single JSON object with a root key 'questions'. - Inside 'questions', provide a list of objects with exactly these keys: 'Question', 'Options', 'Correct Answer'. - 'Options' must be a JSON array containing EXACTLY 4 strings. Do NOT write 'A)', 'B)' inside the array elements. - 'Correct Answer' must map to the correct option WITH a letter indicator (e.g., 'C) 30 m/s')."
                else:
                    prompt = f"Generate {num_q} standard secondary school level Short Answer/Theory questions for {subject} on topic: '{topic}'. Target Audience Level: {q_class}. Adapt the difficulty accordingly. JSON FORMATTING RULE: - Return a single JSON object with a root key 'questions'. - The 'questions' key must hold a list of objects with exactly these keys: 'Question', 'Correct Answer'. - 'Correct Answer' must contain ONLY the short phrase or final numerical answer. - Set 'Options' field as an empty string."
                
                try:
                    response = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[{"role": "system", "content": "You are an intelligent Chief Examiner for Nigerian national exams. Return responses in valid JSON format."}, {"role": "user", "content": prompt}],
                        response_format={"type": "json_object"}, temperature=0.65
                    )
                    generated_data = json.loads(response.choices[0].message.content)
                    new_qs = []
                    for q in generated_data.get("questions", []):
                        raw_opts = q.get("Options", "")
                        opts_str = ", ".join([str(x).strip() for x in raw_opts[:5]]) if isinstance(raw_opts, list) else str(raw_opts)
                        new_qs.append({
                            "School": active_school, "Class": q_class, "Subject": subject, "Topic": topic, "Type": q_type,
                            "Question": q.get("Question", ""), "Image": "", "Options": opts_str, "Correct Answer": q.get("Correct Answer", "")
                        })
                    st.session_state["temp_generated"] = pd.DataFrame(new_qs)
                    st.success("Questions generated successfully!")
                except Exception as e: st.error(f"Groq API Error: {e}")
                    
        if "temp_generated" in st.session_state:
            st.info("💡 **Review and edit the generated questions below.**")
            edited_df = st.data_editor(st.session_state["temp_generated"], use_container_width=True, num_rows="dynamic")
            if st.button("💾 Save Edited Questions to Database", type="primary"):
                edited_df["School"] = active_school 
                df_quiz_global = pd.concat([df_quiz_global, edited_df], ignore_index=True)
                try:
                    conn.update(worksheet="Questions", data=df_quiz_global)
                    st.success("Committed to database!"); st.cache_data.clear(); del st.session_state["temp_generated"]; st.rerun()
                except Exception as e: st.error(f"Failed to save questions: {e}")
    else: st.warning("Please configure your GROQ_API_KEY inside your Streamlit Secrets Panel.")

# --- MODULE 2: MANUAL INPUT ---
elif choice == "Manual Input":
    st.header("📝 Manual Question Entry")
    q_type = st.radio("Select Category", ["Multiple Choice (Objectives)", "Short Answer / Theory"], horizontal=True)
    
    with st.form("manual_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1: 
            q_class = st.selectbox("Designate to Class", sorted(st.session_state.classes))
            sub = st.selectbox("Subject", sorted(st.session_state.subjects))
        with col2: top = st.text_input("Topic")
            
        q_text = st.text_area("Question Text")
        opts_text = st.text_input("Options (Separated by commas, omitting labels)", placeholder="e.g. 20 Hz, 40 Hz, 60 Hz") if q_type == "Multiple Choice (Objectives)" else ""
        ans_text = st.text_area("Correct Answer (Include label prefix if objective, e.g., A) 20 Hz)")
        
        st.markdown("---")
        st.subheader("🖼️ Question Image (Optional)")
        uploaded_img = st.file_uploader("Upload Image (Capped at 100 KB)", type=["png", "jpg", "jpeg"])
        
        if st.form_submit_button("Save Question", type="primary"):
            img_b64 = process_image_for_db(uploaded_img) if uploaded_img else ""
            new_row = { "School": active_school, "Class": q_class, "Subject": sub, "Topic": top, "Type": q_type, "Question": q_text, "Image": img_b64, "Options": opts_text, "Correct Answer": ans_text }
            df_quiz_global = pd.concat([df_quiz_global, pd.DataFrame([new_row])], ignore_index=True)
            try:
                conn.update(worksheet="Questions", data=df_quiz_global)
                st.cache_data.clear(); st.success("Added successfully!")
            except Exception as e: st.error(f"Failed to save question to Google Sheets: {e}")

# --- MODULE 3: VIEW QUIZ BANK ---
elif choice == "View Quiz Bank":
    st.header(f"🗂️ Stored Questions Vault ({active_school})")
    if not df_quiz.empty:
        col1, col2, col3 = st.columns(3)
        with col1: class_filter = st.multiselect("Filter View by Class", sorted(st.session_state.classes))
        with col2: sub_filter = st.multiselect("Filter View by Subject", sorted(st.session_state.subjects))
        with col3: type_filter = st.multiselect("Filter View by Category", df_quiz["Type"].unique())
        
        filtered = df_quiz.copy()
        if class_filter: filtered = filtered[filtered["Class"].isin(class_filter)]
        if sub_filter: filtered = filtered[filtered["Subject"].isin(sub_filter)]
        if type_filter: filtered = filtered[filtered["Type"].isin(type_filter)]
        
        st.subheader(f"📚 Active Database Records ({len(filtered)})")
        filtered.insert(0, "Delete", False)
        
        col_config = { "Image": st.column_config.ImageColumn("Image Thumbnail", help="Thumbnail of uploaded image") }
        edited_df = st.data_editor(filtered, hide_index=False, use_container_width=True, column_config=col_config)
        
        col_save, col_del = st.columns(2)
        with col_save:
            if st.button("💾 Save Changes to Database", type="primary", use_container_width=True):
                updated_subset = edited_df.drop(columns=["Delete"])
                df_quiz_global.update(updated_subset) 
                try:
                    conn.update(worksheet="Questions", data=df_quiz_global)
                    st.success("Changes saved successfully to Google Sheets!"); st.cache_data.clear(); st.rerun()
                except Exception as e: st.error(f"Failed to update database: {e}")
        
        indices_to_delete = edited_df[edited_df["Delete"] == True].index
        with col_del:
            if len(indices_to_delete) > 0:
                if st.button(f"🗑️ Delete Selected Records ({len(indices_to_delete)})", use_container_width=True):
                    df_quiz_global = df_quiz_global.drop(indices_to_delete).reset_index(drop=True)
                    try:
                        conn.update(worksheet="Questions", data=df_quiz_global)
                        st.success("Selected records removed from database successfully!"); st.cache_data.clear(); st.rerun()
                    except Exception as e: st.error(f"Failed to delete records in Google Sheets: {e}")
    else: st.info("The saved question vault is currently empty for this school.")

# --- MODULE 4: LIVE COMPETITION MODE ---
elif choice == "Live Competition Mode":
    if not df_quiz.empty:
        if len(st.session_state.live_questions) == 0:
            st.header("🎬 Grand Arena - Setup")
            chosen_class = st.selectbox("Select Class Level", ["All Classes"] + sorted(st.session_state.classes))
            chosen_type = st.radio("Select Competition Format", ["Multiple Choice (Objectives)", "Short Answer / Theory"], horizontal=True)
            st.write("---")
            st.subheader("⏱️ Timer Settings")
            timer_mode = st.radio("Select Timer Format:", ["No Timer", "Per Question", "Entire Session"], horizontal=True)
            timer_seconds = 60; session_total_seconds = 600
            if timer_mode == "Per Question": timer_seconds = st.number_input("Seconds allocated per question:", min_value=1, max_value=3600, value=60, step=1)
            elif timer_mode == "Entire Session": session_total_seconds = st.number_input("Total seconds allocated for the whole round:", min_value=1, max_value=10800, value=600, step=1)
            
            st.write("---")
            type_filtered_pool = df_quiz[df_quiz["Type"] == chosen_type]
            if chosen_class != "All Classes": type_filtered_pool = type_filtered_pool[type_filtered_pool["Class"] == chosen_class]
            available_subjects = type_filtered_pool["Subject"].dropna().unique()
            chosen_subjects = st.multiselect("Select Subjects to include in this round", available_subjects)
            
            if chosen_subjects:
                st.write(f"🔧 Set Question Quantities per Subject:")
                config_counts = {}
                for s in chosen_subjects:
                    max_avail = len(type_filtered_pool[type_filtered_pool["Subject"] == s])
                    config_counts[s] = st.number_input(f"Questions from '{s}' (Max: {max_avail})", min_value=0, max_value=max_avail, value=min(2, max_avail))
                
                if st.button("🚀 Compile and Randomize Game Show Pool", type="primary"):
                    round_pool = []
                    for s, count in config_counts.items():
                        if count > 0:
                            sub_pool = type_filtered_pool[type_filtered_pool["Subject"] == s].sample(n=int(count)).to_dict(orient="records")
                            round_pool.extend(sub_pool)
                    
                    if round_pool:
                        random.shuffle(round_pool); st.session_state.live_questions = round_pool; st.session_state.current_q_index = 0
                        st.session_state.show_answer = False; st.session_state.timer_mode = timer_mode
                        if timer_mode == "Per Question": st.session_state.timer_seconds = timer_seconds
                        elif timer_mode == "Entire Session": st.session_state.session_total_seconds = session_total_seconds
                        st.session_state.quiz_state = "countdown"; st.rerun()
                    else: st.error("Please allocate at least 1 question to start.")
            elif len(available_subjects) == 0: st.warning(f"No database questions match the chosen Class and Category.")
                
        else:
            if st.session_state.quiz_state == "countdown":
                placeholder = st.empty()
                for i in [3, 2, 1]:
                    placeholder.markdown(f"<div style='display: flex; flex-direction: column; align-items: center; justify-content: center; height: 60vh;'><h1 style='font-size: 4rem; color: var(--text-color); margin-bottom: 0px;'>GET READY</h1><h1 style='font-size: 8rem; color: #ef4444; margin-top: 10px;'>{i}</h1></div>", unsafe_allow_html=True)
                    time.sleep(1)
                placeholder.markdown("<div style='display: flex; flex-direction: column; align-items: center; justify-content: center; height: 60vh;'><h1 style='font-size: 10rem; color: #38bdf8; margin: 0;'>GO! 🚀</h1></div>", unsafe_allow_html=True); time.sleep(1)
                st.session_state.quiz_state = "live"
                if st.session_state.get("timer_mode") == "Entire Session": st.session_state.session_end_time_ms = int(time.time() * 1000) + (st.session_state.session_total_seconds * 1000)
                st.rerun()

            elif st.session_state.quiz_state == "live":
                q_list = st.session_state.live_questions
                idx = st.session_state.current_q_index
                current_q = q_list[idx]
                
                top_c1, top_c2 = st.columns([4, 1])
                with top_c1:
                    q_labels = [f"Question {i+1} {'⭐' if i == idx else ''}" for i in range(len(q_list))]
                    chosen_q_label = st.selectbox("Jump to:", q_labels, index=idx, label_visibility="collapsed")
                    new_idx = q_labels.index(chosen_q_label)
                    if new_idx != idx: st.session_state.current_q_index = new_idx; st.session_state.show_answer = False; st.rerun()
                with top_c2:
                    if st.button("🔄 Restart Round", use_container_width=True): st.session_state.current_q_index = 0; st.session_state.show_answer = False; st.session_state.quiz_state = "countdown"; st.rerun()
                
                st.write("") 
                current_mode = st.session_state.get("timer_mode", "No Timer")
                if current_mode == "Per Question":
                    timer_html = f"""<div style="font-size: 22px; font-family: monospace; font-weight: bold; color: #ef4444; text-align: center; border: 2px solid rgba(239, 68, 68, 0.4); border-radius: 10px; padding: 8px; margin-bottom: 15px; background-color: rgba(239, 68, 68, 0.08); line-height: 1;"><span id="timer_display_{idx}"></span></div><script>var timeLeft = {st.session_state.get('timer_seconds', 60)}; var elem = document.getElementById('timer_display_{idx}'); var timerId = setInterval(countdown, 1000); function countdown() {{ if (timeLeft <= 0) {{ clearInterval(timerId); elem.innerHTML = "🚨 TIME UP!"; }} else {{ elem.innerHTML = "⏱️ " + timeLeft + "s"; timeLeft--; }} }} countdown();</script>"""
                    components.html(timer_html, height=45)
                elif current_mode == "Entire Session":
                    end_time_ms = st.session_state.get("session_end_time_ms", 0)
                    timer_html = f"""<div style="font-size: 22px; font-family: monospace; font-weight: bold; color: #ef4444; text-align: center; border: 2px solid rgba(239, 68, 68, 0.4); border-radius: 10px; padding: 8px; margin-bottom: 15px; background-color: rgba(239, 68, 68, 0.08); line-height: 1;"><span id="global_timer_display"></span></div><script>var endTime = {end_time_ms}; var elem = document.getElementById('global_timer_display'); function updateTimer() {{ var timeLeft = Math.floor((endTime - Date.now()) / 1000); if (timeLeft <= 0) {{ elem.innerHTML = "🚨 TIME UP!"; }} else {{ var h = Math.floor(timeLeft / 3600); var m = Math.floor((timeLeft % 3600) / 60); var s = timeLeft % 60; if (h > 0) {{ elem.innerHTML = "⏱️ " + (h < 10 ? "0" : "") + h + ":" + (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s; }} else {{ elem.innerHTML = "⏱️ " + (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s; }} }} }} updateTimer(); setInterval(updateTimer, 1000); </script>"""
                    components.html(timer_html, height=45)
                
                img_data = current_q.get('Image', '')
                if pd.notna(img_data) and str(img_data).startswith('data:image'): st.image(img_data, use_container_width=False, width=800)
                    
                st.markdown(f"<div style='background-color: var(--secondary-background-color); border: 1px solid rgba(128,128,128,0.2); padding: 12px 18px; border-radius: 10px; margin-bottom: 15px;'><span style='color: #0284c7; font-weight: bold; font-size: 1.1rem;'>📍 Q{idx + 1}/{len(q_list)}:</span> <span style='color: var(--text-color); font-size: 1rem; font-weight: 500;'>{current_q.get('Class', 'Uncategorized')} | {current_q['Subject']} | {current_q['Topic']}</span></div>", unsafe_allow_html=True)
                st.markdown(f"<div style='font-size: 1.3rem; font-weight: 600; line-height: 1.5; margin-bottom: 20px; color: var(--text-color);'>{str(current_q['Question'])}</div>", unsafe_allow_html=True)
                
                if current_q['Type'] == "Multiple Choice (Objectives)" and pd.notna(current_q['Options']) and str(current_q['Options']).strip() != "":
                    options_split = str(current_q['Options']).split(","); prefixes = ["A)", "B)", "C)", "D)", "E)"]
                    for index, option in enumerate(options_split):
                        if index >= len(prefixes): break
                        clean_opt = option.strip()
                        opt_display = clean_opt if any(clean_opt.startswith(p) for p in prefixes) else f"{prefixes[index]} {clean_opt}"
                        st.markdown(f"<div style='background-color: var(--secondary-background-color); border: 1px solid rgba(128, 128, 128, 0.18); border-radius: 8px; padding: 10px 16px; margin-bottom: 8px; font-size: 1.05rem; font-weight: 500; color: var(--text-color);'>🔹 {opt_display}</div>", unsafe_allow_html=True)
                
                st.write("---") 
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    if st.button("👁️ Show Ans", use_container_width=True): st.session_state.show_answer = not st.session_state.show_answer
                with c2:
                    if st.button("⬅️ Prev", use_container_width=True) and idx > 0: st.session_state.current_q_index -= 1; st.session_state.show_answer = False; st.rerun()
                with c3:
                    if st.button("Next ➡️", use_container_width=True) and idx < len(q_list) - 1: st.session_state.current_q_index += 1; st.session_state.show_answer = False; st.rerun()
                with c4:
                    if st.button("❌ End Game", use_container_width=True): st.session_state.live_questions = []; st.session_state.current_q_index = 0; st.session_state.show_answer = False; st.session_state.quiz_state = "setup"; st.rerun()
                
                if st.session_state.show_answer: st.success(f"**Ans:** {current_q['Correct Answer']}")
    else: st.info("The database is currently empty.")

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
                school_name = st.text_input("School Name", value=active_school)
                examiner_name = st.text_input("Examiner Name")
            with col2:
                exam_pin = st.text_input("Examiner PIN (To view scores later)", type="password")
                timer_seconds = st.number_input("Timer (in seconds)", min_value=60, value=3600, step=60)
                points_per_q = st.number_input("Points Per Question", min_value=1, value=1)

            instructions = st.text_area("Instructions for Students", placeholder="e.g., Attempt all questions. No calculators allowed.")

            st.subheader("Availability Schedule")
            col3, col4 = st.columns(2)
            with col3:
                start_date = st.date_input("Start Date"); start_time = st.time_input("Start Time")
            with col4:
                end_date = st.date_input("End Date"); end_time = st.time_input("End Time")

            st.subheader("Question Selection")
            chosen_class = st.selectbox("Select Target Class", ["All Classes"] + sorted(st.session_state.classes))
            subjects = st.multiselect("Select Subjects", st.session_state.subjects)
            
            col_q1, col_q2 = st.columns(2)
            with col_q1: num_mcq = st.number_input("Multiple Choice Questions (per subject)", min_value=0, value=20)
            with col_q2:
                num_theory = st.number_input("Short Answer / Theory Questions (per subject)", min_value=0, value=5)
                allow_calc = st.checkbox("Allow Basic Scientific Calculator for this Exam")

            if st.form_submit_button("Generate Exam Link", type="primary"):
                if not exam_title or not exam_pin or not subjects: st.error("Please fill in the Exam Title, Examiner PIN, and select at least one Subject.")
                elif num_mcq == 0 and num_theory == 0: st.error("Please allocate at least 1 question to generate the exam.")
                else:
                    start_datetime = f"{start_date} {start_time}"; end_datetime = f"{end_date} {end_time}"; exam_id = f"EXAM-{str(uuid.uuid4())[:6].upper()}"
                    filtered_pool = df_quiz[df_quiz["Subject"].isin(subjects)]
                    if chosen_class != "All Classes": filtered_pool = filtered_pool[filtered_pool["Class"] == chosen_class]
                    
                    if filtered_pool.empty: st.error("No questions found in the database matching the selected subjects and class criteria.")
                    else:
                        with st.spinner("Compiling exam and saving to database..."):
                            final_exam_qs = []
                            for subj in subjects:
                                if num_mcq > 0:
                                    pool_mcq = filtered_pool[(filtered_pool["Subject"] == subj) & (filtered_pool["Type"] == "Multiple Choice (Objectives)")]
                                    if not pool_mcq.empty:
                                        if len(pool_mcq) < num_mcq: st.warning(f"⚠️ Only {len(pool_mcq)} Multiple Choice questions available for {subj} (Requested: {num_mcq}).")
                                        sampled_mcq = pool_mcq.sample(n=min(num_mcq, len(pool_mcq)))
                                        for idx, row in sampled_mcq.iterrows():
                                            final_exam_qs.append({ "Exam_ID": exam_id, "Question_Number": 0, "Question_Type": row["Type"], "Class": row.get("Class", ""), "Subject": row["Subject"], "Question_Text": row["Question"], "Image": row.get("Image", ""), "Options": row["Options"], "Correct_Answer": row["Correct Answer"] })
                                            
                                if num_theory > 0:
                                    pool_theory = filtered_pool[(filtered_pool["Subject"] == subj) & (filtered_pool["Type"] == "Short Answer / Theory")]
                                    if not pool_theory.empty:
                                        if len(pool_theory) < num_theory: st.warning(f"⚠️ Only {len(pool_theory)} Theory questions available for {subj} (Requested: {num_theory}).")
                                        sampled_theory = pool_theory.sample(n=min(num_theory, len(pool_theory)))
                                        for idx, row in sampled_theory.iterrows():
                                            final_exam_qs.append({ "Exam_ID": exam_id, "Question_Number": 0, "Question_Type": row["Type"], "Class": row.get("Class", ""), "Subject": row["Subject"], "Question_Text": row["Question"], "Image": row.get("Image", ""), "Options": row["Options"], "Correct_Answer": row["Correct Answer"] })
                            
                            for i, q in enumerate(final_exam_qs): q["Question_Number"] = i + 1
                                
                            exam_record = {
                                "Exam_ID": [exam_id], "Exam_Title": [exam_title], "School_Name": [school_name], "Examiner_Name": [examiner_name], "Instructions": [instructions],
                                "Exam_PIN": [exam_pin], "Start_DateTime": [start_datetime], "End_DateTime": [end_datetime], "Timer_Seconds": [timer_seconds], "Points_Per_Question": [points_per_q], "Status": ["Active"], "Allow_Calculator": [allow_calc]
                            }
                            
                            try:
                                df_active = conn.read(worksheet="Active_Exams", ttl="10m")
                                df_active = pd.concat([df_active, pd.DataFrame(exam_record)], ignore_index=True)
                                conn.update(worksheet="Active_Exams", data=df_active)
                                
                                df_exam_questions = conn.read(worksheet="Exam_Questions", ttl="10m")
                                df_exam_questions = pd.concat([df_exam_questions, pd.DataFrame(final_exam_qs)], ignore_index=True)
                                conn.update(worksheet="Exam_Questions", data=df_exam_questions)
                                
                                st.cache_data.clear()
                                
                                st.success("✅ Exam Successfully Created & Saved to Database!")
                                base_url = "https://quiz-master-by-joe-v8hv3x7blqf35lgjpge6br.streamlit.app"
                                st.info(f"**Share this link with students:**\n{base_url}/?exam={exam_id}")
                            except Exception as e: st.error(f"Failed to connect to Google Sheets: {e}")

    with manage_tab:
        st.subheader("🗑️ Delete Active Exams")
        st.warning("Deleting an exam will permanently erase it from Active_Exams, Exam_Questions, and Student_Results.")
        try:
            df_active_view = conn.read(worksheet="Active_Exams", ttl="10m")
            active_exams_list = ["Select an exam..."] + df_active_view["Exam_ID"].dropna().tolist()
        except: active_exams_list = ["Select an exam..."]
            
        exam_to_delete = st.selectbox("Select Exam to Delete", active_exams_list) 
        admin_pin_input = st.text_input("Enter Master Admin PIN to confirm", type="password", key="delete_exam_pin")
        
        if st.button("🗑️ Delete Exam Record", type="primary"):
            if admin_pin_input == "1960": 
                if exam_to_delete != "Select an exam...":
                    try:
                        with st.spinner("Wiping exam records from all databases..."):
                            df_active = conn.read(worksheet="Active_Exams", ttl="10m")
                            df_active = df_active[df_active["Exam_ID"] != exam_to_delete]
                            conn.update(worksheet="Active_Exams", data=df_active)
                            
                            df_eq = conn.read(worksheet="Exam_Questions", ttl="10m")
                            if not df_eq.empty and "Exam_ID" in df_eq.columns:
                                df_eq = df_eq[df_eq["Exam_ID"] != exam_to_delete]
                                conn.update(worksheet="Exam_Questions", data=df_eq)
                                
                            try:
                                df_sr = conn.read(worksheet="Student_Results", ttl="10m")
                                if not df_sr.empty and "Exam_ID" in df_sr.columns:
                                    df_sr = df_sr[df_sr["Exam_ID"] != exam_to_delete]
                                    conn.update(worksheet="Student_Results", data=df_sr)
                            except: pass 
                                
                            st.success(f"Successfully deleted {exam_to_delete} and all associated records."); time.sleep(2); st.rerun()
                    except Exception as e: st.error(f"Error during deletion: {e}")
                else: st.error("Please select a valid exam to delete.")
            elif admin_pin_input != "": st.error("❌ Incorrect Admin PIN. Deletion unauthorized.")
