# 非主用户（`user 999`）与图案解锁：结论与不修的原因（issue #1）

> 结论：**在本 fork 目前的基础设施下不可修**，不是「没做」，是「缺一整套 Secure World 前置」。
> 本文把已知事实、失败日志、以及「修它要动什么」写清，供以后上游补齐后再回来。

## 1. 现象

在 recovery 里用 `user 999`（图案 / 第二用户）打开 `/data` 会失败；主用户的**密码（PIN / 口令）**
解锁正常。所以这不是「解密坏了」，而是「某一条解锁路径根本没接上」。

## 2. 已确认的三个事实

1. **recovery 的 `ld.config` 只有 default namespace**，造不出能用的 `spu_init`。
2. 起 `spu_init` 立刻失败：
   `Check failed: status == STATUS_OK`（`KeymasterUtils::spu_init`）→ `abort`。
3. 起服务管理器时找不到 gatekeeper 的 VINTF 条目：
   `Could not find android.hardware.gatekeeper.IGatekeeper/default in the VINTF manifest`。

也就是说：`user 999` 要走 **gatekeeper**（图案/第二用户的凭据由它校验），而 bixi 的 recovery 里
gatekeeper 既没有 manifest 条目、它依赖的 SPU 也起不来。

## 3. 为什么主用户密码还能用

主用户走的是 **weaver**（`data.rs` 的 `Bound::Weaver`）：把锁屏密码派生出的 key 交给
`android.hardware.weaver.IWeaver/default` 去换 value，不经过 gatekeeper。
weaver 这条链在 bixi 上是拉通的（`weaver` 服务带 `WakeAlarm`、`/odm` + vendor 库，见
[`bixi-porting.md`](bixi-porting.md) §4），所以密码解锁不受影响——**图案这条路缺的是另一条链**。

## 4. 修它要动什么（工作量评估，不是排期）

| 要补的东西 | 说明 | 难点 |
| --- | --- | --- |
| `spu_init` 可执行 + 它要的 namespace | system-native 程序，依赖 recovery 里不存在的 namespace | 要改 recovery 的 `ld.config`（linker namespace 配置），并补齐它拉的 so |
| `android.hardware.gatekeeper.IGatekeeper` 的 VINTF 条目 | 服务管理器读 `manifest.xml` 才认这个接口 | 要把 gatekeeper HIDL 的 manifest 片段与 HAL 实现一起塞进 ramdisk，注意与 `system` 的分区放置冲突 |
| gatekeeper HAL 本体与它的依赖 | bixi 的这一份在 `vendor` 里，recovery 里没有 | 还要它的 `hwservicemanager` 命名空间、`libbinder` 等 |
| 真机验证 | 图案 / 第二用户两条路径都要跑；且不能把主用户密码路径弄坏 | 需要主人在场，且每次失败都可能把 `/data` 锁住 |

粗估：不是「加一个 service 条目」，是「在 recovery 里再造一套 Secure World 入口」，
与 bixi 现在这套「手工 TEE 链 + weaver」是两条并行方案，改动面和回归风险都不小。

## 5. 决定（本 fork）

- **不修**，作为已知限制写在 README 与 `bixi-porting.md` §5：**图案解锁与第二用户暂不支持，
  主用户请用 PIN / 密码。**
- 触发重开条件（任一满足再看）：上游在 recovery 侧补了 gatekeeper 的 VINTF 与 namespace 方案；
  或 bixi 的 `vendor` 里出现了能直接在 recovery 起的 SPU 服务。
- 届时的第一步不是改代码，而是先把本文第 2 节的三条日志在新基线上重跑一遍，确认缺的还是这三样。

## 6. 复现用到的命令（留档）

```sh
# 解锁后看服务管理器认不认 gatekeeper
su -c 'service list | grep -i gatekeeper'
su -c 'dmesg | grep -iE "spu_init|gatekeeper|vintf"'
# 看 recovery 的 linker namespace 配置
su -c 'cat /system/etc/ld.config.txt | head -40'
```
