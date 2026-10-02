#!/usr/bin/env python3
"""
看板邮件报告脚本
- 读取 email_config.yaml 配置
- 从数据库查询当月/本季签约、验收、收款数据
- 发送 HTML 邮件
"""
import pymysql, yaml, smtplib, ssl, os, sys, traceback
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date, timedelta
import datetime as dt

# ---------- 日志配置 ----------
LOG_DIR = '/root/project_crud/logs'
LOG_FILE = os.path.join(LOG_DIR, 'kanban_report.log')

def log(msg, level='INFO'):
    """写到日志文件 + stdout，level: INFO/WARN/ERROR"""
    ts = dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] [{level}] {msg}'
    print(line, flush=True)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception as e:
        print(f'[WARN] 写日志文件失败: {e}', flush=True)

def log_run_start():
    log('=' * 60)
    log(f'kanban_report.py 开始执行')
    log(f'Python: {sys.version.split()[0]}')
    log(f'工作目录: {os.getcwd()}')
    log(f'环境 PYTHONPATH: {os.environ.get("PYTHONPATH", "(未设置)")}')
    log(f'Cron 环境变量 CODON_*: {[k for k in os.environ if k.startswith("CODON_")]}')
    log('=' * 60)

def log_run_end(success=True, detail=''):
    if success:
        log(f'执行完成 {detail}')
    else:
        log(f'执行异常终止 {detail}', 'ERROR')
    log('=' * 60)

