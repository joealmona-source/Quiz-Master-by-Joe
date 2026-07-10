import streamlit as st
import pandas as pd
import os
import json
import random
import time
import streamlit.components.v1 as components
from groq import Groq

st.set_page_config(page_title="School Quiz Champion Pro", layout="wide", initial_sidebar_state="expanded")

DB_FILE = "quiz_database.csv"
SUBJECTS_FILE = "subjects_list.json"

# --- SYSTEM INITIALIZATION ---
if os.path.exists(DB_FILE):
    df_quiz = pd.read_csv(DB_FILE)
else:
    df_quiz = pd.DataFrame(columns=["Subject", "Topic", "Type", "Question", "Options", "Correct Answer"])

DEFAULT_SUBJECTS = ["Mathematics", "English Language", "Physics", "Chemistry", "Biology", "Basic Science", "Agricultural Science"]
if os.path.exists(SUBJECTS_FILE):
    with open(SUBJECTS_FILE, "r") as f:
        stored_subjects = json.load(f)
else:
    stored_subjects = DEFAULT_SUBJECTS

if "subjects" not in st.session_state:
    st.session_state.subjects = stored_subjects

if "live_questions" not in st.session_state:
    st.session_state.live_questions = []
if "current_q_index" not in st.session_state:
    st.session_state.current_q_index = 0
if "show_answer" not in st.session_state:
    st.session_state.show_answer = False

def save_subjects():
    with open(SUBJECTS_FILE, "w") as f:
        json.dump(st.session_state.subjects, f)

# --- SIDEBAR MANAGEMENT ---
st.sidebar.title("🏆 Quiz Control Panel")
menu = ["AI Question Generator", "Manual Input", "View Quiz Bank", "Subject Settings", "Live Competition Mode"]
choice = st.sidebar.selectbox("Go to Module", menu)

# --- MODULE: SUBJECT SETTINGS ---
if choice == "Subject Settings":
    st.header("⚙️ Subject Management Dashboard")
    st.caption("Customize your school's curriculum fields dynamically.")
    
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
        sub_to_edit = st.selectbox("Select Subject to Modify", st.session_state.subjects)
        
        edit_col1, edit_col2 = st.columns(2)
        with edit_col1:
            rename_val = st.text_input("Rename to:", value=sub_to_edit)
            if st.button("Rename Subject"):
                idx = st.session_state.subjects.index(sub_to_edit)
                st.session_state.subjects[idx] = rename_val.strip()
                if not df_quiz.empty:
                    df_quiz.loc[df_quiz["Subject"] == sub_to_edit, "Subject"] = rename_val.strip()
                    df_quiz.to_csv(DB_FILE, index=False)
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
            subject = st.selectbox("Subject", st.session_state.subjects)
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
            st.dataframe(st.session_state["temp_generated"], use_container_width=True)
            if st.button("💾 Save All Selected to Database"):
                df_quiz = pd.concat([df_quiz, st.session_state["temp_generated"]], ignore_index=True)
                df_quiz.to_csv(DB_FILE, index=False)
                st.success("Committed to database!")
                del st.session_state["temp_generated"]
    else:
        st.warning("Please configure your GROQ_API_KEY inside your Streamlit Secrets Panel.")

