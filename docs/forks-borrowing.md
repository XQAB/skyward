# 别人的 skyward：哪些能搬过来

2026-11-15，扫的是 `kirklin/skyward` 的全部 forks（
`https://api.github.com/repos/kirklin/skyward/forks?sort=newest`，40 个，按 pushed
排）。结论先说：**新推送不等于新功能**——大多数 fork 的最新提交就是上游的
`c5e09f6e`（等模块加载的文件），再往上是 `cc68936f`（dada 的第二个 Peach
驱动）、`bd34c054`（release 0.3.1）、`b6965423`（Linux 宿主上编译 MTP）、
`684a2f43` 与 `0b4ee3ec`（UI 状态机拆分），也就是只跟了上游，自己没有任何
提交。判「只跟上游」要看**上游客栈的最近若干个提交**（至少八个，见第四节），
只比头三个会把新跟上的 fork 当成有独立工作。真正有自己的东西、值得读的只有
下面这几个：

| 仓库 | 分支 / 头 | 它自己的东西 |
| --- | --- | --- |
| `Jamvii/skyward-for-aurora` | `browser-v034` / `ce33a6bc` | 浏览器（文本阅读器 + 外置 Chromium 完整模式）、文件搜索、按类型排序、Magisk 模块页 |
| `Rinrroy/skyward-for-haotian` | `main` / `5e06f509` | 三语/主题/搜索排序之外：super 整包直刷、安装不再无限等、解密拒绝文案、预测式返回、触感时长、WLAN 自连、镜像回退顺序、暂停/续传/删除 |
| `Max1937/skyward-a57` | `main` / `3fc5dac7` | CI 拉自编内核、4.19 内核两段式 loop device、prima WLAN 的 kernel config fragment |
| `ChuiShui233/realme-pineapple-skyward` | `main` / `a15e7b29` | 打包工具宿主 Windows 可移植、`[stock]` 本地全量包、设备配置测试动态枚举、weaver 服务名放宽 |
| `BkaNeko/xaga-skyward` | `main` / `14781cce` | logd 以 root 起、从 stock 包里抽 recovery 所在分区、release 源由设备自己命名、clock offset |
| `Alittlejelly/skyward-for-MI10` | `main` / `42afe684` | 4.19 上重编 WLAN 驱动的一串兼容补丁 |
| `XuexGao/skyward` | `main` / `6f399fb4` | oppo 的 HIDL 服务目录与 binder 节点、`hwservicemanager` 从已装系统起 |
| `FireMapleHyper/skyward-firemaplehyper` | `main` / `ff1668fd` | 双系统的安装/切换/启动集恢复，以及文案 |
| `mariusarva/skyward-pudding` | `main`（基于上游 v0.2.0，迭代到 v0.2.52） | 小米 17（pudding）的 A/B 双槽适配：分区末尾补 AVB、gatekeeper blob 绑 weaver、补 boot control 服务、模块共用已加载集合、WLAN 自动连接与记住密码、触摸等待放宽 |
| `echoskies-works/skyward-extra` | `main`（活跃到 11-13） | 截图、banner 重绘、桌面模式、时钟/计时器页，以及「正在写的页面不因返回而放弃」 |


## 一、值得搬

### 1. 网页读取层 `skyward-net::web`（已搬）

来源 `Jamvii/skyward-for-aurora` @ `browser-v034`（头 `ce33a6bc`），文件
`crates/skyward-net/src/web.rs`（65 548 B，1 791 行）。它在那边是浏览器唯一一处
网络侧代码，演进链是 `224ac090`（加浏览器/文件搜索/模块）→ `56dc94aa`（持久
CDP 全页）→ `af99acbd`（原生滚动/视口帧）→ `d5604e72`（菜单/历史/书签）→
`3f1e8c8f`（表单内联 + JS 页回退）→ `45784226`（下 chromium 插件）→
`6c163943`（侧滑与预测式返回）→ `33cdb792`（全帧流 + 背压）→ `28a34829` 在
0.3.1 上重建 → `b9cf7a73` 0.3.5 那版。

搬的理由是它自足：除了 `crate::download::content_length` 与 `crate::Stopped`
不碰本 crate 别的模块，也不引入新依赖（同一个 `ureq` 3.5 + rustls）。我们已经
搬入：`15d3849`（整文件 + `lib.rs` 的 `pub mod web;`）、`49d03cf1`（clippy 指出的
一处多余借用）。它的两个测试（本地 127.0.0.1 起服务，一个读成页面、一个读成
文件并保存）随文件一起进来。

