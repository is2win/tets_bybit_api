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
SL_PERCENT = 0.0025  # 1%

# Инициализация клиента Bybit V5
client = HTTP(api_key=API_KEY,
              api_secret=API_SECRET,)


def place_orders():
    """Выставить два отложенных ордера с TP и SL."""
    # Получение текущей рыночной цены с помощью V5 API
    price = float(client.get_tickers(category="linear", symbol=SYMBOL).get('result').get('list')[0].get('ask1Price'))
    # price = float(ticker['result']['list'][0]['lastPrice'])  # Последняя цена на рынке
    print(f"Цена отсчета = {price}")
    buy_price = round(price * 1.0001, 2)  # Цена покупки чуть выше текущей
    print(f"Цена для покупки маркетом = {buy_price}")
    sell_price = round(price * 0.9999, 2)  # Цена продажи чуть ниже текущей
    print(f"Цена для продажи маркетом = {sell_price}")

    # Расчёт TP и SL
    tp_buy = round(buy_price * (1 + TP_PERCENT), 2)
    # sl_buy = round(buy_price * (1 - SL_PERCENT), 2)
    tp_sell = round(sell_price * (1 - TP_PERCENT), 2)
    # sl_sell = round(sell_price * (1 + SL_PERCENT), 2)

    position = {
        "Buy": {
            "price": buy_price,
            "tp": tp_buy,
        },
        "Sell": {
            "price": sell_price,
            "tp": tp_sell,
        }
    }

    buy_order = add_new_order_stop(
        symbol=SYMBOL,
        side="Buy",
        order_size=ORDER_SIZE,
        price=buy_price
    )
    sell_order = add_new_order_stop(
        symbol=SYMBOL,
        side="Sell",
        order_size=ORDER_SIZE,
        price=sell_price
    )
    position["Buy"]['order'] = buy_order
    position["Sell"]['order'] = sell_order
    print(
        f"Позиция: {position}"
    )

    return position


def add_new_order_stop(symbol, side, order_size, price):
    """
    Уникальный создатель ордеров
    :param symbol:
    :param side:
    :param order_size:
    :param price:
    :return:
    """
    make_order = client.place_order(
        category="linear",
        symbol=symbol,
        side=side,
        orderType="Market",
        qty=str(order_size),
        price=str(price),
        timeInForce="GTC",
        triggerPrice=str(price),
        triggerDirection=(1, 2)[side == 'Sell'],  # Sell direction for stop order
    )
    return make_order

def add_new_order_limit(symbol, side, order_size, price):
    """
    Уникальный создатель ордеров
    :param symbol:
    :param side:
    :param order_size:
    :param price:
    :return:
    """
    make_order = client.place_order(
        category="linear",
        symbol=symbol,
        side=side,
        orderType="Limit",
        qty=str(order_size),
        price=str(price),
        timeInForce="GTC",
    )
    return make_order

def set_take_profit(symbol, tp_price):
    make_tp = client.set_trading_stop(
        category="linear",
        symbol=symbol,
        takeProfit=tp_price,
        tpTriggerBy="MarkPrice",
        tpslMode="Full",
        tpOrderType="Market",
        positionIdx=0,
    )
    return make_tp


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
    # print(f"r={r}")
    ret = dict(
        avg_price=p.get('avgPrice', '0.0'),
        side=p.get('side'),
        unrel_pnl=p.get('unrealisedPnl', '0.0'),
        qty=qty
    )

    ret['rev_side'] = ("Sell", "Buy")[ret['side'] == 'Sell']
    time.sleep(0.5)
    return ret


def monitor_open_position(position: dict):
    print("Мониторинг открытия позы и создания лока")
    order_positions = dict(
        Buy=position['Buy']['order']['result']['orderId'],
        Sell=position['Sell']['order']['result']['orderId']
    )
    while True:
        current_position = get_open_orders()
        if current_position.get('qty'):
            cancel_order(order_positions.get(current_position['rev_side']))
            set_take_profit(
                symbol=SYMBOL,
                tp_price=position[current_position['side']]['tp']
            )
            position[current_position['side']]['price'] = current_position['avg_price']
            print(f"установлена новая цена для  {current_position['side']} = {current_position['avg_price']}")
            correction_coef = (-1, 1)[current_position['side'] == "Sell"]
            next_order = round(float(current_position['avg_price']) * (1 + (SL_PERCENT * correction_coef)), 2)
            add_new_order_limit(
                symbol=SYMBOL,
                side=current_position['side'],
                order_size=current_position['qty'] * 2,
                price=next_order
            )
            return position


def if_all_positions_closed(position_old: dict):
    print("Смотрю все ли позы закрыты... и добавляю еще одну если что")
    position = position_old
    while True:
        current_position = get_open_orders()
        if not current_position.get('qty'):
            print("Открытых сделок нет - закрываю лимитки")
            client.cancel_all_orders(category="linear", symbol=SYMBOL)
            return
        if not float(current_position.get('avg_price')) == float(position[current_position.get('side')]['price']):
            correction_coef = (-1, 1)[current_position['side'] == "Sell"]
            next_order = round(float(current_position['avg_price']) * (1 + (SL_PERCENT * correction_coef)), 2)
            add_new_order_limit(
                symbol=SYMBOL,
                side=current_position['side'],
                order_size=current_position['qty'] * 2,
                price=next_order
            )
            new_tp = round(current_position['avg_price'] * (1 + TP_PERCENT * correction_coef), 2)
            set_take_profit(
                symbol=SYMBOL,
                tp_price=new_tp
            )
            position[current_position.get('side')]['price'] = current_position['avg_price']


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
        position = place_orders()
        # buy_order_id = position['buy_order']['result']['orderId']
        # sell_order_id = position['sell_order']['result']['orderId']

        # # Мониторим их выполнение
        position = monitor_open_position(position)
        # print(f"Executed side: {executed_side}")

        # Мониторим открытую позицию до её закрытия
        if_all_positions_closed(position)

        # После выполнения ордера и закрытия позиции начинаем заново
        print("Cycle complete. Restarting...")
        # time.sleep(2)


if __name__ == "__main__":
        main()

