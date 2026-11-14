# 小米推了新 OTA 之后，Skyward 怎么重新适配（issue #5 的预案）

> 目标：下次小米放新基线（例如 `OS4.0.3.0` 之后的下一版）时，照这张单子从上往下走一遍就有结论，
> 不用现场想。每条都写了「看什么」和「变了会怎样」。做过一次就把结果追加到
> [`bixi-porting.md`](bixi-porting.md) 的 §8/§9 与 `CHANGELOG-bixi.md`，别只留在对话里。

## 0. 先记三件事

- 新基线的完整版本号（`ro.build.version.incremental`）与 **full OTA 包名**；
- 包的 sha256 与字节数（手机上「文件管理 → 校验」就能看，或 `sha256sum`）；
- 这次是 **同基线补丁** 还是 **跨版本升级**——后者才需要走完下面全部。

## 1. 分区表先对一遍（最容易悄悄变）

```sh
lpdump --slot 0 > /tmp/lp_new.txt      # recovery 里
diff /tmp/lp_old.txt /tmp/lp_new.txt   # 与本仓库 docs 里记录的那一份对照
```

- 看：分区名、`size`、`extent` 起止，尤其 `super` / `userdata` / `metadata` / `recovery_a,b`；
- 变了会怎样：`devices/bixi.toml` 里按 `/dev/block/by-name/…` 取分区的地方会失效，
  备份/恢复/刷写全都指向旧尺寸；双系统按 extent 读写 super，也要跟着改。
- 本次两台机器对照的结果见仓库外记录 `lp_compare.txt`（`super → sda33`、`userdata → sda34`、
  `recovery_a/b → sde27/sde61`、`init_boot_a/b → sde29/sde63`）。

## 2. 关键镜像的哈希对照

在**装着当前系统的那一槽**上读，再和新包解出来的同名镜像比：

| 分区 | 为什么看它 |
| --- | --- |
| `boot` | 内核与 first-stage；变了要重跑模块加载 |
| `init_boot` | KernelSU 补丁在这里；变了 root 会丢，双系统切换也依赖它 |
| `vendor_boot` | `vendor_ramdisk` 里的 `.ko` 与 `bixi-sdcards` 脚本 |
| `dtbo` | 显示/触摸的 panel 配置；**变了就要重验外屏** |
| `vbmeta` | AVB flags 页按它读写；变了「关校验」的假设要重验 |
| `vbmeta_system` | 同上，system 侧 |

新包里的同名镜像用 payload 解包取（`payload.bin` 头部是**大端**：`CrAU` + `version` + `manifest_size`
+ `metadata_signature_size`，数据段起点因包而异；参考 1.0.4 那次把 `system_ext` 重组出来的做法）。

## 3. 固件与模块重新提取

- `vendor_dlkm` / `vendor` 里的 `.ko`：`synaptics_tcm2`（内屏触摸）、`mitee_dlkm`（TEE）、
  `nxp-nci`（NFC ESE HAL）、`rfkill`（WLAN 要它才起 `wlan0`）；
- WLAN 固件：`WCNSS_qcom_cfg.ini` 的加载路径必须给到 `wlan/qca_cld/peach_v2/…`，
  只放 `/etc/firmware` 会以 `Failed to probe host driver, err=-1` 失败；
- 副屏固件 `goodix_firmware_bixi.bin`；
- 变了会怎样：`devices/bixi.toml` 的 `[modules]` 名单与 `sources` 要跟着改。

## 4. TEE 服务链一条条重验

顺序不能乱：`qseecomd` → `vendor.qti.hardware.qseecom@1.0` → `qwesd` → `ssgtzd` →
`keymint` → `secure_element` → `weaver` → `se_omapi`。

- 验的最小手段：`skyward --weaver`（打印槽位数、key/value 字节数）；
- 再看 `ready_property`：`qseecomd` 是 `vendor.sys.listeners.registered`，`weaver` 走 `WakeAlarm`；
- **lib 优先级**永远是「recovery 自带 → true system」；新基线如果换了 `bootstrap` 路径或
  `libbinder_ndk` 版本，这七条的 `libraries` 全要重排。
- 变了会怎样：解密直接不工作（`data.rs` 的 `Bound::Weaver` 读不到值），表现为「密码对但打不开」。

## 5. 解密链路

- 看 `protector` 的两种绑定还在不在：`Bound::Weaver`（有 weaver 的机器）与
  `Bound::Secdiscardable`（配 gatekeeper）；
- 看 `/data/misc/vold` 的 protector 文件是否换了布局（`user.rs` 的 `WEAVER_SLOT_LAYOUT = 1`）；
- 变了会怎样：新系统的 `/data` 在老 recovery 里打不开，反之亦然——**先备份再试**。

## 6. 显示与触摸

- 内屏 1224×2912、460 dpi（`ro.miui.density.secondaryppi`）、圆角 134 px；
- 副屏 1208×1392，Goodix GT9916K，触摸在模式时读 `/odm/lib64/libtouchreport.so`；
- 一次只驱动一个面板（同时驱动会 `atomic modeset` 超 2000 ms 并重启）；
- `dtbo` 变了就重验这三条，别只看主屏能亮。

## 7. 两槽一致性（这次踩过的坑）

装整包到**非当前槽**之后，别只看 `boot` 写进去了：`init_boot` 可能没跟上
（本次 B 槽 `init_boot_b = b25fd911…` 与系统版本不同版，logo 循环；补 `init_boot_a` 后一次起机，
上游记录见 kirklin/skyward#59）。做法：装完读回两槽 `boot` / `init_boot` 的 sha256 再切槽。

## 8. 出包与验收

1. `Cargo.toml` 的 `[workspace.package] version` 先 bump，再打 tag（CI 的 `tag` job 会核对）；
2. CI 六 job 全绿（含桌面 `cargo test --workspace`、`cargo ndk clippy`）；
3. Release 四个资产：`.img`、`.zip`、`SHA256SUMS`、`.verify.txt`；
4. 真机：两槽 `recovery` 读回 sha256 = 资产值；进 rec 走一遍 **解密 → 备份 → 安装 → 双系统切换**；
5. 结论写进 `CHANGELOG-bixi.md` 对应版本段，并把本文改动的行追加到 §8/§9。

## 9. 不要做的事

- 不用 `fastboot flash recovery` 刷 100 MB 的 `.img`（会 `no link` 断链），从 root shell `dd`；
- 不在 `su -c "cmd < 文件"` 里做重定向（会以普通 shell 执行而 `Permission denied`），用管道；
- 不拿 `blockdev --getsize64` 读 by-name 符号链接（ioctl 报错），用 `wc -c`；
- 不清 COW 之前就动槽位（先看 `/metadata/ota/snapshots`、`state`、`/data/gsi/ota` 是否空）。
