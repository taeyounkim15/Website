from flask import Flask, render_template, request, jsonify
from google.cloud import datastore
from datetime import datetime, timezone
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd

# Define a function to strip '%' and convert to float
def strip_percent_and_divide(x):
    try:
        return float(x.strip('%')) / 100
    except AttributeError:
        return x
    except ValueError:
        return x
    
# return ccase >> ccase=0 FIXED coupon, ccase=1 1styrfixed coupon, ccase=2 all float coupon
def return_ccase(code, df1):
    if df1.loc[code, "Coupon Type"] == "Fixed" : return 0
    else : 
        if df1.loc[code, "1st yr fixed"] == "y" : return 1
        elif df1.loc[code, "1st yr fixed"] == "n" : return 2

def bring_the_dfs():
    # Let's try to bring in the data from the Spreadsheet
    CREDENTIALS_FILE = 'credentials.json'

    # Define the scope and authenticate
    SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPE)
    client = gspread.authorize(creds)

    # Google Spreadsheet ID and sheet name
    SPREADSHEET_ID = '1hEfWYWhbnfN3uURJTQNaDV3QAEEyMzKtmV888E0fA8M'
    SHEET_NAME1 = 'DB'
    SHEET_NAME4 = 'Interest'
    SHEET_NAME5 = 'Announced_interest'

    # Open the spreadsheet by ID and sheet by name
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    worksheet1 = spreadsheet.worksheet(SHEET_NAME1)
    worksheet4 = spreadsheet.worksheet(SHEET_NAME4)
    worksheet5 = spreadsheet.worksheet(SHEET_NAME5)

    data1 = worksheet1.get_all_values()
    df1 = pd.DataFrame(data1[1:], columns=data1[0])
    data4 = worksheet4.get_all_values()
    df4 = pd.DataFrame(data4[1:], columns=data4[0])
    data5 = worksheet5.get_all_values()
    df5 = pd.DataFrame(data5[1:], columns=data5[0])

    df1.set_index("Code", inplace=True, drop=True)

    df1["Issue Date"] = pd.to_datetime(df1["Issue Date"]).dt.date
    df1["Maturity Date"] = pd.to_datetime(df1["Maturity Date"]).dt.date
    df1['Price Yield'] = df1['Price Yield'].replace('', '0')
    df1['Coupon% 1']  = df1['Coupon% 1'].replace('', '0')
    df1['Coupon% k1'] = df1['Coupon% k1'].replace('', '0')
    df1['Coupon% k2'] = df1['Coupon% k2'].replace('', '0')

    df1['Price Yield'] = df1['Price Yield'].str.strip('%').astype(float) / 100
    df1['Coupon% 1'] = df1['Coupon% 1'].str.strip('%').astype(float) / 100
    df1['Coupon% k1'] = df1['Coupon% k1'].str.strip('%').astype(float) / 100
    df1['Coupon% k2'] = df1['Coupon% k2'].str.strip('%').astype(float) / 100
    # Replace empty strings with 0
    df1['Bond size'] = df1['Bond size'].replace('', '0')
    df1['Bond size'] = df1['Bond size'].str.replace(',', '').astype(float)

    df1['Par value'] = df1['Par value'].replace('', '0')
    df1['Par value'] = df1['Par value'].str.replace(',', '').astype(float)

    df1['Ex right day'] = df1['Ex right day'].replace('', '0')
    df1['Ex right day'] = df1['Ex right day'].str.replace(',', '').astype(int)

    df1['k1 years'] = df1['k1 years'].replace('', '0')
    df1['k1 years'] = df1['k1 years'].str.replace(',', '').astype(float)

    df4 = df4.ffill(axis=0) # inccase the future interest predictions are not filled, it takes the "Today" values as the interest rate
    df4 = df4.set_index("year").map(strip_percent_and_divide).reset_index()
    df4['year'] = df4['year'].str[1:].astype(int)

    df5["Coupon_Date"] = pd.to_datetime(df5["Coupon_Date"]).dt.date
    df5["Announced_rate"] = df5["Announced_rate"].map(strip_percent_and_divide)

    return df1, df4, df5

# datastore_client = datastore.Client()

# def store_time(dt):
#     entity = datastore.Entity(key=datastore_client.key("visit"))
#     entity.update({"timestamp": dt})
#     datastore_client.put(entity)

