import pymysql, yaml, io
from flask import Flask, render_template, request, redirect, url_for, flash, make_response
from datetime import datetime, date, timedelta
from urllib.parse import quote_plus, unquote_plus
import datetime as dt
app = Flask(__name__)
app.jinja_env.add_extension('jinja2.ext.do')
app.secret_key = 'project_crud_secret_key_2026'


@app.context_processor
def inject_utils():
    return dict(unquote_plus=unquote_plus)


@app.context_processor
def inject_update_param():
    from werkzeug.datastructures import ImmutableMultiDict
    def update_param(key, value):
        args = request.args.copy()
        args[key] = value
        return '&'.join(f'{k}={v}' for k, v in args.items())
    def sort_param(field):
        args = request.args.copy()
        if args.get('sort') == field:
            args['dir'] = 'asc' if args.get('dir', 'desc') == 'desc' else 'desc'
        else:
            args['sort'] = field
            args['dir'] = 'desc'
        return '&'.join(f'{k}={v}' for k, v in args.items())
    return dict(update_param=update_param, sort_param=sort_param)

DB_CONFIG = {
    'host': '47.92.224.221',
    'port': 33067,
    'user': 'root',
    'password': 'Showhanjian@gmail.com',
    'database': 'workdb',
    'charset': 'utf8mb4'
}

AUTH_CODE='hanjian'

def get_db():
    return pymysql.connect(**DB_CONFIG)


def get_quarter_range(year, month):
    quarter = (month - 1) // 3 + 1
    q_start_month = (quarter - 1) * 3 + 1
    q_end_month = q_start_month + 2
    q_start = date(year, q_start_month, 1)
    if q_end_month == 12:
        q_end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        q_end = date(year, q_end_month + 1, 1) - timedelta(days=1)
    return q_start, q_end


def calc_plan_done(cursor, date_field, start_date, end_date, status_field='sign_status', followup_field='sign_followup', extra_date_field=None):
    extra_select = f', {extra_date_field}' if extra_date_field else ''
    overdue_sql = f"""
        SELECT id, project_no, project_name, sign_amt, {status_field}, owner, {date_field}, {followup_field}{extra_select}
        FROM project_db
        WHERE ({date_field} < %s AND {status_field} = '计划')
           OR ({date_field} IS NULL AND {status_field} = '计划')
    """
    period_sql = f"""
        SELECT id, project_no, project_name, sign_amt, {status_field}, owner, {date_field}, {followup_field}{extra_select}
        FROM project_db
        WHERE {date_field} >= %s AND {date_field} <= %s
    """
    cursor.execute(overdue_sql, (start_date.isoformat(),))
    overdue_rows = cursor.fetchall()
    cursor.execute(period_sql, (start_date.isoformat(), end_date.isoformat()))
    period_rows = cursor.fetchall()
    rows = sorted(overdue_rows + period_rows, key=lambda r: (r[6] is None, str(r[6]) if r[6] else ''))
    total_plan = sum(r[3] or 0 for r in rows)
    total_done = sum(r[3] or 0 for r in rows if r[4] == '完成')
    return rows, (total_plan, total_done)


def calc_pay_plan_done(cursor, pay_field, start_date, end_date):
    overdue_sql = f"""
        SELECT id, project_no, project_name, {pay_field}_amt, {pay_field}_status, owner, {pay_field}_date
        FROM project_db
        WHERE {pay_field}_date < %s AND {pay_field}_status = '计划'
    """
    period_sql = f"""
        SELECT id, project_no, project_name, {pay_field}_amt, {pay_field}_status, owner, {pay_field}_date
        FROM project_db
        WHERE {pay_field}_date >= %s AND {pay_field}_date <= %s
    """
    cursor.execute(overdue_sql, (start_date.isoformat(),))
    overdue_rows = cursor.fetchall()
    cursor.execute(period_sql, (start_date.isoformat(), end_date.isoformat()))
    period_rows = cursor.fetchall()
    rows = sorted(overdue_rows + period_rows, key=lambda r: (r[6] is None, str(r[6]) if r[6] else ''))
    total_plan = sum(r[3] or 0 for r in rows)
    total_done = sum(r[3] or 0 for r in rows if r[4] == '完成')
    return rows, (total_plan, total_done)


