import asyncio
import websockets
import simplejson as json
import hashlib
import time
import base64
import numpy as np
import pandas as pd

testnet = 'wss://test.deribit.com/ws/api/v1/'
mainnet = 'wss://www.deribit.com/ws/api/v1/'

access_key_testnet = 'JtzQtGWGg9ij'
secret_key_testnet = 'PIKU2WO6EIWKA7RCTDTZYUXQHQ3ACCFS'

access_key_mainnet = '4B16MPsdUujg8'
secret_key_mainnet = 'DO7F4AYSTVJ33J7KKLKRHIXEZR2YLIF2'

access_key = access_key_testnet
secret_key = access_key_mainnet

#risk calculation, in a future release these could all be pulled or calculated
call_strike = 3750.00
put_strike = 3500
increment_length = .50
manual_range = 125 #will be divided by increment length
contract_quantity = 50
USD_quantity = contract_quantity*10
deribit_order_limit = 80
trade_change_thresh = 1 #threshhold before outlier orders deleted and replaced in USD
initial_order_range = 10 #number of orders in initial spread in one direction
max_order_range = 20

def total_short_risk_calc(current_ask_price, call_strike, USD_quantity):
    USD_risk = 0
    contract_risk = 0

    short_position_length = max(call_strike - current_ask_price, manual_range)
    number_short_positions = round(short_position_length/increment_length)
    sum_range_shorts = range(0, int(number_short_positions))

    for i in sum_range_shorts:
        position_price = current_ask_price + float(i)*increment_length
        risk_exit_price = max(call_strike, current_ask_price + max(sum_range_shorts))
        contract_risk += ((position_price - risk_exit_price)/position_price)
    USD_risk = USD_quantity*contract_risk
    return USD_risk, number_short_positions

def total_long_risk_calc(current_bid_price, put_strike, USD_quantity):
    USD_risk = 0
    contract_risk = 0

    long_position_length = max(current_bid_price - put_strike, manual_range)
    number_long_positions = round(long_position_length/increment_length)
    sum_range_longs = range(0, int(number_long_positions))

    for i in sum_range_longs:
        position_price = current_bid_price - float(i)*increment_length
        risk_exit_price = min(put_strike, current_bid_price - max(sum_range_longs))
        contract_risk += ((risk_exit_price - position_price)/position_price)
    USD_risk = USD_quantity*contract_risk
    return USD_risk, number_long_positions

def get_signature(action, arguments):
    nonce = str(int(time.time() * 1000))

    signature_string = '_=%s&_ackey=%s&_acsec=%s&_action=%s' % (
        nonce, access_key_testnet, secret_key_testnet, action
    )

    for key in sorted(arguments.keys()):
        signature_string += "&" + key + "=" + arguments[key]

    return '%s.%s.%s' % (access_key, nonce, base64.b64encode(hashlib.sha256(signature_string.encode("utf-8")).digest()).decode())

def create_public_websocket_message(id, action, arguments):
    msg = \
        {
            "id": id,
            "action": action,
            "arguments": arguments
        }
    return msg

def create_private_websocket_message(id, action, arguments):
    signature = get_signature(action, arguments)
    msg = \
        {
            "id": id,
            "action": action,
            "arguments": arguments,
            "sig": signature,
        }
    return msg

def create_order_range_lists(order_book, number_long_positions, number_short_positions, interval):
    buy_price_list = []
    sell_price_list = []
    initial_buy_price = order_book["result"]["bids"][0]["price"]
    initial_sell_price = order_book["result"]["asks"][0]["price"]

    for i in range(0, number_long_positions):
        buy_price_list.append(str(initial_buy_price - interval*i))

    for i in range(0, number_short_positions):
        sell_price_list.append(str(initial_sell_price + interval*i))

    return buy_price_list, sell_price_list

def create_id_value(action_id_number):
    action_id_number += 1
    ID = str(action_id_number) + "dagorillaoskrilla"
    return ID, action_id_number

