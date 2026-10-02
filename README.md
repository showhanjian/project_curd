# Project CURD

Flask + MySQL 看板/项目管理小工具，附带邮件报告功能。

## 目录结构

- `app.py`：Flask Web 应用主入口
- `kanban_report.py`：看板数据邮件报告脚本（依赖 `email_config.yaml`）
- `migrate_rebuild.py`：数据库迁移/重建脚本
- `templates/`、`static/`：前端模板与样式
- `appctl.sh` / `start.sh`：进程控制脚本
- `config.yaml.example` / `email_config.yaml.example`：配置模板

## 本地启动

1. 复制配置文件样例并填写真实信息：

   ```bash
   cp config.yaml.example config.yaml
   cp email_config.yaml.example email_config.yaml
   ```

2. 安装依赖（建议使用虚拟环境）：

   ```bash
   pip install flask pymysql pyyaml
   ```

3. 启动：

   ```bash
   ./start.sh
   # 或者直接 python app.py
   ```

## 邮件报告

通过 cron 或 `appctl.sh` 调度 `kanban_report.py` 即可发送当月/本季看板数据邮件。收件人在 `email_config.yaml` 中维护。

## 安全注意

`config.yaml` 与 `email_config.yaml` 已被 `.gitignore` 忽略，**请勿** 将含真实密码的文件提交到仓库。

