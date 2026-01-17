# GLaDOS TTS

# Default recipe shows available commands
default:
    @just --list

# Google Drive file ID for models (from https://github.com/R2D2FISH/glados-tts)
models_file_id := "1TRJtctjETgVVD5p7frSVPmgw8z8FFtjD"

# Install dependencies and download models
[group('setup')]
setup: install download-models
    @echo "Setup complete. Run 'just serve' to start the web server."

# Install Python dependencies with uv
[group('setup')]
install:
    uv venv
    uv pip install -r requirements.txt

# Download and extract models from Google Drive
[group('setup')]
download-models:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -d "models" ] && [ -f "models/glados-new.pt" ]; then
        echo "Models already downloaded"
        exit 0
    fi
    echo "Downloading models from Google Drive..."
    uv pip install gdown
    uv run gdown "{{models_file_id}}" -O models.zip
    echo "Extracting models..."
    unzip -o models.zip
    rm models.zip
    echo "Models ready"

# Start web server
[group('dev')]
serve:
    uv run python web/server.py

# Say something in GLaDOS's voice
[group('dev')]
say text:
    uv run python glados.py "{{text}}"

# Generate GLaDOS audio without playing (for visualizer use)
[group('dev')]
say-silent text:
    uv run python glados.py --no-play "{{text}}"

# Have GLaDOS respond to you (AI mode with Claude)
[group('dev')]
speak text:
    uv run python glados.py --ai "{{text}}"

