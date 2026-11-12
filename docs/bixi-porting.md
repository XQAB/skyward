# Skyward 移植到小米 MIX Flip 2（bixi）—— 适配记录

> 本文是 **bixi 机型的单一真相源（single source of truth）**。
> README 只保留安装入口；`CHANGELOG-bixi.md` 保留逐版本的验证时间线；
> `devices/bixi.toml` 里的中文注释保留现场细节。三者冲突时，**以本文的决策为准**。
>
> 本文最初写在一篇外部对话文档《小米 Mix Flip 2（BIXI）Rec 构建所需补充内容》里，
> 现将其沉淀回仓库，避免知识散落在对话中。

---

## 0. 一句话结论

把通用 Rust recovery **Skyward** 移植到 MIX Flip 2，**90% 的工作不是"填参数"，而是
在 recovery 里手工重建 Android Secure World（TEE）整条信任链**：`qseecomd` →
`keymint` → `weaver` → secure element（ESE），以及让触摸/外屏/WLAN 在 recovery 环境下正确工作。

机型基线：`bixi` · SM8750（骁龙 8 Elite）· A/B + 动态分区 · `OS4.0.0.11.XOHCNXM`。

---

## 1. 覆盖范围

| 能力 | 状态 | 备注 |
| --- | --- | --- |
| 外屏显示与触摸 | ✅ 真机验证 | 一次只驱动一个面板；两屏同时驱动会重启 |
| 双击唤醒 / 外屏手势 | ✅ | 副屏 doze 到亮度 0 而非 blank，保留触摸 |
| 自动解密 / 记住密码 | ✅（0.65+） | AES-GCM 存 `/metadata/skyward/credential` |
| WLAN 合屏后读取 `sp-handle` | ✅（0.66+） | 复制 `locksettings.db` 再打开，让 SQLite 重放 WAL |
| /data、/sdcard、MTP | ✅ | MTP 要先开「文件传输」再解锁 /data：顺序是解密在前、插线在后，未解锁时页面会说明电脑为什么看不到东西 |
| 分区备份（全备份/关联备份/最小可开机集） | ✅ | LZ4 + `.img.lz4` + sidecar；可存内部或 U 盘 |
| AVB flags 可写 | ✅（偏实现） | 先备份四个 vbmeta，写入后报告前后差异 |
| 安装脚本 `7za`/`zstd`/`unzip`/`avbctl`/`resetprop` | ✅ | 内建到 recovery，按 argv[0] 分发 |
| 系统更新 / Skyward 自更新 | ✅ | 双源；6 个镜像；sha256 校验 |
| 镜像加速源 | ✅ | 检查与下载走不同加速源 |
| 自更新 | ✅ | 优先 `.img`，回退 `.zip` |
| **图案解锁 / 第二用户** | ❌ 已知限制 | recovery 里 gatekeeper 起不来（见 §5） |

---

## 2. 硬件与显示

- 主屏（内屏）：1224×2912，460 dpi，6.86″。密度取 `ro.miui.density.secondaryppi=460`，
  并非从屏幕推导出的「缩水值」。
- 圆角：`rounded_corner_radius = 134px`（overlay `DevicesAndroidOverlay.apk`）。
- `diagonal = 6.86`、`covers = true`（有副屏）。

### 关键结论：为什么一次只驱动一个面板

- 同时驱动两屏时，`atomic modeset` 使内屏 commit 超过 2000ms，**手机会重启**。
- 对副屏再拿一个 DRM fd 会返回 `EACCES`（13）。
- 因此 UI 只驱动一个面板，并跟随折叠状态切换。

副屏背光是 `panel1-backlight` / `dsi_display1`；关一个 CRTC 需先置 `CRTC_ID=None`
再 `ACTIVE=false`（只置 `ACTIVE=false` 会返回 `EINVAL`）。

---

## 3. 内核模块与触摸

`[modules]`
- 源：`vendor_boot`、`vendor_dlkm`、`vendor`、`system_dlkm`。
- 加载：`synaptics_tcm2`（内屏 Synaptics TCM）、`mitee_dlkm`（TEE）、`nxp-nci`（NFC ESE HAL）。

