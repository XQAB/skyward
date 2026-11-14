# Skyward for bixi · 1.0.7

> 机型：小米 MIX Flip 2（`bixi`，SM8750 / `sun`，Android 17，A/B + 动态分区，现役系统 `OS4.0.0.11.XOHCNXM`，出包基线 `OS4.0.0.11.XOHCNXM`）
> 上游：[kirklin/skyward](https://github.com/kirklin/skyward)；本分支：[`bixi-cover-display-v2`](https://github.com/XQAB/skyward/tree/bixi-cover-display-v2)（PR #38）

## 1.0.7

1.0.6 只管点击的手感，这一版回到更新页，把「从哪儿下、怎么刷进去」这两件事交给手机自己判断。

| 项 | 状态 | 关键点 |
| --- | --- | --- |
| 镜像测速，最快的那个自动选中 | ✅ 已实现（待真机验证） | 新 `crates/skyward-net/src/mirror.rs`：`rate()` 用一次 `Range: bytes=0-…` 只取 256 KiB 并计时，得到这个镜像在这个网络上的字节/秒；拒答、超时、什么都不发的镜像得到错误而不是「最慢」，因为它是没答上来。`quickest()` 是纯算术：零跳过、其余取最大、相等取先出现的；第一个位置是「不加速」（文件直接走 GitHub），所以 GitHub 自己最快时就选回它。更新页在「在线更新」下面多一行「测速选出最快的镜像」，只在 GitHub 已答出「有比本机新的一版」之后出现，量的是这一版真正要下的那个 `link`，量完直接写回 `state.mirror`——接着点「下载并更新」就走它，不用再手动切换；六个全没答上来时保留用户原本的选择 |
| 本地挑镜像刷（第 4 项的另一半） | ✅ 已实现（待真机验证） | 更新页多一行「从内部存储刷入镜像」。data 分区没打开时照安装页的说法写「请先完成『解密』」并去解密页，已擦除写「data 分区已清除」。挑文件复用现成的 `Screen::Choose(Place::Storage)`，落点在 `App::install_file`：文件名是 Skyward 自己发布的那种（`skyward-…img` / `…zip`）就走 `write_skyward`——把 `skyward_job` 立起来、跳到更新页、交出 `Effect::WriteSkyward`；安装器那条路会把它当 boot 镜像、只写一个槽位，所以不能走。真正写盘的仍是 `updates::write`：先 `upgrade::check` 认这是不是本机的 Skyward 镜像，再写进下次启动那个槽位与另一个装有 Skyward 的槽位，写一段读回一段。`Task::Write` 不下载，也不删用户的文件 |
| 两处新增断言 | ✅ 桌面跑过 | `the_quickest_mirror_is_the_one_the_next_update_goes_through`：交出去的是 build 自己的 `link`、量的时候不会被点第二次、六个数里最快的被选中、全零时保留原选择、没有新版本时这一行不出现。`a_skyward_build_kept_in_storage_goes_into_the_recovery_partitions`：`skyward-…img` 交 `Effect::WriteSkyward` 且跳更新页、第二次被挡住、之后 `rom.zip` 仍交 `Effect::InstallFile`。`mirror.rs` 自己四条（纯算术，与真 TCP 服务器的 206／404／空包） |

`mirror.rs` 的四条与两条界面断言都由桌面 `cargo test --workspace` 真跑；`rate()` 与 `Task::Weigh`／`Task::Write` 的 Android 侧仍靠 `cargo ndk clippy` 看编译、靠真机看行为。

设备侧同期记录：B 槽已回到官方 `OS4.0.0.11.XOHCNXM`（`boot_completed=1`、`zygote running`、`verifiedbootstate=green`，root 与 11 个模块齐全）；两槽 `recovery` 已 `dd` 成 1.0.6 的裸镜像（写后读回 sha256 与 release 资产 `e22ce90c…fe086` 逐位一致）。1.0.7 上机就是把同一处再 dd 一次，用更新页的「从内部存储刷入镜像」也行。

## 1.0.6


1.0.5 让文件页能搜能排，这一版只动一下点击的手感：从「嗡」变成「嗒」，并且一下比一下重。

| 项 | 状态 | 关键点 |
| --- | --- | --- |
| 点击是「嗒」，不是「嗡」 | ✅ 已实现（待真机验证） | 移植 haotian `b5ff5344`＋`45a1a155`＋`68afec53` 的思路，按本 fork 的路线重做：haotian 是把正弦当 `FF_SINE` 周期效果交给驱动、包络写在 `ff_envelope` 里；本 fork 是自己造采样走 `FF_CUSTOM`，所以包络直接乘在样本上。一次点击从固定的 3.5 摆（约 20 ms）改成**跟着滑条 12→26 ms**：起头 1 ms 升到设定强度，末尾按长度的五分之二收回去，驱动摆 2 → 刹车 1.5 的比例没动。摆完了收回去，才是一下，而不是一阵 |
| 长度也带滑条 | ✅ 已实现（待真机验证） | 手指读的「多重」是拿到了多少摆动，所以 `click(position)` 现在同时给出强度与长度：`share()` 走 `click::share`（等步进），长度走 `click::length_of`（`LIGHT_CLICK_MS = 12` / `HEAVY_CLICK_MS = 26`）。`FF_CUSTOM` 的样本按每次点击的强度与长度现造，长度由样本数与采样率决定，`probe`、界面点击、设置页试听走的都是同一条 |
| 滑条等步进 | ✅ 已改 | 原来的 `share()` 是每格同一个倍数（每格同样分贝），手指读不出深浅；改成 `lightest + (strongest - lightest) * at`，每十分之一滑条是同样一点摆幅。`skyward-config` 的 `Strength` 文档同步改过 |
| 样本数学抽到桌面侧 | ✅ 已改 | 新 `crates/skyward-ui/src/click.rs`（`RATE`、`DRIVE_SWINGS`／`BRAKE_SWINGS`、`share`、`length_of`、`fade_of`、`made`、`envelope`），四条断言由桌面 `cargo test --workspace` 真跑：长度 12→26 单调、包络 8 样本升／56 样本落装得进 19 ms、驱动摆到满幅后翻向刹车、滑条等步进（每格 0.075）。这些原来全在 `crates/skyward/src/haptics.rs` 的 `#[cfg(test)]` 里，而 `haptics` 模块本身是 `#[cfg(target_os = "android")]`，桌面编不到——和 `creep.rs` 之前那次一样的假绿 |

`bixi` 的强度上限这次**没有提高**，仍是 `devices/bixi.toml` 的 `strength = { lightest = 0.25, strongest = 0.75 }`。haotian 把它抬到 `0.4 ~ 1.0` 是因为他那台机器两端都嫌弱；bixi 是 `qcom-hv-haptics`，满幅会不会打颤没验过，等真机试完再决定抬不抬。

`crates/skyward-ui` 的 `click.rs` 随桌面测试跑；`crates/skyward` 的 `haptics.rs` 改动仍靠 `cargo ndk clippy` 看编译、靠真机看手感——本机没有 Android 目标可编。

## 1.0.5

1.0.4 把装整包这条路修通了，这一版补两块天天用得上的：无线网不再在页面说出是哪个网络之前自己连一遍又被丢掉，文件页能搜、能按类型排。另带两条 CI 改动。

| 项 | 状态 | 关键点 |
| --- | --- | --- |
| 开机自动连记住的 WLAN | ✅ 已实现（待真机验证） | 移植 haotian `c2879da6`。症结：`wpa_supplicant` 一启动就被交到记住那个网络的密码，于是它在页面说出是哪个网络之前自己连上了；而这边只认「页面点了网络」之后的加入，supplicant 自发的那一次被丢弃——没人要 DHCP，页面一直说没连上。现在 `joining()` 在 `joined == None` 时收到 `Told::Connected` 就 `adopt()`：用 `STATUS-NO_EVENTS` 读回 `wpa_state == COMPLETED` 与 `ssid`，按 SSID 字节匹配记住的网络，然后像页面选网一样要地址；一个都没接住时每 `POLL`（5 秒）再看一次；页面上正常选网先接上的不再自己接（`joined.is_some()` 时不计入）。本 fork 原本没有 `saved`，是从 `KEPT`（`/data/misc/wifi/skyward/joined`）读 `SET_NETWORK` 的 body 行，现在读成 `Remembered { bodies, ssid, name, security }`，`ssid`／`key_mgmt` 两行缺一即不认；离开网络时清掉记住的，连上新的时重读一遍 |
| 文件页可搜索 | ✅ 已实现（待真机验证） | 底栏换成「搜索」与「排序」两个按钮。搜索打开后照搜索页的写法：输入框＋右侧取消圆钮，边输边筛（忽略大小写的子串匹配），行号跟着筛后的列表走，点哪行就开哪行；`Back` 在搜索开着时先关搜索；有结果时回车开第一条，没结果不动作。只在界面里，不碰底下 |
| 文件页可按类型排序 | ✅ 已实现（待真机验证） | 新 `crates/skyward-ui/src/sort.rs`，三种键 `Name`／`Modified`／`Kind` 轮转，**任何键都文件夹在前**（和手机自带文件管理器一致）。`Kind` 的分组照 `FileType` 的列表：压缩包 → 分区镜像 → 图片 → 视频 → 音频 → 安装包 → 文档 → 表格 → 演示 → PDF → 文本 → 代码 → 其它，设备与管道排最后，同组按名。任何键都以忽略大小写的名收尾、再用原名兜底，所以 `IMG_1` 与 `img_1` 挨着却不会比较相等，两次读出来的顺序一样，没有条目会丢或画两遍。`Modified` 新的在前，同一秒按大小分开 |
| 打 tag 先核对版本 | ✅ 已加 | `build.yml` 在 `check` 前插 `tag` job（`if: github.ref_type == 'tag'`）：`python3 -c` 读 `tomllib` 的 `["workspace"]["package"]["version"]`，与 `GITHUB_REF_NAME` 比对，不等就 `::error` 并 `exit 1`；`release` 的 `needs` 已是 `[tag, check, recovery]`，`tools` 里 `sed` 那步留作保险。流程不变：先 bump `Cargo.toml`、提交、再打 tag |
| 工具链钉到 1.100.0 | ✅ 已改 | `rust-toolchain.toml` 从跟着 `stable` 漂改成 `channel = "1.100.0"`，本机与 CI 编的是同一个编译器（上游 0.3.1 也是这个版本） |

`crates/skyward-ui` 的这两块随桌面测试跑（`sort.rs` 七条、文件页几条，含「列表按名称排序后第几条是哪一条」）；`crates/skyward` 的 WLAN 改动仍靠 `cargo ndk clippy` 看编译、靠真机看行为——本机没有 Android 目标可编。

`1.0.5` 的资产：`skyward-v1.0.5-bixi-OS4.0.0.11.XOHCNXM.img`（裸镜像，直写 recovery 分区）、
同名 `.zip`（自更新可直接吃）、`SHA256SUMS`、`skyward-v1.0.5-bixi-OS4.0.0.11.XOHCNXM.verify.txt`（校验报告）。

## 1.0.4

1.0.3 只把「一条 prop 决定 rec 生死」止住了血，`system_ext` 整盘 `os error 95` 留给 issue #4。这版把它查到根、修好，并把「装整包会不会写回 recovery」的答案钉死。

| 项 | 状态 | 关键点 |
| --- | --- | --- |
| `system_ext` 整盘 `ENOTSUP` 的根因 | ✅ 定因 | 官方 `payload.bin` 是**大端**头（`CrAU` + `version >Q` + `manifest_size >Q` + `metadata_signature_size >I`，数据段起点 337614），按 protobuf 解 manifest 取 `system_ext` 的 392 个 op，重组出 820,465,664 B 干净镜像（erofs `root_nid=45 / inos=3712 / blocks=196538`，sha256 `1419004596972f…2d549f`）。设备上的 `system_ext_a` 按 super 元数据那 6 个 extent dump 成同样大小，按 8MB 分片逐片比对：**98 片里 97 片与官方包逐位一致，只有 part0（前 8MB）不一致**，而设备那份超级块是 `root_nid=43 / inos=3700 / blocks=195866`。→ 那个半写是一条**更早的中断更新**留下的，不是 4.0.3.0 干的：现场 dmesg（`dmesg-1.0.3-install-4.0.3.0.txt`）在 `[4.697484]` 就报了这块坏区，那时这台 rec 才开机 4.7 秒；4.0.3.0 的装包发生在 `[1354.279487]`。坏块在装包之前就已经在，那次装包没有写坏它，也没有覆盖到它。两槽共享前 5 段 extent，所以 A、B 的 `/etc` 一起坏，`framework` 不受影响 |
| 修复 | ✅ 真机验过 | 把干净镜像前 8MB（sha256 `9687c46e…d049`）`dd` 到 `/dev/block/sda33` 的 `seek=16631808 count=16384`，再读回同一区间，sha256 与写入逐位一致。随后清掉半截更新状态（`/metadata` 在 rec 里默认 **ro**，必须先 `mount -o remount,rw` 才能删，否则 `rm` 静默失败：`state`、`snapshots/*`、`snapshot-boot`、`/data/gsi/ota/*`） |
| 修好后的现场 | ✅ 真机验过 | 从 B 槽开机成功（`sys.boot_completed=1`、`ro.boot.slot_suffix=_b`、`OS4.0.0.11.XOHCNXM`）；`ro.system_ext.build.version.incremental` = `17OS4.0.260920.222807714.QCPECN.S`（1.0.3 那个「props 读不出来」的症状消失）；`/system_ext/etc` 87 项、`build.prop` 5894 B、`NOTICE.xml.gz` 202941 B |
| 新槽 logo 循环的真因 | ✅ 订正 1.0.2 的记录 | 前两次「装到非当前槽 → 重启新槽」停在 logo，不是快照没清、也不是槽位写错：基座上被半写的 `system_ext` 让 init 读不到 `/etc`，VABC 随后回滚。基座修好后同一个 B 槽直接起来了 |
| 装整包会不会写回 recovery（[issue #4](https://github.com/XQAB/skyward/issues/4)） | ✅ 有正向结果 | `keep_recovery=false` 时 dmesg 里既无 `the recovery partition does not hold Skyward` 也无 `written back to`，`recovery_b` 留原厂；开关打开后装 4.0.0.11 到 B，`recovery_a` 与 `recovery_b` 都是 `17d18608cb1193c4…449241`（Skyward 1.0.3，与装前基线相同），dmesg 三条：`left for the next start: snapshots Snapshotted, merge outstanding true` / `this recovery written back to [B]: Ok(())` / `Installed { slot: B, wipe: false }`。代码侧 `hold()` 传的是**当前运行槽**，不是 next |
| 写回失败的机制 | ✅ 已订正 | RO 分区上 `open(O_RDWR)` 不被拒（`count=0` 的 `dd` 能过），拒绝发生在 `write()`；`blockdev --setrw` 用 `O_RDONLY` 就能清旗标，所以「先 open 再 `make_writable`」的顺序本身没问题，1.0.2 的 bug 是 `make_writable(...).unwrap_or(false)` 把 `BLKROGET` 的失败吞了 |
| `make_writable` 三态 | ✅ 已合 | `Writable::{Already, Cleared, StillReadOnly}`：清完还是只读，不再被当成「本来就可写」 |
| props 读失败 | ✅ 已合 | 只对 EIO/超时类错误做 200 ms 有界重试（erofs inode 坏是稳定错误，重试只是白等）；About 页一行 `Unreadable{partition,file,error}`，带分区名与文件名 |
| 安装进度看得见 | ✅ 已实现（待真机验证） | 比例先取引擎的 `progress` 行，引擎还没说过话时取 fuse 已送字节；两者都经 `along(total, elapsed, counted)` 抬地板——**报过几个数之后再沉默，条子照样按已耗时往前爬**（60 s 时间常数向 90% 逼近并封顶），引擎给的真数字一旦更大就立刻接管，不会把真的 95% 压下去。函数在 `crates/skyward-install/src/creep.rs`，不设 `cfg(target_os = "android")` 门控，八条断言由桌面 `cargo test --workspace` 真跑（含「报过数后沉默不停」与「95% 不被压下」两条）。此前写在 `run.rs` 的 `#[cfg(test)]` 里，桌面测试永远编不到——那是假绿 |
| 整包会覆盖 `init_boot` | 📌 已知行为 | OTA 直写 boot/init_boot，不走快照；装完 KernelSU 的补丁就没了。重刷 `init_boot_a` / `init_boot_b` 即恢复（本次两槽各 8 MB，`fastboot flash` 均 `OKAY`，`su -v` = `3.3.1:KernelSU`） |

`1.0.4` 的资产：`skyward-v1.0.4-bixi-OS4.0.0.11.XOHCNXM.img`（裸镜像，直写 recovery 分区）、
同名 `.zip`（自更新可直接吃）、`SHA256SUMS`、`skyward-v1.0.4-bixi-OS4.0.0.11.XOHCNXM.verify.txt`（校验报告）。

## 1.0.3

1.0.2 刷进真机后进不了 rec：屏幕一直停在 logo，而 `adb` 看得见设备。真机实测主程序根本没起来：

```
skyward: devices not brought up: stat /mnt/system_ext/etc/build.prop: Operation not supported (os error 95)
skyward: recovery failed: stat /mnt/system_ext/etc/build.prop: ... (os error 95)
init: Service 'recovery' (pid 1438) exited with status 1
```

那次 `system_ext` 的 erofs 挂载整盘读不进去（`/mnt/system`、`/mnt/product` 同一时刻都正常），而 `installed_props` 只把「文件不存在」当正常，别的错误一律上抛成致命错误，于是一条 build.prop 读不到就能把整个 rec 带走。

| 项 | 状态 | 关键点 |
| --- | --- | --- |
| 一条 prop 决定 rec 生死 | ✅ 修（待真机复验） | `installed_props` 读 `build.prop` 遇到任何报错只往 kmsg 写一行（`… of … is unreadable: …`）并跳过，About 页少几条属性，rec 照常起来 |
| `system_ext` 整盘读不了 | ⏳ 留真机查 | 只降级、没解释：那一次挂载为什么会整盘 `os error 95`（Android 侧同一分区可读）仍在查，证据见 [issue #4](https://github.com/XQAB/skyward/issues/4) |

`1.0.3` 的资产：`skyward-v1.0.3-bixi-OS4.0.0.11.XOHCNXM.img`（裸镜像，直写 recovery 分区）、
同名 `.zip`（自更新可直接吃）、`SHA256SUMS`、`verify-report.txt`。

## 1.0.2

1.0.1 发出去后第一次拿官方整包做真机验收，暴露出两件事：装完 Skyward 写回 recovery 分区当场失败，以及装完的槽位起不来。这版修前者、把安装进度做成看得见的，后者只留诊断。

| 项 | 状态 | 关键点 |
| --- | --- | --- |
| 写回 recovery 分区失败 | ✅ 修（待真机复验） | 真机实测：装完 `blockdev --getro recovery_b` = **1**，`sha256` 是原厂值；现场 `blockdev --setrw` 后 `dd` 一次写成。根因是 `update_engine` 收尾后目标分区带只读旗标，而 `image::flash()` 只 `open(read+write)` 直写，内核回 `EPERM (os error 1)`。现在写前对每个目标分区 `BLKROSET(0)`（等价 `blockdev --setrw`），非 block 设备忽略；写失败时错误文案直接说「分区只读」，不再只有 `Operation not permitted` |
| 写回重试 | ✅ | 清只读后仍失败时等 0.8 s 再写一次（重试会重新清一遍只读），两次都失败才把首次原因一并报出 |
| 安装进度看得见 | ✅ | 屏幕本来就有「第 1/2/3 步，共 3 步 + 百分比」，但百分比只靠 fuse 已送出的字节推算；现在同时解析 `update_engine` 的 `progress <frac> <seconds>` 状态行，优先用引擎自报的比例，进度条按它走 |
| 装完后的状态留痕 | ✅ | 安装成功后在 kmsg 记一行 `install: left for the next start: snapshots …`（`/metadata/ota` 的快照状态 + 是否欠一次 merge），供「新槽起不来」排查 |
| 整包装完后新槽起不来 | ❌ 本版不修 | 真机实测：同支 `4.0.0.11` 与 `4.0.3.0` 两个整包装进 B 槽后，重启都停在 logo 循环；两槽的 `boot`/`vendor_boot`/`vbmeta`/`dtbo` 的 sha256 前 16 位完全相同，写错已排除。回旧槽启动后 `/metadata/ota/state` 被清成 0 字节、`snapshots/` 清空（`vendor.snapshot_clear`，退出 0），VABC 快照失效，目标槽从此不可启。根因未定，详见 [issue #4](https://github.com/XQAB/skyward/issues/4) |
| About 页出包基线对比 | ⏳ 留真机验收 | 与 1.0.1 相同，仍待真机确认 system 的挂载路径 |

`1.0.2` 的资产：`skyward-v1.0.2-bixi-OS4.0.0.11.XOHCNXM.img`（裸镜像，直写 recovery 分区）、
同名 `.zip`（自更新可直接吃）、`SHA256SUMS`、`verify-report.txt`。

## 1.0.1

1.0.0 之后的收尾版：不改正常使用路径上的行为，补上发布自检、文档，并把几个一直挂着的缺口关掉。

| 项 | 状态 | 关键点 |
| --- | --- | --- |
| 发版只认 sha256 | ✅ | v1.0.0 说明里的 MD5 表删掉，资产表全部换成资产 digest 的 sha256；此后校验只认 sha256 |
| `7za l` | ✅ | 按 7-Zip 的六列（`Date/Time`、`Attr`、`Size`、`Compressed`、`Name`）打印，末行合计 `N file(s), M folder(s)`，可按名字筛选，只读目录区；`.7z` 容器仍不做（要背一个 LZMA/LZMA2 解码器，这套 shim 只为从 zip 里取镜像，原因见「已知限制」） |
| MTP 未解锁提示 | ✅ | 文件传输开着而 `/data` 没解锁时，设置页直接说「电脑上看不到文件：data 还没解锁」，副标题给出顺序（先解密、后插线），点这一行进「解密」页；脚注随「文件传输开/关、data 解锁/未解锁」四种组合换文案 |
| `tools/verify-release.py` | ✅ 已进 CI | 打包后当场把镜像按 bootloader 的读法拆回去核一遍：boot v4 头（recovery 无 kernel）、LZ4 legacy ramdisk、newc 归档、`<codename>_extra` 每个文件逐字节、五个 `system/bin` 软链（`7za`/`zstd`/`unzip`/`avbctl`/`resetprop` → `recovery`）、镜像内 `Skyward <版本>` 串、`prop.default` 出包基线对 `[stock].version`、packer 设置与剥离的属性、extra 二进制的 `DT_NEEDED` 依赖闭包；报告随 img/zip 进 artifact。清单从 `<codename>_extra/` 生成，不认机型 |
| About 页出包基线对比 | ⏳ 留真机验收 | 本版没有动 UI：改之前要先在真机上确认 system 的挂载路径，留为下一版第一项 |
| 文档 | ✅ | `docs/bixi-porting.md`（bixi 移植记录的单一真相源）、`bixi_extra/SOURCES.md`（8 个 extra 文件的出处与用途） |

`1.0.1` 的资产：`skyward-v1.0.1-bixi-OS4.0.0.11.XOHCNXM.img`（裸镜像，直写 recovery 分区）、
同名 `.zip`（自更新可直接吃）、`SHA256SUMS`（两个资产的 sha256）、`verify-report.txt`（本版镜像的自检报告）。
资产名末段是 `[stock].version`（出包基线包），不是现役系统版本——这次的镜像是 `OS4.0.0.11.XOHCNXM` 基线出的。

## 1.0.0：这是第一个可以日常用的版本

从 0.44 到 0.67，这台机器上被逐项打通的是「折叠机 recovery 到底还缺什么」：外屏、触摸、解密、存储、备份、AVB、安装脚本、更新。1.0.0 不是又一个功能版，而是把这些拼成一条**完整链路**——进 recovery、看见界面、解开 /data、备份、改 AVB、装包、更新自己，全部走得通，且每一步都在真机上验过。

里程碑式的三条：

1. **外屏成为主力屏**。合盖状态下 recovery 现在是一块能看能点的外屏界面，不再是「翻开才能用」。
2. **解密无感**。记住一次密码后，之后每次进 recovery 自动解开 `/data`，`/sdcard`、MTP、备份、装包全部随之可用。
3. **能自己更新自己**。从 GitHub 发行取镜像、sha256 校验、写进下一个槽位的 recovery 分区；加速源可选，检查与下载可以走不同的镜像。

## 重要升级（1.0.0 视角）

| 能力 | 状态 | 关键点 |
| --- | --- | --- |
| 外屏显示与触摸 | ✅ 真机验过 | 只驱动一块面板；按折叠状态切换；触摸坐标按面板重算 |
| 双击亮屏 | ✅ 真机验过（0.64） | 用面板 doze 而非关屏，触摸控制器保持工作 |
| 自动解密 / 记住密码 | ✅ 真机验过（0.65） | AES-GCM 密文存 `/metadata/skyward/credential`，密钥由序列号派生 |
| WAL 合并后读 `sp-handle` | ✅ 真机验过（0.66） | 复制 `locksettings.db` 到临时目录再打开，让 `-wal` 真的重放 |
| `/data`、`/sdcard`、MTP | ✅ | 开机后台打开 `/data` 并绑定 `/sdcard`；先解锁再开文件传输 |
| 分区镜像 | ✅ | 全备（LZ4 + `.img.lz4` + sidecar）、关键分区、最小可开机集；可存内部存储或 U 盘 |
| AVB flags 可写 | ✅ 已实现（真机验待补） | 先备份四份 `vbmeta_*`，写后上报 `0x00 -> 0x03` 这类差值 |
| 安装脚本兼容 | ✅ 真机验过 | `7za`、`zstd`、`unzip`、`avbctl`、`resetprop` 都是 recovery 内建命令 |
| 双更新源 | ✅ | 系统更新（`update.miui.com`，答复加密）+ Skyward 更新（GitHub Releases） |
| 加速源 | ✅ | 6 档可选，更新页与下载页共用；检查走能转 API 的镜像，下载走你选的镜像 |
| 自更新 | ✅ | 优先裸 `.img`，退回 `.zip`；sha256 校验；写入下一个槽位与另一块装了 Skyward 的分区 |
| 启动指令页 | ✅ 真机验过（0.66） | 读 `misc` 里的 BCB，可单独清除，不动任何分区 |
| 关于页排版 | ✅ 定案（0.63） | 字标 45.0dp、三行 17.2dp、版本 15.4dp、基线 301.0 |

## 版本时间线

| 版本 | 主题 |
| --- | --- |
| 0.44–0.47 | 外屏起步、构建与刷入链路打通；发行资产名用 `OS4.0.0.11.XOHCNXM` |
| 0.48 | 外屏显示与触摸稳定下来，第一次成套发行 |
| 0.49–0.51 | 折叠状态判定、单面板驱动策略、加速源接入下载 |
| 0.52–0.55 | 解密页、密码输入、网络与校时 |
| 0.56–0.59 | 备份页成型（全备/关键分区）、MTP、日志导出 |
| 0.60–0.62 | 双击亮屏（第一版，落点容差太严） |
| 0.63 | 「关于」页排版定案；发行资产名改为 `OS4.0.11.XOHCNXM` |
| 0.64 | 双击亮屏放宽判定，真机通过 |
| 0.65 | 记住解密密码生效（「进 rec 就自动解锁了」）；ramdisk 兼容 `.img.zst` 资产 |
| 0.66 | 镜像可存 U 盘、最小可开机集、解密页单独删、AVB 写后 flags 差值、MTP 重复 offer 封版 |
| 0.66.01 | 自更新改为优先裸 `.img`；第一次同时挂 `.img` + `.zip` 两份资产 |
| 0.67 | 「Skyward 更新」页补加速源行；加速源扩到 6 档；**检查更新走代理，与下载分开策略** |
| **1.0.0** | 汇总以上全部，版本号落定，README 与发行说明重写 |
| **1.0.1** | 发版只认 sha256、`7za l`、MTP 未解锁提示、`verify-release.py` 进 CI、移植文档入库（About 基线对比留真机验收） |
| **1.0.4** | `system_ext` 半写根因定死并修好（只坏前 8MB）、装整包写回 recovery 有正向结果、`make_writable` 三态、About 标红不可读属性 |

## 逐项说明

### 外屏与显示

- 折叠机第二块面板不能与内屏同时驱动：两边都提交 atomic modeset 时，内屏 commit 会超过 2000ms 直接整机重启；另开一个 DRM fd 拿第二块屏则 `Permission denied (13)`。结论是**按折叠状态只驱动一块面板**。
- 外屏背光走 `panel1-backlight` / `dsi_display1`；只把 CRTC `ACTIVE=false` 会 `EINVAL`，必须先 `CRTC_ID=None` 解绑再关。
- 亮度滑块到 `max_brightness` 一半是正常的：`8191/16383` 就是这块屏的常规上限，不是 bug。
- 双击亮屏落地方式：熄屏走面板 doze（亮度 0）而不是真关屏，触摸控制器因此一直在工作——代价是整机不休眠，换来的才是双击能亮。

### 触摸与交互

- 触摸 IC 是 synaptics **S3910**（`/dev/tcm*`），没有任何 gesture / double-tap 节点；对 `goodix_ts` 或 synaptics 的 `tp-suspend-en/off` 直接写值会重启整机，所以双击只能自己在 UI 层做。
- 判定用「同一落点、容差放宽、抬手清第一下」，0.62 太严失败，0.64 放宽后真机通过。

### 解密与锁定

- 记住密码：成功解开 `/data` 时输入的密码被 AES-GCM 加密保存到 `/metadata/skyward/credential`，密钥由本机序列号派生，不写进设置文件；换手机解不开，关开关即删。之所以不用 TEE：recovery 无法让安全世界封装一个它没见过的密钥。
- WAL 合并：旧实现用 `file:…?immutable=1` 打开 `locksettings.db`，会忽略 `-wal`，读到的 `sp-handle` 是旧的。现在先把 `locksettings.db`（连同 `-wal`/`-shm`）复制到 `/data/local/tmp/skyward-locksettings-<pid>/` 再打开，让 SQLite 真的重放日志，实测读到了当前值。
- 解密页可以单独「删除已保存的密文」，并显示「保存于 年/月/日 时:分」。
- `user 999` 仍打不开：recovery 里 gatekeeper 起不来，这是老限制，不影响 user 0。

### 存储与传输

- 开机后台打开 `/data` 并绑定 `/sdcard`，否则 MTP 与备份都是空的。
- MTP 的顺序问题：先开「文件传输」再去解锁 `/data`，Windows 侧会看不到存储节点——必须先解锁。
- 无线 ADB 默认关闭；开启后 `adb connect 172.20.10.2:5555`，刷机前必须先 `adb disconnect`，否则双设备把脚本搞乱。

### 分区镜像与备份

- 「全部」逐个读、逐个用 LZ4 压成 `.img.lz4` 并存 sidecar `packed=lz4`；`super`、`data` 这类几个 G 的不在「全部」里。
- 「关键」= `boot`、`init_boot`、`vendor_boot`、`dtbo`、`vbmeta`、`vbmeta_system`、`persist`、`misc`。
- 「最小可开机集」= 只有 `boot`、`init_boot`、`vbmeta`、`dtbo`、`persist`、`misc` 的两槽，合起来几十兆。
- 「存到」在内部存储与 U 盘之间轮换（U 盘要插 OTG）；镜像统一落在 `Skyward/partitions`。
- 之前踩过：`persist`/`fsc`/`fsg` 这类运行时会被改写的分区，备份哈希与旧基线不一致是正常的，判断备份好坏要看它是否与**当前**分区一致。

### AVB

- 页面列出 `vbmeta_a/b`、`vbmeta_system_a/b` 的 flags 与签名算法（本机无 `vbmeta_vendor`）。
- 改动分两行：「关闭 verity 与 verification」与「恢复 verity 与 verification」，各自**点两次**（第一下上膛、第二下执行）。
- 动手前先把四份 `vbmeta_*-<时间戳>.img` 复制进镜像文件夹，可回退；写完把写前写后的 flags 差值报出来（例如 `vbmeta_a 0x00 -> 0x03`）。
- 关掉之后官方系统无法启动、官方 OTA 失败，部分应用与售后工具会读到这个状态——页面上直接写明。

### 安装

- 安装脚本里的 `7za`、`zstd`、`unzip`、`avbctl`、`resetprop` 不是外部二进制，而是 recovery 主程序按 `argv[0]` 分派的五个内建命令，ramdisk 里是五个软链。
- 脚本运行时 `PATH=/sbin:/system/bin:/system/xbin`，因此脚本里写 `7za e -so "$ZIPFILE" images/super.img.zst | zstd -d > "$OUT"` 就能直接跑通（真机实测 `7za x`、`7za e -so`、`zstd -d`、`resetprop` 读/写、`avbctl` 均可用）。
- `unzip -p` 边读边输出，避免把超大镜像整个读进内存；`zstd` 走 libzstd，支持 `-dcf` 直通。

### 更新与网络

- 两个更新源分得很清楚：
  1. 系统更新 → `https://update.miui.com/updates/miotaV3.php`，答复加密，用内置公钥解（`skyward-net/src/release.rs`）。镜像站不转这条，所以这一页**没有**加速源。
  2. Skyward 更新 → `https://api.github.com/repos/XQAB/skyward/releases/latest`，同时充当联网校时。
- 自更新的硬条件：tag 以 `v` 开头；资产名前缀 `skyward-{tag}-{codename}-`、后缀 `.zip` 或 `.img`；GitHub 给出 `sha256` digest。0.66.01 起**先找裸 `.img`，没有才退回 `.zip`**。
- 加速源 6 档：不加速 / `gh-proxy.com` / `gh-proxy.org` / `gh-proxy.cc` / `ghfast.top` / `github.akams.cn`，下载页与「Skyward 更新」页共用同一个选择，由 Keeper 定时落盘。
- **检查与下载分开**：`api.github.com` 只有 `gh-proxy.com`、`gh-proxy.org`、`gh-proxy.cc` 会转（`ghfast.top` 对接口 403、`github.akams.cn` 404）。所以检查更新会先走能转 API 的镜像，再兜底直连；下载则走你选的镜像——想要速度就选 ghfast。

### 界面与文案

- 署名三行：`Kirk Lin` / `&` / `一只小小小蜻蜓`。
- 状态栏要秒、要 USB 插线图标；键条三个一排。
- 「启动指令」页说明 `misc` 里的 BCB 是什么、清除只是抹掉那张便条。
- 鸟 log 统一 `skyward: …` 形式，导出日志页可一次取出。

### 构建

- 一个命令出整镜像：`skyward-pack recovery --stock recovery.img --binary … --system-init … --config devices/bixi.toml --font … --mono … --extra bixi_extra --out …`。
- `bixi_extra` 里 8 个文件补的是 recovery 缺的 HAL 声明与脚本（`se_omapi`、两个 NDK so、`android.se.omapi-service.xml`、`weaver-nxp.xml`、`bixi-sockets.rc`、`ueventd.rc`、`bixi-sdcard.sh`）。

## 借鉴与来源

- **上游** [kirklin/skyward](https://github.com/kirklin/skyward)：Rust 写 recovery 的整体架构、UI 框架、双系统、安装器骨架。本分支是在它之上做的机型适配。
- **aurora fork**：`AVB 校验` 页的版式与「改动」小节的分段（先准备、再执行）、BCB/启动指令页、更新页的信息层次，都参考了它的写法。原则是**只取读路径**，写路径（真正落 flags、落分区）自己重写并加备份。
- **Rinrroy/skyward-for-haotian**：折叠机外屏「只驱动一块面板」的思路参考；取源码走 `raw.githubusercontent.com` 经镜像站，避开本机 clone 不稳。
- **KernelSU 的 `resetprop`**：命令行与语义对齐它（读/写经 init、不改属性内存、`-n`/`-v` 照旧），因为安装脚本是按 KernelSU 的用法写的。
- **命令行语义**：`7za` 对齐 7-Zip（`x`/`e`/`l`/`-so`/`-o`/`-aoa`/`-aos`/`-r*`/`-bd`/`-mmt`，其中 `l` 的表头、列宽与合计行照 7-Zip 的列表输出），`zstd` 对齐 zstd 本体，`unzip` 对齐 busybox unzip 的 `-p`，`avbctl` 对齐 AOSP 的 `get-`/`disable-`/`enable-` 子命令与 `--force`。
- **AVB 规范**：flags 位（verity / verification）与「改 flags 会让签名失效」的判断来自 AVB 的公开文档。
- **镜像加速**：`gh-proxy` 系列（`gh-proxy.com` / `gh-proxy.org` / `gh-proxy.cc`）与 `ghfast.top`、`github.akams.cn`，实测数据见发行说明。

## 已知限制

- `user 999` 打不开（recovery 里 gatekeeper 起不来），不影响 user 0。
- 两块面板不能同时驱动，只能按折叠状态各驱动一块。
- 安装包只支持 zip；`7za` 的 `x`/`e`/`l` 都可用，但**不认 `.7z` 容器**：7z 用的是 LZMA/LZMA2 与它自己的容器格式（要再带一个 LZMA 解码器和容器解析），recovery 里这套 shim 只值当「把 zip 里的镜像取出来」，为它多背一个解码器不值。真要装 `.7z` 包，先在上位机转成 zip。
- 系统「在线更新」页没有加速源（镜像站不转 MIUI 的接口）。
- 自更新的裸 `.img` 分支在 0.67.00 → 0.67.01 这一跳上跑过，1.0.0 的完整结论见发行说明下方。
- 双击亮屏的代价是熄屏时整机不再休眠。
- `verify-release.py` 的出包基线比对：同一机型、同一条 OS 线的同一渠道码（例如包里的 recovery 是 `OS4.0.3.1.XPICN`、配置里是 `OS4.0.4.0.XPICNXM`）算 **warn** 并写明「包里的 recovery 建得比包本身早」；跨线（major.minor 或渠道码不同）才算 FAIL。
- `libbinder_ndk.so` 在 extra 里没有对应文件，自检只以 ELF `DT_NEEDED` 告警覆盖，没有硬性检查。

## 资产

- `skyward-v1.0.0-bixi-OS4.0.11.XOHCNXM.img` —— 裸镜像，104857600 字节，直接写 recovery 分区。
- `skyward-v1.0.0-bixi-OS4.0.11.XOHCNXM.zip` —— 同一个镜像压成的 zip。

校验值见发行页（GitHub 会给出每个资产的 `sha256`）。
