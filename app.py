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
        if res.status_code == 200: return res.json()
    except requests.exceptions.ConnectionError: return None
    return None

@st.cache_data(ttl=60)
def get_live_games():
    try:
        res = requests.get(f"{API_URL}/live")
        if res.status_code == 200: return res.json()
    except: return []
    return []

menu = ["Live Standings", "Admin Panel"]
choice = st.sidebar.selectbox("Navigation", menu)

if choice == "Live Standings":
    st.subheader("🔴 LIVE")
    live_matches = get_live_games()
    
    col1, col2 = st.columns([0.8, 0.2])
    with col2:
        if st.button("🔄"):
            get_live_games.clear()
            st.rerun()
            
    if live_matches:
        game_cols = st.columns(min(len(live_matches), 4))
        for idx, game in enumerate(live_matches):
            with game_cols[idx % 4]:
                st.info(f"🏆 **{game['league']}**\n\n"
                        f"**{game['home_team']}** `{game['home_score']} - {game['away_score']}` **{game['away_team']}**\n\n"
                        f"{game['status']}")
    else:
        st.caption("No matches are currently in play right now.")
        
    st.markdown("---")

    st.header("📊 European League Standings")
    
    try:
        db_teams_res = requests.get(f"{API_URL}/teams")
        internal_teams = db_teams_res.json() if db_teams_res.status_code == 200 else []
    except:
        internal_teams = []
    
    leagues = {"Champions League": "CL", "Premier League": "PL", "La Liga": "PD", "Serie A": "SA", "Bundesliga": "BL1", "Ligue 1": "FL1"}
    tabs = st.tabs(list(leagues.keys()))
    
    for tab, (league_name, league_code) in zip(tabs, leagues.items()):
        with tab:
            st.subheader(f"{league_name} Table")
            standings_data = get_league_data(league_code)
                
            if standings_data:
                df = pd.DataFrame(standings_data)
                st.dataframe(df, use_container_width=True, hide_index=True)
                
                st.markdown("---")
                st.subheader("Teams")
                
                club_list = df["Club"].tolist()
                selected_club = st.selectbox(f"Select a club:", club_list, key=f"select_{league_code}")
                matched_team = next((t for t in internal_teams if t["name"] == selected_club), None)
                
                if matched_team:
                    profile_col1, profile_col2 = st.columns([1, 4])
                    with profile_col1:
                        if matched_team.get("crest_url"): st.image(matched_team["crest_url"], width=120)
                    with profile_col2:
                        st.subheader(matched_team["name"])
                        st.write(f"**Manager:** {matched_team.get('manager') or 'Unknown'}")
                        st.caption(f"Club Code: {matched_team['code']}")
                    
                    st.markdown("---")
                    if matched_team.get("players"):
                        st.success(f"Squad List ({len(matched_team['players'])} players)")
                        p_cols = st.columns(4)
                        for idx, player in enumerate(matched_team["players"]):
                            with p_cols[idx % 4]:
                                st.markdown(f"**{player['name']}** \n*{player['position']}*")
                    else: st.warning("Squad list is empty. Run a Player Sync.")
                else: st.info(f"{selected_club} is not in your database yet. Sync the {league_code} players!")
            else: st.error("Failed to load data. Rate limit reached. Wait a minute and refresh.")

elif choice == "Admin Panel":
    st.header("🔒 Admin Portal")
    if "token" not in st.session_state: st.session_state["token"] = None

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
                else: st.error("Invalid credentials.")
    else:
        col1, col2 = st.columns([0.8, 0.2])
        col1.write("Authentication Active. You have admin privileges.")
        if col2.button("Logout"):
            st.session_state["token"] = None
            st.rerun()
            
        st.write("---")
        st.subheader("Database Synchronization")
        sync_league = st.text_input("League Code to Sync (e.g., PL, PD, CL)", value="PL")
        
        c1, c2 = st.columns(2)
        if c1.button("Sync Players & Profiles"):
            headers = {"Authorization": f"Bearer {st.session_state['token']}"}
            with st.spinner(f"Syncing players and profiles for {sync_league}..."):
                res = requests.post(f"{API_URL}/sync/players?league_code={sync_league}", headers=headers)
                if res.status_code == 200: st.success(res.json().get("message"))
                else: st.error(f"Error: {res.json().get('detail')}")
                
        if c2.button("Sync Matches"):
            headers = {"Authorization": f"Bearer {st.session_state['token']}"}
            with st.spinner(f"Syncing matches for {sync_league}..."):
                res = requests.post(f"{API_URL}/sync/matches?league_code={sync_league}", headers=headers)
                if res.status_code == 200: st.success(res.json().get("message"))
                else: st.error(f"Error: {res.json().get('detail')}")