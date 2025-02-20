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

# 全局变量
users = {}  # 存储所有用户的字典，键为用户ID，值为 User 对象
acceptAPI = True  # 服务器开关，默认开启

# 定义 User 类
class User:
    def __init__(self, user_id, username, meter_id, dwelling_type, region, area):
        self.user_id = user_id
        self.username = username
        self.meter_id = meter_id
        self.dwelling_type = dwelling_type
        self.region = region
        self.area = area
        self.meter_readings = []

    def log_action(self, action, message):
        """
        记录用户操作日志。
        :param action: 操作类型（如 REGISTER, UPLOAD_READING）
        :param message: 日志消息
        """
        current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = (
            f"[{current_time}] [{action}] User ID: {self.user_id}, Meter ID: {self.meter_id}, "
            f"Username: {self.username}, Dwelling Type: {self.dwelling_type}, "
            f"Region: {self.region}, Area: {self.area} - {message}\n"
        )
        with open("app_log.txt", "a") as log_file:
            log_file.write(log_entry)

    def add_reading(self, reading, date):
        """
        添加电表读数。
        :param reading: 电表读数
        :param date: 日期
        :return: 如果添加成功返回 None，否则返回错误消息
        """
        if not self.meter_readings:
            current_time = f"{date} 01:00:00"
        else:
            last_reading_time = self.meter_readings[-1]['meter_update_time']
            current_time = (datetime.datetime.strptime(last_reading_time, '%Y-%m-%d %H:%M:%S') +
                           datetime.timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')

        if current_time > f"{date} 23:30:00":
            return "System maintenance in progress. Data upload is not allowed at this time."

        self.meter_readings.append({
            "meter_update_time": current_time,
            "reading": reading
        })

        self.log_action("UPLOAD_READING", f"Uploaded reading {reading} at {current_time}")

    def get_daily_readings(self, date):
        """
        获取某一天的所有电表读数。
        :param date: 日期
        :return: 该日期的所有电表读数
        """
        return [
            reading for reading in self.meter_readings
            if reading['meter_update_time'].startswith(date)
        ]

# 辅助函数
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
            existing_data[user_id]['meter_readings'].extend(data['meter_readings'])
        else:
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
    if os.path.exists('electricity_record.json'):
        with open('electricity_record.json', 'r') as file:
            existing_data = json.load(file)
    else:
        existing_data = {}

    lock = threading.Lock()
    threads = []

    for user_id, user in users.items():
        data = {
            "username": user.username,
            "meter_id": user.meter_id,
            "dwelling_type": user.dwelling_type,
            "region": user.region,
            "area": user.area,
            "meter_readings": user.meter_readings
        }
        t = threading.Thread(target=save_user_data, args=(user_id, data, existing_data, lock))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    with open('electricity_record.json', 'w') as file:
        json.dump(existing_data, file, indent=4)

    for user in users.values():
        user.meter_readings = []

    with open("app_log.txt", "w") as log_file:
        log_file.write("")

# Flask 路由
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
    user = User(unique_user_id, username, meter_id, dwelling_type, region, area)
    users[unique_user_id] = user

    user.log_action("REGISTER", f"Registered user {username} with meter {meter_id}")

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

        if user_id not in users or users[user_id].meter_id != meter_id:
            return render_template('reading.html', message="Invalid User ID or Meter ID")

        session['user_id'] = user_id
        session['meter_id'] = meter_id
        session['date'] = date

        return render_template(
            'upload_reading.html',
            user_id=user_id,
            meter_id=meter_id,
            date=date,
            latest_reading=users[user_id].meter_readings[-1] if users[user_id].meter_readings else None
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
    user = users[user_id]
    result = user.add_reading(reading, date)

    if result:
        return render_template(
            'upload_reading.html',
            user_id=user_id,
            meter_id=meter_id,
            date=date,
            latest_reading=user.meter_readings[-1] if user.meter_readings else None,
            message=result
        )

    return render_template(
        'upload_reading.html',
        user_id=user_id,
        meter_id=meter_id,
        date=date,
        latest_reading=user.meter_readings[-1],
        message=""
    )

@app.route('/stop_server', methods=['GET'])
def stop_server():
    global acceptAPI
    acceptAPI = False
    batch_job()
    acceptAPI = True
    return render_template('stop_server.html')

@app.route('/daily_query', methods=['GET', 'POST'])
def daily_query():
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        meter_id = request.form.get('meter_id')

        if not user_id or not meter_id:
            return render_template('daily_query.html', message="User ID and Meter ID are required!")

        if user_id not in users or users[user_id].meter_id != meter_id:
            return render_template('daily_query.html', message="Invalid User ID or Meter ID")

        user = users[user_id]
        if not user.meter_readings:
            return render_template('daily_query.html', message="No readings available for the selected user and meter")

        first_reading_time = user.meter_readings[0]['meter_update_time']
        date = first_reading_time.split(' ')[0]
        daily_readings = user.get_daily_readings(date)

        return render_template(
            'daily_query.html',
            user_id=user_id,
            meter_id=meter_id,
            daily_readings=daily_readings,
            message=""
        )

    return render_template('daily_query.html', message="")

@app.route('/history_query', methods=['GET', 'POST'])
def history_query():
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        meter_id = request.form.get('meter_id')
        query_date = request.form.get('date')

        if not user_id or not meter_id or not query_date:
            return render_template('history_query.html', message="User ID, Meter ID, and Date are required!")

        try:
            with open('electricity_record.json', 'r') as file:
                json_data = json.load(file)
        except FileNotFoundError:
            return render_template('history_query.html', message="No historical data available")

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
        # 获取用户输入的 User ID 和 Meter ID
        user_id = request.form.get('user_id')
        meter_id = request.form.get('meter_id')

        # 检查 User ID 和 Meter ID 是否为空
        if not user_id or not meter_id:
            return render_template('visualization.html', message="User ID and Meter ID are required!")

        try:
            # 读取电表数据文件
            with open('electricity_record.json', 'r') as file:
                json_data = json.load(file)
        except FileNotFoundError:
            return render_template('visualization.html', message="No historical data available")

        # 检查 User ID 和 Meter ID 是否匹配
        if user_id not in json_data or json_data[user_id]['user_info']['meter_id'] != meter_id:
            return render_template('visualization.html', message="Invalid User ID or Meter ID")

        # 获取电表读数数据
        meter_readings = json_data[user_id]['meter_readings']

        # 将数据转换为 DataFrame
        df = pd.DataFrame(meter_readings)
        df['meter_update_time'] = pd.to_datetime(df['meter_update_time'])
        df['date'] = df['meter_update_time'].dt.date

        # 按日期分组，计算每日的 01:00 和 23:30 读数以及总用电量
        daily_consumption = df.groupby('date').agg(
            reading_0100=pd.NamedAgg(column='reading', aggfunc=lambda x: x.iloc[0] if len(x) > 0 else None),
            reading_2330=pd.NamedAgg(column='reading', aggfunc=lambda x: x.iloc[-1] if len(x) > 0 else None)
        )
        daily_consumption['total_usage'] = daily_consumption['reading_2330'] - daily_consumption['reading_0100']

        # 将日期索引转换为列
        daily_consumption.reset_index(inplace=True)

        # 将 daily_consumption 转换为字典格式，方便传递给模板
        daily_consumption_dict = daily_consumption.to_dict(orient='records')

        # 生成每日用电趋势图
        plt.figure(figsize=(8, 4))
        plt.plot(daily_consumption['date'], daily_consumption['total_usage'], marker='o', linestyle='-', label="Total Consumption")
        plt.xlabel("Date")
        plt.ylabel("Electricity Consumption (kWh)")
        plt.title("Daily Electricity Consumption Trend")
        plt.legend()
        plt.grid(True)

        # 将图表转换为 base64 编码的图片
        line_chart = io.BytesIO()
        plt.savefig(line_chart, format='png')
        line_chart.seek(0)
        line_chart_base64 = base64.b64encode(line_chart.getvalue()).decode()
        return render_template('visualization.html',
                               user_id=user_id,
                               meter_id=meter_id,
                               daily_consumption=daily_consumption_dict,
                               line_chart=line_chart_base64,
                               message="")

    return render_template('visualization.html', message="")

if __name__ == '__main__':
    app.run(debug=True, threaded=True)