#!/bin/bash
# 汇码 · 一键安装（macOS）。Keep LF line endings.
# Usage: curl -fsSL <site>/docs/assets/downloads/huima-install.sh | bash -s -- claude,codex,workbuddy [NAME=value ...]
# Runs with the stock /bin/bash 3.2: no associative arrays or ${var,,}.
# Everything is a function and main runs on the last line, so a truncated download runs nothing.

HUIMA_NPM_REGISTRY='https://registry.npmmirror.com'
HUIMA_NPM_REGISTRY_FALLBACK='https://registry.npmjs.org'
HUIMA_NODE_MIRROR='https://registry.npmmirror.com/-/binary/node'
HUIMA_NODE_MIN='22'
HUIMA_NODE_LTS='24'
HUIMA_CLAUDE_PACKAGE='@anthropic-ai/claude-code'
HUIMA_CODEX_PACKAGE='@openai/codex'
HUIMA_CODEX_DMG_URL='https://persistent.oaistatic.com/codex-app-prod/Codex.dmg'
HUIMA_WORKBUDDY_SITE='https://www.workbuddy.cn/'

URL_PATTERN='^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~/-]*)?$'
PACKAGE_PATTERN='^(@[a-z0-9][a-z0-9._-]{0,100}/)?[a-z0-9][a-z0-9._-]{0,100}$'
HUIMA_HOME="$HOME/.huima"
NPM_PREFIX="$HUIMA_HOME/npm-global"
NODE_ROOT="$HUIMA_HOME/node"
WORK_DIR=''
NODE_DIR=''
NPM_READY=0
ARCH=''
MACOS=''
RESULT_NAMES=()
RESULT_STATES=()

if [ -t 1 ]; then C_STEP=$'\033[36m'; C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_ERR=$'\033[31m'; C_END=$'\033[0m'
else C_STEP=''; C_OK=''; C_WARN=''; C_ERR=''; C_END=''; fi
step() { printf '\n%s%s%s\n' "$C_STEP" "$1" "$C_END"; }
info() { printf '  %s\n' "$1"; }
ok() { printf '  %s%s%s\n' "$C_OK" "$1" "$C_END"; }
warn() { printf '  %s%s%s\n' "$C_WARN" "$1" "$C_END"; }
fail() { printf '  %s%s%s\n' "$C_ERR" "$1" "$C_END"; }
record() { RESULT_NAMES+=("$1"); RESULT_STATES+=("$2"); }

# NAME=value arguments from the manual page override the defaults when they pass the same checks as on Windows.
apply_setting() {
  local name="${1%%=*}" value="${1#*=}" pattern
  case "$name" in
    HUIMA_NPM_REGISTRY|HUIMA_NPM_REGISTRY_FALLBACK|HUIMA_NODE_MIRROR|HUIMA_CODEX_DMG_URL|HUIMA_WORKBUDDY_SITE) pattern="$URL_PATTERN" ;;
    HUIMA_CLAUDE_PACKAGE|HUIMA_CODEX_PACKAGE) pattern="$PACKAGE_PATTERN" ;;
    HUIMA_NODE_MIN|HUIMA_NODE_LTS) pattern='^[0-9]{2}$' ;;
    *) warn "忽略未知参数：$name"; return ;;
  esac
  if [[ "$value" =~ $pattern ]]; then eval "$name=\$value"; else warn "参数 $name 格式不正确，使用默认值。"; fi
}

version_ge() {
  # version_ge 13.5 13.4.1 -> false. Compares up to three numeric parts.
  local IFS=.
  local -a a=($1) b=($2)
  local i
  for i in 0 1 2; do
    local x="${a[$i]:-0}" y="${b[$i]:-0}"
    if [ "$x" -gt "$y" ]; then return 0; fi
    if [ "$x" -lt "$y" ]; then return 1; fi
  done
  return 0
}

ask() {
  # curl | bash feeds the script itself on stdin, so answers come from the terminal.
  local prompt="$1" answer=''
  if [ -r /dev/tty ] && [ -z "${HUIMA_ASSUME_YES:-}" ]; then
    printf '%s' "$prompt" > /dev/tty
    IFS= read -r answer < /dev/tty || answer=''
  fi
  printf '%s' "$answer"
}

