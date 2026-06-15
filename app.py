import streamlit as st
import requests
import pandas as pd

API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="FootballDB", layout="wide", page_icon="⚽")
st.title("⚽ FootballDB")

@st.cache_data(ttl=300)
def get_league_data(league_code):
    try:
        res = requests.get(f"{API_URL}/standings/{league_code}")
        if res.status_code == 200:
            return res.json()
    except requests.exceptions.ConnectionError:
        return None
    return None

menu = ["Live Standings", "Admin Panel"]
choice = st.sidebar.selectbox("Navigation", menu)

if choice == "Live Standings":
    st.header("📊 European League Standings")
    
    try:
        db_teams_res = requests.get(f"{API_URL}/teams")
        internal_teams = db_teams_res.json() if db_teams_res.status_code == 200 else []
    except requests.exceptions.ConnectionError:
        st.error("Backend server offline. Please start your FastAPI server.")
        internal_teams = []
    
    leagues = {
        "Champions League": "CL",
        "Premier League": "PL",
        "La Liga": "PD",
        "Serie A": "SA",
        "Bundesliga": "BL1",
        "Ligue 1": "FL1"
    }
    
    tabs = st.tabs(list(leagues.keys()))
    
    for tab, (league_name, league_code) in zip(tabs, leagues.items()):
        with tab:
            st.subheader(f"{league_name} Table")
            
            with st.spinner(f"Fetching live data for {league_name}..."):
                standings_data = get_league_data(league_code)
                
            if standings_data:
                df = pd.DataFrame(standings_data)
                st.dataframe(df, use_container_width=True, hide_index=True)
                
                st.markdown("---")
                st.subheader("🔎 Team Spotlight")
                
                club_list = df["Club"].tolist()
                selected_club = st.selectbox(
                    f"Select a club to view their roster:", 
                    club_list, 
                    key=f"select_{league_code}"
                )
                
                matched_team = next((t for t in internal_teams if t["name"] == selected_club), None)
                
                if matched_team:
                    if matched_team.get("players"):
                        st.success(f"Found {len(matched_team['players'])} players in database.")
                        
                        p_cols = st.columns(4)
                        for idx, player in enumerate(matched_team["players"]):
                            with p_cols[idx % 4]:
                                st.markdown(f"**{player['name']}** \n*{player['position']}*")
                    else:
                        st.warning(f"We have {selected_club} in the database, but their squad list is empty. Run a Player Sync in the Admin Panel.")
                else:
                    st.info(f"{selected_club} is not in your PostgreSQL database yet. Go to the Admin Panel and sync the {league_code} players!")

            else:
                st.error("Failed to load data. Rate limit reached. Wait a minute and refresh.")

elif choice == "Admin Panel":
    st.header("🔒 Admin Portal")
    
    if "token" not in st.session_state:
        st.session_state["token"] = None

    if not st.session_state["token"]:
        with st.form("login_form"):
            st.subheader("Login to Access Protected Actions")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")
            
            if submitted:
                res = requests.post(f"{API_URL}/login", data={"username": username, "password": password})
                if res.status_code == 200:
                    st.session_state["token"] = res.json()["access_token"]
                    st.success("Logged in successfully!")
                    st.rerun()
                else:
                    st.error("Invalid credentials.")
    else:
        col1, col2 = st.columns([0.8, 0.2])
        col1.write("Authentication Active. You have admin privileges.")
        if col2.button("Logout"):
            st.session_state["token"] = None
            st.rerun()
            
        st.write("---")
        st.subheader("Database Synchronization")
        st.write("Use these controls to pull live data from the sports API into your PostgreSQL database.")
        
        sync_league = st.text_input("League Code to Sync (e.g., PL, PD, CL)", value="PL")
        
        c1, c2 = st.columns(2)
        if c1.button("Sync Players"):
            headers = {"Authorization": f"Bearer {st.session_state['token']}"}
            with st.spinner(f"Syncing players for {sync_league}..."):
                res = requests.post(f"{API_URL}/sync/players?league_code={sync_league}", headers=headers)
                if res.status_code == 200:
                    st.success(res.json().get("message"))
                else:
                    st.error(f"Error: {res.json().get('detail')}")
                
        if c2.button("Sync Matches"):
            headers = {"Authorization": f"Bearer {st.session_state['token']}"}
            with st.spinner(f"Syncing matches for {sync_league}..."):
                res = requests.post(f"{API_URL}/sync/matches?league_code={sync_league}", headers=headers)
                if res.status_code == 200:
                    st.success(res.json().get("message"))
                else:
                    st.error(f"Error: {res.json().get('detail')}")