### 2. 浏览器页面（UI）：搬行为，不搬结构

来源同仓 `crates/skyward-ui/src/browser.rs`（67 863 B）与
`crates/skyward-ui/src/app/browser.rs`（26 934 B）。它那边的页面状态机在上游
0.3.1 之后已经拆成 `app/` 下的 27 个模块，我们是单体 `app.rs`（597 KB）+
`pages.rs`（292 KB），结构照搬不了。取的是它做出来的行为：地址栏（打字/粘贴/
清空）、文字页逐块排版、链接可点、前进后退、书签、菜单（历史/书签/下载）、
停止加载、把链接指向的文件交给下载。

### 3. 文件页的搜索与排序：取口径

来源 `Jamvii/skyward-for-aurora` 的 `b9cf7a73`（0.3.5 上的浏览器、文件页顶部
搜索、OTG 文件）。我们已经有 `Folder { query, sort, finding }`、`SortKey`、
`FileKind`，代码不用搬；要的是它的三条口径：文件夹恒在最前、每一种排序都是
**全序**（并列落到下一个键）、排序与搜索同一条 bar 上选。

### 4. 更新源的回退顺序：GitHub 先，镜像只在无应答时

来源 `Rinrroy/skyward-for-haotian` `main` 的 README「Online updates」与
`docs/releases/v0.3.2.md`（`5ee54c37`）。它的做法是：查和下载都先走 GitHub，
只有 GitHub 不应答时才试大陆镜像（gh-proxy / ghfast / ghproxy /
api.kkgithub.com），且镜像发来的东西仍要过 release 的 SHA-256。

我们现在是「用户在更新页选一档镜像」，`MIRRORS` 五档（`44a78993` 去掉
`github.akams.cn` 之后）。可以加一档「自动」：直连→失败→按测速结果挑镜像。
测速已经在（`Effect::WeighMirrors` + `mirror::SAMPLE`），只差把结论接回选择。

### 5. 下载的暂停/续传/删除

来源 `haotian` README 同段。我们的 `download::fetch` 本来就从 `.part` 的长度续，
`Sum::Unchecked` 也已经为「用户手输地址」准备好了，缺的是页面上的三个入口
（暂停=停、继续=再下、删除=删掉 `.part` 与成品）。这是纯 UI 工作。

### 6. 打包工具在 Windows 上能跑 + 设备配置测试动态枚举

来源 `ChuiShui233/realme-pineapple-skyward`：`9badf0a3`（`build(pack)`：宿主
（Windows）可移植 + `[stock]` 支持本地全量包）、`29b57e13`（Windows 交叉编译
脚本，NDK r29 + cargo-ndk）、`9e1ec684`（`devices/*.toml` 测试动态枚举）。
我们本机就是 Windows（`tools/verify-release.py` 一直在这跑），动态枚举能让我们
以后加机型不改测试。

### 7. 从 stock 包里抽出 recovery 所在的分区

来源 `BkaNeko/xaga-skyward` `cc3e4ca2`（`feat(stock)`）。它的口径是：recovery
在哪个分区由设备配置说，镜像从 stock 全量包里按这个分区名取。我们拼镜像时正
需要同一件事（bixi 是 `recovery_a` / `recovery_b`）。

### 8. logd 以 root 起

来源 `BkaNeko/xaga-skyward` `8f2a0800`（`feat(logd)`：手机自己的启动没起，
就以 root 起）。我们的日志页读内核日志，值得对照核对一次。

### 9. CI 先打印 stock 基线，再做断言

来源 `Max1937/skyward-a57` `5207c361`（`ci: show what the stock image looks
like before the kernel job`）。它的口径是：把要拿来比的 stock 那一面先原样
打印出来（版本、分区、长度），再把自编的产物对着它比；这样断言失败时第一
眼就知道是「stock 变了」还是「打包错了」，省掉一轮「到底是哪边不同」的
返工。我们的 `tools/verify-release.py` 也在比 stock 基线（`devices/bixi.toml`
的 `[stock] version`），已按这个顺序改：报告的第一行先说这一版是拿哪个
stock 比对的，再往下才是逐项检查。

### 10. roadmap 里写「可复现打包命令」

来源 `ChuiShui233/realme-pineapple-skyward` `a15e7b29`（`docs(roadmap)`：记录
首张镜像、阻塞项解除与可复现的打包命令）。我们此前只有 CI 里的 yml，没有一
页写「在别的机器上怎么原样打出来」。已经补进 `docs/roadmap.md`：从 stock 包
抽 recovery、编译三个产物、`skyward-pack recovery` 的完整命令行、校验、打包
与 sha256，以及 Windows 上要靠 WSL 的那几句。


