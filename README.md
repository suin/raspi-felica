# raspi-felica

RaspberryPi + FelicaリーダでSuicaの履歴を読み込み、そのデータをJSON形式にしてウェブに投げる半部品です。

## 使い方

```
git clone git@github.com:suin/raspi-felica.git
cd raspi-felica
sudo API_ENDPOINT=https://example.com/api API_TOKEN=XXX ./main.py
```

## Webhook

`API_ENDPOINT`で指定したURLに`POST`でリクエストを投げます。たとえば、`sudo API_ENDPOINT=http://example.com/api/save_suica API_TOKEN=XXX ./main.py`で起動したプロセスでPASMOを読み込むと次のようなPOSTリクエストを投げます。

```http
POST /api/save_suica HTTP/1.1
Host: example.com
Content-Length: 506
Accept-Encoding: gzip, deflate
Accept: */*
user-agent: FeliCa-Reader
Connection: keep-alive
authorization: Bearer XXX

{
  "idm": "01010A100317C911",
  "system_code": "0003",
  "system": "suica",
  "suica_history": [
    {
      "serial_number": 1,
      "data_type": "train",
      "terminal": 21,
      "processing": 7,
      "date": "2016-07-15",
      "balance": 500,
      "region": 0,
      "station": {
        "entered_line_code": 0,
        "entered_station_code": 0,
        "exited_line_code": 0,
        "exited_station_code": 0
      },
      "block": "1507000020EF00000000F40100000100"
    }
  ]
}
```