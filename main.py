#!/usr/bin/env python
# -*- coding: utf-8 -*-

import struct
import nfc
import json
import time
import os
from collections import OrderedDict
import subprocess
import requests
import traceback
import binascii

# システム
SYSTEM_SUICA = 'suica'
SYSTEM_EDY = 'edy'
SYSTEM_NANACO = 'nanaco'
SYSTEM_WAON = 'waon'
SYSTEM_UNKNOWN = 'unknown'

# システムコード
SYSTEM_CODES_SUICA = [0x0003]
SYSTEM_CODES_EDY = [0x811D]
SYSTEM_CODES_NANACO = [0x04C7]
SYSTEM_CODES_WAON = [0x8B61]

# サービスコード
HISTORY_SERVICE_CODE = 0x090f  # 乗降履歴情報
CARD_INFO_SERVICE_CODE = 0x008b  # カード種別およびカード残額情報

# 参照する履歴件数(Suicaには最大で20件まで保存される)
HISTORY_BLOCK_LENGTH = 20

# データ種別
DATA_TYPE_TRAIN = 'train'
DATA_TYPE_BUS = 'bus'
DATA_TYPE_SALE_OF_GOODS = 'sale_of_goods'

# データ種別と処理コードの対応
PROCESSING_CODES_BUS = {13, 15, 31, 35}
PROCESSING_CODES_SALE_OF_GOODS = {70, 73, 74, 75, 198, 203}

# 設定
CARD_READ_TIME_FILE = './card-read-time.json'  # 連続読み取り防止のための読み取り時刻記録ファイル
SAME_CARD_IGNORING_INTERVAL = 3  # 連続読み取りの無視時間(秒)
API_ENDPOINT = os.getenv('API_ENDPOINT')
API_TOKEN = os.getenv('API_TOKEN')


def get_system(system_code):
    """
    システムコードからシステムを割り出す
    :param int system_code: システムコード
    :return: システム名
    :rtype: srt
    """
    if system_code in SYSTEM_CODES_SUICA:
        return SYSTEM_SUICA
    if system_code in SYSTEM_CODES_EDY:
        return SYSTEM_EDY
    if system_code in SYSTEM_CODES_NANACO:
        return SYSTEM_NANACO
    if system_code in SYSTEM_CODES_WAON:
        return SYSTEM_WAON
    return SYSTEM_UNKNOWN


def get_data_type(processing):
    """
    処理コードからデータ種別を返す
    :param int processing:
    :return: データ種別
    :rtype: str
    """
    if processing in PROCESSING_CODES_BUS:
        return DATA_TYPE_BUS
    elif processing in PROCESSING_CODES_SALE_OF_GOODS:
        return DATA_TYPE_SALE_OF_GOODS
    else:
        return DATA_TYPE_TRAIN


def get_suica_transaction(block):
    """
    ブロックデータ1件から構造化された取引データ1件を返す
    :param str block: 16バイトのブロックデータ
    :return: 取引データ
    :rtype: OrderedDict
    """
    block_string = binascii.hexlify(block).upper()
    be = struct.unpack('>2B2H4BH4B', block)  # ビッグエンディアン
    le = struct.unpack('<2B2H4BH4B', block)  # リトルエンディアン(残高用)
    terminal = be[0]
    processing = be[1]
    date = '%d-%02d-%02d' % (
        ((be[3] >> 9) & 0x7f) + 2000,
        (be[3] >> 5) & 0x0f,
        (be[3] >> 0) & 0x1f
    )
    data_type = get_data_type(processing)
    if data_type == DATA_TYPE_TRAIN:
        station = OrderedDict([
            ('entered_line_code', be[4]),
            ('entered_station_code', be[5]),
            ('exited_line_code', be[6]),
            ('exited_station_code', be[7])
        ])
    else:
        station = None
    balance = le[8]
    serial_number = int('%02x%02x%02x' % (be[9], be[10], be[11]), 16)
    region = be[12]
    transaction = OrderedDict([
        ('serial_number', serial_number),
        ('data_type', data_type),
        ('terminal', terminal),
        ('processing', processing),
        ('date', date),
        ('balance', balance),
        ('region', region),
    ])
    if station:
        transaction['station'] = station
    transaction['block'] = block_string
    return transaction


