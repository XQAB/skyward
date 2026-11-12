#!/system/bin/sh
# Skyward 只在「用密码解开 CE 密钥」成功之后才把 /data/media/0 bind 到 /sdcard，
# 而电脑端的文件传输（MTP）对外共享的就是 /sdcard。bixi 的 weaver 依赖 OMAPI
# 服务（android.se.omapi.ISecureElementService/default），recovery 里没有这个
# 服务，密码路径走不通，于是 /sdcard 一直是空目录。
#
# 这里不去碰解密，只把 DE 部分（/data/media/0，不需要密码即可读）接上，
# 让 MTP 和 recovery 里的文件页能看到用户文件。
while true; do
    if mount | grep -q ' /data type ' ; then
        if ! mount | grep -q ' /sdcard ' ; then
            mount --bind /data/media/0 /sdcard 2>/dev/null
        fi
        break
    fi
    sleep 1
done
