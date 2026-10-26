# OpenCC

创建日期：2026-10-23

仓库：https://github.com/YiFengZ17/OpenCC（私有）。

## 项目定位
基于 Sub2API 的团队内部模型 API 工具：管理员向上游采购调用额度，为团队成员开通账号、独立 API Key 和人民币余额，按高于上游成本的价格扣费，差额为毛利（见 opencc-docs/11）。

已实现：OpenCC 用户界面、模型检测、人民币计价、兑换码充值、后台毛利统计、数据库备份脚本。已在本地用 PostgreSQL + Redis + 模拟上游完成调用、扣费、毛利和上游倍率同步的端到端验证（opencc-docs/07）。尚未部署到 VPS，也未接入真实上游。

## 阅读与执行顺序
1. opencc-docs/04-实现与部署说明.md：本地运行、页面、上线步骤。
2. opencc-docs/05-待配置项.md：上线前需要填写的配置。
3. opencc-docs/11-团队自用与差价计费.md：成本倍率 U、售价倍率 D、后台配置步骤。
4. opencc-docs/08-分组与credit核对.md：上游各分组计费方式，Claude 为 credit 计费。
5. opencc-docs/10-credit结算接入进度.md：Claude credit 逐笔结算模块的进度与启用前条件。
6. opencc-docs/06-模型检测与积分计费.md：ModelTrace 与计价单位细节。
7. opencc-docs/07-验收记录.md、09-前端更新验收.md：已验证与未验证项。

计费自测：`tools/opencc-billing-selftest/run-local.sh`（本地临时环境 + 模拟上游，10 项检查）。

早期规划文档（01–03 及实施计划）不在本仓库中。

## 当前设计基线
- 先验证供应资格、技术兼容、真实成本与客户需求，再采购正式运营资源。
- 首版采用现有网关；单上游、小规模、明确模型白名单。
- 首版网页已实现中国大陆 IP 提示：仅可信 CN 显示用户指定原文，其他地区不显示；生产环境需按部署说明配置可信代理。
- 先实现调用与记账闭环，再接自动支付；不把建站完成视为可以收费。
- 团队内收款后由管理员加余额或发放兑换码；外部发卡平台（wzyp.cn）可选。Sub2API 原生支付不启用。
- 上游凭证只保存在服务端，客户使用本站独立密钥。
- 不把客户预付款全部视为收入或利润；保留待履约余额与退款记录。

## 已指定资源（2026-10-23 更新）
- 上游控制台：https://console.supergpt.dev/；常规 Claude API 地址：https://api.supergpt.dev，分组条件待确认。
- 实际服务器：Vultr 东京，45.76.217.218，Ubuntu 24.04，4 vCPU / 8 GB / 180 GB NVMe；替代原 OVH 计划。
- 域名/DNS 平台：https://dash.cloudflare.com/；实际域名 opencc.app。
- 发卡、收款、额度销售平台：https://wzyp.cn/；用户已确认用途，公开业务能力尚未核实。
- 中转程序：https://github.com/Wei-Shaw/sub2api。
- SuperGPT 公开文档声明不向中国大陆用户提供服务；需确认经营主体和目标客户的适用条件。当前仅登记来源，未确认分销权限。
- https://github.com/YiFengZ17/OpenCC 为云端私人仓库


## 文档使用约定
未填写的内容均为待确认，不代表承诺。截图报价与营销描述不是验收证据。
信息表仅记录密钥保存位置，禁止填写真实密码、API Key、支付签名密钥或个人证件。
