import streamlit as st
import random
import sqlite3
import hashlib
import os
from datetime import datetime, timedelta

# ==========================================
# 0. AUTOMATIC DATABASE SELF-HEALING
# ==========================================
DB_FILE = "smart_planner.db"
if os.path.exists(DB_FILE):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(users);")
        columns = [col[1] for col in cursor.fetchall()]
        conn.close()
        if columns and "username" in columns:
            os.remove(DB_FILE)
    except Exception:
        pass

# ==========================================
# 1. DATABASE MANAGEMENT LAYER (SQLite)
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            password TEXT,
            first_name TEXT,
            last_name TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            name TEXT,
            difficulty INTEGER,
            hours INTEGER,
            days_left INTEGER,
            trait TEXT,
            FOREIGN KEY(email) REFERENCES users(email)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            rating INTEGER,
            comment TEXT,
            submitted_at TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_user(email, password):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    hashed_pw = make_hashes(password)
    cursor.execute("SELECT first_name, last_name, email FROM users WHERE email = ? AND password = ?", (email, hashed_pw))
    data = cursor.fetchone()
    conn.close()
    return data

def add_user(email, password, first_name, last_name):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    hashed_pw = make_hashes(password)
    try:
        cursor.execute("INSERT INTO users(email, password, first_name, last_name) VALUES (?,?,?,?)", 
                       (email, hashed_pw, first_name, last_name))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False  
    conn.close()
    return success

# ==========================================
# 2. LOCAL SEARCH HEURISTIC CORE (AI Engine)
# ==========================================
class StudyTask:
    def __init__(self, name, difficulty, hours_needed, days_left, trait):
        self.name = name
        self.difficulty = difficulty      
        self.hours_needed = hours_needed  
        self.days_left = days_left        
        self.trait = trait 

class StudyDay:
    def __init__(self, day_number, date_string, max_hours=6):
        self.day_number = day_number
        self.date_string = date_string  
        self.max_hours = max_hours
        self.slots = {} 
        self.total_assigned_hours = 0

    def add_study_hours(self, task_name, hours):
        if task_name in self.slots:
            self.slots[task_name] += hours
        else:
            self.slots[task_name] = hours
        self.total_assigned_hours += hours

def calculate_schedule_cost(current_timeline, all_tasks):
    penalty = 0
    task_map = {t.name: t for t in all_tasks}
    
    for day in current_timeline:
        if day.total_assigned_hours > day.max_hours:
            excess = day.total_assigned_hours - day.max_hours
            penalty += (excess ** 2) * 25  
            
        heavy_count = 0
        for task_name, hours in day.slots.items():
            if hours <= 0: continue
            task = task_map[task_name]
            if task.trait == "Brain Melter" or task.difficulty >= 4:
                heavy_count += 1
            if task.trait == "Procrastination Risk" and day.day_number > 2:
                penalty += 35 

        if heavy_count > 1:
            penalty += 60
            
    return penalty

def optimize_schedule(all_tasks, total_days=4, max_daily_hours=6):
    current_timeline = []
    today = datetime.now()
    for i in range(1, total_days + 1):
        future_date = today + timedelta(days=i-1)
        current_timeline.append(StudyDay(day_number=i, date_string=future_date.strftime("%A, %b %d"), max_hours=max_daily_hours))
    
    if not all_tasks: return current_timeline

    for task in all_tasks:
        hours_left = task.hours_needed
        for day in current_timeline:
            if day.day_number <= task.days_left and hours_left > 0:
                space_left = max(0, day.max_hours - day.total_assigned_hours)
                if space_left > 0:
                    allocated = min(hours_left, space_left)
                    day.add_study_hours(task.name, allocated)
                    hours_left -= allocated

    for _ in range(20000):
        current_score = calculate_schedule_cost(current_timeline, all_tasks)
        random_task = random.choice(all_tasks)
        
        possible_src = [d for d in current_timeline if random_task.name in d.slots and d.slots[random_task.name] > 0]
        possible_tgt = [d for d in current_timeline if d.day_number <= random_task.days_left]
        
        if not possible_src or len(possible_tgt) < 2: continue
        from_day = random.choice(possible_src)
        to_day = random.choice([d for d in possible_tgt if d.day_number != from_day.day_number])
        
        from_day.slots[random_task.name] -= 1
        from_day.total_assigned_hours -= 1
        to_day.slots[random_task.name] = to_day.slots.get(random_task.name, 0) + 1
        to_day.total_assigned_hours += 1
        
        if calculate_schedule_cost(current_timeline, all_tasks) > current_score:
            from_day.slots[random_task.name] += 1
            from_day.total_assigned_hours += 1
            to_day.slots[random_task.name] -= 1
            to_day.total_assigned_hours -= 1
                
    return current_timeline

