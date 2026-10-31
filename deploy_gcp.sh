#!/usr/bin/env bash
# =============================================================================
# GCP ALWAYS FREE TIER 24/7 AUTONOMOUS DEPLOYMENT SCRIPT
# Polymarket & Kalshi Dual-Track Weather Bot
# Target: e2-micro (1 vCPU, 1 GB RAM, 30 GB standard-pd) in us-central1 ($0/mo)
# =============================================================================
set -euo pipefail

# Configuration Defaults for GCP Always Free Tier
INSTANCE_NAME="${INSTANCE_NAME:-weather-bot-free}"
ZONE="${ZONE:-us-central1-a}"
REGION="${REGION:-us-central1}"
MACHINE_TYPE="e2-micro"
DISK_SIZE="30GB"
DISK_TYPE="pd-standard"
APP_DIR="/opt/weather-bot"

echo "============================================================"
echo "🛸 DEPLOYING WEATHER BOT TO GOOGLE CLOUD PLATFORM (GCP)"
echo "   Target: Always Free Tier ($0.00 / month forever)"
echo "   Instance: ${INSTANCE_NAME} (${MACHINE_TYPE} in ${ZONE})"
echo "============================================================"

# Mode check: Running inside the VM or running on local machine with gcloud
if [ -f "/etc/debian_version" ] && [ "${1:-}" == "--in-vm" ]; then
    echo ">> Executing In-VM Bootstrap on Linux VM..."

    # 1. Setup 2GB Swapfile (CRITICAL for e2-micro 1GB RAM stability)
    if [ ! -f /swapfile ]; then
        echo ">> Setting up 2GB Swap space for e2-micro memory headroom..."
        fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
        chmod 600 /swapfile
        mkswap /swapfile
        swapon /swapfile
        echo '/swapfile none swap sw 0 0' >> /etc/fstab
        echo ">> Swap configured successfully."
    else
        echo ">> Swap already configured."
    fi

    # 2. Install base system packages
    echo ">> Updating apt repositories and installing prerequisites..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq \
        python3 \
        python3-pip \
        python3-venv \
        build-essential \
        curl \
        git \
        ufw

    # 3. Setup application directory
    echo ">> Setting up application in ${APP_DIR}..."
    mkdir -p "${APP_DIR}"
    if [ -d "./backend" ]; then
        cp -r backend frontend run.py requirements.txt "${APP_DIR}/"
        if [ -f "trade_journal.jsonl" ]; then
            cp trade_journal.jsonl "${APP_DIR}/trade_journal.jsonl"
        fi
        if [ -f ".env" ]; then
            cp .env "${APP_DIR}/.env"
        fi
        if [ -f "kalshi_demo.key" ]; then
            cp kalshi_demo.key "${APP_DIR}/kalshi_demo.key"
        fi
    fi

    cd "${APP_DIR}"

    # 4. Create Python Virtual Environment
    if [ ! -d "venv" ]; then
        echo ">> Creating Python virtual environment..."
        python3 -m venv venv
    fi

    echo ">> Installing Python dependencies..."
    ./venv/bin/pip install --upgrade pip --quiet
    ./venv/bin/pip install -r requirements.txt --quiet

    # 5. Build Frontend (if node exists or prebuilt dist copied)
    if [ ! -d "frontend/dist" ] && command -v node >/dev/null 2>&1; then
        echo ">> Building frontend assets..."
        cd frontend && npm ci && npm run build && cd ..
    fi

    # 6. Ensure .env exists with default configuration
    if [ ! -f ".env" ]; then
        echo ">> Initializing .env configuration..."
        cat << 'EOF' > .env
PORT=8000
DATABASE_URL=sqlite:///./tradingbot.db
SIMULATION_MODE=false
WEATHER_ENABLED=true
WEATHER_SCAN_INTERVAL_SECONDS=300
WEATHER_SETTLEMENT_INTERVAL_SECONDS=1800
WEATHER_MIN_EDGE_THRESHOLD=0.08
WEATHER_PAPER_MIN_EDGE_THRESHOLD=0.03
WEATHER_MAX_ENTRY_PRICE=0.70
WEATHER_MAX_TRADE_SIZE=5.0
WEATHER_CITIES=nyc,chicago,miami,los_angeles,denver,austin,houston
KALSHI_ENABLED=true
KALSHI_USE_DEMO=true
KALSHI_EXECUTE_DEMO_ORDERS=true
KALSHI_SYNC_BALANCE=true
EOF
    fi

    # 7. Install and start systemd service for 24/7 auto-restart
    echo ">> Installing systemd 24/7 auto-restart service..."
    cat << 'EOF' > /etc/systemd/system/weather-bot.service
[Unit]
Description=Polymarket & Kalshi 24/7 Autonomous Weather & BTC Trading Bot
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/weather-bot
EnvironmentFile=/opt/weather-bot/.env
ExecStart=/opt/weather-bot/venv/bin/python run.py
Restart=always
RestartSec=5
KillSignal=SIGINT
TimeoutStopSec=30
StandardOutput=journal
StandardError=journal
SyslogIdentifier=weather-bot
LimitNOFILE=65536
MemoryMax=850M
MemoryHigh=750M

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable weather-bot.service
    systemctl restart weather-bot.service

    # 8. Firewall Configuration (Optional UFW within VM)
    if command -v ufw >/dev/null 2>&1; then
        ufw allow 22/tcp >/dev/null 2>&1 || true
        ufw allow 8000/tcp >/dev/null 2>&1 || true
        ufw --force enable >/dev/null 2>&1 || true
    fi

    echo "============================================================"
    echo "✅ IN-VM INSTALLATION COMPLETE!"
    echo "   Service Status: $(systemctl is-active weather-bot.service)"
    echo "   View Logs: journalctl -u weather-bot.service -f"
    echo "============================================================"
    exit 0
