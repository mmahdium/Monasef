from flask import (
    Flask,
    request,
    Response,
    render_template,
    render_template_string,
    redirect,
    send_from_directory
)
import requests
import os
import datetime
import uuid
from urllib.parse import *
import urllib
from urllib.parse import urlparse, urlunparse, urljoin
from flask_compress import Compress
import logging
from dotenv import dotenv_values
import sqlite3


compress = Compress()
app = Flask(__name__, template_folder="./")
compress.init_app(app)
app.config['COMPRESS_BR_LEVEL'] = 11
app.config['COMPRESS_LEVEL'] = 9
app.config['COMPRESS_STREAMS'] = True
app.static_folder = "static"

logger404 = logging.getLogger('logger404')
logger500 = logging.getLogger('logger500')

handler1 = logging.FileHandler('./logs/404.log', 'w', 'utf-8')
handler2 = logging.FileHandler('./logs/500.log', 'w', 'utf-8')

handler1.setLevel(logging.ERROR)
handler2.setLevel(logging.ERROR)

formatter = logging.Formatter('%(asctime)s - %(name)s - %(message)s')

handler1.setFormatter(formatter)
handler2.setFormatter(formatter)

logger404.addHandler(handler1)
logger500.addHandler(handler2)


def checkdb():
    if not os.path.isfile(os.getenv('SQLITE3DBNAME')):
        print("Error: Database file not found.")
        exit()
    db  = sqlite3.connect(os.getenv('SQLITE3DBNAME'))
    cursor = db.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS nimbaha (id VARCHAR(255) PRIMARY KEY, url TEXT, filename TEXT, filesize INTEGER, extension TEXT, expiry_date DATETIME)
