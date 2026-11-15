# Moondrop Dawn Pro 2 Safe Volume Guard (防轰耳安全音量补丁)

[![License: CC0-1.0](https://img.shields.io/badge/License-CC0_1.0-lightgrey.svg)](LICENSE)
[![Python: 3.6+](https://img.shields.io/badge/Python-3.6+-blue.svg)](https://www.python.org/)

适用于 **水月雨 破晓2 (Moondrop Dawn Pro 2)** 解码耳放小尾巴的固件音量安全保护修补器。

---

## 🎧 背景与问题 (The Problem)

水月雨 Dawn Pro 2 在部分使用场景（如掉电重连、异常复位、或 Flash 中的 UI 参数丢失）下，固件会回退到 **`0 dBFS` 全幅最大音量**：
* 3.5mm 单端满幅输出高达 **2.0 Vrms (+6.02 dBV)**
* 4.4mm 平衡满幅输出高达 **4.0 Vrms (+12.04 dBV)**

对于常见阻抗为 32Ω、灵敏度通常在 112~120 dB SPL/Vrms 的入耳式耳机（IEM），开机瞬间爆发的瞬态声压级可高达 **118 ~ 132 dB SPL**，极易造成**急性听力损伤**或损坏耳机单元。

---

## 🛡️ 保护机制与声学计算 (How It Works)

本补丁通过在固件启动初始化函数（`0x48010C8E`）中植入一个微型条件分支守卫：
* **若 Flash 中有保存的有效音量**：直接沿用用户的设定，完全不受影响；
* **若 Flash 未初始化、掉电丢失或复位为 0**：自动拦截并强制赋予初始安全音量 **`-64.0 dBFS`**（定点值 `0xC000`）。

### 电声声压级测算（以 32Ω 塞子为例）：
$$\text{Output SPL} = \text{Sensitivity (dB/V)} + 20\log_{10}(V_\text{max}) - \text{Attenuation}$$

* **3.5mm 单端 (2.0 Vrms, 115 dB/V 常见动圈)**：
  $$115 + 6.02 - 64.0 = \mathbf{57.0\text{ dB SPL}} \le 60\text{ dB SPL}$$（轻声耳语水平）
* **4.4mm 平衡 (4.0 Vrms, 112 dB/V 塞子)**：
  $$112 + 12.04 - 64.0 = \mathbf{59.0\text{ dB SPL}} \le 60\text{ dB SPL}$$
* **超高敏动铁塞 (122 dB/V)**：
  $$122 + 6.02 - 64.0 = \mathbf{64.0\text{ dB SPL}}$$（正常室内谈话水平，绝对安全）

### ❗ 原有量程是否受影响？
**完全不受影响，100% 保持满血推力。**
UAC 标准 Feature Unit 描述符与控制函数完全未动。日常插上 300Ω 高阻大耳时，你依然可以通过机身物理音量加减按键或系统滑块直接推到 **100% 满幅推力（0 dBFS）**。

---

## 📦 依赖的基础固件版本 (Required Base Firmware)

为了规避著作权纠纷，**本项目不包含任何官方专有固件二进制**。修补器需要在正版官方 v1.5 固件上执行修补。

在运行修补器前，请确保获取官方 v1.5 固件文件并放置在本项目根目录下：

| 属性 | 官方目标参数 |
|---|---|
| **固件版本** | **v1.5** (构建时间: `Nov 17 2025 13:50:18`) |
| **官方文件名** | `65Sh-9xMUd3Qnj5ZO-p65.bin` |
| **文件大小** | `225,351 字节` |
| **MD5 校验码** | `4976dc3570cd430921c0bb2fc946d94f` |
| **SHA-256 校验码** | `59f4afcb60fcf2cbb42cecb5b64dbc3696ebde95690819a943f8c9972c1ba109` |

> 修补脚本会自动对输入文件进行 SHA-256 校验，防止在错误的版本上打补丁。

---

## 🚀 使用方法 (Usage)

### 步骤 1：生成安全保护固件
将官方 `65Sh-9xMUd3Qnj5ZO-p65.bin` 放入本目录，执行：

```bash
python patch_firmware.py
```

执行完毕后将在当前目录下生成安全版固件：
* 文件名：`dawn_pro2_v1.5_safe_60dB.bin`
* 文件大小：`225,351 字节`
* SHA-256：`309a55346a27b84283648080051080d077f93103c934f322a5eee02ef3e91426`

整个 225 KB 固件中**仅修改了 9 个字节**（5 字节逻辑补丁 + 4 字节 HAMAO 头部校验和）。

---

### 步骤 2：烧录写入固件

将小尾巴插入电脑 USB 口，运行自动化烧录脚本：

```bash
# 安装轻量级 HID 依赖
pip install hidapi

# 运行一键烧录
python flash_firmware.py
```

烧录流程自动执行：
1. 发送 `UPGRADE_ENTER` 指令将设备切换至片上 Bootloader 模式（`USB20 0x0666:0x0888`）；
2. 自动握手并按 256 字节分片写入 CPU（133KB）和 EXT 分区；
3. CRC32 校验一致后发送复位指令，设备自动重启回声卡模式。

---

## 🔍 技术审计与安全性 (Technical Audit)

* **零变砖风险**：SPV4040 芯片采用独立的片上硬件 **Mask ROM Bootloader**（光刻硬件只读，无法擦除），即使刷入全空数据也能随时通过 USB DFU 重新刷入原版。
* **HAMAO sum8 校验闭环**：反编译并完整还原了固件头 CPU 代码段累加和校验算法，生成文件的 Checksum（`0x00B6F1FE`）完全通过片上 Bootloader 验证。
* **立体声平衡未动**：逆向确认并排除了声相平衡（Pan Balance）逻辑，左右声道完全对称平衡。

---

## 📄 许可证 (License)

本项目采用 **[Creative Commons Zero v1.0 Universal (CC0 1.0)](LICENSE)** 协议发布，自愿放弃相关著作权，贡献至公有领域（Public Domain）。任何人均可自由使用、修改、分发与集成。

---

## ⚖️ 免责声明 (Disclaimer)

* 本项目为第三方开源社区维护的技术工具，与成都水月雨科技有限公司（MOONDROP Co., Ltd.）或珠海普林芯驰科技有限公司无官方关联。
* 本仓库不包含任何原厂商受著作权保护的专有二进制代码。用户修补固件纯属个人行为，风险自负。
