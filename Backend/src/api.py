﻿from datetime import datetime
from flask_cors import CORS, cross_origin
from flask import Flask, request, send_from_directory
import requests
import json
import uuid
from util import check_existing_token, convert_to_mysql_query, delete_from_DB, get_category_id,get_data_from_db, add_or_update_to_db, delete_from_DB, get_store_id, load_conf, load_db_conn

app = Flask(__name__, static_url_path='', static_folder='../webroot',)
cors = CORS(app, resources={r"/api/upload/*": {"origins": "*"}})
app.config['CORS_HEADERS'] = 'Content-Type'

cfg = None
api_token = None

@app.before_first_request
def first():
    global cfg
    global api_token
    cfg = load_conf()
    api_token = check_existing_token()

@app.route('/', methods=["GET"])
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/upload', methods=["POST","OPTIONS"])
@cross_origin(origin='*', headers=['Content-Type'])
def upload():
    if api_token != request.args['token']:
        return "Unthorized", 401

    file = request.files['file']
    file_name = file.filename 
    legacy_parser = request.args['legacy_parser']
    grayscale_image = request.args['grayscale_image']
    rotate_image = request.args['rotate_image']

    url = "http://" + str(cfg['parserIP']) +":" + str(cfg['parserPort']) +"/api/upload?access_token=" + str(cfg['parserToken']) +"&legacy_parser=" + legacy_parser + "&grayscale_image=" + grayscale_image + "&rotate_image=" + rotate_image + "&gaussian_blur=True&median_blur=True"

    upload = requests.post(url, files = {'file': (file_name, file)})

    if upload.status_code == 200:
        upload_response = json.dumps(upload.content.decode("utf8"))
        response_json = json.loads(upload_response)
        response_json = json.loads(response_json)

        # Replace " in Date
        if ('"' in response_json["receiptDate"]):
            response_json["receiptDate"] = response_json["receiptDate"].replace('"',"")

        # Create 4 digit year 
        if response_json["receiptDate"] != "null":
            year_string = response_json["receiptDate"].split(".")
            if len(year_string[2]) < 4:
                year_string[2] = "20" + year_string[2]
                response_json["receiptDate"] = year_string[0] + "." + year_string[1] + "." + year_string[2]

        conn, cursor = load_db_conn()
        for idx, article in enumerate(response_json["receiptItems"]):
            article = article[0]

            splitted_articles = article.split(' ')

            for article in splitted_articles:
                if len(article) > 3:
                    sql_query = "SELECT TOP 1 category FROM purchaseData where article_name like ? order by timestamp desc"
                    if cfg['dbMode'] == "mysql":
                        sql_query = convert_to_mysql_query(sql_query)

                    cursor.execute(sql_query, [f"%{article}%"])
                    row = cursor.fetchone()

                    if (row):
                        found_cat = row.category
                        copy_array = response_json["receiptItems"][idx]
                        copy_array.insert(2, found_cat)

                        response_json["receiptItems"][idx] = copy_array
                        break

        conn.close()
        return json.dumps(response_json)

    else:
        return "Error on upload", upload.status_code


@app.route('/api/getHistory', methods=["GET","OPTIONS"])
@cross_origin(origin='*', headers=['Content-Type'])
def get_history():
    if api_token != request.args['token']:
        return "Unthorized", 401

    conn, cursor = load_db_conn()
    history_json = []

    cursor.execute("select SUM(total) as totalSum, location, id, timestamp from purchaseData \
	                where id is not null \
                    GROUP BY timestamp, id, location \
                    ORDER BY timestamp desc")

    rows = cursor.fetchall()

    for row in rows:
        if cfg['dbMode'] == "mysql":
            add_json = {'location': row[1], 'totalSum': str(row[0]), 'timestamp': str(row[3]), 'id': row[2]}
        else:
            add_json = {'location': row.location, 'totalSum': str(row.totalSum), 'timestamp': str(row.timestamp), 'id': row.id}
        history_json.append(add_json)

    conn.close()

    return json.dumps(history_json)

@app.route('/api/getHistoryDetails', methods=["GET","OPTIONS"])
@cross_origin(origin='*', headers=['Content-Type'])
def get_history_details():
    if api_token != request.args['token']:
        return "Unthorized", 401

    store_name = request.args['storeName']
    receipt_total = request.args['receiptTotal']
    receipt_date = request.args['receiptDate']
    purchase_id = request.args['purchaseID']
    
    conn, cursor = load_db_conn()

    sql_query = "select article_name, total, category from purchaseData where id = ?"
    if cfg['dbMode'] == "mysql":
        sql_query = convert_to_mysql_query(sql_query)

    cursor.execute(sql_query, [purchase_id])
    
    purchase_details = {"storeName": store_name, "receiptTotal": receipt_total, "receiptDate": receipt_date, "purchaseID": purchase_id,"receiptItems": []}
    
    rows = cursor.fetchall()

    for row in rows:
        if cfg['dbMode'] == "mysql":
            add_json = [row[0], str(row[1]), row[2]]
        else:
            add_json = [row.article_name, str(row.total), row.category]

        purchase_details["receiptItems"].append(add_json)

    conn.close()

    return json.dumps(purchase_details)

@app.route('/api/getValue', methods=["GET","OPTIONS"])
@cross_origin(origin='*', headers=['Content-Type'])
def get_categories():
    if api_token != request.args['token']:
        return "Unthorized", 401

    get_values_from = request.args['getValuesFrom']

    ret_json = get_data_from_db(get_values_from)

    return json.dumps(ret_json, ensure_ascii=False)

