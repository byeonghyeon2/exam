#!/bin/bash
set -Eeuo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
umask 027
[[ $EUID -eq 0 ]] || { echo 'Run this installer with sudo.' >&2; exit 77; }
[[ $# -eq 0 ]] || { echo 'Installer accepts no arguments.' >&2; exit 64; }
bundle=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# 설치는 도구와 서비스 설정만 갱신한다. 소스 배포/DB 변경/백엔드 재시작은 없다.
echo '[설치 1/4] 필수 파일·명령·기존 서버 구성 확인'
for file in exam-deploy exam_deploy.py exam-deploy.service exam-backend-release.conf exam-db-backup-monthly.conf exam-db-backup; do
    [[ -f "$bundle/$file" && ! -L "$bundle/$file" ]] || exit 1
done
for tool in git python3 node npm mysql systemctl systemd-run runuser tar flock cp find sort gzip sha256sum; do
    command -v "$tool" >/dev/null || { echo "Missing dependency: $tool" >&2; exit 1; }
done
id bhadmin >/dev/null
[[ $(systemctl show exam-backend.service -p User --value) == exam ]]
[[ -d /opt/apps/exam/.git && -x /opt/apps/exam/backend/.venv/bin/python ]]
[[ -f /etc/exam/backend.env && -f /etc/exam/mysql-backup.cnf ]]
[[ -L /var/www/apps/exam/current ]]
# 실행 중인 배포와 충돌하지 않도록 동일한 잠금을 사용한다.
echo '[설치 2/4] 배포 잠금 획득 및 실행 경로·빌드 계정 준비'
install -d -o root -g bhadmin -m 0750 /var/lib/exam-deploy /var/lib/exam-deploy/history
exec 9>/var/lib/exam-deploy/deploy.lock
flock -n 9 || { echo 'Deployment is active; installer refused.' >&2; exit 75; }
if [[ -e /opt/apps/exam-current || -L /opt/apps/exam-current ]]; then
    [[ -L /opt/apps/exam-current ]] || { echo 'Refusing to replace a real directory.' >&2; exit 1; }
    active=$(readlink -f /opt/apps/exam-current)
    case "$active" in
        /opt/apps/exam|/opt/apps/exam-releases/*) ;;
        *) echo 'Unexpected backend symlink target.' >&2; exit 1 ;;
    esac
else
    ln -s /opt/apps/exam /opt/apps/exam-current
fi
if ! id exam-build >/dev/null 2>&1; then
    useradd --system --user-group --create-home --home-dir /var/lib/exam-build --shell /usr/sbin/nologin exam-build
fi
[[ $(id -nG exam-build) == exam-build ]] || { echo 'Build account has unexpected groups.' >&2; exit 1; }
install -d -o exam-build -g exam-build -m 0700 /var/lib/exam-build
install -d -o root -g root -m 0755 /opt/apps/exam-releases /opt/apps/exam-python-envs /opt/apps/exam-node-envs /usr/local/lib/exam-deploy
install -d -o root -g bhadmin -m 0750 /var/lib/exam-deploy /var/lib/exam-deploy/history
echo '[설치 3/4] 배포 명령과 systemd 설정 설치'
install -o root -g root -m 0644 "$bundle/exam_deploy.py" /usr/local/lib/exam-deploy/exam_deploy.py
install -o root -g root -m 0755 "$bundle/exam-deploy" /usr/local/sbin/exam-deploy
install -o root -g root -m 0644 "$bundle/exam-deploy.service" /etc/systemd/system/exam-deploy.service
install -d -o root -g root -m 0755 /etc/systemd/system/exam-backend.service.d
install -o root -g root -m 0644 "$bundle/exam-backend-release.conf" /etc/systemd/system/exam-backend.service.d/30-release.conf
install -d -o root -g root -m 0755 /etc/systemd/system/exam-db-backup.timer.d
install -o root -g root -m 0644 "$bundle/exam-db-backup-monthly.conf" /etc/systemd/system/exam-db-backup.timer.d/30-monthly.conf
install -o root -g root -m 0750 "$bundle/exam-db-backup" /usr/local/sbin/exam-db-backup
/usr/local/sbin/exam-db-backup --prune-only
echo '[설치 4/4] systemd 설정 검증 및 다시 읽기 (백엔드 재시작 없음)'
systemd-analyze verify /etc/systemd/system/exam-deploy.service
systemctl daemon-reload
# 부팅 때 별도 백업을 실행하지 않고 월간 타이머로만 예약한다. 백업 데이터는 건드리지 않는다.
systemctl disable exam-db-backup.service
systemctl enable exam-db-backup.timer
systemctl restart exam-db-backup.timer
echo 'INSTALLED: sudo /usr/local/sbin/exam-deploy'
echo 'No deployment or backend restart was performed by this installer.'
echo 'DB backup: monthly on day 1, 03:20 Asia/Seoul (+ existing jitter); latest 3 sets retained.'
