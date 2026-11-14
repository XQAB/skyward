# 双系统在 bixi 上的方案（issue #3，待真机验证）

> 结论：机制在树上（`crates/skyward-systems`）、桌面测试有，但 **bixi 一次真机都没跑过**。
> 本文只写「它是怎么工作的、会占用什么、bixi 上有哪些必须先确认的点、验收怎么做」，**不刷机**。

## 1. 它是怎么工作的（照着代码说话）

| 环节 | 事实 | 位置 |
| --- | --- | --- |
| 第二系统的根 | data 分区里的一块 area，按分区直读直写，不挂文件系统 | `install.rs::FOLDER = /data/skyward/systems`、`skyward-block::area` |
| 启动镜像集 | `boot` + `init_boot` 整套存在**另一块** area（store，3 个 entry 滚动保存） | `store.rs::ENTRIES = 3`、`OTHER = 2` |
| 切换改哪两个分区 | 只改「下次启动槽位」的 `boot` 与 `init_boot`，别的一个都不碰 | `switch.rs::restore` |
| 第二系统怎么起 | 用**主系统的 `vendor_boot` 和 `dtbo`**；它自己的 `init_boot` 里被塞进 Skyward 的程序，first stage 由 Skyward 接 | `store::restore(..., init_boot)`、`boot::with_program` |
| 状态 | `/metadata/skyward/systems.toml`，切换每一步先落盘，断电后下次启动 `resume` 补完 | `state.rs::PATH`、`switch.rs::resume` |
| 主系统启动集会不会丢 | 覆盖之前先把它存进 store 的另一个 entry，存完才算数 | `finish()` 里的 `store::save` |
| 空间怎么算 | `room() = data 空闲 − store − 一份 super − area 头`，root 可选 8/16/32/64/128/256 GB | `install.rs::room` / `sizes` |

## 2. 第二系统的包（zip）

```
system.toml     id / name / version / filesystem / init(= /sbin/init) / minimum(可选)
boot.img        引导内核（bootloader 直接起的那张）
rootfs.img      根文件系统镜像（ext4 等，按 filesystem 字段写着）
init_boot.img   可选：系统自带 first-stage ramdisk 时才有
```

## 3. 会占用什么

- `/data` 里两块 area：`root`（你选的大小）+ `store`（两槽 boot + init_boot 的若干份）；
- **两槽的 `boot` / `init_boot`**：切换时轮流占用——同一时刻只有一个槽装第二系统的启动集；
- 不动的：`vendor_boot`、`dtbo`、`recovery`、`vbmeta`、固件、`super`。

## 4. bixi 上必须先确认的六件事（真机前逐条过）

1. **`init_boot` 补丁**：bixi 现役 `init_boot` 带 KernelSU 补丁（两槽都是 `1cfa51ea…`）。
   第二系统的 `init_boot` 若不是同一基线，注入 Skyward 程序后还能不能被 bootloader 接受，要先验。
2. **外屏**：第二系统若是 Linux 类系统，panel 配置和触摸都不在它的 `boot.img` 里，
   合盖状态大概率黑屏、外屏无触摸。这是产品取舍，不是移植 bug——要先决定「第二系统要不要外屏」。
3. **`vendor_boot` / `dtbo` 共用**：主系统升级会换 `dtbo`，第二系统就起不来。
   store 里记了安装当时的 `vendor_boot` / `dtbo` 哈希，变了界面会提示「变了」，要重新安装或重存。
4. **`vbmeta` / 验证启动**：切换不碰 `vbmeta`，但 `boot` / `init_boot` 换成非签名内容后，
   若设备仍要求校验 `boot`，会拒绝起机。真机前先读两槽 `vbmeta` 的 flags（Skyward 的 AVB 页也能读）。
5. **TEE / 解密**：第二系统不共享 Android 的 TEE 链，但它不碰 `/data` 的文件系统（按 area 直读），
   不影响主系统解密——这一点理论上没耦合，仍要在切换后确认主系统还能解 data。
6. **空间**：`room()` 已经扣掉一份 `super`，但 bixi 的 `super` 不小；先看 `/data` 实际剩余，
   最小 8 GB 起，选中之后安装会按块对齐。

### 4.1 切换靠哪根线：boot control（配置里已经有）

「切槽」这个动作不是直接写 `misc`，而是走
`android.hardware.boot.IBootControl/default`（`crates/skyward-vab/src/boot.rs`，
`skyward/src/systems.rs`、`merge.rs`、`ui.rs` 都从它开）。

`devices/bixi.toml` 的最后一条 service 就是它：

```toml
[[service]]
path = "/vendor/bin/hw/android.hardware.boot-service.qti"
libraries = ["/system/lib64", "/vendor/lib64"]
ready_service = "android.hardware.boot.IBootControl/default"
user = "root"
```

所以真机前要确认的是**它能不能起来**，不是「要不要补这个服务」——
`mariusarva/skyward-pudding` 原本缺这一条，补上之后「下次启动」才读得到、
槽才切得动。我们这边若它没起来，界面会直接显示
「…is not running; the phone's boot control has to be started first」
（`crates/skyward-preview/src/main.rs:899` 就是这条文案的样本），
而不是悄悄切错槽。真机验的时候先看这一句在不在。


## 5. 切换与回退

- 入口：首页「双系统」；切换只改写下次启动槽位的 `boot` / `init_boot`；
- 回主系统：再切一次，主系统的启动集从 store 取回，哈希对得上才算成功；
- 断电：`state.switching` 在盘上，下次启动 `resume()` 补完，不会半途留在别的系统上；
- 卸载：area 归还、`systems.toml` 清空、两槽启动集回到主系统。

## 6. 验收清单（等主人点头再做，按顺序）

1. 先备份并记下两槽 `boot` / `init_boot` / `vbmeta` 的 sha256（`boot_hashes.txt` 已有基线）；
2. 装第二系统（最小 8 GB），确认 `/data` 剩余与界面显示一致；
3. 切过去：第二系统 init 起得来、外屏行为符合预期（黑屏也算结论，记下来）；
4. 切回主系统：`sys.boot_completed=1`、两槽 `boot` / `init_boot` 哈希回到安装前；
5. 断电演练：切换中途强制断电，再启动应自动补完（看 `/metadata/skyward/systems.toml` 里 `switching` 字段是否消化）；
6. 卸载第二系统：area 消失、`systems.toml` 清空、主系统仍能起机。

## 7. 明确不做

今晚不安装、不切换、不刷任何分区。等主人一句话。
