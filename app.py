import streamlit as st
import pandas as pd
import os
import json
import random
from google import genai
from google.genai import types

st.set_page_config(page_title="School Quiz Champion Pro", layout="wide", initial_sidebar_state="expanded")

DB_FILE = "quiz_database.csv"
SUBJECTS_FILE = "subjects_list.json"

# --- SYSTEM INITIALIZATION ---
if os.path.exists(DB_FILE):
    df_quiz = pd.read_csv(DB_FILE)
else:
    df_quiz = pd.DataFrame(columns=["Subject", "Topic", "Type", "Question", "Options", "Correct Answer"])

DEFAULT_SUBJECTS = ["Physics", "Chemistry", "Biology", "General Science", "P.H.E."]
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
        new_sub = st.text_input("Enter Subject Name", placeholder="e.g., Mathematics, Agricultural Science")
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
    
    # Reads the key automatically from the Secrets you just saved!
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
    else:
        api_key = None

    if api_key:
        client = genai.Client(api_key=api_key)
        col1, col2 = st.columns(2)
        with col1:
            subject = st.selectbox("Subject", st.session_state.subjects)
            q_type = st.radio("Select Question Category", ["Multiple Choice (Objectives)", "Short Answer / Theory"])
        with col2:
            topic = st.text_input("Topic / Area")
            num_q = st.slider("Number of Questions", 1, 10, 3)
            
        if st.button("✨ Auto-Generate Questions", type="primary"):
            with st.spinner("Drafting balanced numerical and theoretical questions..."):
                
                # --- STRONGER, CALCULATION-FOCUSED PROMPTS TRIDGERS ---
                if q_type == "Multiple Choice (Objectives)":
                    prompt = f"""
                    Generate {num_q} intermediate-to-hard secondary level Multiple Choice questions for {subject} on topic: '{topic}'.
                    CRITICAL DIRECTION: If the subject is Physics or Chemistry, ensure that at least half of the generated questions are word problems requiring numerical calculations, formulas, calculations, and proper scientific units.
                    Return STRICTLY as a JSON list of objects with keys: 'Question', 'Options', 'Correct Answer'. 
                    Options must be 4 choices separated by commas (e.g., "10 m/s, 20 m/s, 30 m/s, 40 m/s").
                    """
                else:
                    prompt = f"""
                    Generate {num_q} intermediate-to-hard secondary level Short Answer/Theory questions for {subject} on topic: '{topic}'.
                    CRITICAL DIRECTION: If the subject is Physics or Chemistry, ensure that the questions include calculation-based tasks where students must work out numerical problems using formulas.
                    Return STRICTLY as a JSON list of objects with keys: 'Question', 'Correct Answer'.
                    The 'Correct Answer' field should contain the final numerical answer with units and a brief mention of the formula/rubric step used.
                    """
                
                try:
                    response = client.models.generate_content(
                        model='gemini-2.5-flash', contents=prompt,
                        config=types.GenerateContentConfig(response_mime_type="application/json")
                    )
                    generated_data = json.loads(response.text)
                    new_qs = []
                    for q in generated_data:
                        new_qs.append({
                            "Subject": subject, "Topic": topic, "Type": q_type,
                            "Question": q["Question"], "Options": q.get("Options", ""), "Correct Answer": q["Correct Answer"]
                        })
                    st.session_state["temp_generated"] = pd.DataFrame(new_qs)
                    st.success("Done!")
                except Exception as e:
                    st.error(f"Error: {e}")
                    
        if "temp_generated" in st.session_state:
            st.dataframe(st.session_state["temp_generated"], use_container_width=True)
            if st.button("💾 Save All Selected to Database"):
                df_quiz = pd.concat([df_quiz, st.session_state["temp_generated"]], ignore_index=True)
                df_quiz.to_csv(DB_FILE, index=False)
                st.success("Committed to database!")
                del st.session_state["temp_generated"]
    else:
        st.warning("Please provide a Gemini API Key.")

