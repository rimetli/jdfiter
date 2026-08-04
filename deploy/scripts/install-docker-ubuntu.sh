#!/usr/bin/env bash
# Install Docker Engine and the Docker Compose plugin from Docker's official APT repository.
# Run once on a fresh Ubuntu 22.04/24.04 server: sudo bash deploy/scripts/install-docker-ubuntu.sh
set -Eeuo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "请使用 sudo 执行：sudo bash deploy/scripts/install-docker-ubuntu.sh" >&2
  exit 1
fi

apt update
apt install -y ca-certificates curl gnupg
apt remove -y docker.io docker-compose docker-compose-v2 docker-doc podman-docker containerd runc || true

install -m 0755 -d /etc/apt/keyrings
if curl --retry 3 --retry-delay 2 -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc; then
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  cat >/etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
  apt update
  apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
else
  echo "无法访问 Docker 官方仓库，改用 Ubuntu 官方仓库中的 Docker。" >&2
  rm -f /etc/apt/sources.list.d/docker.sources /etc/apt/keyrings/docker.asc
  apt update
  apt install -y docker.io docker-compose-v2
fi
systemctl enable --now docker
docker compose version
echo "Docker 安装完成。"
