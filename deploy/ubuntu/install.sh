#!/bin/bash
set -Eeuo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
umask 027
[[ $EUID -eq 0 ]] || { echo 'Run this installer with sudo.' >&2; exit 77; }
[[ $# -eq 0 ]] || { echo 'Installer accepts no arguments.' >&2; exit 64; }
bundle=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
for file in exam-deploy exam_deploy.py exam-deploy.service exam-backend-release.conf; do
    [[ -f "$bundle/$file" && ! -L "$bundle/$file" ]] || exit 1
done
for tool in git python3 node npm mysql systemctl systemd-run runuser tar flock; do
    command -v "$tool" >/dev/null || { echo "Missing dependency: $tool" >&2; exit 1; }
done
id bhadmin >/dev/null
[[ $(systemctl show exam-backend.service -p User --value) == exam ]]
[[ -d /opt/apps/exam/.git && -x /opt/apps/exam/backend/.venv/bin/python ]]
[[ -f /etc/exam/backend.env && -f /etc/exam/mysql-backup.cnf ]]
[[ -L /var/www/apps/exam/current ]]
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
install -d -o root -g root -m 0755 /opt/apps/exam-releases /usr/local/lib/exam-deploy
install -d -o root -g bhadmin -m 0750 /var/lib/exam-deploy /var/lib/exam-deploy/history
install -o root -g root -m 0644 "$bundle/exam_deploy.py" /usr/local/lib/exam-deploy/exam_deploy.py
install -o root -g root -m 0755 "$bundle/exam-deploy" /usr/local/sbin/exam-deploy
install -o root -g root -m 0644 "$bundle/exam-deploy.service" /etc/systemd/system/exam-deploy.service
install -d -o root -g root -m 0755 /etc/systemd/system/exam-backend.service.d
install -o root -g root -m 0644 "$bundle/exam-backend-release.conf" /etc/systemd/system/exam-backend.service.d/30-release.conf
systemd-analyze verify /etc/systemd/system/exam-deploy.service
systemctl daemon-reload
echo 'INSTALLED: sudo /usr/local/sbin/exam-deploy'
echo 'No deployment or backend restart was performed by this installer.'