- 内屏触摸 IC 是 Synaptics **S3910**（`/dev/tcp*`），无 gesture/double-tap 节点；
  双击唤醒在 UI 层自行实现（写 `tpm-suspend-en/off` 会重启）。
- 副屏是 Goodix **GT9916K**（I2C，覆盖屏 1208×1392），固件在 `goodix_firmware_bixi.bin`，
  虚拟节点（input8/event8）无 DIREC，触摸在模式时读自 `/odm/lib64/libtouchreport.so`。
  副屏不能在开机加载：内屏关闭时把它切走，打开展开后内屏一键。

---

## 4. Secure World（TEE）服务链 —— 本机型最难的部分

在 recovery 里需按顺序拉起，缺一不可：

| 服务 | 作用 | 关键点 |
| --- | --- | --- |
| `qseecomd` | QSEE 通信守护 | `ready_property=vendor.sys.listeners.registered` |
| `vendor.qti.hardware.qseecom@1.0` | QSEE TA 中间件 | 以 `system` 运行，加 `drmrpc` 组 |
| `qwesd` | 小厂安全服务 | TEE 在握手前不响应任何请求 |
| `ssgtzd` | 把 modem 侧 TA 导入 Secure World | recovery init 不自建 socket，需 bind `/dev/socket/ssgtzd`；`WakeAlarm`/`BlockSuspend` |
| **keymint** | 唯一的密钥管理 | recovery 自带 lib64 在前，true system 的 lib64/bootstrap 在后 |
| **secure_element(ESE)** | 安全元件 | 走 `nfc`，service 不应被等待 |
| **weaver** | 每用户密钥在安全元件的槽位 | `WakeAlarm`，`/odm` + vendor 库 |
| `se_omapi` | OMAPI SE 服务 | 走 Android SE 而非 ssgtzd；需 `libbinder_ndk` + 两个 AIDL |

**依赖顺序（lib 优先级）**：recovery 自带 → true system。`bixi.toml` 中 keymint/weaver/se_omapi
的 `libraries` 都按「`/system/lib64` + `/odm/lib64` + `/mnt/system/.../bootstrap`」由前到后排列。

---

## 5. 已知限制：`user 999` / 图案解锁 / 第二用户

**结论：当前无法在 recovery 内打开非主用户数据，图案解锁不可用。**

原因（已在真机验证）：
- 缺 **SPU 服务** + 对应 **VINTF 条目**（system-native，recovery 的 `ld.config` 只有 default namespace，
  无法造出能用的 `spu_init`）。
- 实测报错：
  - `spu_init` → `Check failed: status == STATUS_OK`（KeymasterUtils::spu_init）后 abort；
  - service manager → `Could not find android.hardware.gatekeeper.IGatekeeper/default in the VINTF manifest`。
- 当前密码解锁走的是 **weaver（Bound:Weaver）**，不经过 gatekeeper，因此密码解锁不受影响；
  图案/第二用户因此暂不支持。

> 后续若要支持：需先解决 SPU + VINTF，再谈 gatekeeper。相关失败日志见 TOML 中被注释的
> `[[service]]` 处。**这是一个独立的长期 issue，不在本文展开。**

---

## 6. 安全：凭据存储与密钥派生（⚠️ 待加固）

- 打开 `/data` 的密码被 **AES-GCM 加密**后存于 `/metadata/skyward/credential`，
  密钥**从手机序列号派生**。
- 该密钥**非硬件绑定**、有一定可预测性，对一台自称「daily driver」的设备而言偏弱。
- 更稳妥的方向：改用已拉通的 **weaver** 做 hardare-bound 凭据，或在 TEE 内派生。

> **状态：TODO**。在加固完成前，请勿假定 `credential` 能抵抗具备序列号读取能力的攻击者。

---

## 7. WLAN / 固件 / 备份 / 抹除

