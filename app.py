import streamlit as st
import requests

API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="FootballDB", layout="wide")
st.title("FootballDB")

menu = ["Public Dashboard", "Admin Panel"]
choice = st.sidebar.selectbox("Navigation", menu)

if choice == "Public Dashboard":
    st.header("Current Standings & Match Results")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Registered Teams")
        try:
            teams_res = requests.get(f"{API_URL}/teams")
            if teams_res.status_code == 200:
                teams = teams_res.json()
                for team in teams:
                    st.write(f"**{team['name']}** ({team['code']})")
                    if team["players"]:
                        player_names = [p["name"] for p in team["players"]]
                        st.caption(f"Squad: {', '.join(player_names)}")
            else:
                st.error("Failed to fetch teams.")
        except requests.exceptions.ConnectionError:
            st.error("Backend server is offline.")

    with col2:
        st.subheader("Match History")
        try:
            matches_res = requests.get(f"{API_URL}/matches")
            if matches_res.status_code == 200:
                matches = matches_res.json()
                for match in matches:
                    st.info(f"Team {match['home_team_id']}  [{match['home_score']} - {match['away_score']}]  Team {match['away_team_id']}")
            else:
                st.error("Failed to fetch matches.")
        except requests.exceptions.ConnectionError:
            st.error("Backend server is offline.")

elif choice == "Admin Panel":
    st.header("Admin Portal")
    
    if "token" not in st.session_state:
        st.session_state["token"] = None

    if not st.session_state["token"]:
        st.subheader("Login to Access Protected Actions")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        
        if st.button("Login"):
            res = requests.post(f"{API_URL}/login", data={"username": username, "password": password})
            if res.status_code == 200:
                st.session_state["token"] = res.json()["access_token"]
                st.success("Logged in successfully!")
                st.rerun()
            else:
                st.error("Invalid credentials.")
    else:
        if st.button("Logout"):
            st.session_state["token"] = None
            st.rerun()
            
        st.write("---")
        st.subheader("Log a New Match")
        
        home_id = st.number_input("Home Team ID", min_value=1, step=1)
        away_id = st.number_input("Away Team ID", min_value=1, step=1)
        home_score = st.number_input("Home Score", min_value=0, step=1)
        away_score = st.number_input("Away Score", min_value=0, step=1)
        
        if st.button("Submit Match Result"):
            headers = {"Authorization": f"Bearer {st.session_state['token']}"}
            match_data = {
                "home_team_id": home_id,
                "away_team_id": away_id,
                "home_score": home_score,
                "away_score": away_score
            }
            res = requests.post(f"{API_URL}/matches", json=match_data, headers=headers)
            if res.status_code == 200:
                st.success("Match saved directly to PostgreSQL backend!")
            else:
                st.error(f"Error: {res.json().get('detail')}")