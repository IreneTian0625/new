from flask import Flask, render_template, request, session, redirect, url_for
import random
import datetime
import threading
import json
import os
import matplotlib.pyplot as plt
import pandas as pd
import io
import base64

app = Flask(__name__)
app.secret_key = "your_secret_key"
user_data = {}
users_completed = set()
acceptAPI = True  # 服务器开关，默认开启

def log_action(action, user_id, message):
    current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 获取 meter_id
    meter_id = user_data.get(user_id, {}).get('meter_id', 'Unknown')
    
    # 根据 action 类型生成日志条目
    if action == "REGISTER":
        # 获取用户注册时的详细信息
        username = user_data.get(user_id, {}).get('username', 'Unknown')
        dwelling_type = user_data.get(user_id, {}).get('dwelling_type', 'Unknown')
        region = user_data.get(user_id, {}).get('region', 'Unknown')
        area = user_data.get(user_id, {}).get('area', 'Unknown')
        
        # 生成注册日志条目
        log_entry = (
            f"[{current_time}] [{action}] User ID: {user_id}, Meter ID: {meter_id}, "
            f"Username: {username}, Dwelling Type: {dwelling_type}, "
            f"Region: {region}, Area: {area} - {message}\n"
        )
    else:
        log_entry = f"[{current_time}] [{action}] User ID: {user_id}, Meter ID: {meter_id} - {message}\n"
    
    # 将日志写入本地文件
    with open("app_log.txt", "a") as log_file:
        log_file.write(log_entry)


def save_user_data(user_id, data, existing_data, lock):
    """
    将单个用户的数据保存到 existing_data 中。
    :param user_id: 用户 ID
    :param data: 用户数据
    :param existing_data: 现有的 JSON 数据
    :param lock: 线程锁，用于确保线程安全
    """
    with lock:
        if user_id in existing_data:
            # 如果用户已存在，追加新的读数
            existing_data[user_id]['meter_readings'].extend(data['meter_readings'])
        else:
            # 如果用户不存在，创建新的条目
            existing_data[user_id] = {
                "user_info": {
                    "user_id": user_id,
                    "username": data['username'],
                    "meter_id": data['meter_id'],
                    "dwelling_type": data['dwelling_type'],
                    "region": data['region'],
                    "area": data['area'],
                },
                "meter_readings": data['meter_readings']
            }

def batch_job():
    """
    批处理任务，使用多线程处理每个用户的数据。
    """
    # 加载现有的 JSON 数据（如果文件存在）
    if os.path.exists('electricity_record.json'):
        with open('electricity_record.json', 'r') as file:
            existing_data = json.load(file)
    else:
        existing_data = {}

    # 创建线程锁，确保线程安全
    lock = threading.Lock()

    # 创建线程列表
    threads = []

    # 遍历所有用户，为每个用户创建一个线程
    for user_id, data in user_data.items():
        # 创建线程，目标函数是 save_user_data
        t = threading.Thread(target=save_user_data, args=(user_id, data, existing_data, lock))
        threads.append(t)
        t.start()

    # 等待所有线程完成
    for t in threads:
        t.join()

    # 将更新后的数据写入 JSON 文件
    with open('electricity_record.json', 'w') as file:
        json.dump(existing_data, file, indent=4)

    # 清空当天的读数数据
    for user_id in user_data:
        user_data[user_id]['meter_readings'] = []

    # 清空日志文件
    with open("app_log.txt", "w") as log_file:
        log_file.write("")