### 11. 分区末尾补 AVB 结构（解不开 data 时先查布局）

来源 `mariusarva/skyward-pudding` 的 README（pudding 与 bixi 处境相近：上游同样把
它列在「施工中」、不解密，同样是 A/B 双槽）。它遇到的第一个坑不是密钥链，而是
**分区末尾没有 AVB 结构**：改成在原厂布局的位置补 AVB0（4096 对齐处、512 字节）
与 AVBf（分区末 64 字节），摘要取 `SHA256(镜像[0:L])`。

对我们的用法：bixi 若哪天出现「data 解不开」，**先按这条查布局，别一头扎进
密钥链**（issue #2 就是密钥链那条路）。我们的 `skyward-vab` 已经在读 AVB 页，
可以对照它的布局假设核一遍。

### 12. gatekeeper 绑定的 blob（换 weaver 之前先读）

来源同上。它记的口径是：用户 secret 绑在 Thales weaver 上、recovery 里解不开时，
**记录的保护者绑 weaver，就改用同目录带 `.secdis` + `.pwd` 的 gatekeeper 绑定
blob**。

这条跟 issue #2 是一体两面：我们打算把「从序列号派生」换成 weaver 硬件绑定，
换完 recovery 侧还能不能解，取决于它怎么读 gatekeeper blob。**先读它的做法，
再动手改密钥**（issue #2 的方案就是按这个顺序写的）。

### 13. 内核模块跨请求共用一个「已加载」集合

来源同上。它的坑是共享依赖的内核模块被 `insmod` 两次。我们双系统要加载另一套
模块时，第二次 `insmod` 会踩同一个问题：`skyward-modules` 该跨请求记住已经加载
过的名字，而不是每次从头装。

### 14. WLAN 起不来的重试与「记住密码」

来源同上。它实测「开 WLAN 到联网 19.4 秒降到 12.5 秒」，做法是：先等驱动建出
`/sys/class/net/wlan0` 再应答 ioctl，中间撞 `ENODEV` 就重试，整条起不来自动重开
最多 3 次；密码明文存 `/metadata/skyward/wlan`（0600）。我们 v1.0.5 的自连可以
对照这两处：重试次数与「等节点出现再说话」。

### 15. 触摸等待放宽到 10 秒

来源同上。面板后到会自己恢复触摸，等 10 秒再判定「没有面板」，不再误判。bixi
若偶尔报没面板，这一条就是原因。我们 `[touch]` 的等待值可以对一下。

### 16. 「正在写的页面不因返回而放弃」

来源 `echoskies-works/skyward-extra`（提交信息原文 `Leave a page that is writing
where it is, as going back does`）。这正是我们在 `Effect::OpenPage` 上刚修的那件
事：一次读在飞的时候，下一次读不该被拒，也不该被页面返回打断。它还有截图、
banner 重绘、桌面模式、时钟/计时器页——桌面模式（把页面从桌面打开）我们没有，
bixi 也没有外接显示器的场景，先记着不搬。


- **4.19 内核的两段式 loop device**：`Max1937/skyward-a57` `f2828a52`、`f9f75f58`。bixi 是 SM8750 的新内核，不需要按 4.19 的答法绑 loop。
- **自编内核 + prima WLAN 的 config fragment**：`Max1937` `880b0259`、`fd2d1432`、`3fc5dac7`。我们跟 stock 内核与它自己的模块走，不走重编内核这条路。
- **4.19 上重编 WLAN 驱动的一串兼容补丁**：`Alittlejelly/skyward-for-MI10` `42afe684`、`b9667cab`、`36c0e999`、`9c7877f5`、`e55995c8`、`33374f3c`、`7594fd93`、`74d5cd34`。同上，前提不成立。
- **oppo 的 HIDL 服务目录与 binder 节点**：`XuexGao/skyward` `6f399fb4`、`b2cd25f7`、`9152e023`。服务链是机型自己的，bixi 是小米 OS4，搬不过去。
- **放宽 weaver 服务名识别**：`ChuiShui233` `6689a436`。bixi 的服务名已确定；放宽只会把不该匹配的也匹上。（同一提交里「更新页机型属性名配置化」这一小点可另看，我们的 Specs 页也读机型属性。）
- **双系统的实现与文案**：`FireMapleHyper` `ff7655e2`、`2d2caa1b`、`1b3fa6ea`、`83cdf6f9`。我们自己的 `Screen::Systems` 已经能做装/切/删，只借它「切换前先把要保留那套的启动集写回」的次序。
- **pudding 的 `patches/` 不能直接打**：`mariusarva/skyward-pudding` 的补丁是相对
  上游 v0.2.0 的，我们在 v0.3.1 上重建过（`28a34829`），只能读代码挑逻辑，不能
  `git apply`。
