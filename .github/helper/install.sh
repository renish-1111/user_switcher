#!/bin/bash

set -e

# Fail if merge conflict markers are found
if grep -lr --exclude-dir=node_modules --exclude-dir=.git "^<<<<<<< " "${GITHUB_WORKSPACE}"; then
    echo "Found merge conflicts in workspace"
    exit 1
fi

cd ~ || exit

echo "Setting up system dependencies..."
sudo apt update
sudo apt remove -y mysql-server mysql-client || true
sudo apt install -y libcups2-dev redis-server mariadb-client libmariadb-dev

pip install --upgrade pip
pip install frappe-bench

FRAPPE_BRANCH="${FRAPPE_BRANCH:-develop}"
ERPNEXT_BRANCH="${ERPNEXT_BRANCH:-develop}"
INSTALL_ERPNEXT="${INSTALL_ERPNEXT:-1}"

echo "Cloning Frappe ($FRAPPE_BRANCH)..."
git clone "https://github.com/frappe/frappe" --branch "$FRAPPE_BRANCH" --depth 1 ~/frappe

echo "Initializing Bench..."
bench init --skip-assets --frappe-path ~/frappe --python "$(which python)" ~/frappe-bench

echo "Configuring Database & Site..."
mariadb --host 127.0.0.1 --port 3306 -u root -proot -e "
    SET GLOBAL character_set_server = 'utf8mb4';
    SET GLOBAL collation_server = 'utf8mb4_unicode_ci';
    CREATE USER IF NOT EXISTS 'test_frappe'@'localhost' IDENTIFIED BY 'test_frappe';
    CREATE DATABASE IF NOT EXISTS test_frappe;
    GRANT ALL PRIVILEGES ON \`test_frappe\`.* TO 'test_frappe'@'localhost';
    FLUSH PRIVILEGES;
"

mkdir -p ~/frappe-bench/sites/account.localhost
cp -r "${GITHUB_WORKSPACE}/.github/helper/site_config.json" ~/frappe-bench/sites/account.localhost/site_config.json

cd ~/frappe-bench || exit

# Disable unused background services in Procfile during CI
sed -i 's/watch:/# watch:/g' Procfile || true
sed -i 's/schedule:/# schedule:/g' Procfile || true
sed -i 's/socketio:/# socketio:/g' Procfile || true
sed -i 's/redis_socketio:/# redis_socketio:/g' Procfile || true

if [ "$INSTALL_ERPNEXT" = "1" ]; then
    echo "Installing ERPNext ($ERPNEXT_BRANCH)..."
    bench get-app erpnext --branch "$ERPNEXT_BRANCH" --resolve-deps
fi

echo "Installing user_switcher from workspace..."
bench get-app user_switcher "${GITHUB_WORKSPACE}"

echo "Installing dev requirements..."
bench setup requirements --dev

echo "Reinstalling site database..."
bench --site account.localhost reinstall --yes

if [ "$INSTALL_ERPNEXT" = "1" ]; then
    bench --verbose --site account.localhost install-app erpnext
fi

bench --verbose --site account.localhost install-app user_switcher

echo "Building assets..."
bench build --app user_switcher

echo "127.0.0.1 account.localhost" | sudo tee -a /etc/hosts

echo "Setup completed successfully."
