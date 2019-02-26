import asyncio
import websockets
import simplejson as json

authentication_msg = \
    {"jsonrpc": "2.0",
     "method": "public/auth",
     "id": "dagorillaoskrilla_authentication",
     "params": {
        "grant_type": "client_credentials",
        "client_id": "JtzQtGWGg9ij",
        "client_secret": "PIKU2WO6EIWKA7RCTDTZYUXQHQ3ACCFS",
        "scope": "connection"}
    }

def set_refresh_authentication_msg(refresh_token):
    authentication_msg = \
        {"jsonrpc": "2.0",
         "method": "public/auth",
         "id": "dagorillaoskrilla_authentication",
         "params": {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            }
        }
    return authentication_msg

get_order_book_msg = \
    {"jsonrpc": "2.0",
     "method": "public/get_order_book",
     "id": "dagorillaoskrilla_initial_order_book",
     "params": {
        "instrument_name": "BTC-PERPETUAL",
        "depth": 3}
    }

get_time_msg = \
    {"jsonrpc": "2.0",
     "method": "public/get_time",
     "id": 42
    }

def create_order_range_lists(buy_price_list, ask_price_list, max_range):
    for i in range(1,max_range):
        buy_price_list.append(buy_price_list[i-1] - .50)
        ask_price_list.append(ask_price_list[i-1] + .50)

    return buy_price_list, ask_price_list

def set_public_subscribe_msg(channels):
    msg = \
        {"jsonrpc": "2.0",
            "method": "public/subscribe",
            "id": "dagorillaoskrilla_subscriptions",
            "params": {
            "channels": channels}
        }
    return msg

def set_get_user_trades_msg(access_token, instrument, start_timestamp, count):

    user_trades_msg = \
        {"jsonrpc": "2.0",
         "method": "private/get_user_trades_by_instrument_and_time",
         "id": "user_trades_dagorillaoskrilla",
         "params": {
            "access_token": access_token,
            "instrument_name": instrument,
            "start_timestamp": start_timestamp,
            "count": count
            }
        }
    return user_trades_msg

def set_order_msg(access_token, instrument, price, quantity, method = "buy", label = "sauceybuy"):
    order_msg = \
        {"jsonrpc": "2.0",
         "method": "private/" + method,
         "id": 42,
         "params": {
            "access_token": access_token,
            "instrument_name": instrument,
            "amount": quantity,
            "type": "limit",
            "label": label,
            "price": price,
            "time_in_force": "good_til_cancelled",
            "post_only": "true"}
        }
    return order_msg

async def call_api(authentication_msg):
    async with websockets.connect('wss://test.deribit.com/ws/api/v2') as websocket:
        await websocket.send(authentication_msg)
        while websocket.open:
            response = await websocket.recv()
            print(response)

            #identify refresh_token and access_token for session
            jresponse = json.loads(response)
            refresh_token = jresponse["result"]["refresh_token"]
            access_token = jresponse["result"]["access_token"]
            start_timestamp = jresponse["usOut"]
            print("Starting timestamp is " + json.dumps(start_timestamp))
            print("Refresh token is: " + json.dumps(refresh_token))
            print("Access token is: " + json.dumps(access_token))

            buy_price_list = []
            ask_price_list = []
            #get order book
            await websocket.send(json.dumps(get_order_book_msg))
            order_book_current = await websocket.recv()
            #print(order_book_current)
            jorder_book_current = json.loads(order_book_current)
            buy_price_list = list([float(jorder_book_current["result"]["bids"][0]["price"]) - .25])
            ask_price_list = list([float(jorder_book_current["result"]["asks"][0]["price"])])

            buy_price_list, ask_price_list = create_order_range_lists(buy_price_list, ask_price_list, 10)

            #print(buy_price_list[0])
            #print(ask_price_list[0])
            #print(buy_price_list)
            #print(ask_price_list)

            instrument = "BTC-PERPETUAL"
            for i in range(0, len(buy_price_list)):

                #set buy order info
                private_buy = set_order_msg(access_token, instrument, buy_price_list[i], 50,  method = "buy", label = "buyorder_" + str(i))

                #place a buy order
                await websocket.send(json.dumps(private_buy))
                buy_order_placed = await websocket.recv()
                jbuy_order_placed = json.loads(buy_order_placed)
                buyconfirmation = jbuy_order_placed["result"]["order"]["label"] + jbuy_order_placed["result"]["order"]["direction"] + str(jbuy_order_placed["result"]["order"]["creation_timestamp"])
                print(json.dumps(buyconfirmation))

                #set ask order info
                private_sell = set_order_msg(access_token, instrument, ask_price_list[i], 50, method = "sell", label = "sellorder_" + str(i))

                #place sell order
                await websocket.send(json.dumps(private_sell))
                sell_order_placed = await websocket.recv()
                jsell_order_placed = json.loads(sell_order_placed)
                sellconfirmation = jsell_order_placed["result"]["order"]["label"] + jsell_order_placed["result"]["order"]["direction"] + str(jsell_order_placed["result"]["order"]["creation_timestamp"])
                print(json.dumps(sellconfirmation))
                #

            #set user trades msg

            #get user trades and check when one happens
            x = 0
            print("start user trade search")
            while x < 1:

                get_user_trades_msg = set_get_user_trades_msg(access_token, instrument, start_timestamp, count = 2)
                await websocket.send(json.dumps(get_user_trades_msg))
                user_trades = await websocket.recv()
                user_trades_list = json.loads(user_trades)["result"]["trades"]

                print(user_trades)
                print(len(user_trades_list))

                if len(user_trades_list) > 0:
                    print("finally")
                    x = 1

                await asyncio.sleep(10)

            #close websocket
            await websocket.close()

asyncio.get_event_loop().run_until_complete(call_api(json.dumps(authentication_msg)))

'''
            #set buy order info
            private_buy = set_buy_msg(access_token, buy_price, 100)

            #place a buy order
            await websocket.send(json.dumps(private_buy))
            buy_order_placed = await websocket.recv()
            print(buy_order_placed)

            #set public subscribe channels
            public_channels = ["book.BTC-PERPETUAL.100ms", "ticker.BTC-PERPETUAL.100ms"]
            public_subscribe_msg = set_public_subscribe_msg(public_channels)

            #subscribe to public channels
            await websocket.send(json.dumps(public_subscribe_msg))
            public_subscription_msg = await websocket.recv()
            print("Subscribed: " + json.dumps(public_subscribe_msg))

            first_notification = await websocket.recv()
            print("The first notification is " + first_notification)

            second_notification = await websocket.recv()
            print("The second notification is " + second_notification)

            x = 0
            while x < 1:
                notification = await websocket.recv()
                jnotification = json.loads(notification)
                if jnotification["params"]["channel"] == "ticker.BTC-PERPETUAL.100ms":
                    print("ticker notification is " + notification)
                    x = 1

            #"trades.BTC-PERPETUAL.100ms"
            #"ticker.BTC-PERPETUAL.100ms"
'''