download() {
  # download URL FILE [MAX_SECONDS]; tries the system proxy first, then a direct connection.
  local url="$1" file="$2" max="${3:-600}"
  info "下载：$url"
  if curl -fL --retry 2 --connect-timeout 20 --max-time "$max" -sS -o "$file" "$url"; then return 0; fi
  warn '常规下载失败，尝试直连（不修改现有代理设置）。'
  curl -fL --retry 2 --connect-timeout 20 --max-time "$max" -sS --noproxy '*' -o "$file" "$url"
}

node_ok() {
  local node="$1" major arch
  [ -x "$node" ] || return 1
  major=$("$node" -p 'process.versions.node.split(".")[0]' 2>/dev/null) || return 1
  arch=$("$node" -p 'process.arch' 2>/dev/null) || return 1
  [ -n "$major" ] && [ "$major" -ge "$HUIMA_NODE_MIN" ] && { [ "$arch" = arm64 ] || [ "$arch" = x64 ]; }
}

find_node_release() {
  # Prints "BASE VERSION SHA256". Reads index.json: the mirror's latest-v24.x alias can lag far behind.
  local base="$1" index sums version file line
  index="$WORK_DIR/node-index.json"
  download "$base/index.json" "$index" 60 || return 1
  version=$(tr '{' '\n' < "$index" | grep "\"version\":\"v$HUIMA_NODE_LTS\." | grep "\"osx-$ARCH-tar\"" | grep -v '"lts":false' \
    | head -1 | sed -E 's/.*"version":"(v[0-9.]+)".*/\1/')
  [ -n "$version" ] || return 1
  sums="$WORK_DIR/SHASUMS256.txt"
  download "$base/$version/SHASUMS256.txt" "$sums" 60 || return 1
  file="node-$version-darwin-$ARCH.tar.gz"
  line=$(grep -E "^[0-9a-f]{64}  $file\$" "$sums" | head -1)
  [ -n "$line" ] || return 1
  printf '%s %s %s\n' "$base" "$version" "${line%% *}"
}

ensure_node() {
  step '准备 Node.js 和 npm'
  local node release base version hash file
  node=$(command -v node 2>/dev/null)
  if [ -n "$node" ] && node_ok "$node" && [ -x "$(dirname "$node")/npm" ]; then
    NODE_DIR=$(dirname "$node")
    ok "已安装 Node.js $("$node" --version)，满足要求，跳过下载。"
    return 0
  fi
  if node_ok "$NODE_ROOT/current/bin/node"; then
    NODE_DIR="$NODE_ROOT/current/bin"
    ok "已安装 Node.js $("$NODE_DIR/node" --version)（汇码安装目录），跳过下载。"
    return 0
  fi
  if ! version_ge "$MACOS" 13.5; then
    fail "Node.js $HUIMA_NODE_LTS 需要 macOS 13.5 或更新版本，这台 Mac 是 $MACOS。请先在“系统设置 → 通用 → 软件更新”里升级系统。"
    return 1
  fi
  info "需要安装 Node.js $HUIMA_NODE_LTS LTS（装在你的用户目录里，不需要输入开机密码）。"
  release=''
  for base in "$HUIMA_NODE_MIRROR" 'https://nodejs.org/dist'; do
    release=$(find_node_release "$base") && break
    warn "当前下载源未找到可用的 Node.js：$base"
    release=''
  done
  [ -n "$release" ] || { fail 'Node.js 下载失败。请检查网络或代理后重新运行。'; return 1; }
  set -- $release
  base="$1"; version="$2"; hash="$3"
  file="node-$version-darwin-$ARCH.tar.gz"
  download "$base/$version/$file" "$WORK_DIR/$file" || { fail 'Node.js 下载失败。'; return 1; }
  if [ "$(shasum -a 256 "$WORK_DIR/$file" | cut -d ' ' -f 1)" != "$hash" ]; then
    fail 'Node.js 下载文件校验失败，请重新运行。'
    return 1
  fi
  ok "文件校验通过：$version / $ARCH"
  mkdir -p "$NODE_ROOT"
  tar -xzf "$WORK_DIR/$file" -C "$NODE_ROOT" || { fail 'Node.js 解压失败。'; return 1; }
  ln -sfn "$NODE_ROOT/node-$version-darwin-$ARCH" "$NODE_ROOT/current"
  NODE_DIR="$NODE_ROOT/current/bin"
  node_ok "$NODE_DIR/node" || { fail 'Node.js 安装后无法运行。'; return 1; }
  ok "Node.js $version 已就绪。"
}

