from pybit.unified_trading import HTTP
import time
from environs import Env
from loguru import logger
import decimal


env = Env()
env.read_env()
# API настройки
API_KEY = env("API_KEY")
API_SECRET = env("API_SECRET")

SYMBOL = "SHIB1000USDT"
CATEGORY = "linear"

# ORDER_SIZE = 0.01  # Размер лота
TP_PERCENT = 0.0025  # 0.5%
SL_PERCENT = 0.0025  # 1%

# Инициализация клиента Bybit V5
client = HTTP(api_key=API_KEY,
              api_secret=API_SECRET,)


def get_filters():
    """
    Фильтры заданного инструмента
    - макс колво знаков в аргументах цены,
    - мин размер ордера в Базовой Валюте,
    - макс размер ордера в БВ
    """
    r = client.get_instruments_info(symbol=SYMBOL, category=CATEGORY)
    c = r.get('result', {}).get('list', [])[0]
    print(c)
    min_qty = c.get('lotSizeFilter', {}).get('minOrderQty', '0.0')
    qty_decimals = abs(decimal.Decimal(min_qty).as_tuple().exponent)
    price_decimals = int(c.get('priceScale', '4'))
    min_qty = decimal.Decimal(min_qty) * 500

    logger.success(f"{price_decimals}, {qty_decimals}, {min_qty}")
    return price_decimals, qty_decimals, min_qty


def get_delta(price):
    # Получение текущей рыночной цены с помощью V5 API
    # Расчёт TP и SL
    delta = (price * (1 + TP_PERCENT)) - price
    return round(decimal.Decimal(delta), PRICE_DECIMALS)


def place_orders():
    """Выставить два отложенных ордера с TP и SL."""
    # Получение текущей рыночной цены с помощью V5 API
    price = float(client.get_tickers(category=CATEGORY, symbol=SYMBOL).get('result').get('list')[0].get('ask1Price'))
    # price = float(ticker['result']['list'][0]['lastPrice'])  # Последняя цена на рынке
    logger.info(f"Цена отсчета = {price}")
    buy_price = round(price * 1.001, PRICE_DECIMALS)  # Цена покупки чуть выше текущей
    logger.info(f"Цена для покупки маркетом = {buy_price}")
    sell_price = round(price * 0.999, PRICE_DECIMALS)  # Цена продажи чуть ниже текущей
    logger.info(f"Цена для продажи маркетом = {sell_price}")
    delta = get_delta(buy_price)


    position = {
        "Buy": {
            "price": buy_price,
            "delta": delta,
            "order_num": 1,
            "avg_price": buy_price,
        },
        "Sell": {
            "price": sell_price,
            "delta": delta,
            "order_num": 1,
            "avg_price": sell_price,
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
    logger.info(
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
    logger.info("Мониторинг открытия позы и создания лока")
    order_positions = dict(
        Buy=position['Buy']['order']['result']['orderId'],
        Sell=position['Sell']['order']['result']['orderId']
    )
    while True:
        current_position = get_open_orders()
        if current_position.get('qty'):
            cancel_order(order_positions.get(current_position['rev_side']))
            correction_coef = (1, -1)[current_position['side'] == "Sell"]
            set_take_profit(
                symbol=SYMBOL,
                tp_price=round(decimal.Decimal(
                    float(current_position['avg_price']) * (1 + (TP_PERCENT * correction_coef))),
                    PRICE_DECIMALS)
            )
            position[current_position['side']]['avg_price'] = current_position['avg_price']
            logger.info(f"установлена новая цена для  {current_position['side']} = {current_position['avg_price']}")

            correction_coef = (-1, 1)[current_position['side'] == "Sell"]
            next_order = round(decimal.Decimal(
                position[current_position['side']]['price']) + (
                    position[current_position['side']]['delta'] * position[current_position['side']]['order_num'] * correction_coef),
                               PRICE_DECIMALS)

            position[current_position['side']]['order_num'] = position[current_position['side']]['order_num'] + 1
            correction_coef = (1, -1)[current_position['side'] == "Sell"]
            add_new_order_limit(
                symbol=SYMBOL,
                side=current_position['side'],
                order_size=ORDER_SIZE,
                price=next_order
            )
            return position


def if_all_positions_closed(position_old: dict):
    print("Смотрю все ли позы закрыты... и добавляю еще одну если что")
    position = position_old
    while True:
        current_position = get_open_orders()
        if not current_position.get('qty'):
            logger.success("Открытых сделок нет - закрываю лимитки")
            client.cancel_all_orders(category="linear", symbol=SYMBOL)
            return
        if current_position.get('avg_price') != position[current_position.get('side')]['avg_price']:
            logger.critical(f"current_avg_price = {current_position['avg_price']} vs last_avg_price = {position[current_position.get('side')]['price']}")

            correction_coef = (-1, 1)[current_position['side'] == "Sell"]
            next_order = round(decimal.Decimal(float(
                position[current_position['side']]['price']) + (
                                       position[current_position['side']]['delta'] * position[current_position['side']][
                                   'order_num'] * correction_coef)),
                               PRICE_DECIMALS)

            position[current_position['side']]['order_num'] = position[current_position['side']]['order_num'] + 1
            try:
                add_new_order = add_new_order_limit(
                    symbol=SYMBOL,
                    side=current_position['side'],
                    order_size=ORDER_SIZE,
                    price=next_order
                )
                logger.info(f"add_new_order = {add_new_order}")
            except Exception as ex:
                logger.error(f"Ошибка выстановления новой сетки оредров = {ex}")
            try:
                correction_coef = (1, -1)[current_position['side'] == "Sell"]
                new_tp = round(
                    decimal.Decimal(float(current_position['avg_price']) * (1 + (TP_PERCENT * correction_coef))),
                    PRICE_DECIMALS)

                set_tp = set_take_profit(
                    symbol=SYMBOL,
                    tp_price=new_tp
                )
                logger.info(f"set_tp = {set_tp}")
            except Exception as ex:
                logger.error(f"Ошибка выстановления нового ТП = {ex}")
            position[current_position.get('side')]['avg_price'] = current_position['avg_price']
            logger.critical(position)


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
        logger.success("start")
        # Выставляем ордера
        position = place_orders()
        # buy_order_id = position['buy_order']['result']['orderId']
        # sell_order_id = position['sell_order']['result']['orderId']

        # # Мониторим их выполнение
        position = monitor_open_position(position)


        # Мониторим открытую позицию до её закрытия
        if_all_positions_closed(position)

        # После выполнения ордера и закрытия позиции начинаем заново
        logger.success("Cycle complete. Restarting...")
        # time.sleep(2)



PRICE_DECIMALS, QTY_DECIMALS, ORDER_SIZE = get_filters()

if __name__ == "__main__":
        main()