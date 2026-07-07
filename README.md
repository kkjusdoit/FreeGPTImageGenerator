# Wenfxl 账号维护中心

[![Telegram Group](https://img.shields.io/badge/Telegram-Community_Chat-0088cc?style=for-the-badge&logo=telegram)](https://t.me/+4AmjbVPvvRgxMDVl)
[![License](https://img.shields.io/badge/License-CC_BY--NC_4.0-lightgrey?style=for-the-badge)](https://creativecommons.org/licenses/by-nc/4.0/legalcode)

这是一个面向已授权账号资产的轻量维护台，不再以自动注册为核心，而是聚焦在：

- 本地账号库存整理
- 已授权账号手工导入
- CPA / Sub2API 云端库存与配额查看
- 定期测活与状态维护
- OAuth 凭证刷新后的继续维护
- 微软邮箱资源库管理

> 仅用于你自己拥有、或明确授权你管理的账号与系统。
> 请确保使用过程符合所在地法律、平台规则与服务条款。

## 当前定位

这个仓库现在默认服务于“维护已存在资产”这条链路：

- 不再把自动注册作为主入口
- “仅注册成功”账号会单独列出，但默认不纳入后续 CPA 流程
- 支持把你已授权掌管的账号按文本格式导入本地库
- 对完整凭证账号可继续执行导出、云端推送、测活与配额查看

## 主要能力

### 1. 本地账号库

- 查看本地账号库存
- 按 `CPA可用 / 仅注册 / 全部` 分类筛选
- 批量导出账号、删除账号
- 将完整凭证账号推送到 CPA
- 导出 Sub2API 配置文件

### 2. 授权账号导入

支持手工导入你已经明确授权管理的账号，格式如下：

```text
email----password----client_id----refresh_token
```

导入行为说明：

- 仅做本地解析与入库
- 不联网验证
- 不自动登录
- 不自动测试第三方来源凭证

导入后的常见状态：

- `完整凭证`：已有完整 token，可纳入后续 CPA 维护
- `待刷新`：只有 `refresh_token`，可后续刷新补全
- `仅注册成功`：仅保留查看，不纳入后续 CPA 流程

### 3. 云端库存与配额管理

- 查看 CPA / Sub2API 云端账号
- 批量测活、启用、禁用、删除
- 查看最近检查时间
- 查看配额与用量缓存

### 4. 维护设置

保留与维护链路直接相关的配置：

- CPA 维护参数
- Sub2API 维护参数
- 定期巡检间隔
- Token revive 开关
- Sub2API 推送参数
- 微软邮箱 OAuth 维护

### 5. 微软邮箱资源库

- 导入微软邮箱数据
- 导出 TXT
- 删除、恢复状态
- 为单个邮箱补做 OAuth 授权

## 页面结构

当前前端主导航仅保留：

- `账号库存`
- `配额管理`
- `微软邮箱库`
- `维护设置`
- `维护日志`

## 快速开始

安装依赖：

```bash
pip install -r requirements.txt
```

启动服务：

```bash
python wfxl_openai_regst.py
```

浏览器打开：

```text
http://127.0.0.1:8000
```

默认控制台密码：

```text
admin
```

## 推荐使用流程

1. 启动服务并登录控制台
2. 在 `维护设置` 中配置 CPA / Sub2API / 本地邮箱维护参数
3. 在 `账号库存` 中导入你已授权的账号文本
4. 对 `完整凭证` 或 `待刷新` 账号进行后续维护
5. 在 `配额管理` 中查看云端状态与配额情况
6. 在 `维护日志` 中跟踪测活与维护过程

## 项目结构

```text
.
├── wfxl_openai_regst.py     # Web 控制台入口
├── global_state.py          # 全局状态
├── routers/                 # 后端 API 路由
├── utils/                   # 核心逻辑、数据库与配置
├── static/                  # 前端静态资源
├── assets/                  # README 资源
├── data/                    # 本地配置、SQLite、导出数据
├── index.html               # 前端入口
├── config.example.yaml      # 配置模板
├── requirements.txt         # Python 依赖
└── README.md                # 项目说明
```

## Docker

如果你已经有现成的容器部署习惯，也可以继续使用仓库中的 `Dockerfile` / `docker-compose.yml`。

建议保留的数据目录：

- `data/config.yaml`
- `data/data.db`
- `data/` 下的本地导出与运行数据

## 说明

- 本项目当前文档以“账号维护中心”视角编写
- 历史版本中的注册、接码、代理池、分布式注册等能力已不再作为默认主流程展示
- 若你在升级已有部署，请优先保留 `data/` 下的运行数据与本地配置