fi

# =============================================================================
# Local Mode: gcloud CLI Provisioning
# =============================================================================
if ! command -v gcloud >/dev/null 2>&1; then
    echo "⚠️  gcloud CLI not found on this machine."
    echo "   To deploy manually on an existing GCP VM, copy this repository to your VM and run:"
    echo "   sudo bash deploy_gcp.sh --in-vm"
    echo ""
    echo "   Or install Google Cloud SDK: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

PROJECT_ID=$(gcloud config get-value project 2>/dev/null || echo "")
if [ -z "${PROJECT_ID}" ] || [ "${PROJECT_ID}" == "(unset)" ]; then
    echo "❌ No active GCP project configured. Run 'gcloud init' or 'gcloud config set project <PROJECT_ID>'."
    exit 1
fi

echo ">> Active GCP Project: ${PROJECT_ID}"

# 1. Create Firewall Rule for HTTP and Web Dashboard (Port 8000)
echo ">> Ensuring firewall rule allows ingress on port 8000..."
if ! gcloud compute firewall-rules describe allow-weather-bot >/dev/null 2>&1; then
    gcloud compute firewall-rules create allow-weather-bot \
        --direction=INGRESS \
        --priority=1000 \
        --network=default \
        --action=ALLOW \
        --rules=tcp:8000,tcp:80 \
        --source-ranges=0.0.0.0/0 \
        --target-tags=weather-bot
    echo ">> Firewall rule 'allow-weather-bot' created."
else
    echo ">> Firewall rule already exists."
fi

# 2. Check if instance already exists
INSTANCE_EXISTS=$(gcloud compute instances list --filter="name=${INSTANCE_NAME} AND zone:${ZONE}" --format="value(name)" 2>/dev/null || true)

if [ -z "${INSTANCE_EXISTS}" ]; then
    echo ">> Provisioning Always Free tier VM instance (${MACHINE_TYPE} in ${ZONE})..."
    gcloud compute instances create "${INSTANCE_NAME}" \
        --project="${PROJECT_ID}" \
        --zone="${ZONE}" \
        --machine-type="${MACHINE_TYPE}" \
        --network-interface=network-tier=STANDARD,subnet=default \
        --maintenance-policy=MIGRATE \
        --provisioning-model=STANDARD \
        --boot-disk-size="${DISK_SIZE}" \
        --boot-disk-type="${DISK_TYPE}" \
        --boot-disk-device-name="${INSTANCE_NAME}" \
        --image-family=debian-12 \
        --image-project=debian-cloud \
        --tags=weather-bot,http-server
    echo ">> Instance created."
    echo ">> Waiting 20 seconds for SSH daemon to initialize..."
    sleep 20
else
    echo ">> Instance ${INSTANCE_NAME} already exists in ${ZONE}."
fi

EXTERNAL_IP=$(gcloud compute instances describe "${INSTANCE_NAME}" --zone="${ZONE}" --format="get(networkInterfaces[0].accessConfigs[0].natIP)")
echo ">> VM External IP: ${EXTERNAL_IP}"

# 3. Synchronize Repository Files to VM
echo ">> Synchronizing application files to ${INSTANCE_NAME}..."
FILES_TO_SCP="backend requirements.txt run.py deploy_gcp.sh"
if [ -f "trade_journal.jsonl" ]; then
    FILES_TO_SCP="${FILES_TO_SCP} trade_journal.jsonl"
fi
gcloud compute scp --zone="${ZONE}" --recurse \
    ${FILES_TO_SCP} \
    "${INSTANCE_NAME}:/tmp/weather-bot-src"

# Copy frontend/dist if available
if [ -d "frontend/dist" ]; then
    gcloud compute scp --zone="${ZONE}" --recurse \
        frontend/dist "${INSTANCE_NAME}:/tmp/weather-bot-src/frontend/dist"
fi

# Copy .env and kalshi keys if available
if [ -f ".env" ]; then
    gcloud compute scp --zone="${ZONE}" .env "${INSTANCE_NAME}:/tmp/weather-bot-src/.env"
fi
if [ -f "kalshi_demo.key" ]; then
    gcloud compute scp --zone="${ZONE}" kalshi_demo.key "${INSTANCE_NAME}:/tmp/weather-bot-src/kalshi_demo.key"
fi

# 4. Trigger In-VM installation via SSH
echo ">> Executing automated in-VM bootstrap..."
gcloud compute ssh --zone="${ZONE}" "${INSTANCE_NAME}" --command="
    sudo rm -rf /opt/weather-bot && sudo mkdir -p /opt/weather-bot &&
    sudo cp -r /tmp/weather-bot-src/* /opt/weather-bot/ &&
    cd /opt/weather-bot && sudo bash deploy_gcp.sh --in-vm
"

echo "============================================================"
echo "🎉 DEPLOYMENT SUCCEEDED!"
echo "   Your bot is running 24/7 on GCP Always Free Tier!"
echo "   Dashboard URL: http://${EXTERNAL_IP}:8000/"
echo "   Health Check:  http://${EXTERNAL_IP}:8000/api/health"
echo "   Monitor Logs:  gcloud compute ssh --zone=${ZONE} ${INSTANCE_NAME} --command='sudo journalctl -u weather-bot.service -f'"
echo "============================================================"
