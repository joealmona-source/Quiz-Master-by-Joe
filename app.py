import streamlit as st
import pandas as pd
import os
import json
from google import genai
from google.genai import types

# Page Setup
st.set_page_config(page_title="School Quiz Champion Pro", layout="wide", initial_sidebar_state="expanded")

DB_FILE = "quiz_database.csv"

# Initialize local database
if os.path.exists(DB_FILE):
    df_quiz = pd.read_csv(DB_FILE)
else:
    df_quiz = pd.DataFrame(columns=["Subject", "Topic", "Type", "Question", "Options", "Correct Answer"])

# Initialize session state tracking for Live Competitions
if "live_questions" not in st.session_state:
    st.session_state.live_questions = []
if "current_q_index" not in st.session_state:
    st.session_state.current_q_index = 0
if "show_answer" not in st.session_state:
    st.session_state.show_answer = False

# Sidebar App Control Layout
st.sidebar.title("🏆 Quiz Control Panel")
menu = ["AI Question Generator", "Manual Input", "View Quiz Bank", "Live Competition Mode"]
choice = st.sidebar.selectbox("Go to Module", menu)

# --- MODULE 1: AI QUESTION GENERATOR ---
if choice == "AI Question Generator":
    st.header("🤖 AI-Assisted Question Generator")
    
    api_key = st.text_input("Enter Gemini API Key", type="password", help="Get a key from Google AI Studio")
    
    if api_key:
        client = genai.Client(api_key=api_key)
        
        col1, col2 = st.columns(2)
        with col1:
            subject = st.selectbox("Subject", ["Physics", "Chemistry", "Biology", "General Science", "P.H.E."])
            q_type = st.radio("Select Question Category", ["Multiple Choice (Objectives)", "Short Answer / Theory"])
        with col2:
            topic = st.text_input("Topic / Area", placeholder="e.g., Kinetic Theory, Linear Momentum")
            num_q = st.slider("Number of Questions", 1, 10, 3)
            
        if st.button("✨ Auto-Generate Questions", type="primary"):
            with st.spinner("Drafting curriculum-aligned questions..."):
                
                if q_type == "Multiple Choice (Objectives)":
                    prompt = f"""
                    Generate {num_q} intermediate-to-hard secondary school level Multiple Choice questions for {subject} on the topic: '{topic}'.
                    Return the response STRICTLY as a JSON list of objects, with no markdown formatting around it. Each object must have these exact keys:
                    "Question", "Options", "Correct Answer"
                    The "Options" key must be a single string containing exactly 4 options separated by commas (e.g., "Option A, Option B, Option C, Option D").
                    """
                else:
                    prompt = f"""
                    Generate {num_q} intermediate-to-hard secondary school level Short Answer/Theory questions for {subject} on the topic: '{topic}'.
                    Return the response STRICTLY as a JSON list of objects, with no markdown formatting around it. Each object must have these exact keys:
                    "Question", "Correct Answer"
                    The "Correct Answer" should contain the ideal grading answer/marking rubric key phrases. Leave the options field blank.
                    """
                
                try:
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt,
                        config=types.GenerateContentConfig(response_mime_type="application/json")
                    )
                    
                    generated_data = json.loads(response.text)
                    new_qs = []
                    
                    for q in generated_data:
                        new_qs.append({
                            "Subject": subject,
                            "Topic": topic,
                            "Type": q_type,
                            "Question": q["Question"],
                            "Options": q.get("Options", ""), 
                            "Correct Answer": q["Correct Answer"]
                        })
                    
                    st.session_state["temp_generated"] = pd.DataFrame(new_qs)
                    st.success(f"Generated {len(st.session_state['temp_generated'])} {q_type} questions!")
                    
                except Exception as e:
                    st.error(f"Error generating questions: {e}")
                    
        if "temp_generated" in st.session_state:
            st.subheader("Preview Generated Questions")
            st.dataframe(st.session_state["temp_generated"], use_container_width=True)
            if st.button("💾 Save All Selected to Database"):
                df_quiz = pd.concat([df_quiz, st.session_state["temp_generated"]], ignore_index=True)
                df_quiz.to_csv(DB_FILE, index=False)
                st.success("All questions committed to the master database!")
                del st.session_state["temp_generated"]
    else:
        st.warning("Please provide a Gemini API Key to unlock the automated generation panel.")

