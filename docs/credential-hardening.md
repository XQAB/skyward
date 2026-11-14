# 凭据加固评估（issue #2）

> 对应 `crates/skyward/src/credential.rs` 与 `crates/skyward-crypto/src/credential.rs`。
> 本文是**评估与方案**，不含实现；动手前先在这一页上定稿。

## 0. 结论先行

- 「把凭据改成 **weaver 硬件绑定**」这条路，**用现在这条 HAL 走不通**：本 fork 的 weaver 客户端只有
  `getConfig` 与 `read` 两个调用，槽位里的 value 是用户注册时由 framework 写进去的，recovery 侧
  只能「拿 key 换 value」，**没有 write / seal / unseal**。
- 值得做的是**「默认不再把锁屏密码落盘」**：开关默认关，打开时把风险写在脸上；升级到新版本后，
  第一次成功解开 `/data` 就把旧文件删掉。
- 改动面：`skyward`（一处迁移、一处文案）、`skyward-ui`（设置页默认值与提示）、
  `skyward-crypto`（顶部注释改写），约 80 行代码 + 三条文案；不动分区格式、不动 weaver / gatekeeper。

## 1. 现状（可对照代码核对）

| 事项 | 位置 | 事实 |
| --- | --- | --- |
| 文件 | `crates/skyward/src/credential.rs` | `/metadata/skyward/credential`（同目录的 `credential.new` 先写再改名）；`save` / `load` / `forget` / `present` / `saved_at` |
| 记什么 | 同上 | 打开 `/data` 的那个**锁屏密码原文** |
| 什么时候写 | 设置页开关 | 只有「自动解密」开关打开才写；关掉即删 |
| 密钥 | `crates/skyward-crypto/src/credential.rs::key_of` | `SHA-256("skyward credential v1|" + 序列号 + "|" + 每次随机的 salt)`，AES-256-GCM |
| 序列号从哪来 | `credential.rs::serial` | `ro.serialno`，取不到再 `ro.boot.serialno` |
| 谁能打开 | — | 任何拿到这台机子、能读序列号的人。`getprop ro.serialno` 在 adb 与 fastboot 下都读得到 |

所以这个封印**不是边界，只是标记**：换一台手机打不开（salt + 序列号不同），
同一台手机换个人来读，一样打得开。对一台自称 daily driver 的机器，这是真问题。

## 2. 为什么「weaver 密封」不成立（按接口说话）

`crates/skyward-crypto/src/weaver.rs` 里只有两条调用：

- `GET_CONFIG = 1`：问槽位数、key 长度、value 长度；
- `READ = 2`：`read(slot, key) -> (status, timeout, value)`，key 不对就 `INCORRECT_KEY`、
  连续错就 `THROTTLE`（硬件记次、硬件拖延）。

也就是说 weaver 能做的是**「拿用户知道的 key 换 value，并且数错次数」**，
不是「把一段它没见过的数据封起来」。而 `data.rs` 里真正在用它：

```rust
(Bound::Weaver(slot), _) => {
    let key = crate::user::weaver_key(&stretched, weaver.config()?.key_bytes)?;   // stretched 来自锁屏密码
    let value = weaver.read(*slot, &key)?;
    (crate::user::weaver_protector_secret(&stretched, &value), None)
}
```

`stretched` 是从用户输入/已知的锁屏密码伸出来的。于是：

- 想「用 weaver 包住密码文件」，得先有 key；
- 想让 key 不含密码（否则等于还是要密码），就得让 key 从别处来；
- 从序列号来 = 现在这套（换汤不换药）；从 weaver 的另一个槽位来 = 又要读那个槽位，
  读它又要 key —— 循环。

**结论**：`crates/skyward-crypto/src/credential.rs` 顶部那句「weaver 可以 seal and unseal
without ever handing the key out」是错的，应当改写（替换文本见 §5）。

## 3. 四条路线对比

