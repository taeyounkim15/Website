from flask import Flask, render_template, request, jsonify
from google.cloud import datastore
from datetime import datetime, timezone, date
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from dateutil.relativedelta import relativedelta
import numpy as np
from scipy.optimize import newton

# Define a function to strip '%' and convert to float
def strip_percent_and_divide(x):
    try:
        return float(x.strip('%')) / 100
    except AttributeError:
        return x
    except ValueError:
        return x
    
# Function to calculate trading price based on pry
def calculate_trading_price(pry, df, frq, k):
    df['i'] = range(len(df))
    df["DC CF"] = df["CF"] / (1 + pry * frq / 12)**df["i"]
    return df["DC CF"].sum() / (1 + k * pry)

# Target function for root finding
def target_function(pry, df, trading_price, frq, k):
    return calculate_trading_price(pry, df, frq, k) - trading_price

def format_number(x):
    if isinstance(x, (int, float)):
        return "{:,}".format(x)
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
    df1['Par value'] = df1['Par value'].str.replace(',', '').astype(int)

    df1['Ex right day'] = df1['Ex right day'].replace('', '0')
    df1['Ex right day'] = df1['Ex right day'].str.replace(',', '').astype(int)

    df1['k1 years'] = df1['k1 years'].replace('', '0')
    df1['k1 years'] = df1['k1 years'].str.replace(',', '').astype(float)

    df4.replace('', np.nan, inplace=True)
    df4 = df4.ffill(axis=0) # inccase the future interest predictions are not filled, it takes the "Today" values as the interest rate
    df4 = df4.set_index("year").map(strip_percent_and_divide).reset_index()
    df4['year'] = df4['year'].str[1:].astype(int)

    df5["Coupon_Date"] = pd.to_datetime(df5["Coupon_Date"]).dt.date
    df5["Announced_rate"] = df5["Announced_rate"].map(strip_percent_and_divide)

    return df1, df4, df5