def get_suica_history(tag):
    """
    Suicaの履歴データを返す
    :param tag: タグ
    :return: 履歴データ
    :rtype: list[OrderedDict]
    :raise TypeError: タグがType3Tagでないとき
    """
    history = []
    if isinstance(tag, nfc.tag.tt3.Type3Tag):
        service = nfc.tag.tt3.ServiceCode(HISTORY_SERVICE_CODE >> 6, HISTORY_SERVICE_CODE & 0x3f)
        for i in range(HISTORY_BLOCK_LENGTH):
            block = nfc.tag.tt3.BlockCode(i, service=0)
            transaction = get_suica_transaction(bytes(tag.read_without_encryption([service], [block])))
            if transaction['serial_number'] > 0:
                history.append(transaction)
    else:
        raise TypeError('tag isn\'t Type3Tag')
    history.reverse()
    return history


def get_idm(tag):
    """
    ICカードのIDmを返す
    :param tag: タグ
    :return: IDm
    :rtype: str
    """
    return str(tag.idm).encode('hex').upper()


def prevent_multiple_times_read(fn):
    """
    ICカード置きっぱなし等による連続読み取りを回避する機構
    :param function fn:
    :return: ラップされた関数
    :rtype: function
    """
    if not os.path.exists(CARD_READ_TIME_FILE):
        with open(CARD_READ_TIME_FILE, 'w') as f:
            f.write('{}')

    if not os.path.isfile(CARD_READ_TIME_FILE) or not os.access(CARD_READ_TIME_FILE, os.W_OK):
        raise Exception('File is not writable file: %s' % CARD_READ_TIME_FILE)

    def wrapper(tag):
        with open(CARD_READ_TIME_FILE, 'r+') as ff:
            idm_list = json.load(ff)
            idm = get_idm(tag)

            # 直前に読み取ったばかりのカードは処理を中断する
            if idm in idm_list and idm_list[idm] + SAME_CARD_IGNORING_INTERVAL > time.time():
                print '[ignored] %s' % tag
                return False

            # カード読み取り処理へ
            result = fn(tag)

            # IDmと時刻を書き込む
            idm_list[idm] = int(time.time())
            ff.seek(0)
            ff.truncate()
            json.dump(idm_list, ff)

            return result
    return wrapper


def send_http_request(payload):
    """
    外部サービスにPOSTする
    :param dict payload: 送信するデータ
    """
    loading_sound = subprocess.Popen(
        ['mpg123', '-q', '--loop', '0', 'mp3/waiting.mp3']
    )
    res = requests.post(
        API_ENDPOINT,
        data=payload,
        headers={
            'user-agent': 'FeliCa-Reader',
            'authorization': 'Bearer ' + API_TOKEN,
        }
    )
    loading_sound.kill()

    if res.status_code == requests.codes.ok:
        print 'HTTP request OK'
    else:
        message = None
        try:
            message = res.json()['message']
        except:
            pass
        raise Exception('http error: status: %s, message: %s' % (res.status_code, message))


def validate_config():
    if API_ENDPOINT is None:
        raise Exception('API_ENDPOINT is not specified')
    if API_TOKEN is None:
        raise Exception('API_TOKEN is not specified')


@prevent_multiple_times_read
def connected(tag):
    """
    ICカードが接続されたときの処理
    :param tag: タグ
    """
    print tag
    idm = get_idm(tag)
    system_code = tag.sys
    system = get_system(system_code)
    felica_data = OrderedDict([
        ('idm', idm),
        ('system_code', '%04X' % system_code),
        ('system', system)
    ])
    if system == SYSTEM_SUICA:
        felica_data['suica_history'] = get_suica_history(tag)
    result = json.dumps(felica_data, indent=2, sort_keys=False)
    send_http_request(result)
    subprocess.call('mpg123 -q mp3/ok.mp3'.split(' '))


if __name__ == '__main__':
    validate_config()
    clf = nfc.ContactlessFrontend('usb')
    while True:
        try:
            clf.connect(rdwr={'on-connect': connected})
            time.sleep(1)  # これがないとCtrl-Cがうまく効かない
        except Exception as e:
            print e
            traceback.print_exc()
            subprocess.call('mpg123 -q mp3/error.mp3'.split(' '))