# --- MODULE 2: MANUAL INPUT ---
elif choice == "Manual Input":
    st.header("📝 Manual Question Entry")
    q_type = st.radio("Select Category", ["Multiple Choice (Objectives)", "Short Answer / Theory"], horizontal=True)
    with st.form("manual_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1: sub = st.selectbox("Subject", st.session_state.subjects)
        with col2: top = st.text_input("Topic")
        q_text = st.text_area("Question Text")
        opts_text = st.text_input("Options (Separated by commas, omitting labels)", placeholder="e.g. 20 Hz, 40 Hz, 60 Hz, 80 Hz") if q_type == "Multiple Choice (Objectives)" else ""
        ans_text = st.text_area("Correct Answer (Include label prefix if objective, e.g., A) 20 Hz)")
        if st.form_submit_button("Save Question"):
            new_row = {"Subject": sub, "Topic": top, "Type": q_type, "Question": q_text, "Options": opts_text, "Correct Answer": ans_text}
            df_quiz = pd.concat([df_quiz, pd.DataFrame([new_row])], ignore_index=True)
            df_quiz.to_csv(DB_FILE, index=False)
            st.success("Added successfully!")

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
        
        st.write("---")
        st.subheader("📚 Active Database Records")
        st.caption("💡 **To delete entries:** Check the **'Delete'** box next to any question, then click the red button at the bottom.")
        
        filtered.insert(0, "Delete", False)
        
        edited_df = st.data_editor(
            filtered,
            hide_index=False,
            use_container_width=True,
            disabled=["Subject", "Topic", "Type", "Question", "Options", "Correct Answer"]
        )
        
        indices_to_delete = edited_df[edited_df["Delete"] == True].index
        
        if len(indices_to_delete) > 0:
            st.write("")
            if st.button(f"🗑️ Permanent Delete Selected Questions ({len(indices_to_delete)})", type="primary"):
                df_quiz = df_quiz.drop(indices_to_delete).reset_index(drop=True)
                df_quiz.to_csv(DB_FILE, index=False)
                st.success("Selected records removed from database successfully!")
                st.rerun()
    else:
        st.info("The saved question vault is currently empty.")

# --- MODULE 4: LIVE COMPETITION MODE ---
elif choice == "Live Competition Mode":
    st.header("🎬 Grand Arena - Competition Screen")
    
    if not df_quiz.empty:
        if len(st.session_state.live_questions) == 0:
            st.subheader("Setup Inter-Subject Competition Round")
            
            chosen_type = st.radio("Select Competition Format for this Session", ["Multiple Choice (Objectives)", "Short Answer / Theory"], horizontal=True)
            
            st.write("---")
            st.subheader("⏱️ Timer Settings")
            timer_mode = st.radio("Select Timer Format:", ["No Timer", "Per Question", "Entire Session"], horizontal=True)
            
            timer_seconds = 60
            timer_minutes = 10
            
            if timer_mode == "Per Question":
                timer_seconds = st.number_input("Seconds allocated per question:", min_value=10, max_value=300, value=60, step=5)
            elif timer_mode == "Entire Session":
                timer_minutes = st.number_input("Total minutes allocated for the whole round:", min_value=1, max_value=180, value=10, step=1)
            
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
                        
                        # Save timer settings to session state
                        st.session_state.timer_mode = timer_mode
                        if timer_mode == "Per Question":
                            st.session_state.timer_seconds = timer_seconds
                        elif timer_mode == "Entire Session":
                            # Calculate the absolute end time in milliseconds
                            st.session_state.session_end_time_ms = int(time.time() * 1000) + (timer_minutes * 60 * 1000)
                            
                        st.rerun()
                    else:
                        st.error("Please allocate at least 1 question to start.")
            elif len(available_subjects) == 0:
                st.warning(f"There are no questions in the database categorized as '{chosen_type}' yet.")
        else:
            q_list = st.session_state.live_questions
            idx = st.session_state.current_q_index
            current_q = q_list[idx]
            
            # 1. QUIZ NUMBER SELECTOR
            st.markdown("### 🔢 Select Question Number:")
            q_labels = [f"Question {i+1} {'⭐ (Current)' if i == idx else ''}" for i in range(len(q_list))]
            chosen_q_label = st.selectbox("Jump to:", q_labels, index=idx, label_visibility="collapsed")
            new_idx = q_labels.index(chosen_q_label)
            
            if new_idx != idx:
                st.session_state.current_q_index = new_idx
                st.session_state.show_answer = False
                st.rerun()
            
            # 2. RESIZED AND TIGHTENED TIMER INJECTION
            current_mode = st.session_state.get("timer_mode", "No Timer")
            
            if current_mode == "Per Question":
                timer_html = f"""
                <div style="font-size: 24px; font-family: monospace; font-weight: bold; color: #ff4b4b; text-align: center; border: 2px solid #ff4b4b; border-radius: 8px; padding: 5px; margin: 0px; background-color: #fff1f0;">
                    <span id="timer_display_{idx}"></span>
                </div>
                <script>
                var timeLeft = {st.session_state.get('timer_seconds', 60)};
                var elem = document.getElementById('timer_display_{idx}');
                var timerId = setInterval(countdown, 1000);
                
                function countdown() {{
                    if (timeLeft <= 0) {{
                        clearTimeout(timerId);
                        elem.innerHTML = "🚨 TIME UP! 🚨";
                    }} else {{
                        elem.innerHTML = "⏱️ " + timeLeft + "s";
                        timeLeft--;
                    }}
                }}
                countdown();
                </script>
                """
                # Reduced height to 50
                components.html(timer_html, height=50)
                
            elif current_mode == "Entire Session":
                end_time_ms = st.session_state.get("session_end_time_ms", 0)
                timer_html = f"""
                <div style="font-size: 24px; font-family: monospace; font-weight: bold; color: #ff4b4b; text-align: center; border: 2px solid #ff4b4b; border-radius: 8px; padding: 5px; margin: 0px; background-color: #fff1f0;">
                    <span id="global_timer_display"></span>
                </div>
                <script>
                var endTime = {end_time_ms};
                var elem = document.getElementById('global_timer_display');
                
                function updateTimer() {{
                    var now = Date.now();
                    var timeLeft = Math.floor((endTime - now) / 1000);
                    
                    if (timeLeft <= 0) {{
                        elem.innerHTML = "🚨 SESSION TIME UP! 🚨";
                    }} else {{
                        var minutes = Math.floor(timeLeft / 60);
                        var seconds = timeLeft % 60;
                        var formattedTime = minutes + "m " + (seconds < 10 ? "0" : "") + seconds + "s";
                        elem.innerHTML = "⏱️ " + formattedTime;
                    }}
                }}
                updateTimer(); // run immediately
                setInterval(updateTimer, 1000);
                </script>
                """
                # Reduced height to 50
                components.html(timer_html, height=50)
            
            # Removed the st.write("---") here to kill the gap
            
            # 3. QUESTION CONTAINER 
            st.markdown(f"### 📍 Question Container {idx + 1} of {len(q_list)}")
            st.info(f"**Subject Category:** {current_q['Subject']} | **Topic Field:** {current_q['Topic']} | **Format:** {current_q['Type']}")
            
            st.subheader(str(current_q['Question']))
            
            if current_q['Type'] == "Multiple Choice (Objectives)" and pd.notna(current_q['Options']) and str(current_q['Options']).strip() != "":
                options_split = str(current_q['Options']).split(",")
                prefixes = ["A)", "B)", "C)", "D)", "E)"]
                
                for index, option in enumerate(options_split):
                    if index >= len(prefixes):
                        break
                        
                    clean_opt = option.strip()
                    if any(clean_opt.startswith(p) for p in prefixes):
                        st.markdown(f"**🔹 {clean_opt}**")
                    else:
                        pref = prefixes[index]
                        st.markdown(f"**🔹 {pref} {clean_opt}**")
            
            st.write("---")
            
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                if st.button("👁️ Show/Hide Answer", use_container_width=True):
                    st.session_state.show_answer = not st.session_state.show_answer
            with c2:
                if st.button("⬅️ Previous", use_container_width=True) and idx > 0:
                    st.session_state.current_q_index -= 1
                    st.session_state.show_answer = False
                    st.rerun()
            with c3:
                if st.button("➡️ Next", use_container_width=True) and idx < len(q_list) - 1:
                    st.session_state.current_q_index += 1
                    st.session_state.show_answer = False
                    st.rerun()
            with c4:
                if st.button("❌ Terminate Round", use_container_width=True):
                    st.session_state.live_questions = []
                    st.session_state.current_q_index = 0
                    st.session_state.show_answer = False
                    st.rerun()
            
            if st.session_state.show_answer:
                label = "Correct Option" if current_q['Type'] == "Multiple Choice (Objectives)" else "Expected Points/Rubric"
                st.success(f"**{label}:** {current_q['Correct Answer']}")
                
    else:
        st.info("The database is currently empty.")