def cashflow(df4, df5, selected_option, ccase, par, isd, mtd, trd, exr, cp1, cpR, cpk, cpkY, cpk2, frq, pry):
    if frq == "quarterly" :
        frq = 3
    elif frq == "annually" :
        frq = 12
    elif frq == "semi-annually" :
        frq = 6
    else :
        raise Warning("Frequency => incorrect value")

    d_set = trd + relativedelta(days=1)

    # Generate the list of dates
    l_payd = []
    paydX = isd + relativedelta(months=frq)  # Start from the first increment
    i = 1
    while paydX < mtd:
        # l_payd.append(paydX)
        l_payd.append(isd + relativedelta(months=frq*i))
        paydX = l_payd[-1]
        i += 1

    l_days = []
    paydX = isd
    for x in l_payd :
        l_days.append((x-paydX).days)
        paydX = x

    data = {"d"      : l_days,
            "Date"   : l_payd}
    df = pd.DataFrame(data)
    # calculate the coupons
    # if FIXED
    if ccase == 0 :
        df["CP rate(%)"] = cp1

    # if 1st year fixed, and the rest are ref
    elif ccase == 1 :
        r_grp = cpR.split(', ')
        # Extract the year from the Date column in df
        df['year'] = df['Date'].apply(lambda x: x.year)

        # Calculate the average for each year in df4
        df4['average'] = df4[r_grp].mean(axis=1)

        # Merge df with df4 on the year
        df = df.merge(df4[['year', 'average']], on='year', how='left')
        
        # Rename the average column to cppp
        df.rename(columns={'average': 'CP rate(%)'}, inplace=True)

        df.loc[:int(12/frq)-1, 'CP rate(%)'] = cp1 # 1st year fixed coupon!!!!
        df.loc[int(12/frq):, 'CP rate(%)'] = df.loc[int(12/frq):, 'CP rate(%)'] + cpk

    elif ccase == 2 :
        r_grp = cpR.split(', ')
        # Extract the year from the Date column in df
        df['year'] = df['Date'].apply(lambda x: x.year)

        # Calculate the average for each year in df4
        df4['average'] = df4[r_grp].mean(axis=1)

        # Merge df with df4 on the year
        df = df.merge(df4[['year', 'average']], on='year', how='left')
        
        # Rename the average column to cppp
        df.rename(columns={'average': 'CP rate(%)'}, inplace=True)

        # df.loc[:int(cpkY * 12/frq) - 1, 'CP rate(%)'] = cpk # 1st year fixed coupon!!!!
        df.loc[:int(cpkY * 12/frq) - 1, 'CP rate(%)'] = df.loc[:int(cpkY * 12/frq) - 1, 'CP rate(%)'] + cpk
        df.loc[int(cpkY * 12/frq):, 'CP rate(%)'] = df.loc[int(cpkY * 12/frq):, 'CP rate(%)'] + cpk2


    # change df1.index[ind_a] to selected_option
    # Check if b_code exists in df5['Bond_Code']
    if selected_option in df5['Bond_Code'].values:
        # Iterate over all rows in df5 with the given b_code
        for _, row in df5[df5['Bond_Code'] == selected_option].iterrows():
            coupon_date = row['Coupon_Date']
            announced_rate = row['Announced_rate']
            
            # Update df['cppp'] where df['Date'] matches df5['Coupon_Date']
            df.loc[df['Date'] == coupon_date, 'CP rate(%)'] = announced_rate

    df["Coupon"] = par * df["CP rate(%)"] * df["d"] / 365

    df["Date [yyyy-mm-dd]"] = pd.to_datetime(df["Date"])
    df['X right'] = df['Date [yyyy-mm-dd]'] - pd.offsets.BusinessDay(n=exr)

    df["Date [yyyy-mm-dd]"] = df["Date [yyyy-mm-dd]"].dt.date
    df['X right'] = df['X right'].dt.date

    msk = df["X right"] >= d_set
    df = df[msk].copy()
    df['i'] = range(len(df))

    # print(df)

    df["CF"] = df["Coupon"]
    df.loc[df.index[-1], 'CF'] = df.loc[df.index[-1], 'CF'] + par
    df["DC CF"] = df["CF"] / (1 + pry * frq / 12)**df["i"]

    sumdc = df["DC CF"].sum()
    d_nxt = df.iloc[0]['Date']
    
    if l_payd.index(d_nxt) == 0 :
        d_prv = isd
    else :
        d_prv = l_payd[l_payd.index(d_nxt) -1]

    ptd = sumdc / (1 + (( d_nxt - d_set ).days * pry * frq ) / (12 * (d_nxt - d_prv).days) )

    # print("l_days[0] ",l_days[0])
    # print("d_nxt - d_prv", (d_nxt - d_prv).days)
    # print("d_nxt", d_nxt)
    # print("d_prv", d_prv)

    df["CP rate(%)"] = (df["CP rate(%)"]*100).round(4)
    df[['Coupon', 'CF', 'DC CF']] = df[['Coupon', 'CF', 'DC CF']].round(0).astype(int)
    # dfF = df.applymap(format_number)
    dfF = df.map(format_number)
    

    return dfF.reset_index()[["Date [yyyy-mm-dd]", 'X right', "Coupon", "CF", "DC CF", "CP rate(%)"]].copy(), ptd, df["CF"].sum(), sumdc, d_nxt