configure_npm() {
  step '配置国内下载源和命令路径'
  export PATH="$NPM_PREFIX/bin:$NODE_DIR:$PATH"
  mkdir -p "$NPM_PREFIX"
  "$NODE_DIR/npm" config set registry "$HUIMA_NPM_REGISTRY" --location=user >/dev/null 2>&1 \
    || warn '未能写入 npm 下载源设置，安装时会直接指定下载源。'
  info "安装位置：$NPM_PREFIX"
  info "下载源：$HUIMA_NPM_REGISTRY；失败时自动尝试 npm 官方源。"
}

initialize_npm() {
  [ "$NPM_READY" = 1 ] && return 0
  ensure_node || return 1
  configure_npm
  NPM_READY=1
}

tool_version() {
  local file="$1"
  [ -x "$file" ] || return 1
  "$file" --version 2>/dev/null | grep -E '[0-9]+\.[0-9]+\.[0-9]+' | tail -1
}

install_tool() {
  local command="$1" package="$2" title="$3" existing version registry noproxy hosts
  step "安装 $title"
  existing=$(command -v "$command" 2>/dev/null)
  [ -n "$existing" ] || existing="$NPM_PREFIX/bin/$command"
  version=$(tool_version "$existing")
  if [ -n "$version" ]; then ok "已安装：$version，跳过重复安装。"; return 0; fi
  initialize_npm || return 1
  hosts="$(printf '%s' "$HUIMA_NPM_REGISTRY" | sed -E 's#https://([^/:]+).*#\1#'),$(printf '%s' "$HUIMA_NPM_REGISTRY_FALLBACK" | sed -E 's#https://([^/:]+).*#\1#')"
  for registry in "$HUIMA_NPM_REGISTRY" "$HUIMA_NPM_REGISTRY_FALLBACK"; do
    for noproxy in '' "--noproxy=$hosts"; do
      info "正在安装，请耐心等待。下载源：$registry"
      [ -n "$noproxy" ] && info '本次尝试直连，不修改原有代理设置。'
      # --allow-scripts: npm 11 blocks install scripts unless allowed; Claude Code's postinstall places its binary.
      if "$NODE_DIR/npm" install --global "$package@latest" --prefix "$NPM_PREFIX" --registry "$registry" \
          --include=optional --ignore-scripts=false --no-audit --no-fund --fetch-retries=1 --fetch-timeout=120000 \
          "--allow-scripts=$package" $noproxy; then
        version=$(tool_version "$NPM_PREFIX/bin/$command")
        if [ -n "$version" ]; then ok "安装成功：$version"; return 0; fi
        warn "$title 安装命令已结束，但版本检查未通过。"
      else
        warn '此次安装未成功，换一个方式重试。'
      fi
    done
  done
  fail "$title 未安装成功，继续安装其他软件。"
  return 1
}

install_claude() {
  if install_tool claude "$HUIMA_CLAUDE_PACKAGE" 'Claude Code'; then record 'Claude Code' ok; else record 'Claude Code' fail; fi
}

install_codex_cli() {
  if install_tool codex "$HUIMA_CODEX_PACKAGE" 'Codex 命令行版'; then record 'Codex 命令行版' ok; else record 'Codex 命令行版' fail; fi
}

find_openai_app() {
  local app
  for app in /Applications/ChatGPT.app /Applications/Codex.app "$HOME/Applications/ChatGPT.app" "$HOME/Applications/Codex.app"; do
    [ -d "$app" ] && { printf '%s' "$app"; return 0; }
  done
  return 1
}

