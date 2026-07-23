import streamlit as st
import pandas as pd
import os
import json
import random
import time
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

menu = ["AI Question Generator", "Manual Input", "View Quiz Bank", "Subject Settings", "Live Competition Mode"]
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
                st.write("Danger Zone:")
                if st.button("🗑️ Delete Subject", type="primary"):
                    st.session_state.subjects.remove(sub_to_edit)
                    save_subjects()
                    st.warning(f"'{sub_to_edit}' removed from list configuration.")
                    st.rerun()
        else:
            st.info("No subjects currently registered.")

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
    
    if not df_quiz.empty:
        col1, col2 = st.columns(2)
        with col1: sub_filter = st.multiselect("Filter View by Subject", df_quiz["Subject"].unique())
        with col2: type_filter = st.multiselect("Filter View by Category", df_quiz["Type"].unique())
        
        filtered = df_quiz.copy()
        if sub_filter: filtered = filtered[filtered["Subject"].isin(sub_filter)]
        if type_filter: filtered = filtered[filtered["Type"].isin(type_filter)]
        
        st.subheader("📚 Active Database Records")
        filtered.insert(0, "Delete", False)
        
        edited_df = st.data_editor(
            filtered,
            hide_index=False,
            use_container_width=True,
            disabled=["Subject", "Topic", "Type", "Question", "Options", "Correct Answer"]
        )
        
        indices_to_delete = edited_df[edited_df["Delete"] == True].index
        
        if len(indices_to_delete) > 0:
            if st.button(f"🗑️ Permanent Delete Selected Questions ({len(indices_to_delete)})", type="primary"):
                df_quiz = df_quiz.drop(indices_to_delete).reset_index(drop=True)
                try:
                    conn.update(worksheet="Questions", data=df_quiz)
                    st.success("Selected records removed from database successfully!")
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