# def fetch_times(limit):
#     query = datastore_client.query(kind="visit")
#     query.order = ["-timestamp"]
#     times = query.fetch(limit=limit)
#     return times

app = Flask(__name__)

@app.route("/")
def home():
    df1, df4, df5 = bring_the_dfs()
    ccase = return_ccase(df1.index[0], df1)
    selected_option = df1.index[0]

    yrdf = df1['Maturity Date'][selected_option].year - df1['Issue Date'][selected_option].year
    exp = "["+ df1["Coupon Type"][selected_option] +"]     "

    if ccase == 0:
        exp += str(df1["Coupon% 1"][selected_option] * 100) + f"% annual coupon rate for all period"
    elif ccase == 1:
        exp += "1st Year coupon rate at [" + str(round(df1["Coupon% 1"][selected_option] * 100,3)) + f"%].  [" + str(df1["Coupon% Ref"][selected_option]) + " + " + str(round(df1["Coupon% k1"][selected_option] * 100, 3)) + f"%] for the rest"
    elif ccase == 2:
        if df1["k1 years"][selected_option] >= yrdf:
            exp += "[" + str(df1["Coupon% Ref"][selected_option]) + " + " + str(round(df1["Coupon% k1"][selected_option] * 100, 3)) + f"%] annual coupon rate for all period"
        else :
            exp += str(int(df1["k1 years"][selected_option])) + "years with annual coupon rate of [" + str(df1["Coupon% Ref"][selected_option]) + " + " + str(round(df1["Coupon% k1"][selected_option] * 100, 3)) + f"%]. Then [Ref. + " + str(round(df1["Coupon% k2"][selected_option] * 100, 3)) + f"%] for the rest"

    # Store the current access time in Datastore.
    # store_time(datetime.now(tz=timezone.utc))

    # Fetch the most recent 10 access times from Datastore.
    # times = fetch_times(10)
    d_send = df1.iloc[[0]].to_dict(orient="records")
    return render_template("home.html", codes=df1.index, d_send=d_send, exp = exp)
    
@app.route("/about")
def about():
    return render_template("about.html")

@app.route('/update_data', methods=['POST'])
def update_data():
    df1, df4, df5 = bring_the_dfs()
    selected_option = request.json.get('selected_option')
    ccase = return_ccase(selected_option, df1)

    yrdf = df1['Maturity Date'][selected_option].year - df1['Issue Date'][selected_option].year

    df1['Issue Date'] = df1['Issue Date'].apply(lambda x: x.strftime('%Y-%m-%d'))
    df1['Maturity Date'] = df1['Maturity Date'].apply(lambda x: x.strftime('%Y-%m-%d'))

    exp = "["+ str(df1["Coupon Type"][selected_option]) +"]     "
    if ccase == 0:
        exp += str(df1["Coupon% 1"][selected_option] * 100) + f"% annual coupon rate for all period"
    elif ccase == 1:
        exp += "1st Year coupon rate at [" + str(round(df1["Coupon% 1"][selected_option] * 100,3)) + f"%].  [" + str(df1["Coupon% Ref"][selected_option]) + " + " + str(round(df1["Coupon% k1"][selected_option] * 100, 3)) + f"%] for the rest"
    elif ccase == 2:
        if df1["k1 years"][selected_option] >= yrdf:
            exp += "[" + str(df1["Coupon% Ref"][selected_option]) + " + " + str(round(df1["Coupon% k1"][selected_option] * 100, 3)) + f"%] annual coupon rate for all period"
        else :
            exp += str(int(df1["k1 years"][selected_option])) + "years with annual coupon rate of [" + str(df1["Coupon% Ref"][selected_option]) + " + " + str(round(df1["Coupon% k1"][selected_option] * 100, 3)) + f"%]. Then [Ref. + " + str(round(df1["Coupon% k2"][selected_option] * 100, 3)) + f"%] for the rest"

    d_send = df1.loc[[selected_option]].to_dict(orient="records")
    # new_data = data.get(selected_option, 'No data available')  # Fetch the data based on the selected option
    return jsonify(new_data=selected_option, d_send=d_send, exp=exp)
    
if __name__ == "__main__":
    # app.run(debug=True)
    app.run(host="127.0.0.1", port=8080, debug=True)