''')
    


def check_url(url):
    try:
        # Follow redirects in one step
        response = requests.head(url, allow_redirects=True)
        content_type = response.headers.get("Content-Type", "").lower()

        if response.status_code in [301, 302]:
            print(f"URL is a redirect: {url}")

        if "text/html" in content_type:
            print(f"URL is a web page: {response.url}")
            return False

        print(f"Reached file: {response.url}")
        return True

    except requests.RequestException as e:
        print(f"Error occurred: {e}")
        return False



def save_url_info(url):
    # Save the URL information to the sqlite3 database
    db  = sqlite3.connect(os.getenv('SQLITE3DBNAME'))
    cursor = db.cursor()

    # Check if the URL already exists in the database
    cursor.execute("SELECT id, expiry_date FROM nimbaha WHERE url = ?", (url,))
    result = cursor.fetchone()

    # If exists, update the expiry date and return the unique_id
    if result:
        unique_id, old_expiry_date = result
        new_expiry_date = datetime.datetime.now() + datetime.timedelta(days=3)
        cursor.execute(
            "UPDATE nimbaha SET expiry_date = ? WHERE id = ?",
            (new_expiry_date, unique_id)
        )
        db.commit()
        db.close()
        return unique_id

    # Generate a unique 16-digit ID
    unique_id = uuid.uuid4().hex[:16]

    # Get the file information
    response = requests.get(url, stream=True)
    filename, file_extension = os.path.splitext(os.path.basename(url))
    filesize = int(response.headers["content-length"])

    # Calculate the expiry date
    expiry_date = datetime.datetime.now() + datetime.timedelta(days=3)

    # Insert the URL information into the database
    cursor.execute(
        "INSERT INTO nimbaha (id, url, filename, filesize, extension, expiry_date) VALUES (?, ?, ?, ?, ?, ?)",
        (unique_id, url, filename, filesize, file_extension, expiry_date),
    )
    db.commit()

    db.close()

    return unique_id



def get_filename_from_url(url=None):
    if url is None:
        return None
    urlpath = urlsplit(url).path
    return os.path.basename(urlpath)


def get_file_size(url):
    response = requests.head(url, allow_redirects=True)

    file_size = int(response.headers.get("content-length", 0))

    # Convert size to KB, MB or GB
    if file_size < 1024**2:
        size = f"{file_size / 1024:.2f} کیلوبایت"
    elif file_size < 1024**3:
        size = f"{file_size / 1024**2:.2f} مگابایت"
    else:
        size = f"{file_size / 1024**3:.2f} گیگابایت"

    return size


def get_file_extension(url):
    path = urllib.parse.urlparse(url).path
    extension = path.split(".")[-1] if "." in path else "No extension found"
    return extension


@app.errorhandler(404)
def not_found_error():
    logger404.error(f'404 error at URL: {request.url}')
    return render_template("viewdetails/error.html", err_msg="!اشتباه اومدی"), 404

@app.errorhandler(500)
def internal_error():
    logger500.error(f'500 error at URL: {request.url}')
    return render_template("viewdetails/error.html", err_msg="مشکلی پیش آمده بعدا تلاش کنید"), 500


@app.route('/<path:filename>', methods=['GET'])
def serve_file_in_dir(filename):

    if not os.path.isfile('.accessible/' + filename):
        return not_found_error()

    return send_from_directory('.accessible', filename)

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/verifyurl", methods=["POST"])
def verifyurl():
    url = request.form["url"]
    
    if check_url(url):
            unique_id = save_url_info(url)
            return redirect("/viewdetails/" + unique_id, code=302)
    else:
            return render_template(
                "viewdetails/error.html", err_msg="لینک نامعتبر است یا مستقیم نیست"
            )



@app.route("/viewdetails/<unique_id>")
def viewdetails(unique_id):
    db  = sqlite3.connect(os.getenv('SQLITE3DBNAME'))
    cursor = db.cursor()

    # Check if the unique ID exists
    cursor.execute("SELECT filename, filesize, extension, expiry_date FROM nimbaha WHERE id = ?", (unique_id,))
    url_and_expiry_date = cursor.fetchone()
    db.close()
    if not url_and_expiry_date:
        return render_template("viewdetails/error.html", err_msg="لینک مورد نظر وجود ندارد")

    # Extract URL and expiry date
    filename, filesize, extension, expiry_date = url_and_expiry_date

    # Convert expiry_date from string to datetime
    expiry_date = datetime.datetime.strptime(expiry_date, "%Y-%m-%d %H:%M:%S.%f")

    # Determine if the link has expired
    today = datetime.datetime.today()
    if expiry_date < today:
        return render_template(
            "viewdetails/error.html",
            err_msg="زمان دانلود این لینک به اتمام رسیده",
        )

    # Calculate days to expiration
    days_to_expire = (expiry_date - today).days + 1

    if filesize < 1024**2:
        size = f"{filesize / 1024:.2f} کیلوبایت"
    elif filesize < 1024**3:
        size = f"{filesize / 1024**2:.2f} مگابایت"
    else:
        size = f"{filesize / 1024**3:.2f} گیگابایت"

    # Render the view details page
    return render_template(
        "viewdetails/index.html",
        file_name=filename,
        filesize=size,
        file_ext=extension,
        days_to_expire=str(days_to_expire) + "روز دیگر ",
    )





@app.route("/download/<unique_id>")
def download(unique_id):
    # Check if the unique ID exists in the database
    db  = sqlite3.connect(os.getenv('SQLITE3DBNAME'))
    cursor = db.cursor()

    cursor.execute("SELECT url, expiry_date FROM nimbaha WHERE id = ?", (unique_id,))
    url_and_expiry_date = cursor.fetchone()
    db.close()
    
    if not url_and_expiry_date:
        return render_template("viewdetails/error.html", err_msg="لینک مورد نظر وجود ندارد")
    
    # Check if the expiry date has passed
    url, expiry_date = url_and_expiry_date
    expiry_date = datetime.datetime.strptime(expiry_date, "%Y-%m-%d %H:%M:%S.%f")
    if datetime.datetime.now() > expiry_date:
        return render_template("viewdetails/error.html", err_msg="زمان دانلود این لینک به اتمام رسیده")
        
    req = requests.get(url, stream=True, allow_redirects=True)

    def generate():
        for chunk in req.iter_content(chunk_size= 8 * 1024 * 1024):
            if chunk:
                yield chunk

    headers = dict(req.headers)
    # *************************** ONLY FOR PARSPACK ******************************
    # headers.pop("Content-Length", None)
    # **************************************************************************
    # headers["Accept-Ranges"] = "none"
    if not req.headers["content-type"].startswith("image/"):
        headers["Content-Disposition"] = "attachment; filename=" + os.path.basename(url)
    return Response(
        generate(), headers=headers, content_type=req.headers["content-type"]
    )


@app.route(os.getenv('ANALYTICSPATH'))
def display_data():
    db  = sqlite3.connect(os.getenv('SQLITE3DBNAME'))
    cursor = db.cursor()

    cursor.execute("SELECT * FROM nimbaha")
    data = cursor.fetchall()

    # Remove duplicates based on the 'url' column (assuming it's the second column)
    data = list(dict((x[1], x) for x in data).values())

    # Sort the data by filesize (assuming it's the fourth column)
    data.sort(key=lambda x: x[5], reverse=True)

    # Calculate the total size
    total_size = sum(row[3] for row in data)  # assuming 'filesize' is the fourth column

    db.close()

    # Convert size to KB, MB or GB
    if total_size < 1024**2:
        total_size = f"{total_size / 1024:.2f} KB"
    elif total_size < 1024**3:
        total_size = f"{total_size / 1024**2:.2f} MB"
    else:
        total_size = f"{total_size / 1024**3:.2f} GB"

    # Limit the length of the URL and filename, and add a prefix to the filesize
    for i in range(len(data)):
        id, url, filename, filesize, extension, expiry_date = data[i]
        display_url = url if len(url) <= 50 else url[:50] + "..."
        filename = filename if len(filename) <= 20 else filename[:20] + "..."
        if filesize < 1024**2:
            filesize = f"{filesize / 1024:.2f} KB"
        elif filesize < 1024**3:
            filesize = f"{filesize / 1024**2:.2f} MB"
        else:
            filesize = f"{filesize / 1024**3:.2f} GB"
        
        # Convert expiry_date from string to datetime
        expiry_date = datetime.datetime.strptime(expiry_date, "%Y-%m-%d %H:%M:%S.%f")
        expiry_date = expiry_date.replace(microsecond=0)
        
        data[i] = (id, display_url, url, filename, filesize, extension, expiry_date)

    # HTML template as a string
    template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Data</title>
        <link href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.0/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="bg-dark text-white">
        <div class="container">
            <div class="card bg-secondary text-white mb-3">
                <div class="card-body">
                    <h5 class="card-title">Total Size</h5>
                    <p class="card-text">{{ total_size }}</p>
                </div>
            </div>
            <table class="table table-dark">
                <thead>
                    <tr>
                        <th scope="col">ID</th>
                        <th scope="col">URL</th>
                        <th scope="col">Filename</th>
                        <th scope="col">Filesize</th>
                        <th scope="col">Extension</th>
                        <th scope="col">Expiry Date</th>
                    </tr>
                </thead>
                <tbody>
                    {% for row in data %}
                    <tr>
                        <td>{{ row[0] }}</td>
                        <td><a href="{{ row[2] }}" target="_blank">{{ row[1] }}</a></td>
                        <td>{{ row[3] }}</td>
                        <td>{{ row[4] }}</td>
                        <td>{{ row[5] }}</td>
                        <td>{{ row[6] }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        <script src="https://stackpath.bootstrapcdn.com/bootstrap/4.5.0/js/bootstrap.min.js"></script>
    </body>
    </html>
    """

    return render_template_string(template, data=data, total_size=total_size)



if __name__ == "__main__":
    checkdb()
    app.run(host="0.0.0.0", port=5288, threaded=True)