@app.route('/')
def main_page():
    return render_template('main.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    return render_template('register.html', message="")

@app.route('/register_result', methods=['POST'])
def register_result():
    username = request.form.get('user_name').strip()
    meter_id = request.form.get('meter_id').strip()
    dwelling_type = request.form.get('dwelling_type').strip()
    region = request.form.get('region').strip()
    area = request.form.get('area').strip()

    if not all([username, meter_id, dwelling_type, region, area]):
        return render_template('register.html', message="All fields are required!")

    unique_user_id = str(random.randint(100000, 999999))
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    start_time_str = f"{today} 01:00:00"

    user_data[unique_user_id] = {
        "user_id": unique_user_id,
        "username": username,
        "meter_id": meter_id,
        "dwelling_type": dwelling_type,
        "region": region,
        "area": area,
        "meter_readings": [],
        "next_meter_update_time": start_time_str
    }

    # 记录注册日志
    log_action("REGISTER", unique_user_id, f"Registered user {username} with meter {meter_id}")

    return render_template(
        'register_result.html',
        message=f"Successfully registered!",
        user_id=unique_user_id,
        username=username,
        meter_id=meter_id,
        dwelling_type=dwelling_type,
        region=region,
        area=area
    )

@app.route('/reading', methods=['GET'])
def reading():
    return render_template('reading.html', message="")

@app.route('/upload_reading', methods=['GET', 'POST'])
def upload_reading():
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        meter_id = request.form.get('meter_id')
        date = request.form.get('date')

        if user_id not in user_data or user_data[user_id]['meter_id'] != meter_id:
            return render_template('reading.html', message="Invalid User ID or Meter ID")

        session['user_id'] = user_id
        session['meter_id'] = meter_id
        session['date'] = date

        return render_template(
            'upload_reading.html',
            user_id=user_id,
            meter_id=meter_id,
            date=date,
            latest_reading=user_data[user_id]['meter_readings'][-1] if user_data[user_id]['meter_readings'] else None
        )

    return redirect(url_for('main_page'))

@app.route('/submit_reading', methods=['POST'])
def submit_reading():
    user_id = session.get('user_id')
    meter_id = session.get('meter_id')
    date = session.get('date')

    if not user_id or not meter_id or not date:
        return "Session expired or invalid request", 400

    reading = float(request.form.get('reading'))

    if not user_data[user_id]['meter_readings']:
        current_time = f"{date} 01:00:00"
    else:
        last_reading_time = user_data[user_id]['meter_readings'][-1]['meter_update_time']
        current_time = (datetime.datetime.strptime(last_reading_time, '%Y-%m-%d %H:%M:%S') +
                       datetime.timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')

    if current_time > f"{date} 23:30:00":
        return render_template(
            'upload_reading.html',
            user_id=user_id,
            meter_id=meter_id,
            date=date,
            latest_reading=user_data[user_id]['meter_readings'][-1] if user_data[user_id]['meter_readings'] else None,
            message="System maintenance in progress. Data upload is not allowed at this time."
        )

    user_data[user_id]['meter_readings'].append({
        "meter_update_time": current_time,
        "reading": reading
    })

    user_data[user_id]['next_meter_update_time'] = current_time

    # 记录上传读数日志
    log_action("UPLOAD_READING", user_id, f"Uploaded reading {reading} at {current_time}")

    latest_reading = user_data[user_id]['meter_readings'][-1] if user_data[user_id]['meter_readings'] else None

    return render_template(
        'upload_reading.html',
        user_id=user_id,
        meter_id=meter_id,
        date=date,
        latest_reading=latest_reading,
        message=""
    )

@app.route('/stop_server', methods=['GET'])
def stop_server():
    global acceptAPI
    acceptAPI = False  # 关闭服务器，拒绝新的 API 请求
    batch_job()  # 执行批处理作业
    acceptAPI = True  # 恢复服务器
    return render_template('stop_server.html')

@app.route('/daily_query', methods=['GET', 'POST'])
def daily_query():
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        meter_id = request.form.get('meter_id')

        if not user_id or not meter_id:
            return render_template('daily_query.html', message="User ID and Meter ID are required!")

        if user_id not in user_data or user_data[user_id]['meter_id'] != meter_id:
            return render_template('daily_query.html', message="Invalid User ID or Meter ID")

        if user_data[user_id]['meter_readings']:
            first_reading_time = user_data[user_id]['meter_readings'][0]['meter_update_time']
            date = first_reading_time.split(' ')[0]
        else:
            return render_template('daily_query.html', message="No readings available for the selected user and meter")

        daily_readings = [
            reading for reading in user_data[user_id]['meter_readings']
            if reading['meter_update_time'].startswith(date)
        ]

        return render_template(
            'daily_query.html',
            user_id=user_id,
            meter_id=meter_id,
            daily_readings=daily_readings,
            message=""
        )

    return render_template('daily_query.html', message="")

def load_json_data():
    try:
        with open('electricity_record.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

@app.route('/history_query', methods=['GET', 'POST'])
def history_query():
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        meter_id = request.form.get('meter_id')
        query_date = request.form.get('date')

        if not user_id or not meter_id or not query_date:
            return render_template('history_query.html', message="User ID, Meter ID, and Date are required!")

        json_data = load_json_data()

        if user_id not in json_data:
            return render_template('history_query.html', message="Invalid User ID")

        if json_data[user_id]['user_info']['meter_id'] != meter_id:
            return render_template('history_query.html', message="Invalid Meter ID")

        daily_readings = [
            reading for reading in json_data[user_id]['meter_readings']
            if reading['meter_update_time'].startswith(query_date)
        ]

        if not daily_readings:
            return render_template('history_query.html', message=f"No data available for the date: {query_date}")

        reading_0100 = next(
            (reading['reading'] for reading in daily_readings if reading['meter_update_time'].endswith('01:00:00')),
            None
        )
        reading_2330 = next(
            (reading['reading'] for reading in daily_readings if reading['meter_update_time'].endswith('23:30:00')),
            None
        )

        if not reading_0100 or not reading_2330:
            return render_template('history_query.html', message=f"Incomplete data for the date: {query_date}")

        total_usage = reading_2330 - reading_0100

        query_result = {
            "date": query_date,
            "reading_0100": reading_0100,
            "reading_2330": reading_2330,
            "total_usage": total_usage
        }

        return render_template(
            'history_query.html',
            user_id=user_id,
            meter_id=meter_id,
            query_result=query_result,
            message=""
        )

    return render_template('history_query.html', message="")

@app.route('/visualization', methods=['GET', 'POST'])
def visualization():
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        meter_id = request.form.get('meter_id')

        if not user_id or not meter_id:
            return render_template('visualization.html', message="User ID and Meter ID are required!")

        json_data = load_json_data()

        if user_id not in json_data or json_data[user_id]['user_info']['meter_id'] != meter_id:
            return render_template('visualization.html', message="Invalid User ID or Meter ID")

        meter_readings = json_data[user_id]['meter_readings']

        df = pd.DataFrame(meter_readings)
        df['meter_update_time'] = pd.to_datetime(df['meter_update_time'])
        df['date'] = df['meter_update_time'].dt.date

        daily_consumption = df.groupby('date').agg(
        reading_0100=pd.NamedAgg(column='reading', aggfunc=lambda x: x.iloc[0] if len(x) > 0 else None),
        reading_2330=pd.NamedAgg(column='reading', aggfunc=lambda x: x.iloc[-1] if len(x) > 0 else None)
        )
        daily_consumption['total_usage'] = daily_consumption['reading_2330'] - daily_consumption['reading_0100']

        daily_consumption.index = daily_consumption.index.astype(str)

        plt.figure(figsize=(8, 4))
        plt.plot(daily_consumption.index, daily_consumption['total_usage'], marker='o', linestyle='-', label="Total Consumption")
        plt.xlabel("Date")
        plt.ylabel("Electricity Consumption (kWh)")
        plt.title("Daily Electricity Consumption Trend")
        plt.legend()
        plt.grid(True)

        line_chart = io.BytesIO()
        plt.savefig(line_chart, format='png')
        line_chart.seek(0)
        line_chart_base64 = base64.b64encode(line_chart.getvalue()).decode()

        return render_template('visualization.html',
                               user_id=user_id,
                               meter_id=meter_id,
                               daily_consumption=daily_consumption.to_dict(orient='records'),
                               line_chart=line_chart_base64,
                               message="")

    return render_template('visualization.html', message="")

if __name__ == '__main__':
    app.run(debug=True, threaded=True)