# Clean up generated audio files
[group('dev')]
clean:
    rm -f output.wav glados-tts/output.wav
    rm -f web/audio/*.wav

# Build Docker image
[group('docker')]
docker-build:
    docker compose build

# Start Docker container
[group('docker')]
docker-up:
    docker compose up

# Start Docker container in background
[group('docker')]
docker-up-detached:
    docker compose up -d

# Stop Docker container
[group('docker')]
docker-down:
    docker compose down

# View Docker logs
[group('docker')]
docker-logs:
    docker compose logs -f

# === Voice Generator ===

# Setup voice generator (install Bun dependencies)
[group('voice')]
voice-setup:
    cd voice-generator && bun install
    mkdir -p voice-generator/data
    mkdir -p voice-generator/public/audio

# Start voice generator web server
[group('voice')]
voice-serve:
    cd voice-generator && bun run start

# Start voice generator web server (development mode with hot reload)
[group('voice')]
voice-dev:
    cd voice-generator && bun run dev

# Start voice generator TTS worker
[group('voice')]
voice-worker:
    uv run python voice-generator/worker/processor.py

# Start both voice generator services (web + worker)
[group('voice')]
voice-start:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Starting Voice Generator..."
    echo "Web server: http://localhost:3000"

    # Start worker in background
    uv run python voice-generator/worker/processor.py &
    WORKER_PID=$!

    # Trap to kill worker on exit
    trap "kill $WORKER_PID 2>/dev/null" EXIT

    # Start web server (foreground)
    cd voice-generator && bun run start

# Clean voice generator audio files and database
[group('voice')]
voice-clean:
    rm -f voice-generator/public/audio/*.wav
    rm -f voice-generator/data/glados-voice.db
    rm -f voice-generator/data/glados-voice.db-wal
    rm -f voice-generator/data/glados-voice.db-shm

# Build voice generator Docker image
[group('voice')]
voice-docker-build:
    cd voice-generator && docker compose build

# Start voice generator Docker container
[group('voice')]
voice-docker-up:
    cd voice-generator && docker compose up

# Start voice generator Docker container in background
[group('voice')]
voice-docker-up-detached:
    cd voice-generator && docker compose up -d

# Stop voice generator Docker container
[group('voice')]
voice-docker-down:
    cd voice-generator && docker compose down

# View voice generator Docker logs
[group('voice')]
voice-docker-logs:
    cd voice-generator && docker compose logs -f

# === GLaDOS Hooks (Node.js embedded) ===

# Run downloads watcher (Node.js)
[group('hooks')]
glados-watch-downloads:
    #!/usr/bin/env node
    const { execSync, spawnSync } = require('child_process');
    const fs = require('fs');
    const path = require('path');
    const os = require('os');

    const DOWNLOADS = path.join(os.homedir(), 'Downloads');
    const STATE_FILE = '/tmp/glados-downloads-processed.txt';
    const GLADOS_DIR = path.join(os.homedir(), 'code/glados');
    const RECEIPTS_BASE = path.join(os.homedir(),
        'Library/CloudStorage/GoogleDrive-helge.sverre@gmail.com/My Drive/Business/Liseth Solutions AS');

    const log = (msg) => console.log(`[${new Date().toISOString().slice(0,19).replace('T',' ')}] ${msg}`);
    const logDetail = (msg) => console.log(`[${new Date().toISOString().slice(0,19).replace('T',' ')}]   → ${msg}`);

    const gladosSay = (text) => {
        try { execSync(`just say "${text.replace(/"/g, '\\"')}"`, { cwd: GLADOS_DIR, stdio: 'pipe' }); }
        catch (e) { /* ignore */ }
    };

    const getProcessed = () => {
        try { return new Set(fs.readFileSync(STATE_FILE, 'utf8').split('\n').filter(Boolean)); }
        catch { return new Set(); }
    };

    const saveProcessed = (processed) => {
        fs.writeFileSync(STATE_FILE, [...processed].slice(-200).join('\n'));
    };

    const analyzePdf = (pdfPath) => {
        let text;
        try {
            text = execSync(`pdftotext "${pdfPath}" - 2>/dev/null`, { encoding: 'utf8', maxBuffer: 50*1024*1024 });
            text = text.replace(/\s+/g, ' ').slice(0, 10000);
        } catch { return null; }
        if (!text.trim()) return null;

        const prompt = `Analyze: receipt/invoice? JSON only: {"isReceiptOrInvoice":bool,"vendorHumanReadable":"str","shortSummary":"str","invoiceDate":"YYYY-MM-DD","recipientHumanFriendly":"str","proposedFileName":"str"}`;
        try {
            const result = spawnSync('claude', ['-p','--tools','','--output-format','text','--model','haiku',prompt],
                { input: text, encoding: 'utf8', maxBuffer: 10*1024*1024 });
            const match = result.stdout.replace(/\n/g,' ').match(/\{[^}]+\}/);
            return match ? JSON.parse(match[0]) : null;
        } catch { return null; }
    };

    log('═══════════════════════════════════════════════════════════');
    log('Downloads watcher triggered (Node.js)');

    const pdfs = fs.readdirSync(DOWNLOADS).filter(f => f.toLowerCase().endsWith('.pdf'));
    log(`Found ${pdfs.length} PDF(s) in Downloads`);
    if (pdfs.length === 0) { log('No PDFs to process'); process.exit(0); }

    const processed = getProcessed();

    for (const filename of pdfs) {
        const pdfPath = path.join(DOWNLOADS, filename);
        const stat = fs.statSync(pdfPath);
        const fileId = `${stat.ino}-${filename}`;

        if (processed.has(fileId)) { logDetail(`SKIP: ${filename}`); continue; }

        log(`───────────────────────────────────────────────────────────`);
        log(`Processing: ${filename}`);

        const data = analyzePdf(pdfPath);
        if (!data || !data.isReceiptOrInvoice) {
            logDetail('Not a receipt → skipping');
            processed.add(fileId);
            continue;
        }

        const vendor = data.vendorHumanReadable || 'Unknown';
        const recipient = data.recipientHumanFriendly || '';
        logDetail(`Receipt: ${vendor} → ${recipient}`);

        const isLiseth = /liseth/i.test(vendor + recipient);
        if (!isLiseth) {
            gladosSay(`A receipt from ${vendor}, not for Liseth. Your problem.`);
            processed.add(fileId);
            continue;
        }

        const year = (data.invoiceDate || '').slice(0,4) || new Date().getFullYear().toString();
        const destDir = path.join(RECEIPTS_BASE, year, 'Kvitteringer');
        if (!fs.existsSync(destDir)) fs.mkdirSync(destDir, { recursive: true });

        let destFilename = data.proposedFileName || `${(data.invoiceDate||'').replace(/-/g,'.')} - ${vendor}.pdf`;
        let destPath = path.join(destDir, destFilename);
        let isDuplicate = false;

        if (fs.existsSync(destPath)) {
            isDuplicate = true;
            const base = destFilename.replace(/\.pdf$/i, '');
            let n = 2;
            while (fs.existsSync(path.join(destDir, `${base} (${n}).pdf`))) n++;
            destFilename = `${base} (${n}).pdf`;
            destPath = path.join(destDir, destFilename);
        }

        fs.renameSync(pdfPath, destPath);
        log(`✓ FILED: ${destFilename}`);
        processed.add(fileId);

        gladosSay(isDuplicate
            ? 'Receipt already existed. Renamed it for you.'
            : `Receipt filed. ${data.shortSummary || 'Done'}.`);
    }

    saveProcessed(processed);
    log('═══════════════════════════════════════════════════════════');

