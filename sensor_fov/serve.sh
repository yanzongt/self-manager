#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MODE=serve
HOST=127.0.0.1
PORT=8080
OPEN=yes
BUILD=yes
usage() {
  cat <<'HELP'
用法: ./serve.sh [选项]
默认安装缺失依赖、检查类型、构建静态网页、启动 HTTP 服务并尝试打开浏览器。
  --host ADDRESS  监听地址，默认 127.0.0.1；局域网使用 0.0.0.0
  --port PORT     端口，默认 8080；占用时直接报错
  --no-open       不打开浏览器
  --no-build      直接服务已有 web/dist，无需 npm 或网络
  --build-only    只构建 web/dist，不启动服务
  --dev           Vite 开发模式，支持热更新
  -h, --help      显示帮助
Ctrl+C 停止服务；网页参数在浏览器本地保存，可导出/导入 JSON。
HELP
}
while (($#)); do
  case "$1" in
    --host|--port)
      if (($# < 2)) || [[ -z "$2" || "$2" == --* ]]; then echo "$1 缺少参数" >&2; exit 2; fi
      if [[ "$1" == --host ]]; then HOST="$2"; else PORT="$2"; fi
      shift 2 ;;
    --no-open) OPEN=no; shift ;;
    --no-build) BUILD=no; shift ;;
    --build-only) MODE=build; shift ;;
    --dev) MODE=dev; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知选项: $1" >&2; usage >&2; exit 2 ;;
  esac
done
if [[ ! "$PORT" =~ ^[0-9]{1,5}$ ]] || ((10#$PORT < 1 || 10#$PORT > 65535)); then echo '端口必须为 1 ～ 65535 的整数' >&2; exit 2; fi
PORT=$((10#$PORT))
if [[ "$BUILD" == no && "$MODE" != serve ]]; then echo '--no-build 只能用于静态服务模式' >&2; exit 2; fi
command -v node >/dev/null || { echo '需要 Node.js >= 22.12，请先安装 Node.js。' >&2; exit 1; }
node -e 'const [major, minor] = process.versions.node.split(".").map(Number); if (major < 22 || (major === 22 && minor < 12)) { console.error("需要 Node.js >= 22.12"); process.exit(1) }'
cd -- "$SCRIPT_DIR/web"
if [[ "$BUILD" == yes ]]; then
  command -v npm >/dev/null || { echo '构建需要 npm。' >&2; exit 1; }
  if [[ ! -d node_modules || ! -f node_modules/.package-lock.json || package-lock.json -nt node_modules/.package-lock.json || package.json -nt node_modules/.package-lock.json ]]; then
    npm ci --no-audit --no-fund
  fi
  if [[ "$MODE" == dev ]]; then
    DEV_ARGS=(--host "$HOST" --port "$PORT" --strictPort)
    if [[ "$OPEN" == yes ]]; then DEV_ARGS+=(--open); fi
    exec npm run dev -- "${DEV_ARGS[@]}"
  fi
  npm run build
fi
if [[ "$MODE" == build ]]; then echo "静态网页已生成: $SCRIPT_DIR/web/dist"; exit 0; fi
exec node server.mjs "$HOST" "$PORT" "$OPEN"
