import logging
import os
from logging.handlers import RotatingFileHandler
from http import HTTPStatus

import requests
import time
from dotenv import load_dotenv
import telegram


load_dotenv()
logging.basicConfig(
    level=logging.DEBUG,
    filename='main.log',
    format='%(asctime)s, %(levelname)s, %(message)s, %(lineno)d',
    encoding='UTF-8',
    filemode='w'
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = RotatingFileHandler('my_logger.log',
                              encoding='UTF-8',
                              maxBytes=50000000,
                              backupCount=5)
console_handler = logging.StreamHandler()
formatter = logging.Formatter(
    '%(asctime)s, %(levelname)s, %(message)s, %(lineno)d'
)
handler.setFormatter(formatter)

logger.addHandler(handler)
logger.addHandler(console_handler)

logger.debug('Бот заработал')

formatter = logging.Formatter(
    '%(asctime)s, %(levelname)s, %(message)s, %(lineno)d'
)
handler.setFormatter(formatter)


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверяет доступность переменных окружения.
    Если отсутствует переменная окружения — False.
    Если всё в порядке — True.
    """
    return all((PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID))


def send_message(bot, message):
    """Отправляет сообщение в чат.
    Принимает на вход два параметра:
    экземпляр класса Bot и тектовую строку.
    """
    logging.debug(f'Отправка боту: {bot} сообщения: {message}')
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.info(f'сообщение в чат {TELEGRAM_CHAT_ID}: {message}')
    except Exception:
        logger.error('Ошибка отправки сообщения в телеграм чат')
    logger.debug('Сообщение отправлено')


def get_api_answer(timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса.
    В качестве параметра в функцию передается временная метка.
    В случае успешного запроса должна вернуть ответ API,
    приведя его из формата JSON к типам данных Python.
    """
    timestamp = int(time.time())
    params = {'from_date': timestamp}
    try:
        homework_status = requests.get(ENDPOINT,
                                       headers=HEADERS,
                                       params=params
                                       )
    except Exception as error:
        message = f'Ошибка при запросе к основному API: {error}'
        logging.error(message)
        raise ConnectionError(message)
    if homework_status.status_code != HTTPStatus.OK:
        status_code = homework_status.status_code
        message = f'Ошибка {status_code}'
        logging.error(message)
        raise ConnectionAbortedError(message)
    try:
        return homework_status.json()
    except ValueError:
        message = 'Ошибка парсинга из формата JSON'
        logging.error(message)
        raise ValueError(message)


def check_response(response):
    """Проверяет ответ API на соответствие документации.
    В качестве параметра функция получает ответ API,
    приведенный к типам данных Python. Если соответствует,
    то ф-ция должна вернуть список дом. работ, в API по ключу
    'homeworks'
    """
    if not isinstance(response, dict):
        message = 'Ответ API отличается от словаря'
        logging.error(message)
        raise TypeError(message)

    if not isinstance(response.get('homeworks'), list):
        message = 'homeworks не является списком'
        logging.error(message)
        raise TypeError(message)

    if not response:
        message = 'Содержит пустой словарь.'
        logging.error(message)
        raise KeyError(message)

    if 'homeworks' not in response:
        message = 'Отсутствие ожидаемых ключей в ответе.'
        logging.error(message)
        raise KeyError(message)
    return response['homeworks']


def parse_status(homework):
    """Извлекает статус домашней работы.
    В качестве параметра функция получает
    только один элемент из списка домашних работ.
    В случае успеха, функция возвращает подготовленную для отправки
    в Telegram строку, содержащую один из вердиктов словаря HOMEWORK_VERDICTS.
    """
    if 'homework_name' not in homework:
        message = 'Нет ключа "homework_name" в ответе API'
        logging.error(message)
        raise KeyError(message)
    if 'status' not in homework:
        message = 'Нет ключа "status" в ответе API'
        logging.error(message)
        raise KeyError(message)
    homework_name = homework['homework_name']
    homework_status = homework['status']
    if homework_status not in HOMEWORK_VERDICTS:
        raise NameError(f'Неизвестный статус: {homework_status}')
    verdict = HOMEWORK_VERDICTS[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        message = 'Отсуствует как минимум одна переменная окружения'
        logger.critical(message)
        raise ValueError(message)
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())

    last_message = {
        'error': None,
    }

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if len(homeworks) == 0:
                logging.debug('Ответ API пустой: нет домашних работ')
                continue
            timestamp = response.get('current_date')
            for homework in homeworks:
                message = parse_status(homework)
                if last_message.get(homework['homework_name']) != message:
                    send_message(bot, message)
                    last_message[homework['homework_name']] = message
            timestamp = response.get('current_date')
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            if last_message['error'] != message:
                send_message(bot, message)
                last_message['error'] = message
        else:
            last_message['error'] = None
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
