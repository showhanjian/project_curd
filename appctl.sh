#!/bin/bash
# appctl.sh — Flask 项目管理系统启停脚本
# 用法: ./appctl.sh start | stop | restart | status

APP_NAME="project_crud"
APP_DIR="/root/project_crud"
PORT=35821
HOST="0.0.0.0"

PID_FILE="$APP_DIR/.app.pid"
LOG_FILE="$APP_DIR/nohup.out"

# 通过端口找 PID（最可靠）
find_pid() {
    ss -tlnp 2>/dev/null | grep ":$PORT " | grep -oP 'pid=\K[0-9]+'
}

# 通过进程名找 PID（备用）
find_pid_by_name() {
    ps aux | grep -E "python.*Flask|python.*app\.py" | grep -v grep | awk '{print $2}'
}

start() {
    echo "启动 $APP_NAME ..."
    local pid
    pid=$(find_pid)
    if [ -n "$pid" ]; then
        echo "端口 $PORT 已被占用，PID: $pid"
        return 1
    fi

    cd "$APP_DIR"
    nohup python -c "
from app import app
app.run(host='$HOST', port=$PORT, debug=False, use_reloader=False)
" >> "$LOG_FILE" 2>&1 &

    sleep 3
    pid=$(find_pid)
    if [ -n "$pid" ]; then
        echo "$pid" > "$PID_FILE"
        echo "启动成功，PID: $pid"
    else
        echo "启动失败，请检查 $LOG_FILE"
        rm -f "$PID_FILE"
    fi
}

stop() {
    echo "停止 $APP_NAME ..."

    # 方法1：通过 PID_FILE
    local pid
    pid=$(cat "$PID_FILE" 2>/dev/null)

    # 方法2：通过端口
    if [ -z "$pid" ]; then
        pid=$(find_pid)
    fi

    # 方法3：通过进程名
    if [ -z "$pid" ]; then
        pid=$(find_pid_by_name | head -1)
    fi

    if [ -z "$pid" ]; then
        echo "进程未运行"
        rm -f "$PID_FILE"
        return
    fi

    # 获取父进程（Flask reloader 父子结构）
    local ppid=""
    if [ -d "/proc/$pid" ]; then
        ppid=$(cat /proc/$pid/status 2>/dev/null | grep "^PPid:" | awk '{print $2}')
    fi

    # 杀子进程
    kill -9 $pid 2>/dev/null
    # 杀父进程（reloader）
    if [ -n "$ppid" ] && [ "$ppid" != "1" ]; then
        kill -9 $ppid 2>/dev/null
    fi

    sleep 2

    # 确认已停止
    local remaining
    remaining=$(find_pid)
    if [ -n "$remaining" ]; then
        echo "仍有残留进程: $remaining，再次尝试..."
        kill -9 $remaining 2>/dev/null
        sleep 1
    fi

    remaining=$(find_pid_by_name | head -1)
    if [ -n "$remaining" ]; then
        echo "仍有残留进程: $remaining，强制杀掉..."
        kill -9 $remaining 2>/dev/null
    fi

    rm -f "$PID_FILE"
    echo "已停止"
}

status() {
    local pid
    pid=$(find_pid)
    if [ -n "$pid" ]; then
        echo "运行中，PID: $pid"
    else
        echo "未运行"
    fi
}

restart() {
    stop
    start
}

case "$1" in
    start)   start ;;
    stop)    stop ;;
    restart) restart ;;
    status)  status ;;
    *)
        echo "用法: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
