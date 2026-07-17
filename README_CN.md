# screen-vision

截屏任意桌面窗口，把按钮 + 文本读成像素级精确、可点击的 JSON, 无障碍树优先，视觉作兜底。

[![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-orange?style=flat)](https://docs.anthropic.com/en/docs/claude-code)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Accessibility-first](https://img.shields.io/badge/Reads-UIA%20%2B%20OCR-green?style=flat)](skills/screen-vision/reference/backends.md)
[![Read-only default](https://img.shields.io/badge/Click-opt--in%20%2F%20dry--run-green?style=flat)](skills/screen-vision/reference/schema.md)
[![Languages](https://img.shields.io/badge/Languages-EN%20%2F%20CN-blue?style=flat)](#语言)
[![Roadmap](https://img.shields.io/badge/Roadmap-v0.1.1-purple?style=flat)](ROADMAP.md)

[English](README.md) | [中文版](README_CN.md)

---

## ⭐ 先读这里, 设计理念

大多数"让 agent 看屏幕"的工具，从一张截图出发去问视觉模型"按钮在哪"。这是反的。操作系统本身已经暴露了**结构化的无障碍树**（UI Automation）：每个控件的名称、类型、状态、精确矩形都是**事实**,不靠模型、不靠猜、不受缩放与抗锯齿干扰。所以 screen-vision 只立一条原则：

> **先读无障碍树；只在它读不到的地方用视觉（OCR / 图标模型）兜底；绝不点击一个你无法验证的坐标。**

由此直接派生三条决策，也是它在像素匹配类工具会碎的地方依然可靠的原因：

1. **UIA 是真值，视觉是兜底。** 结构化元素带 confidence 1.0 和可直接触发的 `Invoke` pattern,**完全不靠坐标**即可点击。OCR 只在树缺文字处跑，与 UIA 重叠的 OCR 框被丢弃（UIA 优先）。这正是微软 UFO² 的混合检测路线。
2. **DPI 感知先于一切。** 屏幕工具点偏的头号原因就是进程非 DPI-aware：Windows 会把截图虚拟化拉伸、UIA 矩形漂移。脚本在 `import` 时即设 Per-Monitor-V2，测试也证明了这点（2560×1600 @150% 屏必须截出 2560×1600 的 PNG）。
3. **默认只读；点击是显式的、先 dry-run 的 opt-in。** 看屏幕安全，动屏幕不安全。登录 / 付款 / 验证码留给人工。

📜 **[完整设计理念 → PHILOSOPHY.md](PHILOSOPHY.md)**（每条原则都给出"打补丁 vs 改根因"的对照与它产出的真实决策）。

---

## 它是什么（不是什么）

它是一个 **CLI 脚本 skill**（不是 MCP server,截屏→解析→返回是无状态一次性能力，无需常驻 socket/token 开销），给 agent 三个动词：

- **`probe.py`**, 这台机器到底能干什么（DPI、显示器、装了哪些后端）？
- **`capture.py`**, 截图 + 结构化元素列表，坐标全为**物理像素**（`screen.png` + Set-of-Mark `annotated.png` + `elements.json`）。
- **`click.py`**, 可选、默认 dry-run 的点击，按 `id` 定位（优先 UIA `Invoke`，物理点击仅作兜底）。

**适用于** 桌面 / 原生 / Win32 / WinUI / Electron / 游戏 / 远程桌面窗口,一切**浏览器之外**的界面。

**不适用于** 网页,网页有实时 DOM，请走 **Playwright**。也不是图像生成/编辑工具（那是 `pixel-art` / 图像工具）。

它**仅靠标准库就能跑**（纯 ctypes 截屏 + 标准库 PNG 写出 + ctypes 点击），装上 `uiautomation`（元素）、`winocr`/`rapidocr`（OCR）、`Pillow`（标注）后更强。

## 安装

```
/plugin install github:DaizeDong/screen-vision
```

或手动克隆:

```bash
git clone https://github.com/DaizeDong/screen-vision.git ~/.claude/plugins/screen-vision
```

推荐后端（可选,缺了也能降级运行）:

```bash
pip install uiautomation mss pillow            # 元素 + 快速截图 + 标注
pip install winocr                             # OCR(Windows 原生)，或:
pip install rapidocr-onnxruntime               # OCR(跨平台)
```

（维护者部署：源在 `CodesSelf/screen-vision`，通过 PowerShell junction 把 `skills/screen-vision` 挂到 `~/.claude/skills/screen-vision`。）

## 快速开始

> "用 screen-vision 读屏幕上的按钮，然后点 Save。"

```bash
python skills/screen-vision/scripts/probe.py
python skills/screen-vision/scripts/capture.py --target 'window:Calculator' --clickable-only
python skills/screen-vision/scripts/click.py --elements-json <path> --id 30            # dry-run
python skills/screen-vision/scripts/click.py --elements-json <path> --id 30 --confirm  # 实点
```

## 如何触发

触发词：*截图并读按钮、屏幕上有哪些 UI 元素、找到 X 按钮并给坐标、点击这个桌面应用里的 OK 按钮、读屏幕、浏览器之外的 GUI 自动化。*

## 示例输出

`capture.py` 截计算器返回（节选）:

```json
{"id": 30, "type": "button", "label": "Seven", "automation_id": "num7Button",
 "source": "uia", "center": [337, 1047], "clickable": true, "patterns": ["Invoke"],
 "scale": 1.5, "origin": [0, 0]}
```

`click.py --elements-json <path> --id 30 --confirm` → `{"acted": true, "method": "invoke:Invoke"}`，点两次后显示区读出 `77`,一个闭环、程序可验证的结果（见 `tests/run_gate.py`）。

## 局限

- v0.1 **Windows 优先**。macOS/Linux 的截图 + OCR 可用，但其原生无障碍层（atomacos / AT-SPI）尚未接入（仅截图兜底）。Wayland 禁止静默截图。
- UIA 盲区（未加 `--force-renderer-accessibility` 的 Chromium/Electron、Qt、Canvas、游戏）需 OCR 兜底；重型视觉后端（OmniParser / grounding VLM）是延后的、用户自取的 stub（AGPL 权重不随仓打包,见 `reference/backends.md`）。
- 读取提权（UAC）窗口需同样以管理员身份运行 Python。

## 语言

中文 (`README_CN.md`) · English (`README.md`, 权威版)

## Roadmap · 贡献 · 许可

见 [ROADMAP.md](ROADMAP.md) · [CONTRIBUTING.md](CONTRIBUTING.md) · [LICENSE](LICENSE)(MIT)。
