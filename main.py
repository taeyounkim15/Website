from flask import Flask, render_template
from google.cloud import datastore
from datetime import datetime, timezone
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd

# ============================
# # Let's try to bring in the data from the Spreadsheet
# CREDENTIALS_FILE = 'credentials.json'

# # Define the scope and authenticate
# SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
# creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPE)
# client = gspread.authorize(creds)

# # Google Spreadsheet ID and sheet name
# SPREADSHEET_ID = '1hEfWYWhbnfN3uURJTQNaDV3QAEEyMzKtmV888E0fA8M'
# SHEET_NAME = 'DB'

# # Open the spreadsheet by ID and sheet by name
# spreadsheet = client.open_by_key(SPREADSHEET_ID)
# worksheet = spreadsheet.worksheet(SHEET_NAME)

# data = worksheet.get_all_values()

# ============================

datastore_client = datastore.Client()

def store_time(dt):
    entity = datastore.Entity(key=datastore_client.key("visit"))
    entity.update({"timestamp": dt})
    datastore_client.put(entity)

def fetch_times(limit):
    query = datastore_client.query(kind="visit")
    query.order = ["-timestamp"]
    times = query.fetch(limit=limit)
    return times

app = Flask(__name__)

@app.route("/")
def home():
    # ============================
    # Let's try to bring in the data from the Spreadsheet
    CREDENTIALS_FILE = 'credentials.json'

    # Define the scope and authenticate
    SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPE)
    client = gspread.authorize(creds)

    # Google Spreadsheet ID and sheet name
    SPREADSHEET_ID = '1hEfWYWhbnfN3uURJTQNaDV3QAEEyMzKtmV888E0fA8M'
    SHEET_NAME = 'DB'

    # Open the spreadsheet by ID and sheet by name
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    worksheet = spreadsheet.worksheet(SHEET_NAME)

    data = worksheet.get_all_values()
    df = pd.DataFrame(data[1:], columns=data[0])

    # print(data[0])
    # ============================


    # Store the current access time in Datastore.
    # store_time(datetime.now(tz=timezone.utc))

    # Fetch the most recent 10 access times from Datastore.
    # times = fetch_times(10)
    return render_template("home.html", codes=df["Code"])
    
@app.route("/about")
def about():
    return render_template("about.html")
    
if __name__ == "__main__":
    # app.run(debug=True)
    app.run(host="127.0.0.1", port=8080, debug=True)