def cashflow_for_reverse(selected_option, df4, df5, ccase, par, isd, mtd, trd, exr, cp1, cpR, cpk, cpkY, cpk2, frq):
    if frq == "quarterly" :
        frq = 3
    elif frq == "annually" :
        frq = 12
    elif frq == "semi-annually" :
        frq = 6
    else :
        raise Warning("Frequency => incorrect value")

    d_set = trd + relativedelta(days=1)

    # Generate the list of dates
    l_payd = []
    paydX = isd + relativedelta(months=frq)  # Start from the first increment
    i = 1
    while paydX < mtd:
        # l_payd.append(paydX)
        l_payd.append(isd + relativedelta(months=frq*i))
        paydX = l_payd[-1]
        i += 1

    l_days = []
    paydX = isd
    for x in l_payd :
        l_days.append((x-paydX).days)
        paydX = x

    data = {"d"      : l_days,
            "Date"   : l_payd}
    df = pd.DataFrame(data)
    # calculate the coupons
    # if FIXED
    if ccase == 0 :
        df["CP rate(%)"] = cp1

    # if 1st year fixed, and the rest are ref
    elif ccase == 1 :
        r_grp = cpR.split(', ')
        # Extract the year from the Date column in df
        df['year'] = df['Date'].apply(lambda x: x.year)

        # Calculate the average for each year in df4
        df4['average'] = df4[r_grp].mean(axis=1)

        # Merge df with df4 on the year
        df = df.merge(df4[['year', 'average']], on='year', how='left')
        
        # Rename the average column to cppp
        df.rename(columns={'average': 'CP rate(%)'}, inplace=True)

        df.loc[:int(12/frq)-1, 'CP rate(%)'] = cp1 # 1st year fixed coupon!!!!
        df.loc[int(12/frq):, 'CP rate(%)'] = df.loc[int(12/frq):, 'CP rate(%)'] + cpk

    elif ccase == 2 :
        r_grp = cpR.split(', ')
        # Extract the year from the Date column in df
        df['year'] = df['Date'].apply(lambda x: x.year)

        # Calculate the average for each year in df4
        df4['average'] = df4[r_grp].mean(axis=1)

        # Merge df with df4 on the year
        df = df.merge(df4[['year', 'average']], on='year', how='left')
        
        # Rename the average column to cppp
        df.rename(columns={'average': 'CP rate(%)'}, inplace=True)

        # df.loc[:int(cpkY * 12/frq) - 1, 'CP rate(%)'] = cpk # 1st year fixed coupon!!!!
        df.loc[:int(cpkY * 12/frq) - 1, 'CP rate(%)'] = df.loc[:int(cpkY * 12/frq) - 1, 'CP rate(%)'] + cpk
        df.loc[int(cpkY * 12/frq):, 'CP rate(%)'] = df.loc[int(cpkY * 12/frq):, 'CP rate(%)'] + cpk2


    # change df1.index[ind_a] to bcode.get()
    # Check if b_code exists in df5['Bond_Code']
    if selected_option in df5['Bond_Code'].values:
        # Iterate over all rows in df5 with the given b_code
        for _, row in df5[df5['Bond_Code'] == selected_option].iterrows():
            coupon_date = row['Coupon_Date']
            announced_rate = row['Announced_rate']
            
            # Update df['cppp'] where df['Date'] matches df5['Coupon_Date']
            df.loc[df['Date'] == coupon_date, 'CP rate(%)'] = announced_rate


    df["Coupon"] = par * df["CP rate(%)"] * df["d"] / 365
    df["CF"] = df["Coupon"]
    df.loc[df.index[-1], 'CF'] = df.loc[df.index[-1], 'CF'] + par

    df["Date"] = pd.to_datetime(df["Date"])
    df['X right'] = df['Date'] - pd.offsets.BusinessDay(n=exr)

    df["Date"] = df["Date"].dt.date
    df['X right'] = df['X right'].dt.date

    msk = df["X right"] >= d_set
    df = df[msk].copy()


    d_nxt = df.iloc[0]['Date']
    
    if l_payd.index(d_nxt) == 0 :
        d_prv = isd
    else :
        d_prv = l_payd[l_payd.index(d_nxt) -1]

    k = (( d_nxt - d_set ).days * frq ) / (12 * (d_nxt - d_prv).days) 
    df = df.round(3)

    return df[["Date", 'X right', "Coupon", "CF"]], frq, k
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

    
    par = df1.loc[selected_option, "Par value"]
    isd = df1.loc[selected_option, "Issue Date"]
    mtd = df1.loc[selected_option, "Maturity Date"]
    trd = date.today()
    exr = df1.loc[selected_option, "Ex right day"]
    cp1 = df1.loc[selected_option, "Coupon% 1"]
    cpR = df1.loc[selected_option, "Coupon% Ref"]
    cpk = df1.loc[selected_option, "Coupon% k1"]
    frq = df1.loc[selected_option, "Coupon payment"]
    pry = df1.loc[selected_option, "Price Yield"]
    cpkY= df1.loc[selected_option, "k1 years"]
    cpk2= df1.loc[selected_option, "Coupon% k2"]

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


    cfT, ptd, sumcf, sumdc, d_nxt = cashflow(df4=df4, df5=df5, selected_option=selected_option, ccase = ccase, par=par, isd=isd, mtd=mtd, trd=trd, exr=exr, cp1=cp1, cpR=cpR, cpk=cpk, cpkY=cpkY, cpk2=cpk2, frq=frq, pry=pry)
    cfT_col = cfT.columns.tolist()
    cfT_rec = cfT.to_dict(orient='records')

    return render_template("home.html", codes=df1.index.tolist(), d_send=d_send, exp = exp, cfT_col=cfT_col, cfT_rec=cfT_rec, ptd=int(ptd), d_nxt=d_nxt)
    