- WLAN：Qualcomm **Peach**（`qca_cld3_peach_v2`）→ cnss2；需 `rfkill`（system_dlkm）。
  固件 `WCNSS_qcom_cfg.ini` 须给内核固件加载器 `wlan/qca_cld/peach_v2/...`（不能只放 `/etc/firmware`，
  否则 `wlan0` 起不来，报 `Failed to probe host driver, err=-1`）。
  MAC 在 persist `wlan/wlan_mac.bin`。
- `remember=true`：上次网络在 `/data/misc/wifi/skyward/joined`（0600），不置 false 否则每次开机都手动连。
- modem 分区：`model`（vendor 的固件）。
- 挂载 persist；`[backup]` 的 `efs` = `modemst1`/`modemst2`/`fsg`/`fsc`/`persist`；
  data 备份跳过 tzstorage/qtee/mitee/goodix/fpc/fingerprint/fpdata/mi_fp/secure_element。

---

## 8. stock 基线与构建

- stock：`OS4.0.0.11.XOHCNXM`，完整包（9.35GB）含 recovery 分区，地址已回 200。
- 构建产物需 `bixi_extra` 里的 8 个文件（recovery 侧的 HAL 声明与脚本：`se_omapi`、两个 NDK so、
  `android.se.omapi-service.xml`、`weaver-nxp.xml`、`bixi-sockets.rc`、`ueventd.rc`、`bixi-sdcard.sh`）；
  每个文件的出处与用途见 [`bixi_extra/SOURCES.md`](../bixi_extra/SOURCES.md)。

发行资产：
- `skyward-v1.0.0-bixi-OS4.0.11.XOHCNXM.img`（104857600 字节，直写 recovery 分区）
- 同名 `.zip`（同镜像压缩）

---

## 9. 版本时间线（摘要，详见 CHANGELOG-bixi.md）

| 版本 | 里程碑 |
| --- | --- |
| 0.44–0.47 | 外屏起步、调研，首个可用 stock `OS4.0.0.11.XOHCNXM` |
| 0.48 | 外屏显示 + 触摸锁定，首次成功发版 |
| 0.49–0.51 | 折叠态判定、单面板驱动策略、加速源接入下载 |
| 0.52–0.55 | 解密入口、密码输入、网络与校时 |
| 0.56–0.59 | 备份成型、MTP、日志导出 |
| 0.60–0.62 | 双击唤醒（首版，落点容差太严） |
| 0.63 | 「关于」页排版定稿；发版名改 `OS4.0.11.XOHCNXM` |
| 0.64 | 双击唤醒放宽判定，真机通过 |
| 0.65 | 记住密码生效（「进 rec 就自动解密」）；ramdisk 兼容 `.img.zst` 资产 |
| 0.66 | 分区可存 U 盘、最小可开机集、解密页独立删除、AVB 写后 diff、MTP 重新 offer |
| 0.66.01 | 自更新改优先 `.img`；首次同发 `.img`+`.zip` |
| 0.67 | 「Skyward 更新」页补加速源行；加速源扩到 6 档：**检查更新走代理，下载走你选的源** |
| **1.0.0** | 汇总以上全部，版本号锁定，README 与发版说明重写 |

---

## 10. 借鉴与来源

- 上游 [kirklin/skyward](https://github.com/kirklin/skyward)：Rust recovery 总体架构、UI、双系统、安装器。
- aurora fork：AVB「校验 + 修改」小节版式、先查后写的分步、BCB/启动说明、更新信息层级。
- Rirrory/skyward-for-haotian：折叠屏外屏「只驱动一个面板」的思路。
- [KernelSU](https://github.com/tiann/KernelSU) 的 `resetprop`：库执行与语义对齐（读/写系统 prop、不改属性内存、`-n`/`-v` 等），因安装脚本按 KernelSU 用法编写。
- 库执行语义：`7za`(7-Zip)、`zstd`、`unzip`(busybox `-p`)、`avbctl`(AOSP) 按 argv[0] 内建分发。

（中文版说明详见 `README.zh-CN.md`，时间线完整版见 `CHANGELOG-bixi.md`。）
