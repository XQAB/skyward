# bixi_extra — 文件出处说明

本目录下的文件用于补齐 Skyward recovery 相对原厂 recovery 缺失的
HAL 声明与脚本，共 8 个（`tools/verify-release.py` 按本目录生成清单，
打包后逐个核对）。出处分两类。

## 提取自官方完整包

来源包：`bixi-ota_full-OS4.0.0.11.XOHCNXM-user-17.0-a2f3e2774c.zip`
（即 `devices/bixi.toml` 的 `[stock]` 段所指的那个包）。

| 文件 | 字节 | 说明 |
| --- | --- | --- |
| `system/bin/se_omapi` | 139136 | 官方的 OMAPI HAL 可执行文件；recovery 里 se_omapi 服务要靠它把请求送进安全元件，它是 weaver 那条链上的一环 |
| `system/lib64/android.hardware.secure-element-V1-ndk.so` | 137344 | secure_element HAL 的 NDK 接口库，se_omapi 的依赖 |
| `system/lib64/android.se.omapi-V1-ndk.so` | 140376 | OMAPI 的 NDK 接口库，se_omapi 的依赖 |
| `system/etc/ueventd.rc` | 3943 | 由官方 recovery 的 ueventd.rc 整理而来：保留它的 `/vendor`、`/odm` 两条 import，以及子系统与设备节点权限规则，只留 recovery 用得到的部分 |

`se_omapi` 与两个 `.so` 是字节照搬，换基线包时要整组替换，不能新旧混配。

## 为 recovery 手写

| 文件 | 字节 | 说明 |
| --- | --- | --- |
| `system/etc/vintf/manifest/android.se.omapi-service.xml` | 202 | 声明 `android.se.omapi ISecureElementService/default`（AIDL v1），service manager 才认这个服务 |
| `system/etc/vintf/weaver-nxp.xml` | 181 | 声明 `android.hardware.weaver IWeaver/default`（AIDL），weaver 的 VINTF 条目 |
| `system/etc/init/bixi-sockets.rc` | 984 | 两件事：early-init 把 `/dev/socket` 放开成 0777，让以 system 身份运行的 `ssgtzd` 自己 bind socket；再把 `bixi-sdcard.sh` 声明成 `disabled` 的 oneshot 服务并在 early-init 显式 `start`（recovery 的 init 不自己拉起 class 里的服务） |
| `system/bin/bixi-sdcard.sh` | 772 | 等 `/data` 挂上后把 DE 部分 `/data/media/0` bind 到 `/sdcard`，**不解密**；电脑的 MTP 与 recovery 的文件页读的都是 `/sdcard` |

## 使用限制

这些文件只随 Skyward recovery 打包进 recovery 分区使用，不用于
构建系统镜像，也不得单独分发用于其他用途。二进制文件的版本与
`[stock]` 指定的官方包对应；换基线包时按 issue「换 stock 包时的
重适配清单」重新提取核对。