# Analyze a specific PDF (Node.js)
[group('hooks')]
glados-analyze-pdf file:
    #!/usr/bin/env node
    const { execSync, spawnSync } = require('child_process');
    const file = '{{file}}';
    console.log(`Analyzing: ${file}`);
    const text = execSync(`pdftotext "${file}" -`, { encoding: 'utf8' }).replace(/\s+/g, ' ').slice(0, 8000);
    console.log(`Extracted ${text.length} chars\n`);
    const result = spawnSync('claude', ['-p','--tools','','--model','haiku',
        'Receipt/invoice? JSON: {"isReceiptOrInvoice":bool,"vendor":"str","recipient":"str","date":"str","amount":"str"}'],
        { input: text, encoding: 'utf8' });
    const match = result.stdout.match(/\{[\s\S]*?\}/);
    console.log(match ? JSON.parse(match[0]) : 'Could not parse');

# Check calendar for upcoming meetings (Node.js)
[group('hooks')]
glados-calendar-check:
    #!/usr/bin/env node
    const { execSync } = require('child_process');
    try {
        const events = execSync(
            `icalBuddy -n -nc -nrd -b "" eventsFrom:"$(date -v+9M '+%Y-%m-%d %H:%M:%S %z')" to:"$(date -v+11M '+%Y-%m-%d %H:%M:%S %z')"`,
            { encoding: 'utf8' }).trim();
        if (events) {
            const titles = events.split('\n').filter(l => !l.startsWith('    ')).join(', ');
            console.log(`Upcoming: ${titles}`);
            execSync(`just say "Meeting in 10 minutes. ${titles}."`);
        } else {
            console.log('No meetings in next 10 minutes');
        }
    } catch (e) { console.log('Calendar check failed:', e.message); }

# Check GitHub for failed actions (Node.js)
[group('hooks')]
glados-github-check:
    #!/usr/bin/env node
    const { execSync } = require('child_process');
    const fs = require('fs');
    const REPOS = ['HelgeSverre/jake'];
    const STATE = '/tmp/glados-gh-failures.txt';
    const processed = new Set(fs.existsSync(STATE) ? fs.readFileSync(STATE,'utf8').split('\n') : []);
    for (const repo of REPOS) {
        try {
            const failures = JSON.parse(execSync(
                `gh run list --repo ${repo} --status failure --limit 3 --json databaseId,displayTitle,workflowName`,
                { encoding: 'utf8' }));
            for (const f of failures) {
                if (processed.has(String(f.databaseId))) continue;
                console.log(`Failed: ${f.workflowName} - ${f.displayTitle}`);
                execSync(`just say "GitHub action failed. ${f.workflowName} in ${repo.split('/')[1]}."`);
                processed.add(String(f.databaseId));
                break;
            }
        } catch (e) { console.error(`Error: ${e.message}`); }
    }
    fs.writeFileSync(STATE, [...processed].slice(-100).join('\n'));

# === GLaDOS Visualizer ===

# Run aperture eye visualizer (watches glados-tts/output.wav)
[group('visualizer')]
viz:
    uv run python visualizer/aperture_eye.py

# Run aperture eye visualizer with specific audio file
[group('visualizer')]
viz-file file:
    uv run python visualizer/aperture_eye.py "{{file}}"

# Run audio-reactive orb visualizer
[group('visualizer')]
viz-orb:
    uv run python visualizer/audio_orb.py

# Say something and show visualizer (visualizer handles playback)
[group('visualizer')]
say-viz text:
    #!/usr/bin/env bash
    set -euo pipefail
    # Start visualizer in background
    uv run python visualizer/aperture_eye.py &
    VIZ_PID=$!
    sleep 1
    # Generate audio without playing (visualizer will play it)
    uv run python glados.py --no-play "{{text}}"
    sleep 3
    kill $VIZ_PID 2>/dev/null || true