# ---------- 主逻辑 ----------
try:
    log_run_start()

    # ---------- 配置 ----------
    cfg_path = '/root/project_crud/email_config.yaml'
    log(f'读取配置文件: {cfg_path}')
    with open(cfg_path, encoding='utf-8') as f:
        cfg = yaml.safe_load(f)

    ec = cfg.get('email', {})
    if not ec.get('enabled'):
        log('邮件发送未启用，退出', 'WARN')
        log_run_end(success=True)
        sys.exit(0)

    now = date.today()
    year, month = now.year, now.month
    log(f'当前日期: {now}')

    def get_quarter_range(y, m):
        quarter = (m - 1) // 3 + 1
        q_start_month = (quarter - 1) * 3 + 1
        q_end_month = q_start_month + 2
        q_start = date(y, q_start_month, 1)
        if q_end_month == 12:
            q_end = date(y + 1, 1, 1) - timedelta(days=1)
        else:
            q_end = date(y, q_end_month + 1, 1) - timedelta(days=1)
        return q_start, q_end

    q_start, q_end = get_quarter_range(year, month)
    log(f'本季区间: {q_start} ~ {q_end}')

    # ---------- 数据库 ----------
    log('开始连接数据库...')
    conn = pymysql.connect(
        host=ec.get('db_host', '47.92.224.221'),
        port=int(ec.get('db_port', 33067)),
        user=ec.get('db_user', 'root'),
        password=ec.get('db_password', 'Showhanjian@gmail.com'),
        database=ec.get('db_name', 'workdb'),
        charset='utf8mb4',
        connect_timeout=10,
        read_timeout=30
    )
    log('数据库连接成功')
    cursor = conn.cursor()

    # 测试时只发307868053@qq.com
    TEST_MODE = False

    def calc_plan_done_sign(cursor, d_start, d_end):
        overdue_sql = """
            SELECT id, project_no, project_name, sign_amt, sign_status, owner,
                   DATE_FORMAT(sign_date, '%%Y-%%m-%%d'), sign_followup
            FROM project_db
            WHERE (sign_date < %s AND sign_status = '计划')
               OR (sign_date IS NULL AND sign_status = '计划')
        """
        period_sql = """
            SELECT id, project_no, project_name, sign_amt, sign_status, owner,
                   DATE_FORMAT(sign_date, '%%Y-%%m-%%d'), sign_followup
            FROM project_db
            WHERE sign_date >= %s AND sign_date <= %s
        """
        cursor.execute(overdue_sql, (d_start.isoformat(),))
        overdue_rows = cursor.fetchall()
        cursor.execute(period_sql, (d_start.isoformat(), d_end.isoformat()))
        period_rows = cursor.fetchall()
        rows = sorted(overdue_rows + period_rows, key=lambda r: (r[6] is None, str(r[6]) if r[6] else ''))
        total_plan = sum(r[3] or 0 for r in rows)
        total_done = sum(r[3] or 0 for r in rows if r[4] == '完成')
        return rows, (total_plan, total_done)

    def calc_pay(cursor, pay_type, d_start, d_end):
        if pay_type == 'first':
            df = 'first_pay_date'; af = 'first_pay_amt'; sf = 'first_pay_status'
        else:
            df = 'final_pay_date'; af = 'final_pay_amt'; sf = 'final_pay_status'
        overdue_sql = f"""
            SELECT id, project_no, project_name, {af}, {sf}, owner,
                   DATE_FORMAT({df}, '%%Y-%%m-%%d')
            FROM project_db
            WHERE {df} < %s AND {sf} = '计划'
        """
        period_sql = f"""
            SELECT id, project_no, project_name, {af}, {sf}, owner,
                   DATE_FORMAT({df}, '%%Y-%%m-%%d')
            FROM project_db
            WHERE {df} >= %s AND {df} <= %s
        """
        cursor.execute(overdue_sql, (d_start.isoformat(),))
        overdue_rows = cursor.fetchall()
        cursor.execute(period_sql, (d_start.isoformat(), d_end.isoformat()))
        period_rows = cursor.fetchall()
        rows = sorted(overdue_rows + period_rows,
                     key=lambda r: (r[6] is None, str(r[6]) if r[6] else ''))
        total_plan = sum(r[3] or 0 for r in rows)
        total_done = sum(r[3] or 0 for r in rows if r[4] == '完成')
        return rows, (total_plan, total_done)

    log('查询签约数据...')
    sign_quarter, sign_quarter_totals = calc_plan_done_sign(cursor, q_start, q_end)
    log(f'  签约本季: {len(sign_quarter)} 条')

    log('查询验收数据...')
    # 验收本季: accept_date <= q_end AND actual_handover IS NULL（无下限），金额取 accept_amt
    accept_quarter_sql = """
        SELECT id, project_no, project_name, accept_amt, accept_status, owner,
               DATE_FORMAT(accept_date, '%%Y-%%m-%%d'), accept_followup,
               DATE_FORMAT(actual_handover, '%%Y-%%m-%%d')
        FROM project_db
        WHERE accept_date <= %s AND actual_handover IS NULL
        ORDER BY accept_date
    """
    cursor.execute(accept_quarter_sql, (q_end.isoformat(),))
    accept_quarter = cursor.fetchall()
    accept_quarter_totals = (
        sum(r[3] or 0 for r in accept_quarter),
        sum(r[3] or 0 for r in accept_quarter if r[4] == '完成')
    )
    log(f'  验收本季: {len(accept_quarter)} 条')

    log('查询首款数据...')
    fp_q, fp_q_t = calc_pay(cursor, 'first', q_start, q_end)
    log(f'  首款本季: {len(fp_q)} 条')

    log('查询尾款数据...')
    lp_q, lp_q_t = calc_pay(cursor, 'final', q_start, q_end)
    log(f'  尾款本季: {len(lp_q)} 条')

    cursor.close()
    conn.close()
    log('数据库查询完成')

    # ---------- 生成 HTML（看板样式） ----------
    CSS = """
<style>
body{font-family:Arial,sans-serif;margin:20px;background:#f5f5f5}
.notice{background:#fff3cd;border:2px solid #ffc107;border-radius:8px;padding:14px 18px;margin-bottom:20px;font-size:15px;font-weight:bold;color:#856404;text-align:center}
.notice span{font-size:18px;margin-right:8px}
h2{font-size:14px;margin:20px 0 4px;color:#333}
h2:first-child{margin-top:0}
h3{font-size:13px;color:#555;margin:8px 0 4px;border-bottom:1px solid #eee;padding-bottom:4px}
.kanban-card{background:#fff;border-radius:8px;padding:14px 16px;box-shadow:0 1px 4px rgba(0,0,0,.1);margin-bottom:16px}
table{width:100%;border-collapse:collapse;font-size:12px;table-layout:fixed}
th{background:#cce4fc;color:#333;font-weight:600;text-align:left;padding:6px 8px;border-bottom:2px solid #b8d4f8;white-space:nowrap}
td{padding:5px 8px;border-bottom:1px solid #e8e8e8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
tr:hover td{background:#f0f7ff}
.status-plan td{background:#fff9e6}
.status-done td{background:#e8f5ed}
tr:hover .status-plan td{background:#fff3cc}
tr:hover .status-done td{background:#d9eddf}
.total-row td{background:#f0f0f0;font-weight:bold;border-top:2px solid #ccc}
.empty-cell{color:#999;text-align:center;padding:16px}
.footer{color:#888;font-size:11px;margin-top:20px}
</style>
"""

    # ---------- 生成 HTML（与看板页面字段一致） ----------
    COL_WIDTHS = {
        'plan_date': 'width:121px',
        'project_no': 'width:138px',
        'project_name': 'width:320px',
        'plan_amt': 'width:115px',
        'owner': 'width:100px',
        'status': 'width:100px',
        'followup': 'width:200px',
        'actual': 'width:120px',
    }

    CSS = """
<style>
body{font-family:Arial,sans-serif;margin:20px;background:#f5f5f5}
.notice{background:#fff3cd;border:2px solid #ffc107;border-radius:8px;padding:14px 18px;margin-bottom:20px;font-size:15px;font-weight:bold;color:#856404;text-align:center}
h2{font-size:14px;margin:20px 0 4px;color:#333}
h2:first-child{margin-top:0}
h3{font-size:13px;color:#555;margin:8px 0 4px;border-bottom:1px solid #eee;padding-bottom:4px}
.kanban-card{background:#fff;border-radius:8px;padding:14px 16px;box-shadow:0 1px 4px rgba(0,0,0,.1);margin-bottom:16px}
table{width:100%;border-collapse:collapse;font-size:12px;table-layout:fixed}
th{background:#cce4fc;color:#333;font-weight:600;text-align:left;padding:6px 8px;border-bottom:2px solid #b8d4f8;white-space:nowrap}
td{padding:5px 8px;border-bottom:1px solid #e8e8e8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
tr:hover td{background:#f0f7ff}
.status-plan td{background:#fff9e6}
.status-done td{background:#e8f5ed}
tr:hover .status-plan td{background:#fff3cc}
tr:hover .status-done td{background:#d9eddf}
.total-row td{background:#f0f0f0;font-weight:bold;border-top:2px solid #ccc}
.empty-cell{color:#999;text-align:center;padding:16px}
.footer{color:#888;font-size:11px;margin-top:20px}
</style>
"""

    def fmt_amt(v):
        if v is None:
            return '-'
        try:
            return f'{float(v):.2f}'
        except:
            return str(v)

    def make_sign_table(rows, totals):
        """签约表：计划日期、项目编号、项目名称、计划金额、负责人、完成情况、签约跟踪"""
        if not rows:
            return '<p class="empty-cell">暂无数据</p>'
        html = '<table>'
        html += '<colgroup>'
        html += f'<col style="{COL_WIDTHS["plan_date"]}">'
        html += f'<col style="{COL_WIDTHS["project_no"]}">'
        html += f'<col style="{COL_WIDTHS["project_name"]}">'
        html += f'<col style="{COL_WIDTHS["plan_amt"]}">'
        html += f'<col style="{COL_WIDTHS["owner"]}">'
        html += f'<col style="{COL_WIDTHS["status"]}">'
        html += f'<col style="{COL_WIDTHS["followup"]}">'
        html += '</colgroup>'
        html += '<tr><th>计划日期</th><th>项目编号</th><th>项目名称</th><th>计划金额</th><th>负责人</th><th>完成情况</th><th>签约跟踪</th></tr>'
        for r in rows:
            cls = 'status-plan' if r[4] == '计划' else 'status-done'
            html += f'<tr class="{cls}">'
            html += f'<td>{r[6] or "-"}</td>'
            html += f'<td>{r[1] or "-"}</td>'
            html += f'<td style="max-width:320px;overflow:hidden;text-overflow:ellipsis">{r[2] or "(无名称)"}</td>'
            html += f'<td>{fmt_amt(r[3])}</td>'
            html += f'<td>{r[5] or "-"}</td>'
            html += f'<td>{r[4] or "-"}</td>'
            html += f'<td style="max-width:200px;overflow:hidden;text-overflow:ellipsis">{r[7] or "-"}</td>'
            html += '</tr>'
        html += f'<tr class="total-row"><td></td><td></td><td>合计</td><td>{fmt_amt(totals[0])}</td><td></td><td></td><td></td></tr>'
        html += '</table>'
        return html

    def make_accept_table(rows, totals):
        """验收表：计划日期、项目编号、项目名称、计划金额、负责人、完成情况、验收跟踪、实际上会"""
        if not rows:
            return '<p class="empty-cell">暂无数据</p>'
        html = '<table>'
        html += '<colgroup>'
        html += f'<col style="{COL_WIDTHS["plan_date"]}">'
        html += f'<col style="{COL_WIDTHS["project_no"]}">'
        html += f'<col style="{COL_WIDTHS["project_name"]}">'
        html += f'<col style="{COL_WIDTHS["plan_amt"]}">'
        html += f'<col style="{COL_WIDTHS["owner"]}">'
        html += f'<col style="{COL_WIDTHS["status"]}">'
        html += f'<col style="{COL_WIDTHS["followup"]}">'
        html += f'<col style="{COL_WIDTHS["actual"]}">'
        html += '</colgroup>'
        html += '<tr><th>计划日期</th><th>项目编号</th><th>项目名称</th><th>计划金额</th><th>负责人</th><th>完成情况</th><th>验收跟踪</th><th>实际上会</th></tr>'
        for r in rows:
            cls = 'status-plan' if r[4] == '计划' else 'status-done'
            html += f'<tr class="{cls}">'
            html += f'<td>{r[6] or "-"}</td>'
            html += f'<td>{r[1] or "-"}</td>'
            html += f'<td style="max-width:320px;overflow:hidden;text-overflow:ellipsis">{r[2] or "(无名称)"}</td>'
            html += f'<td>{fmt_amt(r[3])}</td>'
            html += f'<td>{r[5] or "-"}</td>'
            html += f'<td>{r[4] or "-"}</td>'
            html += f'<td style="max-width:200px;overflow:hidden;text-overflow:ellipsis">{r[7] or "-"}</td>'
            html += f'<td style="max-width:120px;overflow:hidden;text-overflow:ellipsis">{r[8] or "-"}</td>'
            html += '</tr>'
        html += f'<tr class="total-row"><td></td><td></td><td>合计</td><td>{fmt_amt(totals[0])}</td><td></td><td></td><td></td><td></td></tr>'
        html += '</table>'
        return html

    def make_pay_table(rows, totals):
        """收款表（首款/尾款）：计划日期、项目编号、项目名称、计划金额、负责人、完成情况"""
        if not rows:
            return '<p class="empty-cell">暂无数据</p>'
        html = '<table>'
        html += '<colgroup>'
        html += f'<col style="{COL_WIDTHS["plan_date"]}">'
        html += f'<col style="{COL_WIDTHS["project_no"]}">'
        html += f'<col style="{COL_WIDTHS["project_name"]}">'
        html += f'<col style="{COL_WIDTHS["plan_amt"]}">'
        html += f'<col style="{COL_WIDTHS["owner"]}">'
        html += f'<col style="{COL_WIDTHS["status"]}">'
        html += '</colgroup>'
        html += '<tr><th>计划日期</th><th>项目编号</th><th>项目名称</th><th>计划金额</th><th>负责人</th><th>完成情况</th></tr>'
        for r in rows:
            cls = 'status-plan' if r[4] == '计划' else 'status-done'
            html += f'<tr class="{cls}">'
            html += f'<td>{r[6] or "-"}</td>'
            html += f'<td>{r[1] or "-"}</td>'
            html += f'<td style="max-width:320px;overflow:hidden;text-overflow:ellipsis">{r[2] or "(无名称)"}</td>'
            html += f'<td>{fmt_amt(r[3])}</td>'
            html += f'<td>{r[5] or "-"}</td>'
            html += f'<td>{r[4] or "-"}</td>'
            html += '</tr>'
        html += f'<tr class="total-row"><td></td><td></td><td>合计</td><td>{fmt_amt(totals[0])}</td><td></td><td></td></tr>'
        html += '</table>'
        return html

    body = f"""
<html><body>
{CSS}
<div class="notice">⚠️ 请曹维洋、菜根谭及时同步信息， 谢谢！http://47.92.224.221:35821</div>
<h2>📋 签约</h2>
<div class="kanban-card">
  <h3>本季计划及完成情况</h3>
  {make_sign_table(sign_quarter, sign_quarter_totals)}
</div>

<h2>✅ 验收</h2>
<div class="kanban-card">
  <h3>本季计划及完成情况</h3>
  {make_accept_table(accept_quarter, accept_quarter_totals)}
</div>

<h2>💰 首款收款</h2>
<div class="kanban-card">
  <h3>本季计划及完成情况</h3>
  {make_pay_table(fp_q, fp_q_t)}
</div>

<h2>💰 尾款收款</h2>
<div class="kanban-card">
  <h3>本季计划及完成情况</h3>
  {make_pay_table(lp_q, lp_q_t)}
</div>

<p class="footer">由项目管理系统自动生成 · {now}</p>
</body></html>
"""

    log('生成 HTML 完成，准备发送邮件...')

    # 解析收件人
    if TEST_MODE:
        recipients = ['307868053@qq.com']
    else:
        raw_recipients = ec.get('recipients', [])
        if isinstance(raw_recipients, str):
            raw_recipients = [raw_recipients]
        recipients = []
        for r in raw_recipients:
            recipients.extend(r.replace(';', ',').split(','))
        recipients = [x.strip() for x in recipients if x.strip()]
    log(f'收件人列表: {recipients}')

    # ---------- 发送邮件 ----------
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f'湖北建行KPI跟踪{now.strftime("%Y%m%d")}'
    msg['From'] = ec.get('sender', '')
    msg['To'] = ', '.join(recipients)
    msg.attach(MIMEText(body, 'html', 'utf-8'))

    enc = ec.get('encryption', 'none')
    smtp_host = ec.get('smtp_host', 'smtp.git.com.cn')
    smtp_port = int(ec.get('smtp_port', 587))
    log(f'连接 SMTP: {smtp_host}:{smtp_port}, 加密: {enc}')

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    if enc == 'ssl':
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=ctx) as server:
            log('SMTP_SSL 连接建立，尝试登录...')
            server.login(ec.get('username', ''), ec.get('password', ''))
            server.sendmail(ec.get('sender', ''), recipients, msg.as_string())
    elif enc == 'tls':
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            log('SMTP 连接建立，执行 STARTTLS...')
            server.starttls(context=ctx)
            log('TLS 握手完成，尝试登录...')
            server.login(ec.get('username', ''), ec.get('password', ''))
            log('SMTP 登录成功，发送邮件...')
            server.sendmail(ec.get('sender', ''), recipients, msg.as_string())
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.sendmail(ec.get('sender', ''), recipients, msg.as_string())

    log('邮件发送成功！')
    log_run_end(success=True)

except Exception as e:
    err_detail = f'{type(e).__name__}: {e}\n{traceback.format_exc()}'
    log(f'异常: {err_detail}', 'ERROR')
    log_run_end(success=False)
    sys.exit(1)