- **pudding 的「补第六条 boot control 服务」在我们这儿不是同一件事**：它切槽是
  「请 bootloader 换槽」（`set_active` 那一路），缺
  `android.hardware.boot-service.qti` 就发不出请求；我们的双系统切换**直接写
  那个槽的 `boot` / `init_boot` 分区**（`switch.rs` 里没有 `bootctl` / `misc` /
  `set_active`），boot control 只用来**读**两槽状态与「下次启动是哪个槽」。
  `devices/bixi.toml` 的最后一条 service 就是它，所以 `bixi_extra` 不需要再加
  第三个 manifest；它起不来时界面报
  「…is not running; the phone's boot control has to be started first」，
  而不是猜一个槽去写（见 `docs/dual-boot-bixi.md` 4.1）。
- **桌面模式 / 截图 / banner**：`echoskies-works/skyward-extra` 这几项要外接显示器
  或桌面概念，bixi 没有这个场景。
- **super 整包直刷**：`haotian` 0.3.2 文档里的「super 镜像整包直刷：先 discard、4 MiB 一次写、三个窗口读回校验」。风险高，且 bixi 走 A/B 整包，不做。
- **上游 0.3.1 的三件事（omapi 服务、按系统分区起 keymint 的 programs、recovery 自己的对象注册进 servicemanager）**：面向「密钥槽在安全元件里」的机型（haotian）。bixi 的解锁链是 weaver + 序列号派生（见 issue #2），不需要 eSE 通道。

## 三、aurora 的「完整模式」：现在不碰

它把浏览器分两层：普通模式是纯文本阅读器（就是我们搬来的 `web.rs` + 它的
`browser.rs`）；完整模式要一个外置的 Linux arm64 Chromium 插件：

- 插件来自它自己的 release：`https://github.com/Jamvii/skyward-for-aurora/releases/latest/download/chromium.zip`；
- 落点 `/sdcard/Download/Skyward/chromium.zip`，也认 `/sdcard/Skyward/plugins/chromium.zip` 与 `chromium.tar.gz`；
- 解到 `/data/media/0/Skyward/plugins/chromium`，`run.sh` 用 Chromium 画页，输出 `/tmp/skyward-chromium.png`；
- 前提是 data 已经解密（插件在 `/data/media/0` 下），且本机 Cargo 里没有它的 websocket/CDP 客户端。

要在我们这版做，得先有自己的 arm64 chromium rootfs、签名与版本管理，今晚不做，
也不列为 1.x 目标。这一版先把纯文本阅读器做到「能打开、能输入、能滚、能前后、
能存书签」。

## 四、扫描口径（便于下次复查）

- fork 列表：`GET /repos/kirklin/skyward/forks?sort=newest&per_page=40`；
- **还要走一遍仓库搜索**：`GET /search/repositories?q=skyward+fork:true&per_page=100`
  （翻页到全）。它扫到的比 fork 列表多——fork 的 fork、改过名的、以及二次分叉
  （`mariusarva/skyward-pudding`、`echoskies-works/skyward-extra` 这两个就是这样
  找到的，都不在 40 个直接 fork 里）。两条路都走，再按「有没有自己的提交」筛；
- 有没有自己的提交：取每个 fork 的 `GET /repos/{fork}/commits?per_page=8`，与
  **上游客栈的最近八个提交**（`c5e09f6e` / `cc68936f` / `bd34c054` / `b6965423`
  / `684a2f43` / `0b4ee3ec` / `e5f3cf0c` / `31f3978a`）比对，全在这些里面就是
  「只跟上游」；只看头三个会漏掉后来才跟上的 fork（2026-11-14 那批 own=0 的
  就是头三个之外还多跟了 b6965423）。更稳的判法是 `merge-base`：fork 的
  `default_branch` 与上游 `main` 的最近公共祖先是上游 HEAD，就等于只跟上游；
- 分支结构（aurora 这种把特性放分支上的）：`GET /repos/{fork}/branches`；
- 逐提交看做了什么：`GET /repos/{fork}/commits?sha={branch}&per_page=30`。