def get_kanban_data(conn, year=None, month=None):
    """获取看板所有数据，供页面和邮件报告共用"""
    if year is None or month is None:
        now = datetime.now()
        year, month = now.year, now.month
    m_start = date(year, month, 1)
    m_end = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year + 1, 1, 1) - timedelta(days=1)
    q_start, q_end = get_quarter_range(year, month)

    cursor = conn.cursor()

    sign_quarter, sign_quarter_totals = calc_plan_done(cursor, 'sign_date', q_start, q_end)
    accept_quarter_sql = f"""
        SELECT id, project_no, project_name, accept_amt, accept_status, owner,
               accept_date, accept_followup, actual_handover
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

    fp_q, fp_q_totals = calc_pay_plan_done(cursor, 'first_pay', q_start, q_end)
    lp_q, lp_q_totals = calc_pay_plan_done(cursor, 'final_pay', q_start, q_end)

    cursor.close()

    return dict(
        year=year, month=month,
        m_start=m_start, m_end=m_end,
        q_start=q_start, q_end=q_end,
        sign_quarter=sign_quarter, sign_quarter_totals=sign_quarter_totals,
        accept_quarter=accept_quarter, accept_quarter_totals=accept_quarter_totals,
        fp_quarter=fp_q, fp_quarter_totals=fp_q_totals,
        lp_quarter=lp_q, lp_quarter_totals=lp_q_totals,
    )


@app.route('/')
def index():
    tab = request.args.get('tab', 'kanban')
    if tab == 'list':
        return render_template('index.html', tab='list')
    elif tab == 'analysis':
        return render_template('analysis.html', tab='analysis')
    else:
        conn = get_db()
        data = get_kanban_data(conn)
        conn.close()
        return render_template('kanban.html', tab='kanban', **data)


@app.route('/sign_kanban')
def sign_kanban():
    conn = get_db()
    now = datetime.now()
    year, month = now.year, now.month
    m_start = date(year, month, 1)
    m_end = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year + 1, 1, 1) - timedelta(days=1)
    q_start, q_end = get_quarter_range(year, month)
    y_start = date(year, 1, 1)
    y_end = date(year, 12, 31)
    cursor = conn.cursor()
    sign_month, sign_month_totals = calc_plan_done(cursor, 'sign_date', q_start, q_end)
    sign_quarter, sign_quarter_totals = calc_plan_done(cursor, 'sign_date', y_start, y_end)
    cursor.close()
    conn.close()
    return render_template(
        'sign_kanban.html', tab='sign_kanban',
        year=year, month=month,
        sign_month=sign_month, sign_month_totals=sign_month_totals,
        sign_quarter=sign_quarter, sign_quarter_totals=sign_quarter_totals,
    )


@app.route('/accept_kanban')
def accept_kanban():
    conn = get_db()
    now = datetime.now()
    year, month = now.year, now.month
    m_end = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year + 1, 1, 1) - timedelta(days=1)
    q_start, q_end = get_quarter_range(year, month)
    y_start = date(year, 1, 1)
    y_end = date(year, 12, 31)
    cursor = conn.cursor()
    accept_month_sql = f"""
        SELECT id, project_no, project_name, accept_amt, accept_status, owner,
               accept_date, accept_followup, actual_handover
        FROM project_db
        WHERE accept_date <= %s AND actual_handover IS NULL
        ORDER BY accept_date
    """
    cursor.execute(accept_month_sql, (q_end.isoformat(),))
    accept_month = cursor.fetchall()
    accept_month_totals = (
        sum(r[3] or 0 for r in accept_month),
        sum(r[3] or 0 for r in accept_month if r[4] == '完成')
    )
    accept_quarter_sql = f"""
        SELECT id, project_no, project_name, accept_amt, accept_status, owner,
               accept_date, accept_followup, actual_handover
        FROM project_db
        WHERE accept_date >= %s AND accept_date <= %s
        ORDER BY accept_date
    """
    cursor.execute(accept_quarter_sql, (y_start.isoformat(), y_end.isoformat(),))
    accept_quarter = cursor.fetchall()
    accept_quarter_totals = (
        sum(r[3] or 0 for r in accept_quarter),
        sum(r[3] or 0 for r in accept_quarter if r[4] == '完成')
    )
    cursor.close()
    conn.close()
    return render_template(
        'accept_kanban.html', tab='accept_kanban',
        year=year, month=month,
        accept_month=accept_month, accept_month_totals=accept_month_totals,
        accept_quarter=accept_quarter, accept_quarter_totals=accept_quarter_totals,
    )


@app.route('/fp_kanban')
def fp_kanban():
    conn = get_db()
    now = datetime.now()
    year, month = now.year, now.month
    m_start = date(year, month, 1)
    m_end = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year + 1, 1, 1) - timedelta(days=1)
    q_start, q_end = get_quarter_range(year, month)
    y_start = date(year, 1, 1)
    y_end = date(year, 12, 31)
    cursor = conn.cursor()
    fp_month, fp_month_totals = calc_pay_plan_done(cursor, 'first_pay', q_start, q_end)
    fp_quarter, fp_quarter_totals = calc_pay_plan_done(cursor, 'first_pay', y_start, y_end)
    cursor.close()
    conn.close()
    return render_template(
        'fp_kanban.html', tab='fp_kanban',
        year=year, month=month,
        fp_month=fp_month, fp_month_totals=fp_month_totals,
        fp_quarter=fp_quarter, fp_quarter_totals=fp_quarter_totals,
    )


@app.route('/lp_kanban')
def lp_kanban():
    conn = get_db()
    now = datetime.now()
    year, month = now.year, now.month
    m_start = date(year, month, 1)
    m_end = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year + 1, 1, 1) - timedelta(days=1)
    q_start, q_end = get_quarter_range(year, month)
    y_start = date(year, 1, 1)
    y_end = date(year, 12, 31)
    cursor = conn.cursor()
    lp_month, lp_month_totals = calc_pay_plan_done(cursor, 'final_pay', q_start, q_end)
    lp_quarter, lp_quarter_totals = calc_pay_plan_done(cursor, 'final_pay', y_start, y_end)
    cursor.close()
    conn.close()
    return render_template(
        'lp_kanban.html', tab='lp_kanban',
        year=year, month=month,
        lp_month=lp_month, lp_month_totals=lp_month_totals,
        lp_quarter=lp_quarter, lp_quarter_totals=lp_quarter_totals,
    )


@app.route('/list')
def list_view():
    search = request.args.get('search', '').strip()
    q = request.args.get('q', '')
    project_names = request.args.get('project_names', '').strip()
    sign_date_start = request.args.get('sign_date_start', '').strip()
    sign_date_end = request.args.get('sign_date_end', '').strip()
    accept_date_start = request.args.get('accept_date_start', '').strip()
    accept_date_end = request.args.get('accept_date_end', '').strip()
    pay1_date_start = request.args.get('pay1_date_start', '').strip()
    pay1_date_end = request.args.get('pay1_date_end', '').strip()
    pay2_date_start = request.args.get('pay2_date_start', '').strip()
    pay2_date_end = request.args.get('pay2_date_end', '').strip()
    sort_field = request.args.get('sort', 'sign_date')
    sort_dir = request.args.get('dir', 'desc')

    # 季度快捷查询
    if q:
        now = datetime.now()
        quarter = (now.month - 1) // 3 + 1
        q_start_month = (quarter - 1) * 3 + 1
        q_end_month = q_start_month + 2
        q_start = date(now.year, q_start_month, 1)
        if q_end_month == 12:
            q_end = date(now.year + 1, 1, 1) - timedelta(days=1)
        else:
            q_end = date(now.year, q_end_month + 1, 1) - timedelta(days=1)
        if q == 'sign_q':
            # 本季签约
            sign_date_start = q_start.isoformat()
            sign_date_end = q_end.isoformat()
        elif q == 'sign_y':
            # 本年签约
            sign_date_start = date(now.year, 1, 1).isoformat()
            sign_date_end = date(now.year, 12, 31).isoformat()
        elif q == 'accept_q':
            # 本季验收
            accept_date_start = q_start.isoformat()
            accept_date_end = q_end.isoformat()
        elif q == 'accept_y':
            # 本年验收
            accept_date_start = date(now.year, 1, 1).isoformat()
            accept_date_end = date(now.year, 12, 31).isoformat()
        elif q == 'pay1_q':
            # 本季首付
            pay1_date_start = q_start.isoformat()
            pay1_date_end = q_end.isoformat()
        elif q == 'pay1_y':
            # 本年首付
            pay1_date_start = date(now.year, 1, 1).isoformat()
            pay1_date_end = date(now.year, 12, 31).isoformat()
        elif q == 'pay2_q':
            # 本季尾款
            pay2_date_start = q_start.isoformat()
            pay2_date_end = q_end.isoformat()
        elif q == 'pay2_y':
            # 本年尾款
            pay2_date_start = date(now.year, 1, 1).isoformat()
            pay2_date_end = date(now.year, 12, 31).isoformat()

    allowed_sort = {
        'project_no':     'project_no',
        'sign_date':      'sign_date',
        'accept_date':    'accept_date',
        'first_pay_date': 'first_pay_date',
        'final_pay_date': 'final_pay_date',
    }
    sort_col = allowed_sort.get(sort_field, 'sign_date')
    # 升降序切换
    if request.args.get('sort') == sort_field:
        sort_dir = 'asc' if sort_dir == 'desc' else 'desc'
    else:
        sort_dir = 'asc'

    where_clauses = []
    params = []

    if search:
        where_clauses.append("(project_no LIKE %s OR project_name LIKE %s)")
        params.extend([f'%{search}%', f'%{search}%'])

    if project_names:
        names = [n.strip() for n in project_names.split(',') if n.strip()]
        if names:
            placeholders = ','.join(['%s'] * len(names))
            where_clauses.append(f"project_name IN ({placeholders})")
            params.extend(names)

    if sign_date_start:
        where_clauses.append("sign_date >= %s")
        params.append(sign_date_start)
    if sign_date_end:
        where_clauses.append("sign_date <= %s")
        params.append(sign_date_end)
    if accept_date_start:
        where_clauses.append("accept_date >= %s")
        params.append(accept_date_start)
    if accept_date_end:
        where_clauses.append("accept_date <= %s")
        params.append(accept_date_end)
    if pay1_date_start:
        where_clauses.append("first_pay_date >= %s")
        params.append(pay1_date_start)
    if pay1_date_end:
        where_clauses.append("first_pay_date <= %s")
        params.append(pay1_date_end)
    if pay2_date_start:
        where_clauses.append("final_pay_date >= %s")
        params.append(pay2_date_start)
    if pay2_date_end:
        where_clauses.append("final_pay_date <= %s")
        params.append(pay2_date_end)

    where_sql = ' AND '.join(where_clauses) if where_clauses else '1=1'

    conn = get_db()
    cursor = conn.cursor()

    query_sql = f"""
        SELECT
            id, project_no, project_name, demand_type,
            workload, extra_work,
            remark,
            sign_status, sign_amt, sign_date, sign_followup,
            attend_start, attend_end,
            accept_status, accept_amt, accept_date, actual_handover, accept_followup,
            first_pay_status, first_pay_amt, first_pay_date,
            final_pay_status, final_pay_amt, final_pay_date,
            profit_rate, profit_amt, owner
        FROM project_db
        WHERE {where_sql}
        ORDER BY {sort_col} {sort_dir}
    """
    cursor.execute(query_sql, params)
    rows = cursor.fetchall()

    # 所有项目名（用于多选过滤）
    cursor.execute("SELECT DISTINCT project_name FROM project_db WHERE project_name IS NOT NULL AND project_name != '' ORDER BY project_name")
    all_project_names = [r[0] for r in cursor.fetchall()]

    # 汇总：签约金额、验收金额、首款金额、尾款金额
    sum_sql = f"""
        SELECT
            COALESCE(SUM(sign_amt), 0)    AS total_sign_amt,
            COALESCE(SUM(accept_amt), 0)  AS total_accept_amt,
            COALESCE(SUM(first_pay_amt), 0) AS total_first_pay_amt,
            COALESCE(SUM(final_pay_amt), 0) AS total_final_pay_amt
        FROM project_db
        WHERE {where_sql}
    """
    cursor.execute(sum_sql, params)
    sums = cursor.fetchone()
    total_sign_amt      = sums[0] or 0
    total_accept_amt    = sums[1] or 0
    total_first_pay_amt = sums[2] or 0
    total_final_pay_amt = sums[3] or 0

    cursor.close()
    conn.close()

    return render_template('list.html',
                           tab='list',
                           rows=rows, search=search,
                           sign_date_start=sign_date_start, sign_date_end=sign_date_end,
                           accept_date_start=accept_date_start, accept_date_end=accept_date_end,
                           pay1_date_start=pay1_date_start, pay1_date_end=pay1_date_end,
                           pay2_date_start=pay2_date_start, pay2_date_end=pay2_date_end,
                           sort_field=sort_field, sort_dir=sort_dir, q=q,
                           dir=request.args.get('dir', 'desc'),
                           total_sign_amt=total_sign_amt,
                           total_accept_amt=total_accept_amt,
                           total_first_pay_amt=total_first_pay_amt,
                           total_final_pay_amt=total_final_pay_amt,
                           project_names=project_names,
                           project_names_list=project_names.split(',') if project_names else [],
                           all_project_names=all_project_names)


@app.route('/detail/<int:id>')
def detail(id):
    conn = get_db()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    cursor.execute("SELECT * FROM project_db WHERE ID = %s", (id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if not row:
        flash('记录不存在')
        return redirect(url_for('index'))
    return render_template('detail.html', row=row)


@app.route('/new', methods=['GET', 'POST'])
def new():
    if request.method == 'POST':
        data = {k: v for k, v in request.form.items() if v != '' and k != 'next'}
        for date_field in ['sign_date', 'accept_date', 'first_pay_date', 'final_pay_date', 'attend_start', 'attend_end', 'actual_handover']:
            data[date_field] = data.get(date_field) or None

        cols = list(data.keys())
        vals = list(data.values())
        placeholders = ', '.join(['%s'] * len(cols))
        col_names = ', '.join(cols)
        sql = f"INSERT INTO project_db ({col_names}) VALUES ({placeholders})"

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(sql, vals)
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(unquote_plus(request.form.get('next', '')) or request.args.get('next') or request.referrer or url_for('index'))

    return render_template('edit.html', row=None, next_url=quote_plus(request.args.get('next', '')))


@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit(id):
    conn = get_db()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    if request.method == 'POST':
        data = {k: v for k, v in request.form.items() if v != '' and k != 'next'}
        for date_field in ['sign_date', 'accept_date', 'first_pay_date', 'final_pay_date', 'attend_start', 'attend_end', 'actual_handover']:
            if date_field in data:
                data[date_field] = data[date_field] or None
            else:
                data[date_field] = None

        set_sql = ', '.join([f"{k} = %s" for k in data.keys()])
        sql = f"UPDATE project_db SET {set_sql} WHERE ID = %s"

        cursor.execute(sql, list(data.values()) + [id])
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(unquote_plus(request.form.get('next', '')) or request.args.get('next') or request.referrer or url_for('index'))

    cursor.execute("SELECT * FROM project_db WHERE ID = %s", (id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if not row:
        flash('记录不存在')
        return redirect(url_for('index'))
    return render_template('edit.html', row=row, next_url=quote_plus(request.args.get('next', '')))


@app.route('/system', methods=['GET', 'POST'])
def system():
    cfg_path = '/root/project_crud/email_config.yaml'
    with open(cfg_path, encoding='utf-8') as f:
        cfg = yaml.safe_load(f)

    email_cfg = cfg.get('email', {})

    if request.method == 'POST':
        recipients_raw = request.form.get('recipients', '').strip()
        recipients = [r.strip() for r in recipients_raw.split('\n') if r.strip()]

        # 密码为空时保留原值
        password = request.form.get('password', '').strip()
        if not password:
            password = email_cfg.get('password', '')

        cfg['email'] = {
            'enabled': request.form.get('email_enabled') == 'true',
            'smtp_host': request.form.get('smtp_host', ''),
            'smtp_port': int(request.form.get('smtp_port', 465)),
            'encryption': request.form.get('encryption', 'ssl'),
            'username': request.form.get('username', ''),
            'password': password,
            'sender': request.form.get('sender', ''),
            'recipients': recipients,
            'subject': request.form.get('subject', ''),
            'schedule': request.form.get('schedule', '0 9 * * 1'),
        }
        with open(cfg_path, 'w', encoding='utf-8') as f:
            yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
        flash('保存成功')

        # 更新内存中的 email_cfg
        email_cfg = cfg['email']
        return redirect(url_for('system'))

    now = datetime.now()
    return render_template('system.html', email_cfg=email_cfg,
                           year=now.year, month=now.month)


@app.route('/delete/<int:id>', methods=['POST'])
def delete(id):
    import sys
    print(f"=== DELETE id={id} ===", flush=True)
    code = request.form.get('auth_code', '').strip()
    print(f"code='{code}', AUTH_CODE='{AUTH_CODE}', match={code == AUTH_CODE}", flush=True)
    sys.stdout.flush()
    if code != AUTH_CODE:
        print("AUTH FAILED, redirecting", flush=True)
        flash('授权码错误')
        return redirect(url_for('list_view'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM project_db WHERE ID = %s", (id,))
    print(f"rows affected: {cursor.rowcount}", flush=True)
    conn.commit()
    print("committed", flush=True)
    cursor.close()
    conn.close()
    flash('删除成功')
    return redirect(url_for('list_view'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=35821, debug=True)


# 临时诊断路由：查各列最大字符宽度
@app.route('/col_widths')
def col_widths():
    import pymysql
    conn = pymysql.connect(host='127.0.0.1', port=3306, user='root', password='root', database='workdb')
    cur = conn.cursor()
    cur.execute('''SELECT
  MAX(LENGTH(COALESCE(project_no,""))) as project_no,
  MAX(LENGTH(COALESCE(project_name,""))) as project_name,
  MAX(LENGTH(COALESCE(demand_type,""))) as demand_type,
  MAX(LENGTH(COALESCE(CAST(workload AS CHAR),""))) as workload,
  MAX(LENGTH(COALESCE(supplement,""))) as supplement,
  MAX(LENGTH(COALESCE(remark,""))) as remark,
  MAX(LENGTH(COALESCE(sign_status,""))) as sign_status,
  MAX(LENGTH(COALESCE(CAST(sign_amt AS CHAR),""))) as sign_amt,
  MAX(LENGTH(COALESCE(sign_date,""))) as sign_date,
  MAX(LENGTH(COALESCE(sign_follow,""))) as sign_follow,
  MAX(LENGTH(COALESCE(accept_status,""))) as accept_status,
  MAX(LENGTH(COALESCE(CAST(accept_amt AS CHAR),""))) as accept_amt,
  MAX(LENGTH(COALESCE(accept_date,""))) as accept_date,
  MAX(LENGTH(COALESCE(actual_meeting,""))) as actual_meeting,
  MAX(LENGTH(COALESCE(first_status,""))) as first_status,
  MAX(LENGTH(COALESCE(CAST(first_amt AS CHAR),""))) as first_amt,
  MAX(LENGTH(COALESCE(first_date,""))) as first_date,
  MAX(LENGTH(COALESCE(final_status,""))) as final_status,
  MAX(LENGTH(COALESCE(CAST(final_amt AS CHAR),""))) as final_amt,
  MAX(LENGTH(COALESCE(final_date,""))) as final_date
FROM project_db''')
    row = cur.fetchone()
    cols = ['project_no','project_name','demand_type','workload','supplement','remark','sign_status','sign_amt','sign_date','sign_follow','accept_status','accept_amt','accept_date','actual_meeting','first_status','first_amt','first_date','final_status','final_amt','final_date']
    result = {c: v or 0 for c, v in zip(cols, row)}
    conn.close()
    return str(result)

@app.route('/run_sql')
def run_sql():
    sql = request.args.get('sql', '')
    if not sql:
        return 'No SQL'
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(sql)
        if sql.strip().upper().startswith('SELECT'):
            result = cur.fetchall()
            conn.close()
            return str(result)
        conn.commit()
        conn.close()
        return 'OK'
    except Exception as e:
        return str(e)


# ============================================================
# 导出Excel（/api/export）
# ============================================================
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from datetime import datetime as dt

@app.route('/api/export')
def api_export():
    # 1. 动态获取字段名（SHOW FULL COLUMNS，匹配 list.html 表头顺序）
    conn = get_db()
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute('SHOW FULL COLUMNS FROM project_db')
    db_cols = {r['Field']: r['Comment'] for r in cur.fetchall()}

    # 2. 字段顺序与 list.html 表头一致（id/project_no/project_name/...）
    field_order = [
        'project_no', 'project_name', 'demand_type', 'workload',
        'extra_work', 'remark',
        'sign_status', 'sign_amt', 'sign_date', 'sign_followup',
        'accept_status', 'accept_amt', 'accept_date', 'actual_handover', 'accept_followup',
        'attend_start', 'attend_end',
        'first_pay_status', 'first_pay_amt', 'first_pay_date',
        'final_pay_status', 'final_pay_amt', 'final_pay_date',
        'profit_rate'
    ]
    # 只保留数据库里有的字段
    fields = [f for f in field_order if f in db_cols]
    headers = [db_cols[f] for f in fields]

    # 3. 查数据
    cur.execute('SELECT * FROM project_db ORDER BY id')
    rows = cur.fetchall()
    conn.close()

    # 4. 生成 Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = '项目信息'

    hf  = Font(bold=True, color='FFFFFF', size=12)
    hb  = PatternFill(fill_type='solid', fgColor='4472C4')
    ha  = Alignment(horizontal='center', vertical='center')
    thin = Side(style='thin', color='000000')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # 写表头
    for col, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=col, value=h)
        c.font = hf
        c.fill = hb
        c.alignment = ha
        c.border = border

    # 写数据（DictCursor，按字段名取值）
    for row_idx, row in enumerate(rows, 2):
        for col_idx, field in enumerate(fields, 1):
            val = row.get(field, '')
            if val is None:
                val = ''
            # 日期转字符串
            if hasattr(val, 'strftime'):
                val = val.strftime('%Y-%m-%d')
            c = ws.cell(row=row_idx, column=col_idx, value=val)
            c.border = border
            c.alignment = Alignment(vertical='center')

    # 5. 返回文件流
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    ts = dt.now().strftime('%Y%m%d_%H%M%S')
    from urllib.parse import quote
    filename_ascii = f'project_info_{ts}.xlsx'
    filename_zh = quote(f'项目信息_{ts}.xlsx', safe='')
    resp = make_response(output.getvalue())
    resp.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    resp.headers['Content-Disposition'] = f"attachment; filename={filename_ascii}; filename*=UTF-8''{filename_zh}"
    return resp