@app.route('/api/addValue', methods=["POST","OPTIONS"])
@cross_origin(origin='*',headers=['Content-Type'])
def add_value():
    if api_token != request.args['token']:
        return "Unthorized", 401

    to_add_array = request.args['toAddArray']
    to_add_value = request.args['toAddValue']
    id = request.args['id']

    add_or_update_to_db(to_add_array, id,to_add_value)

    return "Done!"

@app.route('/api/deleteValue', methods=["POST","OPTIONS"])
@cross_origin(origin='*', headers=['Content-Type'])
def delete_value():
    if api_token != request.args['token']:
        return "Unthorized", 401

    table_name = request.args['tableName']
    id = request.args['id']

    delete_from_DB(table_name, id)

    return "Done!"

@app.route('/api/updateReceiptToDB', methods=["POST","OPTIONS"])
@cross_origin(origin='*', headers=['Content-Type'])
def update_receipt_to_db():
    if api_token != request.args['token']:
        return "Unthorized", 401

    post_string = json.dumps(request.get_json())
    post_json = json.loads(post_string)

    conn, cursor = load_db_conn()

    store_id = get_store_id(post_json["storeName"])
    receipt_date = post_json["receiptDate"]
    receipt_total = post_json["receiptTotal"]
    receipt_id = post_json["purchaseID"]

    receipt_date = datetime.strptime(receipt_date, "%d.%m.%Y")
    receipt_date = receipt_date.strftime("%m-%d-%Y")

    # Delete old values
    sql_query = "DELETE FROM receipts WHERE ID = ?"
    if cfg['dbMode'] == "mysql":
        sql_query = convert_to_mysql_query(sql_query)

    cursor.execute(sql_query, [receipt_id])

    sql_query = "DELETE FROM purchasesArticles WHERE ID = ?"
    if cfg['dbMode'] == "mysql":
        sql_query = convert_to_mysql_query(sql_query)
    cursor.execute(sql_query, [receipt_id])

    sql_query = "DELETE FROM items where id IN (select itemid from purchasesArticles where id = ?)"
    if cfg['dbMode'] == "mysql":
        sql_query = convert_to_mysql_query(sql_query)
    cursor.execute(sql_query, [receipt_id])

    # Write article positions
    for article in post_json["receiptItems"]:
        article_id = int(str(uuid.uuid1().int)[:8])
        article_name = article[1]
        article_sum = article[2]
        article_category_id = get_category_id(article[3])

        sql_query = "INSERT INTO items values (?,?,?,?)"
        if cfg['dbMode'] == "mysql":
            sql_query = convert_to_mysql_query(sql_query)
        cursor.execute(sql_query, [article_id, article_name, article_sum, article_category_id])

        sql_query = "INSERT INTO purchasesArticles values (?,?)"
        if cfg['dbMode'] == "mysql":
            sql_query = convert_to_mysql_query(sql_query)
        cursor.execute(sql_query, [receipt_id, article_id])

    # Write receipt summary
    if cfg['dbMode'] == "mysql":
        sql_query = "INSERT INTO receipts values (%s,%s,STR_TO_DATE(%s,'%m-%d-%Y'),%s,%s,%s)"
    else:
        sql_query = "INSERT INTO receipts values (?,?,?,?,?,?)"

    cursor.execute(sql_query, [receipt_id, store_id, receipt_date, receipt_total, None, receipt_id])
    
    conn.commit()
    conn.close()

    return "Done!"

@app.route('/api/writeReceiptToDB', methods=["POST","OPTIONS"])
@cross_origin(origin='*',headers=['Content-Type'])
def write_receipt_to_db():
    if api_token != request.args['token']:
        return "Unthorized", 401
        
    post_string = json.dumps(request.get_json())
    post_json = json.loads(post_string)

    conn, cursor = load_db_conn()

    store_id = get_store_id(post_json["storeName"])
    receipt_date = post_json["receiptDate"]
    receipt_total = post_json["receiptTotal"]
    receipt_id = int(str(uuid.uuid1().int)[:6])

    receipt_date = datetime.strptime(receipt_date, "%d.%m.%Y")
    receipt_date = receipt_date.strftime("%m-%d-%Y")

    # Write article positions
    for article in post_json["receiptItems"]:
        article_id = int(str(uuid.uuid1().int)[:8])
        article_name = article[1]
        article_sum = article[2]
        article_category_id = get_category_id(article[3])

        sql_query = "INSERT INTO items values (?,?,?,?)"
        if cfg['dbMode'] == "mysql":
            sql_query = convert_to_mysql_query(sql_query)
        cursor.execute(sql_query, [article_id, article_name, article_sum, article_category_id])

        sql_query = "INSERT INTO purchasesArticles values (?,?)"
        if cfg['dbMode'] == "mysql":
            sql_query = convert_to_mysql_query(sql_query)
        cursor.execute(sql_query, [receipt_id, article_id])

    # Write receipt summary
    if cfg['dbMode'] == "mysql":
        sql_query = "INSERT INTO receipts values (%s,%s,STR_TO_DATE(%s,'%m-%d-%Y'),%s,%s,%s)"
    else:
        sql_query = "INSERT INTO receipts values (?,?,?,?,?,?)"

    cursor.execute(sql_query, [receipt_id, store_id, receipt_date, receipt_total, None, receipt_id])

    conn.commit()
    conn.close()

    return "Done!"