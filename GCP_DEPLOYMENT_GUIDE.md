# 🌐 24/7 Free GCP Deployment Guide ($0.00 / month forever)

This guide walks you through deploying the **Prediction Market Trading Bot** for 24/7 continuous action on Google Cloud Platform's (GCP) **Always Free tier**.

---

## 💰 How is it $0 / Month Forever?

Google Cloud provides an [Always Free tier](https://cloud.google.com/free/docs/free-cloud-features#compute) that includes:
- **1 `e2-micro` VM instance** per month (1 vCPU, 1 GB memory).
- **30 GB Standard Persistent Disk (`pd-standard`)**.
- **1 GB egress** network traffic per month from North America to all regions (excluding China and Australia).
- Eligible free tier regions:
  - `us-central1` (Iowa)
  - `us-west1` (Oregon)
  - `us-east1` (South Carolina)

Because our application serves both the **FastAPI backend and React frontend** as a single service on port `8000`, a single `e2-micro` VM handles everything with zero external dependencies, zero paid databases, and zero monthly fees.

---

## 🚀 Option A: 1-Click Automated Deployment (`deploy_gcp.sh`)

If you have `gcloud` installed on your machine:

```bash
# 1. Log in to your GCP account
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# 2. Run the turnkey deploy script
chmod +x deploy_gcp.sh
./deploy_gcp.sh
```

The script will automatically:
1. Verify GCP project eligibility.
2. Create firewall rules for port `8000` (and port `80`).
3. Provision an `e2-micro` VM with a 30 GB standard persistent disk in `us-central1-a`.
4. Copy the repository, `.env`, and Kalshi keys to the VM.
5. Configure a **2GB swapfile** (preventing OOM errors on 1GB RAM).
6. Install Python 3, create a virtual environment, and install dependencies.
7. Configure and enable `systemd` (`weather-bot.service`) for 24/7 autonomous execution with instant crash auto-restart.

---

## 🛠️ Option B: Manual Setup on Any GCP VM

If you prefer creating the VM via the GCP Console or already have an instance:

### Step 1: Create the Free Tier VM
1. Go to the [Google Cloud Console](https://console.cloud.google.com/compute/instances).
2. Click **Create Instance**.
3. Set:
   - **Name**: `weather-bot-free`
   - **Region**: `us-central1` (Iowa), `us-west1` (Oregon), or `us-east1` (South Carolina)
   - **Zone**: Any zone in the selected region (e.g., `us-central1-a`)
   - **Series**: `E2`
   - **Machine type**: `e2-micro` (2 vCPUs, 1 GB memory)
   - **Boot disk**: Change to **Debian GNU/Linux 12 (bookworm)**, Disk type: **Standard persistent disk**, Size: **30 GB**.
   - **Firewall**: Check **Allow HTTP traffic** and add Network Tag `weather-bot`.
4. Click **Create**.

### Step 2: Open Port 8000 in GCP Firewall
In Google Cloud Console, navigate to **VPC Network** > **Firewall** > **Create Firewall Rule**:
- **Name**: `allow-weather-bot-8000`
- **Target tags**: `weather-bot`
- **Source IPv4 ranges**: `0.0.0.0/0`
- **Protocols and ports**: Specified protocols and ports -> `tcp: 8000`

### Step 3: Run In-VM Bootstrap
SSH into your VM (via GCP Console SSH button or `gcloud compute ssh weather-bot-free`):

```bash
# Clone or copy your bot into /opt/weather-bot
sudo git clone <YOUR_REPO_URL> /opt/weather-bot
cd /opt/weather-bot

# Run the in-VM automated setup
sudo bash deploy_gcp.sh --in-vm
```

---

## 🐳 Option C: Container Deployment (Cloud Run Free Tier or Docker)

The bot includes a production multi-stage `Dockerfile`.

GCP Cloud Run provides an Always Free tier:
- 2 million requests per month.
- 360,000 GB-seconds of memory and 180,000 vCPU-seconds per month.

### Deploy to Cloud Run:
```bash
# 1. Build and submit container image
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/weather-bot

# 2. Deploy to Cloud Run
gcloud run deploy weather-bot \
  --image gcr.io/YOUR_PROJECT_ID/weather-bot \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 512Mi \
  --port 8000
```

---

## ⚡ 24/7 Operations & Maintenance

### Check Service Status
```bash
sudo systemctl status weather-bot.service
```

### View Live Streaming Logs
```bash
sudo journalctl -u weather-bot.service -f
```

### Restart or Stop the Bot
```bash
# Restart
sudo systemctl restart weather-bot.service

# Stop
sudo systemctl stop weather-bot.service
```

### Accessing the Web Dashboard
Open your browser at:
```
http://<YOUR_VM_EXTERNAL_IP>:8000/
```
The React frontend is served directly by FastAPI alongside the real-time WebSocket connection (`/ws/events`).
