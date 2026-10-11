# Codex Pet ⚡

一个实时显示 **Codex / ChatGPT Plus** 配额余额的 Windows 任务栏小工具。

在任务栏托盘左侧显示一行紧凑文字,如 `● Codex 29% · 2h15m`:
状态圆点随剩余量变色(绿 → 橙 → 红),倒计时实时跳动,不占用桌面空间。
全屏看视频/玩游戏时自动隐藏(与任务栏自身行为一致),退出全屏自动恢复。

![余额条](shots/bar_mid.png)

## 功能

- **实时余额**:通过官方 `codex app-server` 协议获取,自动跟随推送更新 + 5 分钟兜底轮询
- **紧凑直观**:状态圆点 + 剩余百分比 + 重置倒计时,一眼可读
- **详情面板**:点击弹出,显示套餐类型、5 小时/周双窗口进度条与重置倒计时;点击面板以外任何位置或按 Esc 自动收起
- **全屏自动隐藏**:检测到真正的全屏应用(全屏视频/游戏/幻灯片)时隐藏,最大化窗口不受影响;退出全屏恢复
- **置顶强化**:周期性重申置顶层级,避免被任务栏或其他窗口压住;任务栏挪动/分辨率变化时自动跟随锚定
- **系统托盘**:迷你电量图标 + 悬停提示,可隐藏/显示余额条
- **零凭证接触**:不读取 `~/.codex/auth.json`,鉴权完全由 Codex CLI 自己管理
- **离线兜底**:codex 未安装/未登录时显示离线状态,进程崩溃自动退避重启

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
uv run python test_smoke.py    # 端到端冒烟测试(离屏,验证真实数据链路)
uv run python test_render.py   # 渲染余额条各状态截图到 shots/
```

## 项目结构

```
src/codex_pet/
├── __main__.py      # 入口:装配各组件
├── codex_client.py  # codex app-server JSONL 客户端(QProcess + JSON-RPC 2.0)
├── taskbar_bar.py   # 任务栏余额条(Win32 任务栏/托盘探测 + 全屏检测 + 置顶强化)
├── detail_panel.py  # 点击弹出的配额详情浮层(点击外部自动收起)
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
