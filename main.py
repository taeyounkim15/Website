from flask import Flask, render_template
from google.cloud import datastore
import datetime

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
    # Store the current access time in Datastore.
    store_time(datetime.datetime.now(tz=datetime.timezone.utc))

    # Fetch the most recent 10 access times from Datastore.
    times = fetch_times(10)
    return render_template("home.html", times=times)
    
@app.route("/about")
def about():
    return render_template("about.html")
    
if __name__ == "__main__":
    # app.run(debug=True)
    app.run(host="127.0.0.1", port=8080, debug=True)