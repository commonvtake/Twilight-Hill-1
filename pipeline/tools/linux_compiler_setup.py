from pathlib import Path
import urllib.request
root=Path(__file__).resolve().parents[2];work=root/'tp_work'
for name,url in [('wibo-old','https://github.com/decompals/wibo/releases/download/0.6.16/wibo'),('qemu-i386','https://github.com/multiarch/qemu-user-static/releases/download/v7.2.0-1/qemu-i386-static')]:
 p=work/name
 if not p.exists():urllib.request.urlretrieve(url,p)
 p.chmod(0o755)
p=work/'compiler-wrapper.sh';p.write_text('#!/bin/sh\nexec "'+str(work/'qemu-i386')+'" "'+str(work/'wibo-old')+'" "$@"\n');p.chmod(0o755)