@app.route("/about")
def about():
    return render_template("about.html")

@app.route('/update_data', methods=['POST'])
def update_data():
    df1, df4, df5 = bring_the_dfs()
    selected_option = request.json.get('selected_option')
    ccase = return_ccase(selected_option, df1)

    par = df1.loc[selected_option, "Par value"]
    isd = df1.loc[selected_option, "Issue Date"]
    mtd = df1.loc[selected_option, "Maturity Date"]
    trd = date.today()
    exr = df1.loc[selected_option, "Ex right day"]
    cp1 = df1.loc[selected_option, "Coupon% 1"]
    cpR = df1.loc[selected_option, "Coupon% Ref"]
    cpk = df1.loc[selected_option, "Coupon% k1"]
    frq = df1.loc[selected_option, "Coupon payment"]
    pry = df1.loc[selected_option, "Price Yield"]
    cpkY= df1.loc[selected_option, "k1 years"]
    cpk2= df1.loc[selected_option, "Coupon% k2"]

    yrdf = df1['Maturity Date'][selected_option].year - df1['Issue Date'][selected_option].year

    df1['Issue Date'] = df1['Issue Date'].apply(lambda x: x.strftime('%Y-%m-%d'))
    df1['Maturity Date'] = df1['Maturity Date'].apply(lambda x: x.strftime('%Y-%m-%d'))

    exp = "["+ str(df1["Coupon Type"][selected_option]) +"]     "
    if ccase == 0:
        exp += str(df1["Coupon% 1"][selected_option] * 100) + f"% annual coupon rate for all period nha"
    elif ccase == 1:
        exp += "1st Year coupon rate at [" + str(round(df1["Coupon% 1"][selected_option] * 100,3)) + f"%].  [" + str(df1["Coupon% Ref"][selected_option]) + " + " + str(round(df1["Coupon% k1"][selected_option] * 100, 3)) + f"%] for the rest. nha"
    elif ccase == 2:
        if df1["k1 years"][selected_option] >= yrdf:
            exp += "[" + str(df1["Coupon% Ref"][selected_option]) + " + " + str(round(df1["Coupon% k1"][selected_option] * 100, 3)) + f"%] annual coupon rate for all period nha"
        else :
            exp += str(int(df1["k1 years"][selected_option])) + "years with annual coupon rate of [" + str(df1["Coupon% Ref"][selected_option]) + " + " + str(round(df1["Coupon% k1"][selected_option] * 100, 3)) + f"%]. Then [Ref. + " + str(round(df1["Coupon% k2"][selected_option] * 100, 3)) + f"%] for the rest. nha"

    d_send = df1.loc[[selected_option]].to_dict(orient="records")

    # print(df4)
    # return
    cfT, ptd, sumcf, sumdc, d_nxt = cashflow(df4=df4, df5=df5, selected_option=selected_option, ccase = ccase, par=par, isd=isd, mtd=mtd, trd=trd, exr=exr, cp1=cp1, cpR=cpR, cpk=cpk, cpkY=cpkY, cpk2=cpk2, frq=frq, pry=pry)
    cfT['Date [yyyy-mm-dd]'] = cfT['Date [yyyy-mm-dd]'].apply(lambda x: x.strftime('%Y-%m-%d'))
    cfT['X right'] = cfT['X right'].apply(lambda x: x.strftime('%Y-%m-%d'))
    cfT_col = cfT.columns.tolist()
    cfT_rec = cfT.to_dict(orient='records')

    # new_data = data.get(selected_option, 'No data available')  # Fetch the data based on the selected option
    return jsonify(new_data=selected_option, codes=df1.index.tolist(), d_send=d_send, exp=exp, cfT_col=cfT_col, cfT_rec=cfT_rec, ptd=int(ptd), d_nxt=d_nxt.strftime('%Y-%m-%d'))

