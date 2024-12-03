from pybit.unified_trading import HTTP
import time
from environs import Env

env = Env()
env.read_env()
# API настройки
API_KEY = env("API_KEY")
API_SECRET = env("API_SECRET")


# Параметры торговли
# SYMBOL = "BTCUSDT"
SYMBOL = "ETHUSDT"


ORDER_SIZE = 0.01  # Размер лота
TP_PERCENT = 0.0025  # 0.5%
SL_PERCENT = 0.005  # 1%

# Инициализация клиента Bybit V5
client = HTTP(api_key=API_KEY,
              api_secret=API_SECRET,)


def place_orders():
    """Выставить два отложенных ордера с TP и SL."""
    # Получение текущей рыночной цены с помощью V5 API
    price = float(client.get_tickers(category="linear", symbol=SYMBOL).get('result').get('list')[0].get('ask1Price'))
    # price = float(ticker['result']['list'][0]['lastPrice'])  # Последняя цена на рынке
    print(price)
    buy_price = round(price * 1.001, 2)  # Цена покупки чуть выше текущей
    print(buy_price)
    sell_price = round(price * 0.999, 2)  # Цена продажи чуть ниже текущей
    print(sell_price)

    # Расчёт TP и SL
    tp_buy = round(buy_price * (1 + TP_PERCENT), 2)
    sl_buy = round(buy_price * (1 - SL_PERCENT), 2)
    tp_sell = round(sell_price * (1 - TP_PERCENT), 2)
    sl_sell = round(sell_price * (1 + SL_PERCENT), 2)

    position = {
                "buy_price": buy_price,
                "sell_price": sell_price,
                "tp_buy": tp_buy,
                "sl_buy": sl_buy,
                "tp_sell": tp_sell,
                "sl_sell": sl_sell
    }

    print(
        position
    )

    # Создание условного ордера на покупку
    buy_order = client.place_order(
        category="linear",
        symbol=SYMBOL,
        side="Buy",
        orderType="Market",
        qty=str(ORDER_SIZE),
        price=str(buy_price),
        timeInForce="GTC",
        triggerPrice=str(buy_price),
        triggerDirection=1,  # Buy direction for stop order
        takeProfit=str(tp_buy),
        stopLoss=str(sl_buy)
    )

    # Создание условного ордера на продажу
    sell_order = client.place_order(
        category="linear",
        symbol=SYMBOL,
        side="Sell",
        orderType="Market",
        qty=str(ORDER_SIZE),
        price=str(sell_price),
        timeInForce="GTC",
        triggerPrice=str(sell_price),
        triggerDirection=2,  # Sell direction for stop order
        takeProfit=str(tp_sell),
        stopLoss=str(sl_sell)
    )

    print("Buy Order:", buy_order)
    print("Sell Order:", sell_order)
    return buy_order['result']['orderId'], sell_order['result']['orderId']


def get_open_orders():
    """
    Получить текущую открытой позиции
    :param buy_order_id:
    :param sell_order_id:
    :return:
    """
    r = client.get_positions(category="linear", symbol=SYMBOL)
    p = r.get('result', {}).get('list', [])[0]
    qty = float(p.get('size', '0.0'))

    ret = dict(
        avg_price=p.get('avgPrice', '0.0'),
        side=p.get('side'),
        unrel_pnl=p.get('unrealisedPnl', '0.0'),
        qty=qty
    )

    ret['rev_side'] = ("Sell", "Buy")[ret['side'] == 'Sell']
    time.sleep(0.5)
    return ret


def monitor_open_position(buy_order_id, sell_order_id ):
    order_positions = dict(
        Buy=buy_order_id,
        Sell=sell_order_id
    )
    while True:
        current_position = get_open_orders()
        if current_position.get('qty'):
            cancel_order(order_positions.get(current_position['rev_side']))
            return


def if_all_positions_closed():
    while True:
        current_position = get_open_orders()
        if not current_position.get('qty'):
            return


def cancel_order(order_id):
    """
    Отмена ордера по id
    :param order_id:
    :return:
    """
    r = client.cancel_order(category="linear", symbol=SYMBOL, orderId=order_id)
    return r


def main():
    """Основной цикл работы бота."""
    while True:
        print("start")
        # Выставляем ордера
        buy_order_id, sell_order_id = place_orders()

        # # Мониторим их выполнение
        monitor_open_position(buy_order_id, sell_order_id)
        # print(f"Executed side: {executed_side}")

        # Мониторим открытую позицию до её закрытия
        if_all_positions_closed()

        # После выполнения ордера и закрытия позиции начинаем заново
        print("Cycle complete. Restarting...")
        # time.sleep(2)


if __name__ == "__main__":
        main()