# ==========================================
# 3. STREAMLIT FRONTEND USER INTERFACE
# ==========================================
st.set_page_config(page_title="AI Study Planner", page_icon="🧠", layout="wide")

if "user_profile" not in st.session_state:
    st.session_state.user_profile = None

# --- SIMPLIFIED LOGIN & SIGNUP RE-DESIGN ---
if st.session_state.user_profile is None:
    st.markdown("<h1 style='text-align: center; color: #4A90E2;'>🧠 AI Smart Study Planner</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Organize your studies, avoid burnout, and plan your schedule automatically.</p>", unsafe_allow_html=True)
    
    auth_col1, auth_col2, auth_col3 = st.columns([1, 2, 1])
    
    with auth_col2:
        auth_mode = st.tabs(["🔐 Log In", "📝 Sign Up"])
        
        # 1. TAB: LOG IN
        with auth_mode[0]:
            with st.form("login_form"):
                login_email = st.text_input("Email Address", placeholder="e.g., student@university.edu").strip().lower()
                login_pass = st.text_input("Password", type="password", placeholder="••••••••")
                
                login_btn = st.form_submit_button("Log In", use_container_width=True)
                
                if login_btn and login_email and login_pass:
                    user_meta = check_user(login_email, login_pass)
                    if user_meta:
                        st.session_state.user_profile = {
                            "first_name": user_meta[0],
                            "last_name": user_meta[1],
                            "email": user_meta[2]
                        }
                        st.balloons() 
                        st.success(f"Welcome back, {user_meta[0]}!")
                        st.rerun()
                    else:
                        st.error("Incorrect email or password. Please try again.")
                        
        # 2. TAB: SIGN UP
        with auth_mode[1]:
            with st.form("signup_form"):
                reg_email = st.text_input("Email Address *", placeholder="e.g., student@university.edu").strip().lower()
                reg_pass = st.text_input("Create Password *", type="password", placeholder="Choose a strong password")
                
                col_a, col_b = st.columns(2)
                first_name = col_a.text_input("First Name *")
                last_name = col_b.text_input("Last Name *")
                
                signup_btn = st.form_submit_button("Create Account", use_container_width=True)
                
                if signup_btn:
                    if not (reg_email and reg_pass and first_name and last_name):
                        st.error("Please fill in all fields marked with an asterisk (*).")
                    elif add_user(reg_email, reg_pass, first_name, last_name):
                        st.toast("Account created successfully! 🎉")
                        st.success("Your account is ready! Now, please click the 'Log In' tab above to sign in.")
                    else:
                        st.error("This email address is already registered.")
    st.stop()

# --- AUTHENTICATED RUNTIME ENVIRONMENT ---
profile = st.session_state.user_profile
user_email = profile["email"]

# Sidebar Profile Header
st.sidebar.markdown(f"<div style='background-color:#1E1E1E; padding:15px; border-radius:10px; margin-bottom:15px;'>"
                    f"<h3 style='margin:0; color:#4A90E2;'>👋 Hello,</h3>"
                    f"<p style='margin:5px 0; font-size:16px; font-weight:bold;'>{profile['first_name']} {profile['last_name']}</p>"
                    f"<p style='margin:0; font-size:12px; color:#888;'>{user_email}</p>"
                    f"</div>", unsafe_allow_html=True)

if st.sidebar.button("Log Out", type="secondary", use_container_width=True):
    st.session_state.user_profile = None
    st.rerun()

st.sidebar.write("---")
st.sidebar.subheader("⚙️ Planner Settings")
user_max_hours = st.sidebar.slider("Daily Study Limit (Max Hours)", 2, 10, 6)
timeline_range = st.sidebar.slider("Planning Range (Days Ahead)", 3, 7, 5)

# Sidebar Feedback Portal
st.sidebar.write("---")
st.sidebar.subheader("📣 Share Feedback")
with st.sidebar.form("feedback_form", clear_on_submit=True):
    rating = st.slider("Rate your experience (1-5 ⭐)", 1, 5, 5)
    comment = st.text_area("What features should we add or fix next?", placeholder="Tell us your suggestions...")
    feedback_submit = st.form_submit_button("Submit Feedback")
    
    if feedback_submit and comment:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO feedback(email, rating, comment, submitted_at) VALUES(?,?,?,?)",
                       (user_email, rating, comment, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
        st.sidebar.success("Thank you for your feedback!")

# Main Application Title Dashboard
st.title("🧠 Your Personalized Study Dashboard")
st.markdown("Add your upcoming exam topics or assignments below, and let the AI find the healthiest daily study path.")
st.write("---")

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("📥 Add a New Subject")
    with st.form("task_form", clear_on_submit=True):
        name = st.text_input("Subject Title", placeholder="e.g., Data Structures")
        difficulty = st.slider("Difficulty Level (1 = Easy, 5 = Hard)", 1, 5, 3)
        hours = st.number_input("Total Study Time Needed (Hours)", min_value=1, max_value=40, value=6)
        days_left = st.number_input("Days Left Until Deadline", min_value=1, max_value=int(timeline_range), value=3)
        
        trait = st.selectbox("How do you feel about this subject?", [
            "Normal Core Subject",
            "Brain Melter (Causes high mental burnout/fatigue)",
            "Procrastination Risk (You constantly keep putting it off)",
            "Reading Heavy (Requires passive conceptual retention)"
        ])
        
        submit = st.form_submit_button("Save Subject", use_container_width=True)
        
        if submit and name:
            clean_trait = trait.split(" (")[0]
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO tasks(email, name, difficulty, hours, days_left, trait) VALUES(?,?,?,?,?,?)",
                           (user_email, name, difficulty, hours, days_left, clean_trait))
            conn.commit()
            conn.close()
            st.success(f"Successfully saved {name}!")
            st.rerun()

