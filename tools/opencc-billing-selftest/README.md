# OpenCC 计费自测

不连真实上游、不花钱，验证本站计费链路是否正确：成员扣费、上游成本、毛利、余额、上游倍率探测和对账工具。

上游由 `mock_upstream.py` 模拟（Sub2API 兼容），默认按“标准费用 × 0.8 + 每次 ¥0.002”扣自己的余额，用来模拟 credit 计费的按次费用。它**不是** SuperGPT，结果只说明本站逻辑正确，不代表真实上游价格。

## 一条命令运行（推荐）

```bash
tools/opencc-billing-selftest/run-local.sh
```

脚本会临时启动 PostgreSQL（55433）、Redis（56380）、OpenCC 服务（18088）和模拟上游（18080），跑完自动停止并删除临时数据，不影响已有服务和数据库。约 1–2 分钟。

需要（WSL / Ubuntu）：

```bash
sudo apt install postgresql redis-server python3 golang-go
sudo systemctl disable --now postgresql redis-server   # 可选：脚本自己启动临时实例，不需要常驻服务
```

Go 版本低于 `backend/go.mod` 要求时，`go build` 会自动下载所需工具链。已有编译好的服务时可跳过编译：`OPENCC_SERVER_BIN=/path/to/server run-local.sh`。

参数会传给 `selftest.py`，例如 `run-local.sh --sell 1.33 --cost 0.9 --requests 5`。

## 检查项

| # | 检查 | 说明 |
|---|---|---|
| 1 | 上游只收到服务端上游 Key | 成员密钥没有被转发到上游 |
| 2 | 用量记录已写入 | 每个请求一条 |
| 3 | Token 数与上游返回一致 | 网关正确读取上游 usage（含流式） |
| 4 | 标准费用 = Token × 渠道基础单价 | |
| 5 | 成员实扣 = 标准费用 × D | D 为分组倍率，默认 1.2 |
| 6 | 账号成本 = 标准费用 × U | U 为账号倍率，默认 0.8 |
| 7 | 成员余额减少量 = 成员实扣 | |
| 8 | 后台仪表盘毛利增加 = 实扣 − 成本 | 仪表盘约每分钟聚合一次 |
| 9 | 上游倍率探测读到上游声明的倍率 | |
| 10 | `deploy/opencc-cost-check.py reconcile` 能对比上游余额与本站记录 | 输出真实 U 与真实毛利 |

全部通过时退出码为 0，任一失败为 1。

第 10 项的输出里，真实 U 会明显高于 0.8 并出现亏损警告，这是预期的：自测请求很小，模拟上游每次 ¥0.002 的固定费用占比很高。这正好演示了 credit 计费下小请求的成本风险。

## 对已运行的测试实例运行

已有一个**测试用**实例时，可以只运行检查脚本。模拟上游要运行在服务端能访问的地址上：

```bash
python3 tools/opencc-billing-selftest/mock_upstream.py --port 18080 &
OPENCC_ADMIN_EMAIL=... OPENCC_ADMIN_PASSWORD=... \
  python3 tools/opencc-billing-selftest/selftest.py --base http://127.0.0.1:8088 --mock http://127.0.0.1:18080
```

- 它会创建测试用户、分组、账号和渠道（名称带 `selftest-` 前缀），**不要对生产实例运行**。非本机地址默认拒绝，需显式加 `--allow-remote`。
- 后台未确认 Sub2API 合规承诺时脚本会停止并提示；只有在测试实例上才加 `--accept-compliance` 让测试管理员确认。
- 第 10 项需要数据库访问：`--psql "psql -h ... -U opencc -d opencc"`，不提供则跳过。
