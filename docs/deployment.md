# 部署现有 Python 网页

## 已准备与未完成

已提供 Dockerfile、render.yaml 和独立云端入口 `aftersales.hosting`。
当前尚未在云平台创建服务，没有线上网址；需先选择平台并完成账号登录、代码仓库连接。
本机没有 Docker，镜像构建尚未验证；入口可通过本地 Python 测试验证。

## 方案一：Render

1. 将部署包内文件上传至自己的私有 GitHub 仓库根目录，保持 src、data、web、reports 结构。
2. 在 Render 登录，New → Blueprint，连接该仓库，选择根目录 render.yaml。
3. 确认服务为 Docker、Free；在平台密钥配置中填写 QIANFAN_API_KEY（千帆 v2 密钥）和 DEMO_ACCESS_PASSWORD（至少16位随机访问密码）。不要把本地 .env 上传到仓库。
4. 部署后访问平台实际返回的 onrender.com 地址；浏览器访问凭据用户名为 demo，密码为上一步设置的值。
5. 验证首页、任一政策问答、高金额转人工、历史报告和真实评测；从服务日志检查启动错误。只有实际部署成功后，才能确认最终网址。

Free 服务存在空闲休眠和临时文件系统限制。会话/工单在内存中，服务重启会丢失；镜像中已有历史报告仍保留，新产生报告需另行导出，不能依赖其持久保存。面试前提前访问并验证。模型调用消耗千帆账户额度，与主机计费分开。

## 方案二：有 Docker 的云服务器

上传同一部署包，解压至项目目录。将云端密钥单独写入服务器受限的环境配置文件，权限只允许部署账户读取。

```sh
docker build -t aftersales-demo .
docker run -d --name aftersales-demo --restart unless-stopped --env-file /secure/aftersales.env -p 127.0.0.1:8000:8000 aftersales-demo
```

环境文件需要 AGENT_MODE=live、QIANFAN_API_KEY、DEMO_ACCESS_USERNAME=demo、DEMO_ACCESS_PASSWORD。
前方配置 HTTPS 反向代理，再通过域名访问；访问密码采用 HTTP Basic，必须通过 HTTPS 使用。
健康检查为 /healthz，仅返回存活状态；页面、静态文件、文档及业务接口均需要访问密码。
仅运行1个 worker/实例：目前会话和工单不在共享数据库中。

## 离线展示

将 AGENT_MODE 改为 offline 可以先部署模板演示，不需要千帆密钥，仍需访问密码。离线评测通过不代表真实模型验收。

## 官方资料

- [Render Docker](https://render.com/docs/docker)
- [Blueprint](https://render.com/docs/blueprint-spec)
- [环境变量](https://render.com/docs/configure-environment-variables)
- [免费服务限制](https://render.com/docs/free)