with col2:
    st.subheader("📋 Your Saved Subjects")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, difficulty, hours, days_left, trait FROM tasks WHERE email=?", (user_email,))
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        st.info("No subjects added yet. Use the left panel to register your workload.")
    else:
        total_workload_hours = sum(r[3] for r in rows)
        
        metric_col1, metric_col2 = st.columns(2)
        metric_col1.metric("Total Subjects Registered", f"{len(rows)} Courses")
        metric_col2.metric("Total Study Hours Needed", f"{total_workload_hours} Hours")
        
        display_list = [{"ID": r[0], "Subject Title": r[1], "Difficulty ⭐": r[2], "Study Hours ⏱️": r[3], "Days Left 📅": r[4], "Subject Category": r[5]} for r in rows]
        st.dataframe(display_list, use_container_width=True)
        
        del_col1, del_col2 = st.columns([2, 1])
        del_id = del_col1.number_input("Enter ID number to delete", min_value=1, step=1)
        if del_col2.button("🗑️ Delete Subject", use_container_width=True):
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM tasks WHERE id=? AND email=?", (del_id, user_email))
            conn.commit()
            conn.close()
            st.toast("Subject deleted successfully.")
            st.rerun()

st.write("---")

# --- AI SCHEDULER MATRIX ENGINE GENERATION ---
if rows:
    if st.button("🚀 GENERATE MY OPTIMIZED STUDY PLAN", type="primary", use_container_width=True):
        ai_tasks_input = [StudyTask(r[1], r[2], r[3], r[4], r[5]) for r in rows]
        
        with st.spinner("AI is calculating the best daily breakdown to minimize your mental fatigue..."):
            optimized_timeline = optimize_schedule(ai_tasks_input, total_days=timeline_range, max_daily_hours=user_max_hours)
            final_pain_score = calculate_schedule_cost(optimized_timeline, ai_tasks_input)
            
        st.success(f"🎉 Optimized Plan Computed Successfully!")
        
        st.subheader("📅 Your Balanced Study Calendar")
        grid_cols = st.columns(len(optimized_timeline))
        
        for idx, day in enumerate(optimized_timeline):
            with grid_cols[idx]:
                if day.total_assigned_hours > user_max_hours:
                    st.error(f"🔴 {day.date_string}")
                elif day.total_assigned_hours >= (user_max_hours - 2):
                    st.warning(f"🟡 {day.date_string}")
                else:
                    st.success(f"🟢 {day.date_string}")
                
                st.metric(label="Study Load", value=f"{day.total_assigned_hours}/{user_max_hours} hrs")
                
                active_blocks = {task: hrs for task, hrs in day.slots.items() if hrs > 0}
                if not active_blocks:
                    st.caption("✨ Open Window / Rest Day")
                else:
                    for t_name, t_hours in active_blocks.items():
                        st.markdown(f"📖 **{t_name}**: `{t_hours} hrs`")
                st.write("---")

# --- TRULY HIDDEN ADMIN VIEW (VIA URL PARAMETER) ---
query_params = st.query_params
if "admin" in query_params and query_params["admin"] == "secretkey123":
    st.write("---")
    st.subheader("🛠️ Hidden Admin Panel")
    st.caption("Only you can see this section using your private key parameter link.")
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, email, rating, comment, submitted_at FROM feedback ORDER BY id DESC")
    feedback_rows = cursor.fetchall()
    conn.close()
    
    if not feedback_rows:
        st.info("No feedback submissions found in the database.")
    else:
        feedback_list = [
            {"Feedback ID": f[0], "User Email": f[1], "Rating ⭐": f[2], "Comment": f[3], "Date Submitted 📅": f[4]} 
            for f in feedback_rows
        ]
        st.dataframe(feedback_list, use_container_width=True)