def get_number_of_open_buy_orders(open_orders_response):
    number_of_open_buy_orders = 0
    for order in json.loads(open_orders_response)["result"]:
        if order["direction"] == "buy":
            number_of_open_buy_orders += 1
    return number_of_open_buy_orders

def get_number_of_open_sell_orders(open_orders_response):
    number_of_open_sell_orders = 0
    for order in json.loads(open_orders_response)["result"]:
        if order["direction"] == "buy":
            number_of_open_sell_orders += 1
    return number_of_open_sell_orders

#Construct different messages
private_buy_action = "/api/v1/private/buy"
private_sell_action = "/api/v1/private/sell"
instrument = "BTC-PERPETUAL"
quantity = str(USD_quantity)
type = "limit"
max_show = quantity
post_only = "true"

def create_private_order_arguments(instrument, quantity, type, label, price, max_show, post_only = "true"):
    args = {
        "instrument": instrument,
        "quantity": quantity,
        "type": type,
        "label": label,
        "price": price,
        "max_show": max_show,
        "post_only": post_only
        }
    return args

get_order_book_action = "/api/v1/public/getorderbook"
depth = 5
def create_get_order_book_arguments(instrument, depth):
    args = {
        "instrument": instrument,
        "depth": depth
        }
    return args

get_trade_history_action = "/api/v1/private/tradehistory"
count = "5"
def create_get_trade_history_arguments(instrument, count, startTimestamp):
    args = {
        "instrument": instrument,
        "count": count,
        "startTimestamp": startTimestamp
        }
    return args

get_open_orders_action = "/api/v1/private/getopenorders"
def create_get_open_orders_arguments(instrument):
    args = {
        "instrument": instrument,
        }
    return args

cancel_order_action = "/api/v1/private/cancel"
def create_cancel_order_arguments(orderId):
    args = {
        "orderId": orderId,
        }
    return args

def create_get_time_msg():
    msg = {
        "action": "/api/v1/public/time"
        }
    return msg

async def market_maker_loop(websocket):
    x = 0
    while x < 1:
        global action_id_number
        global timestamp
        global equilibrium_bid_price
        global equilibrium_ask_price

        #init vars
        action_id_number = action_id_number
        timestamp = timestamp
        equilibrium_bid_price = equilibrium_bid_price
        equilibrium_ask_price = equilibrium_ask_price

        #get trade history
        action_id, action_id_number = create_id_value(action_id_number)
        get_trade_history_args = create_get_trade_history_arguments(instrument, count, timestamp)
        get_trade_history_msg = create_private_websocket_message(action_id, get_trade_history_action, get_trade_history_args)

        await websocket.send(json.dumps(get_trade_history_msg))
        trade_history = await websocket.recv()
        trade_history_object = json.loads(trade_history)

        #if there was a trade then apply logic
        if len(trade_history_object["result"]) > 0:
            #print(trade_history)

            timestamp = str(trade_history_object["result"][-1]["timeStamp"] + 1)
            balance_step_interval = increment_length

            #find balance for the executed trades
            for trade in trade_history_object["result"]:

                #handle buy order balance
                if trade["side"] == "buy":

                    # balance sell order args
                    balance_trade_price = str(trade["price"] + balance_step_interval)
                    balance_quantity = str(trade["quantity"])
                    if "balance" in trade["label"]:
                        balance_trade_label = trade["label"].strip("balancebuy_")
                    else:
                        balance_trade_label = "balancesell_" + trade["label"]
                    sell_order_args = create_private_order_arguments(instrument, balance_quantity, type, balance_trade_label, balance_trade_price, max_show, post_only)

                    #create balance sell order
                    action_id, action_id_number = create_id_value(action_id_number)
                    place_balance_sell_order_msg = create_private_websocket_message(action_id, private_sell_action, sell_order_args)

                    #place balance sell order
                    await websocket.send(json.dumps(place_balance_sell_order_msg))
                    balance_sell_order = await websocket.recv()

                    try:
                        print(json.loads(balance_sell_order)["result"]["order"]["label"])

                    except:
                        print("Key Error!")
                        print(balance_sell_order)
                        exit()


                elif trade["side"] == "sell":

                    # balance buy order args
                    balance_trade_price = str(trade["price"] - balance_step_interval)
                    balance_quantity = str(trade["quantity"])
                    if "balance" in trade["label"]:
                        balance_trade_label = "b" + trade["label"].strip("balancesell_")
                    else:
                        balance_trade_label = "balancebuy_" + trade["label"]
                    buy_order_args = create_private_order_arguments(instrument, balance_quantity, type, balance_trade_label, balance_trade_price, max_show, post_only)

                    #create balance buy order
                    action_id, action_id_number = create_id_value(action_id_number)
                    place_balance_buy_order_msg = create_private_websocket_message(action_id, private_buy_action, buy_order_args)

                    #place balance buy order
                    await websocket.send(json.dumps(place_balance_buy_order_msg))
                    balance_buy_order = await websocket.recv()

                    try:
                        print(json.loads(balance_buy_order)["result"]["order"]["label"])

                    except:
                        print("Key Error!")
                        print(balance_buy_order)
                        exit()

                else:
                    raise ValueError("Somehow a trade that is neither buy nor sell")

            #check if price has moved from previous "equilibrium" then apply appropriate logic
            #if price has drifted up beyond trade thresh then delete low buy orders and place upward sell orders
            if trade_history_object["result"][-1]["price"] - equilibrium_ask_price > trade_change_thresh:
                #create open orders df
                open_orders_args = create_get_open_orders_arguments(instrument)
                action_id, action_id_number = create_id_value(action_id_number)
                get_open_orders_msg = create_private_websocket_message(action_id, get_open_orders_action, open_orders_args)

                await websocket.send(json.dumps(get_open_orders_msg))
                open_orders_response = await websocket.recv()

                #calculate number of sell orders currently open
                number_of_open_sell_orders = get_number_of_open_sell_orders(open_orders_response)

                print("number of open sell orders is " + str(number_of_open_sell_orders))

                open_orders = pd.DataFrame(json.loads(open_orders_response)["result"])