install_codex_desktop() {
  step '安装 Codex 桌面版（OpenAI 官方安装包）'
  local existing dmg mount app minimum target signer
  if [ "$ARCH" != arm64 ]; then
    warn 'Codex 桌面版只支持 Apple 芯片（M1 及更新）的 Mac，这台是 Intel 芯片。'
    warn '改装 Codex 命令行版，配置方法相同，在终端里使用。'
    record 'Codex 桌面版' skip
    install_codex_cli
    return
  fi
  if existing=$(find_openai_app); then
    ok "已安装：$existing，跳过下载。它会自动更新；打开后如果没有 Codex 功能，请在应用菜单里检查更新。"
    record 'Codex 桌面版' ok
    return
  fi
  mkdir -p "$HOME/Library/Caches/HuimaSetup"
  dmg="$HOME/Library/Caches/HuimaSetup/Codex.dmg"
  info '安装包约 750 MB，国内直连一般 5～15 分钟。中途断开时重新运行同一行命令，会接着下载。'
  info "下载：$HUIMA_CODEX_DMG_URL"
  if ! curl -fL -C - --retry 3 --connect-timeout 20 --progress-bar -o "$dmg" "$HUIMA_CODEX_DMG_URL"; then
    if ! curl -fL -C - --retry 3 --connect-timeout 20 --progress-bar --noproxy '*' -o "$dmg" "$HUIMA_CODEX_DMG_URL"; then
      fail 'Codex 桌面版下载失败，改装命令行版。'
      record 'Codex 桌面版' fail
      install_codex_cli
      return
    fi
  fi
  mount="$WORK_DIR/codex-dmg"
  mkdir -p "$mount"
  if ! hdiutil attach -nobrowse -readonly -noautoopen -quiet -mountpoint "$mount" "$dmg"; then
    rm -f "$dmg"
    fail '安装包无法打开（可能下载不完整），已删除。请重新运行；先改装命令行版。'
    record 'Codex 桌面版' fail
    install_codex_cli
    return
  fi
  app=$(find "$mount" -maxdepth 1 -name '*.app' -type d | head -1)
  signer=$(codesign -dvv "$app" 2>&1 | grep '^Authority=Developer ID Application:' | head -1)
  if [ -z "$app" ] || ! codesign --verify --deep --strict "$app" 2>/dev/null || [[ "$signer" != *OpenAI* ]]; then
    hdiutil detach "$mount" -quiet
    rm -f "$dmg"
    fail "安装包签名校验未通过（${signer:-无签名}），已删除，没有安装。先改装命令行版，并请联系客服。"
    record 'Codex 桌面版' fail
    install_codex_cli
    return
  fi
  ok "签名校验通过：${signer#Authority=}"
  minimum=$(defaults read "$app/Contents/Info.plist" LSMinimumSystemVersion 2>/dev/null)
  if [ -n "$minimum" ] && ! version_ge "$MACOS" "$minimum"; then
    hdiutil detach "$mount" -quiet
    warn "Codex 桌面版需要 macOS $minimum 或更新版本，这台 Mac 是 $MACOS。先改装命令行版。"
    record 'Codex 桌面版' skip
    install_codex_cli
    return
  fi
  target=/Applications
  [ -w "$target" ] || { target="$HOME/Applications"; mkdir -p "$target"; }
  if ditto "$app" "$target/$(basename "$app")"; then
    hdiutil detach "$mount" -quiet
    rm -f "$dmg"
    ok "Codex 桌面版已安装到 $target/$(basename "$app")。在启动台或“应用程序”里打开它。"
    record 'Codex 桌面版' ok
  else
    hdiutil detach "$mount" -quiet
    fail "复制到 $target 失败。先改装命令行版。"
    record 'Codex 桌面版' fail
    install_codex_cli
  fi
}

install_workbuddy() {
  step '安装 WorkBuddy（腾讯官方安装包）'
  if [ -d /Applications/WorkBuddy.app ] || [ -d "$HOME/Applications/WorkBuddy.app" ]; then
    ok '已安装 WorkBuddy，跳过。'
    record 'WorkBuddy' ok
    return
  fi
  [ -n "${CI:-}" ] || open "$HUIMA_WORKBUDDY_SITE" 2>/dev/null || true
  info "已打开 WorkBuddy 官网：$HUIMA_WORKBUDDY_SITE"
  info '点击“下载”，按芯片选择 Mac 版（Apple 芯片选 ARM64），双击下载好的 dmg，把 WorkBuddy 拖进“应用程序”。'
  record 'WorkBuddy' manual
}

persist_path() {
  # Terminal opens login shells, which read ~/.zprofile (zsh, the default) or ~/.bash_profile.
  local line block file
  line="export PATH=\"\$HOME/.huima/npm-global/bin:\$HOME/.huima/node/current/bin:\$PATH\""
  block="# >>> huima >>>"$'\n'"$line"$'\n'"# <<< huima <<<"
  for file in "$HOME/.zprofile" "$HOME/.bash_profile"; do
    [ "$file" = "$HOME/.bash_profile" ] && [ ! -f "$file" ] && continue
    if [ -f "$file" ] && grep -q '^# >>> huima >>>$' "$file"; then continue; fi
    printf '\n%s\n' "$block" >> "$file" && info "已把命令路径写入 $file"
  done
}

