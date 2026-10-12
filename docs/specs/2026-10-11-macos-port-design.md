# codex-pet macOS 版设计

日期:2026-10-11
状态:已确认(用户拍板:悬浮条形态 + 本地构建 arm64 发布)

## 背景

codex-pet 现为 Windows 任务栏余额条(Python 3.12 + PyQt6),显示 Codex/ChatGPT Plus
配额并支持 DeepSeek 余额自动切换。核心数据链路(codex app-server JSONL 客户端、
config.toml 提供方检测、DeepSeek 网络客户端、配置读写)跨平台;平台耦合集中在:

1. `taskbar_bar.py`:Win32 任务栏/托盘锚定、置顶强化、全屏检测(模块级
   `ctypes.WinDLL`,非 Windows import 即崩)
2. `detail_panel.py`:`GetAsyncKeyState` 全局鼠标轮询(点外自动收起)
3. `codex_client.py`:`_locate_codex` 只找 Windows 路径
4. 字体写死 Segoe UI

## 方案

共享基类 + 平台子类,零新增 Python 依赖(原生调用全部走 ctypes,与现有 Win32
代码风格一致)。备选被否方案:引入 pyobjc(多一个 MB 级依赖,风格不符);
重写 SwiftUI 独立应用(脱离现有代码库,双倍维护)。

### 模块结构

```
src/codex_pet/
├── bar.py           # 新:平台分发(darwin → macos_bar,win32 → taskbar_bar)
├── status_bar.py    # 新:共享胶囊条基类(文案/测量/绘制/拖拽/右键菜单/set_state)
├── taskbar_bar.py   # 改:继承基类,保留 Win32 逻辑,import 不再崩溃非 win32
├── macos_bar.py     # 新:macOS 悬浮条
├── detail_panel.py  # 改:_button_state 增加 macOS 分支
├── codex_client.py  # 改:_locate_codex 增加 macOS 分支
├── tray.py          # 改:字体按平台选择
└── __main__.py      # 改:从 bar 导入 TaskbarBar
```

### macOS 悬浮条行为(macos_bar.py)

- 外观与 Windows 版同款:深色圆角胶囊(24px 高)、状态圆点、分段着色文字;
  字体用系统默认(SF Pro)。
- 位置:锚定所在屏菜单栏下方右侧——右缘距屏边 12px,顶部贴 availableGeometry
  下沿 4px;复用 `~/.codex-pet/config.json` 的 `bar_offset` 支持拖拽微调。
- 跨桌面 Space:ctypes 调 ObjC runtime 给 NSWindow 设
  `collectionBehavior = CanJoinAllSpaces | FullScreenAuxiliary`,所有桌面可见;
  失败回退普通置顶 Tool 窗口。
- 全屏自动隐藏:每秒轮询 `CGWindowListCopyWindowInfo`(仅 on-screen、layer 0),
  存在覆盖整屏(含菜单栏区,≥97%)且非本进程的窗口 → 隐藏并发射 autoHidden
  (详情面板一并收起);退出全屏恢复。
- 置顶:WindowStaysOnTopHint;无需 Windows 的 250ms 重排循环。
- 交互:左键弹详情、拖拽调位、右键菜单(立即刷新/重置位置/退出)复用基类。

### 配套修改

- `detail_panel._button_state`:macOS 用 ctypes CoreGraphics
  `CGEventSourceButtonState(kCGEventSourceStateCombinedSessionState, 按钮)`,
  失败返回 0(仅退化为面板不自动收起,不崩)。
- `codex_client._locate_codex`:macOS 候选 `shutil.which("codex")` +
  `/opt/homebrew/bin`、`/usr/local/bin`、`~/.local/bin`、`~/.npm-global/bin`
  (.app 从 Finder 启动时 PATH 有限,显式路径必需)。
- 字体:Segoe UI 仅 win32;其余平台 QFont() 默认。

### 打包与发布

1. `scripts/make_icns.py`:Qt offscreen 画电池+⚡图标 → `iconutil` 生成
   `CodexPet.icns`。
2. PyInstaller `--windowed`(非 onefile)+ 自定义 Info.plist(`LSUIElement=1`,
   菜单栏应用无 Dock 图标)+ icns → `dist/CodexPet.app`(arm64,ad-hoc 签名)。
3. `ditto -c -k --keepParent` 打 zip → `CodexPet-macos-arm64.zip`。
4. 版本 1.2.1 → 1.3.0;README 补 macOS 章节;提交推送到 fork;
   `gh release create v1.3.0` 上传 zip,notes 含 Gatekeeper 提示
   (未公证,首次右键打开或 `xattr -cr`)。

### 测试

- test_smoke / test_render 改从 `codex_pet.bar` 导入,macOS offscreen 可跑。
- test_anchor.py(Windows 锚定)加平台跳过。
- 真机验收:锚定、跨 Space、全屏隐藏/恢复、面板弹出与点外收起、托盘。

### 错误处理

所有 ctypes/ObjC 调用 try/except 静默回退(与现有风格一致);ObjC 不可用 →
普通置顶 Tool 窗口行为;CGWindowList 失败 → 不触发自动隐藏。

### 风险

- ctypes 调 objc_msgSend 在 arm64 需显式 argtypes/restype(成熟做法,逐函数声明)。
- CGWindowList 全屏判定对"自动隐藏菜单栏 + 满窗窗口"存在误报可能,阈值兜底,
  误报后果仅为条临时隐藏,可接受。
- Gatekeeper:未公证 app 首次打开需右键 → 打开,release notes 写明。

## v1.4 修订(2026-10-12,真机反馈后)

悬浮胶囊条方案在真机上被否:太小、易误触隐藏(托盘左键=切换条显示)。
macOS 显示层重设计:

- **删除 macos_bar / bar,悬浮条方案整体下线**;macos_native 只保留
  `mouse_button_state`(详情面板点外收起)。
- 主显示改为**菜单栏状态项电池图标**(tray.py,剩余额度数字嵌在电池内,
  离线 Z / DeepSeek ¥),常驻不消失——对齐系统电池的使用习惯。
- 左键状态项 → 详情面板弹出在菜单栏下沿(锚点取状态项几何,失败回退
  鼠标位置);右键手动弹菜单(仍不挂原生菜单,规避 clickCount 断言崩溃,
  见 v1.3.0 修复)。
- `__main__` 平台化装配:Windows 路径行为不变;macOS 无 bar 分支。

修复记录:v1.3.0 期间发现并修复 (1) codex CLI npm 包缺原生二进制导致
始终离线(环境问题,重装修复);(2) 托盘原生菜单 → NSMenuTrackingSession
→ Qt 观察者 clickCount 断言 → SIGABRT(4 份同签名崩溃报告)。
