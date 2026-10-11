# Codex Pet ⚡

一个实时显示 **Codex / ChatGPT Plus** 配额余额的 Windows 任务栏小工具,支持 **DeepSeek API 余额**自动切换。

在任务栏托盘左侧显示一行紧凑文字,状态圆点随余额变色,不占用桌面空间。
全屏看视频/玩游戏时自动隐藏(与任务栏自身行为一致),退出全屏自动恢复。

**双模式自动切换**(每 60 秒检测 `~/.codex/config.toml`):

| Codex 当前使用 | 余额条显示 |
| --- | --- |
| ChatGPT(默认) | `● Codex 29% · 2h15m`(5 小时窗口剩余配额) |
| DeepSeek | `● DeepSeek ¥354.27`(官方 API 余额,总/赠/充在详情面板) |

![余额条](shots/bar_mid.png) ![DeepSeek 模式](shots/bar_ds.png)

## 功能

- **实时余额**:通过官方 `codex app-server` 协议获取,自动跟随推送更新 + 5 分钟兜底轮询;DeepSeek 余额走官方 `/user/balance` 接口,2 分钟轮询
- **自动切换**:检测到 `config.toml` 的 active provider 是 DeepSeek(base_url/name 含 deepseek)即切换显示,密钥支持 `experimental_bearer_token` 字段或 `env_key` 环境变量,切回 ChatGPT 自动恢复
- **紧凑直观**:状态圆点 + 余额/百分比 + 重置倒计时;DeepSeek 余额 <¥20 橙色、<¥5 红色预警
- **详情面板**:点击弹出——DeepSeek 总/赠/充余额与 ChatGPT 双窗口进度条;点击面板以外任何位置或按 Esc 自动收起
- **全屏自动隐藏**:检测到真正的全屏应用(全屏视频/游戏/幻灯片)时隐藏,最大化窗口不受影响;退出全屏恢复
- **置顶强化**:每秒检测是否被其他置顶窗口(如任务栏)盖住,被盖自动重排回顶端;任务栏挪动/分辨率变化时跟随锚定
- **系统托盘**:模式化图标(配额电量 / DeepSeek ¥)+ 悬停提示
- **零凭证接触**:ChatGPT 鉴权完全由 Codex CLI 自己管理;DeepSeek 密钥只用于调余额接口,不写日志
- **离线兜底**:codex 未安装/未登录时显示离线状态,进程崩溃自动退避重启;DeepSeek 密钥无效时明确提示

## 环境要求

- Windows 10/11
- 已安装并登录 [Codex CLI](https://developers.openai.com/codex)(即 `codex` 命令可用,ChatGPT Plus 订阅)
- [uv](https://docs.astral.sh/uv/)(Python 环境管理)

## 运行

**方式一**:从 [Releases](../../releases) 下载 `CodexPet.exe`,双击即可,无需 Python 环境。

**方式二**:源码运行

```bash
cd codex-pet
uv run codex-pet
```

首次运行会自动解析 `codex` 可执行文件位置并后台拉起 `codex app-server`。

## 交互

| 操作 | 效果 |
| --- | --- |
| 左键点击余额条 | 弹出/收起详情面板 |
| 点击面板以外任何位置 / Esc | 收起详情面板 |
| 按住拖拽余额条 | 微调位置(自动记忆;任务栏挪动时跟随锚定) |
| 右键余额条 | 菜单:立即刷新 / 重置位置 / 退出 |
| 托盘图标 | 单击显示/隐藏余额条;菜单同上 |

## 配置

`~/.codex-pet/config.json`(自动生成):

```jsonc
{
  "bar_offset": [0, 0]  // 余额条相对任务栏托盘左侧锚点的偏移
}
```

## 打包成 exe(可选)

```bash
uv run --with pyinstaller pyinstaller --onefile --windowed \
    --name CodexPet --paths src launcher.py --noconfirm
```

产物在 `dist/CodexPet.exe`(约 36MB),双击即可运行,无需 Python 环境。

## 开发自检脚本

```bash
uv run python test_smoke.py    # 端到端冒烟测试(离屏,验证真实数据链路,含 DeepSeek)
uv run python test_render.py   # 渲染余额条各状态截图到 shots/
```

## 项目结构

```
src/codex_pet/
├── __main__.py      # 入口:装配各组件、提供方自动切换
├── codex_client.py  # codex app-server JSONL 客户端(QProcess + JSON-RPC 2.0)
├── deepseek_client.py # DeepSeek 官方 /user/balance 客户端(QNetworkAccessManager)
├── provider.py      # 解析 ~/.codex/config.toml 检测当前提供方
├── taskbar_bar.py   # 任务栏余额条(Win32 任务栏/托盘探测 + 全屏检测 + 置顶强化)
├── detail_panel.py  # 点击弹出的详情浮层(DeepSeek 余额 + 双窗口配额)
├── tray.py          # 系统托盘
├── colors.py        # 共享配色
└── config.py        # 配置读写(~/.codex-pet/config.json)
```

## 数据来源说明

配额数据来自 Codex CLI 文档化的 app-server JSONL 协议
(`initialize` → `account/rateLimits/read`,并订阅 `account/rateLimits/updated` 推送),
返回 `primary`(5 小时窗口)与 `secondary`(周窗口)的 `usedPercent` / `resetsAt` 等。

注:`CODEX_PET_DEBUG=1` 环境变量可让余额条渲染成品红实心块,用于诊断定位问题。
另:半透明(layered)窗口在部分环境下不会被 GDI 截屏捕获,截图验证时需注意。

## License

[MIT](LICENSE)