| 路线 | 做法 | 安全结果 | 改动面 | 体验 |
| --- | --- | --- | --- | --- |
| **A（推荐）** 默认关 + 迁移删除 | 开关默认 `false`；升级后第一次成功解开 `/data` 且开关是关的就 `forget()` | 机器上不再有明文密码；回到原厂语义「要开 data 就得输密码」 | 小 | 每次进 rec 输一次密码 |
| B 保留 opt-in | A 的基础上，打开时弹窗写明：文件里就是锁屏密码、密钥由序列号派生、拿到本机即可解开 | 用户知情后自选 | 小 | 愿意换便利的人自己开 |
| C KeyMint 授权绑定 | 用一把「需要 gatekeeper auth token」的 KeyMint 密钥封装（`data.rs::made_up_credential` 已是这个形状） | 不输密码就打不开——**这正是「自动解密」要避免的那一步** | 大：keymint 生成带 auth 的密钥、auth token 传递、失败面变宽 | 若要「一次开机内不再问」，与 A 差距很小 |
| D 改 weaver 绑定 | 见 §2 | 接口不允许 | 无解 | — |

C 值得记下来，但它的收益和 A 几乎重合：两者都要求「每次进 recovery 输一次锁屏密码」，
差别只在 C 之后同一会话内不用再输。为这点差别去动 KeyMint 授权链，风险大于收益。

## 4. 建议方案（A + B 的文案）

1. **默认值**：设置页「记住密码（进 rec 自动解密）」默认关。新装机不再产生这个文件。
2. **迁移**：`open_user_files` 成功之后，若 `credential::present()` 且开关为关，
   `credential::forget()`，并在 kmsg 记一行 `the kept credential was taken away`。
   覆盖 1.0.0–1.0.7 里开过这个开关的机器。
3. **打开时的文案**（三语，`lang.rs` 加常量）：
   - 中文：「把锁屏密码存在 /metadata 上，进 recovery 就不用再输。文件用这台手机的序列号派生的密钥加密：
     换一台手机打不开，但拿到这台手机的人能打开。确定要存？」
   - 英文 / 繁体同义，占位符集合为空，不触发 `lang.rs` 的占位符断言。
4. **不改的部分**：`Bound::Weaver` 解锁路径（weaver 保护的是「猜密码」这件事，key 每次都从密码派生，
   这条链没有洞）；`made_up_credential` 走 KeyMint + owner auth token，也没有洞。
5. **文档**：`docs/bixi-porting.md` §6 改为指向本文，删掉「改用 weaver 做 hardware-bound」那句。

## 5. `credential.rs` 顶部注释替换文本（实现时照抄）

```rust
//! Keeping what opened the data partition's users' own files, sealed with a
//! key this phone alone can derive: a file copied to another phone does not
//! open there, as the key is derived from this phone's serial number.
//!
//! What this does not protect against is someone holding this phone: they can
//! read the serial number and run the same code. The weaver this phone starts
//! cannot help - its interface only reads a value for a key the caller
//! already has (see `weaver.rs`), so a key made from the serial is the best a
//! recovery can do without asking for the lock credential itself. The
//! assessment and the way out are in `docs/credential-hardening.md`: keep
//! nothing by default, and say plainly what the file holds before keeping it.
```

## 6. 验证计划

- 桌面（`cargo test --workspace`）：
  - 现有三条（同一台机可开、换序列号打不开、改一字节打不开）不动；
  - 新增一条：不存在的文件 `load()` 报的是「没有保存」而不是解密失败（现在走的是 `fs::read` 的
    `read {FILE}` 上下文，要在 `skyward/src` 侧加一个 `present()` 前置判断的断言）。
- 真机（bixi，B 槽 `OS4.0.0.11.XOHCNXM`）：
  1. 开关关 → 进 rec → 必须输密码 → `/metadata/skyward/credential` 不存在；
  2. 开关开 → 存一次 → 重启进 rec 不再问密码；
  3. 关闭开关 → 文件立即消失（`forget()` 返回 true）；
  4. 升级路径：开关关着但文件在（模拟旧版本遗留）→ 第一次解开 `/data` 后文件消失。

## 7. 工作量

约半天：代码 ~80 行（1 个迁移分支 + 1 个默认值 + 1 个弹窗文案接进设置页）、文案 3 条、
桌面断言 1 条、真机 1 轮。不碰 `data.rs` 的解锁主流程，不碰 weaver / gatekeeper 服务。