#
#                distance = round(trade_history_object["result"][-1]["price"] - equilibrium_ask_price)
#                open_orders["price"] = open_orders["price"].astype(float)
#                open_orders["orderId"] = open_orders["orderId"].astype(int)
#
#                #cancel lowest buy orders out of price range
#                orders_to_cancel = open_orders[open_orders["price"] < min(open_orders["price"]) + distance]
#                for i, order in orders_to_cancel.iterrows():
#                    action_id, action_id_number = create_id_value(action_id_number)
#                    cancel_order_args = create_cancel_order_arguments(str(order["orderId"]))
#                    cancel_order_msg = create_private_websocket_message(action_id, cancel_order_action, cancel_order_args)
#
#                    await websocket.send(json.dumps(cancel_order_msg))
#                    cancel_order = await websocket.recv()
#                    print(cancel_order)

                #replace with sell orders at the top of the range
                how_many_orders_to_place =  initial_order_range - number_of_open_sell_orders
                print("the diff between initial range and number of open sells is :" + str(number_of_open_sell_orders))
                if how_many_orders_to_place > 0:

                    for i in range(0, how_many_orders_to_place):
                        sell_order_label = "sellordercor" + str(i)
                        sell_order_price = str(max(open_orders["price"]) + (i+1)*increment_length)
                        sell_order_args = create_private_order_arguments(instrument, quantity, type, sell_order_label, sell_order_price, max_show, post_only)

                        action_id, action_id_number = create_id_value(action_id_number)
                        place_sell_order_msg = create_private_websocket_message(action_id, private_sell_action, sell_order_args)

                        await websocket.send(json.dumps(place_sell_order_msg))
                        sell_order = await websocket.recv()
                        try:
                            print(json.loads(sell_order)["result"]["order"]["label"])

                        except:
                            print("Key Error!")
                            print(sell_order)
                            exit()

                action_id, action_id_number = create_id_value(action_id_number)
                get_order_book_arguments = create_get_order_book_arguments(instrument, depth)
                get_order_book_msg = create_public_websocket_message(action_id, get_order_book_action, get_order_book_arguments)

                #get order book
                await websocket.send(json.dumps(get_order_book_msg))
                order_book = await websocket.recv()
                equilibrium_ask_price = json.loads(order_book)["result"]["asks"][0]["price"]

            #if price has drifted down beyond thresh then delete highest sell orders and replace with new low buy orders
            if equilibrium_bid_price - trade_history_object["result"][-1]["price"] > trade_change_thresh:
                #create open orders df
                open_orders_args = create_get_open_orders_arguments(instrument)
                action_id, action_id_number = create_id_value(action_id_number)
                get_open_orders_msg = create_private_websocket_message(action_id, get_open_orders_action, open_orders_args)

                await websocket.send(json.dumps(get_open_orders_msg))
                open_orders_response = await websocket.recv()

                #calculate number of buy orders currently open
                number_of_open_buy_orders = get_number_of_open_buy_orders(open_orders_response)

                print("number of open buy orders is " + str(number_of_open_buy_orders))

                open_orders = pd.DataFrame(json.loads(open_orders_response)["result"])

