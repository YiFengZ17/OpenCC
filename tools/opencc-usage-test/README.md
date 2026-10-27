# OpenCC 用量测试

在**真实部署 + 真实上游**上验证用量与扣费，花费很少（一次完整运行约 ¥0.02–0.1，取决于模型价格），上限 ¥2。

和 `tools/opencc-billing-selftest` 的区别：自测工具用模拟上游、不花钱，验证本站计费逻辑；这里测的是上线后的真实链路。

## 交给 agent

把 `AGENT_TASK.md` 交给本地 agent，它包含步骤、规则、结果判断和报告格式。你只需要提供环境变量（见下）。

## 自己运行

准备一个**专用测试成员**（余额 ≥ ¥2，测试期间没有别人用），然后：

```bash
export OPENCC_BASE=https://opencc.app
export OPENCC_MEMBER_EMAIL=tester@example.com
read -rs OPENCC_MEMBER_PASSWORD && export OPENCC_MEMBER_PASSWORD   # 输入时不显示

python3 tools/opencc-usage-test/usage_test.py
```

只需要 Python 3，不用装依赖。常用参数：

| 参数 | 说明 |
|---|---|
| `--model claude-sonnet-4-6` | 测试用的模型 |
| `--group-id 2` | 临时密钥绑定的分组（默认第一个可用分组） |
| `--max-spend 2` | 花费上限（¥），到达即停 |
| `--with-admin` | 加跑 C7（余额不足）、C10（成员隔离），需要 `OPENCC_ADMIN_EMAIL` / `OPENCC_ADMIN_PASSWORD` |
| `--skip C3,C9` | 跳过部分用例 |
| `--report file.json` | JSON 报告位置 |

脚本会创建名字以 `usagetest-` 开头的临时密钥（`--with-admin` 时还有一个临时成员），结束时自动删除。退出码：有 FAIL 为 1，否则为 0。

## 用例

C1 普通请求 · C2 流式请求 · C3 提示缓存 · C4 失败请求不扣费 · C5 中途断开（只记录）· C6 密钥额度 · C7 余额不足 · C8 汇总一致 · C9 并发 · C10 成员隔离。期望结果和判断方法见 `AGENT_TASK.md`。

## 本地验证结果

用本地临时环境 + 模拟上游（支持流式和提示缓存）跑通：11 项 PASS，C5 INFO，C7 WARN。

C7 WARN 是 Sub2API 的已知行为：放行请求只要求余额 > 0、费用事后结算，所以余额很低的成员会先透支一次（金额 = 那次请求的费用）再被拒绝；并发透支由在途预留拦住。团队自用时影响很小，管理员留意负余额即可。
