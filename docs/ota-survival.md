# 系统更新覆盖 recovery 之后，Skyward 还在不在（issue #4 的验证步骤）

> 这一段机制在 `crates/skyward-install/src/keep.rs`：装包之前先把**当前槽的 `recovery` 整块读进内存**、
> 记下两槽当时各是什么（sha256 + 是不是 Skyward），装完之后按「装完的现状」算出该写回哪些槽，
> 写回并逐块读回校验；第一次写入被 `EPERM` 拒掉时等 800 ms 再整块重写一次。
> 下面是把这件事在 bixi 上跑一遍的步骤。

## 0. 前置（缺一条就不要开始）

- 两槽 `recovery` 现在都是本机 Skyward（本机基线：v1.0.6，`e22ce90c…`）：
  `su -c 'sha256sum /dev/block/by-name/recovery_a /dev/block/by-name/recovery_b'`
- 设置页 **自动重新刷入 Skyward** 打开（默认就是开）；
- 手机插电、≥ 50%；
- 手上留一份裸镜像，路径记好：`/sdcard/shuaji/skyward-v1.0.6-bixi-OS4.0.0.11.XOHCNXM.img`。

## 1. 谁触发系统更新（**主人**，我不动手）

在系统里走小米自己的更新流程（或让 Skyward 装整包到「另一个槽位」），使更新**写出目标槽的 `recovery`**。
这一步结束后不要急着重启，先按第 2 步读回。

## 2. 看三处，判定「写回」成没成

| 看哪儿 | 命令 / 位置 | 成功的样子 |
| --- | --- | --- |
| 结果页 | Skyward 安装结果页 | 没有 `failed to write`；写回的槽列出来 |
| 内核日志 | `su -c 'dmesg \| grep -i skyward'` | `Skyward's build written to [A, B]: Ok(())` 这一类行（`slots` 是写回的槽） |
| 读回 | `su -c 'sha256sum /dev/block/by-name/recovery_a /dev/block/by-name/recovery_b'` | 被写回的那个槽 = 本机镜像的 sha256（`e22ce90c…`，1.0.7 之后换成 `53f3f17a…`） |

判定成功＝第 3 行两槽都是本机镜像，且日志里**没有** `failed twice` 字样。

## 3. 失败长什么样，怎么兜

- 日志里 `writing the recovery partitions failed twice; the first attempt: write /dev/block/by-name/recovery_b: …`
  → 两次都被拒：分区还没从「更新刚写完的只读」状态放开。**兜底**（我在任意能起机的槽上就能做）：

  ```sh
  su -c 'dd if=/sdcard/shuaji/skyward-v1.0.6-bixi-OS4.0.0.11.XOHCNXM.img \
          of=/dev/block/by-name/recovery_b bs=1048576'
  su -c 'sha256sum /dev/block/by-name/recovery_b'
  ```

- 两槽都写坏、系统也起不来：从**能起机的那个槽**起机后再写另一槽（bixi 不要在 `fastboot flash recovery`
  上赌，会在 100 MB 中途 `no link` 断链）。
- 只有「另一个槽」坏：切回能起机的槽起机，按上面一行写回即可。

## 4. 结论怎么写回 issue #4

把三样贴进 issue 并关掉：
1. 触发方式（系统更新 / Skyward 装整包到另一槽）与目标槽；
2. 结果页与 `dmesg` 里那一行原文；
3. 两槽 `sha256sum` 的读回结果。

## 5. 这次跑完还要顺手确认的两点

- 「自动重新刷入 Skyward」关掉时，同样的更新**应该**不写回——这是反向验证，别只验正向；
- 写回发生在 `next` 槽与「被写成非 Skyward」的槽；如果两槽原来都是 Skyward 且更新只写了 `next`，
  那就只有 `next` 被写回，别把「另一槽没动」当成失败。
