# OpenClaw Infrastructure Scripts

Scripts for running OpenClaw as a persistent service on macOS.

## Architecture

```
~/openclaw/                     ← Fork (code, extensions, skills)
├── dist/index.js               ← Gateway entry point
├── extensions/                 ← Plugins (voice-call, camofox-browser, etc.)
├── skills/                     ← Skill definitions
└── scripts/                    ← This directory
    ├── start-gateway.sh        ← Gateway launcher
    ├── watchdog.sh             ← Health monitor + auto-recovery
    └── README.md               ← You are here

~/.openclaw/                    ← Data directory (managed by OpenClaw)
├── openclaw.json               ← Configuration
├── env                         ← Secret references for 1Password op run
├── workspace/                  ← Agent workspace (separate git repo)
├── sessions/                   ← Session history
├── logs/                       ← Gateway + watchdog logs
├── credentials/                ← Runtime credentials
├── cron/                       ← Cron job state
└── start-gateway.sh            ← Thin redirect → ~/openclaw/scripts/start-gateway.sh
```

## Setup on a New Machine

### 1. Clone the fork

```bash
git clone --recurse-submodules https://github.com/<your-user>/openclaw ~/openclaw
cd ~/openclaw && npm install && npm run build
```

### 2. Store 1Password Service Account token in Keychain

```bash
security add-generic-password -s "op-service-account" -a "openclaw" -w "<your-op-sa-token>" -U
```

### 3. Create env file

```bash
mkdir -p ~/.openclaw
cat > ~/.openclaw/env << 'EOF'
OPENAI_API_KEY=op://<vault>/OpenAI/credential
ELEVENLABS_API_KEY=op://<vault>/ElevenLabs/credential
# Add more as needed
EOF
```

### 4. Create config

```bash
# Run wizard or copy openclaw.json from backup
node ~/openclaw/dist/index.js doctor
```

### 5. Create redirect scripts

```bash
cat > ~/.openclaw/start-gateway.sh << 'EOF'
#!/bin/bash
exec ~/openclaw/scripts/start-gateway.sh "$@"
EOF
chmod +x ~/.openclaw/start-gateway.sh

cat > ~/.openclaw/watchdog.sh << 'EOF'
#!/bin/bash
exec ~/openclaw/scripts/watchdog.sh "$@"
EOF
chmod +x ~/.openclaw/watchdog.sh
```

### 6. Install LaunchAgents

```bash
# Gateway (starts on boot, restarts on crash)
cp ~/openclaw/scripts/launchagents/ai.openclaw.gateway.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.openclaw.gateway.plist

# Watchdog (health check every 60s)
cp ~/openclaw/scripts/launchagents/ai.openclaw.watchdog.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.openclaw.watchdog.plist
```

### 7. Verify

```bash
curl -s http://127.0.0.1:18789/health
```

## Secrets

| Secret                   | Storage                                          | Used by           |
| ------------------------ | ------------------------------------------------ | ----------------- |
| OP Service Account Token | macOS Keychain (`op-service-account`/`openclaw`) | start-gateway.sh  |
| All other API keys       | 1Password vault (via `op run`)                   | Gateway runtime   |
| Gateway auth token       | LaunchAgent env var                              | Gateway HTTP auth |

## Recovery

The watchdog checks `/health` every 60 seconds:

- **1 failure**: Logged, no action
- **2+ failures**: Config rolled back to `.bak`, gateway kickstarted
- **Process missing**: Re-bootstrapped via launchctl

## Updating

```bash
cd ~/openclaw
git pull --recurse-submodules
npm install && npm run build
launchctl kickstart -k gui/$(id -u)/ai.openclaw.gateway
```
