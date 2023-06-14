import pandas as pd
import requests
import pandas_ta as ta
from flask import Flask, request
import os
from dotenv import load_dotenv
import json
import subprocess

load_dotenv()

app = Flask(__name__)

telegram_token = os.environ['TELEGRAM_TOKEN']
oanda_token = os.environ['OANDA_TOKEN']

def process_user_input(input_text):
    # Run your desired logic here using the user input
    # For example, you can run a shell command
    result = subprocess.run([input_text], capture_output=True, text=True)

    return result.stdout

def send_telegram_message(message, chat_id, reply_to_message_id=None):
    url = f'https://api.telegram.org/bot{telegram_token}/sendMessage'
    data = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'Markdown',
        'reply_to_message_id': reply_to_message_id
    }
    response = requests.post(url, json=data)
    return response.json()

def calculate_lot_size(margin_balance, risk_percentage, sl_pips):
    dollar_per_pips = 13
    risk_amount = margin_balance * risk_percentage / 100
    lot_size = round(risk_amount / (dollar_per_pips * sl_pips), 3)
    return lot_size

def calculate_indicators(data, lengths):
    # Calculation of indicators here
    indicators = {}
    for length in lengths:
        sma_column_name = f'SMA_{length}'
        data[sma_column_name] = ta.sma(data['close'], window=length)
        indicators[sma_column_name] = data[sma_column_name].iloc[-1]

        ema_column_name = f'EMA_{length}'
        data[ema_column_name] = ta.ema(data['close'], window=length)
        indicators[ema_column_name] = data[ema_column_name].iloc[-1]
    print(indicators)
    return indicators

def get_prices_from_list():
    with open('list.json') as file:
        instrument_list = json.load(file)
    prices = []
    base_url = 'https://api-fxtrade.oanda.com/v3/instruments'
    headers = {
        'Authorization': f'Bearer {oanda_token}'
    }
    for instrument in instrument_list:
        symbol = instrument['symbol']
        url = f'{base_url}/{symbol}/candles?count=1&granularity=M1'
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if 'candles' in data and len(data['candles']) > 0:
                close_price = data['candles'][0]['mid']['c']
                price_info = f"Symbol: {symbol}, Close Price: {close_price}"
            else:
                price_info = f"No price available for symbol: {symbol}"
        else:
            price_info = f"Failed to fetch price for symbol: {symbol}"
        prices.append(price_info)
        print(prices)
    return prices

def get_indicators(symbol, granularity):
    base_url = 'https://api-fxtrade.oanda.com/v3/instruments'
    headers = {
        'Authorization': f'Bearer {oanda_token}'
    }
    url = f'{base_url}/{symbol}/candles?count=200&granularity={granularity}'
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if 'candles' in data and len(data['candles']) > 0:
            df = pd.DataFrame(data['candles'])
            df['time'] = pd.to_datetime(df['time'])
            df.set_index('time', inplace=True)
            df.sort_index(ascending=True, inplace=True)
            df['close'] = df['mid'].apply(lambda x: float(x['c']))
            indicators = calculate_indicators(df, [5, 10, 14, 21, 34, 50, 100, 200])
            return indicators
    return None

@app.route('/', methods=['GET'])
def index():
    return 'worked'

@app.route('/command', methods=['GET', 'POST'])
def command():
    if request.method == 'POST':
        # Get the user input from the 'input_text' form field
        user_input = request.form['input_text']

        # Process the user input (e.g., run a shell command)
        result = process_user_input(user_input)

        return result

    return '''
        <form method="POST">
            <input type="text" name="input_text">
            <input type="submit" value="Submit">
        </form>
    '''

@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    data = request.json
    if 'message' in data:
        message = data['message']
        chat_id = message['chat']['id']
        message_id = message['message_id']
        if 'text' in message:
            text = message['text']
            if text == '/price':
                prices = get_prices_from_list()
                response_message = '\n'.join(prices)
                send_telegram_message(response_message, chat_id, reply_to_message_id=message_id)
            elif text.startswith('/mm'):
                params = text.split()[1:]
                if len(params) == 3:
                    try:
                        margin_balance = float(params[0])
                        risk_percentage = float(params[1].rstrip('%'))
                        sl_pips = int(params[2].rstrip('pips'))

                        lot_size = calculate_lot_size(margin_balance, risk_percentage, sl_pips)

                        response_message = f"Money management calculation result:\n\nMargin Balance: ${margin_balance}\nRisk Percentage: {risk_percentage}%\nSL Pips: {sl_pips}\nLot Size: {lot_size}"

                        send_telegram_message(response_message, chat_id, reply_to_message_id=message_id)
                    except ValueError:
                        error_message = "Invalid parameters. Please use numeric values for margin balance, risk percentage, and SL pips."
                        send_telegram_message(error_message, chat_id, reply_to_message_id=message_id)
                else:
                    error_message = "Invalid parameters. Please use the format `/mm margin_balance risk_percentage sl_pips`."
                    send_telegram_message(error_message, chat_id, reply_to_message_id=message_id)
            elif text == '/chatid':
                response_message = f"Your Chat ID is: {chat_id}"
                send_telegram_message(response_message, chat_id, reply_to_message_id=message_id)
            elif text.startswith('/indicator'):
                params = text.split()[1:]
                if len(params) == 2:
                    symbol = params[0]
                    granularity = params[1].upper()
                    indicators = get_indicators(symbol, granularity)
                    if indicators is not None:
                        indicators_info = "\n".join([f"{key}: {value}" for key, value in indicators.items()])
                        response_message = f"Indicators for {symbol} ({granularity}):\n\n{indicators_info}"
                    else:
                        response_message = f"No data available for symbol: {symbol}"
                    send_telegram_message(response_message, chat_id, reply_to_message_id=message_id)
                else:
                    error_message = "Invalid parameters. Please use the format `/indicator symbol granularity`."
                    send_telegram_message(error_message, chat_id, reply_to_message_id=message_id)

    return 'OK'

if __name__ == '__main__':
    app.run(debug=True)
