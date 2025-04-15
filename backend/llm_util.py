import base64
import datetime
import hashlib
import hmac
import json
import ssl
from urllib.parse import urlencode, urlparse
from time import mktime
from wsgiref.handlers import format_date_time

import websocket
import threading

class Ws_Param:
    def __init__(self, APPID, APIKey, APISecret, gpt_url):
        self.APPID = APPID
        self.APIKey = APIKey
        self.APISecret = APISecret
        self.host = urlparse(gpt_url).netloc
        self.path = urlparse(gpt_url).path
        self.gpt_url = gpt_url

    def create_url(self):
        now = datetime.datetime.now()
        date = format_date_time(mktime(now.timetuple()))

        signature_origin = f"host: {self.host}\n"
        signature_origin += f"date: {date}\n"
        signature_origin += f"GET {self.path} HTTP/1.1"

        signature_sha = hmac.new(
            self.APISecret.encode('utf-8'),
            signature_origin.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()

        signature_sha_base64 = base64.b64encode(signature_sha).decode()

        authorization_origin = (
            f'api_key="{self.APIKey}", algorithm="hmac-sha256", '
            f'headers="host date request-line", signature="{signature_sha_base64}"'
        )

        authorization = base64.b64encode(authorization_origin.encode()).decode()

        return self.gpt_url + '?' + urlencode({
            "authorization": authorization,
            "date": date,
            "host": self.host
        })


def gen_params(appid, query, domain):
    return {
        "header": {
            "app_id": appid,
            "uid": "sensor-001",
        },
        "parameter": {
            "chat": {
                "domain": domain,
                "temperature": 0.5,
                "max_tokens": 2048,
                "auditing": "default",
            }
        },
        "payload": {
            "message": {
                "text": [{"role": "user", "content": query}]
            }
        }
    }

def ask_spark(query: str) -> str:
    appid = "2c6796f9"
    api_key = "03f06dd13ab3d8b75cc649fab89aa572"
    api_secret = "N2VmOTMzMzc3MmZlZWU0ZDA5ODk3NmI2"
    spark_url = "wss://spark-api.xf-yun.com/v1.1/chat"
    domain = "lite"

    wsParam = Ws_Param(appid, api_key, api_secret, spark_url)
    url = wsParam.create_url()

    result = []

    def on_message(ws, message):
        data = json.loads(message)
        code = data['header']['code']
        if code != 0:
            ws.close()
            raise Exception(f"Spark API Error: {code}, {data}")
        else:
            content = data["payload"]["choices"]["text"][0]["content"]
            result.append(content)
            if data["payload"]["choices"]["status"] == 2:
                ws.close()

    def on_open(ws):
        def run():
            data = json.dumps(gen_params(appid, query, domain))
            ws.send(data)
        threading.Thread(target=run).start()

    def on_error(ws, error):
        print(f"WebSocket error: {error}")

    def on_close(ws):
        pass  # Optional logging

    websocket.enableTrace(False)
    ws = websocket.WebSocketApp(
        url,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open
    )

    ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

    return ''.join(result)
