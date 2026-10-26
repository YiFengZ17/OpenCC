# 分组与 credit 核对

核对日期：2026-10-24。

来源： https://console.supergpt.dev/api/v1/model-plaza ，帮助文档 https://console.supergpt.dev/help/models-and-billing 。

沿用原定服务范围 Claude、GPT、Grok。公开接口还包含 Gemini，本轮没有扩展该服务。

| 分组 | 计费依据 |
| --- | --- |
| grok | 基础 Token 价格 × 0.15 |
| ChatGPT-Pro【稳定】 | 基础 Token 价格 × 0.22 |
| ChatGPT-Pro【企业】 | 基础 Token 价格 × 0.25 |
| ChatGPT-ProMax【企业】 | 基础 Token 价格 × 0.36 |
| claude 满血kiro 纯满血 | credit_billing.enabled=true，unit_price=0.095 |

上游帮助页说明“实付”以人民币展示、已包含适用倍率；美元官方参考价不是最终扣款。不能将人民币实付金额再次换汇。OpenCC 沿用已确认的数值计价方式。

Claude 描述提及 0.12，但结构化接口实际为 0.095。当前价格展示采用 ¥0.095/credit，10 credit 为 ¥0.95。credit 是上游计量单位，不等同于 1 元、1 Token 或一次请求；没有证据支持固定换算成 Token 数。不再使用此分组 0.8 的 Token 倍率计算 credit 账单。

## 上线配置边界

`deploy/opencc-groups.json` 保存分组方案及来源 ID。上游 ID 不作为本站数据库 ID。用户页面使用本站 `/groups/available` 的权限，创建密钥仍绑定本站分组 ID。

当前没有真实后台、数据库和上游凭证，分组方案未写入生产数据库。预览可选分组为演示数据，公开目录明确标注待接入。

当前 Sub2API 版本没有上游 SuperGPT 私有的 credit_billing 扣费实现。**Claude credit 分组在取得实际响应中的 credit 字段及结算口径、完成幂等记账适配前不得开放售卖。**不能从 Token 数估算 credit 后冒充实际扣费。其余 Token 分组可通过原生管理后台建立，绑定对应渠道和模型价格后联调。图片独立倍率与时段、阶梯价格仍须单独核对。

## 认证

注册页包含用户名、邮箱、密码、确认密码。用户名保存到用户记录，邮箱为登录标识。没有短信流程；现有邮箱验证码、验证码与双因素设置保留，是否开启由部署配置决定。本地预览关闭邮箱验证码，但未绕过生产认证。