# --- MODULE 2: MANUAL INPUT ---
elif choice == "Manual Input":
    st.header("📝 Manual Question Entry")
    
    q_type = st.radio("Select Category to Create", ["Multiple Choice (Objectives)", "Short Answer / Theory"], horizontal=True)
    st.write("---")
    
    with st.form("manual_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            sub = st.selectbox("Subject", ["Physics", "Chemistry", "Biology", "General Science", "P.H.E."])
        with col2:
            top = st.text_input("Topic")
            
        q_text = st.text_area("Question Text")
        
        if q_type == "Multiple Choice (Objectives)":
            opts_text = st.text_input("Options (Separated by commas)", placeholder="Option A, Option B, Option C, Option D")
            ans_text = st.text_input("Correct Answer (Exact text match or Letter choice)")
        else:
            opts_text = ""
            ans_text = st.text_area("Ideal Short Answer Response / Marking Rubric Hint")
        
        if st.form_submit_button("Save Question"):
            if q_text and ans_text:
                new_row = {"Subject": sub, "Topic": top, "Type": q_type, "Question": q_text, "Options": opts_text, "Correct Answer": ans_text}
                df_quiz = pd.concat([df_quiz, pd.DataFrame([new_row])], ignore_index=True)
                df_quiz.to_csv(DB_FILE, index=False)
                st.success(f"Successfully added {q_type} question!")
            else:
                st.error("Question and Answer fields cannot be left empty.")

# --- MODULE 3: VIEW QUIZ BANK ---
elif choice == "View Quiz Bank":
    st.header("🗂️ Stored Questions Vault")
    if not df_quiz.empty:
        col1, col2 = st.columns(2)
        with col1:
            sub_filter = st.multiselect("Filter by Subject", df_quiz["Subject"].unique())
        with col2:
            type_filter = st.multiselect("Filter by Category", df_quiz["Type"].unique())
            
        filtered = df_quiz
        if sub_filter:
            filtered = filtered[filtered["Subject"].isin(sub_filter)]
        if type_filter:
            filtered = filtered[filtered["Type"].isin(type_filter)]
            
        st.dataframe(filtered, use_container_width=True)
        
        csv = filtered.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Export Current Selection (CSV)", csv, "exported_questions.csv", "text/csv")
    else:
        st.info("No questions stored yet.")

# --- MODULE 4: LIVE COMPETITION MODE ---
elif choice == "Live Competition Mode":
    st.header("🎬 Live Projector View")
    
    if not df_quiz.empty:
        if len(st.session_state.live_questions) == 0:
            st.subheader("Setup the Competition Round")
            col1, col2, col3 = st.columns(3)
            with col1:
                sel_sub = st.selectbox("Select Subject", df_quiz["Subject"].unique())
            with col2:
                sel_type = st.selectbox("Select Category", df_quiz["Type"].unique())
            with col3:
                pool = df_quiz[(df_quiz["Subject"] == sel_sub) & (df_quiz["Type"] == sel_type)]
                total_avail = len(pool)
                num_to_pull = st.number_input("Number of Questions", min_value=1, max_value=max(1, total_avail), value=min(5, max(1, total_avail)))
            
            if total_avail == 0:
                st.warning(f"No questions available in the database matching {sel_sub} - {sel_type}.")
            elif st.button("🚀 Load and Start Live Competition", type="primary"):
                st.session_state.live_questions = pool.sample(n=int(num_to_pull)).to_dict(orient="records")
                st.session_state.current_q_index = 0
                st.session_state.show_answer = False
                st.rerun()
        else:
            q_list = st.session_state.live_questions
            idx = st.session_state.current_q_index
            current_q = q_list[idx]
            
            st.markdown(f"### 📍 Question {idx + 1} of {len(q_list)} ({current_q['Type']})")
            st.info(f"**Subject:** {current_q['Subject']} | **Topic:** {current_q['Topic']}")
            
            st.markdown(f"<div style='font-size:24px; font-weight:bold; background-color:#1e293b; padding:20px; border-radius:10px; margin-bottom:20px;'>{current_q['Question']}</div>", unsafe_allowed_html=True)
            
            if current_q['Type'] == "Multiple Choice (Objectives)" and pd.notna(current_q['Options']) and current_q['Options'].strip() != "":
                options_split = current_q['Options'].split(",")
                for option in options_split:
                    st.markdown(f"<div style='font-size:18px; margin-left:20px; padding:5px;'>🔹 {option.strip()}</div>", unsafe_allowed_html=True)
            elif current_q['Type'] == "Short Answer / Theory":
                st.caption("_📝 Contestants should write down or verbally provide a short analytical response._")
            
            st.write("---")
            
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                if st.button("👁️ Show/Hide Answer"):
                    st.session_state.show_answer = not st.session_state.show_answer
            with c2:
                if st.button("⬅️ Previous Question") and idx > 0:
                    st.session_state.current_q_index -= 1
                    st.session_state.show_answer = False
                    st.rerun()
            with c3:
                if st.button("➡️ Next Question") and idx < len(q_list) - 1:
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
                st.markdown(f"<div style='font-size:22px; font-weight:bold; color:#10b981; background-color:#064e3b; padding:15px; border-radius:8px; text-align:center;'>✅ {label}: {current_q['Correct Answer']}</div>", unsafe_allowed_html=True)
                
    else:
        st.info("The database is currently empty. Please add or generate questions before running a competition.")
