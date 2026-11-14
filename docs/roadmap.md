# 路线图与可复现的打包

这一页记两件事：一版镜像是怎么从源码打出来的（换一台机器也能打出同一版），
以及校验报告为什么先给 stock 基线。两条都是照着别的 fork 的做法定的，来源
写在每节末尾。

## 一、在别的机器上原样打出一版

`.github/workflows/build.yml` 是最权威的那份；下面把它摊平成一组命令。前提：
Linux x86_64，或 Windows 上的 WSL2。要 **Rust 1.100.0**（`rust-toolchain.toml`
钉的版本）、**Android NDK r29**（`$ANDROID_NDK_HOME` 指到它）、`cargo-ndk`、
`zip`、`python3`。

```sh
rustup target add aarch64-linux-android
cargo install cargo-ndk --locked
```

三个产物（前两个交叉编译给手机，第三个是宿主上跑的打包装）：

```sh
# recovery 本体
cargo ndk -t arm64-v8a --platform 30 build --release --locked -p skyward
# 第二系统的第一个程序，静态：它先于任何库起来
RUSTFLAGS=-C target-feature=+crt-static \
  cargo ndk -t arm64-v8a --platform 30 build --release --locked \
  -p skyward-system-init --target-dir target/system-init
# 打包装
cargo build --release --locked -p skyward-pack
mkdir -p dist
cp target/aarch64-linux-android/release/skyward target/release/skyward-pack dist/
cp target/system-init/aarch64-linux-android/release/system-init dist/
```

拿 stock 的 recovery 分区（`devices/bixi.toml` 里有它的版本与 sha256）：

```sh
dist/skyward-pack stock --config devices/bixi.toml                  # 只说版本与 sha256
dist/skyward-pack stock --config devices/bixi.toml --out stock/recovery.img
echo "<上面说的 sha256>  stock/recovery.img" | sha256sum --check     # 对不上就重取
```

打包（`bixi_extra` 是 stock recovery 不自带、而手机自己的厂商程序要用的库）：

```sh
name="skyward-$(git rev-parse --short=7 HEAD)-bixi-<stock 版本>"
mkdir -p out
dist/skyward-pack recovery --stock stock/recovery.img \
  --binary dist/skyward --system-init dist/system-init \
  --config devices/bixi.toml \
  --font resources/fonts/MiSansVF.ttf \
  --mono resources/fonts/KirkMono-Regular.ttf \
  --mono-license resources/fonts/KirkMono-OFL.txt \
  --extra bixi_extra --out "out/$name.img"
```

校验、压缩、出校验和：

```sh
python3 tools/verify-release.py "out/$name.img" --config devices/bixi.toml \
  --extra bixi_extra --report "out/$name.verify.txt"
(cd out && zip -9 "$name.zip" "$name.img")
(cd out && sha256sum "$name.img" "$name.zip" > SHA256SUMS)
```

要发 release 时，`--version` 还得给：`python3 tools/verify-release.py ... --version <x.y.z>`，
打包时也一样（`skyward-pack recovery --version <x.y.z>`）。CI 只有在打 tag 时才
补这两个，平时分支上的产物按提交号命名。

**Windows 宿主**：交叉编译那两步必须在 WSL2 里跑（`cargo ndk` 要 Linux 上的
NDK 工具链），`tools/verify-release.py` 是纯 python3，Windows 原生就能跑——
v1.0.7 的 `58 passed / 0 warnings / 0 failed` 就是这么出来的。

来源：`ChuiShui233/realme-pineapple-skyward` `a15e7b29`（`docs(roadmap)`：记录首张
镜像、阻塞项解除与可复现的打包命令）。它把「能打出来」写进文档而不是只留在
CI 里，这一页照这个做法补的。

## 二、校验报告先给 stock 基线

`tools/verify-release.py` 报告的第一行现在是：

```
stock build: OS4.0.3.0.XOHCNXM, from devices/bixi.toml
```

先说是拿哪一版 stock 比的，往下才是逐项断言（boot header、ramdisk、AVB、条目
清单、ELF 依赖、SELinux 标签、版本号）。这样断言失败时，第一眼就能分开两种
情况：stock 那一版变了（小米推了 OTA，`devices/bixi.toml` 该更新），还是打包
这一侧错了（少了文件、链接断了）。

来源：`Max1937/skyward-a57` `5207c361`（`ci: show what the stock image looks like
before the kernel job`）。

## 三、浏览器

纯文本阅读器已经进 main：`crates/skyward-net/src/web.rs`（网页读取与解析）、
`Screen::Browser` 的页面与动作（地址、逐块排版、链接、前进后退、书签）、
书签随设置文件跨重启保留（`crates/skyward-ui/src/settings.rs`）。

主线五条——能打开、能输入地址、能滚、能前进后退、能存书签——都在。没做的：
表单不显示也不提交、图片只说位置不渲染、完整模式（外置 arm64 Chromium 插件）
不做，见 `docs/forks-borrowing.md` 第三节。

## 四、等真机的两条

- **OTA 覆盖后 recovery 是否还在**：步骤在 `docs/ota-survival.md`，结论写进
  issue #4，验完再关。真机操作等主人点头。
- **双系统**：方案与分区在 `docs/dual-boot-bixi.md`，上游的 dual boot 代码在库里
  但 bixi 没有真机验证过，结论写进 issue #3。同样等主人点头。