#                distance = round(equilibrium_bid_price - trade_history_object["result"][-1]["price"])
#                open_orders["price"] = open_orders["price"].astype(float)
#                open_orders["orderId"] = open_orders["orderId"].astype(int)
#
#                #cancel highest sell orders
#                orders_to_cancel = open_orders[open_orders["price"] > max(open_orders["price"]) - distance]
#                for i, order in orders_to_cancel.iterrows():
#                    action_id, action_id_number = create_id_value(action_id_number)
#                    cancel_order_args = create_cancel_order_arguments(str(order["orderId"]))
#                    cancel_order_msg = create_private_websocket_message(action_id, cancel_order_action, cancel_order_args)
#
                #    await websocket.send(json.dumps(cancel_order_msg))
                #    cancel_order = await websocket.recv()
                #    print(cancel_order)

                #replace with new low buy orders
                how_many_orders_to_place = initial_order_range - number_of_open_buy_orders
                print("the diff between initial range and number of open buys is :" + str(number_of_open_buy_orders))
                if how_many_orders_to_place > 0:
                    for i in range(0, how_many_orders_to_place):
                        buy_order_label = "buyordercor" + str(i)
                        buy_order_price = str(min(open_orders["price"]) - (i+1)*increment_length)
                        buy_order_args = create_private_order_arguments(instrument, quantity, type, buy_order_label, buy_order_price, max_show, post_only)

                        action_id, action_id_number = create_id_value(action_id_number)
                        place_buy_order_msg = create_private_websocket_message(action_id, private_buy_action, buy_order_args)

                        await websocket.send(json.dumps(place_buy_order_msg))
                        buy_order = await websocket.recv()

                        try:
                            print(json.loads(buy_order)["result"]["order"]["label"])

                        except KeyError:
                            print("Key Error!")
                            print(buy_order)
                            exit()

                    action_id, action_id_number = create_id_value(action_id_number)
                    get_order_book_arguments = create_get_order_book_arguments(instrument, depth)
                    get_order_book_msg = create_public_websocket_message(action_id, get_order_book_action, get_order_book_arguments)

                    #get order book
                    await websocket.send(json.dumps(get_order_book_msg))
                    order_book = await websocket.recv()
                    equilibrium_bid_price = json.loads(order_book)["result"]["bids"][0]["price"]

            #canceling all orders outside of range
            #create open orders df
            open_orders_args = create_get_open_orders_arguments(instrument)
            action_id, action_id_number = create_id_value(action_id_number)
            get_open_orders_msg = create_private_websocket_message(action_id, get_open_orders_action, open_orders_args)

            await websocket.send(json.dumps(get_open_orders_msg))
            open_orders_response = await websocket.recv()

            open_orders = pd.DataFrame(json.loads(open_orders_response)["result"])
            open_orders["price"] = open_orders["price"].astype(float)
            open_orders["orderId"] = open_orders["orderId"].astype(int)

            #cancel highest sell orders
            orders_to_cancel = open_orders[(open_orders["price"] > equilibrium_ask_price + max_order_range*increment_length) | (open_orders["price"] < equilibrium_bid_price - max_order_range*increment_length)]
            for i, order in orders_to_cancel.iterrows():
                action_id, action_id_number = create_id_value(action_id_number)
                cancel_order_args = create_cancel_order_arguments(str(order["orderId"]))
                cancel_order_msg = create_private_websocket_message(action_id, cancel_order_action, cancel_order_args)

                await websocket.send(json.dumps(cancel_order_msg))
                cancel_order = await websocket.recv()
                print(cancel_order)

