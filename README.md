
# ⚽ FootballDB 

A high-performance, automated football data pipeline and interactive dashboard for real-time European league analytics.

## Table of Contents
- Overview
- Key Features
- Tech Stack
- Setup & Usage
- Documentation

## Overview
FootballDB is a full-stack analytics platform that synchronizes real-world football data from European leagues into a local relational database. It features a secure, automated background daemon that pulls live match results, updates league standings and stores comprehensive team profiles (including crests, managers and active rosters), displaying it all on a responsive, cached frontend dashboard.

## Key Features
- 🔴 **Live Match Scoreboard:** Real-time match tracking with a 60-second caching mechanism to prevent rate-limiting.
- 🤖 **Autonomous Nightly Sync:** Integrated APScheduler daemon that updates the database silently at midnight.
- 📊 **Dynamic League Tables:** Instant standings for the Premier League, La Liga, Champions League, Serie A, Bundesliga and Ligue 1.
- 🔎 **Deep Team Spotlights:** Relational database mapping connects external API data (managers, crests, rosters) into an internal PostgreSQL schema.
- 🔒 **JWT Secured Admin Panel:** Protected endpoints for manual database synchronization and user management.

## Tech Stack
- Frontend: Streamlit, Pandas
- Backend: FastAPI, SQLAlchemy, APScheduler, Passlib, PyJWT
- Database: PostgreSQL
- External Integrations: football-data.org API

## Setup & Usage
- **Prerequisites**
    - Python 3.10+
    - PostgreSQL installed and running locally

- **Steps**
    
    1. **Clone the repository:**

        `git clone https://github.com/zdityz/FootballDB.git`

        `cd FootballDB`

    2. **Create and activate a virtual environment**

        `python3 -m venv venv`

        `source venv/bin/activate`
    
    3. **Install dependencies**
    
        `pip install -r requirements.txt`
    
    4. **Set up the database**
    
        Ensure PostgreSQL is running. The app will automatically build the tables on the first run.
    
    5. **Create Environment Variables**
    
        Create a .env file in the root directory and configure the following variables:
        

        | Variable | Description | Required |
        | :--- | :--- | :--- |
        | SPORTS_API_KEY | Your authentication token from football-data.org | Yes |
        | DATABASE_URL | PostgreSQL connection string (e.g., postgresql://localhost/analytics) | Yes |
        | JWT_SECRET | A secure 32-byte hex string for hashing user tokens | Yes |
        
- Usage
    1. **Start the FastAPI Backend:** Open a terminal and run the server:
        `python3 -m uvicorn main:app --reload`
    2. **Start the Streamlit Frontend:** Open a second terminal, activate your virtual environment and run:
        `streamlit run app.py`
## API Documentation
The backend automatically generates interactive Swagger documentation. Once the FastAPI server is running, navigate to: http://127.0.0.1:8000/docs to view and test all available endpoints (e.g., /live, /sync/players, /register, etc.).


## ⭐ Support the Project

If you found this project useful or interesting, consider giving it a **star** on GitHub. It helps increase the project's visibility and motivates continued development.

Thank you for your support!