@app.route('/recalculate', methods=['POST'])
def recalculate():
    df1, df4, df5 = bring_the_dfs()
    selected_option = request.json.get('resultCode')
    ccase = return_ccase(selected_option, df1)

    # par = df1.loc[selected_option, "Par value"]
    par = int(request.json.get('parvalu')) # integer
    # print("par      " )
    # print(par)
    # print(type(par))
    # isd = df1.loc[selected_option, "Issue Date"]
    isd = datetime.strptime(request.json.get('isudate'), "%Y-%m-%d").date() # datetime.date
    # mtd = df1.loc[selected_option, "Maturity Date"]
    mtd = datetime.strptime(request.json.get('matdate'), "%Y-%m-%d").date()
    # trd = date.today()
    if request.json.get('trddte') == '' :
        trd = date.today()
    else :
        trd = datetime.strptime(request.json.get('trddte'), "%Y-%m-%d").date()
    # exr = df1.loc[selected_option, "Ex right day"]
    exr = int(request.json.get('exrtday'))
    # frq = df1.loc[selected_option, "Coupon payment"]
    frq = request.json.get('freqncy')
    # pry = df1.loc[selected_option, "Price Yield"]
    pry = float(request.json.get('prcyld')) / 100
    cp1 = df1.loc[selected_option, "Coupon% 1"]
    cpR = df1.loc[selected_option, "Coupon% Ref"]
    cpk = df1.loc[selected_option, "Coupon% k1"]
    cpkY= df1.loc[selected_option, "k1 years"]
    cpk2= df1.loc[selected_option, "Coupon% k2"]

    cfT, ptd, sumcf, sumdc, d_nxt = cashflow(df4=df4, df5=df5, selected_option=selected_option, ccase = ccase, par=par, isd=isd, mtd=mtd, trd=trd, exr=exr, cp1=cp1, cpR=cpR, cpk=cpk, cpkY=cpkY, cpk2=cpk2, frq=frq, pry=pry)
    cfT['Date [yyyy-mm-dd]'] = cfT['Date [yyyy-mm-dd]'].apply(lambda x: x.strftime('%Y-%m-%d'))
    cfT['X right'] = cfT['X right'].apply(lambda x: x.strftime('%Y-%m-%d'))
    cfT_col = cfT.columns.tolist()
    cfT_rec = cfT.to_dict(orient='records')
    
    # return jsonify(new_data=selected_option, codes=df1.index.tolist(), d_send=d_send, exp=exp, cfT_col=cfT_col, cfT_rec=cfT_rec, ptd=int(ptd), d_nxt=d_nxt.strftime('%Y-%m-%d'))
    return jsonify(cfT_col=cfT_col, cfT_rec=cfT_rec, ptd=int(ptd), d_nxt=d_nxt.strftime('%Y-%m-%d'))

@app.route('/reverso', methods=['POST'])
def reverso():
    df1, df4, df5 = bring_the_dfs()
    selected_option = request.json.get('resultCode')
    ccase = return_ccase(selected_option, df1)

    par = int(request.json.get('parvalu')) # integer
    isd = datetime.strptime(request.json.get('isudate'), "%Y-%m-%d").date() # datetime.date
    mtd = datetime.strptime(request.json.get('matdate'), "%Y-%m-%d").date()
    if request.json.get('trddte') == '' :
        trd = date.today()
    else :
        trd = datetime.strptime(request.json.get('trddte'), "%Y-%m-%d").date()
    exr = int(request.json.get('exrtday'))
    frq = request.json.get('freqncy')
    # pry = float(request.json.get('prcyld')) / 100 #skip Price Yield for the reverso
    cp1 = df1.loc[selected_option, "Coupon% 1"]
    cpR = df1.loc[selected_option, "Coupon% Ref"]
    cpk = df1.loc[selected_option, "Coupon% k1"]
    cpkY= df1.loc[selected_option, "k1 years"]
    cpk2= df1.loc[selected_option, "Coupon% k2"]

    ### Different to Recalculate from this point on
    ttt, fr1, k = cashflow_for_reverse(selected_option, df4, df5, ccase, par, isd, mtd, trd, exr, cp1, cpR, cpk, cpkY, cpk2, frq)

    initial_guess = 0.07
    trading_price = float(request.json.get('reverso'))

    pry_solution = newton(target_function, initial_guess, args=(ttt, trading_price, fr1, k)) * 100

    return jsonify(pry_solution = pry_solution)


if __name__ == "__main__":
    # app.run(debug=True)
    app.run(host="127.0.0.1", port=8080, debug=True)