async def initial_api_call():
    async with websockets.connect(testnet) as websocket:
        while websocket.open:
            global action_id_number
            global timestamp
            global equilibrium_bid_price
            global equilibrium_ask_price

            #get time
            get_time_msg_one = create_get_time_msg()
            await websocket.send(json.dumps(get_time_msg_one))
            current_time_response = await websocket.recv()
            start_timestamp = str(json.loads(current_time_response)["result"])
            print("The startin' time is " + start_timestamp)

            #create message to get orderbook
            action_id_number = 0
            action_id, action_id_number = create_id_value(action_id_number)
            get_order_book_arguments = create_get_order_book_arguments(instrument, depth)
            get_order_book_msg = create_public_websocket_message(action_id, get_order_book_action, get_order_book_arguments)

            #get order book
            await websocket.send(json.dumps(get_order_book_msg))
            order_book = await websocket.recv()
            print(order_book)

            #create price range lists
            equilibrium_bid_price = json.loads(order_book)["result"]["bids"][0]["price"]
            equilibrium_ask_price = json.loads(order_book)["result"]["asks"][0]["price"]
            total_USD_short_risk, number_short_positions = total_short_risk_calc(equilibrium_ask_price, call_strike, USD_quantity)
            total_USD_long_risk, number_long_positions = total_long_risk_calc(equilibrium_bid_price, put_strike, USD_quantity)
            buy_price_list, sell_price_list = create_order_range_lists(json.loads(order_book), number_long_positions, number_short_positions, increment_length)

            print("Total USD short risk if realized: " + str(total_USD_short_risk))
            print("Total USD long risk if realized: " + str(total_USD_long_risk))

            #place initial orders orders
            for i in range(0, initial_order_range):              #round(deribit_order_limit/2)):
                buy_order_label = "buyorder" + str(i)
                sell_order_label = "sellorder" + str(i)

                buy_order_args = create_private_order_arguments(instrument, quantity, type, buy_order_label, buy_price_list[i], max_show, post_only)
                sell_order_args = create_private_order_arguments(instrument, quantity, type, sell_order_label, sell_price_list[i], max_show, post_only)

                action_id, action_id_number = create_id_value(action_id_number)
                place_buy_order_msg = create_private_websocket_message(action_id, private_buy_action, buy_order_args)

                action_id, action_id_number = create_id_value(action_id_number)
                place_sell_order_msg = create_private_websocket_message(action_id, private_sell_action, sell_order_args)

                await websocket.send(json.dumps(place_buy_order_msg))
                buy_order = await websocket.recv()

                await websocket.send(json.dumps(place_sell_order_msg))
                sell_order = await websocket.recv()

                if i % 5 == 0:
                    print(str(i) + " orders placed in each direction")

            #look for a trade to execute
            print("number of actions so far: " + str(action_id_number))
            timestamp = start_timestamp
            await market_maker_loop(websocket)


                    #elif action_id_number > 500:
                    #    x = 1

            #close websocket
            await websocket.close()

async def reconnect_api_call():
    async with websockets.connect(testnet) as websocket:
        while websocket.open:
            print("Reconnected")
            await market_maker_loop(websocket)


try:
    asyncio.get_event_loop().run_until_complete(initial_api_call())

except websockets.ConnectionClosed:
    print("Connection Lost")

    y = 1
    while y > 0:

        try:
            print("Reconnecting...")
            asyncio.get_event_loop().run_until_complete(reconnect_api_call())

        except websockets.ConnectionClosed:
            print("Conncetion Lost")