# --- MODULE 2: MANUAL INPUT ---
elif choice == "Manual Input":
    st.header("📝 Manual Question Entry")
    q_type = st.radio("Select Category", ["Multiple Choice (Objectives)", "Short Answer / Theory"], horizontal=True)
    with st.form("manual_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1: sub = st.selectbox("Subject", st.session_state.subjects)
        with col2: top = st.text_input("Topic")
        q_text = st.text_area("Question Text")
        opts_text = st.text_input("Options (Separated by commas)") if q_type == "Multiple Choice (Objectives)" else ""
        ans_text = st.text_area("Correct Answer")
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
        with col1: sub_filter = st.multiselect("Filter by Subject", df_quiz["Subject"].unique())
        with col2: type_filter = st.multiselect("Filter by Category", df_quiz["Type"].unique())
        filtered = df_quiz
        if sub_filter: filtered = filtered[filtered["Subject"].isin(sub_filter)]
        if type_filter: filtered = filtered[filtered["Type"].isin(type_filter)]
        st.dataframe(filtered, use_container_width=True)
    else:
        st.info("No questions stored yet.")

# --- MODULE 4: LIVE COMPETITION MODE (STRICT TYPE ENFORCEMENT) ---
elif choice == "Live Competition Mode":
    st.header("🎬 Grand Arena - Competition Screen")
    
    if not df_quiz.empty:
        if len(st.session_state.live_questions) == 0:
            st.subheader("Setup Inter-Subject Competition Round")
            
            # 1. Choose Round Format First (Strict Enforcement)
            chosen_type = st.radio("Select Competition Format for this Session", ["Multiple Choice (Objectives)", "Short Answer / Theory"], horizontal=True)
            st.write("---")
            
            # Filter main database by selected type immediately
            type_filtered_pool = df_quiz[df_quiz["Type"] == chosen_type]
            
            # 2. Multi-Subject Selection based on available subjects for that type
            available_subjects = type_filtered_pool["Subject"].unique()
            chosen_subjects = st.multiselect("Select Subjects to include in this round", available_subjects)
            
            if chosen_subjects:
                st.write(f"🔧 Set Question Quantities per Subject ({chosen_type} only):")
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
                        st.rerun()
                    else:
                        st.error("Please allocate at least 1 question to start.")
            elif len(available_subjects) == 0:
                st.warning(f"There are no questions in the database categorized as '{chosen_type}' yet.")
        else:
            q_list = st.session_state.live_questions
            idx = st.session_state.current_q_index
            current_q = q_list[idx]
            
            st.markdown("### 🔢 Choose / Jump to Question Number:")
            grid_cols = st.columns(10) 
            for i in range(len(q_list)):
                col_target = grid_cols[i % 10]
                btn_label = f"⭐ {i+1}" if i == idx else f"{i+1}"
                if col_target.button(btn_label, key=f"nav_btn_{i}", use_container_width=True):
                    st.session_state.current_q_index = i
                    st.session_state.show_answer = False
                    st.rerun()
            
            st.write("---")
            
            st.markdown(f"### 📍 Question Container {idx + 1} of {len(q_list)}")
            st.info(f"**Subject Category:** {current_q['Subject']} | **Topic Field:** {current_q['Topic']} | **Format:** {current_q['Type']}")
            
            st.subheader(str(current_q['Question']))
            
            if current_q['Type'] == "Multiple Choice (Objectives)" and pd.notna(current_q['Options']) and str(current_q['Options']).strip() != "":
                options_split = str(current_q['Options']).split(",")
                for option in options_split:
                    st.markdown(f"**🔹 {option.strip()}**")
            
            st.write("---")
            
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                if st.button("👁️ Show/Hide Answer"):
                    st.session_state.show_answer = not st.session_state.show_answer
            with c2:
                if st.button("⬅️ Previous") and idx > 0:
                    st.session_state.current_q_index -= 1
                    st.session_state.show_answer = False
                    st.rerun()
            with c3:
                if st.button("➡️ Next") and idx < len(q_list) - 1:
                    st.session_state.current_q_index += 1
                    st.session_state.show_answer = False
                    st.rerun()
            with c4:
                if st.button("❌ Terminate Round"):
                    st.session_state.live_questions = []
                    st.session_state.current_q_index = 0
                    st.session_state.show_answer = False
                    st.rerun()
            
            if st.session_state.show_answer:
                label = "Correct Option" if current_q['Type'] == "Multiple Choice (Objectives)" else "Expected Points/Rubric"
                st.success(f"**{label}:** {current_q['Correct Answer']}")
                
    else:
        st.info("The database is currently empty.")