choose_tools() {
  local raw="$1" answer tools='' item
  if [ -z "$raw" ]; then
    printf '\n请选择要安装的软件：\n' > /dev/tty 2>/dev/null || true
    printf '  1  Claude Code   （在终端里使用的 AI 编程助手）\n  2  Codex 桌面版  （OpenAI 的 AI 编程助手，有窗口界面）\n  3  WorkBuddy     （腾讯的 AI 办公助手，有窗口界面）\n' > /dev/tty 2>/dev/null || true
    answer=$(ask '输入编号后回车，例如 13 表示安装 1 和 3；直接回车表示全部安装：')
    [ -n "$answer" ] || answer=123
    case "$answer" in *1*) raw="$raw,claude" ;; esac
    case "$answer" in *2*) raw="$raw,codex" ;; esac
    case "$answer" in *3*) raw="$raw,workbuddy" ;; esac
  fi
  for item in $(printf '%s' "$raw" | tr ',' ' '); do
    case "$item" in
      claude|codex|workbuddy) case ",$tools," in *",$item,"*) ;; *) tools="$tools,$item" ;; esac ;;
    esac
  done
  printf '%s' "${tools#,}"
}

main() {
  local raw='' arg tools tool code=0 all_ok=1 codex_cli_ok=0 i
  for arg in "$@"; do
    case "$arg" in *=*) apply_setting "$arg" ;; *) raw="$arg" ;; esac
  done
  echo '========================================================'
  echo '                汇码 · 一键安装（Mac）'
  echo '========================================================'
  if [ "$(uname -s)" != Darwin ]; then fail '这个脚本只能在 Mac 上运行。Windows 请回到手册下载 .cmd 安装脚本。'; return 1; fi
  MACOS=$(sw_vers -productVersion)
  if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = 1 ]; then ARCH=arm64; else ARCH=x64; fi
  tools=$(choose_tools "$raw")
  if [ -z "$tools" ]; then fail '没有选择任何软件，请重新运行并输入编号。'; return 1; fi
  WORK_DIR="$HOME/Library/Logs/HuimaSetup/$(date +%Y%m%d-%H%M%S)-$$"
  mkdir -p "$WORK_DIR"
  # Keep a log the customer can send to support; the script never prints keys.
  exec > >(tee -a "$WORK_DIR/安装日志.txt") 2>&1
  cd "$WORK_DIR" || return 1
  info "系统：macOS $MACOS（$([ "$ARCH" = arm64 ] && echo 'Apple 芯片' || echo 'Intel 芯片')）"
  info '全程使用国内可访问的下载源，不需要科学上网。请保持联网，不要关闭这个窗口。'
  info '已经装好的软件会自动跳过。不需要输入开机密码。'
  for tool in $(printf '%s' "$tools" | tr ',' ' '); do
    case "$tool" in
      claude) install_claude ;;
      codex) install_codex_desktop ;;
      workbuddy) install_workbuddy ;;
    esac
  done
  [ "$NPM_READY" = 1 ] && persist_path
  step '安装结果'
  for i in "${!RESULT_NAMES[@]}"; do
    [ "${RESULT_NAMES[$i]}" = 'Codex 命令行版' ] && [ "${RESULT_STATES[$i]}" = ok ] && codex_cli_ok=1
  done
  for i in "${!RESULT_NAMES[@]}"; do
    case "${RESULT_STATES[$i]}" in
      ok) ok "[ 完成 ] ${RESULT_NAMES[$i]}" ;;
      manual) warn "[需手动] ${RESULT_NAMES[$i]}：请在打开的官网下载安装" ;;
      skip) warn "[ 跳过 ] ${RESULT_NAMES[$i]}：已改装命令行版" ;;
      *)
        fail "[ 失败 ] ${RESULT_NAMES[$i]}"
        # A failed desktop install is fine when the CLI fallback worked.
        if ! { [ "${RESULT_NAMES[$i]}" = 'Codex 桌面版' ] && [ "$codex_cli_ok" = 1 ]; }; then all_ok=0; fi
        ;;
    esac
  done
  echo
  printf '%s下一步：回到使用手册，完成“4.2 一键配置”。%s\n' "$C_STEP" "$C_END"
  [ "$NPM_READY" = 1 ] && warn '新装的 claude、codex 命令要在新开的终端窗口里才能用：先关掉这个窗口，再打开一个新的。'
  if [ "$all_ok" != 1 ]; then
    warn '有软件没装好：检查网络后重新运行同一行命令即可，已装好的会自动跳过。'
    code=1
  fi
  printf '\n日志文件夹：%s\n' "$WORK_DIR"
  return "$code"
}

main "$@"
